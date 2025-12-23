# Azure AD Application Permissions Setup

This guide explains how to configure Azure AD application permissions for client credentials flow in Azure Container Apps.

## Overview

The application now supports two authentication modes:

1. **Device Code Flow** (local development): Interactive authentication with delegated permissions
2. **Client Credentials Flow** (production/Azure): Unattended authentication with application permissions

## Prerequisites

- Azure AD application registration (already created)
- Azure CLI installed and authenticated
- Admin consent capability for your Azure AD tenant

## Step 1: Add Application Permissions to Azure AD App

Run these commands to add the required Microsoft Graph application permissions:

```powershell
# Get your app registration object ID
$APP_ID = "<your-azure-client-id>"
$APP_OBJECT_ID = az ad app show --id $APP_ID --query id -o tsv

# Microsoft Graph API ID
$GRAPH_API_ID = "00000003-0000-0000-c000-000000000000"

# Add Mail.ReadWrite application permission (role ID)
$MAIL_READWRITE_ROLE = "e2a3a72e-5f79-4c64-b1b1-878b674786c9"

az ad app permission add `
  --id $APP_OBJECT_ID `
  --api $GRAPH_API_ID `
  --api-permissions "$MAIL_READWRITE_ROLE=Role"

# Add Mail.Send application permission (role ID)
$MAIL_SEND_ROLE = "b633e1c5-b582-4048-a93e-9f11b44c7e96"

az ad app permission add `
  --id $APP_OBJECT_ID `
  --api $GRAPH_API_ID `
  --api-permissions "$MAIL_SEND_ROLE=Role"
```

## Step 2: Grant Admin Consent

Application permissions require admin consent:

```powershell
# Grant admin consent for the permissions
az ad app permission admin-consent --id $APP_OBJECT_ID
```

**Alternative**: Go to Azure Portal → Azure Active Directory → App registrations → Your App → API permissions → Grant admin consent

## Step 3: Configure Container App Environment Variables

Add the required environment variables to your Azure Container App:

```powershell
$RESOURCE_GROUP = "outlook-categorizer-rg"
$CONTAINER_APP = "outlook-categorizer"
$KEYVAULT_NAME = "outlook-cat-kv-alain"

# Add TARGET_USER_PRINCIPAL_NAME to Key Vault
az keyvault secret set `
  --vault-name $KEYVAULT_NAME `
  --name TARGET-USER-PRINCIPAL-NAME `
  --value "your-email@domain.com"

# Update Container App to include the new secret
az containerapp update `
  --name $CONTAINER_APP `
  --resource-group $RESOURCE_GROUP `
  --set-env-vars `
    "GROQ_API_KEY=secretref:groq-api-key" `
    "AZURE_TENANT_ID=secretref:azure-tenant-id" `
    "AZURE_CLIENT_ID=secretref:azure-client-id" `
    "AZURE_CLIENT_SECRET=secretref:azure-client-secret" `
    "TARGET_USER_PRINCIPAL_NAME=secretref:target-user-principal-name"
```

## Step 4: Add Secret Reference to Container App

```powershell
# Add the new secret reference
az containerapp secret set `
  --name $CONTAINER_APP `
  --resource-group $RESOURCE_GROUP `
  --secrets `
    target-user-principal-name=keyvaultref:https://$KEYVAULT_NAME.vault.azure.net/secrets/TARGET-USER-PRINCIPAL-NAME,identityref:system
```

## Environment Variables Summary

For **Azure Container Apps** (client credentials flow):
- `AZURE_CLIENT_ID`: Your Azure AD app client ID
- `AZURE_CLIENT_SECRET`: Your Azure AD app client secret
- `AZURE_TENANT_ID`: Your Azure AD tenant ID
- `TARGET_USER_PRINCIPAL_NAME`: Email address of the mailbox to access
- `GROQ_API_KEY`: Your Groq API key

For **Local Development** (device code flow):
- `AZURE_CLIENT_ID`: Your Azure AD app client ID
- `AZURE_TENANT_ID`: Your Azure AD tenant ID (or "consumers" for personal accounts)
- `GROQ_API_KEY`: Your Groq API key
- Do NOT set `AZURE_CLIENT_SECRET` (this triggers client credentials mode)

## Verification

After deployment, check the logs:

```powershell
az containerapp logs show `
  --name $CONTAINER_APP `
  --resource-group $RESOURCE_GROUP `
  --follow
```

You should see:
- `Created MSAL confidential client application (client credentials flow)`
- `Using application permissions for user: your-email@domain.com`
- `Acquiring token using client credentials flow...`
- `Successfully acquired token via client credentials`

## Troubleshooting

### Error: "Insufficient privileges to complete the operation"

**Cause**: Application permissions not granted or admin consent not provided.

**Solution**: Run Step 2 again to grant admin consent.

### Error: "The user or administrator has not consented to use the application"

**Cause**: Missing admin consent for application permissions.

**Solution**: 
1. Go to Azure Portal → Azure AD → App registrations → Your App → API permissions
2. Click "Grant admin consent for [Your Tenant]"

### Error: "Resource not found for the segment 'users'"

**Cause**: `TARGET_USER_PRINCIPAL_NAME` not set or incorrect.

**Solution**: Verify the environment variable is set correctly with the user's email address.

### Local Development Still Works

The app automatically detects whether `AZURE_CLIENT_SECRET` is set:
- **If set**: Uses client credentials flow (requires `TARGET_USER_PRINCIPAL_NAME`)
- **If not set**: Uses device code flow (interactive authentication)

This allows the same codebase to work in both environments without changes.
