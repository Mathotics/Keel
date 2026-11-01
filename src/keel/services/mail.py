import logging
import smtplib
from email.message import EmailMessage

from keel.settings import get_settings

logger = logging.getLogger(__name__)


def send(to: str, subject: str, body: str) -> None:
    """Hand a plain-text message to SMTP.

    When the host or From address is unset, or the handoff fails, this returns
    without raising. Callers still show the same notice either way.
    """
    settings = get_settings()
    if not settings.smtp_host.strip() or not settings.smtp_from.strip():
        logger.info("Mail is not configured; nothing was sent to %s.", to)
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from.strip()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(
            settings.smtp_host.strip(), settings.smtp_port, timeout=15
        ) as client:
            if settings.smtp_starttls:
                client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    except OSError:
        logger.exception("Mail to %s was not handed off.", to)
