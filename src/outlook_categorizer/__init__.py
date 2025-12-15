"""Outlook Email Categorizer package.

Objective:
    Provide a Python implementation of an email categorization workflow:
    - Fetch emails from Microsoft Outlook using Microsoft Graph.
    - Categorize emails using a hybrid approach:
        - Deterministic heuristics for strict business rules.
        - Groq LLM for general classification.
    - Create destination folders and move emails accordingly.

Key modules:
    - :mod:`src.outlook_categorizer.auth`:
        Microsoft Graph authentication (device code flow, token cache).
    - :mod:`src.outlook_categorizer.email_client`:
        Graph API wrapper for emails and folders.
    - :mod:`src.outlook_categorizer.categorizer`:
        Prompt construction, heuristics, Groq calls, response parsing.
    - :mod:`src.outlook_categorizer.folder_manager`:
        Folder caching, folder creation, destination resolution.
    - :mod:`src.outlook_categorizer.orchestrator`:
        End-to-end workflow coordination.
    - :mod:`src.outlook_categorizer.cli` / :mod:`src.outlook_categorizer.webapp`:
        User-facing entrypoints.
"""

__version__ = "0.1.0"
