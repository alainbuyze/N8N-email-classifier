# Azure Deployment Guide

This guide walks you through deploying the Outlook Email Categorizer to Azure Container Apps with automated builds and secure secret management.

## Architecture

### Component Overview

- **Azure Container Registry (ACR)**: Stores Docker images
- **Azure Container Apps**: Runs the web application
- **Azure Key Vault**: Securely stores secrets (.env variables)
- **GitHub Actions**: Automated CI/CD pipeline
- **Managed Identity**: Secure access from Container App to Key Vault

### Azure Components Dependency Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Azure Subscription                             │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                    Resource Group                                 │ │
│  │                 (outlook-categorizer-rg)                          │ │
│  │                                                                   │ │
│  │  ┌──────────────────────┐         ┌─────────────────────────┐   │ │
│  │  │  Container Apps Env  │         │   Azure Key Vault       │   │ │
│  │  │  (managed env)       │         │   (secrets storage)     │   │ │
│  │  │                      │         │                         │   │ │
│  │  │  ┌────────────────┐  │         │  • GROQ_API_KEY        │   │ │
│  │  │  │ Container App  │  │         │  • AZURE_TENANT_ID     │   │ │
│  │  │  │ (your app)     │◄─┼─────────┤  • AZURE_CLIENT_ID     │   │ │
│  │  │  │                │  │  reads  │  • AZURE_CLIENT_SECRET │   │ │
│  │  │  │ • Port: 8000   │  │ secrets │                         │   │ │
│  │  │  │ • Scale: 0-3   │  │    via  │  Access via:            │   │ │
│  │  │  │ • CPU: 1.0     │  │ Managed │  • RBAC Role Assignment │   │ │
│  │  │  │ • Memory: 2GB  │  │ Identity│    (Key Vault Secrets   │   │ │
│  │  │  │                │  │    │    │     User)               │   │ │
│  │  │  └────────┬───────┘  │    │    └─────────────────────────┘   │ │
│  │  │           │          │    │                                   │ │
│  │  │           │pulls     │    │                                   │ │
│  │  │           │image     │    │                                   │ │
│  │  │           ▼          │    │                                   │ │
│  │  └───────────┼──────────┘    │                                   │ │
│  │              │               │                                   │ │
│  │  ┌───────────▼──────────┐    │                                   │ │
│  │  │ Container Registry   │    │                                   │ │
│  │  │ (ACR)                │    │                                   │ │
│  │  │                      │    │                                   │ │
│  │  │ • Stores Docker      │    │                                   │ │
│  │  │   images             │    │                                   │ │
│  │  │ • Basic tier         │    │                                   │ │
│  │  │ • Admin enabled      │    │                                   │ │
│  │  │                      │    │                                   │ │
│  │  │ Images:              │    │                                   │ │
│  │  │ • outlook-           │    │                                   │ │
│  │  │   categorizer:latest │    │                                   │ │
│  │  │ • outlook-           │    │                                   │ │
│  │  │   categorizer:sha    │    │                                   │ │
│  │  └──────────▲───────────┘    │                                   │ │
│  │             │                │                                   │ │
│  └─────────────┼────────────────┼───────────────────────────────────┘ │
│                │                │                                     │
│                │ pushes         │ manages                             │
│                │ image          │ secrets                             │
└────────────────┼────────────────┼─────────────────────────────────────┘
                 │                │
                 │                │
        ┌────────┴────────┐       │
        │                 │       │
        │  GitHub Actions │       │
        │  (CI/CD)        │       │
        │                 │       │
        │  Workflow:      │       │
        │  1. Build image │       │
        │  2. Push to ACR │───────┘
        │  3. Deploy to   │
        │     Container   │
        │     Apps        │
        │                 │
        │  Secrets:       │
        │  • AZURE_       │
        │    CREDENTIALS  │
        │  • ACR_USERNAME │
        │  • ACR_PASSWORD │
        └─────────────────┘
                │
                │ triggered by
                │ git push
                │
        ┌───────▼─────────┐
        │                 │
        │  GitHub Repo    │
        │  (source code)  │
        │                 │
        │  • Dockerfile   │
        │  • App code     │
        │  • Workflow     │
        │    (.yml)       │
        └─────────────────┘
