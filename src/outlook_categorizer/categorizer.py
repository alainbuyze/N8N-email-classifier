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
from pathlib import Path
from typing import Optional

import re

from groq import Groq

from .config import Settings
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

        prompt_path = (
            Path(__file__).resolve().parent
            / "prompts"
            / "Email Categorization prompt.md"
        )
        return prompt_path.read_text(encoding="utf-8")

    def _render_system_prompt_template(self, template: str) -> str:
        """Render the system prompt template using safe placeholder substitution.

        This project intentionally stores prompts as Markdown that can include
        JSON examples and other brace-heavy content.

        Python's ``str.format`` is unsafe here because it treats *any* ``{...}``
        as a format field (including JSON objects like ``{"ID": ...}``).

        Args:
            template: Raw template text.

        Returns:
            str: Rendered template with known placeholders replaced.
        """

        replacements = {
            "{boss_email}": self.settings.boss_email,
            "{company_domain}": self.settings.company_domain,
            "{management_emails}": (self.settings.management_emails or ""),
            "{direct_reports_emails}": (self.settings.direct_reports_emails or ""),
            "{categories}": ", ".join(self.settings.categories_list),
        }

        rendered = template
        for key, value in replacements.items():
            rendered = rendered.replace(key, value)

        return rendered

    def _build_system_prompt(self) -> str:
        """
        Build system prompt for email categorization.

        This formats the template with runtime settings and provides a fallback
        inline prompt if the file cannot be loaded.

        Returns:
            str: System prompt with categorization rules.
        """
        try:
            template = self._load_system_prompt_template()
            rendered = self._render_system_prompt_template(template)
            # Reason: Extremely large system prompts can increase the odds of
            # incomplete/truncated model output.
            return rendered[:12000]
        except Exception as e:
            logger.warning(f"Failed to load system prompt file: {e}")
            return """You're an AI assistant for a business manager, categorizing emails. Email info is in <email> tags.
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
                "analysis": "Brief 1-2 sentence explanation",
                "senderGoal": "Very short (3-8 words) description of why the sender sent this email"
                }}

                No additional text or tokens outside the JSON.
                """

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
            "body": sanitized_body[:1200],  # Limit body size
        }

        return f"""Categorize the following email:
<email>
{json.dumps(email_data, indent=2)}
</email>

Ensure your final output is valid JSON with no additional text.
Also include senderGoal: a very short description (3-8 words) of the sender's intent.
Return a single JSON object only (no Markdown fences).
"""

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
        extracted = self._extract_first_json_object(response_text)
        if extracted is None:
            snippet = (response_text or "")[:300].replace("\n", "\\n")
            logger.warning(
                "LLM response had no parseable JSON (email_id=%s, response_text=%s)",
                email_id,
                response_text,
            )
            return None

        try:
            data = json.loads(extracted)

            # Ensure ID is set
            if "ID" not in data and "id" not in data:
                data["ID"] = email_id

            if "senderGoal" not in data and "sender_goal" not in data:
                data["senderGoal"] = ""

            '''# Validate category
            category = data.get("category", "Other")
            valid_categories = [c.value for c in EmailCategory]
            if category not in valid_categories:
                logger.warning(f"Invalid category '{category}', defaulting to 'Other'")
                data["category"] = "Other"
                '''

            return CategorizationResult.model_validate(data)

        except json.JSONDecodeError as e:
            snippet = (response_text or "")[:300].replace("\n", "\\n")
            logger.warning(
                "Failed to parse JSON from LLM response (email_id=%s, error=%s, snippet=%s)",
                email_id,
                str(e),
                snippet,
            )
            return None
        except Exception as e:
            logger.error(f"Failed to create CategorizationResult: {e}")
            return None

    def _extract_first_json_object(self, response_text: str) -> Optional[str]:
        """Extract the first valid JSON object from a model response.

        The Groq model is instructed to return raw JSON, but in practice it can
        include surrounding text, Markdown fences, or multiple JSON blobs.

        This function uses Python's JSONDecoder to locate the first decodable
        JSON object starting from the first '{' and then scanning forward.

        Args:
            response_text: Raw model response text.

        Returns:
            Optional[str]: JSON object string if found, else None.
        """
        if not response_text:
            return None

        cleaned = self._strip_code_fences(response_text)

        decoder = json.JSONDecoder()
        start = cleaned.find("{")
        while start != -1:
            try:
                _, end = decoder.raw_decode(cleaned[start:])
                return cleaned[start : start + end]
            except json.JSONDecodeError:
                start = cleaned.find("{", start + 1)

        # Some models return an object but truncate it mid-field. Try a
        # best-effort recovery to salvage at least category/subCategory.
        recovered = self._recover_truncated_json(cleaned)
        if recovered is not None:
            return recovered

        return None

    def _strip_code_fences(self, text: str) -> str:
        """Remove Markdown code fences from a model response.

        Args:
            text: Raw model response.

        Returns:
            str: Response with code fences removed.
        """

        # Remove ```json ... ``` and generic ``` ... ``` wrappers.
        return re.sub(r"```(?:json)?\s*|```", "", text, flags=re.IGNORECASE)

    def _recover_truncated_json(self, text: str) -> Optional[str]:
        """Best-effort recovery for truncated JSON objects.

        This handles cases where the response begins with '{' and contains
        valid JSON fields, but is cut off mid-key or mid-string.

        Strategy:
            - Start from the first '{'.
            - Iteratively trim trailing partial content back to a stable
              boundary (newline/comma), then
            - Auto-close missing braces and attempt json.loads.

        Args:
            text: Cleaned model response.

        Returns:
            Optional[str]: A JSON string that can be parsed, or None.
        """

        start = text.find("{")
        if start == -1:
            return None

        candidate = text[start:]

        # Avoid pathological loops.
        for _ in range(200):
            snippet = candidate.strip()
            if len(snippet) < 2:
                return None

            open_braces = snippet.count("{")
            close_braces = snippet.count("}")
            missing = max(0, open_braces - close_braces)

            attempt = snippet + ("}" * missing)
            attempt = re.sub(r",\s*}\s*$", "}\n", attempt)

            try:
                json.loads(attempt)
                return attempt
            except json.JSONDecodeError:
                pass

            # Trim to a likely safe boundary.
            last_nl = candidate.rfind("\n")
            last_comma = candidate.rfind(",")
            cut = max(last_nl, last_comma)
            if cut <= 0:
                candidate = candidate[:-1]
            else:
                candidate = candidate[:cut]

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

        '''# Apply quick heuristics for obvious cases
        quick_result = self._apply_heuristics(email)
        if quick_result:
            logger.info(f"Quick categorization for '{email.subject}': {quick_result.category}")
            return quick_result'''

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
                temperature=0,
                max_tokens=900,
            )

            response_text = (response.choices[0].message.content or "").strip()
            logger.debug(f"LLM response: {response_text}")

            result = self._parse_response(response_text, email.id)
            if result:
                logger.info(
                    f"Categorized '{email.subject}' as {result.category}"
                    f"{f'/{result.sub_category}' if result.sub_category else ''}"
                )
                return result

            logger.warning(
                "LLM categorization unusable; falling back to Other (email_id=%s)",
                email.id,
            )
            return CategorizationResult(
                id=email.id,
                subject=email.subject,
                category="Other",
                analysis="LLM response could not be parsed",
                sender_goal="",
            )

        except Exception as e:
            logger.warning(
                "LLM categorization failed; falling back to Other (email_id=%s, error=%s)",
                email.id,
                str(e),
            )
            return CategorizationResult(
                id=email.id,
                subject=email.subject,
                category="Other",
                analysis="LLM call failed",
                sender_goal="",
            )

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

        # Microsoft account security / sign-in alerts (common and time-sensitive).
        # Reason: These emails are high-signal, frequently formatted in a way that can
        # confuse the LLM output, and should reliably route to Action.
        if sender_domain and sender_domain.endswith("accountprotection.microsoft.com"):
            return CategorizationResult(
                id=email.id,
                subject=email.subject,
                category="Action",
                analysis="Microsoft account security alert",
                sender_goal="Verify new account sign-in",
            )

        # Domain-based business routing
        if sender_domain == "em.delhaize.be":
            return CategorizationResult(
                id=email.id,
                subject=email.subject,
                category="Business",
                sub_category="Delhaize",
                analysis="Email from Delhaize marketing domain",
                sender_goal="Promote Delhaize offers",
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
                    sender_goal="Request your attention",
                )

        # Check for collaborators
        if sender in self.settings.collaborator_email_list:
            return CategorizationResult(
                id=email.id,
                subject=email.subject,
                category="Collaborators",
                analysis="Email from team collaborator",
                sender_goal="Share a work update",
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
                    sender_goal="Provide a company update",
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
                    sender_goal="Confirm your purchase",
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
                        sender_goal="",
                    )
                )
        return results
