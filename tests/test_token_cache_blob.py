from __future__ import annotations

import types

import pytest


class _Props:
    def __init__(self, etag: str) -> None:
        self.etag = etag


class _FakeBlobClient:
    def __init__(self) -> None:
        self._data: bytes | None = None
        self._etag = '"0x1"'
        self._exists = False
        self._conflict_once = False

    def download_blob(self):
        if not self._exists:
            raise self._ResourceNotFoundError()

        stream = types.SimpleNamespace(readall=lambda: self._data or b"{}")
        return stream

    def get_blob_properties(self):
        if not self._exists:
            raise self._ResourceNotFoundError()
        return _Props(self._etag)

    def upload_blob(self, data: bytes, overwrite: bool, if_match=None):
        if not overwrite and self._exists:
            raise Exception("Already exists")

        if if_match is not None and if_match != self._etag:
            raise self._ResourceModifiedError()

        if self._conflict_once:
            self._conflict_once = False
            raise self._ResourceModifiedError()

        self._data = data
        self._exists = True
        # bump etag
        self._etag = '"0x2"'

    class _ResourceNotFoundError(Exception):
        pass

    class _ResourceModifiedError(Exception):
        pass


@pytest.fixture()
def store(monkeypatch):
    from outlook_categorizer import token_cache_blob

    fake = _FakeBlobClient()

    def _get_blob_client(self):
        return fake

    monkeypatch.setattr(token_cache_blob.BlobTokenCacheStore, "_get_blob_client", _get_blob_client)
    monkeypatch.setattr(token_cache_blob, "ResourceNotFoundError", _FakeBlobClient._ResourceNotFoundError)
    monkeypatch.setattr(token_cache_blob, "ResourceModifiedError", _FakeBlobClient._ResourceModifiedError)

    loc = token_cache_blob.BlobTokenCacheLocation(
        account_url="https://example.blob.core.windows.net",
        container_name="c",
        blob_name="b",
    )
    return token_cache_blob.BlobTokenCacheStore(loc), fake


def test_download_missing_returns_none(store):
    s, _ = store
    payload, etag = s.download()
    assert payload is None
    assert etag is None


def test_upload_create_then_download(store):
    s, _ = store
    new_etag = s.upload("{}", etag=None)
    assert new_etag == '"0x2"'
    payload, etag = s.download()
    assert payload == "{}"
    assert etag == '"0x2"'


def test_upload_etag_conflict_retries(store):
    s, fake = store
    # create first
    s.upload("{}", etag=None)
    payload, etag = s.download()
    assert etag == '"0x2"'

    # simulate conflict once
    fake._conflict_once = True

    # stale etag triggers conflict, store should retry and succeed
    new_etag = s.upload("{\"k\":1}", etag='"stale"', max_retries=3)
    assert new_etag == '"0x2"'
