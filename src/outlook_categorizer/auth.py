"""Microsoft Graph authentication.

Objective:
    Provide a small, reusable authentication layer for Microsoft Graph API
    requests. This module is responsible for acquiring and caching an OAuth2
    access token that can be attached to HTTP requests.

Responsibilities:
    - Manage MSAL ``PublicClientApplication`` or ``ConfidentialClientApplication`` lifecycle.
    - Persist and reload the MSAL token cache to/from disk.
    - Perform interactive device-code authentication when no cached token is
      available (delegated permissions).
    - Perform client credentials authentication for unattended scenarios
      (application permissions).
    - Provide ready-to-use HTTP headers for Graph API calls.

High-level call tree:
    - :class:`GraphAuthenticator`
        - :meth:`GraphAuthenticator.get_auth_headers`
            - :meth:`GraphAuthenticator.get_access_token`
                - :meth:`GraphAuthenticator._get_token_client_credentials` (if client secret provided)
                - :meth:`GraphAuthenticator._get_token_device_code` (fallback for delegated)
                - :meth:`GraphAuthenticator._get_app`
                    - :meth:`GraphAuthenticator._load_token_cache`
                - :meth:`GraphAuthenticator._save_token_cache`

Operational notes:
    - Client credentials flow is used when AZURE_CLIENT_SECRET is set.
      This requires application permissions in Azure AD.
    - Device-code flow requires user interaction (copy/paste code in browser).
      When running as CLI or in a container, the prompt will be printed to
      stdout.
    - Token cache location is stored in the user's home directory.
"""

import logging
from pathlib import Path
from typing import Any, Optional

import msal

from .config import Settings
from .token_cache_blob import BlobTokenCacheLocation, BlobTokenCacheStore, is_valid_msal_cache_json

logger = logging.getLogger(__name__)

# Token cache file location
TOKEN_CACHE_FILE = Path.home() / ".outlook_categorizer_token_cache.json"


class DeviceCodeAuthRequired(RuntimeError):
    """Raised when interactive device-code authentication is required.

    Args:
        flow: MSAL device flow payload returned by ``initiate_device_flow``.
    """

    def __init__(self, flow: dict[str, Any]) -> None:
        super().__init__(flow.get("message") or "Device code authentication required")
        self.flow = flow

    @property
    def user_code(self) -> str:
        """Return the device code shown to the user.

        Returns:
            str: User code.
        """

        return str(self.flow.get("user_code", ""))

    @property
    def verification_uri(self) -> str:
        """Return the verification URL.

        Returns:
            str: Verification URL.
        """

        return str(
            self.flow.get("verification_uri")
            or self.flow.get("verification_uri_complete")
            or "https://www.microsoft.com/link"
        )

    @property
    def message(self) -> str:
        """Return the MSAL-generated instruction message.

        Returns:
            str: Instruction message.
        """

        return str(self.flow.get("message") or "")