```

### Data Flow

1. **Developer pushes code** → GitHub repository
2. **GitHub Actions triggered** → Builds Docker image
3. **Image pushed** → Azure Container Registry (ACR)
4. **Container App updated** → Pulls new image from ACR
5. **Container App starts** → Reads secrets from Key Vault via Managed Identity
6. **User accesses app** → Container scales up from 0 to 1 replica
7. **App authenticates** → Uses secrets to connect to Microsoft Graph API
8. **Emails processed** → AI categorization via Groq API

### Security Model

- **Managed Identity**: Container App uses system-assigned managed identity (no passwords needed)
- **RBAC**: Key Vault access controlled via role assignments (Key Vault Secrets User)
- **GitHub Secrets**: Encrypted secrets for CI/CD pipeline
- **Key Vault**: Centralized secret storage with audit logging
- **No hardcoded secrets**: All credentials stored securely in Key Vault

## Prerequisites

- Azure CLI installed: `az --version`
- Azure subscription
- GitHub repository with admin access

## Step 1: Create Azure Resources

### 1.1 Login to Azure

```bash
az login
az account set --subscription "<your-subscription-id>"
```

### 1.2 Register Required Resource Providers

New Azure subscriptions need to register resource providers before first use. This is a one-time setup.

**PowerShell:**

```powershell
# Register all required providers
az provider register --namespace Microsoft.KeyVault
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

# Wait for registration to complete (takes ~1-2 minutes)
# Check status - should return "Registered" for each
az provider show --namespace Microsoft.KeyVault --query "registrationState"
az provider show --namespace Microsoft.ContainerRegistry --query "registrationState"
az provider show --namespace Microsoft.App --query "registrationState"
az provider show --namespace Microsoft.OperationalInsights --query "registrationState"
```

**Bash:**

```bash
# Register all required providers
az provider register --namespace Microsoft.KeyVault
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

# Wait for registration to complete (takes ~1-2 minutes)
# Check status - should return "Registered" for each
az provider show --namespace Microsoft.KeyVault --query "registrationState"
az provider show --namespace Microsoft.ContainerRegistry --query "registrationState"
az provider show --namespace Microsoft.App --query "registrationState"
az provider show --namespace Microsoft.OperationalInsights --query "registrationState"
```

**Note**: Wait until all providers show `"Registered"` before proceeding to the next step.

### 1.3 Set Variables

**For PowerShell (Windows):**

```powershell
$RESOURCE_GROUP="outlook-categorizer-rg"
$LOCATION="westeurope"
$ACR_NAME="your-unique-acr-name"        # Must be globally unique, lowercase, no hyphens - CHANGE THIS
$KEYVAULT_NAME="your-unique-kv-name"    # Must be globally unique - CHANGE THIS
$CONTAINER_APP_NAME="outlook-categorizer"
$CONTAINER_APP_ENV="outlook-categorizer-env"
```

**For Bash (Linux/Mac):**

```bash
RESOURCE_GROUP="outlook-categorizer-rg"
LOCATION="westeurope"
ACR_NAME="your-unique-acr-name"        # Must be globally unique, lowercase, no hyphens - CHANGE THIS
KEYVAULT_NAME="your-unique-kv-name"    # Must be globally unique - CHANGE THIS
CONTAINER_APP_NAME="outlook-categorizer"
CONTAINER_APP_ENV="outlook-categorizer-env"
```

**Important**: `ACR_NAME` and `KEYVAULT_NAME` must be globally unique across all Azure users. Replace the example values with your own unique names (e.g., add your initials, numbers, or company name).

**Check if names are available:**

```powershell
# PowerShell
az acr check-name --name $ACR_NAME
```

```bash
# Bash
az acr check-name --name $ACR_NAME
```

If the name is already taken, modify `$ACR_NAME` or `$KEYVAULT_NAME` and check again.

### 1.3 Create Resource Group

**PowerShell:**

```powershell
az group create `
  --name $RESOURCE_GROUP `
  --location $LOCATION
