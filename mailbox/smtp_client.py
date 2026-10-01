from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

import aiosmtplib


@dataclass(slots=True)
class SMTPSettings:
    """SMTP connection settings.

    Args:
        host: SMTP host name.
        port: SMTP port.
        username: Optional login username.
        password: Optional login password.
        use_tls: Whether to use implicit TLS.
        use_starttls: Whether to upgrade the connection via STARTTLS.
        timeout_seconds: Network timeout for send operations.
    """

    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    use_starttls: bool
    timeout_seconds: float


async def send_message(
    settings: SMTPSettings,
    message: EmailMessage,
    sender: str,
    recipients: list[str],
) -> tuple[str, str]:
    """Send a message through SMTP and normalize the response.

    Args:
        settings: SMTP connection settings.
        message: Built email message.
        sender: Envelope sender address.
        recipients: Envelope recipient list.

    Returns:
        SMTP status code and message text.
    """
    response = await aiosmtplib.send(
        message,
        hostname=settings.host,
        port=settings.port,
        username=settings.username or None,
        password=settings.password or None,
        sender=sender,
        recipients=recipients,
        use_tls=settings.use_tls,
        start_tls=settings.use_starttls,
        timeout=settings.timeout_seconds,
    )
    status_code, status_message = response
    return str(status_code), _normalize_status_message(status_message)


def _normalize_status_message(status_message: Any) -> str:
    """Convert SMTP response payloads to a displayable string.

    Args:
        status_message: Raw SMTP response payload.

    Returns:
        Human-readable response string.
    """
    if isinstance(status_message, bytes):
        return status_message.decode("utf-8", errors="replace").strip()

    message_attr = getattr(status_message, "message", None)
    if isinstance(message_attr, bytes):
        return message_attr.decode("utf-8", errors="replace").strip()
    if isinstance(message_attr, str):
        return message_attr.strip()

    if isinstance(status_message, (list, tuple)):
        parts = [_normalize_status_message(item) for item in status_message]
        return "; ".join(part for part in parts if part)

    text = str(status_message).strip()
    if text == "{}":
        return ""
    return text
