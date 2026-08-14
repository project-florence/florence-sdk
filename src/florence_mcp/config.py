"""MCP server yapilandirmasi — ``MCP_*`` ortam degiskenleri.

Tum degiskenler istege baglidir; SDK'nin ``FLORENCE_API_URL`` /
``FLORENCE_TOKEN`` degiskenleri her durumda gecerli kalir (kimlik zinciri
``auth.py``'de, Bölüm 3.1).

Ortam degiskenleri:
- ``MCP_FLORENCE_BOT``: bot profili (sunucu baslangicinda bot olarak login).
- ``MCP_FLORENCE_BOT_PASSWORD``: bot sifresi (gecici/CI kullanimi; yoksa
  keyring/FileTokenStore'daki kayitli sifre kullanilir).
- ``MCP_DOWNLOAD_DIR``: ``dest_path`` icin varsayilan dizin (path traversal
  korumali — ``files.py``). Yoksa calisma dizini kullanilir.
- ``MCP_REPORT_TIMEOUT``: ``analysis_generate_report`` read timeout (saniye,
  default 180 — backend senkron doner).
- ``MCP_REPORT_DOWNLOAD_TIMEOUT``: ``analysis_download_report`` read timeout
  (saniye, default 60).
- ``MCP_DISABLE_GROUPS``: virgulle ayrilmis grup listesi (orn.
  ``admin,export``) — bu gruplarin tool'lari kaydedilmez.
"""

from __future__ import annotations

import os

__all__ = [
    "DEFAULT_DOWNLOAD_DIR",
    "DEFAULT_REPORT_DOWNLOAD_TIMEOUT",
    "DEFAULT_REPORT_TIMEOUT",
    "get_download_dir",
    "get_disabled_groups",
    "get_report_download_timeout",
    "get_report_timeout",
]


def get_download_dir() -> str:
    """``dest_path`` varsayilan dizini (``MCP_DOWNLOAD_DIR``, yoksa cwd)."""
    return os.environ.get("MCP_DOWNLOAD_DIR") or os.getcwd()


def get_report_timeout() -> float:
    """``analysis_generate_report`` icin read timeout (saniye)."""
    return float(os.environ.get("MCP_REPORT_TIMEOUT", DEFAULT_REPORT_TIMEOUT))


def get_report_download_timeout() -> float:
    """``analysis_download_report`` icin read timeout (saniye)."""
    return float(
        os.environ.get("MCP_REPORT_DOWNLOAD_TIMEOUT", DEFAULT_REPORT_DOWNLOAD_TIMEOUT)
    )


def get_disabled_groups() -> set[str]:
    """``MCP_DISABLE_GROUPS`` ile kapatilan gruplarin kumesi."""
    raw = os.environ.get("MCP_DISABLE_GROUPS", "")
    return {g.strip() for g in raw.split(",") if g.strip()}


#: Varsayilanlar (overridable).
DEFAULT_DOWNLOAD_DIR: str = "."
DEFAULT_REPORT_TIMEOUT: float = 180.0
DEFAULT_REPORT_DOWNLOAD_TIMEOUT: float = 60.0
