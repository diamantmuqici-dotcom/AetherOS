"""SMTP delivery with mandatory TLS and bounded inputs."""

from __future__ import annotations

import base64
import smtplib
import ssl
from email.message import EmailMessage
from typing import Iterable

from .account import Account, AccountError

DEFAULT_TIMEOUT = 30
MAX_RECIPIENTS = 50


class MailSendError(Exception):
    """Base class for SMTP failures."""


def build_message(
    sender: str,
    recipients: Iterable[str],
    subject: str,
    body: str,
    *,
    pgp_status: str | None = None,
) -> EmailMessage:
    to = list(recipients)
    if not to or len(to) > MAX_RECIPIENTS:
        raise MailSendError(f"recipient count must be 1..{MAX_RECIPIENTS}")
    if any(not isinstance(item, str) or "@" not in item or len(item) > 254 for item in to):
        raise MailSendError("invalid recipient address")
    if not isinstance(sender, str) or "@" not in sender or len(sender) > 254:
        raise MailSendError("invalid sender address")
    if not isinstance(subject, str) or len(subject) > 512:
        raise MailSendError("subject must be at most 512 characters")
    if not isinstance(body, str) or len(body) > 16 * 1024 * 1024:
        raise MailSendError("body exceeds the size limit")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(to)
    message["Subject"] = subject.replace("\r", " ").replace("\n", " ")
    if pgp_status:
        message["X-Aether-PGP"] = pgp_status[:200]
    message.set_content(body)
    return message


def send_message(
    account: Account,
    password: str,
    message: EmailMessage,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    ssl_context: ssl.SSLContext | None = None,
) -> None:
    try:
        account.validate()
    except AccountError as exc:
        raise MailSendError(str(exc)) from exc
    mode = account.smtp_mode
    if mode not in ("ssl", "starttls"):
        raise MailSendError("cleartext SMTP is not allowed")
    if not isinstance(password, str) or not password:
        raise MailSendError("a password or access token is required")
    if not isinstance(message, EmailMessage):
        raise MailSendError("message must be an EmailMessage")
    ctx = ssl_context or ssl.create_default_context()

    client: smtplib.SMTP | None = None
    try:
        if mode == "ssl":
            client = smtplib.SMTP_SSL(
                account.smtp_host, account.smtp_port, timeout=timeout, context=ctx
            )
        else:
            client = smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=timeout)
            client.ehlo()
            client.starttls(context=ctx)
            client.ehlo()
        if account.auth_method.strip().lower() == "oauth2":
            token = f"user={account.username}\x01auth=Bearer {password}\x01\x01"
            encoded = base64.b64encode(token.encode("utf-8")).decode("ascii")
            client.docmd("AUTH", "XOAUTH2 " + encoded)
        else:
            client.login(account.username, password)
        client.send_message(message)
    except (OSError, smtplib.SMTPException, ssl.SSLError) as exc:
        raise MailSendError(f"SMTP delivery failed: {exc}") from exc
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                pass
