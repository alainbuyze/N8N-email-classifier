"""Microsoft Graph authentication.

Objective:
    Provide a small, reusable authentication layer for Microsoft Graph API
    requests. This module is responsible for acquiring and caching an OAuth2
    access token that can be attached to HTTP requests.

Responsibilities:
    - Manage MSAL ``PublicClientApplication`` lifecycle.
    - Persist and reload the MSAL token cache to/from disk.
    - Perform interactive device-code authentication when no cached token is
      available.
    - Provide ready-to-use HTTP headers for Graph API calls.

High-level call tree:
    - :class:`GraphAuthenticator`
        - :meth:`GraphAuthenticator.get_auth_headers`
            - :meth:`GraphAuthenticator.get_access_token`
                - :meth:`GraphAuthenticator._get_app`
                    - :meth:`GraphAuthenticator._load_token_cache`
                - MSAL silent token acquisition
                - Device code flow fallback
                - :meth:`GraphAuthenticator._save_token_cache`

Operational notes:
    - Device-code flow requires user interaction (copy/paste code in browser).
      When running as CLI or in a container, the prompt will be printed to
      stdout.
    - Token cache location is stored in the user's home directory.
"""

import logging
from pathlib import Path
from typing import Optional

import msal

from .config import Settings

logger = logging.getLogger(__name__)

# Token cache file location
TOKEN_CACHE_FILE = Path.home() / ".outlook_categorizer_token_cache.json"


class GraphAuthenticator:
    """
    Handles Microsoft Graph API authentication using MSAL.

    Uses device code flow for personal Microsoft accounts (delegated permissions).

    Attributes:
        settings: Application settings containing Azure AD credentials.
        _app: MSAL public client application instance.
        _account: Cached user account.
    """

    # Delegated scopes for personal accounts
    GRAPH_SCOPES = [
        "https://graph.microsoft.com/Mail.ReadWrite",
        "https://graph.microsoft.com/Mail.Send",
    ]

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the authenticator with settings.

        Args:
            settings: Application settings with Azure AD credentials.
        """
        self.settings = settings
        self._app: Optional[msal.PublicClientApplication] = None
        self._account: Optional[dict] = None

    def _load_token_cache(self) -> msal.SerializableTokenCache:
        """
        Load token cache from file.

        The MSAL cache is serialized to a single JSON file. If the file cannot
        be read or is invalid, the authenticator falls back to an empty cache.

        Returns:
            msal.SerializableTokenCache: Token cache instance.
        """
        cache = msal.SerializableTokenCache()
        if TOKEN_CACHE_FILE.exists():
            try:
                cache.deserialize(TOKEN_CACHE_FILE.read_text())
                logger.debug("Loaded token cache from file")
            except Exception as e:
                logger.warning(f"Failed to load token cache: {e}")
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
                TOKEN_CACHE_FILE.write_text(cache.serialize())
                logger.debug("Saved token cache to file")
            except Exception as e:
                logger.warning(f"Failed to save token cache: {e}")

    def _get_app(self) -> msal.PublicClientApplication:
        """
        Get or create MSAL public client application.

        The application is configured with:
        - The tenant authority derived from settings.
        - The persistent token cache.

        Returns:
            msal.PublicClientApplication: MSAL app instance.
        """
        if self._app is None:
            authority = f"https://login.microsoftonline.com/{self.settings.azure_tenant_id}"
            cache = self._load_token_cache()

            self._app = msal.PublicClientApplication(
                client_id=self.settings.azure_client_id,
                authority=authority,
                token_cache=cache,
            )
            logger.debug("Created MSAL public client application")
        return self._app

    def get_access_token(self) -> str:
        """
        Acquire access token for Microsoft Graph API.

        Strategy:
            1. Try silent token acquisition using the MSAL cache.
            2. If that fails (no cached token, expired refresh token, etc.),
               fall back to device-code flow.

        Tokens are cached and reused until expiration.

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
            result = app.acquire_token_silent(
                scopes=self.GRAPH_SCOPES,
                account=accounts[0],
            )
            if result and "access_token" in result:
                logger.debug("Successfully acquired token from cache")
                self._save_token_cache(app.token_cache)
                return result["access_token"]

        # No cached token, use device code flow
        logger.debug("No cached token, starting device code authentication...")
        flow = app.initiate_device_flow(scopes=self.GRAPH_SCOPES)

        if "user_code" not in flow:
            error = flow.get("error_description", "Unknown error")
            raise RuntimeError(f"Failed to initiate device flow: {error}")

        # Display instructions to user
        print("\n" + "=" * 60)
        print("AUTHENTICATION REQUIRED")
        print("=" * 60)
        print(f"\n{flow['message']}\n")
        print("=" * 60 + "\n")

        # Wait for user to complete authentication
        result = app.acquire_token_by_device_flow(flow)

        if "access_token" in result:
            logger.debug("Successfully authenticated")
            self._save_token_cache(app.token_cache)
            return result["access_token"]

        error_description = result.get("error_description", "Unknown error")
        error = result.get("error", "unknown")
        logger.error(f"Failed to acquire token: {error} - {error_description}")
        raise RuntimeError(f"Failed to acquire access token: {error_description}")

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
