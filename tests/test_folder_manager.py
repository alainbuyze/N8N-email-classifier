"""
Tests for the folder_manager module.
"""

import pytest
from unittest.mock import MagicMock

from src.outlook_categorizer.folder_manager import FolderManager
from src.outlook_categorizer.models import Folder, CategorizationResult


@pytest.fixture
def mock_email_client():
    """Create mock email client."""
    client = MagicMock()
    return client


@pytest.fixture
def sample_folders():
    """Create sample folder list."""
    return [
        Folder(id="folder-1", displayName="Inbox", parentFolderId=None),
        Folder(id="folder-2", displayName="Action", parentFolderId=None),
        Folder(id="folder-3", displayName="Junk", parentFolderId=None),
        Folder(id="folder-4", displayName="Business", parentFolderId=None),
        Folder(id="folder-5", displayName="Urgent", parentFolderId="folder-2"),
    ]


class TestFolderManagerInitialization:
    """Tests for folder manager initialization."""

    def test_initialize_loads_folders(self, mock_email_client, sample_folders):
        """Test that initialize loads and caches folders."""
        mock_email_client.get_folders.return_value = sample_folders

        manager = FolderManager(mock_email_client)
        manager.initialize()

        assert manager._initialized is True
        assert len(manager._folder_cache) == 5
        mock_email_client.get_folders.assert_called_once()

    def test_refresh_reloads_folders(self, mock_email_client, sample_folders):
        """Test that refresh reloads folders."""
        mock_email_client.get_folders.return_value = sample_folders

        manager = FolderManager(mock_email_client)
        manager.initialize()
        manager.refresh()

        assert mock_email_client.get_folders.call_count == 2


class TestFolderManagerLookup:
    """Tests for folder lookup operations."""

    def test_get_folder_by_name_case_insensitive(self, mock_email_client, sample_folders):
        """Test case-insensitive folder lookup by name."""
        mock_email_client.get_folders.return_value = sample_folders

        manager = FolderManager(mock_email_client)
        manager.initialize()

        folder = manager.get_folder_by_name("action")
        assert folder is not None
        assert folder.display_name == "Action"

        folder = manager.get_folder_by_name("ACTION")
        assert folder is not None
        assert folder.display_name == "Action"

    def test_get_folder_by_name_not_found(self, mock_email_client, sample_folders):
        """Test folder lookup when folder doesn't exist."""
        mock_email_client.get_folders.return_value = sample_folders

        manager = FolderManager(mock_email_client)
        manager.initialize()

        folder = manager.get_folder_by_name("NonExistent")
        assert folder is None

    def test_get_folder_by_id(self, mock_email_client, sample_folders):
        """Test folder lookup by ID."""
        mock_email_client.get_folders.return_value = sample_folders

        manager = FolderManager(mock_email_client)
        manager.initialize()

        folder = manager.get_folder_by_id("folder-2")
        assert folder is not None
        assert folder.display_name == "Action"

    def test_resolve_folder_label_single_name(self, mock_email_client, sample_folders):
        """Resolve a single folder label by name."""
        mock_email_client.get_folders.return_value = sample_folders

        manager = FolderManager(mock_email_client)
        manager.initialize()

        resolved = manager.resolve_folder_label("Inbox")
        assert resolved is not None
        assert resolved.id == "folder-1"

    def test_resolve_folder_label_path(self, mock_email_client):
        """Resolve a folder path like Inbox/Boss using child-folder scoping."""
        folders = [
            Folder(id="inbox", displayName="Inbox", parentFolderId=None),
            Folder(id="boss", displayName="Boss", parentFolderId="inbox"),
        ]
        mock_email_client.get_folders.return_value = folders

        manager = FolderManager(mock_email_client)
        manager.initialize()

        resolved = manager.resolve_folder_label("Inbox/Boss")
        assert resolved is not None
        assert resolved.id == "boss"

    def test_resolve_folder_label_not_found(self, mock_email_client, sample_folders):
        """Return None when a label cannot be resolved."""
        mock_email_client.get_folders.return_value = sample_folders

        manager = FolderManager(mock_email_client)
        manager.initialize()

        resolved = manager.resolve_folder_label("Inbox/DoesNotExist")
        assert resolved is None


