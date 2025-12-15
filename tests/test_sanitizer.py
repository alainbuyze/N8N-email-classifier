"""
Tests for the sanitizer module.
"""

from src.outlook_categorizer.sanitizer import (
    clean_text,
    extract_sender_domain,
    extract_text_from_html,
    html_to_markdown,
    is_noreply_address,
    sanitize_email_body,
)


class TestHtmlToMarkdown:
    """Tests for html_to_markdown function."""

    def test_empty_string(self):
        """Test with empty input."""
        assert html_to_markdown("") == ""

    def test_simple_html(self):
        """Test with simple HTML content."""
        html = "<p>Hello <strong>World</strong></p>"
        result = html_to_markdown(html)
        assert "Hello" in result
        assert "World" in result

    def test_removes_script_tags(self):
        """Test that script tags are removed."""
        html = "<p>Content</p><script>alert('xss')</script>"
        result = html_to_markdown(html)
        assert "alert" not in result
        assert "Content" in result


class TestCleanText:
    """Tests for clean_text function."""

    def test_empty_string(self):
        """Test with empty input."""
        assert clean_text("") == ""

    def test_removes_html_tags(self):
        """Test HTML tag removal."""
        text = "<div>Hello</div><span>World</span>"
        result = clean_text(text)
        assert "<div>" not in result
        assert "Hello" in result

    def test_removes_markdown_links(self):
        """Test Markdown link removal."""
        text = "Click [here](https://example.com) for more"
        result = clean_text(text)
        assert "[here]" not in result
        assert "https://example.com" not in result
        assert "here" in result

    def test_removes_urls(self):
        """Test URL removal."""
        text = "Visit https://example.com for info"
        result = clean_text(text)
        assert "https://example.com" not in result
        assert "Visit" in result

    def test_normalizes_whitespace(self):
        """Test whitespace normalization."""
        text = "Hello    World\n\n\nTest"
        result = clean_text(text)
        assert "  " not in result
        assert "\n" not in result

    def test_removes_horizontal_rules(self):
        """Test horizontal rule removal."""
        text = "Before---After"
        result = clean_text(text)
        assert "---" not in result


class TestExtractTextFromHtml:
    """Tests for extract_text_from_html function."""

    def test_empty_string(self):
        """Test with empty input."""
        assert extract_text_from_html("") == ""

    def test_extracts_text(self):
        """Test text extraction from HTML."""
        html = "<html><body><p>Hello World</p></body></html>"
        result = extract_text_from_html(html)
        assert "Hello World" in result

    def test_removes_scripts(self):
        """Test script removal."""
        html = "<p>Content</p><script>malicious()</script>"
        result = extract_text_from_html(html)
        assert "malicious" not in result


class TestSanitizeEmailBody:
    """Tests for sanitize_email_body function."""

    def test_empty_string(self):
        """Test with empty input."""
        assert sanitize_email_body("") == ""

    def test_html_content(self):
        """Test HTML content sanitization."""
        html = "<html><body><p>Test email content</p></body></html>"
        result = sanitize_email_body(html, "html")
        assert "Test email content" in result

    def test_text_content(self):
        """Test plain text sanitization."""
        text = "Plain text email   with   extra spaces"
        result = sanitize_email_body(text, "text")
        assert "  " not in result

    def test_truncates_long_content(self):
        """Test that long content is truncated."""
        long_text = "A" * 5000
        result = sanitize_email_body(long_text, "text")
        assert len(result) <= 4003  # 4000 + "..."


class TestExtractSenderDomain:
    """Tests for extract_sender_domain function."""

    def test_valid_email(self):
        """Test with valid email address."""
        assert extract_sender_domain("user@example.com") == "example.com"

    def test_empty_string(self):
        """Test with empty input."""
        assert extract_sender_domain("") is None

    def test_invalid_email(self):
        """Test with invalid email (no @)."""
        assert extract_sender_domain("invalid-email") is None

    def test_case_insensitive(self):
        """Test case insensitivity."""
        assert extract_sender_domain("User@EXAMPLE.COM") == "example.com"


class TestIsNoreplyAddress:
    """Tests for is_noreply_address function."""

    def test_noreply_variations(self):
        """Test various noreply patterns."""
        assert is_noreply_address("noreply@example.com") is True
        assert is_noreply_address("no-reply@example.com") is True
        assert is_noreply_address("donotreply@example.com") is True
        assert is_noreply_address("do-not-reply@example.com") is True

    def test_normal_address(self):
        """Test normal email address."""
        assert is_noreply_address("john@example.com") is False
        assert is_noreply_address("support@example.com") is False

    def test_empty_string(self):
        """Test with empty input."""
        assert is_noreply_address("") is False

    def test_case_insensitive(self):
        """Test case insensitivity."""
        assert is_noreply_address("NoReply@example.com") is True
        assert is_noreply_address("NOREPLY@EXAMPLE.COM") is True
