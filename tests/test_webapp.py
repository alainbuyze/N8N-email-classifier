from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.outlook_categorizer.models import ProcessingResult
from src.outlook_categorizer.webapp import create_app, get_orchestrator
from src.outlook_categorizer.auth import DeviceCodeAuthRequired


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


def test_run_html_auth_required_renders_device_code_instructions() -> None:
    """HTML run shows device-code instructions when auth is required."""

    app = create_app()

    orchestrator = MagicMock()
    orchestrator.run.side_effect = DeviceCodeAuthRequired(
        {
            "user_code": "ABCDE12345",
            "verification_uri": "https://www.microsoft.com/link",
            "message": "To sign in, open https://www.microsoft.com/link and enter the code ABCDE12345",
        }
    )

    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    client = TestClient(app)

    resp = client.post(
        "/run",
        data={"limit": "5", "folder_label": "Inbox", "dry_run": "true"},
    )

    assert resp.status_code == 401
    assert "Authentication Required" in resp.text
    assert "ABCDE12345" in resp.text
    assert "microsoft.com/link" in resp.text


def test_api_run_auth_required_returns_401_payload() -> None:
    """API run returns a structured 401 JSON when auth is required."""

    app = create_app()

    orchestrator = MagicMock()
    orchestrator.run.side_effect = DeviceCodeAuthRequired(
        {
            "user_code": "ZZZZZ99999",
            "verification_uri": "https://www.microsoft.com/link",
            "message": "Use code ZZZZZ99999",
        }
    )

    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    client = TestClient(app)

    resp = client.post(
        "/api/run",
        json={"limit": 1, "folder_label": "Inbox", "dry_run": True},
    )

    assert resp.status_code == 401
    payload = resp.json()
    assert payload["error"] == "authentication_required"
    assert payload["verification_uri"] == "https://www.microsoft.com/link"
    assert payload["user_code"] == "ZZZZZ99999"


def test_auth_complete_returns_home_page() -> None:
    """Auth complete endpoint should not 404 and returns the home page."""

    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/auth/complete",
        data={"state_id": "", "limit": "", "folder_label": "", "dry_run": "false"},
    )

    assert resp.status_code == 200
    assert "Outlook Email Categorizer" in resp.text


def test_run_html_passes_target_user_principal_name() -> None:
    """HTML run passes target_user_principal_name to orchestrator when provided."""

    app = create_app()

    orchestrator = MagicMock()
    orchestrator.run.return_value = []

    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    client = TestClient(app)

    resp = client.post(
        "/run",
        data={
            "limit": "5",
            "folder_label": "Inbox",
            "dry_run": "true",
            "target_user_principal_name": "someone@tenant.com",
        },
    )

    assert resp.status_code == 200
    orchestrator.run.assert_called_once_with(
        limit=5,
        folder_label="Inbox",
        dry_run=True,
        target_user_principal_name="someone@tenant.com",
    )


def test_api_run_passes_target_user_principal_name() -> None:
    """API run passes target_user_principal_name in JSON payload to orchestrator."""

    app = create_app()

    orchestrator = MagicMock()
    orchestrator.run.return_value = []

    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    client = TestClient(app)

    resp = client.post(
        "/api/run",
        json={
            "limit": 2,
            "folder_label": "Inbox",
            "dry_run": False,
            "target_user_principal_name": "api-user@tenant.com",
        },
    )

    assert resp.status_code == 200
    orchestrator.run.assert_called_once_with(
        limit=2,
        folder_label="Inbox",
        dry_run=False,
        target_user_principal_name="api-user@tenant.com",
    )
