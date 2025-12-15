# Outlook Email Categorizer

A Python module that automatically categorizes and organizes Microsoft Outlook emails using AI (Groq LLM). This is a Python implementation of an N8N workflow.

## Features

- **AI-Powered Categorization**: Uses Groq LLM to intelligently categorize emails
- **Automatic Folder Organization**: Creates folders and moves emails automatically
- **Smart Heuristics**: Quick categorization for obvious cases (boss, company, receipts)
- **Configurable Categories**: Action, Response, Junk, Spam, Receipt, Boss, Company, Collaborators, Community, Business, Other
- **Subcategory Support**: Organize emails into nested folders
- **Dry Run Mode**: Test categorization without moving emails

## Prerequisites

1. **Python 3.10+**
2. **Azure AD Application** with Mail.ReadWrite permissions
3. **Groq API Key** from [console.groq.com](https://console.groq.com)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd N8N-email-classifier
   ```

2. Create and activate virtual environment:
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

## Azure AD Setup (Personal Microsoft Account)

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App registrations**
3. Click **New registration**
4. Configure:
   - Name: `Outlook Email Categorizer`
   - Supported account types: **Personal Microsoft accounts only** (or "Accounts in any organizational directory and personal Microsoft accounts")
   - Redirect URI: Leave blank (we use device code flow)
5. After creation, note the **Application (client) ID**
6. Go to **Authentication**:
   - Enable **Allow public client flows** → Set to **Yes**
7. Go to **API permissions** → **Add permission** → **Microsoft Graph** → **Delegated permissions**:
   - `Mail.ReadWrite`
   - `Mail.Send` (optional)
8. No admin consent needed for personal accounts

## Configuration

Edit `.env` file with your credentials:

```env
# Azure AD
AZURE_CLIENT_ID=your-client-id
# For personal accounts, use "consumers"
AZURE_TENANT_ID=consumers

# Groq
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=llama-3.1-70b-versatile

# Categorization
BOSS_EMAIL=boss@yourcompany.com
COMPANY_DOMAIN=yourcompany.com
COLLABORATOR_EMAILS=colleague1@company.com,colleague2@company.com

# Processing
EMAIL_BATCH_SIZE=10
LOG_LEVEL=INFO
```

## Usage

### Command Line

```bash
# Process emails with default settings
python -m src.outlook_categorizer.cli

# Process only 5 emails
python -m src.outlook_categorizer.cli --limit 5

# Process a specific folder by label (name or path)
python -m src.outlook_categorizer.cli --limit 5 --folder-label "Inbox/Boss"

# Dry run (categorize without moving)
python -m src.outlook_categorizer.cli --dry-run

# Verbose output
python -m src.outlook_categorizer.cli --verbose

# Combine options
python -m src.outlook_categorizer.cli --limit 10 --dry-run --verbose

# Or run the file directly (also supported)
python src/outlook_categorizer/cli.py
```

### Web UI (FastAPI)

```bash
# Start the web server
python -m uvicorn src.outlook_categorizer.webapp:app --reload

# Open in browser
# http://127.0.0.1:8000
```

### Docker

```bash
# Build image
docker build -t outlook-categorizer .

# Run (expects a .env file in the project root)
docker run --rm -p 8000:8000 --env-file .env outlook-categorizer

# Open in browser
# http://127.0.0.1:8000
```

### Docker Compose

```bash
# Run (expects a .env file in the project root)
docker compose up --build
```

### Python API

```python
from src.outlook_categorizer.orchestrator import EmailOrchestrator

# Initialize orchestrator
orchestrator = EmailOrchestrator()

# Run categorization
results = orchestrator.run(limit=10, dry_run=False)

# Process results
for result in results:
    print(f"{result.subject}: {result.category}")
    if not result.success:
        print(f"  Error: {result.error}")
```

### Individual Components

```python
from src.outlook_categorizer.config import get_settings
from src.outlook_categorizer.auth import GraphAuthenticator
from src.outlook_categorizer.email_client import EmailClient
from src.outlook_categorizer.categorizer import EmailCategorizer

# Load settings
settings = get_settings()

# Authenticate
auth = GraphAuthenticator(settings)

# Fetch emails
client = EmailClient(settings, auth)
emails = client.get_emails(limit=5)

# Categorize
categorizer = EmailCategorizer(settings)
for email in emails:
    result = categorizer.categorize(email)
    print(f"{email.subject} -> {result.category}")
```

## Email Categories

| Category | Description |
|----------|-------------|
| **Action** | Requires response or action |
| **Response** | Reply to your previous email |
| **Junk** | Ads, newsletters, promotions |
| **Spam** | Phishing, scams, suspicious |
| **Receipt** | Purchase confirmations |
| **Boss** | From your boss |
| **Company** | From company domain |
| **Collaborators** | From team members |
| **Community** | Forums, events, updates |
| **Business** | Business communications |
| **Other** | Uncategorized |

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/outlook_categorizer

# Run specific test file
pytest tests/test_sanitizer.py -v
```

## Project Structure

```
outlook_categorizer/
├── src/
│   └── outlook_categorizer/
│       ├── __init__.py
│       ├── config.py          # Settings and configuration
│       ├── auth.py            # Microsoft Graph authentication
│       ├── models.py          # Pydantic data models
│       ├── email_client.py    # Email operations
│       ├── sanitizer.py       # HTML/text sanitization
│       ├── categorizer.py     # AI categorization
│       ├── folder_manager.py  # Folder operations
│       ├── orchestrator.py    # Workflow orchestration
│       └── cli.py             # Command-line interface
├── tests/
│   ├── test_sanitizer.py
│   ├── test_categorizer.py
│   └── test_folder_manager.py
├── .env.example
├── requirements.txt
├── PLANNING.md
├── TASK.md
└── README.md
```

## Troubleshooting

### Authentication Errors
- Verify Azure AD credentials in `.env`
- Ensure admin consent is granted for API permissions
- Check tenant ID matches your organization

### Rate Limiting
- Microsoft Graph has throttling limits
- Reduce `EMAIL_BATCH_SIZE` if hitting limits
- Add delays between requests if needed

### Categorization Issues
- Check Groq API key is valid
- Review logs for LLM response errors
- Use `--verbose` flag for detailed output

## License

MIT License
