# Deployment Options

This document describes the available deployment options for the Outlook Email Categorizer.

## Local Development (Docker Compose)

For local development and testing:

```bash
# Build and run
docker compose up --build

# Access the web UI
http://localhost:8000
```

See `README.md` for detailed local setup instructions.

## Azure Container Apps (Production)

For production deployment with automated builds and secure secret management.

### Quick Start

1. **Follow the complete setup guide**: See `azure-setup.md` for detailed step-by-step instructions
2. **Configure GitHub Actions**: The workflow in `.github/workflows/azure-deploy.yml` will automatically build and deploy on every push to `main`
3. **Manage secrets securely**: All `.env` variables are stored in Azure Key Vault and accessed via Managed Identity

### What You Get

- ✅ **Automated builds**: Push to GitHub → automatic Docker build and deployment
- ✅ **Secure secrets**: No secrets in code or environment variables
- ✅ **Auto-scaling**: Scales based on traffic (1-3 replicas)
- ✅ **HTTPS**: Automatic SSL certificate
- ✅ **Monitoring**: Built-in logs and metrics
- ✅ **Cost-effective**: Pay only for what you use (~$10-30/month)

### Architecture

```
GitHub Push → GitHub Actions → Build Docker Image → Push to ACR → Deploy to Container Apps
                                                                          ↓
                                                                    Azure Key Vault
                                                                    (Secrets via Managed Identity)
```

### Required Azure Resources

1. **Resource Group**: Container for all resources
2. **Azure Container Registry (ACR)**: Stores Docker images
3. **Azure Key Vault**: Stores secrets (API keys, credentials)
4. **Container Apps Environment**: Hosting environment
5. **Container App**: Runs your application

### Deployment Flow

1. **Initial Setup** (one-time):
   - Create Azure resources (see `azure-setup.md`)
   - Configure GitHub secrets
   - Update workflow file with your resource names

2. **Every Push to `main`**:
   - GitHub Actions builds Docker image
   - Pushes to Azure Container Registry
   - Deploys new version to Container Apps
   - Zero downtime deployment

3. **Secret Management**:
   - Secrets stored in Azure Key Vault
   - Container App uses Managed Identity to access secrets
   - No secrets in code or logs
   - Easy rotation via Azure CLI

### Cost Breakdown

| Resource | Tier | Estimated Cost |
|----------|------|----------------|
| Container Apps | Consumption | $5-20/month (based on usage) |
| Container Registry | Basic | $5/month |
| Key Vault | Standard | $0.03 per 10k operations (~$1/month) |
| **Total** | | **$10-30/month** |

### Monitoring

- **Logs**: Real-time via Azure CLI or Portal
- **Metrics**: CPU, memory, requests, response times
- **Alerts**: Configure alerts for errors or high usage
- **Application Insights**: Optional, for detailed telemetry

### Security

- ✅ Secrets stored in Key Vault (not in environment variables)
- ✅ Managed Identity (no credentials in code)
- ✅ HTTPS by default
- ✅ Network isolation options available
- ✅ Azure AD authentication for management

## Comparison

| Feature | Local (Docker Compose) | Azure Container Apps |
|---------|------------------------|----------------------|
| **Cost** | Free (your machine) | ~$10-30/month |
| **Availability** | Only when your PC is on | 24/7 |
| **Scaling** | Manual | Automatic (1-3 replicas) |
| **HTTPS** | No | Yes (automatic SSL) |
| **Secrets** | `.env` file | Azure Key Vault |
| **Updates** | Manual rebuild | Automatic on git push |
| **Monitoring** | Docker logs | Azure Monitor + Logs |
| **Access** | localhost only | Public URL |

## Next Steps

- **For local development**: See `README.md`
- **For Azure deployment**: See `azure-setup.md`
- **For CI/CD details**: See `.github/workflows/azure-deploy.yml`
