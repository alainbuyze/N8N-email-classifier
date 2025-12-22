from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.outlook_categorizer.models import ProcessingResult
from src.outlook_categorizer.webapp import create_app, get_orchestrator


def test_health() -> None:
    """Health endpoint returns ok."""

    app = create_app()
    client = TestClient(app)

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_api_run_returns_results_and_summary() -> None:
    """API run returns results list and summary."""

    app = create_app()

    orchestrator = MagicMock()
    orchestrator.run.return_value = [
        ProcessingResult(
            email_id="e1",
            subject="Hello",
            sender="alice@example.com",
            category="Business",
            sender_goal="Request information",
            success=True,
        ),
        ProcessingResult(
            email_id="e2",
            subject="Oops",
            sender="bob@example.com",
            category="Other",
            sender_goal="",
            success=False,
            error="boom",
        ),
    ]

    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    client = TestClient(app)
    resp = client.post(
        "/api/run",
        json={"limit": 5, "folder_label": "Inbox/Boss", "dry_run": True},
    )

    assert resp.status_code == 200
    payload = resp.json()

    assert payload["summary"] == {"total": 2, "successful": 1, "failed": 1}
    assert len(payload["results"]) == 2
    assert payload["results"][0]["email_id"] == "e1"
    assert payload["results"][0]["sender_goal"] == "Request information"
    assert payload["results"][1]["success"] is False

    orchestrator.run.assert_called_once_with(
        limit=5,
        folder_label="Inbox/Boss",
        dry_run=True,
    )
