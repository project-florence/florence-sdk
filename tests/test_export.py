"""Export akisi testleri: create -> poll (wait) -> download (token URL).

Backend gercegi (exports.py ile birebir):
- POST /data/export -> 202 ``{export_id, status}`` (queued)
- GET /data/export/{id} -> ``{id, year, format, status, download_url, ...}``
- GET /data/export/download/{token} -> PUBLIC, gzip dosya (auth YOK)
- Durum terminal degilse 410 (expired/not ready)
TAMAMEN OFFLINE (httpx.MockTransport).
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from florence import AsyncFlorenceClient, FlorenceClient, MemoryTokenStore
from florence.models import ExportRecord

API = "https://api.florencex.com.tr"
P = f"{API}/api/v1"

GZIP_BYTES = b"\x1f\x8b\x08\x00mock-gzip-content"


def _export_record(export_id: int, status: str, token: str | None = None) -> dict:
    rec = {
        "id": export_id,
        "year": 2025,
        "format": "csv",
        "status": status,
        "created_at": "2026-08-01T10:00:00+00:00",
        "updated_at": "2026-08-01T10:00:01+00:00",
        "row_count": 250,
        "size_bytes": 1234,
        "downloaded_count": 0,
        "expires_at": "2026-09-01T10:00:00+00:00",
        "error": None,
        "downloadable": status in ("ready", "sent"),
        "download_url": f"/api/v1/data/export/download/{token}" if token else None,
    }
    return rec


def _export_handler(export_id: int) -> httpx.MockTransport:
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/data/export") and request.method == "POST":
            body = json.loads(request.content)
            assert body["year"] == 2025
            assert body["format"] == "csv"
            return httpx.Response(202, json={"export_id": export_id, "status": "queued"})
        if path.endswith(f"/data/export/{export_id}"):
            state["polls"] += 1
            if state["polls"] < 3:
                return httpx.Response(200, json=_export_record(export_id, "processing"))
            return httpx.Response(200, json=_export_record(export_id, "ready", token="tok-123"))
        if path.endswith("/data/export/download/tok-123"):
            return httpx.Response(
                200,
                content=GZIP_BYTES,
                headers={"Content-Type": "application/gzip", "Content-Disposition": 'attachment; filename="florence-daily-2025.csv.gz"'},
            )
        return httpx.Response(404, json={"detail": "unmocked"})

    return httpx.MockTransport(handler)


def _client(handler: httpx.MockTransport) -> FlorenceClient:
    store = MemoryTokenStore()
    store.set_tokens("at-1", "rt-1")
    return FlorenceClient(token_store=store, transport=handler, max_retries=0)


def test_export_create_returns_202():
    client = _client(_export_handler(7))
    result = client.export.create_export(2025, format="csv")
    assert result == {"export_id": 7, "status": "queued"}
    client.close()


def test_export_get_and_list():
    client = _client(_export_handler(7))
    rec = client.export.get_export(7)
    assert rec["id"] == 7
    assert rec["status"] in ("processing", "ready")
    assert ExportRecord.model_validate(rec).year == 2025
    client.close()


def test_export_list():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/data/export") and request.method == "GET":
            return httpx.Response(200, json=[_export_record(7, "ready", token="tok-1")])
        return httpx.Response(404, json={"detail": "unmocked"})

    client = _client(httpx.MockTransport(handler))
    exports = client.export.list_exports()
    assert isinstance(exports, list)
    assert exports[0]["downloadable"] is True
    client.close()


def test_export_wait_polls_until_ready():
    client = _client(_export_handler(7))
    record = client.export.wait_export(7, poll_interval=0.0, timeout=10.0)
    assert record["status"] == "ready"
    assert record["download_url"] == "/api/v1/data/export/download/tok-123"
    client.close()


def test_export_wait_timeout():
    handler = httpx.MockTransport(
        lambda req: httpx.Response(200, json=_export_record(7, "processing"))
    )
    client = _client(handler)
    with pytest.raises(TimeoutError):
        client.export.wait_export(7, poll_interval=0.0, timeout=0.0)
    client.close()


def test_export_download_public_token_to_file(tmp_path):
    client = _client(_export_handler(7))
    dest = tmp_path / "florence-2025.csv.gz"
    result = client.export.download("tok-123", str(dest))
    assert result == str(dest)
    assert dest.read_bytes() == GZIP_BYTES
    client.close()


def test_export_download_with_full_url():
    """Export kaydindaki download_url (path) veya token kabul edilir."""
    client = _client(_export_handler(7))
    content = client.export.download("/api/v1/data/export/download/tok-123")
    assert content == GZIP_BYTES
    client.close()


def test_export_full_flow_sync(tmp_path):
    """create -> wait -> download: uc adimli tam OFFLINE akis."""
    client = _client(_export_handler(42))
    created = client.export.create_export(2025)
    assert created["status"] == "queued"
    record = client.export.wait_export(created["export_id"], poll_interval=0.0, timeout=10.0)
    dest = tmp_path / "export.csv.gz"
    client.export.download(record["download_url"], str(dest))
    assert dest.read_bytes() == GZIP_BYTES
    client.close()


def test_export_download_expired_raises_410():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/data/export/download/bayat"):
            return httpx.Response(410, json={"detail": "Export link expired or not ready"})
        return httpx.Response(404, json={"detail": "unmocked"})

    from florence import FlorenceAPIError

    client = _client(httpx.MockTransport(handler))
    with pytest.raises(FlorenceAPIError) as exc:
        client.export.download("bayat")
    assert exc.value.status_code == 410
    client.close()


def test_export_async_full_flow(tmp_path):
    """Asenkron client: create -> wait_export_async -> download_async."""
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/data/export") and request.method == "POST":
            return httpx.Response(202, json={"export_id": 5, "status": "queued"})
        if path.endswith("/data/export/5"):
            state["polls"] += 1
            if state["polls"] < 2:
                return httpx.Response(200, json=_export_record(5, "processing"))
            return httpx.Response(200, json=_export_record(5, "sent", token="tok-abc"))
        if path.endswith("/data/export/download/tok-abc"):
            return httpx.Response(200, content=GZIP_BYTES)
        return httpx.Response(404, json={"detail": "unmocked"})

    async def run() -> None:
        async with AsyncFlorenceClient(
            token_store=MemoryTokenStore(), transport=httpx.MockTransport(handler), max_retries=0
        ) as client:
            created = await client.export.create_export(2025, format="json")
            assert created["export_id"] == 5
            record = await client.export.wait_export_async(5, poll_interval=0.0, timeout=10.0)
            assert record["status"] == "sent"
            content = await client.export.download_async("tok-abc")
            assert content == GZIP_BYTES

    asyncio.run(run())
