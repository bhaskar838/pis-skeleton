"""Outbound e-mail (Mailpit in dev, SES SMTP in prod)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from control_api.settings import ControlSettings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    text: str


class Mailer(Protocol):
    async def send(self, mail: Mail) -> None: ...


class SmtpMailer:
    def __init__(self, settings: ControlSettings) -> None:
        self._s = settings

    async def send(self, mail: Mail) -> None:
        import aiosmtplib

        msg = EmailMessage()
        msg["From"] = self._s.mail_from
        msg["To"] = mail.to
        msg["Subject"] = mail.subject
        msg.set_content(mail.text)
        try:
            await aiosmtplib.send(
                msg,
                hostname=self._s.smtp_host,
                port=self._s.smtp_port,
                username=self._s.smtp_user,
                password=self._s.smtp_password.get_secret_value() if self._s.smtp_password else None,
                start_tls=self._s.smtp_tls,
                timeout=10,
            )
        except Exception:
            log.exception("email send failed", extra={"subject": mail.subject})


class MemoryMailer:
    def __init__(self) -> None:
        self.sent: list[Mail] = []

    async def send(self, mail: Mail) -> None:
        self.sent.append(mail)
