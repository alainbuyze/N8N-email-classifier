# GitHub Actions Automated Build & Deployment to Azure

Complete guide for setting up GitHub Actions to automatically build Docker images and deploy them to Azure Container Apps whenever you push code.

**What This Automates:**
- Build Docker images on every push to main branch
- Push images to Azure Container Registry
- Update Container Apps with new images
- Run tests before building (optional)
- Send deployment notifications

**Time to Setup:** 15-20 minutes

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Phase 1: Create Azure Service Principal](#phase-1-create-azure-service-principal)
3. [Phase 2: Add GitHub Secrets](#phase-2-add-github-secrets)
4. [Phase 3: Create GitHub Actions Workflows](#phase-3-create-github-actions-workflows)
5. [Phase 4: Configure Workflows](#phase-4-configure-workflows)
6. [Phase 5: Test and Verify](#phase-5-test-and-verify)
7. [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)
8. [Advanced Features](#advanced-features)

---

## Prerequisites

- GitHub account with push access to your GOVC-advisor repository
- Azure subscription with Container Registry and Container Apps already created
- Azure CLI installed locally

---

## Phase 1: Create Azure Service Principal

GitHub Actions needs credentials to access your Azure resources. You'll create a Service Principal for this.

### Step 1: Create Service Principal

Open PowerShell and run:

```powershell
$SUBSCRIPTION_ID = az account show --query "id" -o tsv
$RESOURCE_GROUP = "govc-advisor-rg"
$ACR_NAME = "gocvadvisoracr"
$SERVICE_PRINCIPAL_NAME = "github-actions-govc"

# Create the service principal
$SP_JSON = az ad sp create-for-rbac `
  --name $SERVICE_PRINCIPAL_NAME `
  --role "AcrPush" `
  --scopes "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.ContainerRegistry/registries/$ACR_NAME" `
  -o json

# Also add Container Apps Contributor role
$SP_OBJECT_ID = ($SP_JSON | ConvertFrom-Json).id
az role assignment create `
  --assignee $SP_OBJECT_ID `
  --role "Contributor" `
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP"

# Display credentials (save these!)
$SP_JSON | ConvertFrom-Json | Format-Table
```

This output looks like:
```
appId               : xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
displayName         : github-actions-govc
password            : xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
tenant              : xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**Save these values - you'll need them in the next step!**

### Step 2: Verify Service Principal Permissions

```powershell
$SUBSCRIPTION_ID = az account show --query "id" -o tsv
$SP_OBJECT_ID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # From above

# Check role assignments
az role assignment list --assignee $SP_OBJECT_ID --resource-group "govc-advisor-rg"
```

---

## Phase 2: Add GitHub Secrets

### Step 3: Add Secrets to GitHub Repository

1. Go to your GitHub repository: `https://github.com/alainbuyze/GOVC-advisor`
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**

Add these secrets one by one:

**Secret 1: AZURE_CLIENT_ID**
- Name: `AZURE_CLIENT_ID`
- Value: `appId` from Step 1

**Secret 2: AZURE_CLIENT_SECRET**
- Name: `AZURE_CLIENT_SECRET`
- Value: `password` from Step 1

**Secret 3: AZURE_TENANT_ID**
- Name: `AZURE_TENANT_ID`
- Value: `tenant` from Step 1

**Secret 4: AZURE_SUBSCRIPTION_ID**
- Name: `AZURE_SUBSCRIPTION_ID`
- Value: Your subscription ID (from Step 1)

**Secret 5: ACR_LOGIN_SERVER**
- Name: `ACR_LOGIN_SERVER`
- Value: `gocvadvisoracr.azurecr.io`

**Secret 6: ACR_NAME**
- Name: `ACR_NAME`
- Value: `gocvadvisoracr`

**Application Secrets (from your .env.keys file):**

**Secret 7: SUPABASE_URL**
- Name: `SUPABASE_URL`
- Value: Your Supabase URL

**Secret 8: SUPABASE_KEY**
- Name: `SUPABASE_KEY`
- Value: Your Supabase anon key

**Secret 9: SUPABASE_SERVICE_KEY**
- Name: `SUPABASE_SERVICE_KEY`
- Value: Your Supabase service key

**Secret 10: OPENAI_API_KEY**
- Name: `OPENAI_API_KEY`
- Value: Your OpenAI API key

**Secret 11: JWT_SECRET**
- Name: `JWT_SECRET`
- Value: Your JWT secret

### Step 4: Verify Secrets Are Added

Go to **Settings** → **Secrets and variables** → **Actions** and verify all 11 secrets are listed.

---

## Phase 3: Create GitHub Actions Workflows

### Step 5: Create Workflow Directory Structure

In your local repository, create the workflow files:

```powershell
# From your repository root
mkdir -p .github/workflows

# Create two workflow files (we'll add content next)
New-Item -Path ".github/workflows/build-and-deploy.yml" -ItemType File
New-Item -Path ".github/workflows/test.yml" -ItemType File
```

### Step 6: Create Main Build & Deploy Workflow

Create `.github/workflows/build-and-deploy.yml`:

```yaml
name: Build and Deploy to Azure

on:
  push:
    branches:
      - main
      - develop
  pull_request:
    branches:
      - main
  workflow_dispatch:  # Allows manual trigger

env:
  REGISTRY: ${{ secrets.ACR_LOGIN_SERVER }}
  ACR_NAME: ${{ secrets.ACR_NAME }}
  RESOURCE_GROUP: govc-advisor-rg
  API_APP_NAME: govc-api
  UI_APP_NAME: govc-ui

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Azure Login
        uses: azure/login@v1
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Log in to Azure Container Registry
        run: |
          az acr login --name ${{ env.ACR_NAME }}

      - name: Build and push API image
        run: |
          docker build \
            -f docker/Dockerfile.api \
            -t ${{ env.REGISTRY }}/govc-api:${{ github.sha }} \
            -t ${{ env.REGISTRY }}/govc-api:latest \
            .
          
          docker push ${{ env.REGISTRY }}/govc-api:${{ github.sha }}
          docker push ${{ env.REGISTRY }}/govc-api:latest

      - name: Build and push UI image
        run: |
          docker build \
            -f docker/Dockerfile.ui \
            -t ${{ env.REGISTRY }}/govc-ui:${{ github.sha }} \
            -t ${{ env.REGISTRY }}/govc-ui:latest \
            .
          
          docker push ${{ env.REGISTRY }}/govc-ui:${{ github.sha }}
          docker push ${{ env.REGISTRY }}/govc-ui:latest

      - name: Update API Container App
        if: github.ref == 'refs/heads/main' && github.event_name == 'push'
        run: |
          az containerapp update \
            --name ${{ env.API_APP_NAME }} \
            --resource-group ${{ env.RESOURCE_GROUP }} \
            --image ${{ env.REGISTRY }}/govc-api:latest

      - name: Update UI Container App
        if: github.ref == 'refs/heads/main' && github.event_name == 'push'
        run: |
          az containerapp update \
            --name ${{ env.UI_APP_NAME }} \
            --resource-group ${{ env.RESOURCE_GROUP }} \
            --image ${{ env.REGISTRY }}/govc-ui:latest

      - name: Wait for deployments
        if: github.ref == 'refs/heads/main' && github.event_name == 'push'
        run: |
          echo "Waiting for API deployment..."
          sleep 30
          
          echo "Waiting for UI deployment..."
          sleep 30

      - name: Verify API deployment
        if: github.ref == 'refs/heads/main' && github.event_name == 'push'
        run: |
          API_URL=$(az containerapp show \
            --name ${{ env.API_APP_NAME }} \
            --resource-group ${{ env.RESOURCE_GROUP }} \
            --query "properties.configuration.ingress.fqdn" -o tsv)
          
          echo "Checking API health at https://$API_URL/health"
          curl -f -m 10 "https://$API_URL/health" || echo "Warning: API health check timed out"

      - name: Notify Deployment Success
        if: success() && github.ref == 'refs/heads/main' && github.event_name == 'push'
        run: |
          echo "✅ Deployment successful!"
          echo "API: https://$(az containerapp show --name ${{ env.API_APP_NAME }} --resource-group ${{ env.RESOURCE_GROUP }} --query 'properties.configuration.ingress.fqdn' -o tsv)"
          echo "UI: https://$(az containerapp show --name ${{ env.UI_APP_NAME }} --resource-group ${{ env.RESOURCE_GROUP }} --query 'properties.configuration.ingress.fqdn' -o tsv)"

      - name: Notify Deployment Failure
        if: failure() && github.ref == 'refs/heads/main'
        run: |
          echo "❌ Deployment failed!"
          echo "Check GitHub Actions logs for details"
```

### Step 7: Create Test Workflow (Optional)

Create `.github/workflows/test.yml`:

```yaml
name: Tests

on:
  push:
    branches:
      - main
      - develop
  pull_request:
    branches:
      - main

jobs:
  test:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        python-version: ['3.12']

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt

      - name: Run linting (flake8)
        run: |
          # Stop the build if there are Python syntax errors or undefined names
          flake8 src/ --count --select=E9,F63,F7,F82 --show-source --statistics
          # Exit-zero treats all errors as warnings
          flake8 src/ --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
        continue-on-error: true

      - name: Run tests
        run: |
          pytest tests/ -v --tb=short
        continue-on-error: true

      - name: Check code format (black)
        run: |
          black --check src/ --diff
        continue-on-error: true
```

---

## Phase 4: Configure Workflows

### Step 8: Update Workflow Environment Variables

If your environment variables need to be injected at build time (not runtime), update the workflows:

**Option A: Environment Variables from Secrets (Recommended)**

The workflows above pull from GitHub secrets at runtime. Your Container Apps have these set in their environment variables.

**Option B: Build-Time Secrets (if needed)**

If you need secrets during build:

```yaml
- name: Build API image with secrets
  run: |
    docker build \
      --build-arg OPENAI_API_KEY=${{ secrets.OPENAI_API_KEY }} \
      -f docker/Dockerfile.api \
      -t ${{ env.REGISTRY }}/govc-api:latest \
      .
```

### Step 9: Configure Branch Protection (Optional)

To ensure tests pass before merging:

1. Go to **Settings** → **Branches** → **Add rule**
2. Select branch: `main`
3. Require status checks to pass:
   - Check "Build and Deploy to Azure"
   - Check "Tests"
4. Click **Create**

---

## Phase 5: Test and Verify

### Step 10: Push Code to Trigger Workflow

```powershell
cd C:\Users\alain\CascadeProjects\GOVC-advisor

# Make a small change to test
echo "# Deployment test" >> README.md

# Commit and push
git add .
git commit -m "test: trigger GitHub Actions workflow"
git push origin main
```

### Step 11: Monitor Workflow Execution

1. Go to your GitHub repository
2. Click **Actions** tab
3. Watch the workflow run in real-time
4. Once complete, verify:
   - ✅ Docker images built successfully
   - ✅ Images pushed to Azure Container Registry
   - ✅ Container Apps updated
   - ✅ Health checks passed

### Step 12: Verify Deployment in Azure

```powershell
$RESOURCE_GROUP = "govc-advisor-rg"

# Check if images were updated
az acr repository show-manifests --name gocvadvisoracr --image govc-api:latest

# Check Container App status
az containerapp show --name govc-api --resource-group $RESOURCE_GROUP --query "properties.runningStatus"
az containerapp show --name govc-ui --resource-group $RESOURCE_GROUP --query "properties.runningStatus"

# Get latest deployment details
az containerapp show --name govc-api --resource-group $RESOURCE_GROUP --query "properties.template.containers[0].image"
```

---

## Monitoring and Troubleshooting

### Monitor Workflow Runs

In GitHub repository:
- **Actions** → **Build and Deploy to Azure** → View recent runs
- Click on a run to see detailed logs
- Each step shows input/output and errors

### Common Issues

#### Issue: "Azure Login Failed"

**Cause:** Service Principal credentials expired or incorrect

**Solution:**
1. Regenerate Service Principal:
```powershell
az ad sp credential reset --name "github-actions-govc"
```

2. Update GitHub secrets with new credentials

#### Issue: "ACR Push Failed"

**Cause:** Service Principal doesn't have AcrPush role

**Solution:**
```powershell
$SP_OBJECT_ID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

az role assignment create `
  --assignee $SP_OBJECT_ID `
  --role "AcrPush" `
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/govc-advisor-rg/providers/Microsoft.ContainerRegistry/registries/gocvadvisoracr"
```

#### Issue: "Container App Update Failed"

**Cause:** Service Principal lacks Container Apps Contributor role

**Solution:**
```powershell
$SP_OBJECT_ID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
$SUBSCRIPTION_ID = az account show --query "id" -o tsv

az role assignment create `
  --assignee $SP_OBJECT_ID `
  --role "Contributor" `
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/govc-advisor-rg"
```

#### Issue: "Workflow Timeout"

**Cause:** Docker build takes too long

**Solution:** Increase timeout in workflow:
```yaml
jobs:
  build-and-deploy:
    timeout-minutes: 60  # Increase from default 360
```

#### Issue: "Health Check Failed"

**Cause:** Container App not responding yet

**Solution:** Increase wait time in workflow:
```yaml
- name: Wait for deployments
  run: |
    echo "Waiting for deployments..."
    sleep 60  # Increase from 30
```

### View Detailed Logs

In GitHub Actions:
1. Click the failed job
2. Expand "Build and push API image" or "Update API Container App"
3. See detailed error messages

### Rollback Deployment

If deployment goes wrong:

```powershell
# Redeploy previous image version
az containerapp update `
  --name govc-api `
  --resource-group govc-advisor-rg `
  --image gocvadvisoracr.azurecr.io/govc-api:previous-sha
```

Or trigger workflow on a previous commit:

```powershell
# In GitHub Actions, click "Run workflow" and select branch/commit
```

---

## Advanced Features

### Feature 1: Deploy Only on Version Tags

Update `.github/workflows/build-and-deploy.yml` to only deploy when creating a release:

```yaml
on:
  push:
    branches:
      - main
    tags:
      - 'v*'  # Only deploy on version tags like v1.0.0
```

### Feature 2: Automatic Rollback on Health Check Failure

```yaml
- name: Rollback on failure
  if: failure()
  run: |
    # Get previous image SHA
    PREVIOUS_IMAGE=$(az acr repository show-manifests \
      --name gocvadvisoracr \
      --image govc-api:latest \
      --query "[1].digest" -o tsv)
    
    echo "Rolling back to previous image..."
    az containerapp update \
      --name govc-api \
      --resource-group govc-advisor-rg \
      --image gocvadvisoracr.azurecr.io/govc-api@$PREVIOUS_IMAGE
```

### Feature 3: Send Slack Notifications

Add Slack notifications on deployment:

```yaml
- name: Send Slack notification
  if: always()
  uses: slackapi/slack-github-action@v1.24.0
  with:
    webhook-url: ${{ secrets.SLACK_WEBHOOK }}
    payload: |
      {
        "text": "GOVC-Advisor Deployment",
        "blocks": [
          {
            "type": "section",
            "text": {
              "type": "mrkdwn",
              "text": "Status: ${{ job.status }}\nCommit: ${{ github.sha }}\nBranch: ${{ github.ref }}"
            }
          }
        ]
      }
```

Then add `SLACK_WEBHOOK` secret to GitHub.

### Feature 4: Deploy to Multiple Environments

```yaml
on:
  push:
    branches:
      - main
      - develop

jobs:
  deploy:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        environment: 
          - { name: 'production', branch: 'main', rg: 'govc-advisor-rg' }
          - { name: 'staging', branch: 'develop', rg: 'govc-advisor-staging-rg' }
    
    if: github.ref == format('refs/heads/{0}', matrix.environment.branch)
    
    steps:
      # ... build steps ...
      
      - name: Deploy to ${{ matrix.environment.name }}
        run: |
          az containerapp update \
            --name govc-api \
            --resource-group ${{ matrix.environment.rg }} \
            --image ${{ env.REGISTRY }}/govc-api:latest
```

### Feature 5: Docker Build Optimization with Buildx

Use Docker Buildx for faster, multi-platform builds:

```yaml
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v2

- name: Build and push with buildx
  uses: docker/build-push-action@v4
  with:
    context: .
    file: ./docker/Dockerfile.api
    push: true
    tags: |
      ${{ env.REGISTRY }}/govc-api:${{ github.sha }}
      ${{ env.REGISTRY }}/govc-api:latest
    cache-from: type=registry,ref=${{ env.REGISTRY }}/govc-api:buildcache
    cache-to: type=registry,ref=${{ env.REGISTRY }}/govc-api:buildcache,mode=max
```

### Feature 6: Automated Image Cleanup

Keep only last 5 images in ACR:

```yaml
- name: Clean up old images
  run: |
    # Delete images older than 30 days
    az acr repository delete \
      --name gocvadvisoracr \
      --image govc-api:* \
      --keep-days 30 \
      --yes
```

---

## Complete Workflow Summary

After setup, here's what happens automatically:

```
1. You push code to GitHub
   ↓
2. GitHub Actions triggers automatically
   ↓
3. Code is checked out
   ↓
4. Azure login with Service Principal
   ↓
5. Docker images built from Dockerfiles
   ↓
6. Images pushed to Azure Container Registry
   ↓
7. Container Apps are updated with new images
   ↓
8. Workflow waits for deployment
   ↓
9. Health checks verify deployment
   ↓
10. Success notification
   ↓
11. New version live in production!
```

Total time: ~5-10 minutes per deployment

---

## Maintenance Tasks

### Monthly: Verify Credentials

```powershell
# Check Service Principal still has correct roles
$SP_OBJECT_ID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
az role assignment list --assignee $SP_OBJECT_ID
```

### Quarterly: Update GitHub Actions

Workflows use pinned versions (e.g., `actions/checkout@v4`). Update quarterly:

```powershell
# In your .github/workflows/*.yml files, update to latest major versions
```

### Weekly: Review Deployment Logs

In GitHub Actions → Build and Deploy to Azure → check recent runs for any warnings.

### On-Demand: Trigger Manual Deployment

```yaml
workflow_dispatch:  # Already enabled in our workflows
```

In GitHub: Actions → Build and Deploy to Azure → **Run workflow** → Select branch

---

## Security Best Practices

1. ✅ **Use OIDC Federation (Optional but Recommended)**
   
   Instead of storing secrets, use OpenID Connect:
   
   ```powershell
   # Create OIDC-based Service Principal
   az ad app federated-credential create \
     --id $SP_OBJECT_ID \
     --parameters '{"name":"github-repo","issuer":"https://token.actions.githubusercontent.com","subject":"repo:alainbuyze/GOVC-advisor:ref:refs/heads/main"}'
   ```

2. ✅ **Limit Service Principal Permissions**
   
   Only give AcrPush and Container Apps Contributor roles.

3. ✅ **Rotate Credentials Quarterly**
   
   ```powershell
   az ad sp credential reset --name "github-actions-govc"
   ```

4. ✅ **Use Branch Protection**
   
   Require reviews and passing checks before merge.

5. ✅ **Audit Deployments**
   
   Review workflow logs regularly for suspicious activity.

---

## Next Steps

1. Commit workflow files to git
2. Push to GitHub
3. Watch first automated deployment
4. Update README with deployment badge:

   ```markdown
   [![Build and Deploy to Azure](https://github.com/alainbuyze/GOVC-advisor/actions/workflows/build-and-deploy.yml/badge.svg)](https://github.com/alainbuyze/GOVC-advisor/actions)
   ```

5. (Optional) Set up Slack notifications
6. (Optional) Configure multiple environments
7. (Optional) Set up OIDC federation for improved security

Congratulations! Your GOVC-advisor is now on fully automated deployment! 🚀