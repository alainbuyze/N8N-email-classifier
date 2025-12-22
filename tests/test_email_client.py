from unittest.mock import MagicMock

import requests

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


def test_get_emails_url_encodes_folder_id() -> None:
    """Ensure get_emails URL-encodes folder IDs containing special characters."""

    settings = MagicMock()
    auth = MagicMock()
    client = EmailClient(settings, auth)

    client._make_request = MagicMock(return_value={"value": []})

    client.get_emails(folder_id="a/b+c=", limit=5)

    client._make_request.assert_called_once()
    args, kwargs = client._make_request.call_args
    assert args[0] == "GET"
    assert args[1] == "/me/mailFolders/a%2Fb%2Bc%3D/messages"


def test_move_email_url_encodes_message_id() -> None:
    """Ensure move_email URL-encodes message IDs before calling Graph."""

    settings = MagicMock()
    auth = MagicMock()
    client = EmailClient(settings, auth)

    client._make_request = MagicMock(return_value={})

    assert client.move_email(email_id="AQM+/=", folder_id="dest") is True

    client._make_request.assert_called_once()
    args, kwargs = client._make_request.call_args
    assert args[0] == "POST"
    assert args[1] == "/me/messages/AQM%2B%2F%3D/move"
    assert kwargs["json_data"] == {"destinationId": "dest"}


def test_move_email_falls_back_to_folder_scoped_endpoint_on_404() -> None:
    """When /me/messages/{id}/move returns 404, retry via folder-scoped message URL."""

    settings = MagicMock()
    auth = MagicMock()
    client = EmailClient(settings, auth)

    not_found_response = MagicMock(status_code=404)
    not_found_error = requests.HTTPError(response=not_found_response)

    client._make_request = MagicMock(side_effect=[not_found_error, {}])

    moved = client.move_email(email_id="AQM+/=", folder_id="dest", source_folder_id="src")
    assert moved is True

    assert client._make_request.call_count == 2
    first_call = client._make_request.call_args_list[0]
    assert first_call.args[0] == "POST"
    assert first_call.args[1] == "/me/messages/AQM%2B%2F%3D/move"

    second_call = client._make_request.call_args_list[1]
    assert second_call.args[0] == "POST"
    assert second_call.args[1] == "/me/mailFolders/src/messages/AQM%2B%2F%3D/move"
