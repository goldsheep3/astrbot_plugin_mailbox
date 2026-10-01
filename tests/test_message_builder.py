from __future__ import annotations

from astrbot_plugin_mailbox.mailbox.message_builder import build_message, html_to_text
from astrbot_plugin_mailbox.mailbox.models import OutgoingMailRequest


def test_html_to_text_strips_tags_and_scripts() -> None:
    assert (
        html_to_text(
            "<style>.x{}</style><script>alert(1)</script><p>Hello&nbsp;<b>world</b></p>"
        )
        == "Hello world"
    )


def test_build_message_sets_thread_headers_and_plain_fallback() -> None:
    request = OutgoingMailRequest(
        to=["alice@example.com"],
        cc=["bob@example.com"],
        subject="Status update",
        html_body="<p>Line <strong>one</strong></p>",
        reply_to="reply@example.com",
        in_reply_to="<parent@example.com>",
        references=["<root@example.com>", "<parent@example.com>"],
    )

    message = build_message(
        request=request,
        from_email="sender@example.com",
        from_name="AstrMailbox",
        subject_prefix="[Bot] ",
    )

    assert message["Subject"] == "[Bot] Status update"
    assert message["Reply-To"] == "reply@example.com"
    assert message["In-Reply-To"] == "<parent@example.com>"
    assert message["References"] == "<root@example.com> <parent@example.com>"
    assert message.get_body(preferencelist=("plain",)).get_content().strip() == "Line one"
    assert message.get_body(preferencelist=("html",)).get_content().strip() == "<p>Line <strong>one</strong></p>"
