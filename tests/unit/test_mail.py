import smtplib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from keel.services import mail


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "smtp_host": "mail.local",
        "smtp_port": 587,
        "smtp_username": "keel",
        "smtp_password": "secret",
        "smtp_from": "keel@example.com",
        "smtp_starttls": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_unconfigured_mail_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail, "get_settings", lambda: _settings(smtp_host=""))
    mail.send("ada@example.com", "Hello", "Body")


def test_send_hands_the_message_to_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.__enter__.return_value = client
    smtp = MagicMock(return_value=client)
    monkeypatch.setattr(mail, "get_settings", lambda: _settings())
    monkeypatch.setattr(smtplib, "SMTP", smtp)
    mail.send("ada@example.com", "Hello", "Body")
    smtp.assert_called_once_with("mail.local", 587, timeout=15)
    client.starttls.assert_called_once_with()
    client.login.assert_called_once_with("keel", "secret")
    sent = client.send_message.call_args.args[0]
    assert sent["To"] == "ada@example.com"
    assert sent["Subject"] == "Hello"
    assert "Body" in sent.get_content()


def test_a_failed_handoff_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail, "get_settings", lambda: _settings(smtp_username=""))
    monkeypatch.setattr(smtplib, "SMTP", MagicMock(side_effect=OSError("down")))
    mail.send("ada@example.com", "Hello", "Body")
