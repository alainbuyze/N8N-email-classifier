"""Email body sanitization and sender heuristics.

Objective:
    Convert raw email content returned by Microsoft Graph (often HTML) into a
    compact, safe plain-text representation suitable for LLM prompting.

Responsibilities:
    - Strip potentially dangerous HTML elements (e.g., ``<script>``).
    - Convert HTML to markdown-ish text to preserve some structure.
    - Normalize and compress whitespace.
    - Provide small utilities for email address inspection used by heuristics
      (domain extraction, noreply detection).

High-level call tree:
    - :func:`sanitize_email_body`
        - :func:`html_to_markdown` (HTML input)
        - :func:`clean_text`
    - :func:`extract_sender_domain` (heuristics support)
    - :func:`is_noreply_address` (heuristics support)

Security notes:
    Sanitization is defensive: it is intended to prevent prompt injection via
    raw HTML/script content, and to reduce noise/tokens sent to the LLM.
"""

import re
from typing import Optional

from bs4 import BeautifulSoup
from markdownify import markdownify as md


def html_to_markdown(html_content: str) -> str:
    """Convert HTML to markdown-like plain text.

    This function performs a defensive HTML cleanup using BeautifulSoup before
    calling ``markdownify``.

    The primary goal is to preserve readable content while removing:
    - scripts
    - styles
    - document metadata (head/meta/link)

    Args:
        html_content: Raw HTML string.

    Returns:
        str: Markdown formatted text.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "html.parser")
    for element in soup(["script", "style", "head", "meta", "link"]):
        element.decompose()

    return md(str(soup), heading_style="ATX")


def clean_text(text: str) -> str:
    """Normalize and compact plain text.

    This function is intentionally aggressive to reduce token count and noise
    before sending content to the LLM.

    Removes:
    - HTML tags
    - Markdown links and images
    - Table separators
    - Horizontal rules
    - Multiple newlines and spaces
    - Special characters (except essential punctuation)

    Args:
        text: Raw text to clean.

    Returns:
        str: Cleaned text.
    """
    if not text:
        return ""

    # Remove any remaining HTML tags
    text = re.sub(r"<[^>]*>", "", text)

    # Remove Markdown links like [text](link)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)

    # Remove Markdown images like ![alt](image-link)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)

    # Remove table separators "|"
    text = re.sub(r"\|", " ", text)

    # Remove horizontal rules "---" or more
    text = re.sub(r"-{3,}", "", text)

    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)

    # Remove email-style quoted text (lines starting with >)
    text = re.sub(r"^>.*$", "", text, flags=re.MULTILINE)

    # Remove multiple newlines, replace with single space
    text = re.sub(r"\n+", " ", text)

    # Remove special characters except essential ones
    text = re.sub(r"[^\w\s.,!?@:;'\"-]", "", text)

    # Replace multiple spaces with single space
    text = re.sub(r"\s{2,}", " ", text)

    # Trim whitespace
    text = text.strip()

    return text


def extract_text_from_html(html_content: str) -> str:
    """Extract plain text from HTML.

    This is a lower-level helper than :func:`sanitize_email_body`. It removes
    non-content elements and returns the visible text.

    Args:
        html_content: Raw HTML string.

    Returns:
        str: Extracted plain text.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style", "head", "meta", "link"]):
        element.decompose()

    # Get text
    text = soup.get_text(separator=" ")

    return text


def sanitize_email_body(
    body_content: str, content_type: str = "html"
) -> str:
    """Sanitize an email body for AI processing.

    This is the main entrypoint used by the categorizer.

    Behavior:
        - For HTML:
            - Convert to markdown-like text via :func:`html_to_markdown`.
            - Normalize via :func:`clean_text`.
        - For plain text:
            - Normalize via :func:`clean_text`.
        - Truncate to a maximum length to reduce prompt token usage.

    Converts HTML to text, cleans up formatting, and normalizes content.

    Args:
        body_content: Raw email body content.
        content_type: Content type ("html" or "text").

    Returns:
        str: Sanitized text ready for AI processing.
    """
    if not body_content:
        return ""

    if content_type.lower() == "html":
        # First convert HTML to markdown for better structure
        markdown_text = html_to_markdown(body_content)
        # Then clean the text
        cleaned = clean_text(markdown_text)
    else:
        # For plain text, just clean it
        cleaned = clean_text(body_content)

    # Truncate if too long (to avoid token limits)
    max_length = 4000
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length] + "..."

    return cleaned


def extract_sender_domain(email_address: str) -> Optional[str]:
    """Extract the domain part from an email address.

    This is used by domain-based heuristics (e.g. deterministic routing for
    known sender domains).

    Args:
        email_address: Email address string.

    Returns:
        Optional[str]: Domain part of email, or None if invalid.
    """
    if not email_address or "@" not in email_address:
        return None

    parts = email_address.lower().split("@")
    if len(parts) == 2:
        return parts[1]
    return None


def is_noreply_address(email_address: str) -> bool:
    """Check whether an email address looks like a no-reply sender.

    The heuristic is substring-based and intentionally broad.

    Args:
        email_address: Email address to check.

    Returns:
        bool: True if it's a no-reply address.
    """
    if not email_address:
        return False

    noreply_patterns = [
        "noreply",
        "no-reply",
        "donotreply",
        "do-not-reply",
        "mailer-daemon",
        "postmaster",
    ]

    email_lower = email_address.lower()
    return any(pattern in email_lower for pattern in noreply_patterns)
