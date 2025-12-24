# Complete End-to-End Guide: Deploying n8n on Azure Container Apps with OAuth

This guide walks you through deploying n8n on Azure's free tier with proper OAuth2 configuration, using real parameters from the conversation and lessons learned.

**Total Setup Time:** 45-60 minutes  
**Monthly Cost:** $0 (within free tier limits)

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Phase 1: Azure Setup](#phase-1-azure-setup)
3. [Phase 2: Database Setup (Neon)](#phase-2-database-setup-neon)
4. [Phase 3: Deploy n8n Container](#phase-3-deploy-n8n-container)
5. [Phase 4: Configure Custom Domain (Optional)](#phase-4-configure-custom-domain-optional)
6. [Phase 5: OAuth Configuration](#phase-5-oauth-configuration)
7. [Phase 6: Testing and Verification](#phase-6-testing-and-verification)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before starting, ensure you have:

- Azure account with active subscription
- Azure CLI installed on Windows (PowerShell)
- Neon account (free tier available at neon.tech)
- Git Bash or PowerShell for running commands
- Text editor to save credentials safely
- (Optional) Custom domain registered and Cloudflare account if using custom domain

### Step 0: Verify Prerequisites

Open PowerShell and verify Azure CLI is installed:

```powershell
az --version
az login
az account show
```

If Azure CLI is not installed, download it from https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows

---

## Phase 1: Azure Setup

### Step 1: Register Required Providers

```powershell
# Register Container Apps provider
az provider register --namespace Microsoft.App

# Register Log Analytics provider
az provider register --namespace Microsoft.OperationalInsights

# Check registration status (wait for "Registered" status)
az provider show -n Microsoft.App --query registrationState
az provider show -n Microsoft.OperationalInsights --query registrationState
```

Wait until both show `"Registered"` before proceeding.

### Step 2: Create Resource Group

```powershell
# Create resource group
az group create --name n8n-free-rg --location eastus
```

### Step 3: Create Container Apps Environment

```powershell
# Create Container Apps environment (takes 2-3 minutes)
az containerapp env create --name n8n-env --resource-group n8n-free-rg --location eastus
```

---

## Phase 2: Database Setup (Neon)

### Step 4: Create Neon PostgreSQL Database

1. Go to https://console.neon.tech
2. Sign up or log in
3. Click "New Project"
4. Name it: `n8n-azure-database`
5. Choose region: `us-east-1` (closest to Azure East US)
6. Click "Create Project"

### Step 5: Get Neon Connection Details

In the Neon console:

1. Go to your project
2. Copy the **Connection String** (looks like: `postgresql://user:password@host/database`)
3. From the connection string, extract:
   - **Host:** `ep-xxx-pooler.c-2.us-east-1.aws.neon.tech` (use the pooler endpoint)
   - **Database:** `neondb`
   - **User:** `neondb_owner`
   - **Password:** `npg_xxxxx` (the part after the colon and before the @)

**Save these credentials in a safe place** - you'll need them in the next step.

---

## Phase 3: Deploy n8n Container

### Step 6: Get Your Azure FQDN

```powershell
# This will show your Container Apps FQDN (write it down)
$FQDN = az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null
if ($FQDN) { Write-Host "FQDN: $FQDN" } else { Write-Host "Container not created yet" }
```

If it shows "Container not created yet", that's fine - we'll create it next.

### Step 7: Deploy n8n with Complete Configuration

Replace the placeholder values with your actual Neon credentials:

```powershell
# Set your variables
$NEON_HOST = "ep-green-butterfly-ad850hp3-pooler.c-2.us-east-1.aws.neon.tech"  # Your Neon host
$NEON_USER = "neondb_owner"  # Your Neon user
$NEON_PASSWORD = "npg_wXc53yTUoGQV"  # Your Neon password
$NEON_DATABASE = "neondb"  # Your Neon database name

# Deploy n8n container with all required configuration
az containerapp create `
  --name n8n-app `
  --resource-group n8n-free-rg `
  --environment n8n-env `
  --image n8nio/n8n:latest `
  --target-port 5678 `
  --ingress external `
  --cpu 0.5 `
  --memory 1Gi `
  --min-replicas 0 `
  --max-replicas 1 `
  --env-vars `
    N8N_HOST=0.0.0.0 `
    N8N_PORT=5678 `
    N8N_PROTOCOL=http `
    N8N_TRUST_PROXY=true `
    TRUST_PROXY=true `
    N8N_SECURE_COOKIE=false `
    NODE_OPTIONS="--max-http-header-size=32768" `
    N8N_BLOCK_ENV_ACCESS_IN_NODE=false `
    N8N_RUNNERS_ENABLED=false `
    N8N_BASIC_AUTH_ACTIVE=true `
    N8N_BASIC_AUTH_USER=admin `
    N8N_BASIC_AUTH_PASSWORD=SecurePass123! `
    N8N_ENCRYPTION_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6 `
    N8N_USER_MANAGEMENT_DISABLED=true `
    N8N_USER_FOLDER=/home/node/.n8n `
    N8N_USER_MANAGEMENT_JWT_SECRET=myJwtSecret123 `
    DB_TYPE=postgresdb `
    DB_POSTGRESDB_HOST=$NEON_HOST `
    DB_POSTGRESDB_PORT=5432 `
    DB_POSTGRESDB_DATABASE=$NEON_DATABASE `
    DB_POSTGRESDB_USER=$NEON_USER `
    DB_POSTGRESDB_PASSWORD=$NEON_PASSWORD `
    DB_POSTGRESDB_SCHEMA=public `
    DB_POSTGRESDB_SSL=true `
    DB_POSTGRESDB_SSL_REJECT_UNAUTHORIZED=false
```

Wait 2-3 minutes for deployment to complete.

### Step 8: Verify Initial Deployment

```powershell
# Check if n8n is running
az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.runningStatus"

# Get your FQDN (Azure auto-generated URL)
$FQDN = az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.configuration.ingress.fqdn" -o tsv
Write-Host "Your n8n URL: https://$FQDN"
```

Visit `https://$FQDN` in your browser. You should see the n8n login screen.

Login with:
- **Username:** admin
- **Password:** SecurePass123!

---

## Phase 4: Configure Custom Domain (Optional)

Skip this section if you just want to use the Azure auto-generated domain. Otherwise, follow these steps.

### Step 9: Register a Domain

If you don't already own a domain, register one at:
- Namecheap.com
- GoDaddy.com
- OVH.com
- Register.be (for .be domains)

For this example, we'll use `assistt.be`.

### Step 10: Point Domain to Cloudflare Nameservers

1. Log in to your domain registrar
2. Find DNS/Nameserver settings
3. Replace nameservers with Cloudflare's:
   - `ns1.cloudflare.com`
   - `ns2.cloudflare.com`
   - `ns3.cloudflare.com`
   - `ns4.cloudflare.com`
4. Save changes
5. Wait 5-10 minutes for propagation

### Step 11: Add DNS Records in Cloudflare

1. Go to https://dash.cloudflare.com
2. Select your domain
3. Click **DNS** in the sidebar

Add two records:

**Record 1: TXT for Domain Verification**
```
Type: TXT
Name: asuid.n8n
Content: (run the command below to get this)
TTL: Auto
Proxy status: DNS only
```

To get the verification ID:

```powershell
$DOMAIN = "assistt.be"  # Change to your domain
$HOSTNAME = "n8n.$DOMAIN"

# This will fail but show the verification ID you need
az containerapp hostname add --hostname $HOSTNAME --name n8n-app --resource-group n8n-free-rg 2>&1 | grep -i "content\|verify"
```

Look for a string like `8FE59AB6950B100B757E4B7E7D69DD10AB7865FC841A31F9B407175073D08380` - that's your verification ID.

**Record 2: CNAME for Your Subdomain**

Get your Azure FQDN first:

```powershell
$FQDN = az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.configuration.ingress.fqdn" -o tsv
Write-Host "Azure FQDN: $FQDN"
```

Then add the CNAME:
```
Type: CNAME
Name: n8n
Content: (your Azure FQDN from above)
TTL: Auto
Proxy status: DNS only (gray cloud)
```

### Step 12: Link Custom Domain to Azure

```powershell
$DOMAIN = "assistt.be"  # Change to your domain
$HOSTNAME = "n8n.$DOMAIN"

# Wait 30 seconds for DNS to propagate
Start-Sleep -Seconds 30

# Add custom domain to Azure
az containerapp hostname add --hostname $HOSTNAME --name n8n-app --resource-group n8n-free-rg

# Enable SSL certificate
az containerapp hostname bind `
  --hostname $HOSTNAME `
  --name n8n-app `
  --resource-group n8n-free-rg `
  --environment n8n-env `
  --validation-method CNAME
```

Wait 10-20 minutes for SSL certificate to provision.

### Step 13: Update n8n with Custom Domain

If you set up a custom domain, update n8n to use it:

```powershell
$DOMAIN = "assistt.be"  # Change to your domain
$HOSTNAME = "n8n.$DOMAIN"

az containerapp update `
  --name n8n-app `
  --resource-group n8n-free-rg `
  --set-env-vars `
    N8N_EDITOR_BASE_URL=https://$HOSTNAME `
    WEBHOOK_URL=https://$HOSTNAME/
```

Restart the container:

```powershell
$REVISION = az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.latestRevisionName" -o tsv
az containerapp revision restart --name n8n-app --resource-group n8n-free-rg --revision $REVISION
```

Wait 2-3 minutes, then access n8n at `https://n8n.assistt.be` (or your custom domain).

---

## Phase 5: OAuth Configuration

### Step 14: Set Up OAuth with Azure AD (Microsoft)

1. Go to https://portal.azure.com
2. Search for "App registrations"
3. Click "New registration"
4. Fill in:
   - **Name:** n8n-oauth
   - **Supported account types:** Accounts in any organizational directory (Multi-tenant)
5. Click "Register"

Get your FQDN or custom domain:

```powershell
# If using Azure auto-generated domain
$FQDN = az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.configuration.ingress.fqdn" -o tsv
$CALLBACK_URL = "https://$FQDN/rest/oauth2-credential/callback"

# If using custom domain, replace with:
# $CALLBACK_URL = "https://n8n.assistt.be/rest/oauth2-credential/callback"

Write-Host "Your OAuth Callback URL: $CALLBACK_URL"
```

In your Azure AD app registration:

1. Click **Authentication** in the left sidebar
2. Click "Add a platform"
3. Select "Web"
4. Under "Redirect URIs", paste your callback URL
5. Enable "Access tokens" and "ID tokens"
6. Click "Configure"
7. Click **Certificates & secrets**
8. Click "New client secret"
9. Copy the secret value (you'll use this in n8n)

### Step 15: Connect OAuth in n8n

1. Access n8n at your URL
2. Login with admin / SecurePass123!
3. Go to **Credentials** (left sidebar)
4. Click "New" → Search for "Microsoft Outlook OAuth2 API" or "Google OAuth2 API"
5. Fill in:

**For Microsoft:**
- **Client ID:** (from Azure AD app registration)
- **Client Secret:** (from Azure AD app registration)
- Leave other fields blank - n8n will auto-fill them

**For Google:**
1. Go to https://console.cloud.google.com
2. Create a new project
3. Enable Google API
4. Create OAuth consent screen
5. Create OAuth 2.0 credentials (Web application)
6. Add redirect URI: `https://$FQDN/rest/oauth2-credential/callback`
7. Copy Client ID and Secret to n8n

6. Click "Test" to verify the connection works
7. Save the credential

---

## Phase 6: Testing and Verification

### Step 16: Verify All Components

```powershell
# Check container status
az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.runningStatus"

# Check environment variables are set correctly
az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.template.containers[0].env[0:5]" -o table

# Get your FQDN
$FQDN = az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.configuration.ingress.fqdn" -o tsv
Write-Host "Access n8n at: https://$FQDN"
```

### Step 17: Test OAuth Flow

1. In n8n, create a new workflow
2. Add a node that requires OAuth (e.g., Gmail, Outlook, Google Sheets)
3. Click "Authenticate" and follow the OAuth flow
4. You should be redirected to the provider and back to n8n
5. The connection should be saved successfully

### Step 18: Create a Test Workflow

1. Add two nodes:
   - **Start:** Webhook trigger
   - **End:** Send email (using your OAuth credential)
2. Go to Webhook node → copy the webhook URL
3. Test the webhook by visiting the URL in browser
4. Verify the email was sent

---

## Troubleshooting

### Issue: OAuth returns "Request failed with status code 431"

**Solution:** This means request headers are too large, usually due to missing authentication variables.

```powershell
# Verify all required variables are set
az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.template.containers[0].env" -o json | ConvertFrom-Json | Format-Table -Property name, value
```

Check that these exist:
- `N8N_ENCRYPTION_KEY`
- `N8N_BASIC_AUTH_ACTIVE=true`
- `N8N_USER_MANAGEMENT_DISABLED=true`

If missing, run:

```powershell
$FQDN = az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.configuration.ingress.fqdn" -o tsv

az containerapp update `
  --name n8n-app `
  --resource-group n8n-free-rg `
  --replace-env-vars `
    N8N_HOST=0.0.0.0 `
    N8N_PORT=5678 `
    N8N_PROTOCOL=http `
    N8N_EDITOR_BASE_URL=https://$FQDN `
    WEBHOOK_URL=https://$FQDN/ `
    N8N_TRUST_PROXY=true `
    TRUST_PROXY=true `
    N8N_SECURE_COOKIE=false `
    NODE_OPTIONS="--max-http-header-size=32768" `
    N8N_BLOCK_ENV_ACCESS_IN_NODE=false `
    N8N_RUNNERS_ENABLED=false `
    N8N_BASIC_AUTH_ACTIVE=true `
    N8N_BASIC_AUTH_USER=admin `
    N8N_BASIC_AUTH_PASSWORD=SecurePass123! `
    N8N_ENCRYPTION_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6 `
    N8N_USER_MANAGEMENT_DISABLED=true `
    N8N_USER_FOLDER=/home/node/.n8n `
    N8N_USER_MANAGEMENT_JWT_SECRET=myJwtSecret123 `
    DB_TYPE=postgresdb `
    DB_POSTGRESDB_HOST=YOUR_NEON_HOST `
    DB_POSTGRESDB_PORT=5432 `
    DB_POSTGRESDB_DATABASE=neondb `
    DB_POSTGRESDB_USER=YOUR_NEON_USER `
    DB_POSTGRESDB_PASSWORD=YOUR_NEON_PASSWORD `
    DB_POSTGRESDB_SCHEMA=public `
    DB_POSTGRESDB_SSL=true `
    DB_POSTGRESDB_SSL_REJECT_UNAUTHORIZED=false
```

Then restart and clear browser cache.

### Issue: "0.0.0.0:5678" showing in OAuth URL

**Solution:** Update environment variables and restart:

```powershell
$FQDN = az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.configuration.ingress.fqdn" -o tsv

az containerapp update `
  --name n8n-app `
  --resource-group n8n-free-rg `
  --set-env-vars `
    N8N_EDITOR_BASE_URL=https://$FQDN `
    WEBHOOK_URL=https://$FQDN/ `
    N8N_TRUST_PROXY=true

$REVISION = az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.latestRevisionName" -o tsv
az containerapp revision restart --name n8n-app --resource-group n8n-free-rg --revision $REVISION
```

Clear browser cache after restart.

### Issue: Database Connection Error

```powershell
# Check logs
az containerapp logs show --name n8n-app --resource-group n8n-free-rg --tail 100

# Verify Neon database is accessible:
# 1. Go to Neon console
# 2. Check database is not hibernating
# 3. Verify credentials are correct
# 4. Use pooler endpoint (not regular endpoint)
```

### Issue: Custom Domain Not Working

```powershell
# Check DNS records
nslookup n8n.assistt.be

# Check Azure domain binding
az containerapp show --name n8n-app --resource-group n8n-free-rg --query "properties.configuration.ingress.customDomains" -o json

# Verify certificate status
az containerapp env certificate list --resource-group n8n-free-rg --name n8n-env
```

---

## Important Notes

⚠️ **Never change these after initial setup:**
- `N8N_ENCRYPTION_KEY` - Changing this makes all encrypted data unreadable
- Database connection details - Changing these breaks all stored credentials

🔐 **Security Best Practices:**
- Change default password `SecurePass123!` to something secure
- Generate new encryption key: `openssl rand -hex 16`
- Store credentials securely
- Use strong OAuth client secrets

💾 **Backup Strategy:**
- Neon database is automatically backed up
- Export workflows regularly from n8n
- Document custom environment variables

---

## Summary of Real Configuration Used

Based on the conversation:

```
Azure Region: eastus
Container: n8n:latest
FQDN: n8n-app.delightfulpond-10798329.eastus.azurecontainerapps.io
Database: Neon PostgreSQL (ep-green-butterfly-ad850hp3-pooler.c-2.us-east-1.aws.neon.tech)
Default Domain: assistt.be (optional custom domain)
```

This configuration costs **$0/month** and stays within Azure's free tier limits.

---

## Next Steps After Deployment

1. Change admin password from default
2. Disable basic auth if using OAuth exclusively
3. Create your first workflows
4. Set up webhook integrations
5. Configure alerts and monitoring
6. Export workflow definitions for backup

For more help, visit:
- n8n Docs: https://docs.n8n.io
- Azure Container Apps: https://learn.microsoft.com/en-us/azure/container-apps/
- Neon Docs: https://neon.tech/docs/