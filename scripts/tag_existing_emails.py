"""Utility script to tag already-categorized emails with 'Categorized' tag.

This script is useful after deploying the category tagging fix to tag emails
that were moved before the fix was deployed. This prevents them from being
reprocessed and causing 404 errors.

Usage:
    python scripts/tag_existing_emails.py
"""

import logging
from outlook_categorizer.auth import GraphAuthenticator
from outlook_categorizer.config import get_settings, CATEGORIZED_TAG
from outlook_categorizer.email_client import EmailClient
from outlook_categorizer.folder_manager import FolderManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def tag_emails_in_folder(email_client: EmailClient, folder_id: str, folder_name: str):
    """Tag all emails in a folder with the Categorized tag.
    
    Args:
        email_client: Email client instance
        folder_id: Folder ID to process
        folder_name: Folder name for logging
    """
    logger.info(f"Processing folder: {folder_name}")
    
    # Fetch emails without skip_categorized filter to get all emails
    emails = email_client.get_emails(
        folder_id=folder_id,
        limit=50,  # Process in batches
        skip_flagged=False,
        skip_categorized=False,  # Get all emails, even if already tagged
    )
    
    if not emails:
        logger.info(f"  No emails found in {folder_name}")
        return
    
    tagged_count = 0
    already_tagged_count = 0
    failed_count = 0
    
    for email in emails:
        # Check if already tagged
        if email.categories and CATEGORIZED_TAG in email.categories:
            already_tagged_count += 1
            continue
        
        # Tag the email
        success = email_client.add_category(email.id, CATEGORIZED_TAG)
        if success:
            tagged_count += 1
            logger.debug(f"  Tagged: {email.subject[:50]}")
        else:
            failed_count += 1
            logger.warning(f"  Failed to tag: {email.subject[:50]}")
    
    logger.info(
        f"  Results: {tagged_count} tagged, {already_tagged_count} already tagged, "
        f"{failed_count} failed"
    )


def main():
    """Main function to tag all emails in category folders."""
    logger.info("Starting email tagging utility")
    
    # Initialize components
    settings = get_settings()
    auth = GraphAuthenticator(settings)
    email_client = EmailClient(settings, auth)
    folder_manager = FolderManager(email_client)
    
    # Initialize folder cache
    folder_manager.initialize()
    
    # Get all folders
    all_folders = folder_manager.folders
    
    # Filter to category folders (folders under Inbox)
    inbox_folder = folder_manager.resolve_folder_label("Inbox")
    if not inbox_folder:
        logger.error("Could not find Inbox folder")
        return
    
    # Get all descendant folders of Inbox (these are category folders)
    category_folders = folder_manager.get_descendant_folders(
        inbox_folder.id,
        include_self=False  # Don't include Inbox itself
    )
    
    logger.info(f"Found {len(category_folders)} category folders to process")
    
    total_tagged = 0
    total_already_tagged = 0
    total_failed = 0
    
    for folder in category_folders:
        tag_emails_in_folder(email_client, folder.id, folder.display_name)
    
    logger.info("=" * 60)
    logger.info("Tagging complete!")
    logger.info(f"Total emails tagged: {total_tagged}")
    logger.info(f"Total already tagged: {total_already_tagged}")
    logger.info(f"Total failed: {total_failed}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
