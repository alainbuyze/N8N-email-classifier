import runpy
from pathlib import Path


def test_cli_can_be_loaded_via_runpy_without_package_context() -> None:
    """Load cli.py as a script module without executing main.

    This verifies the ImportError fallback path works (relative import fails,
    then absolute import succeeds after adding the src root to sys.path).
    """

    project_root = Path(__file__).resolve().parents[1]
    cli_path = project_root / "src" / "outlook_categorizer" / "cli.py"

    runpy.run_path(str(cli_path), run_name="_cli_test_")


def test_cli_path_is_expected() -> None:
    """Ensure the cli.py path exists (sanity check for repository layout)."""

    project_root = Path(__file__).resolve().parents[1]
    cli_path = project_root / "src" / "outlook_categorizer" / "cli.py"

    assert cli_path.exists()