```

**Bash:**

```bash
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION
```

### 1.4 Create Azure Container Registry

**PowerShell:**

```powershell
az acr create `
  --resource-group $RESOURCE_GROUP `
  --name $ACR_NAME `
  --sku Basic `
  --admin-enabled true
```

**Bash:**

```bash
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true
```

Get ACR credentials (save these for GitHub secrets):

```powershell
# PowerShell or Bash (same command)
az acr credential show --name $ACR_NAME
```

### 1.5 Create Azure Key Vault

**PowerShell:**

```powershell
az keyvault create `
  --name $KEYVAULT_NAME `
  --resource-group $RESOURCE_GROUP `
  --location $LOCATION
```

**Bash:**

```bash
az keyvault create \
  --name $KEYVAULT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION
```

### 1.6 Grant Yourself Key Vault Access

Before adding secrets, you need to grant yourself permission to manage secrets in the Key Vault.

First, get your subscription ID:

**PowerShell:**
```powershell
$SUBSCRIPTION_ID = az account show --query id -o tsv
```

**Bash:**
```bash
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
```

Then assign yourself the "Key Vault Secrets Officer" role:

**PowerShell:**

```powershell
az role assignment create `
  --role "Key Vault Secrets Officer" `
  --assignee (az ad signed-in-user show --query id -o tsv) `
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$KEYVAULT_NAME"
```

**Bash:**

```bash
az role assignment create \
  --role "Key Vault Secrets Officer" \
  --assignee $(az ad signed-in-user show --query id -o tsv) \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$KEYVAULT_NAME"
```

**Note**: RBAC role assignments can take 1-2 minutes to propagate. Wait a moment before adding secrets.

### 1.7 Add Secrets to Key Vault

Before running these commands, you need to gather the required values:

#### Required Secrets

1. **GROQ-API-KEY**: Your Groq API key
   - Get it from: https://console.groq.com/keys
   - Click "Create API Key" if you don't have one
   - Copy the key (starts with `gsk_...`)

2. **AZURE-TENANT-ID**: Your Azure AD tenant ID
   - Get it from your `.env` file, OR
   - Run: `az account show --query tenantId -o tsv`

3. **AZURE-CLIENT-ID**: Your Azure AD application (client) ID
   - Get it from your `.env` file, OR
   - Azure Portal → Azure Active Directory → App registrations → Your app → Application (client) ID

4. **AZURE-CLIENT-SECRET**: Your Azure AD application client secret
   - Get it from your `.env` file, OR
   - Azure Portal → Azure Active Directory → App registrations → Your app → Certificates & secrets → Client secrets
   - If you don't have one, create a new client secret

#### Add Secrets to Key Vault

**PowerShell:**

```powershell
# Replace with your actual values
az keyvault secret set --vault-name $KEYVAULT_NAME --name "GROQ-API-KEY" --value "your-groq-api-key"
az keyvault secret set --vault-name $KEYVAULT_NAME --name "AZURE-TENANT-ID" --value "your-tenant-id"
az keyvault secret set --vault-name $KEYVAULT_NAME --name "AZURE-CLIENT-ID" --value "your-client-id"
az keyvault secret set --vault-name $KEYVAULT_NAME --name "AZURE-CLIENT-SECRET" --value "your-client-secret"
```

**Bash:**

```bash
# Replace with your actual values
az keyvault secret set --vault-name $KEYVAULT_NAME --name "GROQ-API-KEY" --value "your-groq-api-key"
az keyvault secret set --vault-name $KEYVAULT_NAME --name "AZURE-TENANT-ID" --value "your-tenant-id"
az keyvault secret set --vault-name $KEYVAULT_NAME --name "AZURE-CLIENT-ID" --value "your-client-id"
az keyvault secret set --vault-name $KEYVAULT_NAME --name "AZURE-CLIENT-SECRET" --value "your-client-secret"
```

**Quick way to get values from your local `.env` file:**

If you have a working local `.env` file, you can read the values from it:

**PowerShell:**
```powershell
# Navigate to your project directory
cd "path\to\your\project"

