"""
Tests for the categorizer module.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.outlook_categorizer.categorizer import EmailCategorizer
from src.outlook_categorizer.config import Settings
from src.outlook_categorizer.models import Email, EmailBody, EmailRecipient, EmailAddress


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.groq_api_key = "test-api-key"
    settings.groq_model = "llama-3.1-70b-versatile"
    settings.boss_email = "boss@company.com"
    settings.company_domain = "company.com"
    settings.collaborator_email_list = ["colleague@company.com"]
    settings.categories_list = [
        "Action", "Response", "Junk", "Spam", "Receipt",
        "Boss", "Company", "Collaborators", "Community", "Business", "Other"
    ]
    return settings


@pytest.fixture
def sample_email():
    """Create a sample email for testing."""
    return Email(
        id="test-email-123",
        subject="Test Subject",
        body=EmailBody(content_type="text", content="Test body content"),
        sender=EmailRecipient(
            emailAddress=EmailAddress(name="Sender", address="sender@example.com")
        ),
        from_recipient=EmailRecipient(
            emailAddress=EmailAddress(name="Sender", address="sender@example.com")
        ),
        importance="normal",
    )


@pytest.fixture
def boss_email(mock_settings):
    """Create an email from the boss."""
    return Email(
        id="boss-email-123",
        subject="Important Meeting",
        body=EmailBody(content_type="text", content="Please attend the meeting"),
        sender=EmailRecipient(
            emailAddress=EmailAddress(name="Boss", address="boss@company.com")
        ),
        from_recipient=EmailRecipient(
            emailAddress=EmailAddress(name="Boss", address="boss@company.com")
        ),
        importance="high",
    )


@pytest.fixture
def company_email():
    """Create an email from company domain."""
    return Email(
        id="company-email-123",
        subject="Company Update",
        body=EmailBody(content_type="text", content="Company news"),
        sender=EmailRecipient(
            emailAddress=EmailAddress(name="HR", address="hr@company.com")
        ),
        from_recipient=EmailRecipient(
            emailAddress=EmailAddress(name="HR", address="hr@company.com")
        ),
        importance="normal",
    )


class TestEmailCategorizerHeuristics:
    """Tests for heuristic-based categorization."""

    def test_boss_email_detection(self, mock_settings, boss_email):
        """Test that emails from boss are categorized correctly."""
        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)
            result = categorizer._apply_heuristics(boss_email)

            assert result is not None
            assert result.category == "Boss"

    def test_company_email_detection(self, mock_settings, company_email):
        """Test that emails from company domain are categorized correctly."""
        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)
            result = categorizer._apply_heuristics(company_email)

            assert result is not None
            assert result.category == "Company"

    def test_collaborator_email_detection(self, mock_settings):
        """Test that emails from collaborators are categorized correctly."""
        email = Email(
            id="collab-email-123",
            subject="Project Update",
            body=EmailBody(content_type="text", content="Here's the update"),
            sender=EmailRecipient(
                emailAddress=EmailAddress(name="Colleague", address="colleague@company.com")
            ),
            from_recipient=EmailRecipient(
                emailAddress=EmailAddress(name="Colleague", address="colleague@company.com")
            ),
        )

        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)
            result = categorizer._apply_heuristics(email)

            assert result is not None
            assert result.category == "Collaborators"

    def test_receipt_detection(self, mock_settings):
        """Test that receipt emails are detected."""
        email = Email(
            id="receipt-email-123",
            subject="Order Confirmation #12345",
            body=EmailBody(content_type="text", content="Thank you for your purchase"),
            sender=EmailRecipient(
                emailAddress=EmailAddress(name="Store", address="noreply@store.com")
            ),
            from_recipient=EmailRecipient(
                emailAddress=EmailAddress(name="Store", address="noreply@store.com")
            ),
        )

        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)
            result = categorizer._apply_heuristics(email)

            assert result is not None
            assert result.category == "Receipt"

    def test_delhaize_domain_routes_to_business_delhaize(self, mock_settings):
        """Test that Delhaize domain emails route to Business/Delhaize."""

        email = Email(
            id="delhaize-email-123",
            subject="Delhaize Promo",
            body=EmailBody(content_type="text", content="Promo"),
            sender=EmailRecipient(
                emailAddress=EmailAddress(name="Delhaize", address="hello@em.delhaize.be")
            ),
            from_recipient=EmailRecipient(
                emailAddress=EmailAddress(name="Delhaize", address="hello@em.delhaize.be")
            ),
        )

        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)
            result = categorizer._apply_heuristics(email)

            assert result is not None
            assert result.category == "Business"
            assert result.sub_category == "Delhaize"

    def test_unknown_email_returns_none(self, mock_settings, sample_email):
        """Test that unknown emails return None for AI processing."""
        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)
            result = categorizer._apply_heuristics(sample_email)

            assert result is None


class TestEmailCategorizerPrompts:
    """Tests for prompt building."""

    def test_system_prompt_contains_categories(self, mock_settings):
        """Test that system prompt contains all categories."""
        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)
            prompt = categorizer._build_system_prompt()

            for category in mock_settings.categories_list:
                assert category in prompt

    def test_system_prompt_contains_boss_email(self, mock_settings):
        """Test that system prompt contains boss email."""
        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)
            prompt = categorizer._build_system_prompt()

            assert mock_settings.boss_email in prompt

    def test_build_user_prompt_includes_email_data(self, mock_settings):
        """Test that user prompt includes email data."""
        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)
            email = Email(
                id="test-123",
                subject="Test Subject",
                body=EmailBody(content_type="text", content="Test body"),
                sender=EmailRecipient(
                    emailAddress=EmailAddress(name="Sender", address="sender@test.com")
                ),
                from_recipient=EmailRecipient(
                    emailAddress=EmailAddress(name="Sender", address="sender@test.com")
                ),
                importance="normal",
            )

            prompt = categorizer._build_user_prompt(email, "Sanitized body")
            assert "Test Subject" in prompt
            assert "sender@test.com" in prompt


class TestEmailCategorizerSystemPromptLoading:
    """Tests for loading the external system prompt template."""

    def test_build_system_prompt_uses_external_template(self, mock_settings):
        """Test external system prompt template is loaded and formatted."""

        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)
            categorizer._load_system_prompt_template = MagicMock(
                return_value="Boss={boss_email} Domain={company_domain} Cats={categories}"
            )

            prompt = categorizer._build_system_prompt()
            assert mock_settings.boss_email in prompt
            assert mock_settings.company_domain in prompt
            assert "Cats=" in prompt

    def test_build_system_prompt_falls_back_when_template_missing(self, mock_settings):
        """Test prompt falls back to inline default when template can't be read."""

        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)
            categorizer._load_system_prompt_template = MagicMock(
                side_effect=FileNotFoundError("missing")
            )

            prompt = categorizer._build_system_prompt()
            assert "Output in valid JSON format only" in prompt
            assert "You may only use these categories" in prompt


