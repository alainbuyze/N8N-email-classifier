# Deploying GOVC-Advisor to Azure Container Apps

Complete guide for deploying your GOVC-advisor application (Streamlit UI + FastAPI backend) to Azure at minimal cost using Container Apps and Azure Container Registry.

**Architecture:**
- Streamlit UI (Port 8507)
- FastAPI Backend (Port 8000)
- Supabase PostgreSQL (external)
- Azure Container Registry (for image storage)
- Azure Container Apps (hosting)

**Estimated Monthly Cost:** $0-10 (within free tier + minimal overages)

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Phase 1: Azure Setup](#phase-1-azure-setup)
3. [Phase 2: Build and Push Container Images](#phase-2-build-and-push-container-images)
4. [Phase 3: Deploy to Azure Container Apps](#phase-3-deploy-to-azure-container-apps)
5. [Phase 4: Configure Custom Domain (Optional)](#phase-4-configure-custom-domain-optional)
6. [Phase 5: Testing and Verification](#phase-5-testing-and-verification)
7. [Monitoring and Maintenance](#monitoring-and-maintenance)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Azure account with subscription
- Azure CLI installed
- Docker Desktop installed
- Git with your repository access
- Environment variables ready:
  - `SUPABASE_URL`
  - `SUPABASE_KEY`
  - `SUPABASE_SERVICE_KEY`
  - `OPENAI_API_KEY`
  - `JWT_SECRET`

---

## Phase 1: Azure Setup

### Step 1: Login to Azure

```powershell
az login
az account show
```

### Step 2: Create Resource Group

```powershell
$RESOURCE_GROUP = "govc-advisor-rg"
$LOCATION = "eastus"

az group create --name $RESOURCE_GROUP --location $LOCATION
```

### Step 3: Create Azure Container Registry (ACR)

```powershell
$ACR_NAME = "gocvadvisoracr"  # Must be lowercase, no hyphens
$RESOURCE_GROUP = "govc-advisor-rg"

az acr create `
  --resource-group $RESOURCE_GROUP `
  --name $ACR_NAME `
  --sku Basic
```

Get your registry URL:

```powershell
$ACR_URL = az acr show --name $ACR_NAME --resource-group $RESOURCE_GROUP --query "loginServer" -o tsv
Write-Host "ACR URL: $ACR_URL"
```

### Step 4: Enable Admin Access to ACR

```powershell
az acr update --name $ACR_NAME --admin-enabled true
```

Get credentials:

```powershell
$ACR_CREDS = az acr credential show --name $ACR_NAME --resource-group $RESOURCE_GROUP
Write-Host $ACR_CREDS | ConvertFrom-Json | Format-Table
```

Save the username and password for later.

### Step 5: Create Container Apps Environment

```powershell
# Register providers first
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

# Wait for registration...
Start-Sleep -Seconds 30

# Create environment
az containerapp env create `
  --name govc-env `
  --resource-group $RESOURCE_GROUP `
  --location $LOCATION
```

---

## Phase 2: Build and Push Container Images

### Step 6: Clone and Navigate to Repository

```powershell
cd C:\Users\alain\CascadeProjects\GOVC-advisor
```

### Step 7: Build Docker Images

```powershell
$ACR_URL = "gocvadvisoracr.azurecr.io"  # Your ACR URL
$RESOURCE_GROUP = "govc-advisor-rg"
$ACR_NAME = "gocvadvisoracr"

# Login to ACR
az acr login --name $ACR_NAME

# Build and push UI image
az acr build `
  --registry $ACR_NAME `
  --file docker/Dockerfile.ui `
  --image govc-ui:latest `
  .

# Build and push API image
az acr build `
  --registry $ACR_NAME `
  --file docker/Dockerfile.api `
  --image govc-api:latest `
  .
```

This may take 10-15 minutes. Monitor progress:

```powershell
# Check image status
az acr repository list --name $ACR_NAME

# View image details
az acr repository show --name $ACR_NAME --image govc-ui:latest
az acr repository show --name $ACR_NAME --image govc-api:latest
```

### Step 8: Create ACR Access Token

```powershell
$ACR_NAME = "gocvadvisoracr"
$RESOURCE_GROUP = "govc-advisor-rg"

# Get ACR credentials
$ACR_ADMIN_USER = az acr credential show --name $ACR_NAME --resource-group $RESOURCE_GROUP --query "username" -o tsv
$ACR_ADMIN_PASSWORD = az acr credential show --name $ACR_NAME --resource-group $RESOURCE_GROUP --query "passwords[0].value" -o tsv

Write-Host "ACR Admin User: $ACR_ADMIN_USER"
Write-Host "ACR Admin Password: $ACR_ADMIN_PASSWORD"
```

Save these credentials - you'll need them to pull images from Container Apps.

---

## Phase 3: Deploy to Azure Container Apps

### Step 9: Create FastAPI Backend Container App

```powershell
$APP_NAME = "govc-api"
$RESOURCE_GROUP = "govc-advisor-rg"
$ACR_URL = "gocvadvisoracr.azurecr.io"
$ACR_ADMIN_USER = "gocvadvisoracr"
$ACR_ADMIN_PASSWORD = "YOUR_PASSWORD_HERE"  # From Step 8

# Set your environment variables
$SUPABASE_URL = "https://your-supabase-url.supabase.co"
$SUPABASE_KEY = "your-supabase-key"
$SUPABASE_SERVICE_KEY = "your-supabase-service-key"
$OPENAI_API_KEY = "your-openai-key"
$JWT_SECRET = "your-jwt-secret-change-this-in-production"

az containerapp create `
  --name $APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --environment govc-env `
  --image "$ACR_URL/govc-api:latest" `
  --target-port 8000 `
  --ingress external `
  --cpu 0.5 `
  --memory 1Gi `
  --min-replicas 0 `
  --max-replicas 2 `
  --registry-server $ACR_URL `
  --registry-username $ACR_ADMIN_USER `
  --registry-password $ACR_ADMIN_PASSWORD `
  --env-vars `
    SUPABASE_URL=$SUPABASE_URL `
    SUPABASE_KEY=$SUPABASE_KEY `
    SUPABASE_SERVICE_KEY=$SUPABASE_SERVICE_KEY `
    OPENAI_API_KEY=$OPENAI_API_KEY `
    JWT_SECRET=$JWT_SECRET `
    IN_DOCKER=true `
    PYTHONUNBUFFERED=1 `
    PYTHONDONTWRITEBYTECODE=1 `
    MPLBACKEND=Agg `
    QT_QPA_PLATFORM=offscreen
```

Get the API URL:

```powershell
$API_FQDN = az containerapp show --name govc-api --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv
Write-Host "API URL: https://$API_FQDN"
```

### Step 10: Create Streamlit UI Container App

```powershell
$APP_NAME = "govc-ui"
$RESOURCE_GROUP = "govc-advisor-rg"
$ACR_URL = "gocvadvisoracr.azurecr.io"
$ACR_ADMIN_USER = "gocvadvisoracr"
$ACR_ADMIN_PASSWORD = "YOUR_PASSWORD_HERE"  # From Step 8
$API_FQDN = "govc-api.xxx.eastus.azurecontainerapps.io"  # From Step 9

# Same environment variables as API
$SUPABASE_URL = "https://your-supabase-url.supabase.co"
$SUPABASE_KEY = "your-supabase-key"
$SUPABASE_SERVICE_KEY = "your-supabase-service-key"
$OPENAI_API_KEY = "your-openai-key"

az containerapp create `
  --name $APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --environment govc-env `
  --image "$ACR_URL/govc-ui:latest" `
  --target-port 8507 `
  --ingress external `
  --cpu 0.5 `
  --memory 1Gi `
  --min-replicas 0 `
  --max-replicas 2 `
  --registry-server $ACR_URL `
  --registry-username $ACR_ADMIN_USER `
  --registry-password $ACR_ADMIN_PASSWORD `
  --env-vars `
    API_BASE_URL=https://$API_FQDN `
    SUPABASE_URL=$SUPABASE_URL `
    SUPABASE_KEY=$SUPABASE_KEY `
    SUPABASE_SERVICE_KEY=$SUPABASE_SERVICE_KEY `
    OPENAI_API_KEY=$OPENAI_API_KEY `
    IN_DOCKER=true `
    PYTHONPATH=/app:/app/src `
    STREAMLIT_SERVER_PORT=8507 `
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 `
    STREAMLIT_SERVER_HEADLESS=true `
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false `
    MPLBACKEND=Agg `
    QT_QPA_PLATFORM=offscreen
```

Get the UI URL:

```powershell
$UI_FQDN = az containerapp show --name govc-ui --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv
Write-Host "UI URL: https://$UI_FQDN"
```

### Step 11: Verify Deployments

```powershell
$RESOURCE_GROUP = "govc-advisor-rg"

# Check API status
az containerapp show --name govc-api --resource-group $RESOURCE_GROUP --query "properties.runningStatus"

# Check UI status
az containerapp show --name govc-ui --resource-group $RESOURCE_GROUP --query "properties.runningStatus"

# Get full URLs
$API_URL = az containerapp show --name govc-api --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv
$UI_URL = az containerapp show --name govc-ui --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv

Write-Host "API: https://$API_URL"
Write-Host "UI: https://$UI_URL"
```

---

## Phase 4: Configure Custom Domain (Optional)

If you have a custom domain and want to use it instead of Azure's auto-generated URLs:

### Step 12: Add Custom Domain to Container Apps

```powershell
$RESOURCE_GROUP = "govc-advisor-rg"
$CUSTOM_DOMAIN = "govc-advisor.be"  # Your domain

# For API
az containerapp hostname add `
  --hostname api.$CUSTOM_DOMAIN `
  --name govc-api `
  --resource-group $RESOURCE_GROUP

# For UI
az containerapp hostname add `
  --hostname ui.$CUSTOM_DOMAIN `
  --name govc-ui `
  --resource-group $RESOURCE_GROUP
```

### Step 13: Configure DNS Records

In your DNS provider (Cloudflare, Route53, etc.), add CNAME records:

```
api.govc-advisor.be  → govc-api.xxxxxx.eastus.azurecontainerapps.io
ui.govc-advisor.be   → govc-ui.xxxxxx.eastus.azurecontainerapps.io
```

Wait for DNS propagation (5-10 minutes).

### Step 14: Bind SSL Certificates

```powershell
$RESOURCE_GROUP = "govc-advisor-rg"
$CUSTOM_DOMAIN = "govc-advisor.be"

# Bind API domain
az containerapp hostname bind `
  --hostname api.$CUSTOM_DOMAIN `
  --name govc-api `
  --resource-group $RESOURCE_GROUP `
  --environment govc-env `
  --validation-method CNAME

# Bind UI domain
az containerapp hostname bind `
  --hostname ui.$CUSTOM_DOMAIN `
  --name govc-ui `
  --resource-group $RESOURCE_GROUP `
  --environment govc-env `
  --validation-method CNAME
```

---

## Phase 5: Testing and Verification

### Step 15: Test API Health

```powershell
$API_URL = "https://govc-api.xxxxxx.eastus.azurecontainerapps.io"

# Test health endpoint
curl -i "$API_URL/health"

# Should return 200 OK with {"status":"ok"}
```

### Step 16: Test UI Access

Visit your UI URL in browser:
```
https://govc-ui.xxxxxx.eastus.azurecontainerapps.io
```

You should see the Streamlit login interface.

### Step 17: Test End-to-End

1. Login to UI with your credentials
2. Test document upload/processing
3. Verify API calls are working
4. Check Supabase database for stored documents

---

## Monitoring and Maintenance

### View Logs

```powershell
$RESOURCE_GROUP = "govc-advisor-rg"

# API logs
az containerapp logs show --name govc-api --resource-group $RESOURCE_GROUP --tail 100

# UI logs
az containerapp logs show --name govc-ui --resource-group $RESOURCE_GROUP --tail 100
```

### Update Container Images

When you push new images to ACR:

```powershell
$RESOURCE_GROUP = "govc-advisor-rg"

# Update API
az containerapp update `
  --name govc-api `
  --resource-group $RESOURCE_GROUP `
  --image gocvadvisoracr.azurecr.io/govc-api:latest

# Update UI
az containerapp update `
  --name govc-ui `
  --resource-group $RESOURCE_GROUP `
  --image gocvadvisoracr.azurecr.io/govc-ui:latest
```

### Monitor Resource Usage

```powershell
$RESOURCE_GROUP = "govc-advisor-rg"

# Get API resource details
az containerapp show --name govc-api --resource-group $RESOURCE_GROUP --query "properties.template.containers[0].resources"

# Get UI resource details
az containerapp show --name govc-ui --resource-group $RESOURCE_GROUP --query "properties.template.containers[0].resources"
```

### Scale Container Apps

```powershell
$RESOURCE_GROUP = "govc-advisor-rg"

# Keep API always running for better response
az containerapp update `
  --name govc-api `
  --resource-group $RESOURCE_GROUP `
  --min-replicas 1 `
  --max-replicas 3

# Keep UI scale-to-zero for cost savings
az containerapp update `
  --name govc-ui `
  --resource-group $RESOURCE_GROUP `
  --min-replicas 0 `
  --max-replicas 2
```

---

## Troubleshooting

### Issue: Container App Won't Start

Check the logs:

```powershell
az containerapp logs show --name govc-api --resource-group govc-advisor-rg --tail 50
```

Common causes:
- Missing environment variables (check API_BASE_URL, SUPABASE_* keys)
- Insufficient permissions in ACR
- Missing Python dependencies in Dockerfile

### Issue: API Can't Connect to Supabase

```powershell
# Verify environment variables
az containerapp show --name govc-api --resource-group govc-advisor-rg --query "properties.template.containers[0].env" -o json

# Check Supabase connection
# Add debug logging to your FastAPI app to diagnose
```

### Issue: UI Can't Connect to API

Make sure in UI environment variables:
```
API_BASE_URL=https://govc-api.xxxxx.eastus.azurecontainerapps.io
```

Not:
```
API_BASE_URL=http://govc-api:8000  # This only works in local Docker Compose
```

### Issue: Out of Memory Errors

Increase memory allocation:

```powershell
az containerapp update `
  --name govc-api `
  --resource-group govc-advisor-rg `
  --memory 2Gi
```

### Issue: Slow Performance

Check if containers are scale-to-zero:

```powershell
# Set minimum replicas to 1 for always-on
az containerapp update `
  --name govc-api `
  --resource-group govc-advisor-rg `
  --min-replicas 1
```

---

## Cost Optimization

To minimize costs while keeping the application functional:

1. **API (FastAPI):** Set `--min-replicas 1` to avoid cold starts
2. **UI (Streamlit):** Keep `--min-replicas 0` to scale-to-zero
3. **ACR:** Use Basic SKU (included in free tier for small images)
4. **Container Apps:** Stay within 2 million requests/month and 400GB-seconds

Monitor usage:

```powershell
# Check Azure costs
az consumption usage list --top 5
```

---

## Summary of Real Configuration

**Your GOVC-Advisor Setup:**
- **Resource Group:** govc-advisor-rg
- **Region:** eastus
- **ACR:** gocvadvisoracr.azurecr.io
- **API:** govc-api (FastAPI, 0.5 CPU, 1GB RAM)
- **UI:** govc-ui (Streamlit, 0.5 CPU, 1GB RAM)
- **Database:** Supabase PostgreSQL (external)
- **Scaling:** 0-2 replicas each, auto-scaling enabled

**Key Environment Variables:**
- `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_KEY`
- `OPENAI_API_KEY`
- `JWT_SECRET`
- `API_BASE_URL` (for UI to reach API)

---

## Next Steps

1. Push your code changes to trigger new builds
2. Monitor logs for issues
3. Set up GitHub Actions for automated builds (optional)
4. Configure backup strategy for Supabase data
5. Set up monitoring alerts
6. Document your custom environment variables securely

For more help, refer to:
- Azure Container Apps: https://learn.microsoft.com/en-us/azure/container-apps/
- Docker: https://docs.docker.com/
- Your application documentation