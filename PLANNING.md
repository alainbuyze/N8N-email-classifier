# Outlook Email Categorizer - Python Module

## Project Overview
A Python module that replicates the N8N "Outlook Categorizer" workflow. It fetches emails from Microsoft Outlook via Graph API, uses AI (Groq LLM) to categorize them, and organizes them into folders.

## Architecture

```
outlook_categorizer/
├── src/
│   └── outlook_categorizer/
│       ├── __init__.py
│       ├── config.py          # Configuration and settings
│       ├── auth.py            # Microsoft Graph authentication
│       ├── email_client.py    # Email fetching and operations
│       ├── sanitizer.py       # HTML/text sanitization
│       ├── categorizer.py     # AI categorization with Groq
│       ├── folder_manager.py  # Folder creation and management
│       └── orchestrator.py    # Main workflow orchestration
├── tests/
│   ├── __init__.py
│   ├── test_sanitizer.py
│   ├── test_categorizer.py
│   └── test_folder_manager.py
├── .env.example
├── requirements.txt
├── README.md
├── PLANNING.md
└── TASK.md
```

## Technology Stack
- **Python 3.10+**
- **msal** - Microsoft Authentication Library
- **requests** - HTTP client for Graph API
- **groq** - Groq LLM SDK
- **markdownify** - HTML to Markdown conversion
- **pydantic** - Data validation and settings
- **python-dotenv** - Environment variable management

## Email Categories
Based on the N8N workflow, the following categories are supported:
- **Action** - Needs response or action from a personal email
- **Response** - Reply to a personal email from user
- **Junk** - Ads, sales, newsletters, promotions
- **Spam** - Phishing, scams, suspicious emails
- **Receipt** - Purchase confirmations
- **Boss** - Messages from boss (configurable)
- **Company** - Messages from company domain
- **Collaborators** - Messages from team members
- **Community** - Updates, events, forums
- **Business** - Business communications
- **Other** - Doesn't fit other categories

## Data Flow
1. Authenticate with Microsoft Graph API
2. Fetch unprocessed emails (unflagged, uncategorized)
3. For each email:
   a. Sanitize HTML body to clean text
   b. Send to Groq LLM for categorization
   c. Create category folder if needed
   d. Create subcategory folder if needed
   e. Move email to appropriate folder
4. Log results and handle errors

## Configuration
All sensitive data via environment variables:
- `AZURE_CLIENT_ID` - Azure AD application ID
- `AZURE_CLIENT_SECRET` - Azure AD client secret
- `AZURE_TENANT_ID` - Azure AD tenant ID
- `GROQ_API_KEY` - Groq API key
- `BOSS_EMAIL` - Boss email address for categorization
- `COMPANY_DOMAIN` - Company domain for categorization
- `INBOX_FOLDER_ID` - Optional specific folder to process

## Code Style
- PEP8 compliant
- Type hints throughout
- Google-style docstrings
- Formatted with black
- Pydantic for validation
