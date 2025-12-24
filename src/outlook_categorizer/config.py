"""Application configuration and settings.

Objective:
    Provide a single source of truth for runtime configuration used across the
    application (Graph auth, Groq, categorization rules, and batch processing
    behavior).

Responsibilities:
    - Define the canonical set of email categories (:class:`EmailCategory`).
    - Load environment-driven settings via :class:`Settings` (Pydantic
      BaseSettings).
    - Provide small convenience helpers for frequently used derived settings
      (e.g., parsing comma-separated collaborator email lists).

High-level call tree:
    - :func:`get_settings` -> returns :class:`Settings`
    - :class:`Settings`
        - :attr:`Settings.collaborator_email_list`
        - :attr:`Settings.categories_list`

Operational notes:
    - ``Settings`` loads from ``.env`` by default via ``pydantic-settings``.
    - Most modules accept a ``Settings`` object explicitly to enable testing;
      the orchestrator falls back to :func:`get_settings` when not provided.
"""

from enum import Enum
from typing import Optional
import logging

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Category tag applied to processed emails to prevent reprocessing
CATEGORIZED_TAG = "Categorized"

class EmailCategory(str, Enum):
    """Canonical set of categories used by the system.

    These values are referenced by:
    - the LLM prompt
    - deterministic heuristics
    - folder creation/routing

    The Enum values are the user-facing folder names.
    """

    ACTION = "Action"
    RESPONSE = "Response"
    JUNK = "Junk"
    SPAM = "Spam"
    RECEIPT = "Receipt"
    BOSS = "Boss"
    COMPANY = "Company"
    COLLABORATORS = "Collaborators"
    COMMUNITY = "Community"
    BUSINESS = "Business"
    OTHER = "Other"
    SECURITY = "Security"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    The settings model is intentionally flat and human-editable via `.env`.
    Most fields map directly to environment variables.

    Function tree:
        - :meth:`collaborator_email_list` derives a normalized list from the
          raw comma-separated env var.
        - :meth:`categories_list` exposes category names as strings.

    Attributes:
        azure_client_id: Azure AD application client ID.
        azure_client_secret: Azure AD application client secret.
        azure_tenant_id: Azure AD tenant ID.
        groq_api_key: Groq API key for LLM access.
        groq_model: Groq model to use for categorization.
        boss_email: Email address of the boss for categorization.
        company_domain: Company domain for categorization.
        inbox_folder_id: Optional specific folder ID to process.
        email_batch_size: Number of emails to process per batch.
        log_level: Logging level.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Azure AD Configuration
    azure_client_id: str = Field(..., description="Azure AD application client ID")
    azure_client_secret: Optional[str] = Field(
        default=None, description="Azure AD application client secret (for client credentials flow)"
    )
    azure_tenant_id: str = Field(
        default="consumers", description="Azure AD tenant ID (consumers for personal accounts)"
    )

    outlook_account_username: Optional[str] = Field(
        default=None,
        description=(
            "Preferred Outlook account username to select from the MSAL token cache. "
            "If omitted, the first cached account is used."
        ),
    )

    device_code_prompt_mode: str = Field(
        default="console",
        description=(
            "How to surface device-code authentication instructions. "
            "Use 'console' to print to stdout. Use 'web' to raise a structured exception so the web UI can render it."
        ),
    )
    
    use_client_credentials: bool = Field(
        default=False,
        description=(
            "Use client credentials flow instead of device code flow. "
            "Requires an organizational tenant (not 'consumers')."
        ),
    )
    
    target_user_principal_name: Optional[str] = Field(
        default=None,
        description=(
            "User principal name (email) for the mailbox to access when using "
            "client credentials flow. Required when using application permissions."
        ),
    )

    # Token cache persistence (Azure)
    token_cache_backend: str = Field(
        default="file",
        description=(
            "Token cache backend. 'file' stores cache on local filesystem. "
            "'azure_blob' stores cache JSON in Azure Blob Storage (recommended for Azure Container Apps)."
        ),
    )
    token_cache_blob_account_url: Optional[str] = Field(
        default=None,
        description="Azure Storage account URL, e.g. https://<account>.blob.core.windows.net",
    )
    token_cache_blob_container: Optional[str] = Field(
        default=None,
        description="Azure Blob container name for MSAL token cache",
    )
    token_cache_blob_name: str = Field(
        default="msal_token_cache.json",
        description="Azure Blob name for MSAL token cache",
    )

    # Groq Configuration
    groq_api_key: str = Field(..., description="Groq API key")
    groq_model: str = Field(
        default="openai/gpt-oss-120b", description="Groq model name"
    )

    # Categorization Settings
    boss_email: str = Field(default="", description="Boss email address")
    company_domain: str = Field(default="", description="Company domain")
    management_emails: str = Field(
        default="", description="Comma-separated list of management emails"
    )
    direct_reports_emails: str = Field(
        default="", description="Comma-separated list of direct report emails"
    )
    collaborator_emails: str = Field(
        default="", description="Comma-separated list of collaborator emails"
    )

    # Processing Settings
    inbox_folder_id: Optional[str] = Field(
        default=None, description="Specific folder ID to process"
    )
    email_batch_size: int = Field(
        default=10, ge=1, le=50, description="Emails per batch"
    )
    log_level: str = Field(default="INFO", description="Logging level")

    @property
    def collaborator_email_list(self) -> list[str]:
        """
        Parse collaborator emails from comma-separated string.

        This is used by :meth:`src.outlook_categorizer.categorizer.EmailCategorizer._apply_heuristics`
        to force deterministic routing of known collaborators.

        Returns:
            list[str]: List of collaborator email addresses.
        """
        if not self.collaborator_emails:
            return []
        return [email.strip().lower() for email in self.collaborator_emails.split(",")]

    @property
    def management_email_list(self) -> list[str]:
        """Parse management emails from comma-separated string.

        Returns:
            list[str]: List of management email addresses.
        """
        if not self.management_emails:
            return []
        return [email.strip().lower() for email in self.management_emails.split(",")]

    @property
    def direct_reports_email_list(self) -> list[str]:
        """Parse direct report emails from comma-separated string.

        Returns:
            list[str]: List of direct report email addresses.
        """
        if not self.direct_reports_emails:
            return []
        return [email.strip().lower() for email in self.direct_reports_emails.split(",")]

    @property
    def categories_list(self) -> list[str]:
        """
        Get list of all valid category names.

        This list is used when building the system/user prompts to constrain
        the model output to known folder names.

        Returns:
            list[str]: List of category names.
        """
        return [cat.value for cat in EmailCategory]


def get_settings() -> Settings:
    """
    Load and return application settings.

    This helper is a convenience for production code. For tests, you typically
    construct a :class:`Settings` instance directly or pass a mocked settings
    object.

    Returns:
        Settings: Application settings instance.

    Raises:
        ValidationError: If required environment variables are missing.
    """
    return Settings()
