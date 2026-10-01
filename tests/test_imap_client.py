from __future__ import annotations

from email.message import EmailMessage


def _build_raw_message() -> bytes:
    message = EmailMessage()
    message["From"] = "Alice <alice@example.com>"
    message["To"] = "Bot <bot@example.com>"
    message["Cc"] = "Bob <bob@example.com>"
    message["Reply-To"] = "Reply <reply@example.com>"
    message["Subject"] = "Mailbox subject"
    message["Date"] = "Wed, 29 Jul 2026 10:00:00 +0800"
    message["Message-ID"] = "<msg-1@example.com>"
    message["In-Reply-To"] = "<parent@example.com>"
    message["References"] = "<root@example.com> <parent@example.com>"
    message.set_content("Plain body")
    message.add_alternative("<p>Hello <strong>HTML</strong> body</p>", subtype="html")
    message.add_attachment(
        b"report-data",
        maintype="application",
        subtype="octet-stream",
        filename="report.txt",
    )
    return message.as_bytes()


def test_parse_email_extracts_headers_flags_and_attachment_metadata(imap_module) -> None:
    settings = imap_module.IMAPSettings(
        host="imap.example.com",
        port=993,
        username="bot@example.com",
        password="secret",
        use_tls=True,
        folder="INBOX",
        preview_length=20,
    )
    client = imap_module.IMAPClient(settings)

    email_obj = client._parse_email(
        uid="321",
        raw_bytes=_build_raw_message(),
        flags={"\\Seen", "\\Flagged"},
    )

    assert email_obj.uid == "321"
    assert email_obj.message_id == "<msg-1@example.com>"
    assert email_obj.from_.address == "alice@example.com"
    assert [item.address for item in email_obj.to] == ["bot@example.com"]
    assert [item.address for item in email_obj.cc] == ["bob@example.com"]
    assert [item.address for item in email_obj.reply_to] == ["reply@example.com"]
    assert email_obj.in_reply_to == "<parent@example.com>"
    assert email_obj.references == ["<root@example.com>", "<parent@example.com>"]
    assert email_obj.text == "Plain body"
    assert email_obj.is_read is True
    assert email_obj.is_starred is True
    assert email_obj.summary == "Plain body"
    assert email_obj.attachments[0].filename == "report.txt"


def test_list_recent_emails_uses_uid_search_order(imap_module) -> None:
    settings = imap_module.IMAPSettings(
        host="imap.example.com",
        port=993,
        username="bot@example.com",
        password="secret",
        use_tls=True,
        folder="INBOX",
    )
    client = imap_module.IMAPClient(settings)

    class FakeMail:
        def uid(self, command, *_args):
            if command == "SEARCH":
                return "OK", [b"1 2 3"]
            raise AssertionError("Unexpected command")

    client._mail = FakeMail()
    client._connect = lambda: None
    seen = []

    def fake_fetch(uid: str):
        seen.append(uid)
        return {"uid": uid}

    client.fetch_email_by_uid = fake_fetch

    result = client.list_recent_emails(limit=2)

    assert seen == ["3", "2"]
    assert result == [{"uid": "3"}, {"uid": "2"}]
