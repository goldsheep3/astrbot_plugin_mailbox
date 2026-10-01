from __future__ import annotations

from types import SimpleNamespace

from conftest import run_async


def test_normalize_status_message_reads_message_attribute(smtp_module) -> None:
    status = SimpleNamespace(message=b"OK: queued as 12345")

    assert smtp_module._normalize_status_message(status) == "OK: queued as 12345"


def test_send_message_forwards_expected_args(smtp_module, stubbed_runtime) -> None:
    captured = {}

    async def fake_send(message, **kwargs):
        captured["message"] = message
        captured["kwargs"] = kwargs
        return 250, b"queued"

    stubbed_runtime["smtp_module"].send = fake_send

    settings = smtp_module.SMTPSettings(
        host="smtp.example.com",
        port=465,
        username="bot@example.com",
        password="secret",
        use_tls=True,
        use_starttls=False,
        timeout_seconds=10.0,
    )
    result = run_async(
        smtp_module.send_message(
            settings=settings,
            message=SimpleNamespace(),
            sender="bot@example.com",
            recipients=["alice@example.com"],
        )
    )

    assert result == ("250", "queued")
    assert captured["kwargs"]["hostname"] == "smtp.example.com"
    assert captured["kwargs"]["port"] == 465
    assert captured["kwargs"]["sender"] == "bot@example.com"
    assert captured["kwargs"]["recipients"] == ["alice@example.com"]
