"""Veri disa aktarim (export) endpoint'leri.

Akis (poll tabanli, mail gerektirmez):
1. ``create_export(year, format)`` -> 202 ``{export_id, status}`` (idempotent,
   3 export/saat)
2. ``wait_export(export_id, ...)`` -> ``ready``/``sent`` olana kadar poll
3. ``download(token, dest_path)`` -> PUBLIC token ile indirme (gzip dosya)

Status degerleri: queued | processing | ready | sent | error.
Token suresi dolmus/henuz hazir degilse backend 410 dondurur.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from ..config import EXPORT_DOWNLOAD_TIMEOUT
from .base import BaseResource

__all__ = ["ExportResource"]

#: Poll isleminde kabul edilen terminal durumlar.
_TERMINAL_STATUSES = frozenset({"ready", "sent", "error"})


class ExportResource(BaseResource):
    """POST /data/export — export siparisi ver (JWT; 202).

    Body: ``{year, format: csv|json}`` (format default csv). Ayni user+year+
    format icin aktif kayit varsa mevcut ``export_id`` donulur (idempotent).
    """

    def create_export(self, year: int, format: str = "csv") -> Any:
        return self._request(
            "POST",
            "/data/export",
            json={"year": year, "format": format},
        )

    """GET /data/export/{export_id} — tek export kaydi (JWT; owner-only)."""

    def get_export(self, export_id: int) -> Any:
        return self._request("GET", f"/data/export/{export_id}")

    """GET /data/export — export listesi (JWT)."""

    def list_exports(self) -> Any:
        return self._request("GET", "/data/export")

    def wait_export(
        self,
        export_id: int,
        poll_interval: float = 3.0,
        timeout: float = 300.0,
    ) -> Any:
        """Export kaydi ``ready``/``sent`` olana kadar poll et (SENKRON).

        Her poll ``GET /data/export/{export_id}`` cagirir; ``timeout`` asilirsa
        ``TimeoutError`` firlatir. Durum ``error`` olursa kayit yine dondurulur
        (cagiran hata durumunu kayittan okur).
        """
        deadline = time.monotonic() + timeout
        while True:
            record = self.get_export(export_id)
            if record.get("status") in _TERMINAL_STATUSES:
                return record
            if time.monotonic() >= deadline:
                status = record.get("status")
                raise TimeoutError(
                    f"Export {export_id} {timeout}s icinde hazir olmadi (son durum: {status})"
                )
            time.sleep(max(0.0, poll_interval))

    async def wait_export_async(
        self,
        export_id: int,
        poll_interval: float = 3.0,
        timeout: float = 300.0,
    ) -> Any:
        """Export kaydi ``ready``/``sent`` olana kadar poll et (ASENKRON)."""
        deadline = time.monotonic() + timeout
        while True:
            record = await self.get_export(export_id)
            if record.get("status") in _TERMINAL_STATUSES:
                return record
            if time.monotonic() >= deadline:
                status = record.get("status")
                raise TimeoutError(
                    f"Export {export_id} {timeout}s icinde hazir olmadi (son durum: {status})"
                )
            await asyncio.sleep(max(0.0, poll_interval))

    def download(self, token_or_url: str, dest_path: str | None = None) -> Any:
        """PUBLIC export indirme — auth gerekmez (SENKRON).

        ``token_or_url``: export kaydindaki ham token VEYA ``download_url``
        (``/api/v1/data/export/download/<token>``) olabilir. ``dest_path``
        verilirse gzip icerik dosyaya yazilir ve yol dondurulur; verilmezse
        ham bytes dondurulur.
        """
        path = self._resolve_download_path(token_or_url)
        response = self._request(
            "GET",
            path,
            auth=False,
            timeout=EXPORT_DOWNLOAD_TIMEOUT,
            raw=True,
        )
        content = response.content
        if dest_path:
            Path(dest_path).write_bytes(content)
            return dest_path
        return content

    async def download_async(self, token_or_url: str, dest_path: str | None = None) -> Any:
        """PUBLIC export indirme — auth gerekmez (ASENKRON)."""
        path = self._resolve_download_path(token_or_url)
        response = await self._request(
            "GET",
            path,
            auth=False,
            timeout=EXPORT_DOWNLOAD_TIMEOUT,
            raw=True,
        )
        content = response.content
        if dest_path:
            Path(dest_path).write_bytes(content)
            return dest_path
        return content

    @staticmethod
    def _resolve_download_path(token_or_url: str) -> str:
        """Token veya download_url'i istek path'ine cevirir."""
        token = token_or_url
        if "/data/export/download/" in token_or_url:
            token = token_or_url.rsplit("/data/export/download/", 1)[-1]
        return f"/data/export/download/{token}"
