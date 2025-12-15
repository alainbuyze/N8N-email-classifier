# Task Tracker

## Current Sprint - 2024-12-14

### Completed
- [x] Analyze N8N workflow and identify components
- [x] Create project structure with PLANNING.md, TASK.md, README.md
- [x] Implement config module with environment variables and settings
- [x] Implement Microsoft Graph authentication module
- [x] Implement email fetching and sanitization module
- [x] Implement AI categorization module with Groq
- [x] Implement folder management module
- [x] Implement main orchestrator/CLI
- [x] Create unit tests
- [x] Create requirements.txt
- [x] Fix CLI relative import error when running cli.py directly (2025-12-15)

## Discovered During Work
- Added Pydantic models module for data validation
- Added CLI module for command-line interface
- Added .env.example for configuration template
- Pytest currently failing in sanitizer and collaborator heuristic tests (unrelated to CLI entrypoint fix)
- Fixed folder cache collision where root-level and child folders share the same name (prevents subcategory fallback warnings) (2025-12-15)
- Externalized Groq system prompt into src/outlook_categorizer/prompts/system_prompt.txt (2025-12-15)
- Fixed heuristic precedence so collaborator emails are categorized as Collaborators before Company domain (2025-12-15)
- Enhanced CLI output to include short received date and sender per email in results (2025-12-15)
- Added INFO log to clarify which source folder is used for fetching emails (Inbox default vs INBOX_FOLDER_ID/--folder-id) (2025-12-15)
- Fixed email fetching default to use /me/mailFolders/inbox/messages (prevents processing messages outside Inbox when no folder is specified) (2025-12-15)
- Added heuristic routing for em.delhaize.be emails to categorize as Business/Delhaize (ensures correct subfolder placement) (2025-12-15)
- Replaced CLI source folder selection from --folder-id to --folder-label (supports folder name/path like Inbox/Boss, resolved to Graph folder ID) (2025-12-15)
- Added FastAPI web UI and JSON API to run the categorizer with limit/folder-label/dry-run and view results in the browser (2025-12-15)
- Migrated Pydantic models to use ConfigDict/model_config (removes deprecated class-based Config; Pydantic v3-ready) (2025-12-15)
- Added Dockerfile, .dockerignore, and docker-compose.yml to run the FastAPI web app in a container (2025-12-15)
- Expanded module/class/function docstrings across src/outlook_categorizer for clearer objectives, call trees, and operational notes (2025-12-15)

## Future Enhancements
- [ ] Add async support for parallel email processing
- [ ] Add email scheduling/cron support
- [ ] Add webhook trigger support
- [ ] Add email statistics/reporting
- [ ] Add retry logic for API failures
