"""Outbound e-mail (Mailpit in dev, SES SMTP in prod).

SMTP connection, sender and product name are read from the control panel at send time (ADR-0011), so staff can
change them without a restart. ``{product}`` in a subject or body is replaced by ``body.product_name``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from email.message import EmailMessage
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from control_api.config import ConfigRegistry

log = logging.getLogger(__name__)

PRODUCT = "{product}"
DEFAULT_PRODUCT = "DCS-PIS"


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    text: str


class Mailer(Protocol):
    async def send(self, mail: Mail) -> None: ...


def branded(mail: Mail, product: str) -> Mail:
    return Mail(
        to=mail.to, subject=mail.subject.replace(PRODUCT, product), text=mail.text.replace(PRODUCT, product)
    )


class SmtpMailer:
    def __init__(self, config: ConfigRegistry | None = None) -> None:
        self.config = config  # attached by AppState / the worker

    async def send(self, mail: Mail) -> None:
        import aiosmtplib

        c = self.config
        if c is None:
            raise RuntimeError("SmtpMailer has no ConfigRegistry")
        try:
            mail = branded(mail, await c.get_str("body.product_name"))
            msg = EmailMessage()
            msg["From"] = await c.get_str("electricals.mail_from")
            msg["To"] = mail.to
            msg["Subject"] = mail.subject
            msg.set_content(mail.text)
            await aiosmtplib.send(
                msg,
                hostname=await c.get_str("electricals.smtp_host"),
                port=await c.get_int("electricals.smtp_port"),
                username=(await c.get_str("electricals.smtp_username")) or None,
                password=await c.secret("electricals.smtp_password"),
                start_tls=await c.get_bool("electricals.smtp_starttls"),
                timeout=10,
            )
        except Exception:
            log.exception("email send failed", extra={"subject": mail.subject})


class MemoryMailer:
    """Test mailer. Brands mail with the registry's product name when given one."""

    def __init__(self, config: ConfigRegistry | None = None) -> None:
        self.sent: list[Mail] = []
        self.config = config

    async def send(self, mail: Mail) -> None:
        product = await self.config.get_str("body.product_name") if self.config else DEFAULT_PRODUCT
        self.sent.append(branded(mail, product))
