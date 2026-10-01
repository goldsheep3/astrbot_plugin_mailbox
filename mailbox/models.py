from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


class EmailAddress(BaseModel):
    """Structured email address used by parsed and outgoing messages.

    Args:
        name: Optional display name from the mail header.
        address: RFC-compatible mailbox address.
    """

    name: str = Field("", description="显示名称")
    address: EmailStr = Field(..., description="邮箱地址")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Trim surrounding whitespace from display names.

        Args:
            value: Raw display name.

        Returns:
            Normalized display name.
        """
        return value.strip()


class EmailAttachment(BaseModel):
    """Attachment or inline resource metadata.

    Args:
        filename: Original or overridden file name.
        content_type: MIME type of the file.
        size: File size in bytes.
        content_id: Optional CID used by inline images.
        path: Local storage path if the file has been persisted.
        is_inline: Whether the file should be rendered inline.
    """

    filename: str = Field(..., description="附件文件名")
    content_type: str = Field("application/octet-stream", description="MIME 类型")
    size: int = Field(0, description="附件大小（字节）", ge=0)
    content_id: str | None = Field(None, description="内联资源 CID")
    path: str | None = Field(None, description="本地持久化路径")
    is_inline: bool = Field(False, description="是否作为内联资源使用")


class Email(BaseModel):
    """Unified email entity for inbox messages and reply workflows.

    Args:
        id: Internal stable identifier for plugin storage.
        message_id: RFC 5322 Message-ID used for deduplication.
        uid: IMAP UID of the message.
        thread_id: Internal thread identifier used by the plugin.
        in_reply_to: Parent message identifier from the header.
        references: Message reference chain used for threading.
        from_: Sender address structure.
        sender: Optional envelope sender or Sender header.
        reply_to: Optional reply-to addresses.
        to: Primary recipients.
        cc: Carbon copy recipients.
        bcc: Blind carbon copy recipients.
        subject: Email subject line.
        text: Plain text body.
        html: HTML body.
        date: Message declared send time.
        received_date: Actual receive time observed by IMAP.
        is_read: Whether the message is marked as read.
        is_starred: Whether the message is marked important.
        labels: Provider-specific labels or folders.
        priority: Normalized priority level.
        summary: Short summary prepared for agent consumption.
        raw: Raw source message if retained.
        headers: Parsed message headers.
        attachments: Attachment and inline image metadata.
    """

    id: str = Field(..., min_length=1, description="内部唯一 ID")
    message_id: str = Field(..., min_length=1, description="RFC 5322 Message-ID")
    uid: str | None = Field(None, description="IMAP UID")
    thread_id: str | None = Field(None, description="插件内部线程 ID")
    in_reply_to: str | None = Field(None, description="父邮件 Message-ID")
    references: list[str] = Field(default_factory=list, description="线程引用链")

    from_: EmailAddress = Field(..., description="发件人")
    sender: EmailAddress | None = Field(None, description="Sender 头或 envelope sender")
    reply_to: list[EmailAddress] = Field(
        default_factory=list, description="回复地址列表"
    )
    to: list[EmailAddress] = Field(default_factory=list, description="主要收件人")
    cc: list[EmailAddress] = Field(default_factory=list, description="抄送人")
    bcc: list[EmailAddress] = Field(default_factory=list, description="密送人")

    subject: str = Field(..., description="邮件主题")
    text: str = Field("", description="正文（纯文本）")
    html: str = Field("", description="正文（HTML）")

    date: datetime = Field(..., description="邮件发送时间")
    received_date: datetime | None = Field(None, description="实际接收时间")

    is_read: bool = Field(False, description="是否已读")
    is_starred: bool = Field(False, description="是否标记为重要")
    labels: list[str] = Field(default_factory=list, description="邮件标签")
    priority: Literal["high", "medium", "low"] = Field(
        "medium", description="邮件优先级"
    )
    summary: str = Field("", description="邮件内容摘要")

    raw: str | None = Field(None, description="原始邮件全文")
    headers: dict[str, str | list[str]] = Field(
        default_factory=dict, description="完整邮件头"
    )
    attachments: list[EmailAttachment] = Field(
        default_factory=list, description="附件信息列表"
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("subject", "text", "html", "summary")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        """Normalize line-oriented text fields by trimming surrounding whitespace.

        Args:
            value: Raw string value.

        Returns:
            Normalized string.
        """
        return value.strip()

    @field_validator("references")
    @classmethod
    def normalize_references(cls, value: list[str]) -> list[str]:
        """Remove empty message references while preserving order.

        Args:
            value: Raw reference chain.

        Returns:
            Filtered reference chain.
        """
        return [item.strip() for item in value if item.strip()]

    @field_validator("labels")
    @classmethod
    def normalize_labels(cls, value: list[str]) -> list[str]:
        """Remove empty labels while preserving order.

        Args:
            value: Raw labels.

        Returns:
            Filtered labels.
        """
        return [item.strip() for item in value if item.strip()]


class OutgoingMailRequest(BaseModel):
    """Validated outbound mail request used by the SMTP tool.

    Args:
        to: Primary recipient list.
        subject: Subject line without the configured prefix.
        text_body: Plain text body.
        html_body: Optional HTML body.
        cc: Carbon copy recipients.
        bcc: Blind carbon copy recipients.
        reply_to: Optional reply-to address.
        in_reply_to: Optional parent Message-ID.
        references: Optional message reference chain.
    """

    to: list[EmailStr] = Field(..., min_length=1, description="主要收件人")
    subject: str = Field(..., min_length=1, description="邮件主题")
    text_body: str = Field("", description="纯文本正文")
    html_body: str = Field("", description="HTML 正文")
    cc: list[EmailStr] = Field(default_factory=list, description="抄送人")
    bcc: list[EmailStr] = Field(default_factory=list, description="密送人")
    reply_to: EmailStr | None = Field(None, description="回复地址")
    in_reply_to: str | None = Field(None, description="父邮件 Message-ID")
    references: list[str] = Field(default_factory=list, description="线程引用链")

    @field_validator("subject", "text_body", "html_body", "in_reply_to")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Trim text-like fields before validation completes.

        Args:
            value: Raw text value.

        Returns:
            Normalized text value.
        """
        if value is None:
            return None
        return value.strip()

    @field_validator("references")
    @classmethod
    def normalize_outgoing_references(cls, value: list[str]) -> list[str]:
        """Drop empty references while preserving order.

        Args:
            value: Raw reference chain.

        Returns:
            Filtered reference list.
        """
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def validate_body_content(self) -> "OutgoingMailRequest":
        """Require at least one non-empty body representation.

        Returns:
            The validated outgoing mail request.

        Raises:
            ValueError: Raised when both plain text and HTML bodies are empty.
        """
        if not self.text_body and not self.html_body:
            raise ValueError("text_body 和 html_body 至少需要提供一个。")
        return self

    @property
    def all_recipients(self) -> list[str]:
        """Return a deduplicated recipient list for SMTP delivery.

        Returns:
            Recipients in stable order.
        """
        recipients: list[str] = []
        for address in [*self.to, *self.cc, *self.bcc]:
            normalized = str(address)
            if normalized not in recipients:
                recipients.append(normalized)
        return recipients


