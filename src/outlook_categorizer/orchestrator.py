"""Workflow orchestrator.

Objective:
    Coordinate the end-to-end workflow:
    1) Authenticate to Microsoft Graph
    2) Fetch candidate emails
    3) Categorize each email (heuristics first, then LLM)
    4) Ensure destination folders exist
    5) Move emails (unless running in dry-run mode)
    6) Return per-email results suitable for CLI/web UI

Responsibilities:
    - Compose the core components (auth, graph client, categorizer, folder
      manager).
    - Provide an imperative API (:meth:`EmailOrchestrator.run`) that can be
      called from the CLI, FastAPI webapp, or other scripts.

High-level call tree:
    - :class:`EmailOrchestrator`
        - :meth:`EmailOrchestrator.run`
            - :meth:`FolderManager.initialize`
            - (optional) :meth:`FolderManager.resolve_folder_label`
            - :meth:`EmailClient.get_emails`
            - for each email:
                - :meth:`EmailOrchestrator.process_email` OR dry-run branch
                    - :meth:`EmailCategorizer.categorize`
                    - :meth:`FolderManager.get_destination_folder`
                    - :meth:`EmailClient.move_email`
    - :func:`run_categorizer` convenience wrapper

Operational notes:
    - Microsoft Graph auth uses device-code flow, which prints instructions to
      stdout. When run from a server (FastAPI) this still occurs in logs.
    - The orchestrator does not persist state between runs.
"""

import logging
from typing import Optional

from .auth import GraphAuthenticator
from .categorizer import EmailCategorizer
from .config import Settings, get_settings
from .email_client import EmailClient
from .folder_manager import FolderManager
from .models import Email, ProcessingResult

logger = logging.getLogger(__name__)


