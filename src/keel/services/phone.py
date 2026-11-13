"""Phone alerts through Firebase or ntfy.

The owner picks one provider in settings. An empty provider, a missing
credential, or a failed handoff returns false and leaves the notice to retry.
"""

import base64
import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from email.header import Header
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.db.models import Notice, User
from keel.db.models.phone_device import PhoneDevice, PhoneTopic
from keel.db.models.user import utc_now
from keel.domain.enums import NotificationType
from keel.domain.errors import InvalidNotificationError, NotFoundError
from keel.settings import KeelSettings, get_settings

logger = logging.getLogger(__name__)

_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_COMMENT_TYPES = {
    NotificationType.COMMENT_ON_CREATED.value,
    NotificationType.COMMENT_ON_ASSIGNED.value,
}
_DELETE_TYPES = {
    NotificationType.DELETE_ON_CREATED.value,
    NotificationType.DELETE_ON_ASSIGNED.value,
}
_access: dict[str, tuple[str, float]] = {}
_warned = False


def deliver(session: Session, notice: Notice) -> bool:
    """Hand one due phone alert to the configured provider."""
    settings = get_settings()
    provider = settings.push_provider.strip().lower()
    try:
        if provider == "ntfy":
            return _ntfy(session, notice, settings)
        if provider == "fcm":
            return _fcm(session, notice, settings)
    except Exception:
        logger.exception("Phone alert for notice %s was not sent.", notice.id)
        return False
    _warn_once()
    return False


def setup(session: Session, user_id: int) -> tuple[str, str | None]:
    """The provider the server will use, and an ntfy subscribe URL when that is it."""
    settings = get_settings()
    provider = settings.push_provider.strip().lower()
    if provider == "ntfy":
        base = _ntfy_base(settings)
        if base is None:
            return "ntfy", None
        topic = ensure_topic(session, user_id)
        quoted = urllib.parse.quote(topic, safe="")
        return "ntfy", f"{base}/{quoted}"
    if provider == "fcm":
        return "fcm", None
    return "", None


def describe(provider: str, url: str | None) -> str:
    """The profile sentence that follows "Phone alert is saved here." """
    if provider == "ntfy" and url:
        return "Subscribe to this topic in the ntfy app."
    if provider == "fcm":
        return "Open Keel on the phone so it can register for Firebase alerts."
    return "The server sends nothing until a provider is configured."


def register_token(session: Session, user_id: int, token: str) -> None:
    """Remember this phone's Firebase token for the signed-in person."""
    cleaned = token.strip()
    if not cleaned:
        raise InvalidNotificationError("A phone token is required.")
    if len(cleaned) > 512:
        raise InvalidNotificationError("A phone token is at most 512 characters.")
    existing = session.scalar(select(PhoneDevice).where(PhoneDevice.token == cleaned))
    if existing is None:
        session.add(PhoneDevice(user_id=user_id, token=cleaned))
    else:
        existing.user_id = user_id
        existing.updated_at = utc_now()
    session.flush()


def forget_token(session: Session, user_id: int, token: str) -> None:
    """Drop this phone's Firebase token when it belongs to the signed-in person."""
    cleaned = token.strip()
    device = session.scalar(select(PhoneDevice).where(PhoneDevice.token == cleaned))
    if device is None or device.user_id != user_id:
        return
    session.delete(device)
    session.flush()


def ensure_topic(session: Session, user_id: int) -> str:
    """The secret ntfy topic for this person, created on first use."""
    if session.get(User, user_id) is None:
        raise NotFoundError("That person does not exist.")
    stored = session.get(PhoneTopic, user_id)
    if stored is not None:
        return stored.topic
    for _ in range(5):
        topic = secrets.token_urlsafe(32)
        taken = session.scalar(
            select(PhoneTopic.user_id).where(PhoneTopic.topic == topic),
        )
        if taken is None:
            session.add(PhoneTopic(user_id=user_id, topic=topic))
            session.flush()
            return topic
    raise InvalidNotificationError("A phone topic could not be chosen.")


def alert_message(notice: Notice) -> tuple[str, str]:
    """The same subject and body the email uses."""
    key = notice.issue_key
    actor = notice.actor_name
    kind = notice.notice_type
    if kind == NotificationType.ASSIGNED.value:
        subject = f"Assigned to you: {key}"
    elif kind in _DELETE_TYPES:
        subject = f"{actor} deleted {key}"
    elif kind in _COMMENT_TYPES:
        subject = f"{actor} commented on {key}"
    else:
        subject = f"{actor} updated {key}"
    heading = f"{key} {notice.issue_title}".strip()
    text = notice.body.strip()
    body = f"{heading}\n\n{text}\n" if text else f"{heading}\n"
    return subject, body