class GraphAuthenticator:
    """
    Handles Microsoft Graph API authentication using MSAL.

    Supports two authentication modes:
    1. Client credentials flow (application permissions) - for unattended scenarios
    2. Device code flow (delegated permissions) - for interactive scenarios

    Attributes:
        settings: Application settings containing Azure AD credentials.
        _app: MSAL public or confidential client application instance.
        _account: Cached user account.
    """

    # Delegated scopes for personal accounts
    GRAPH_SCOPES = [
        "https://graph.microsoft.com/Mail.ReadWrite",
        "https://graph.microsoft.com/Mail.Send",
    ]
    
    # Application scopes for client credentials flow
    GRAPH_APP_SCOPES = [
        "https://graph.microsoft.com/.default",
    ]

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the authenticator with settings.

        Args:
            settings: Application settings with Azure AD credentials.
        """
        self.settings = settings
        self._app: Optional[msal.PublicClientApplication | msal.ConfidentialClientApplication] = None
        self._account: Optional[dict] = None
        self._use_client_credentials = bool(settings.use_client_credentials)
        self._blob_cache: Optional[BlobTokenCacheStore] = None
        if self.settings.token_cache_backend == "azure_blob":
            account_url = (self.settings.token_cache_blob_account_url or "").strip()
            container = (self.settings.token_cache_blob_container or "").strip()
            blob_name = (self.settings.token_cache_blob_name or "").strip()
            if account_url and container and blob_name:
                self._blob_cache = BlobTokenCacheStore(
                    BlobTokenCacheLocation(
                        account_url=account_url,
                        container_name=container,
                        blob_name=blob_name,
                    )
                )
            else:
                logger.warning(
                    "token_cache_backend=azure_blob but blob settings are incomplete; falling back to file cache"
                )

    def _load_token_cache(self) -> msal.SerializableTokenCache:
        """
        Load token cache from file.

        The MSAL cache is serialized to a single JSON file. If the file cannot
        be read or is invalid, the authenticator falls back to an empty cache.

        Returns:
            msal.SerializableTokenCache: Token cache instance.
        """
        cache = msal.SerializableTokenCache()

        if self._blob_cache is not None:
            try:
                payload, _etag = self._blob_cache.download()
                if payload and is_valid_msal_cache_json(payload):
                    cache.deserialize(payload)
                    logger.debug("Loaded token cache from Azure Blob")
                    return cache
                else:
                    logger.debug("Azure Blob cache missing or invalid; falling back to file")
            except Exception as e:
                logger.warning(f"Failed to load token cache from Azure Blob: {e}")

        if TOKEN_CACHE_FILE.exists():
            try:
                cache.deserialize(TOKEN_CACHE_FILE.read_text())
                logger.debug("Loaded token cache from file")
            except Exception as e:
                logger.warning(f"Failed to load token cache: {e}")
        else:
            logger.debug("No token cache file found; starting with empty cache")
        return cache

    def _save_token_cache(self, cache: msal.SerializableTokenCache) -> None:
        """
        Save token cache to file.

        MSAL tracks whether the cache has changed. This function only writes to
        disk when a new token has been acquired or refreshed.

        Args:
            cache: Token cache to save.
        """
        if cache.has_state_changed:
            try:
                payload = cache.serialize()

                if self._blob_cache is not None:
                    existing, etag = self._blob_cache.download()
                    # Reason: If blob contains invalid data, treat as missing
                    if existing and not is_valid_msal_cache_json(existing):
                        etag = None
                    self._blob_cache.upload(payload, etag=etag)
                    logger.debug("Saved token cache to Azure Blob")
                    return

                TOKEN_CACHE_FILE.write_text(payload)
                logger.debug("Saved token cache to file")
            except Exception as e:
                logger.warning(f"Failed to save token cache: {e}")

    def _get_app(self) -> msal.PublicClientApplication | msal.ConfidentialClientApplication:
        """
        Get or create MSAL client application.

        Creates either a ConfidentialClientApplication (for client credentials)
        or PublicClientApplication (for device code flow) based on whether
        a client secret is configured.

        The application is configured with:
        - The tenant authority derived from settings.
        - The persistent token cache (for public client only).

        Returns:
            msal.PublicClientApplication | msal.ConfidentialClientApplication: MSAL app instance.
        """
        if self._app is None:
            authority = f"https://login.microsoftonline.com/{self.settings.azure_tenant_id}"
            
            if self._use_client_credentials:
                if not self.settings.azure_client_secret:
                    raise RuntimeError(
                        "use_client_credentials=true requires AZURE_CLIENT_SECRET to be set"
                    )
                self._app = msal.ConfidentialClientApplication(
                    client_id=self.settings.azure_client_id,
                    client_credential=self.settings.azure_client_secret,
                    authority=authority,
                )
                logger.debug("Created MSAL confidential client application (client credentials flow)")
            else:
                cache = self._load_token_cache()
                self._app = msal.PublicClientApplication(
                    client_id=self.settings.azure_client_id,
                    authority=authority,
                    token_cache=cache,
                )
                logger.debug("Created MSAL public client application (device code flow)")
        return self._app

    def _select_account(self, accounts: list[dict]) -> Optional[dict]:
        """Select a cached MSAL account.

        The app may have multiple cached accounts if the user authenticated
        different Outlook identities over time. When
        ``settings.outlook_account_username`` is set, this function selects the
        matching account by username (case-insensitive). Otherwise it returns
        the first cached account.

        Args:
            accounts: List of cached MSAL accounts.

        Returns:
            Optional[dict]: Selected account or None when no accounts exist.

        Raises:
            ValueError: If a preferred username is configured but not found.
        """
        if not accounts:
            return None

        preferred = (self.settings.outlook_account_username or "").strip()
        if not preferred:
            return accounts[0]

        preferred_lower = preferred.lower()
        for account in accounts:
            username = str(account.get("username", "")).strip().lower()
            if username and username == preferred_lower:
                return account

        available = [a.get("username") for a in accounts if a.get("username")]
        raise ValueError(
            "Configured OUTLOOK_ACCOUNT_USERNAME was not found in token cache. "
            f"preferred={preferred!r} available={available!r}"
        )

    def _get_token_client_credentials(self) -> str:
        """
        Acquire access token using client credentials flow.

        This is used for unattended scenarios where the app runs with
        application permissions (not delegated permissions).

        Returns:
            str: Valid access token for Graph API.

        Raises:
            RuntimeError: If token acquisition fails.
        """
        app = self._get_app()
        logger.debug("Acquiring token using client credentials flow...")
        
        result = app.acquire_token_for_client(scopes=self.GRAPH_APP_SCOPES)
        
        if "access_token" in result:
            logger.debug("Successfully acquired token via client credentials")
            return result["access_token"]
        
        error_description = result.get("error_description", "Unknown error")
        error = result.get("error", "unknown")
        logger.error(f"Failed to acquire token: {error} - {error_description}")
        raise RuntimeError(f"Failed to acquire access token: {error_description}")

    def acquire_token_by_device_flow(self, flow: dict[str, Any]) -> dict[str, Any]:
        """Poll the device-code flow to obtain an access token.

        Args:
            flow: MSAL device flow payload from ``initiate_device_flow``.

        Returns:
            dict[str, Any]: Raw MSAL result.
        """

        app = self._get_app()
        return app.acquire_token_by_device_flow(flow)
    
    def _get_token_device_code(self) -> str:
        """
        Acquire access token using device code flow.

        This is used for interactive scenarios with delegated permissions.

        Returns:
            str: Valid access token for Graph API.

        Raises:
            RuntimeError: If token acquisition fails.
        """
        app = self._get_app()
        
        # Try to get token from cache first
        accounts = app.get_accounts()
        if accounts:
            logger.debug(f"Found {len(accounts)} cached account(s)")
            selected = self._select_account(accounts)
            result = app.acquire_token_silent(
                scopes=self.GRAPH_SCOPES,
                account=selected,
            )
            if result and "access_token" in result:
                logger.debug("Successfully acquired token from cache")
                self._save_token_cache(app.token_cache)
                return result["access_token"]
            else:
                logger.debug(f"Silent acquisition failed for account {selected.get('username')}: {result.get('error') if result else 'no result'}")
        else:
            logger.debug("No cached accounts found")

        # No cached token, use device code flow
        logger.debug("No cached token, starting device code authentication...")
        flow = app.initiate_device_flow(scopes=self.GRAPH_SCOPES)

        if "user_code" not in flow:
            error = flow.get("error_description", "Unknown error")
            raise RuntimeError(f"Failed to initiate device flow: {error}")

        if self.settings.device_code_prompt_mode == "web":
            raise DeviceCodeAuthRequired(flow)

        # Display instructions to user
        print("\n" + "=" * 60)
        print("AUTHENTICATION REQUIRED")
        print("=" * 60)
        print(f"\n{flow['message']}\n")
        print("=" * 60 + "\n")

        # Wait for user to complete authentication
        result = self.acquire_token_by_device_flow(flow)

        if "access_token" in result:
            logger.debug("Successfully authenticated")
            self._save_token_cache(app.token_cache)
            return result["access_token"]

        error_description = result.get("error_description", "Unknown error")
        error = result.get("error", "unknown")
        logger.error(f"Failed to acquire token: {error} - {error_description}")
        raise RuntimeError(f"Failed to acquire access token: {error_description}")
    
    def get_access_token(self) -> str:
        """
        Acquire access token for Microsoft Graph API.

        Strategy:
            1. If client secret is configured, use client credentials flow.
            2. Otherwise, try silent token acquisition using the MSAL cache.
            3. If that fails (no cached token, expired refresh token, etc.),
               fall back to device-code flow.

        Tokens are cached and reused until expiration.

        Returns:
            str: Valid access token for Graph API.

        Raises:
            RuntimeError: If token acquisition fails.
        """
        if self._use_client_credentials:
            return self._get_token_client_credentials()
        else:
            return self._get_token_device_code()

    def get_auth_headers(self) -> dict[str, str]:
        """
        Get HTTP headers with authorization for Graph API requests.

        Returns a dict suitable for ``requests`` or any other HTTP client.

        Returns:
            dict[str, str]: Headers dictionary with Bearer token.
        """
        token = self.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def logout(self) -> None:
        """
        Clear cached tokens and log out.

        This removes the persisted token cache file and resets the in-memory
        MSAL application reference.
        """
        if TOKEN_CACHE_FILE.exists():
            TOKEN_CACHE_FILE.unlink()
            logger.debug("Cleared token cache")
        self._app = None
        self._account = None