class TestEmailCategorizerResponseParsing:
    """Tests for response parsing."""

    def test_parse_valid_json(self, mock_settings):
        """Test parsing valid JSON response."""
        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)

            response = '{"ID": "123", "subject": "Test", "category": "Business", "analysis": "Business email"}'
            result = categorizer._parse_response(response, "123")

            assert result is not None
            assert result.category == "Business"
            assert result.id == "123"

    def test_parse_json_with_extra_text(self, mock_settings):
        """Test parsing JSON with surrounding text."""
        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)

            response = 'Here is the result: {"ID": "123", "subject": "Test", "category": "Junk", "analysis": "Promotional"} Done.'
            result = categorizer._parse_response(response, "123")

            assert result is not None
            assert result.category == "Junk"

    def test_parse_invalid_category_defaults_to_other(self, mock_settings):
        """Test that invalid category defaults to Other."""
        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)

            response = '{"ID": "123", "subject": "Test", "category": "InvalidCategory", "analysis": "Test"}'
            result = categorizer._parse_response(response, "123")

            assert result is not None
            assert result.category == "Other"

    def test_parse_no_json_returns_none(self, mock_settings):
        """Test that response without JSON returns None."""
        with patch("src.outlook_categorizer.categorizer.Groq"):
            categorizer = EmailCategorizer(mock_settings)

            response = "I cannot categorize this email."
            result = categorizer._parse_response(response, "123")

            assert result is None
