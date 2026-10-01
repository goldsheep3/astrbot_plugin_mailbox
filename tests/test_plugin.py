from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from conftest import DummyEvent, run_async


def test_plugin_registers_three_tools(build_plugin) -> None:
    plugin = build_plugin()

    tool_names = [tool.name for tool in plugin.context.tools]

    assert tool_names == ["send_email", "list_recent_emails", "get_email_detail"]


def test_recipient_policy_blocks_disallowed_domains(build_plugin, models) -> None:
    plugin = build_plugin(allowed_recipient_domains=["example.com"])
    settings = plugin._load_settings()
    request = models.OutgoingMailRequest(
        to=["alice@other.com"],
        subject="Blocked",
        text_body="Hello",
    )

    with pytest.raises(ValueError, match="不在白名单"):
        plugin._check_recipient_policy(settings, request)


def test_send_email_tool_returns_delivery_summary(build_plugin, monkeypatch) -> None:
    plugin = build_plugin()

    async def fake_send_mail(settings, request):
        assert settings.email_address == "bot@example.com"
        assert request.subject == "Hello"
        return "邮件发送成功。 SMTP 状态: 250 queued。 收件人: alice@example.com。 主题: [Bot] Hello"

    monkeypatch.setattr(plugin, "_send_mail", fake_send_mail)

    result = run_async(
        plugin.send_email_tool(
            DummyEvent(),
            to=["alice@example.com"],
            subject="Hello",
            text_body="Body",
        )
    )

    assert "邮件发送成功" in result
    assert "alice@example.com" in result


@pytest.mark.parametrize(
    ("mode", "use_tls", "use_starttls"),
    [(0, False, False), (1, True, False), (2, False, True)],
)
def test_smtp_security_mode_maps_to_client_settings(
    build_plugin, mode: int, use_tls: bool, use_starttls: bool
) -> None:
    plugin = build_plugin(smtp_security_mode=mode)

    smtp_settings = plugin._smtp_settings(plugin._load_settings())

    assert smtp_settings.use_tls is use_tls
    assert smtp_settings.use_starttls is use_starttls


def test_legacy_smtp_security_settings_are_migrated(build_plugin) -> None:
    plugin = build_plugin(
        smtp_security_mode=None,
        smtp_use_tls=False,
        smtp_use_starttls=True,
        require_reply_confirmation=None,
    )

    settings = plugin._load_settings()

    assert settings.smtp_security_mode == 2
    assert settings.require_reply_confirmation is True


def test_send_email_tool_requires_confirmation_for_reply(build_plugin) -> None:
    plugin = build_plugin(require_reply_confirmation=True)

    with pytest.raises(ValueError, match="需要先向用户询问"):
        run_async(
            plugin.send_email_tool(
                DummyEvent(),
                to=["alice@example.com"],
                subject="Re: Hello",
                text_body="Reply",
                in_reply_to="<message@example.com>",
            )
        )


def test_send_email_tool_sends_confirmed_reply(build_plugin, monkeypatch) -> None:
    plugin = build_plugin(require_reply_confirmation=True)

    async def fake_send_mail(settings, request):
        assert settings.require_reply_confirmation is True
        assert request.in_reply_to == "<message@example.com>"
        return "邮件发送成功。"

    monkeypatch.setattr(plugin, "_send_mail", fake_send_mail)

    result = run_async(
        plugin.send_email_tool(
            DummyEvent(),
            to=["alice@example.com"],
            subject="Re: Hello",
            text_body="Reply",
            in_reply_to="<message@example.com>",
            confirmed_by_user=True,
        )
    )

    assert result == "邮件发送成功。"


def test_list_recent_emails_tool_handler_returns_json(
    build_plugin, models, monkeypatch
) -> None:
    plugin = build_plugin()
    email_obj = models.Email(
        id="1",
        message_id="<m1@example.com>",
        uid="1",
        from_=models.EmailAddress(name="Alice", address="alice@example.com"),
        to=[models.EmailAddress(name="Bot", address="bot@example.com")],
        subject="Latest",
        text="Body",
        html="",
        date="2026-07-29T10:00:00+08:00",
        summary="Body",
    )

    async def fake_list_recent_emails(count: int):
        assert count == 5
        return [email_obj]

    monkeypatch.setattr(plugin, "_list_recent_emails", fake_list_recent_emails)

    raw = run_async(plugin._list_recent_emails_tool_handler(DummyEvent(), count=5))
    payload = json.loads(raw)

    assert payload[0]["uid"] == "1"
    assert payload[0]["from"]["address"] == "alice@example.com"
    assert payload[0]["subject"] == "Latest"


