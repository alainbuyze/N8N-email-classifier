"""Folder management and destination resolution.

Objective:
    Provide a higher-level abstraction for working with Outlook mail folders
    during categorization. This module maps a categorization decision
    (category/subcategory) to an actual Graph folder id, creating folders when
    necessary.

Responsibilities:
    - Cache mailbox folders for fast lookups by name/id.
    - Resolve a destination folder for a given categorization.
    - Create missing category or subcategory folders.
    - Resolve human-friendly folder labels/paths to actual folders.

Caching strategy:
    Folder names in Outlook are not globally unique (a child folder can share a
    name with a root folder). To avoid cache collisions:
    - ``_folder_cache`` stores *one* folder per lowercased display name for
      convenience.
    - ``_child_folder_cache`` stores folders keyed by
      ``(parent_folder_id, lowercased_display_name)`` for safe subfolder
      resolution.

High-level call tree:
    - :class:`FolderManager`
        - :meth:`initialize` / :meth:`refresh` (load caches)
        - :meth:`resolve_folder_label` (CLI/web source folder selection)
        - :meth:`get_destination_folder`
            - :meth:`ensure_subcategory_folder`
                - :meth:`ensure_category_folder`
                - :meth:`EmailClient.create_folder`
            - :meth:`ensure_category_folder`
                - :meth:`EmailClient.create_folder`

Operational notes:
    - Folder creation is opportunistic; when a create call returns conflict, we
      refresh and attempt to read again.
"""

import logging
from typing import Optional

from .email_client import EmailClient
from .models import Folder, CategorizationResult

logger = logging.getLogger(__name__)


