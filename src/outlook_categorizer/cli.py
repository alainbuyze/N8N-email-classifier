"""Command-line interface (CLI) entrypoint.

Objective:
    Provide a human-friendly CLI wrapper around
    :class:`src.outlook_categorizer.orchestrator.EmailOrchestrator`.

Responsibilities:
    - Parse arguments (limit, folder selection, verbosity, dry-run).
    - Configure logging (including suppressing noisy HTTP request logs).
    - Invoke the orchestrator and print a readable summary of results.

High-level call tree:
    - :func:`main`
        - :func:`setup_logging`
            - installs :class:`_HttpxRequestInfoToDebugFilter`
        - instantiate :class:`EmailOrchestrator`
        - :meth:`EmailOrchestrator.run`
        - :func:`print_results`

Operational notes:
    - This module supports being run both as a package module
      (``python -m src.outlook_categorizer.cli``) and as a script
      (``python src/outlook_categorizer/cli.py``). The import fallback handles
      the script case.
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from .orchestrator import EmailOrchestrator
    from .config import get_settings
except ImportError:  # pragma: no cover
    src_root = Path(__file__).resolve().parents[1]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    from outlook_categorizer.orchestrator import EmailOrchestrator
    from outlook_categorizer.config import get_settings


class _HttpxRequestInfoToDebugFilter(logging.Filter):
    """Filter to suppress noisy httpx "HTTP Request:" INFO logs.

    Some underlying libraries log each HTTP request at INFO level. This filter
    hides those messages unless the root logger is in DEBUG mode.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Determine whether a log record should be emitted.

        Args:
            record: Log record emitted by the logging framework.

        Returns:
            bool: True to allow emission, False to suppress.
        """
        msg = record.getMessage()
        if record.name.startswith("httpx") and msg.startswith("HTTP Request:"):
            # Only show request logs when running in DEBUG/verbose mode.
            return logging.getLogger().isEnabledFor(logging.DEBUG)
        return True


def setup_logging(level: str = "INFO") -> None:
    """
    Configure logging for the application.

    This sets the root logger level and installs the
    :class:`_HttpxRequestInfoToDebugFilter` on all root handlers.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR).
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    root_logger = logging.getLogger()
    downgrade_filter = _HttpxRequestInfoToDebugFilter()
    for handler in root_logger.handlers:
        handler.addFilter(downgrade_filter)


def print_results(results: list, verbose: bool = False) -> None:
    """
    Print processing results to console.

    Output format:
        - Group results by category.
        - Display sender and short received date when available.
        - Optionally print errors when ``verbose=True``.

    Args:
        results: List of ProcessingResult objects.
        verbose: If True, print detailed information.
    """
    if not results:
        print("\nNo emails processed.")
        return

    print(f"\n{'='*60}")
    print(f"PROCESSING RESULTS: {len(results)} emails")
    print(f"{'='*60}\n")

    # Group by category
    by_category: dict[str, list] = {}
    for result in results:
        cat = result.category
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(result)

    for category, items in sorted(by_category.items()):
        print(f"\n📁 {category} ({len(items)} emails)")
        print("-" * 40)

        for item in items:
            status = "✅" if item.success else "❌"
            subcat = f" → {item.sub_category}" if item.sub_category else ""
            subject = item.subject[:50] + "..." if len(item.subject) > 50 else item.subject

            short_date = ""
            if getattr(item, "received_date_time", None):
                try:
                    if isinstance(item.received_date_time, datetime):
                        short_date = item.received_date_time.strftime("%m-%d")
                    else:
                        parsed_dt = datetime.fromisoformat(
                            str(item.received_date_time).replace("Z", "+00:00")
                        )
                        short_date = parsed_dt.strftime("%m-%d")
                except Exception:
                    short_date = ""

            sender = getattr(item, "sender", "") or ""
            prefix = ""
            if short_date:
                prefix += f"[{short_date}] "
            if sender:
                prefix += f"{sender} "

            sender_goal = (getattr(item, "sender_goal", "") or "").strip()
            goal_suffix = f" — {sender_goal}" if sender_goal else ""

            print(f"  {status} {prefix}{subject}{subcat}{goal_suffix}")

            if verbose and item.error:
                print(f"      Error: {item.error}")

    # Summary
    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful

    print(f"\n{'='*60}")
    print(f"SUMMARY: ✅ {successful} successful, ❌ {failed} failed")
    print(f"{'='*60}\n")


def main(args: Optional[list[str]] = None) -> int:
    """
    Main CLI entry point.

    This function is structured to be testable: pass an explicit ``args`` list
    instead of relying on ``sys.argv``.

    It delegates all business logic to the orchestrator.

    Args:
        args: Command line arguments (uses sys.argv if None).

    Returns:
        int: Exit code (0 for success, 1 for error).
    """
    parser = argparse.ArgumentParser(
        description="Outlook Email Categorizer - AI-powered email organization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    Process emails with default settings
  %(prog)s --limit 5          Process only 5 emails
  %(prog)s --dry-run          Categorize without moving emails
  %(prog)s --verbose          Show detailed output
        """,
    )

    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Maximum number of emails to process",
    )

    parser.add_argument(
        "--folder-label",
        "-f",
        type=str,
        default=None,
        help="Folder label to process (name or path like 'Inbox/Boss')",
    )

    parser.add_argument(
        "--account-username",
        type=str,
        default=None,
        help=(
            "Outlook account username to select from the MSAL token cache. "
            "Overrides OUTLOOK_ACCOUNT_USERNAME when provided."
        ),
    )

    parser.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="Categorize emails without moving them",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    parsed_args = parser.parse_args(args)

    # Setup logging
    log_level = "DEBUG" if parsed_args.verbose else parsed_args.log_level
    setup_logging(log_level)

    logger = logging.getLogger(__name__)

    try:
        print("\n🚀 Starting Outlook Email Categorizer...\n")

        if parsed_args.dry_run:
            print("⚠️  DRY RUN MODE - Emails will not be moved\n")

        # Run orchestrator
        settings = get_settings()
        if parsed_args.account_username:
            settings.outlook_account_username = parsed_args.account_username

        orchestrator = EmailOrchestrator(settings=settings)
        results = orchestrator.run(
            limit=parsed_args.limit,
            folder_label=parsed_args.folder_label,
            dry_run=parsed_args.dry_run,
        )

        # Print results
        print_results(results, verbose=parsed_args.verbose)

        # Return appropriate exit code
        failed = sum(1 for r in results if not r.success)
        return 1 if failed > 0 else 0

    except Exception as e:
        logger.exception("Fatal error")
        print(f"\n❌ Error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