# Read from .env file
Get-Content .env | Select-String "GROQ_API_KEY|AZURE_TENANT_ID|AZURE_CLIENT_ID|AZURE_CLIENT_SECRET"

# Or set them as variables for easy copy-paste
$GROQ_KEY = (Get-Content .env | Select-String "GROQ_API_KEY=" | ForEach-Object { $_ -replace "GROQ_API_KEY=", "" }).Trim()
$TENANT_ID = (Get-Content .env | Select-String "AZURE_TENANT_ID=" | ForEach-Object { $_ -replace "AZURE_TENANT_ID=", "" }).Trim()
$CLIENT_ID = (Get-Content .env | Select-String "AZURE_CLIENT_ID=" | ForEach-Object { $_ -replace "AZURE_CLIENT_ID=", "" }).Trim()
$CLIENT_SECRET = (Get-Content .env | Select-String "AZURE_CLIENT_SECRET=" | ForEach-Object { $_ -replace "AZURE_CLIENT_SECRET=", "" }).Trim()

# Then use them directly
az keyvault secret set --vault-name $KEYVAULT_NAME --name "GROQ-API-KEY" --value $GROQ_KEY
az keyvault secret set --vault-name $KEYVAULT_NAME --name "AZURE-TENANT-ID" --value $TENANT_ID
az keyvault secret set --vault-name $KEYVAULT_NAME --name "AZURE-CLIENT-ID" --value $CLIENT_ID
az keyvault secret set --vault-name $KEYVAULT_NAME --name "AZURE-CLIENT-SECRET" --value $CLIENT_SECRET
```

**Bash:**
```bash
# Navigate to your project directory
cd "path/to/your/project"

# Read from .env file
grep -E "GROQ_API_KEY|AZURE_TENANT_ID|AZURE_CLIENT_ID|AZURE_CLIENT_SECRET" .env

# Or set them as variables for easy copy-paste
export GROQ_KEY=$(grep "GROQ_API_KEY=" .env | cut -d '=' -f2)
export TENANT_ID=$(grep "AZURE_TENANT_ID=" .env | cut -d '=' -f2)
export CLIENT_ID=$(grep "AZURE_CLIENT_ID=" .env | cut -d '=' -f2)
export CLIENT_SECRET=$(grep "AZURE_CLIENT_SECRET=" .env | cut -d '=' -f2)

# Then use them directly
az keyvault secret set --vault-name $KEYVAULT_NAME --name "GROQ-API-KEY" --value "$GROQ_KEY"
az keyvault secret set --vault-name $KEYVAULT_NAME --name "AZURE-TENANT-ID" --value "$TENANT_ID"
az keyvault secret set --vault-name $KEYVAULT_NAME --name "AZURE-CLIENT-ID" --value "$CLIENT_ID"
az keyvault secret set --vault-name $KEYVAULT_NAME --name "AZURE-CLIENT-SECRET" --value "$CLIENT_SECRET"
```

This will automatically extract the values from your `.env` file and add them to Key Vault.

### 1.7 Create Container Apps Environment

**PowerShell:**

```powershell
az containerapp env create `
  --name $CONTAINER_APP_ENV `
  --resource-group $RESOURCE_GROUP `
  --location $LOCATION
```

