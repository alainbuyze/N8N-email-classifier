from datetime import datetime

from src.outlook_categorizer.cli import print_results
from src.outlook_categorizer.models import ProcessingResult


def test_print_results_includes_date_and_sender(capsys) -> None:
    """Ensure CLI output includes short date and sender when available."""

    results = [
        ProcessingResult(
            email_id="email-1",
            subject="Hello World",
            sender="alice@example.com",
            received_date_time=datetime(2025, 12, 15, 10, 30, 0),
            category="Action",
            sub_category="Business",
            sender_goal="Ask for a quick reply",
            success=True,
        )
    ]

    print_results(results, verbose=False)

    captured = capsys.readouterr().out
    assert "[12-15]" in captured
    assert "alice@example.com" in captured
    assert "Hello World" in captured
    assert "Ask for a quick reply" in captured
