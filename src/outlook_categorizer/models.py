"""Pydantic data models used across the application.

Objective:
    Centralize all strongly-typed data structures representing:
    - Email messages returned by Microsoft Graph
    - Categorization outputs returned by the LLM or heuristics
    - Mail folder metadata used for routing
    - Per-email processing results produced by the orchestrator

Design notes:
    - These models use Pydantic aliases to match Microsoft Graph field names
      (e.g. ``receivedDateTime`` -> :attr:`Email.received_date_time`).
    - ``model_config = ConfigDict(populate_by_name=True)`` is used to allow
      constructing models with either alias names or pythonic field names.

High-level structure:
    - Graph email primitives:
        - :class:`EmailAddress`
        - :class:`EmailRecipient`
        - :class:`EmailBody`
        - :class:`EmailFlag`
        - :class:`Email`
    - Categorization primitives:
        - :class:`CategorizationResult`
        - :class:`ProcessingResult`
    - Folder primitives:
        - :class:`Folder`

Call tree usage:
    - :class:`src.outlook_categorizer.email_client.EmailClient`:
        - validates Graph responses into :class:`Email` and :class:`Folder`
    - :class:`src.outlook_categorizer.categorizer.EmailCategorizer`:
        - returns :class:`CategorizationResult`
    - :class:`src.outlook_categorizer.orchestrator.EmailOrchestrator`:
        - returns :class:`ProcessingResult`
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EmailAddress(BaseModel):
    """Email address with name and address.

    This corresponds to the nested Graph structure:
    ``{"name": "...", "address": "..."}``.
    """

    name: str = ""
    address: str = ""


class EmailRecipient(BaseModel):
    """Email recipient wrapper.

    Microsoft Graph wraps addresses under an ``emailAddress`` object.
    This model captures that wrapper and exposes :attr:`email_address`.
    """

    email_address: EmailAddress = Field(alias="emailAddress")

    model_config = ConfigDict(populate_by_name=True)


class EmailBody(BaseModel):
    """Email body content.

    The body is provided by Graph with both a content type (usually HTML) and
    the raw content string.
    """

    content_type: str = Field(default="text", alias="contentType")
    content: str = ""

    model_config = ConfigDict(populate_by_name=True)


class EmailFlag(BaseModel):
    """Email flag status.

    This is used to skip flagged emails during fetching.
    """

    flag_status: str = Field(default="notFlagged", alias="flagStatus")

    model_config = ConfigDict(populate_by_name=True)


class Email(BaseModel):
    """
    Email message from Microsoft Graph API.

    Attributes:
        id: Unique message ID.
        subject: Email subject line.
        body: Email body content.
        sender: Sender information.
        from_recipient: From address information.
        to_recipients: List of recipients.
        importance: Email importance level.
        is_read: Whether email has been read.
        categories: Existing categories on the email.
        flag: Flag status.
    """

    id: str
    subject: str = ""
    received_date_time: Optional[datetime] = Field(default=None, alias="receivedDateTime")
    body: EmailBody = Field(default_factory=EmailBody)
    sender: Optional[EmailRecipient] = None
    from_recipient: Optional[EmailRecipient] = Field(default=None, alias="from")
    to_recipients: list[EmailRecipient] = Field(default_factory=list, alias="toRecipients")
    importance: str = "normal"
    is_read: bool = Field(default=False, alias="isRead")
    categories: list[str] = Field(default_factory=list)
    flag: EmailFlag = Field(default_factory=EmailFlag)

    model_config = ConfigDict(populate_by_name=True)

    @property
    def sender_email(self) -> str:
        """Get sender email address.

        Returns:
            str: Sender email address lowercased, or an empty string if missing.
        """
        if self.sender and self.sender.email_address:
            return self.sender.email_address.address.lower()
        return ""

    @property
    def from_email(self) -> str:
        """Get from email address.

        Some emails have both ``sender`` and ``from`` populated. The
        categorizer uses both to make routing decisions.

        Returns:
            str: From email address lowercased, or an empty string if missing.
        """
        if self.from_recipient and self.from_recipient.email_address:
            return self.from_recipient.email_address.address.lower()
        return ""


class CategorizationResult(BaseModel):
    """
    Result of AI or heuristic email categorization.

    The LLM is instructed to return JSON using keys like ``ID`` and
    ``subCategory``. This model accepts both alias keys and pythonic names.

    Attributes:
        id: Original email ID.
        subject: Email subject.
        category: Primary category assigned.
        sub_category: Optional subcategory.
        analysis: Brief explanation of categorization.
    """

    id: str = Field(alias="ID", default="")
    subject: str = ""
    category: str
    sub_category: Optional[str] = Field(default=None, alias="subCategory")
    analysis: str = ""

    model_config = ConfigDict(populate_by_name=True)


class Folder(BaseModel):
    """
    Outlook mail folder.

    This model represents both top-level folders and nested subfolders.

    Attributes:
        id: Unique folder ID.
        display_name: Folder display name.
        parent_folder_id: Parent folder ID.
        child_folder_count: Number of child folders.
    """

    id: str
    display_name: str = Field(alias="displayName")
    parent_folder_id: Optional[str] = Field(default=None, alias="parentFolderId")
    child_folder_count: int = Field(default=0, alias="childFolderCount")

    model_config = ConfigDict(populate_by_name=True)


class ProcessingResult(BaseModel):
    """
    Result of processing a single email.

    This is the primary output type returned to the CLI and web UI.
    It captures both the final categorization decision and whether the email
    move operation succeeded.

    Attributes:
        email_id: Original email ID.
        subject: Email subject.
        category: Assigned category.
        sub_category: Assigned subcategory.
        folder_id: Destination folder ID.
        success: Whether processing succeeded.
        error: Error message if failed.
    """

    email_id: str
    subject: str
    sender: str = ""
    received_date_time: Optional[datetime] = None
    category: str
    sub_category: Optional[str] = None
    folder_id: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