**Bash:**

```bash
az containerapp env create \
  --name $CONTAINER_APP_ENV \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION
```

### 1.8 Create Container App with Managed Identity

**Note**: The `mcr.microsoft.com/azuredocs/containerapps-helloworld:latest` image is a temporary placeholder. It's a simple "Hello World" demo app from Microsoft used to bootstrap the Container App. When you deploy via GitHub Actions (Step 3), your actual Outlook Email Categorizer Docker image will automatically replace this placeholder.

**PowerShell:**

```powershell
# Create the container app with scale-to-zero for cost optimization
# Using a placeholder image that will be replaced by GitHub Actions deployment
az containerapp create `
  --name $CONTAINER_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --environment $CONTAINER_APP_ENV `
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest `
  --target-port 8000 `
  --ingress external `
  --cpu 1.0 `
  --memory 2.0Gi `
  --min-replicas 0 `
  --max-replicas 3 `
  --system-assigned

# Note: --min-replicas 0 enables scale-to-zero for cost savings (~$5-8/month vs $20-25/month)
# This adds a 2-3 second cold start when accessing the app after idle periods
# To keep 1 replica always running, change --min-replicas to 1

# Get the managed identity principal ID
$IDENTITY_ID = az containerapp show `
  --name $CONTAINER_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --query identity.principalId -o tsv

# Grant Key Vault access to the managed identity using RBAC
az role assignment create `
  --role "Key Vault Secrets User" `
  --assignee $IDENTITY_ID `
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$KEYVAULT_NAME"
```

**Bash:**

```bash
# Create the container app with scale-to-zero for cost optimization
az containerapp create \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --environment $CONTAINER_APP_ENV \
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
  --target-port 8000 \
  --ingress external \
  --cpu 1.0 \
  --memory 2.0Gi \
  --min-replicas 0 \
  --max-replicas 3 \
  --system-assigned

# Get the managed identity principal ID
IDENTITY_ID=$(az containerapp show \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query identity.principalId -o tsv)

