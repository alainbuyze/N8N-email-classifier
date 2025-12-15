from unittest.mock import MagicMock

from src.outlook_categorizer.email_client import EmailClient


def test_get_emails_defaults_to_inbox_endpoint() -> None:
    """Ensure get_emails fetches only Inbox when folder_id is None."""

    settings = MagicMock()
    auth = MagicMock()
    client = EmailClient(settings, auth)

    client._make_request = MagicMock(return_value={"value": []})

    client.get_emails(folder_id=None, limit=5)

    client._make_request.assert_called_once()
    args, kwargs = client._make_request.call_args
    assert args[0] == "GET"
    assert args[1] == "/me/mailFolders/inbox/messages"


def test_get_emails_uses_specific_folder_endpoint() -> None:
    """Ensure get_emails uses mailFolders/{id}/messages when folder_id is provided."""

    settings = MagicMock()
    auth = MagicMock()
    client = EmailClient(settings, auth)

    client._make_request = MagicMock(return_value={"value": []})

    client.get_emails(folder_id="folder-123", limit=5)

    client._make_request.assert_called_once()
    args, kwargs = client._make_request.call_args
    assert args[0] == "GET"
    assert args[1] == "/me/mailFolders/folder-123/messages"
