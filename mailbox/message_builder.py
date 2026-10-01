from __future__ import annotations

import html
import re
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import make_msgid

from .models import OutgoingMailRequest

HTML_TAG_RE = re.compile(r"<[^>]+>")
HTML_BREAK_RE = re.compile(r"<(?:br|/p|/div|/li|/tr|/h[1-6])\b[^>]*>", re.IGNORECASE)
HTML_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
WHITESPACE_RE = re.compile(r"\s+")


def html_to_text(html_content: str) -> str:
    """Convert simple HTML content to a plain text fallback.

    Args:
        html_content: Raw HTML body.

    Returns:
        Flattened text content.
    """
    text = HTML_SCRIPT_STYLE_RE.sub(" ", html_content)
    text = HTML_BREAK_RE.sub(" ", text)
    text = HTML_TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return WHITESPACE_RE.sub(" ", text).strip()


def _set_addresses(message: EmailMessage, header: str, addresses: list[str]) -> None:
    """Populate an address header when values are present.

    Args:
        message: Email message under construction.
        header: Header name.
        addresses: Normalized address list.
    """
    if addresses:
        message[header] = ", ".join(addresses)


def build_message(
    request: OutgoingMailRequest,
    from_email: str,
    from_name: str,
    subject_prefix: str = "",
) -> EmailMessage:
    """Build an RFC-compatible email message for SMTP delivery.

    Args:
        request: Validated outgoing mail request.
        from_email: Sender address.
        from_name: Sender display name.
        subject_prefix: Optional configured subject prefix.

    Returns:
        EmailMessage ready for SMTP delivery.
    """
    message = EmailMessage()
    if from_name:
        message["From"] = str(Address(display_name=from_name, addr_spec=from_email))
    else:
        message["From"] = from_email

    _set_addresses(message, "To", [str(address) for address in request.to])
    _set_addresses(message, "Cc", [str(address) for address in request.cc])

    subject = request.subject
    if subject_prefix:
        subject = f"{subject_prefix}{subject}"
    message["Subject"] = subject
    message["Message-ID"] = make_msgid()

    if request.reply_to:
        message["Reply-To"] = str(request.reply_to)
    if request.in_reply_to:
        message["In-Reply-To"] = request.in_reply_to
    if request.references:
        message["References"] = " ".join(request.references)

    text_body = request.text_body or html_to_text(request.html_body)
    message.set_content(text_body)
    if request.html_body:
        message.add_alternative(request.html_body, subtype="html")

    return message