# Grant Key Vault access to the managed identity using RBAC
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee $IDENTITY_ID \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$KEYVAULT_NAME"
```

### 1.8.1 Configure Container App to pull images from ACR

Container Apps must authenticate to your ACR to pull private images. If you enabled ACR admin user, you can configure the Container App registry credentials directly:

**PowerShell:**

```powershell
# Configure ACR pull credentials (uses ACR admin user)
$ACR_LOGIN_SERVER = "$ACR_NAME.azurecr.io"
$ACR_USERNAME = $ACR_NAME
$ACR_PASSWORD = (az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

az containerapp registry set `
  --name $CONTAINER_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --server $ACR_LOGIN_SERVER `
  --username $ACR_USERNAME `
  --password $ACR_PASSWORD
```

**Bash:**

```bash
# Configure ACR pull credentials (uses ACR admin user)
ACR_LOGIN_SERVER="$ACR_NAME.azurecr.io"
ACR_USERNAME=$ACR_NAME
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

az containerapp registry set \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --server $ACR_LOGIN_SERVER \
  --username $ACR_USERNAME \
  --password $ACR_PASSWORD
```

**Note**: Without this step you may see `ImagePullUnauthorized` events.

### 1.9 Configure Secrets in Container App

**PowerShell:**

```powershell
# Link Key Vault secrets to Container App
az containerapp secret set `
  --name $CONTAINER_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --secrets `
    groq-api-key=keyvaultref:https://$KEYVAULT_NAME.vault.azure.net/secrets/GROQ-API-KEY,identityref:system `
    azure-tenant-id=keyvaultref:https://$KEYVAULT_NAME.vault.azure.net/secrets/AZURE-TENANT-ID,identityref:system `
    azure-client-id=keyvaultref:https://$KEYVAULT_NAME.vault.azure.net/secrets/AZURE-CLIENT-ID,identityref:system `
    azure-client-secret=keyvaultref:https://$KEYVAULT_NAME.vault.azure.net/secrets/AZURE-CLIENT-SECRET,identityref:system

# Set environment variables from secrets
az containerapp update `
  --name $CONTAINER_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --set-env-vars `
    GROQ_API_KEY=secretref:groq-api-key `
    AZURE_TENANT_ID=secretref:azure-tenant-id `
    AZURE_CLIENT_ID=secretref:azure-client-id `
    AZURE_CLIENT_SECRET=secretref:azure-client-secret
```

**Bash:**

```bash
# Link Key Vault secrets to Container App
az containerapp secret set \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --secrets \
    groq-api-key=keyvaultref:https://${KEYVAULT_NAME}.vault.azure.net/secrets/GROQ-API-KEY,identityref:system \
    azure-tenant-id=keyvaultref:https://${KEYVAULT_NAME}.vault.azure.net/secrets/AZURE-TENANT-ID,identityref:system \
    azure-client-id=keyvaultref:https://${KEYVAULT_NAME}.vault.azure.net/secrets/AZURE-CLIENT-ID,identityref:system \
    azure-client-secret=keyvaultref:https://${KEYVAULT_NAME}.vault.azure.net/secrets/AZURE-CLIENT-SECRET,identityref:system

# Set environment variables from secrets
az containerapp update \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --set-env-vars \
    GROQ_API_KEY=secretref:groq-api-key \
    AZURE_TENANT_ID=secretref:azure-tenant-id \
    AZURE_CLIENT_ID=secretref:azure-client-id \
    AZURE_CLIENT_SECRET=secretref:azure-client-secret
```

## Important notes (learned during real deployment)

- **ACR image pulls require auth**
  The Container App must be able to pull from your private ACR. If this is not configured, you will see system events like:
  - `ImagePullUnauthorized`
  - `ImagePullFailure`
  and the public URL may show `404 - This Container App is stopped or does not exist`.

- **Scale-to-zero can hide startup issues**
  With `minReplicas: 0`, the app may remain at 0 replicas unless traffic arrives, and it can be harder to capture startup logs. For debugging, temporarily set `minReplicas: 1`.

- **Personal Microsoft accounts (`AZURE_TENANT_ID=consumers`) cannot use client credentials flow**
  Device code flow requires user interaction. For Azure, use **Option A** (persist token cache on a mounted volume) if you want to keep using a personal account.

## Step 2: Configure GitHub Actions

### 2.1 Create Service Principal for GitHub

**PowerShell:**

```powershell
az ad sp create-for-rbac `
  --name "github-actions-outlook-categorizer" `
  --role contributor `
  --scopes /subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP `
  --sdk-auth
```

**Bash:**

```bash
az ad sp create-for-rbac \
  --name "github-actions-outlook-categorizer" \
  --role contributor \
  --scopes /subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP \
  --sdk-auth
```

**Save the entire JSON output** - you'll need it for GitHub secrets.

### 2.2 Add GitHub Secrets

Go to your GitHub repository → Settings → Secrets and variables → Actions → New repository secret

Add these secrets:

1. **AZURE_CREDENTIALS**: The full JSON output from step 2.1
2. **AZURE_ACR_USERNAME**: The username from `az acr credential show --name $ACR_NAME`
3. **AZURE_ACR_PASSWORD**: The password from `az acr credential show --name $ACR_NAME`

### 2.3 Update GitHub Workflow

Edit `.github/workflows/azure-deploy.yml` and replace the placeholders:

```yaml
env:
  AZURE_CONTAINER_REGISTRY: your-acr-name  # Replace with your ACR name
  AZURE_CONTAINER_APP: outlook-categorizer
  AZURE_RESOURCE_GROUP: outlook-categorizer-rg
```

## Step 3: Deploy

### 3.1 Push to GitHub

```bash
git add .github/workflows/azure-deploy.yml
git commit -m "Add Azure deployment configuration"
git push origin main
```

GitHub Actions will automatically:
1. Build the Docker image
2. Push to Azure Container Registry
3. Deploy to Azure Container Apps

### 3.2 Monitor Deployment

- Go to GitHub → Actions tab to watch the workflow
- Check Azure Portal → Container Apps → your app → Logs

### 3.2.1 Verify image exists in ACR

**PowerShell:**

```powershell
az acr repository list --name $ACR_NAME -o table
az acr repository show-tags --name $ACR_NAME --repository outlook-categorizer --output table
```

If `show-tags` fails with `repository not found`, your GitHub Actions run likely did not push the image.

### 3.3 Access Your App

```bash
# Get the app URL
az containerapp show \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn -o tsv
```

Visit `https://<your-app-url>` to access the web UI.

## Step 4: Update Secrets (When Needed)

To update a secret (e.g., rotate API key):

```bash
# Update in Key Vault
az keyvault secret set --vault-name $KEYVAULT_NAME --name "GROQ-API-KEY" --value "new-api-key"

# Restart the container app to pick up the new secret
az containerapp revision restart \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP
```

## Monitoring and Logs

### View Live Logs

```bash
az containerapp logs show \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --follow
```

### View Metrics

```bash
az monitor metrics list \
  --resource /subscriptions/<subscription-id>/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.App/containerApps/$CONTAINER_APP_NAME \
  --metric "Requests"
```

## Cost Optimization

### Current Configuration (Scale-to-Zero)

With the default `--min-replicas 0` configuration:

- **Container Apps**: ~$2-5/month (only charged when running)
- **ACR Basic**: ~$5/month
- **Key Vault**: ~$0.03 per 10,000 operations (~$0.03/month)
- **Bandwidth**: ~$0.40/month
- **Total estimated cost**: **$5-8/month**

**Tradeoff**: 2-3 second cold start when accessing the app after idle periods.

### Alternative: Always-On Configuration

To keep 1 replica always running (no cold starts):

```bash
az containerapp update \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --min-replicas 1 \
  --max-replicas 3
```

**Cost**: ~$20-25/month (1 vCPU + 2 GB RAM running 24/7)

### Cost Breakdown by Resource

| Resource | Configuration | Monthly Cost |
|----------|--------------|--------------|
| Container Apps (scale-to-zero) | 0-3 replicas, 1 vCPU, 2 GB | $2-5 |
| Container Apps (always-on) | 1-3 replicas, 1 vCPU, 2 GB | $17-25 |
| Azure Container Registry | Basic tier, 10 GB storage | $5 |
| Azure Key Vault | Standard, ~1K operations | $0.03 |
| Bandwidth | ~5 GB outbound | $0.40 |

### Additional Cost Savings

- **Smaller resources**: Use `--cpu 0.5 --memory 1.0Gi` for ~50% savings (slower processing)
- **ACR Basic tier**: Already configured (cheapest option)
- **Scheduled processing**: Use Azure Functions with Timer Trigger instead (~$5/month, no web UI)

## Troubleshooting

### Container app won't start

```bash
# Check logs
az containerapp logs show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP --tail 100

# Check revision status
az containerapp revision list --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP -o table
```

### The app URL returns `404 - stopped or does not exist`

This often means **no healthy replicas are running**. Common causes:

- **Image pull auth failure**
  Check system logs for:
  - `ImagePullUnauthorized`
  - `ImagePullFailure`

  ```powershell
  az containerapp logs show `
    --name $CONTAINER_APP_NAME `
    --resource-group $RESOURCE_GROUP `
    --type system `
    --tail 200
  ```

- **Scale-to-zero + no traffic**
  For debugging, force a replica:

  ```powershell
  az containerapp update `
    --name $CONTAINER_APP_NAME `
    --resource-group $RESOURCE_GROUP `
    --min-replicas 1 `
    --max-replicas 3
  ```

### App page loads but stays on “Processing…” for a long time

This can happen if the app is waiting for device-code authentication.

```powershell
az containerapp logs show `
  --name $CONTAINER_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --follow
```

If you see:
`To sign in, use a web browser to open the page https://www.microsoft.com/link and enter the code ...`
then the container is blocked on interactive login.

## Option A (recommended for personal Microsoft accounts): Persist the MSAL token cache in Azure Blob Storage (ETag-safe)

If you use `AZURE_TENANT_ID=consumers`, you must use delegated/device-code flow. In Azure Container Apps, the container filesystem is ephemeral, so you need persistent storage for the MSAL token cache.

This project supports persisting the MSAL cache JSON in **Azure Blob Storage** using **ETag-based optimistic concurrency** (safe when multiple replicas exist).

### 1) Create Storage Account + Container

**PowerShell:**

```powershell
$STORAGE_ACCOUNT_NAME = "outlookclassifierstore"  # e.g. outlookcattokencache01
$BLOB_CONTAINER_NAME = "token-cache"

az storage account create `
  --name $STORAGE_ACCOUNT_NAME `
  --resource-group $RESOURCE_GROUP `
  --location $LOCATION `
  --sku Standard_LRS `
  --kind StorageV2

az storage container create `
  --name $BLOB_CONTAINER_NAME `
  --account-name $STORAGE_ACCOUNT_NAME `
  --auth-mode login
```

### 2) Grant Container App managed identity access to the container

Get the Container App principal id:

```powershell
$IDENTITY_ID = az containerapp show `
  --name $CONTAINER_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --query identity.principalId -o tsv
```

Assign RBAC on the storage account scope:

```powershell
$SUBSCRIPTION_ID = az account show --query id -o tsv
$STORAGE_SCOPE = "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/$STORAGE_ACCOUNT_NAME"

az role assignment create `
  --assignee $IDENTITY_ID `
  --role "Storage Blob Data Contributor" `
  --scope $STORAGE_SCOPE
```

### 3) Configure Container App environment variables

Set these env vars (no secrets required for blob when using Managed Identity):

```powershell
$ACCOUNT_URL = "https://$STORAGE_ACCOUNT_NAME.blob.core.windows.net"

az containerapp update `
  --name $CONTAINER_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --set-env-vars `
    TOKEN_CACHE_BACKEND=azure_blob `
    TOKEN_CACHE_BLOB_ACCOUNT_URL=$ACCOUNT_URL `
    TOKEN_CACHE_BLOB_CONTAINER=$BLOB_CONTAINER_NAME `
    TOKEN_CACHE_BLOB_NAME=msal_token_cache.json
```

### 4) Authenticate once (device code)

After redeploy/restart, tail logs and complete the device-code sign-in once:

```powershell
az containerapp logs show `
  --name $CONTAINER_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --follow
```

The token cache will be saved to Blob and reused across restarts.

### Cost note

Azure Blob Storage has **recurring costs** (storage + transactions). For this use case the blob is tiny (KBs), so costs are typically low. Use **Standard_LRS** for the lowest cost.

### Secrets not loading

```bash
# Verify Key Vault access
az keyvault secret show --vault-name $KEYVAULT_NAME --name "GROQ-API-KEY"

# Check managed identity has permissions
az role assignment list --scope /subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$KEYVAULT_NAME
```

### GitHub Actions failing

- Check GitHub Actions logs for specific errors
- Verify all GitHub secrets are set correctly
- Ensure service principal has contributor role

## Cleanup (Delete All Resources)

```bash
az group delete --name $RESOURCE_GROUP --yes --no-wait
```

## Next Steps

- Set up **Application Insights** for detailed monitoring
- Configure **custom domain** and SSL certificate
- Set up **staging slots** for zero-downtime deployments
- Enable **auto-scaling rules** based on HTTP requests
