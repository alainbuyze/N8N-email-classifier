from unittest.mock import MagicMock

from src.outlook_categorizer.orchestrator import EmailOrchestrator
from src.outlook_categorizer.models import Email, EmailBody


def _make_email(email_id: str) -> Email:
    """Create a minimal Email model for orchestrator tests."""

    return Email(
        id=email_id,
        subject=f"Subject {email_id}",
        body=EmailBody(content_type="text", content="Body"),
    )


def test_orchestrator_fetches_from_folder_and_subfolders(monkeypatch) -> None:
    """When a folder is selected, the orchestrator should include all subfolders."""

    settings = MagicMock()
    settings.email_batch_size = 10
    settings.inbox_folder_id = None

    orchestrator = EmailOrchestrator(settings=settings)

    # Stub out destination folder setup to keep test focused on fetching.
    orchestrator.folder_manager.initialize = MagicMock()
    orchestrator.folder_manager.resolve_folder_label = MagicMock(
        return_value=MagicMock(id="root")
    )

    orchestrator.folder_manager.get_descendant_folders = MagicMock(
        return_value=[
            MagicMock(id="root"),
            MagicMock(id="child-1"),
            MagicMock(id="child-2"),
        ]
    )

    orchestrator.email_client.get_emails = MagicMock(
        side_effect=[
            [_make_email("e1")],
            [_make_email("e2")],
            [_make_email("e3")],
        ]
    )

    # Avoid categorizer/folder/move logic in this test.
    orchestrator.process_email = MagicMock(
        side_effect=lambda email: MagicMock(success=True, category="Other")
    )

    results = orchestrator.run(limit=10, folder_label="Inbox/Target", dry_run=False)

    assert len(results) == 3
    assert orchestrator.email_client.get_emails.call_count == 3

    called_folder_ids = [
        call.kwargs["folder_id"]
        for call in orchestrator.email_client.get_emails.mock_calls
    ]
    assert called_folder_ids == ["root", "child-1", "child-2"]


def test_orchestrator_folder_without_children_only_fetches_once(monkeypatch) -> None:
    """If the selected folder has no children, only fetch once."""

    settings = MagicMock()
    settings.email_batch_size = 10
    settings.inbox_folder_id = None

    orchestrator = EmailOrchestrator(settings=settings)

    orchestrator.folder_manager.initialize = MagicMock()
    orchestrator.folder_manager.resolve_folder_label = MagicMock(
        return_value=MagicMock(id="root")
    )

    orchestrator.folder_manager.get_descendant_folders = MagicMock(
        return_value=[MagicMock(id="root")]
    )

    orchestrator.email_client.get_emails = MagicMock(return_value=[_make_email("e1")])
    orchestrator.process_email = MagicMock(
        side_effect=lambda email: MagicMock(success=True, category="Other")
    )

    results = orchestrator.run(limit=10, folder_label="Inbox/Target", dry_run=False)

    assert len(results) == 1
    orchestrator.email_client.get_emails.assert_called_once()
    assert orchestrator.email_client.get_emails.call_args.kwargs["folder_id"] == "root"
