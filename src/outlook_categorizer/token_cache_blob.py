"""Azure Blob Storage backed MSAL token cache.

Objective:
    Provide a small persistence layer to store the MSAL SerializableTokenCache
    JSON in Azure Blob Storage. This enables running delegated (device code)
    authentication in Azure Container Apps while keeping the token cache
    persistent across restarts.

Key points:
    - Uses optimistic concurrency control with blob ETags.
    - Uses DefaultAzureCredential for authentication (Managed Identity in Azure).

Operational notes:
    - The token cache contains refresh tokens. Treat blob access as sensitive.
    - Prefer restricting the container/app identity to a single container.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from azure.core.exceptions import ResourceNotFoundError, ResourceModifiedError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BlobTokenCacheLocation:
    """Location of the token cache blob.

    Args:
        account_url: Storage account blob endpoint URL.
        container_name: Blob container name.
        blob_name: Blob name inside the container.
    """

    account_url: str
    container_name: str
    blob_name: str


class BlobTokenCacheStore:
    """Store and retrieve MSAL token cache JSON from Azure Blob Storage.

    This store implements ETag-based optimistic concurrency to avoid
    overwriting updates when multiple writers are present.
    """

    def __init__(self, location: BlobTokenCacheLocation) -> None:
        """Initialize the blob token cache store.

        Args:
            location: Target blob location.
        """

        self._location = location
        self._credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)

    def _get_blob_client(self) -> BlobClient:
        """Create a BlobClient using DefaultAzureCredential.

        Returns:
            BlobClient: Configured blob client.
        """

        return BlobClient(
            account_url=self._location.account_url,
            container_name=self._location.container_name,
            blob_name=self._location.blob_name,
            credential=self._credential,
        )

    def download(self) -> Tuple[Optional[str], Optional[str]]:
        """Download the token cache JSON and its ETag.

        Returns:
            tuple[Optional[str], Optional[str]]: (cache_json, etag). If the blob
            does not exist, returns (None, None).
        """

        client = self._get_blob_client()
        try:
            stream = client.download_blob()
            data = stream.readall()
            props = client.get_blob_properties()
            etag = props.etag
            cache_json = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
            return cache_json, etag
        except ResourceNotFoundError:
            return None, None

    def upload(self, cache_json: str, etag: Optional[str], max_retries: int = 5) -> str:
        """Upload the token cache JSON using ETag concurrency.

        Args:
            cache_json: The serialized MSAL cache (JSON string).
            etag: ETag from previous download. If None, will attempt create.
            max_retries: Number of retries on ETag conflicts.

        Returns:
            str: The new ETag after upload.

        Raises:
            RuntimeError: If the cache cannot be uploaded after retries.
        """

        client = self._get_blob_client()

        for attempt in range(max_retries):
            try:
                if etag is None:
                    # Create only if it doesn't exist
                    client.upload_blob(cache_json.encode("utf-8"), overwrite=False)
                else:
                    # Overwrite only if ETag matches
                    client.upload_blob(
                        cache_json.encode("utf-8"),
                        overwrite=True,
                        if_match=etag,
                    )

                new_etag = client.get_blob_properties().etag
                return new_etag
            except ResourceModifiedError:
                # Someone updated the blob between download and upload
                logger.warning("Token cache blob ETag conflict; retrying (attempt=%s)", attempt + 1)
                latest, latest_etag = self.download()
                etag = latest_etag
                # If latest is None, try create on next loop
                if latest is None:
                    etag = None
            except Exception as exc:
                raise RuntimeError(f"Failed to upload token cache blob: {exc}") from exc

            # Small backoff
            time.sleep(0.2 * (attempt + 1))

        raise RuntimeError("Failed to upload token cache blob due to repeated ETag conflicts")


def is_valid_msal_cache_json(payload: str) -> bool:
    """Validate that a string is valid JSON for MSAL cache serialization.

    Args:
        payload: JSON string.

    Returns:
        bool: True if valid JSON, False otherwise.
    """

    try:
        json.loads(payload)
        return True
    except Exception:
        return False
