"""Tests for email category tagging functionality."""

import pytest
from unittest.mock import Mock, patch
from src.outlook_categorizer.email_client import EmailClient
from src.outlook_categorizer.config import Settings


@pytest.fixture
def email_client():
    """Create email client with mocked auth."""
    settings = Settings(
        azure_client_id="test-client-id",
        azure_tenant_id="test-tenant-id",
        groq_api_key="test-groq-key",
    )
    with patch("src.outlook_categorizer.email_client.GraphAuthenticator"):
        client = EmailClient(settings)
        client._make_request = Mock()
        return client


def test_add_category_success(email_client):
    """Test successfully adding a category to an email."""
    email_client._make_request.return_value = {"categories": ["Categorized"]}
    
    result = email_client.add_category("test-email-id", "Categorized")
    
    assert result is True
    email_client._make_request.assert_called_once_with(
        "PATCH",
        "/me/messages/test-email-id",
        json_data={"categories": ["Categorized"]},
    )


def test_add_category_failure(email_client):
    """Test handling failure when adding category."""
    import requests
    error = requests.HTTPError()
    error.response = Mock(status_code=500)
    email_client._make_request.side_effect = error
    
    result = email_client.add_category("test-email-id", "Categorized")
    
    assert result is False


def test_move_email_with_category(email_client):
    """Test moving email and adding category tag."""
    email_client._make_request.return_value = {}
    email_client.add_category = Mock(return_value=True)
    
    result = email_client.move_email(
        "test-email-id",
        "destination-folder-id",
        category="Categorized",
    )
    
    assert result is True
    # Verify move was called
    assert email_client._make_request.call_count == 1
    # Verify category was added
    email_client.add_category.assert_called_once_with("test-email-id", "Categorized")


def test_move_email_without_category(email_client):
    """Test moving email without adding category tag."""
    email_client._make_request.return_value = {}
    email_client.add_category = Mock(return_value=True)
    
    result = email_client.move_email(
        "test-email-id",
        "destination-folder-id",
    )
    
    assert result is True
    # Verify move was called
    assert email_client._make_request.call_count == 1
    # Verify category was NOT added
    email_client.add_category.assert_not_called()


def test_move_email_fallback_with_category(email_client):
    """Test fallback move also adds category tag."""
    import requests
    
    # First call (primary move) fails with 404
    error = requests.HTTPError()
    error.response = Mock(status_code=404)
    
    # Second call (fallback move) succeeds
    email_client._make_request.side_effect = [error, {}]
    email_client.add_category = Mock(return_value=True)
    
    result = email_client.move_email(
        "test-email-id",
        "destination-folder-id",
        source_folder_id="source-folder-id",
        category="Categorized",
    )
    
    assert result is True
    # Verify both move attempts were made
    assert email_client._make_request.call_count == 2
    # Verify category was added after fallback move
    email_client.add_category.assert_called_once_with("test-email-id", "Categorized")