def test_get_email_detail_tool_handler_returns_json(
    build_plugin, models, monkeypatch
) -> None:
    plugin = build_plugin()
    email_obj = models.Email(
        id="2",
        message_id="<m2@example.com>",
        uid="2",
        from_=models.EmailAddress(name="Alice", address="alice@example.com"),
        reply_to=[models.EmailAddress(name="Reply", address="reply@example.com")],
        to=[models.EmailAddress(name="Bot", address="bot@example.com")],
        subject="Detailed",
        text="Body",
        html="<p>Body</p>",
        date="2026-07-29T11:00:00+08:00",
        summary="Body",
        attachments=[
            models.EmailAttachment(
                filename="report.txt",
                content_type="text/plain",
                size=12,
            )
        ],
    )

    async def fake_get_email_detail(uid: str):
        assert uid == "2"
        return email_obj

    monkeypatch.setattr(plugin, "_get_email_detail", fake_get_email_detail)

    raw = run_async(plugin._get_email_detail_tool_handler(DummyEvent(), uid="2"))
    payload = json.loads(raw)

    assert payload["uid"] == "2"
    assert payload["reply_to"][0]["address"] == "reply@example.com"
    assert payload["attachments"][0]["filename"] == "report.txt"


def test_mailbox_config_check_reports_masked_secrets(build_plugin) -> None:
    plugin = build_plugin()

    async def collect():
        results = []
        async for item in plugin.mailbox_config_check(DummyEvent()):
            results.append(item)
        return results

    output = run_async(collect())[0]
    assert "IMAP 密码: im***et" in output
    assert "SMTP 密码: sm***et" in output


def test_mailbox_read_requires_uid(build_plugin) -> None:
    plugin = build_plugin()

    async def collect():
        results = []
        async for item in plugin.mailbox_read(DummyEvent(), ""):
            results.append(item)
        return results

    output = run_async(collect())[0]
    assert output == "用法: /mailbox_read <uid>"


def test_inbox_subscription_replaces_previous_session(build_plugin) -> None:
    plugin = build_plugin()

    async def collect_subscribe(event):
        results = []
        async for item in plugin.mailbox_subscribe(event):
            results.append(item)
        return results

    run_async(collect_subscribe(DummyEvent(session="platform:one")))
    run_async(collect_subscribe(DummyEvent(session="platform:two")))

    state = json.loads(plugin.inbox_push_state_path.read_text(encoding="utf-8"))
    assert state["session"] == "platform:two"

    async def collect_unsubscribe(event):
        results = []
        async for item in plugin.mailbox_unsubscribe(event):
            results.append(item)
        return results

    run_async(collect_unsubscribe(DummyEvent(session="platform:one")))
    assert plugin._subscribed_session == "platform:two"
    run_async(collect_unsubscribe(DummyEvent(session="platform:two")))
    assert plugin._subscribed_session is None


def test_new_inbox_email_is_stored_and_sent_to_subscribed_session(
    build_plugin, models, monkeypatch
) -> None:
    plugin = build_plugin(enable_agent_inbox_processing=True)
    plugin._subscribed_session = "platform:one"
    email_obj = models.Email(
        id="3",
        uid="3",
        message_id="<m3@example.com>",
        from_=models.EmailAddress(name="Alice", address="alice@example.com"),
        to=[models.EmailAddress(name="Bot", address="bot@example.com")],
        subject="New mail",
        text="New content",
        html="",
        date="2026-07-30T10:00:00+08:00",
        summary="New content",
    )

    async def fake_list_recent_emails(_count: int):
        return [email_obj]

    monkeypatch.setattr(plugin, "_list_recent_emails", fake_list_recent_emails)

    run_async(plugin._poll_inbox_push())
    assert plugin.context.sent_messages == []

    newer_email = email_obj.model_copy(
        update={"id": "4", "uid": "4", "message_id": "<m4@example.com>"}
    )

    async def fake_list_newer_email(_count: int):
        return [newer_email, email_obj]

    monkeypatch.setattr(plugin, "_list_recent_emails", fake_list_newer_email)
    run_async(plugin._poll_inbox_push())

    assert {session for session, _ in plugin.context.sent_messages} == {
        "platform:one",
    }
    assert "UID: 4" in plugin.context.sent_messages[0][1]
    assert "邮件 Agent 建议" in plugin.context.sent_messages[1][1]
    assert plugin.context.llm_requests[0]["chat_provider_id"] == "provider:platform:one"
    assert (plugin.mail_store_dir / "4.json").is_file()
