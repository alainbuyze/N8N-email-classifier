from unittest.mock import MagicMock

import pytest

from src.outlook_categorizer.auth import GraphAuthenticator


def test_select_account_defaults_to_first_when_no_preferred_username() -> None:
    """Return the first cached account when no preference is configured."""

    settings = MagicMock()
    settings.outlook_account_username = None

    auth = GraphAuthenticator(settings)

    accounts = [
        {"username": "first@example.com"},
        {"username": "second@example.com"},
    ]

    selected = auth._select_account(accounts)
    assert selected == accounts[0]


def test_select_account_matches_preferred_username_case_insensitive() -> None:
    """Select the cached account matching the preferred username."""

    settings = MagicMock()
    settings.outlook_account_username = "Second@Example.com"

    auth = GraphAuthenticator(settings)

    accounts = [
        {"username": "first@example.com"},
        {"username": "second@example.com"},
    ]

    selected = auth._select_account(accounts)
    assert selected == accounts[1]


def test_select_account_raises_when_preferred_username_missing() -> None:
    """Raise a clear error when the preferred username is not in cache."""

    settings = MagicMock()
    settings.outlook_account_username = "missing@example.com"

    auth = GraphAuthenticator(settings)

    accounts = [
        {"username": "first@example.com"},
        {"username": "second@example.com"},
    ]

    with pytest.raises(ValueError, match="OUTLOOK_ACCOUNT_USERNAME"):
        auth._select_account(accounts)
