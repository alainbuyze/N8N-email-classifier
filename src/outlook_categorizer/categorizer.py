"""AI-assisted email categorization.

Objective:
    Convert an :class:`src.outlook_categorizer.models.Email` into a structured
    :class:`src.outlook_categorizer.models.CategorizationResult` representing a
    primary category (and optional subcategory).

Core strategy:
    1. Sanitize the email body to reduce prompt noise and remove unsafe HTML.
    2. Apply deterministic heuristics for cases where we want strict behavior
       (e.g., domain routing like Delhaize).
    3. If no heuristic matches, call the Groq LLM and parse its JSON response.

Responsibilities:
    - Build a system prompt from a template file on disk.
    - Build a user prompt embedding key email fields.
    - Call Groq chat completions and parse the response.
    - Enforce known categories and provide safe fallbacks.

High-level call tree:
    - :class:`EmailCategorizer`
        - :meth:`EmailCategorizer.categorize`
            - :func:`src.outlook_categorizer.sanitizer.sanitize_email_body`
            - :meth:`EmailCategorizer._apply_heuristics`
            - :meth:`EmailCategorizer._build_system_prompt`
                - :meth:`EmailCategorizer._load_system_prompt_template`
            - :meth:`EmailCategorizer._build_user_prompt`
            - Groq chat completion
            - :meth:`EmailCategorizer._parse_response`
        - :meth:`EmailCategorizer.categorize_batch`

Operational notes:
    - The system prompt lives in ``src/outlook_categorizer/prompts/system_prompt.txt``.
    - Heuristics should be kept simple and deterministic. When adding new ones,
      ensure they run *before* LLM calls.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from groq import Groq

from .config import Settings, EmailCategory
from .models import Email, CategorizationResult
from .sanitizer import sanitize_email_body, is_noreply_address, extract_sender_domain

logger = logging.getLogger(__name__)


class EmailCategorizer:
    """
    AI-powered email categorizer using Groq LLM.

    This class is instantiated once per orchestrator run. It is safe to reuse
    for multiple emails because the Groq client is stateless.

    Attributes:
        settings: Application settings.
        client: Groq API client.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize categorizer with settings.

        Args:
            settings: Application settings with Groq API key.
        """
        self.settings = settings
        self.client = Groq(api_key=settings.groq_api_key)

    def _load_system_prompt_template(self) -> str:
        """Load the system prompt template from disk.

        The template contains placeholders for:
        - boss email
        - company domain
        - allowed categories

        Returns:
            str: Prompt template text.
        """

        prompt_path = Path(__file__).resolve().parent / "prompts" / "system_prompt.txt"
        return prompt_path.read_text(encoding="utf-8")

    def _build_system_prompt(self) -> str:
        """
        Build system prompt for email categorization.

        This formats the template with runtime settings and provides a fallback
        inline prompt if the file cannot be loaded.

        Returns:
            str: System prompt with categorization rules.
        """
        categories = ", ".join(self.settings.categories_list)

        try:
            template = self._load_system_prompt_template()
            return template.format(
                boss_email=self.settings.boss_email,
                company_domain=self.settings.company_domain,
                categories=categories,
            )
        except Exception as e:
            logger.warning(f"Failed to load system prompt file: {e}")
            return f"""You're an AI assistant for a business manager, categorizing emails. Email info is in <email> tags.

Categorization priority:

Action: Needs response or action from a personal email address
Response: An email that is a response to a personal email from the user
Junk: Ads, sales, newsletters, promotions, daily digests. Often the reply email address is noreply@...
Spam: Phishing, scams, discounts, suspicious emails. Including emails from Zendesk, often urging action, impersonal address
Receipt: Any purchase confirmation
Boss: A message from the boss ({self.settings.boss_email}), addressed personally
Company: A message from the company domain (@{self.settings.company_domain})
Collaborators: A message from team members
Community: Updates, events, forums, everything related to "community"
Business: Any communication related to business, usually from a non-personal email address
Other: Doesn't fit into any other category

Key points:

- Analyze the subject, body, email addresses and other data
- Look for specific keywords and phrases for each category
- Email can have 2 categories: primary and sub (e.g., "Action" and "Boss")
- Emails from business development executives are often junk
- Emojis in subject often indicate junk/spam

Output in valid JSON format only:
{{
  "ID": "email_id",
  "subject": "SUBJECT_LINE",
  "category": "PRIMARY_CATEGORY",
  "subCategory": "SUBCATEGORY",
  "analysis": "Brief 1-2 sentence explanation"
}}

No additional text or tokens outside the JSON.
You may only use these categories: {categories}"""

    def _build_user_prompt(self, email: Email, sanitized_body: str) -> str:
        """
        Build user prompt with email data.

        The prompt wraps JSON inside <email> tags to make it easy for the model
        to locate the input payload.

        Args:
            email: Email object to categorize.
            sanitized_body: Cleaned email body text.

        Returns:
            str: User prompt with email data.
        """
        email_data = {
            "id": email.id,
            "subject": email.subject,
            "sender": email.sender_email,
            "from": email.from_email,
            "importance": email.importance,
            "body": sanitized_body[:2000],  # Limit body size
        }

        return f"""Categorize the following email:
<email>
{json.dumps(email_data, indent=2)}
</email>

