from __future__ import annotations

import html
import imaplib
import re
from dataclasses import dataclass
from datetime import datetime
from email import message_from_bytes, policy
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from .models import Email, EmailAddress

HTML_TAG_RE = re.compile(r"<[^>]+>")
HTML_BREAK_RE = re.compile(r"<(?:br|/p|/div|/li|/tr|/h[1-6])\b[^>]*>", re.IGNORECASE)
HTML_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
WHITESPACE_RE = re.compile(r"\s+")
FLAGS_RE = re.compile(r"FLAGS \((?P<flags>[^)]*)\)")


@dataclass(slots=True)
class IMAPSettings:
    """IMAP connection settings.

    Args:
        host: IMAP host name.
        port: IMAP port.
        username: Login username.
        password: Login password.
        use_tls: Whether to use implicit TLS.
        folder: Mail folder to inspect.
        preview_length: Maximum summary length.
    """

    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    folder: str
    preview_length: int = 200


class IMAPClient:
    """Blocking IMAP client for fetching recent mailbox content.

    Args:
        settings: Validated IMAP connection settings.
    """

    def __init__(self, settings: IMAPSettings) -> None:
        self.settings = settings
        self._mail: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None

    def close(self) -> None:
        """Close the IMAP session if it is open."""
        if self._mail is None:
            return
        try:
            self._mail.close()
        except Exception:
            pass
        try:
            self._mail.logout()
        except Exception:
            pass
        self._mail = None

    def list_recent_emails(self, limit: int = 10) -> list[Email]:
        """Fetch the most recent emails from the selected folder.

        Args:
            limit: Maximum number of emails to return.

        Returns:
            Parsed email list ordered from newest to oldest.
        """
        self._connect()
        status, data = self._mail.uid("SEARCH", None, "ALL")
        if status != "OK" or not data or not data[0]:
            return []

        uids = data[0].split()
        recent_uids = list(reversed(uids[-max(1, limit) :]))
        emails: list[Email] = []
        for uid in recent_uids:
            parsed = self.fetch_email_by_uid(uid.decode("utf-8", errors="replace"))
            if parsed is not None:
                emails.append(parsed)
        return emails

    def fetch_email_by_uid(self, uid: str) -> Email | None:
        """Fetch and parse a single email by IMAP UID.

        Args:
            uid: IMAP UID string.

        Returns:
            Parsed email, or None when the message cannot be fetched.
        """
        self._connect()
        status, data = self._mail.uid("FETCH", uid.encode("utf-8"), "(RFC822 FLAGS)")
        if status != "OK" or not data:
            return None

        for item in data:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            metadata, raw_bytes = item
            if not isinstance(raw_bytes, (bytes, bytearray)):
                continue
            flags = self._extract_flags(metadata)
            return self._parse_email(uid=uid, raw_bytes=bytes(raw_bytes), flags=flags)
        return None

    def _connect(self) -> None:
        """Open and authenticate an IMAP connection."""
        if self._mail is not None:
            try:
                self._mail.noop()
                return
            except Exception:
                self.close()

        if self.settings.use_tls:
            self._mail = imaplib.IMAP4_SSL(self.settings.host, self.settings.port)
        else:
            self._mail = imaplib.IMAP4(self.settings.host, self.settings.port)
        self._mail.login(self.settings.username, self.settings.password)
        self._mail.select(self.settings.folder, readonly=True)

    def _parse_email(self, uid: str, raw_bytes: bytes, flags: set[str]) -> Email:
        """Parse raw RFC822 bytes into the internal email model.

        Args:
            uid: IMAP UID.
            raw_bytes: Raw message bytes.
            flags: IMAP flags associated with the message.

        Returns:
            Parsed email model.
        """
        msg = message_from_bytes(raw_bytes, policy=policy.default)
        text_body, html_body = self._extract_bodies(msg)
        normalized_text = self._normalize_text(text_body)
        normalized_html_text = self._normalize_text(self._html_to_text(html_body))
        effective_text = normalized_text or normalized_html_text
        summary = self._truncate(effective_text, self.settings.preview_length)
        message_id = str(
            msg.get("Message-ID") or f"<uid-{uid}@astrmailbox.local>"
        ).strip()
        date_value = self._parse_date(msg.get("Date"))
        headers = self._extract_headers(msg)
        attachments = self._extract_attachment_metadata(msg)

        return Email(
            id=uid,
            message_id=message_id,
            uid=uid,
            thread_id=message_id,
            in_reply_to=str(msg.get("In-Reply-To") or "").strip() or None,
            references=self._split_references(str(msg.get("References") or "")),
            from_=self._first_address(msg.get_all("From", [])),
            sender=self._optional_first_address(msg.get_all("Sender", [])),
            reply_to=self._parse_addresses(msg.get_all("Reply-To", [])),
            to=self._parse_addresses(msg.get_all("To", [])),
            cc=self._parse_addresses(msg.get_all("Cc", [])),
            bcc=self._parse_addresses(msg.get_all("Bcc", [])),
            subject=str(msg.get("Subject") or "").strip() or "(No Subject)",
            text=effective_text,
            html=html_body,
            date=date_value,
            received_date=date_value,
            is_read="\\Seen" in flags,
            is_starred="\\Flagged" in flags,
            labels=sorted(flags),
            summary=summary,
            raw=raw_bytes.decode("utf-8", errors="replace"),
            headers=headers,
            attachments=attachments,
        )

    def _extract_bodies(self, msg: Message) -> tuple[str, str]:
        """Extract plain text and HTML message bodies.

        Args:
            msg: Parsed email message.

        Returns:
            Plain text and HTML bodies.
        """
        text_parts: list[str] = []
        html_parts: list[str] = []
        for part in msg.walk():
            if part.is_multipart():
                continue
            content_disposition = str(part.get_content_disposition() or "").lower()
            if content_disposition == "attachment":
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                continue
            content_type = part.get_content_type()
            if content_type == "text/plain":
                text_parts.append(decoded)
            elif content_type == "text/html":
                html_parts.append(decoded)

        if not msg.is_multipart():
            payload = msg.get_payload(decode=True)
            if isinstance(payload, (bytes, bytearray)):
                charset = msg.get_content_charset() or "utf-8"
                decoded = bytes(payload).decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    html_parts.append(decoded)
                else:
                    text_parts.append(decoded)

        return "\n".join(text_parts).strip(), "\n".join(html_parts).strip()

    def _extract_headers(self, msg: Message) -> dict[str, str | list[str]]:
        """Normalize message headers into a serializable mapping.

        Args:
            msg: Parsed email message.

        Returns:
            Header mapping.
        """
        headers: dict[str, str | list[str]] = {}
        for key in msg.keys():
            values = [
                str(value).strip()
                for value in msg.get_all(key, [])
                if str(value).strip()
            ]
            if not values:
                continue
            headers[key] = values[0] if len(values) == 1 else values
        return headers

    def _extract_attachment_metadata(self, msg: Message) -> list[dict[str, Any]]:
        """Extract lightweight attachment metadata.

        Args:
            msg: Parsed email message.

        Returns:
            Attachment metadata list.
        """
        attachments: list[dict[str, Any]] = []
        for part in msg.walk():
            if part.is_multipart():
                continue
            filename = part.get_filename()
            disposition = str(part.get_content_disposition() or "").lower()
            content_id = str(part.get("Content-ID") or "").strip() or None
            if disposition != "attachment" and not content_id and not filename:
                continue
            payload = part.get_payload(decode=True) or b""
            attachments.append(
                {
                    "filename": filename or "unnamed",
                    "content_type": part.get_content_type(),
                    "size": len(payload),
                    "content_id": content_id,
                    "is_inline": disposition == "inline" or content_id is not None,
                }
            )
        return attachments

    def _parse_addresses(self, header_values: list[str]) -> list[EmailAddress]:
        """Parse header values into structured addresses.

        Args:
            header_values: Raw address headers.

        Returns:
            Structured addresses.
        """
        addresses: list[EmailAddress] = []
        for name, address in getaddresses(header_values):
            normalized_address = address.strip()
            if not normalized_address:
                continue
            addresses.append(
                EmailAddress(name=name.strip(), address=normalized_address)
            )
        return addresses

    def _first_address(self, header_values: list[str]) -> EmailAddress:
        """Return the first parsed address, or a safe fallback.

        Args:
            header_values: Raw address headers.

        Returns:
            Parsed sender address.
        """
        parsed = self._parse_addresses(header_values)
        if parsed:
            return parsed[0]
        return EmailAddress(name="Unknown Sender", address="unknown@example.com")

    def _optional_first_address(self, header_values: list[str]) -> EmailAddress | None:
        """Return the first parsed address when present.

        Args:
            header_values: Raw address headers.

        Returns:
            Parsed sender or None.
        """
        parsed = self._parse_addresses(header_values)
        return parsed[0] if parsed else None

    def _parse_date(self, raw_date: str | None) -> datetime:
        """Parse RFC5322 date headers with a stable fallback.

        Args:
            raw_date: Raw Date header value.

        Returns:
            Parsed datetime value.
        """
        if raw_date:
            try:
                return parsedate_to_datetime(raw_date)
            except Exception:
                pass
        return datetime.now()

    def _split_references(self, raw_references: str) -> list[str]:
        """Split the References header into individual message identifiers.

        Args:
            raw_references: Raw References header value.

        Returns:
            Message identifier list.
        """
        return [item.strip() for item in raw_references.split() if item.strip()]

    def _extract_flags(self, metadata: bytes | bytearray | str) -> set[str]:
        """Extract IMAP flags from FETCH metadata.

        Args:
            metadata: Raw FETCH metadata.

        Returns:
            Flag set.
        """
        if isinstance(metadata, (bytes, bytearray)):
            text = bytes(metadata).decode("utf-8", errors="replace")
        else:
            text = str(metadata)
        match = FLAGS_RE.search(text)
        if not match:
            return set()
        return {flag.strip() for flag in match.group("flags").split() if flag.strip()}

    def _truncate(self, text: str, limit: int) -> str:
        """Truncate long summaries with an ellipsis.

        Args:
            text: Raw summary text.
            limit: Maximum length.

        Returns:
            Truncated summary.
        """
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."

    def _normalize_text(self, text: str) -> str:
        """Normalize whitespace in text content.

        Args:
            text: Raw text.

        Returns:
            Normalized text.
        """
        return WHITESPACE_RE.sub(" ", text).strip()

    def _html_to_text(self, html_content: str) -> str:
        """Convert basic HTML content to plain text.

        Args:
            html_content: Raw HTML.

        Returns:
            Plain text.
        """
        text = HTML_SCRIPT_STYLE_RE.sub(" ", html_content)
        text = HTML_BREAK_RE.sub(" ", text)
        text = HTML_TAG_RE.sub(" ", text)
        text = html.unescape(text)
        return WHITESPACE_RE.sub(" ", text).strip()
