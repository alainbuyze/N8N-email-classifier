# Managing Files and Secrets in Azure for GOVC-Advisor

Complete guide for handling your local directory structure (`F:\GOVC`) and secret environment variables in Azure Container Apps.

**The Problem:**
- Your app stores files locally on `F:\GOVC` (Input, Output, Projects directories)
- Your app uses `.env.keys` with secrets (SUPABASE, OPENAI, etc.)
- `.env.local` has machine-specific paths that won't work in Azure
- Azure Container Apps has ephemeral storage (files are lost on restart)

**The Solution:**
- Azure Blob Storage for persistent file storage
- Azure Key Vault for secrets management
- Managed Identity for secure access
- Environment-specific configuration files

---

## Table of Contents

1. [Understanding the File System Issue](#understanding-the-file-system-issue)
2. [Phase 1: Set Up Azure Storage](#phase-1-set-up-azure-storage)
3. [Phase 2: Set Up Azure Key Vault](#phase-2-set-up-azure-key-vault)
4. [Phase 3: Update Application Configuration](#phase-3-update-application-configuration)
5. [Phase 4: Configure Container Apps](#phase-4-configure-container-apps)
6. [Phase 5: Update GitHub Actions](#phase-5-update-github-actions)
7. [Local Development Workflow](#local-development-workflow)
8. [Monitoring and Management](#monitoring-and-management)

---

## Understanding the File System Issue

### Current Local Setup

```
F:\GOVC\
├── Input/              # Downloaded documents
├── Output/             # Processed output
├── Projects/           # Project data
└── Generic info/       # Reference data
```

### Azure Container Apps Reality

- ✅ `/app/data` volume mount exists but is **NOT persistent**
- ❌ Files are lost when container restarts or scales
- ❌ Multiple container instances can't share files
- ❌ Ephemeral storage unsuitable for production

### Azure Solution Architecture

```
GitHub Push
    ↓
GitHub Actions
    ↓
Azure Container Apps (stateless - no files stored)
    ↓
Azure Blob Storage (persistent files)
    ↓
Supabase (metadata, vectors)
    ↓
Azure Key Vault (secrets)
```

---

## Phase 1: Set Up Azure Storage

### Step 1: Create Storage Account

```powershell
$RESOURCE_GROUP = "govc-advisor-rg"
$STORAGE_ACCOUNT_NAME = "gocvadvisorstorage"  # Must be globally unique, lowercase, no hyphens
$LOCATION = "eastus"

# Create storage account
az storage account create `
  --name $STORAGE_ACCOUNT_NAME `
  --resource-group $RESOURCE_GROUP `
  --location $LOCATION `
  --sku Standard_LRS `
  --kind StorageV2

# Get storage account key
$STORAGE_ACCOUNT_KEY = az storage account keys list `
  --name $STORAGE_ACCOUNT_NAME `
  --resource-group $RESOURCE_GROUP `
  --query "[0].value" -o tsv

Write-Host "Storage Account Key: $STORAGE_ACCOUNT_KEY"
```

### Step 2: Create Blob Storage Containers

```powershell
$STORAGE_ACCOUNT_NAME = "gocvadvisorstorage"

# Create containers for each directory structure
az storage container create `
  --name govc-input `
  --account-name $STORAGE_ACCOUNT_NAME

az storage container create `
  --name govc-output `
  --account-name $STORAGE_ACCOUNT_NAME

az storage container create `
  --name govc-projects `
  --account-name $STORAGE_ACCOUNT_NAME

az storage container create `
  --name govc-generic-info `
  --account-name $STORAGE_ACCOUNT_NAME

az storage container create `
  --name govc-archives `
  --account-name $STORAGE_ACCOUNT_NAME

# Verify containers created
az storage container list --account-name $STORAGE_ACCOUNT_NAME --query "[].name"
```

### Step 3: Get Storage Connection Details

```powershell
$STORAGE_ACCOUNT_NAME = "gocvadvisorstorage"
$RESOURCE_GROUP = "govc-advisor-rg"

# Get storage account details
$STORAGE_ACCOUNT_URL = az storage account show `
  --name $STORAGE_ACCOUNT_NAME `
  --resource-group $RESOURCE_GROUP `
  --query "primaryEndpoints.blob" -o tsv

$STORAGE_ACCOUNT_KEY = az storage account keys list `
  --name $STORAGE_ACCOUNT_NAME `
  --resource-group $RESOURCE_GROUP `
  --query "[0].value" -o tsv

Write-Host "Storage Account URL: $STORAGE_ACCOUNT_URL"
Write-Host "Storage Account Key: $STORAGE_ACCOUNT_KEY"
```

### Step 4: (Optional) Upload Initial Data

If you have existing data to migrate:

```powershell
$STORAGE_ACCOUNT_NAME = "gocvadvisorstorage"
$LOCAL_DATA_PATH = "F:\GOVC"

# Upload entire GOVC directory
az storage blob upload-batch `
  --account-name $STORAGE_ACCOUNT_NAME `
  --destination govc-input `
  --source "$LOCAL_DATA_PATH\Input" `
  --pattern "*"

# Repeat for other directories
az storage blob upload-batch `
  --account-name $STORAGE_ACCOUNT_NAME `
  --destination govc-projects `
  --source "$LOCAL_DATA_PATH\Projects" `
  --pattern "*"
```

---

## Phase 2: Set Up Azure Key Vault

### Step 5: Create Key Vault

```powershell
$RESOURCE_GROUP = "govc-advisor-rg"
$KEY_VAULT_NAME = "govc-advisor-kv"  # Must be globally unique
$LOCATION = "eastus"

# Create Key Vault
az keyvault create `
  --name $KEY_VAULT_NAME `
  --resource-group $RESOURCE_GROUP `
  --location $LOCATION `
  --enable-rbac-authorization

Write-Host "Key Vault created: $KEY_VAULT_NAME"
```

### Step 6: Add Secrets to Key Vault

```powershell
$KEY_VAULT_NAME = "govc-advisor-kv"

# Add API Keys and Secrets (from your .env.keys file)
az keyvault secret set `
  --name "supabase-url" `
  --vault-name $KEY_VAULT_NAME `
  --value "https://your-supabase-url.supabase.co"

az keyvault secret set `
  --name "supabase-key" `
  --vault-name $KEY_VAULT_NAME `
  --value "your-supabase-anon-key"

az keyvault secret set `
  --name "supabase-service-key" `
  --vault-name $KEY_VAULT_NAME `
  --value "your-supabase-service-key"

az keyvault secret set `
  --name "openai-api-key" `
  --vault-name $KEY_VAULT_NAME `
  --value "your-openai-api-key"

az keyvault secret set `
  --name "jwt-secret" `
  --vault-name $KEY_VAULT_NAME `
  --value "your-jwt-secret-change-in-production"

az keyvault secret set `
  --name "groq-api-key" `
  --vault-name $KEY_VAULT_NAME `
  --value "your-groq-api-key"

az keyvault secret set `
  --name "gemini-api-key" `
  --vault-name $KEY_VAULT_NAME `
  --value "your-gemini-api-key"

az keyvault secret set `
  --name "storage-account-key" `
  --vault-name $KEY_VAULT_NAME `
  --value "your-storage-account-key"

# Verify secrets created
az keyvault secret list --vault-name $KEY_VAULT_NAME --query "[].name"
```

### Step 7: Grant Container Apps Access to Key Vault

```powershell
$KEY_VAULT_NAME = "govc-advisor-kv"
$RESOURCE_GROUP = "govc-advisor-rg"

# Enable system-assigned identity for API Container App
az containerapp identity assign `
  --name govc-api `
  --resource-group $RESOURCE_GROUP `
  --system-assigned

# Enable system-assigned identity for UI Container App
az containerapp identity assign `
  --name govc-ui `
  --resource-group $RESOURCE_GROUP `
  --system-assigned

# Get the principal IDs
$API_PRINCIPAL_ID = az containerapp show `
  --name govc-api `
  --resource-group $RESOURCE_GROUP `
  --query "identity.principalId" -o tsv

$UI_PRINCIPAL_ID = az containerapp show `
  --name govc-ui `
  --resource-group $RESOURCE_GROUP `
  --query "identity.principalId" -o tsv

# Grant Key Vault access to both apps
az keyvault set-policy `
  --name $KEY_VAULT_NAME `
  --object-id $API_PRINCIPAL_ID `
  --secret-permissions get list

az keyvault set-policy `
  --name $KEY_VAULT_NAME `
  --object-id $UI_PRINCIPAL_ID `
  --secret-permissions get list
```

---

## Phase 3: Update Application Configuration

### Step 8: Create Azure Configuration Module

Create a new file: `src/core/azure_config.py`

```python
"""
Azure-specific configuration for cloud deployments.
Handles secrets from Key Vault and files from Blob Storage.
"""

import os
from pathlib import Path
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.blob import BlobServiceClient


class AzureConfig:
    """Manage Azure resources: Key Vault and Blob Storage."""

    def __init__(self):
        self.in_azure = os.getenv("IN_DOCKER") == "true"
        self.key_vault_name = os.getenv("KEY_VAULT_NAME", "govc-advisor-kv")
        self.storage_account_name = os.getenv("STORAGE_ACCOUNT_NAME", "gocvadvisorstorage")
        
        if self.in_azure:
            self.credential = DefaultAzureCredential()
            self._init_key_vault()
            self._init_blob_storage()
    
    def _init_key_vault(self):
        """Initialize Key Vault client."""
        kv_url = f"https://{self.key_vault_name}.vault.azure.net/"
        self.secret_client = SecretClient(vault_url=kv_url, credential=self.credential)
    
    def _init_blob_storage(self):
        """Initialize Blob Storage client."""
        account_url = f"https://{self.storage_account_name}.blob.core.windows.net"
        self.blob_service_client = BlobServiceClient(account_url=account_url, credential=self.credential)
    
    def get_secret(self, secret_name: str) -> Optional[str]:
        """Retrieve secret from Key Vault."""
        if not self.in_azure:
            # Fall back to environment variable
            return os.getenv(secret_name.upper().replace("-", "_"))
        
        try:
            secret = self.secret_client.get_secret(secret_name)
            return secret.value
        except Exception as e:
            print(f"Error retrieving secret {secret_name}: {e}")
            return None
    
    def get_blob_container_client(self, container_name: str):
        """Get a blob container client."""
        if not self.in_azure:
            raise RuntimeError("Blob Storage only available in Azure")
        
        return self.blob_service_client.get_container_client(container_name)
    
    def download_file(self, container_name: str, blob_name: str, local_path: str):
        """Download file from Blob Storage."""
        container_client = self.get_blob_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)
        
        with open(local_path, "wb") as download_file:
            download_file.write(blob_client.download_blob().readall())
    
    def upload_file(self, container_name: str, blob_name: str, local_path: str):
        """Upload file to Blob Storage."""
        container_client = self.get_blob_container_client(container_name)
        
        with open(local_path, "rb") as data:
            container_client.upload_blob(blob_name, data, overwrite=True)


# Global instance
azure_config = AzureConfig()
```

### Step 9: Update GOVC_config.py

Modify `src/core/GOVC_config.py` to use Azure when running in cloud:

```python
# Add at the top of the file after imports
from azure_config import azure_config

# In the Settings class, add properties for Azure storage paths:

class Settings(BaseSettings):
    # ... existing settings ...
    
    # Azure Storage Configuration
    AZURE_ENABLED: bool = Field(default_factory=lambda: os.getenv("IN_DOCKER") == "true")
    KEY_VAULT_NAME: str = Field(default="govc-advisor-kv")
    STORAGE_ACCOUNT_NAME: str = Field(default="gocvadvisorstorage")
    
    # Storage container names
    AZURE_INPUT_CONTAINER: str = "govc-input"
    AZURE_OUTPUT_CONTAINER: str = "govc-output"
    AZURE_PROJECTS_CONTAINER: str = "govc-projects"
    AZURE_GENERIC_INFO_CONTAINER: str = "govc-generic-info"
    
    # Build absolute paths based on environment
    @property
    def GOVC_INPUT_DIR(self) -> Path:
        """Get input directory path."""
        if self.AZURE_ENABLED:
            return Path("/tmp/govc/input")  # Temporary local cache
        else:
            return Path(self.ROOT_DRIVE) / self.ROOT_INPUT_DIR
    
    @property
    def GOVC_OUTPUT_DIR(self) -> Path:
        """Get output directory path."""
        if self.AZURE_ENABLED:
            return Path("/tmp/govc/output")
        else:
            return Path(self.ROOT_DRIVE) / self.ROOT_OUTPUT_DIR
    
    @property
    def GOVC_PROJECT_DIR(self) -> Path:
        """Get project directory path."""
        if self.AZURE_ENABLED:
            return Path("/tmp/govc/projects")
        else:
            return Path(self.ROOT_DRIVE) / self.ROOT_PROJECT_DIR
    
    @property
    def GOVC_GENERIC_INFO_DIR(self) -> Path:
        """Get generic info directory path."""
        if self.AZURE_ENABLED:
            return Path("/tmp/govc/generic_info")
        else:
            return Path(self.ROOT_DRIVE) / self.ROOT_GENERIC_INFO_DIR
    
    def get_azure_secret(self, secret_name: str) -> str:
        """Get secret from Azure Key Vault."""
        if not self.AZURE_ENABLED:
            return os.getenv(secret_name.upper().replace("-", "_"))
        return azure_config.get_secret(secret_name)
```

### Step 10: Create Sync Service for Files

Create `src/core/azure_storage_sync.py`:

```python
"""
Sync files between local container storage and Azure Blob Storage.
This is a background service that periodically syncs generated files.
"""

import asyncio
import logging
from pathlib import Path
from typing import List

from azure_config import azure_config

logger = logging.getLogger(__name__)


class AzureStorageSync:
    """Handle syncing files to/from Azure Blob Storage."""
    
    CONTAINER_MAPPINGS = {
        "input": "govc-input",
        "output": "govc-output",
        "projects": "govc-projects",
        "generic_info": "govc-generic-info",
    }
    
    @staticmethod
    def upload_file(file_path: Path, storage_type: str) -> bool:
        """Upload a file to Azure Blob Storage."""
        if not azure_config.in_azure:
            return False
        
        try:
            container_name = AzureStorageSync.CONTAINER_MAPPINGS.get(storage_type)
            if not container_name:
                logger.error(f"Unknown storage type: {storage_type}")
                return False
            
            blob_name = str(file_path.relative_to(f"/tmp/govc/{storage_type}"))
            azure_config.upload_file(container_name, blob_name, str(file_path))
            logger.info(f"Uploaded {file_path} to {container_name}/{blob_name}")
            return True
        except Exception as e:
            logger.error(f"Error uploading file {file_path}: {e}")
            return False
    
    @staticmethod
    def upload_directory(directory: Path, storage_type: str) -> int:
        """Upload all files in a directory to Azure Blob Storage."""
        if not azure_config.in_azure:
            return 0
        
        count = 0
        try:
            container_name = AzureStorageSync.CONTAINER_MAPPINGS.get(storage_type)
            if not container_name:
                return 0
            
            container_client = azure_config.get_blob_container_client(container_name)
            
            for file_path in directory.rglob("*"):
                if file_path.is_file():
                    blob_name = str(file_path.relative_to(f"/tmp/govc/{storage_type}"))
                    with open(file_path, "rb") as data:
                        container_client.upload_blob(blob_name, data, overwrite=True)
                    count += 1
            
            logger.info(f"Uploaded {count} files to {container_name}")
            return count
        except Exception as e:
            logger.error(f"Error uploading directory {directory}: {e}")
            return count
    
    @staticmethod
    def download_file(blob_name: str, local_path: Path, storage_type: str) -> bool:
        """Download a file from Azure Blob Storage."""
        if not azure_config.in_azure:
            return False
        
        try:
            container_name = AzureStorageSync.CONTAINER_MAPPINGS.get(storage_type)
            if not container_name:
                return False
            
            azure_config.download_file(container_name, blob_name, str(local_path))
            logger.info(f"Downloaded {blob_name} from {container_name}")
            return True
        except Exception as e:
            logger.error(f"Error downloading file {blob_name}: {e}")
            return False


async def periodic_sync_output(interval_seconds: int = 300):
    """Periodically sync output directory to Azure (every 5 minutes)."""
    from GOVC_config import settings
    
    while True:
        try:
            if settings.AZURE_ENABLED:
                output_dir = settings.GOVC_OUTPUT_DIR
                if output_dir.exists():
                    count = AzureStorageSync.upload_directory(output_dir, "output")
                    logger.info(f"Periodic sync: uploaded {count} files from output")
        except Exception as e:
            logger.error(f"Error in periodic sync: {e}")
        
        await asyncio.sleep(interval_seconds)
```

---

## Phase 4: Configure Container Apps

### Step 11: Update Container App Environment Variables

```powershell
$RESOURCE_GROUP = "govc-advisor-rg"
$KEY_VAULT_NAME = "govc-advisor-kv"
$STORAGE_ACCOUNT_NAME = "gocvadvisorstorage"

# Update API Container App
az containerapp update `
  --name govc-api `
  --resource-group $RESOURCE_GROUP `
  --set-env-vars `
    IN_DOCKER=true `
    KEY_VAULT_NAME=$KEY_VAULT_NAME `
    STORAGE_ACCOUNT_NAME=$STORAGE_ACCOUNT_NAME `
    AZURE_ENABLED=true `
    PYTHONUNBUFFERED=1 `
    PYTHONDONTWRITEBYTECODE=1 `
    MPLBACKEND=Agg `
    QT_QPA_PLATFORM=offscreen

# Update UI Container App (same variables)
az containerapp update `
  --name govc-ui `
  --resource-group $RESOURCE_GROUP `
  --set-env-vars `
    IN_DOCKER=true `
    KEY_VAULT_NAME=$KEY_VAULT_NAME `
    STORAGE_ACCOUNT_NAME=$STORAGE_ACCOUNT_NAME `
    AZURE_ENABLED=true `
    PYTHONUNBUFFERED=1 `
    PYTHONDONTWRITEBYTECODE=1 `
    STREAMLIT_SERVER_PORT=8507 `
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 `
    STREAMLIT_SERVER_HEADLESS=true
```

### Step 12: Update Dockerfile to Install Azure SDK

Modify `docker/requirements-base.txt`:

```
# ... existing requirements ...

# Azure Cloud Storage
azure-identity>=1.14.0
azure-storage-blob>=12.18.0
azure-keyvault-secrets>=4.7.0
```

### Step 13: Update Dockerfile Entry Point

Modify `docker/Dockerfile.api`:

```dockerfile
# Before the CMD line, ensure environment is set for Azure access
ENV AZURE_USE_MANAGED_IDENTITY=true
ENV AZURE_AUTHORITY_HOST=https://login.microsoftonline.com

# Run with startup script that initializes Azure connection
CMD ["python", "backend/startup.py", "&&", "uvicorn", "backend.auth_supabase:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

Create `backend/startup.py`:

```python
"""
Startup script that initializes Azure connections and creates required directories.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

if os.getenv("AZURE_ENABLED") == "true":
    logger.info("Initializing Azure storage connections...")
    
    try:
        from src.core.azure_config import azure_config
        from src.core.GOVC_config import settings
        
        # Verify Key Vault connection
        test_secret = azure_config.get_secret("supabase-url")
        if test_secret:
            logger.info("✅ Key Vault connection successful")
        
        # Create temporary local directories for caching
        for subdir in ["input", "output", "projects", "generic_info"]:
            dir_path = Path(f"/tmp/govc/{subdir}")
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"✅ Created directory: {dir_path}")
        
        logger.info("✅ Azure initialization complete")
    except Exception as e:
        logger.error(f"❌ Azure initialization failed: {e}")
        raise
else:
    logger.info("Running in local mode (AZURE_ENABLED=false)")
```

---

## Phase 5: Update GitHub Actions

### Step 14: Update GitHub Actions Workflow

Update `.github/workflows/build-and-deploy.yml`:

```yaml
# After Azure Login step, add:

      - name: Update Key Vault secrets (production only)
        if: github.ref == 'refs/heads/main' && github.event_name == 'push'
        run: |
          KEY_VAULT_NAME="govc-advisor-kv"
          
          # Secrets are already in Key Vault, this just logs them
          echo "Key Vault: $KEY_VAULT_NAME"
          echo "Update secrets manually via Azure Portal or:"
          echo "az keyvault secret set --name secret-name --vault-name $KEY_VAULT_NAME --value your-value"

      - name: Build and push API image
        # ... rest of build step ...
```

### Step 15: Add Secret Rotation Workflow (Optional)

Create `.github/workflows/rotate-secrets.yml`:

```yaml
name: Rotate Azure Secrets

on:
  schedule:
    - cron: '0 0 1 * *'  # First day of month
  workflow_dispatch:

jobs:
  rotate:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Azure Login
        uses: azure/login@v1
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      
      - name: Rotate secrets reminder
        run: |
          echo "⚠️ Time to rotate secrets!"
          echo "1. Update OPENAI_API_KEY in Key Vault"
          echo "2. Update SUPABASE keys if needed"
          echo "3. Verify GitHub Actions secrets are in sync"
          echo ""
          echo "Command to update a secret:"
          echo "az keyvault secret set --name secret-name --vault-name govc-advisor-kv --value new-value"
```

---

## Local Development Workflow

### Step 16: Develop Locally Without Azure

Your local development stays the same:

```powershell
cd C:\Users\alain\CascadeProjects\GOVC-advisor

# .env.local still points to F:\GOVC
# IN_DOCKER=False means Azure is bypassed
# Works with local Supabase, OpenAI, etc.

streamlit run src/ui/app.py
```

### Step 17: Test Azure Configuration Locally (Optional)

To test Azure config locally with real credentials:

```powershell
# In .env.local, add:
IN_DOCKER=true
KEY_VAULT_NAME=govc-advisor-kv
STORAGE_ACCOUNT_NAME=gocvadvisorstorage
AZURE_ENABLED=true

# And authenticate locally:
az login

# Run application:
python -m uvicorn backend.auth_supabase:app --reload
```

---

## Monitoring and Management

### Step 18: Monitor Azure Storage Usage

```powershell
$STORAGE_ACCOUNT_NAME = "gocvadvisorstorage"
$RESOURCE_GROUP = "govc-advisor-rg"

# Get storage account size
az storage account show --name $STORAGE_ACCOUNT_NAME --resource-group $RESOURCE_GROUP --query "storageAccount.properties"

# List all blobs and sizes
az storage blob list `
  --account-name $STORAGE_ACCOUNT_NAME `
  --container-name govc-output `
  --query "[].{name:name, size:properties.contentLength}"

# Get container size
az storage container show-usage `
  --account-name $STORAGE_ACCOUNT_NAME `
  --container-name govc-output
```

### Step 19: Monitor Key Vault Access

```powershell
$KEY_VAULT_NAME = "govc-advisor-kv"
$RESOURCE_GROUP = "govc-advisor-rg"

# List all secrets
az keyvault secret list --vault-name $KEY_VAULT_NAME --query "[].name"

# Check secret properties (last updated, enabled, etc.)
az keyvault secret show --vault-name $KEY_VAULT_NAME --name "supabase-url"

# View access policies
az keyvault show --name $KEY_VAULT_NAME --resource-group $RESOURCE_GROUP --query "properties.accessPolicies"
```

### Step 20: Clean Up Old Files in Blob Storage

```powershell
$STORAGE_ACCOUNT_NAME = "gocvadvisorstorage"

# Delete files older than 30 days (example)
# Note: Blob Storage doesn't have built-in expiration, use lifecycle policies:

# Create a lifecycle policy to auto-delete old blobs
cat > lifecycle-policy.json @"
{
  "rules": [
    {
      "name": "DeleteOldOutput",
      "enabled": true,
      "type": "Lifecycle",
      "definition": {
        "actions": {
          "baseBlob": {
            "delete": {
              "daysAfterModificationGreaterThan": 90
            }
          }
        },
        "filters": {
          "blobTypes": ["blockBlob"],
          "prefixMatch": ["govc-output/"]
        }
      }
    }
  ]
}
"@

az storage account management-policy create `
  --account-name $STORAGE_ACCOUNT_NAME `
  --policy @lifecycle-policy.json `
  --resource-group govc-advisor-rg
```

### Step 21: Set Up Storage Monitoring Alerts

```powershell
$STORAGE_ACCOUNT_NAME = "gocvadvisorstorage"
$RESOURCE_GROUP = "govc-advisor-rg"

# Enable logging
az storage logging update `
  --account-name $STORAGE_ACCOUNT_NAME `
  --services b `
  --log-read --log-write --log-delete `
  --retention 7
```

---

## Cost Optimization Tips

1. **Use Standard Storage Class** - Appropriate for development/testing
2. **Set Blob Lifecycle Policies** - Auto-delete old output files
3. **Monitor Usage** - Check storage size monthly
4. **Archive Old Projects** - Move completed projects to Archive tier
5. **Delete Unused Containers** - Clean up test containers

**Estimated Monthly Costs:**
- Storage (10 GB at Standard): ~$0.50
- Key Vault (10 operations/month): ~$1
- **Total: ~$2-3/month**

---

## Troubleshooting

### Issue: "No credentials provided"

**Cause:** Managed Identity not properly assigned

**Solution:**
```powershell
# Verify identity is assigned
az containerapp show --name govc-api --resource-group govc-advisor-rg --query "identity"

# Reassign if needed
az containerapp identity assign --name govc-api --resource-group govc-advisor-rg --system-assigned
```

### Issue: "Key Vault access denied"

**Cause:** Insufficient RBAC permissions

**Solution:**
```powershell
$API_PRINCIPAL_ID = az containerapp show --name govc-api --resource-group govc-advisor-rg --query "identity.principalId" -o tsv

az keyvault set-policy --name govc-advisor-kv --object-id $API_PRINCIPAL_ID --secret-permissions get list
```

### Issue: "File not found in Blob Storage"

**Cause:** File path mismatch between local and Azure paths

**Solution:**
- Use `AzureStorageSync.upload_file()` to upload with correct paths
- Check Azure Storage Explorer for actual file structure
- Use blob name mappings consistently

### Issue: "Quota exceeded"

**Cause:** Storage account has reached limit

**Solution:**
```powershell
# Upgrade storage account tier or delete old files
az storage account update --name gocvadvisorstorage --resource-group govc-advisor-rg --sku Standard_GRS
```

---

## Summary: Local vs Azure File Handling

| Aspect | Local | Azure |
|--------|-------|-------|
| **Secrets** | `.env.keys` file | Azure Key Vault |
| **File Storage** | `F:\GOVC` (Windows) | Azure Blob Storage |
| **Configuration** | `.env.local` | Environment variables + Key Vault |
| **File Persistence** | ✅ Persistent | ✅