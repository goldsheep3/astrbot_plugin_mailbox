from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PARENT_ROOT = PLUGIN_ROOT.parent


def _find_workspace_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "astrbot").is_dir() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("Unable to locate AstrBot workspace root from test path.")


WORKSPACE_ROOT = _find_workspace_root(PLUGIN_ROOT)
ORIGINAL_SYS_PATH = list(sys.path)
for path in (WORKSPACE_ROOT, PARENT_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


class _Logger:
    def info(self, *_args, **_kwargs) -> None:
        return None

    def exception(self, *_args, **_kwargs) -> None:
        return None

    def warning(self, *_args, **_kwargs) -> None:
        return None


class _FunctionTool:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class _MessageChain:
    def __init__(self) -> None:
        self.text = ""

    def message(self, text: str):
        self.text = text
        return self


class _Filter:
    class PermissionType:
        ADMIN = "admin"

    @staticmethod
    def command(_name):
        def decorator(func):
            return func

        return decorator

    @staticmethod
    def permission_type(_permission_type):
        def decorator(func):
            return func

        return decorator


class _Star:
    def __init__(self, context) -> None:
        self.context = context


class _StarTools:
    data_dir = Path(".")

    @classmethod
    def get_data_dir(cls, _name: str) -> Path:
        return cls.data_dir


class _AioSmtpModule(ModuleType):
    async def send(self, *args, **kwargs):
        return 250, b"queued"


class DummyContext:
    def __init__(self) -> None:
        self.tools = []
        self.sent_messages = []
        self.llm_requests = []

    def add_llm_tools(self, *tools) -> None:
        self.tools.extend(tools)

    async def send_message(self, session: str, message) -> bool:
        self.sent_messages.append((session, message.text))
        return True

    async def get_current_chat_provider_id(self, session: str) -> str:
        return f"provider:{session}"

    async def llm_generate(self, **kwargs):
        self.llm_requests.append(kwargs)
        return type("Response", (), {"completion_text": "建议回复，请确认是否发送。"})()


class DummyEvent:
    def __init__(self, sender_id: str = "tester", session: str = "test:session") -> None:
        self._sender_id = sender_id
        self.unified_msg_origin = session

    def get_sender_id(self) -> str:
        return self._sender_id

    def plain_result(self, text: str) -> str:
        return text


@pytest.fixture
def stubbed_runtime(tmp_path: Path):
    originals = {
        name: sys.modules.get(name)
        for name in (
            "astrbot",
            "astrbot.api",
            "astrbot.api.event",
            "astrbot.api.star",
            "aiosmtplib",
        )
    }

    astrbot_module = ModuleType("astrbot")
    api_module = ModuleType("astrbot.api")
    event_module = ModuleType("astrbot.api.event")
    star_module = ModuleType("astrbot.api.star")
    smtp_module = _AioSmtpModule("aiosmtplib")

    def _register(*_args, **_kwargs):
        def decorator(cls):
            return cls

        return decorator

    api_module.AstrBotConfig = dict
    api_module.FunctionTool = _FunctionTool
    api_module.logger = _Logger()
    event_module.AstrMessageEvent = object
    event_module.MessageChain = _MessageChain
    event_module.filter = _Filter()
    star_module.Context = object
    star_module.Star = _Star
    star_module.StarTools = _StarTools
    star_module.register = _register

    _StarTools.data_dir = tmp_path

    sys.modules["astrbot"] = astrbot_module
    sys.modules["astrbot.api"] = api_module
    sys.modules["astrbot.api.event"] = event_module
    sys.modules["astrbot.api.star"] = star_module
    sys.modules["aiosmtplib"] = smtp_module

    try:
        yield {
            "smtp_module": smtp_module,
            "tmp_path": tmp_path,
        }
    finally:
        for module_name in list(sys.modules):
            if module_name == "astrbot_plugin_mailbox" or module_name.startswith(
                "astrbot_plugin_mailbox."
            ):
                sys.modules.pop(module_name, None)
        for name, module in originals.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


@pytest.fixture
def plugin_modules(stubbed_runtime):
    main_module = importlib.import_module("astrbot_plugin_mailbox.main")
    imap_module = importlib.import_module("astrbot_plugin_mailbox.mailbox.imap_client")
    builder_module = importlib.import_module(
        "astrbot_plugin_mailbox.mailbox.message_builder"
    )
    models_module = importlib.import_module("astrbot_plugin_mailbox.mailbox.models")
    smtp_module = importlib.import_module("astrbot_plugin_mailbox.mailbox.smtp_client")
    return {
        "main": main_module,
        "imap": imap_module,
        "builder": builder_module,
        "models": models_module,
        "smtp": smtp_module,
    }


@pytest.fixture
def MailboxPlugin(plugin_modules):
    return plugin_modules["main"].MailboxPlugin


@pytest.fixture
def models(plugin_modules):
    return plugin_modules["models"]


@pytest.fixture
def imap_module(plugin_modules):
    return plugin_modules["imap"]


@pytest.fixture
def builder_module(plugin_modules):
    return plugin_modules["builder"]


@pytest.fixture
def smtp_module(plugin_modules):
    return plugin_modules["smtp"]


@pytest.fixture
def build_plugin(MailboxPlugin, tmp_path: Path):
    def _build(**overrides):
        config = {
            "email_address": "bot@example.com",
            "imap_username": "",
            "imap_server": "imap.example.com",
            "imap_port": 993,
            "imap_password": "imap-secret",
            "imap_use_tls": True,
            "imap_folder": "INBOX",
            "imap_interval": 3.0,
            "enable_agent_inbox_processing": False,
            "smtp_username": "",
            "smtp_server": "smtp.example.com",
            "smtp_port": 465,
            "smtp_password": "smtp-secret",
            "smtp_security_mode": 1,
            "smtp_timeout_seconds": 10.0,
            "smtp_sender_name": "AstrMailbox",
            "smtp_prefix": "[Bot] ",
            "smtp_max_html_length": 2000,
            "require_reply_confirmation": True,
            "allowed_recipient_domains": [],
            "blocked_recipient_domains": [],
        }
        config.update(overrides)
        plugin = MailboxPlugin(DummyContext(), config)
        return plugin

    return _build


def run_async(awaitable):
    return asyncio.run(awaitable)


def pytest_sessionfinish(session, exitstatus):
    sys.path[:] = ORIGINAL_SYS_PATH