def _ntfy(session: Session, notice: Notice, settings: KeelSettings) -> bool:
    base = _ntfy_base(settings)
    if base is None:
        return False
    topic = ensure_topic(session, notice.recipient_id)
    subject, body = alert_message(notice)
    headers = {
        "Title": _header(subject),
        "Content-Type": "text/plain; charset=utf-8",
    }
    token = settings.ntfy_token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{base}/{urllib.parse.quote(topic, safe='')}"
    status, _text = _post(url, body.encode(), headers)
    return 200 <= status < 300


def _fcm(session: Session, notice: Notice, settings: KeelSettings) -> bool:
    account = _service_account(settings.fcm_credentials_file)
    if account is None:
        return False
    devices = list(
        session.scalars(
            select(PhoneDevice).where(PhoneDevice.user_id == notice.recipient_id),
        ).all(),
    )
    if not devices:
        return False
    access = _access_token(account)
    if access is None:
        return False
    subject, body = alert_message(notice)
    issue_id = "" if notice.issue_id is None else str(notice.issue_id)
    delivered = False
    for device in devices:
        payload = {
            "message": {
                "token": device.token,
                "notification": {"title": subject, "body": body},
                "data": {"issueId": issue_id},
                "android": {
                    "priority": "HIGH",
                    "notification": {"channel_id": "keel-alerts"},
                },
            },
        }
        status, text = _post(
            (
                "https://fcm.googleapis.com/v1/projects/"
                f"{urllib.parse.quote(account['project_id'], safe='')}/messages:send"
            ),
            json.dumps(payload).encode(),
            {
                "Authorization": f"Bearer {access}",
                "Content-Type": "application/json",
            },
        )
        if 200 <= status < 300:
            delivered = True
        elif _unregistered(status, text):
            session.delete(device)
    session.flush()
    return delivered


def _ntfy_base(settings: KeelSettings) -> str | None:
    base = settings.ntfy_base_url.strip().rstrip("/")
    if base.startswith("http://") or base.startswith("https://"):
        return base
    return None


def _service_account(path: str) -> dict[str, str] | None:
    cleaned = path.strip()
    if not cleaned:
        return None
    try:
        raw = json.loads(Path(cleaned).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Firebase credentials could not be read.")
        return None
    if not isinstance(raw, dict):
        return None
    email = raw.get("client_email")
    key = raw.get("private_key")
    project = raw.get("project_id")
    if (
        not isinstance(email, str)
        or not email
        or not isinstance(key, str)
        or not key
        or not isinstance(project, str)
        or not project
    ):
        logger.info("Firebase credentials are missing a project, email, or key.")
        return None
    return {"client_email": email, "private_key": key, "project_id": project}


def _access_token(account: dict[str, str]) -> str | None:
    clock = time.time()
    cached = _access.get(account["client_email"])
    if cached is not None and cached[1] > clock + 30:
        return cached[0]
    assertion = _jwt(account, int(clock))
    if assertion is None:
        return None
    status, text = _post(
        _TOKEN_URL,
        urllib.parse.urlencode(
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        ).encode(),
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    if status != 200:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    token = parsed.get("access_token")
    expires = parsed.get("expires_in")
    if not isinstance(token, str) or not token:
        return None
    seconds = expires if isinstance(expires, int) else 3600
    _access[account["client_email"]] = (token, clock + max(seconds, 1))
    return token


def _jwt(account: dict[str, str], now: int) -> str | None:
    header = _b64(
        json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode(),
    )
    claims = _b64(
        json.dumps(
            {
                "iss": account["client_email"],
                "scope": _FCM_SCOPE,
                "aud": _TOKEN_URL,
                "iat": now,
                "exp": now + 3600,
            },
            separators=(",", ":"),
        ).encode(),
    )
    signing = f"{header}.{claims}".encode()
    try:
        key = serialization.load_pem_private_key(
            account["private_key"].encode(),
            password=None,
        )
    except ValueError:
        logger.exception("Firebase credentials could not be read.")
        return None
    if not isinstance(key, RSAPrivateKey):
        logger.info("Firebase credentials are missing a project, email, or key.")
        return None
    signature = key.sign(signing, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{claims}.{_b64(signature)}"


def _post(url: str, data: bytes, headers: dict[str, str]) -> tuple[int, str]:
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, raw.decode(errors="replace")
    except OSError:
        logger.exception("Phone alert was not handed off.")
        return 0, ""


def _unregistered(status: int, text: str) -> bool:
    if status not in {400, 404}:
        return False
    return "UNREGISTERED" in text or "NOT_FOUND" in text


def _header(value: str) -> str:
    cleaned = " ".join(value.split())
    if cleaned.isascii():
        return cleaned
    return str(Header(cleaned, "utf-8"))


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _warn_once() -> None:
    global _warned
    if _warned:
        return
    _warned = True
    logger.info("Phone alerts are not configured.")
