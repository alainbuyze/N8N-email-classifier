"""Microsoft Graph API client for mail operations.

Objective:
    Provide a thin wrapper around Microsoft Graph Mail endpoints used by this
    project. This module centralizes HTTP request construction, authentication
    headers, and Pydantic validation of responses.

Responsibilities:
    - Issue authenticated HTTP requests to Graph (via :class:`requests`).
    - Fetch emails from Inbox (default) or a specific folder.
    - Move emails into destination folders.
    - List folders and create folders (for folder manager).

High-level call tree:
    - Public API:
        - :meth:`EmailClient.get_emails` -> returns :class:`src.outlook_categorizer.models.Email`
        - :meth:`EmailClient.move_email`
        - :meth:`EmailClient.get_folders` -> returns :class:`src.outlook_categorizer.models.Folder`
        - :meth:`EmailClient.create_folder`
    - Internal helpers:
        - :meth:`EmailClient._make_request` (auth + error handling)
        - :meth:`EmailClient._get_child_folders` (recursive traversal)

Graph endpoints used:
    - ``GET /me/mailFolders/inbox/messages`` (Inbox default)
    - ``GET /me/mailFolders/{folder_id}/messages`` (explicit folder)
    - ``POST /me/messages/{email_id}/move``
    - ``GET /me/mailFolders``
    - ``GET /me/mailFolders/{id}/childFolders``
    - ``POST /me/mailFolders`` (create root folder)
    - ``POST /me/mailFolders/{id}/childFolders`` (create child folder)

Error handling:
    - HTTP errors are logged and raised from :meth:`_make_request`.
    - Some operations (like moving emails) catch errors and return ``False``.
"""

import logging
from typing import Optional

from urllib.parse import quote
from typing import AbstractSet

import requests

from .auth import GraphAuthenticator
from .config import Settings
from .models import Email, Folder

logger = logging.getLogger(__name__)