class FolderManager:
    """
    Manages email folders for categorization.

    Caches folder information and handles folder creation.

    Attributes:
        email_client: Email client for API operations.
        _folder_cache: Cached folder lookup by name.
        _folder_id_cache: Cached folder lookup by ID.
    """

    def __init__(self, email_client: EmailClient) -> None:
        """
        Initialize folder manager.

        Args:
            email_client: Email client for folder operations.
        """
        self.email_client = email_client
        self._folder_cache: dict[str, Folder] = {}
        self._folder_id_cache: dict[str, Folder] = {}
        self._child_folder_cache: dict[tuple[str, str], Folder] = {}
        self._root_folder_ids: set[str] = set()
        self._initialized = False

    def initialize(self) -> None:
        """
        Load and cache all folders from mailbox.

        This builds:
        - name -> folder cache
        - id -> folder cache
        - (parent_id, name) -> folder cache

        The cache is populated from :meth:`EmailClient.get_folders` which may
        recursively list child folders.
        """
        root_folders = self.email_client.get_folders(include_children=False)
        self._root_folder_ids = {f.id for f in root_folders}

        folders = self.email_client.get_folders(include_children=True)

        self._folder_cache.clear()
        self._folder_id_cache.clear()
        self._child_folder_cache.clear()

        for folder in folders:
            # Cache by lowercase name for case-insensitive lookup
            self._folder_cache[folder.display_name.lower()] = folder
            self._folder_id_cache[folder.id] = folder

            if folder.parent_folder_id:
                key = (folder.parent_folder_id, folder.display_name.lower())
                self._child_folder_cache[key] = folder

        self._initialized = True
        logger.debug(f"Initialized folder cache with {len(folders)} folders")

    def refresh(self) -> None:
        """
        Refresh folder cache from mailbox.

        This is a thin wrapper around :meth:`initialize`.
        """
        self.initialize()

    def get_folder_by_name(self, name: str) -> Optional[Folder]:
        """
        Get folder by display name (case-insensitive).

        Note:
            Since folder names are not guaranteed unique across the mailbox,
            this is best-effort and may return an arbitrary folder when multiple
            folders share a name. Prefer parent-scoped lookups via
            ``_child_folder_cache`` when resolving subfolders.

        Args:
            name: Folder display name.

        Returns:
            Optional[Folder]: Folder if found, None otherwise.
        """
        if not self._initialized:
            self.initialize()

        return self._folder_cache.get(name.lower())

    def get_folder_by_id(self, folder_id: str) -> Optional[Folder]:
        """
        Get folder by ID.

        Folder IDs are unique, so this lookup is always unambiguous.

        Args:
            folder_id: Folder ID.

        Returns:
            Optional[Folder]: Folder if found, None otherwise.
        """
        if not self._initialized:
            self.initialize()

        return self._folder_id_cache.get(folder_id)

    def resolve_folder_label(self, label: str) -> Optional[Folder]:
        """Resolve a folder label or path to a Folder.

        The CLI/web UI uses a human-friendly label rather than a Graph folder
        ID.
        Labels can be:
        - A single folder name (case-insensitive), e.g. "Inbox"
        - A path with '/' or '\\' separators, e.g. "Inbox/Boss".

        Args:
            label: Folder label or path.

        Returns:
            Optional[Folder]: Resolved folder if found, otherwise None.
        """

        if not label:
            return None

        if not self._initialized:
            self.initialize()

        normalized = label.strip().replace("\\", "/")
        parts = [p.strip() for p in normalized.split("/") if p.strip()]
        if not parts:
            return None

        current = self._resolve_root_preferred_folder_name(parts[0])
        if not current:
            return None

        for part in parts[1:]:
            cache_key = (current.id, part.lower())
            child = self._child_folder_cache.get(cache_key)
            if not child:
                return None
            current = child

        return current

    def _resolve_root_preferred_folder_name(self, name: str) -> Optional[Folder]:
        """Resolve a single folder name, preferring the root-level folder.

        Folder names are not globally unique; a mailbox can contain multiple
        folders with the same display name at different depths.

        Args:
            name: Folder display name.

        Returns:
            Optional[Folder]: Resolved folder.
        """

        if not self._initialized:
            self.initialize()

        lowered = (name or "").strip().lower()
        if not lowered:
            return None

        # Prefer a top-level folder when there are duplicates.
        for folder in self._folder_id_cache.values():
            if folder.display_name.lower() == lowered and folder.id in self._root_folder_ids:
                return folder

        return self.get_folder_by_name(name)

    def get_descendant_folders(self, folder_id: str, include_self: bool = True) -> list[Folder]:
        """Return all descendant folders for a folder id.

        This uses the cached folder list built by :meth:`initialize`.

        Args:
            folder_id: Root folder id to start from.
            include_self: Whether to include the root folder in results.

        Returns:
            list[Folder]: Folders including all descendants (depth-first).
        """

        if not folder_id:
            return []

        if not self._initialized:
            self.initialize()

        by_parent: dict[str, list[Folder]] = {}
        for folder in self._folder_id_cache.values():
            if folder.parent_folder_id:
                by_parent.setdefault(folder.parent_folder_id, []).append(folder)

        results: list[Folder] = []
        if include_self:
            root = self._folder_id_cache.get(folder_id)
            if root:
                results.append(root)

        stack = list(reversed(by_parent.get(folder_id, [])))
        while stack:
            current = stack.pop()
            results.append(current)

            children = by_parent.get(current.id, [])
            if children:
                stack.extend(reversed(children))

        return results

    def ensure_category_folder(self, category: str) -> Optional[Folder]:
        """
        Ensure a category folder exists, creating if needed.

        This is the root-level destination for a given category when no
        subcategory is provided.

        Args:
            category: Category name for the folder.

        Returns:
            Optional[Folder]: The category folder.
        """
        # Check if folder exists
        existing = self.get_folder_by_name(category)
        if existing:
            return existing

        # Create new folder at root level
        logger.debug(f"Creating category folder: {category}")
        new_folder = self.email_client.create_folder(category)

        if new_folder:
            # Update cache
            self._folder_cache[new_folder.display_name.lower()] = new_folder
            self._folder_id_cache[new_folder.id] = new_folder
            return new_folder

        # Refresh cache and try again (folder might have been created).
        # Reason: Graph returns 409 when a folder already exists; create_folder
        # returns None in that case.
        self.refresh()
        resolved = self._resolve_root_preferred_folder_name(category)
        if resolved:
            return resolved
        return self.get_folder_by_name(category)

    def ensure_subcategory_folder(
        self, category: str, subcategory: str
    ) -> Optional[Folder]:
        """
        Ensure a subcategory folder exists under a category folder.

        This method is careful to avoid name collisions by scoping the lookup
        to the parent category folder.

        Args:
            category: Parent category name.
            subcategory: Subcategory name.

        Returns:
            Optional[Folder]: The subcategory folder.
        """
        if not subcategory:
            return None

        # First ensure parent category folder exists
        parent_folder = self.ensure_category_folder(category)
        if not parent_folder:
            logger.error(f"Failed to get/create parent folder: {category}")
            return None

        # Check if subcategory folder exists (must be scoped by parent)
        cache_key = (parent_folder.id, subcategory.lower())
        existing_child = self._child_folder_cache.get(cache_key)
        if existing_child:
            return existing_child

        # Create subcategory folder
        logger.debug(f"Creating subcategory folder: {subcategory} under {category}")
        new_folder = self.email_client.create_folder(subcategory, parent_folder.id)

        if new_folder:
            # Update cache
            self._folder_cache[new_folder.display_name.lower()] = new_folder
            self._folder_id_cache[new_folder.id] = new_folder
            if new_folder.parent_folder_id:
                child_key = (
                    new_folder.parent_folder_id,
                    new_folder.display_name.lower(),
                )
                self._child_folder_cache[child_key] = new_folder
            return new_folder

        # Refresh and try again.
        # Reason: Graph returns 409 when a folder already exists; create_folder
        # returns None in that case.
        self.refresh()

        # Re-resolve the parent folder in case its id changed or cache updated.
        parent_folder = self._folder_id_cache.get(parent_folder.id) or parent_folder
        cache_key = (parent_folder.id, subcategory.lower())
        resolved_child = self._child_folder_cache.get(cache_key)
        if resolved_child:
            return resolved_child
        return None


    def get_destination_folder(
        self, categorization: CategorizationResult
    ) -> Optional[Folder]:
        """
        Get the destination folder for a categorized email.

        Resolution rules:
            - If a subcategory is present, attempt to ensure the subfolder
              exists under the category folder.
            - If that fails, fall back to the category folder.
            - If no subcategory, ensure and return the category folder.

        Creates folders if they don't exist.

        Args:
            categorization: Categorization result with category/subcategory.

        Returns:
            Optional[Folder]: Destination folder for the email.
        """
        category = categorization.category
        subcategory = categorization.sub_category

        # If there's a subcategory, use that folder
        if subcategory:
            folder = self.ensure_subcategory_folder(category, subcategory)
            if folder:
                return folder
            # Fall back to category folder if subcategory creation fails
            logger.warning(
                f"Failed to create subcategory folder, using category: {category}"
            )

        # Use category folder
        return self.ensure_category_folder(category)

    def list_category_folders(self) -> list[Folder]:
        """
        List all top-level category folders.

        This helper is primarily intended for debugging and inspection.

        Returns:
            list[Folder]: List of category folders.
        """
        if not self._initialized:
            self.initialize()

        # Get folders that are at root level (no parent or parent is Inbox)
        category_folders = []
        for folder in self._folder_cache.values():
            # Check if it's a category folder (matches our categories)
            from .config import EmailCategory

            if folder.display_name in [c.value for c in EmailCategory]:
                category_folders.append(folder)

        return category_folders