class TestFolderManagerCreation:
    """Tests for folder creation operations."""

    def test_ensure_category_folder_exists(self, mock_email_client, sample_folders):
        """Test ensuring existing category folder."""
        mock_email_client.get_folders.return_value = sample_folders

        manager = FolderManager(mock_email_client)
        manager.initialize()

        folder = manager.ensure_category_folder("Action")
        assert folder is not None
        assert folder.display_name == "Action"
        mock_email_client.create_folder.assert_not_called()

    def test_ensure_category_folder_creates_new(self, mock_email_client, sample_folders):
        """Test creating new category folder."""
        mock_email_client.get_folders.return_value = sample_folders
        new_folder = Folder(id="folder-new", displayName="Receipt", parentFolderId=None)
        mock_email_client.create_folder.return_value = new_folder

        manager = FolderManager(mock_email_client)
        manager.initialize()

        folder = manager.ensure_category_folder("Receipt")
        assert folder is not None
        assert folder.display_name == "Receipt"
        mock_email_client.create_folder.assert_called_once_with("Receipt")

    def test_ensure_subcategory_folder(self, mock_email_client, sample_folders):
        """Test creating subcategory folder."""
        mock_email_client.get_folders.return_value = sample_folders
        new_subfolder = Folder(id="folder-sub", displayName="Priority", parentFolderId="folder-2")
        mock_email_client.create_folder.return_value = new_subfolder

        manager = FolderManager(mock_email_client)
        manager.initialize()

        folder = manager.ensure_subcategory_folder("Action", "Priority")
        assert folder is not None
        mock_email_client.create_folder.assert_called_once_with("Priority", "folder-2")

    def test_ensure_subcategory_folder_prefers_child_over_root_same_name(
        self, mock_email_client
    ):
        """Test subcategory lookup when root-level folder shares the same name.

        This guards against cache collisions where a root-level folder named
        like a subfolder (e.g. 'Business') could overwrite the subfolder entry.
        """

        folders = [
            Folder(id="folder-action", displayName="Action", parentFolderId=None),
            Folder(id="folder-business-root", displayName="Business", parentFolderId=None),
            Folder(
                id="folder-business-child",
                displayName="Business",
                parentFolderId="folder-action",
            ),
        ]
        mock_email_client.get_folders.return_value = folders

        manager = FolderManager(mock_email_client)
        manager.initialize()

        folder = manager.ensure_subcategory_folder("Action", "Business")
        assert folder is not None
        assert folder.id == "folder-business-child"
        mock_email_client.create_folder.assert_not_called()


class TestFolderManagerDestination:
    """Tests for destination folder resolution."""

    def test_get_destination_folder_category_only(self, mock_email_client, sample_folders):
        """Test getting destination folder for category only."""
        mock_email_client.get_folders.return_value = sample_folders

        manager = FolderManager(mock_email_client)
        manager.initialize()

        categorization = CategorizationResult(
            id="email-1",
            subject="Test",
            category="Action",
            sub_category=None,
            analysis="Test",
        )

        folder = manager.get_destination_folder(categorization)
        assert folder is not None
        assert folder.display_name == "Action"

    def test_get_destination_folder_with_subcategory(self, mock_email_client, sample_folders):
        """Test getting destination folder with subcategory."""
        mock_email_client.get_folders.return_value = sample_folders

        manager = FolderManager(mock_email_client)
        manager.initialize()

        # Subcategory already exists
        categorization = CategorizationResult(
            id="email-1",
            subject="Test",
            category="Action",
            sub_category="Urgent",
            analysis="Test",
        )

        folder = manager.get_destination_folder(categorization)
        assert folder is not None
        assert folder.display_name == "Urgent"