class EmailClient:
    """
    Client for interacting with Microsoft Graph API for email operations.

    This class is intentionally state-light: it primarily depends on
    :class:`src.outlook_categorizer.auth.GraphAuthenticator` for tokens and
    builds URLs relative to :attr:`GRAPH_BASE_URL`.

    Attributes:
        settings: Application settings.
        auth: Graph API authenticator.
    """

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, settings: Settings, auth: GraphAuthenticator) -> None:
        """
        Initialize email client.

        Args:
            settings: Application settings.
            auth: Graph API authenticator.
        """
        self.settings = settings
        self.auth = auth

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        suppress_statuses: Optional[AbstractSet[int]] = None,
    ) -> dict:
        """Make an authenticated request to Microsoft Graph.

        This helper:
        - Adds auth headers (Bearer token).
        - Applies a default timeout.
        - Raises for non-2xx responses.
        - Returns decoded JSON or ``{}`` for 204 responses.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            endpoint: API endpoint path.
            params: Query parameters.
            json_data: JSON body data.

        Returns:
            dict: Response JSON data.

        Raises:
            requests.HTTPError: If request fails.
        """
        url = f"{self.GRAPH_BASE_URL}{endpoint}"
        headers = self.auth.get_auth_headers()

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_data,
            timeout=30,
        )

        if not response.ok:
            suppress = suppress_statuses and response.status_code in suppress_statuses
            if suppress:
                logger.debug(
                    "Graph API expected non-2xx: %s - %s",
                    response.status_code,
                    response.text,
                )
            else:
                logger.error(
                    f"Graph API error: {response.status_code} - {response.text}"
                )
            response.raise_for_status()

        if response.status_code == 204:
            return {}

        return response.json()

    def get_emails(
        self,
        folder_id: Optional[str] = None,
        limit: int = 10,
        skip_flagged: bool = True,
        skip_categorized: bool = True,
    ) -> list[Email]:
        """Fetch emails from a mailbox folder.

        By default, emails are fetched from the Inbox folder. This behavior is
        important to avoid processing items from other folders unless explicitly
        requested.

        Filtering behavior:
            - ``skip_flagged`` filters out messages where Graph flagStatus is
              notFlagged.
            - ``skip_categorized`` filters out messages that already have
              categories assigned.

        Args:
            folder_id: Specific folder ID to fetch from (None for Inbox).
            limit: Maximum number of emails to fetch.
            skip_flagged: Skip flagged emails.
            skip_categorized: Skip emails with existing categories.

        Returns:
            list[Email]: List of email objects.
        """
        # Build endpoint
        if folder_id:
            safe_folder_id = quote(folder_id, safe="")
            endpoint = f"/me/mailFolders/{safe_folder_id}/messages"
        else:
            endpoint = "/me/mailFolders/inbox/messages"

        # Build filter
        filters = []
        if skip_flagged:
            filters.append("flag/flagStatus eq 'notFlagged'")
        if skip_categorized:
            filters.append("not categories/any()")

        # Build query parameters
        params = {
            "$top": limit,
            "$select": "id,parentFolderId,subject,receivedDateTime,body,sender,from,toRecipients,importance,isRead,categories,flag",
            "$orderby": "receivedDateTime desc",
        }

        if filters:
            params["$filter"] = " and ".join(filters)

        logger.debug(f"Fetching up to {limit} emails")
        response = self._make_request("GET", endpoint, params=params)

        emails = []
        for item in response.get("value", []):
            try:
                email = Email.model_validate(item)
                emails.append(email)
            except Exception as e:
                logger.warning(f"Failed to parse email: {e}")
                continue

        logger.debug(f"Fetched {len(emails)} emails")
        return emails

    def add_category(
        self,
        email_id: str,
        category: str,
    ) -> bool:
        """Add a category tag to an email.

        This marks the email as categorized so it can be skipped in future runs.

        Args:
            email_id: ID of email to tag.
            category: Category name to add.

        Returns:
            bool: True if successful.
        """
        safe_email_id = quote(email_id, safe="")
        endpoint = f"/me/messages/{safe_email_id}"
        json_data = {"categories": [category]}

        try:
            self._make_request("PATCH", endpoint, json_data=json_data)
            logger.debug(f"Added category '{category}' to email {email_id}")
            return True
        except requests.HTTPError as e:
            logger.warning(f"Failed to add category to email {email_id}: {e}")
            return False

    def move_email(
        self,
        email_id: str,
        folder_id: str,
        source_folder_id: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        """Move an email to a different folder.

        This wraps the Graph move endpoint. Failures are logged and returned as
        ``False`` (rather than raising) since move failures are treated as a
        per-email processing error.

        Optionally adds a category tag to mark the email as processed, preventing
        it from being selected again by skip_categorized filter. The category is
        added BEFORE moving to avoid 404 errors from stale email IDs after move.

        Args:
            email_id: ID of email to move.
            folder_id: Destination folder ID.
            source_folder_id: Source folder ID for fallback.
            category: Optional category name to add before moving.

        Returns:
            bool: True if successful.
        """
        # Add category tag BEFORE moving to avoid 404 errors
        if category:
            self.add_category(email_id, category)
        
        safe_email_id = quote(email_id, safe="")
        endpoint = f"/me/messages/{safe_email_id}/move"
        json_data = {"destinationId": folder_id}

        try:
            self._make_request("POST", endpoint, json_data=json_data)
            logger.debug(f"Moved email {email_id} to folder {folder_id}")
            return True
        except requests.HTTPError as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code == 404 and source_folder_id:
                logger.debug(
                    "Primary move returned 404; attempting fallback (email_id=%r, source_folder_id=%r)",
                    email_id,
                    source_folder_id,
                )
                try:
                    safe_source_folder_id = quote(source_folder_id, safe="")
                    fallback_endpoint = (
                        f"/me/mailFolders/{safe_source_folder_id}"
                        f"/messages/{safe_email_id}/move"
                    )
                    self._make_request("POST", fallback_endpoint, json_data=json_data)
                    logger.debug(
                        "Moved email %s to folder %s using fallback (source_folder_id=%s)",
                        email_id,
                        folder_id,
                        source_folder_id,
                    )
                    return True
                except requests.HTTPError as retry_error:
                    retry_status = getattr(
                        getattr(retry_error, "response", None), "status_code", None
                    )
                    if retry_status == 404:
                        logger.warning(
                            "Message not found (404) on both primary and fallback move; "
                            "likely already moved or deleted (email_id=%s, source_folder_id=%s)",
                            email_id,
                            source_folder_id,
                        )
                    else:
                        logger.error(
                            "Failed to move email %s (fallback) to folder %s: %s",
                            email_id,
                            folder_id,
                            retry_error,
                        )
                    return False

            if status_code == 404:
                logger.warning(
                    "Message not found (404) on primary move; no source_folder_id for fallback "
                    "(email_id=%s). Likely already moved or deleted.",
                    email_id,
                )
                return False

            logger.error(f"Failed to move email {email_id}: {e}")
            return False

    def get_folders(self, include_children: bool = True) -> list[Folder]:
        """Get all mail folders.

        If ``include_children`` is True, this will recursively walk folder
        children to build a flattened list. The folder manager uses this list
        to build caches for name/id lookups.

        Args:
            include_children: Include child folders recursively.

        Returns:
            list[Folder]: List of folder objects.
        """
        endpoint = "/me/mailFolders"
        params = {
            "$top": 100,
            "$select": "id,displayName,parentFolderId,childFolderCount",
        }

        all_folders = []

        response = self._make_request("GET", endpoint, params=params)
        for item in response.get("value", []):
            try:
                folder = Folder.model_validate(item)
                all_folders.append(folder)

                # Recursively get child folders
                if include_children and folder.child_folder_count > 0:
                    child_folders = self._get_child_folders(folder.id)
                    all_folders.extend(child_folders)
            except Exception as e:
                logger.warning(f"Failed to parse folder: {e}")
                continue

        logger.debug(f"Found {len(all_folders)} folders")
        return all_folders

    def _get_child_folders(self, parent_folder_id: str) -> list[Folder]:
        """Get child folders of a parent folder.

        This helper performs a depth-first traversal via Graph.

        Args:
            parent_folder_id: Parent folder ID.

        Returns:
            list[Folder]: List of child folders.
        """
        endpoint = f"/me/mailFolders/{parent_folder_id}/childFolders"
        params = {
            "$top": 100,
            "$select": "id,displayName,parentFolderId,childFolderCount",
        }

        folders = []
        try:
            response = self._make_request("GET", endpoint, params=params)
            for item in response.get("value", []):
                folder = Folder.model_validate(item)
                folders.append(folder)

                # Recursively get grandchildren
                if folder.child_folder_count > 0:
                    grandchildren = self._get_child_folders(folder.id)
                    folders.extend(grandchildren)
        except Exception as e:
            logger.warning(f"Failed to get child folders: {e}")

        return folders

    def create_folder(
        self, display_name: str, parent_folder_id: Optional[str] = None
    ) -> Optional[Folder]:
        """Create a new mail folder.

        Folder creation is used primarily by :class:`src.outlook_categorizer.folder_manager.FolderManager`.
        If Graph returns a conflict (HTTP 409), this function returns ``None``
        and lets the folder manager refresh and retry.

        Args:
            display_name: Name for the new folder.
            parent_folder_id: Parent folder ID (None for root level).

        Returns:
            Optional[Folder]: Created folder, or None if failed.
        """
        if parent_folder_id:
            endpoint = f"/me/mailFolders/{parent_folder_id}/childFolders"
        else:
            endpoint = "/me/mailFolders"

        json_data = {"displayName": display_name}

        try:
            response = self._make_request(
                "POST",
                endpoint,
                json_data=json_data,
                suppress_statuses={409},
            )
            folder = Folder.model_validate(response)
            logger.debug(f"Created folder: {display_name}")
            return folder
        except requests.HTTPError as e:
            # Folder might already exist
            if e.response.status_code == 409:
                logger.debug(f"Folder already exists: {display_name}")
                return None
            logger.error(f"Failed to create folder {display_name}: {e}")
            return None