class EmailOrchestrator:
    """
    Orchestrates the email categorization workflow.

    Coordinates fetching emails, categorizing them, and moving to folders.

    This class is intentionally "glue" code: it connects the Graph client,
    categorizer, and folder manager without embedding business rules.

    Attributes:
        settings: Application settings.
        auth: Graph API authenticator.
        email_client: Email client for API operations.
        categorizer: AI email categorizer.
        folder_manager: Folder management.
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        """
        Initialize orchestrator with all components.

        The orchestrator is constructed with a settings object to make testing
        easy. If settings are not provided, :func:`get_settings` is used.

        Args:
            settings: Application settings (loads from env if None).
        """
        self.settings = settings or get_settings()

        # Initialize components
        self.auth = GraphAuthenticator(self.settings)
        self.email_client = EmailClient(self.settings, self.auth)
        self.categorizer = EmailCategorizer(self.settings)
        self.folder_manager = FolderManager(self.email_client)

    def process_email(self, email: Email) -> ProcessingResult:
        """
        Process a single email: categorize and move to folder.

        This method represents the "full" workflow for one email (categorize,
        resolve destination folder, move).

        Errors are caught and returned inside :class:`ProcessingResult` so that
        a batch run can continue processing other emails.

        Args:
            email: Email to process.

        Returns:
            ProcessingResult: Result of processing.
        """
        try:
            # Categorize email
            categorization = self.categorizer.categorize(email)

            if not categorization:
                return ProcessingResult(
                    email_id=email.id,
                    subject=email.subject,
                    sender=email.sender_email,
                    received_date_time=email.received_date_time,
                    category="Other",
                    success=False,
                    error="Failed to categorize email",
                )

            # Get destination folder
            folder = self.folder_manager.get_destination_folder(categorization)

            if not folder:
                return ProcessingResult(
                    email_id=email.id,
                    subject=email.subject,
                    sender=email.sender_email,
                    received_date_time=email.received_date_time,
                    category=categorization.category,
                    sub_category=categorization.sub_category,
                    success=False,
                    error="Failed to get/create destination folder",
                )

            # Move email to folder
            moved = self.email_client.move_email(
                email.id,
                folder.id,
                source_folder_id=email.parent_folder_id,
            )

            return ProcessingResult(
                email_id=email.id,
                subject=email.subject,
                sender=email.sender_email,
                received_date_time=email.received_date_time,
                category=categorization.category,
                sub_category=categorization.sub_category,
                sender_goal=categorization.sender_goal,
                folder_id=folder.id,
                success=moved,
                error=None if moved else "Failed to move email",
            )

        except Exception as e:
            logger.exception(f"Error processing email {email.id}")
            return ProcessingResult(
                email_id=email.id,
                subject=email.subject,
                sender=email.sender_email,
                received_date_time=email.received_date_time,
                category="Other",
                success=False,
                error=str(e),
            )

    def run(
        self,
        limit: Optional[int] = None,
        folder_id: Optional[str] = None,
        folder_label: Optional[str] = None,
        dry_run: bool = False,
    ) -> list[ProcessingResult]:
        """Run the email categorization workflow.

        Source folder selection:
            - If ``folder_label`` is provided, it is resolved to a Graph folder
              id using :meth:`FolderManager.resolve_folder_label`.
            - Otherwise, if ``folder_id`` is provided, it is used directly.
            - Otherwise, ``settings.inbox_folder_id`` is used if configured.
            - If none of the above are set, :meth:`EmailClient.get_emails`
              defaults to Inbox.

        Dry-run mode:
            When ``dry_run=True`` the orchestrator will categorize emails but
            will not move them. This is useful for debugging and validating
            rules without changing mailbox state.

        Args:
            limit: Maximum emails to process (uses settings default if None).
            folder_id: Specific folder ID to process (uses settings default if None).
            folder_label: Human-friendly folder name or path to process.
            dry_run: If True, categorize but don't move emails.

        Returns:
            list[ProcessingResult]: Results for all processed emails.
        """
        batch_size = limit or self.settings.email_batch_size
        target_folder_id = folder_id or self.settings.inbox_folder_id

        source_folder: Optional[str] = None
        explicit_source_folder = bool(folder_label or folder_id or self.settings.inbox_folder_id)
        skip_categorized = not explicit_source_folder

        logger.info(f"Starting email categorization (batch_size={batch_size})")

        # Initialize folder cache (needed for label resolution and destination folders).
        self.folder_manager.initialize()

        if folder_label:
            resolved = self.folder_manager.resolve_folder_label(folder_label)
            if not resolved:
                raise ValueError(f"Folder label not found: {folder_label}")

            target_folder_id = resolved.id
            source_folder = folder_label
            logger.info(
                "Fetching emails from folder_label=%s (folder_id=%s)",
                folder_label,
                target_folder_id,
            )
        elif target_folder_id:
            source_folder = f"folder_id={target_folder_id}"
            logger.info(f"Fetching emails from folder_id={target_folder_id}")
        else:
            logger.info("Fetching emails from Inbox (default)")

        # Always skip categorized emails to prevent 404 errors on re-runs
        skip_categorized = True

        # Fetch emails.
        # When a specific folder is requested, include all subfolders.
        if target_folder_id:
            folders = self.folder_manager.get_descendant_folders(
                target_folder_id,
                include_self=True,
            )
            folder_ids = [f.id for f in folders]
            logger.info(
                "Including subfolders for source=%s (folders=%s)",
                source_folder or target_folder_id,
                len(folder_ids),
            )

            seen: set[str] = set()
            emails = []

            remaining = batch_size
            for fid in folder_ids:
                if remaining <= 0:
                    break

                chunk = self.email_client.get_emails(
                    folder_id=fid,
                    limit=remaining,
                    skip_flagged=True,
                    skip_categorized=skip_categorized,
                )

                for email in chunk:
                    if email.id in seen:
                        continue
                    seen.add(email.id)
                    emails.append(email)
                    remaining -= 1
                    if remaining <= 0:
                        break
        else:
            emails = self.email_client.get_emails(
                folder_id=None,
                limit=batch_size,
                skip_flagged=True,
                skip_categorized=skip_categorized,
            )

        if not emails:
            logger.info("No emails to process")
            return []

        logger.info(f"Processing {len(emails)} emails")

        results = []
        for i, email in enumerate(emails, 1):
            logger.info(f"Processing email {i}/{len(emails)}: {email.subject[:50]}...")

            if dry_run:
                # Dry run: categorize only
                categorization = self.categorizer.categorize(email)
                if categorization:
                    results.append(
                        ProcessingResult(
                            email_id=email.id,
                            subject=email.subject,
                            sender=email.sender_email,
                            received_date_time=email.received_date_time,
                            category=categorization.category,
                            sub_category=categorization.sub_category,
                            sender_goal=categorization.sender_goal,
                            success=True,
                            error="DRY RUN - not moved",
                        )
                    )
                else:
                    results.append(
                        ProcessingResult(
                            email_id=email.id,
                            subject=email.subject,
                            sender=email.sender_email,
                            received_date_time=email.received_date_time,
                            category="Other",
                            success=False,
                            error="Failed to categorize",
                        )
                    )
            else:
                # Full processing
                result = self.process_email(email)
                results.append(result)

        # Summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        logger.info(f"Completed: {successful} successful, {failed} failed")

        return results


def run_categorizer(
    limit: Optional[int] = None,
    folder_id: Optional[str] = None,
    folder_label: Optional[str] = None,
    dry_run: bool = False,
) -> list[ProcessingResult]:
    """Convenience wrapper to run the categorizer.

    This is a thin wrapper around :class:`EmailOrchestrator` used by some
    scripts/tests to run the workflow without manually instantiating the class.

    Args:
        limit: Maximum emails to process.
        folder_id: Specific folder ID to process.
        folder_label: Human-friendly folder name or path to process.
        dry_run: If True, categorize but don't move emails.

    Returns:
        list[ProcessingResult]: Results for all processed emails.
    """
    orchestrator = EmailOrchestrator()
    return orchestrator.run(
        limit=limit,
        folder_id=folder_id,
        folder_label=folder_label,
        dry_run=dry_run,
    )