Ensure your final output is valid JSON with no additional text.
Available categories: {", ".join(self.settings.categories_list)}"""

    def _parse_response(
        self, response_text: str, email_id: str
    ) -> Optional[CategorizationResult]:
        """
        Parse LLM response into CategorizationResult.

        Parsing strategy:
            - Extract the first JSON object found in the response.
            - Validate that the category is one of the allowed values.
            - Use :meth:`CategorizationResult.model_validate` for final parsing.

        Failures return ``None`` so the caller can decide fallback behavior.

        Args:
            response_text: Raw LLM response.
            email_id: Original email ID for fallback.

        Returns:
            Optional[CategorizationResult]: Parsed result or None if failed.
        """
        # Try to extract JSON from response
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not json_match:
            logger.error(f"No JSON found in response: {response_text[:200]}")
            return None

        try:
            data = json.loads(json_match.group())

            # Ensure ID is set
            if "ID" not in data and "id" not in data:
                data["ID"] = email_id

            # Validate category
            category = data.get("category", "Other")
            valid_categories = [c.value for c in EmailCategory]
            if category not in valid_categories:
                logger.warning(f"Invalid category '{category}', defaulting to 'Other'")
                data["category"] = "Other"

            return CategorizationResult.model_validate(data)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create CategorizationResult: {e}")
            return None

    def categorize(self, email: Email) -> Optional[CategorizationResult]:
        """
        Categorize a single email using AI.

        This is the primary entrypoint used by the orchestrator.

        Notes:
            The method performs an early return when heuristics match.

        Args:
            email: Email to categorize.

        Returns:
            Optional[CategorizationResult]: Categorization result or None if failed.
        """
        # Sanitize email body
        content_type = email.body.content_type if email.body else "text"
        body_content = email.body.content if email.body else ""
        sanitized_body = sanitize_email_body(body_content, content_type)

        # Apply quick heuristics for obvious cases
        quick_result = self._apply_heuristics(email)
        if quick_result:
            logger.info(f"Quick categorization for '{email.subject}': {quick_result.category}")
            return quick_result

        # Build prompts
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(email, sanitized_body)

        try:
            # Call Groq API
            response = self.client.chat.completions.create(
                model=self.settings.groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=500,
            )

            response_text = response.choices[0].message.content
            logger.debug(f"LLM response: {response_text}")

            result = self._parse_response(response_text, email.id)
            if result:
                logger.info(
                    f"Categorized '{email.subject}' as {result.category}"
                    f"{f'/{result.sub_category}' if result.sub_category else ''}"
                )
            return result

        except Exception as e:
            logger.error(f"Failed to categorize email: {e}")
            return None

    def _apply_heuristics(self, email: Email) -> Optional[CategorizationResult]:
        """
        Apply quick heuristics for obvious categorizations.

        Heuristic precedence is important. Rules here run before the LLM.
        Add new deterministic rules above more general ones.

        Current heuristics:
            - Domain routing: Delhaize (em.delhaize.be) -> Business/Delhaize
            - Boss email -> Boss
            - Collaborators -> Collaborators
            - Company domain -> Company
            - Noreply receipt keywords -> Receipt

        Args:
            email: Email to check.

        Returns:
            Optional[CategorizationResult]: Quick result or None to use AI.
        """
        sender = email.sender_email
        from_addr = email.from_email
        subject_lower = email.subject.lower()

        sender_domain = extract_sender_domain(sender)

        # Domain-based business routing
        if sender_domain == "em.delhaize.be":
            return CategorizationResult(
                id=email.id,
                subject=email.subject,
                category="Business",
                sub_category="Delhaize",
                analysis="Email from Delhaize marketing domain",
            )

        # Check for boss
        if self.settings.boss_email:
            boss_email_lower = self.settings.boss_email.lower()
            if sender == boss_email_lower or from_addr == boss_email_lower:
                return CategorizationResult(
                    id=email.id,
                    subject=email.subject,
                    category="Boss",
                    analysis="Email from boss",
                )

        # Check for collaborators
        if sender in self.settings.collaborator_email_list:
            return CategorizationResult(
                id=email.id,
                subject=email.subject,
                category="Collaborators",
                analysis="Email from team collaborator",
            )

        # Check for company domain
        if self.settings.company_domain:
            domain = self.settings.company_domain.lower()
            if sender_domain and domain in sender_domain:
                return CategorizationResult(
                    id=email.id,
                    subject=email.subject,
                    category="Company",
                    analysis=f"Email from company domain ({domain})",
                )

        # Check for obvious spam/junk indicators
        if is_noreply_address(sender) or is_noreply_address(from_addr):
            # Check for receipt keywords
            receipt_keywords = ["receipt", "order confirmation", "purchase", "invoice"]
            if any(kw in subject_lower for kw in receipt_keywords):
                return CategorizationResult(
                    id=email.id,
                    subject=email.subject,
                    category="Receipt",
                    analysis="Purchase/order confirmation from noreply address",
                )

        return None

    def categorize_batch(self, emails: list[Email]) -> list[CategorizationResult]:
        """
        Categorize multiple emails.

        This is a convenience helper that calls :meth:`categorize` for each
        email and emits an ``Other`` fallback result when categorization fails.

        Args:
            emails: List of emails to categorize.

        Returns:
            list[CategorizationResult]: List of categorization results.
        """
        results = []
        for email in emails:
            result = self.categorize(email)
            if result:
                results.append(result)
            else:
                # Create fallback result
                results.append(
                    CategorizationResult(
                        id=email.id,
                        subject=email.subject,
                        category="Other",
                        analysis="Failed to categorize, defaulting to Other",
                    )
                )
        return results