class MailboxSettings(BaseModel):
    """Mailbox connection and safety settings for the plugin.

    Args:
        email_address: Primary mailbox address owned by the bot.
        imap_username: Optional IMAP login name.
        imap_server: IMAP server hostname.
        imap_port: IMAP server port.
        imap_password: IMAP password or app token.
        imap_use_tls: Whether to use implicit TLS for IMAP.
        imap_folder: Inbox folder name to watch.
        imap_interval: Polling interval in seconds.
        enable_agent_inbox_processing: Whether received email bodies are sent to the
            subscribed session's LLM for analysis and draft generation.
        smtp_username: Optional SMTP login name.
        smtp_server: SMTP server hostname.
        smtp_port: SMTP server port.
        smtp_password: SMTP password or app token.
        smtp_security_mode: SMTP security mode: 0 for plain, 1 for implicit TLS,
            and 2 for STARTTLS.
        smtp_timeout_seconds: SMTP send timeout in seconds.
        smtp_sender_name: Display name used for outgoing mail.
        smtp_prefix: Subject prefix for outgoing mail.
        smtp_max_html_length: Maximum allowed HTML length.
        require_reply_confirmation: Whether the agent must ask before replying.
        allowed_recipient_domains: Optional allowlist for outgoing domains.
        blocked_recipient_domains: Optional denylist for outgoing domains.
    """

    email_address: EmailStr = Field(..., description="邮箱地址")

    imap_username: str = Field("", description="IMAP 登录用户名")
    imap_server: str = Field(..., description="IMAP 服务器地址")
    imap_port: int = Field(..., description="IMAP 服务器端口", ge=1, le=65535)
    imap_password: str = Field(..., min_length=1, description="IMAP 应用密码")
    imap_use_tls: bool = Field(True, description="是否使用 IMAP 隐式 TLS")
    imap_folder: str = Field("INBOX", description="监听的邮箱文件夹")
    imap_interval: float = Field(3.0, description="邮件检查间隔（秒）", ge=0.5)
    enable_agent_inbox_processing: bool = Field(
        False, description="是否将新邮件正文发送给 LLM 生成分析和草稿"
    )

    smtp_username: str = Field("", description="SMTP 登录用户名")
    smtp_server: str = Field(..., description="SMTP 服务器地址")
    smtp_port: int = Field(..., description="SMTP 服务器端口", ge=1, le=65535)
    smtp_password: str = Field(..., min_length=1, description="SMTP 应用密码")
    smtp_security_mode: int = Field(
        1,
        description="SMTP 加密模式：0 明文、1 隐式 TLS、2 STARTTLS",
        ge=0,
        le=2,
    )
    smtp_timeout_seconds: float = Field(
        10.0, description="SMTP 发送超时时间（秒）", ge=1.0
    )
    smtp_sender_name: str = Field(..., min_length=1, description="SMTP 发件人姓名")
    smtp_prefix: str = Field("", description="SMTP 邮件主题前缀")
    smtp_max_html_length: int = Field(
        1000, description="SMTP 邮件 HTML 内容最大长度", ge=1
    )

    require_reply_confirmation: bool = Field(
        True, description="回复邮件前是否需要用户确认"
    )
    allowed_recipient_domains: list[str] = Field(
        default_factory=list, description="允许发送的收件域名"
    )
    blocked_recipient_domains: list[str] = Field(
        default_factory=list, description="禁止发送的收件域名"
    )

    @field_validator(
        "imap_username",
        "imap_server",
        "imap_folder",
        "smtp_username",
        "smtp_server",
        "smtp_sender_name",
        "smtp_prefix",
    )
    @classmethod
    def normalize_string_fields(cls, value: str) -> str:
        """Trim surrounding whitespace from configurable string fields.

        Args:
            value: Raw field value.

        Returns:
            Normalized string.
        """
        return value.strip()

    @field_validator("allowed_recipient_domains", "blocked_recipient_domains")
    @classmethod
    def normalize_domain_lists(cls, value: list[str]) -> list[str]:
        """Normalize configured domain lists to lowercase unique items.

        Args:
            value: Raw domain list.

        Returns:
            Normalized domain list.
        """
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            domain = item.strip().lower()
            if domain and domain not in seen:
                seen.add(domain)
                normalized.append(domain)
        return normalized
