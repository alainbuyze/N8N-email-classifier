from unittest.mock import MagicMock

from src.outlook_categorizer import cli


def test_cli_passes_folder_label_to_orchestrator(monkeypatch) -> None:
    """Ensure CLI forwards --folder-label/-f to EmailOrchestrator.run."""

    orchestrator_instance = MagicMock()
    monkeypatch.setattr(
        cli,
        "EmailOrchestrator",
        lambda *args, **kwargs: orchestrator_instance,
    )

    orchestrator_instance.run.return_value = []

    exit_code = cli.main(["--limit", "1", "--folder-label", "Inbox/Boss", "--dry-run"])

    assert exit_code == 0
    orchestrator_instance.run.assert_called_once()
    _, kwargs = orchestrator_instance.run.call_args
    assert kwargs["folder_label"] == "Inbox/Boss"
