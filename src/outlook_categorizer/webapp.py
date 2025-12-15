"""FastAPI web frontend for Outlook Email Categorizer.

Objective:
    Provide a lightweight web interface and JSON API for running the existing
    email categorization workflow implemented in :mod:`src.outlook_categorizer.orchestrator`.
    This module intentionally keeps business logic inside the orchestrator and
    only handles HTTP request parsing and response rendering.

High-level call tree:
    - :func:`create_app`:
        - defines routes:
            - ``GET /health`` -> :func:`health`
            - ``GET /`` -> :func:`home`
            - ``POST /run`` -> :func:`run_html`
            - ``POST /api/run`` -> :func:`run_api`
        - wires templates via :class:`fastapi.templating.Jinja2Templates`
    - :func:`get_orchestrator`:
        - returns a new :class:`src.outlook_categorizer.orchestrator.EmailOrchestrator`
          instance.

Data flow:
    - HTTP request -> parse inputs -> call orchestrator.run(...) -> render results.

Operational notes:
    - The orchestrator performs Microsoft Graph authentication (device code
      flow) and Groq API calls. When running this server, authentication prompts
      may appear in the server console.
    - For tests, :func:`get_orchestrator` is overridden via
      ``app.dependency_overrides``.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .orchestrator import EmailOrchestrator


def get_orchestrator() -> EmailOrchestrator:
    """Create an :class:`~src.outlook_categorizer.orchestrator.EmailOrchestrator`.

    This function exists primarily to support FastAPI dependency injection and
    testing. Production code uses the real orchestrator; tests can override this
    dependency with a stub object implementing ``run(...)``.

    Returns:
        EmailOrchestrator: A new orchestrator instance.
    """

    return EmailOrchestrator()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    The app provides both an HTML UI and a JSON API.

    Routes:
        - ``GET /health``:
            Basic liveness check.
        - ``GET /``:
            Renders a form to run the categorizer.
        - ``POST /run``:
            Runs the categorizer and renders an HTML results table.
        - ``POST /api/run``:
            Runs the categorizer and returns JSON results.

    Template directory:
        Uses an explicit directory path to work reliably when the package is
        executed via ``python -m uvicorn src.outlook_categorizer.webapp:app``.

    Returns:
        FastAPI: FastAPI app.
    """

    app = FastAPI(title="Outlook Email Categorizer")

    templates = Jinja2Templates(directory="src/outlook_categorizer/templates")

    @app.get("/health")
    def health() -> dict[str, str]:
        """Health check endpoint.

        This is intentionally simple and should not perform external calls.

        Returns:
            dict[str, str]: Health payload.
        """

        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> Any:
        """Render the homepage.

        The homepage contains a form allowing the user to choose:
        - limit (optional)
        - folder_label (optional)
        - dry_run (checkbox)
        and submit it to ``POST /run``.

        Args:
            request: FastAPI request.

        Returns:
            Any: Template response.
        """

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
            },
        )

    @app.post("/run", response_class=HTMLResponse)
    def run_html(
        request: Request,
        limit: Optional[int] = Form(default=None),
        folder_label: Optional[str] = Form(default=None),
        dry_run: bool = Form(default=False),
        orchestrator: EmailOrchestrator = Depends(get_orchestrator),
    ) -> Any:
        """Run the categorizer via HTML form and render results.

        This route delegates all categorization logic to
        :meth:`src.outlook_categorizer.orchestrator.EmailOrchestrator.run`.

        Args:
            request: FastAPI request.
            limit: Maximum number of emails.
            folder_label: Human-friendly source folder label or path.
            dry_run: If True, do not move emails.
            orchestrator: Orchestrator dependency.

        Returns:
            Any: Template response.
        """

        results = orchestrator.run(limit=limit, folder_label=folder_label, dry_run=dry_run)

        summary = {
            "total": len(results),
            "successful": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
        }

        return templates.TemplateResponse(
            "results.html",
            {
                "request": request,
                "results": results,
                "summary": summary,
                "limit": limit,
                "folder_label": folder_label,
                "dry_run": dry_run,
            },
        )

    @app.post("/api/run")
    def run_api(
        payload: dict[str, Any],
        orchestrator: EmailOrchestrator = Depends(get_orchestrator),
    ) -> dict[str, Any]:
        """Run the categorizer via JSON API.

        Expected request body:
            ``{"limit": 5, "folder_label": "Inbox/Boss", "dry_run": true}``

        Notes:
            This endpoint deliberately uses a minimal unvalidated dict payload
            to keep the API surface small. If you want stricter validation, we
            can introduce a Pydantic request model.

        Args:
            payload: JSON payload with keys: limit, folder_label, dry_run.
            orchestrator: Orchestrator dependency.

        Returns:
            dict[str, Any]: Results payload.
        """

        limit = payload.get("limit")
        folder_label = payload.get("folder_label")
        dry_run = bool(payload.get("dry_run", False))

        results = orchestrator.run(limit=limit, folder_label=folder_label, dry_run=dry_run)

        return {
            "results": [r.model_dump() for r in results],
            "summary": {
                "total": len(results),
                "successful": sum(1 for r in results if r.success),
                "failed": sum(1 for r in results if not r.success),
            },
        }

    return app


app = create_app()
