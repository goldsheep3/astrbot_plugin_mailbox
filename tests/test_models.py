from __future__ import annotations

import pytest


def test_outgoing_mail_request_requires_body(models) -> None:
    with pytest.raises(ValueError, match="至少需要提供一个"):
        models.OutgoingMailRequest(
            to=["alice@example.com"],
            subject="No body",
        )


def test_outgoing_mail_request_deduplicates_recipients(models) -> None:
    request = models.OutgoingMailRequest(
        to=["alice@example.com"],
        cc=["alice@example.com", "bob@example.com"],
        bcc=["bob@example.com", "carol@example.com"],
        subject="Weekly",
        text_body="Hello",
    )

    assert request.all_recipients == [
        "alice@example.com",
        "bob@example.com",
        "carol@example.com",
    ]


def test_mailbox_settings_normalizes_domains(models) -> None:
    settings = models.MailboxSettings(
        email_address="bot@example.com",
        imap_server="imap.example.com",
        imap_port=993,
        imap_password="imap-secret",
        smtp_server="smtp.example.com",
        smtp_port=465,
        smtp_password="smtp-secret",
        smtp_sender_name="AstrMailbox",
        allowed_recipient_domains=[" Example.COM ", "example.com", "test.com"],
        blocked_recipient_domains=[" Blocked.COM ", "blocked.com"],
    )

    assert settings.allowed_recipient_domains == ["example.com", "test.com"]
    assert settings.blocked_recipient_domains == ["blocked.com"]
    assert settings.enable_agent_inbox_processing is False


def test_mailbox_settings_rejects_invalid_smtp_security_mode(models) -> None:
    with pytest.raises(ValueError, match="less than or equal to 2"):
        models.MailboxSettings(
            email_address="bot@example.com",
            imap_server="imap.example.com",
            imap_port=993,
            imap_password="imap-secret",
            smtp_server="smtp.example.com",
            smtp_port=465,
            smtp_password="smtp-secret",
            smtp_security_mode=3,
            smtp_sender_name="AstrMailbox",
        )


def test_email_model_normalizes_references_and_labels(models) -> None:
    sender = models.EmailAddress(name=" Alice ", address="alice@example.com")
    email_obj = models.Email(
        id="123",
        message_id="<m1@example.com>",
        from_=sender,
        to=[sender],
        subject="  Subject  ",
        text="  Body  ",
        html="  <p>Body</p>  ",
        date="2026-07-29T12:00:00",
        references=["  <m0@example.com>  ", "  ", "<m1@example.com>"],
        labels=[" inbox ", "", " flagged "],
    )

    assert email_obj.from_.name == "Alice"
    assert email_obj.subject == "Subject"
    assert email_obj.text == "Body"
    assert email_obj.references == ["<m0@example.com>", "<m1@example.com>"]
    assert email_obj.labels == ["inbox", "flagged"]
