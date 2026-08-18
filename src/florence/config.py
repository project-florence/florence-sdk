"""Florence SDK yapilandirmasi.

Ortam degiskenleri:
- ``FLORENCE_API_URL``: API taban URL'i (default ``https://api.florencex.com.tr``).
  Yerel gelistirme icin ornek: ``FLORENCE_API_URL=http://localhost:7055``.
- ``FLORENCE_TOKEN``: Hazir erisim token'i (JWT). Ayarlanirsa ``AuthManager``
  bu token'i token store'dan ONCE kullanir (salt-okunur override).
- ``FLORENCE_TIMEOUT_CONNECT`` / ``FLORENCE_TIMEOUT_READ`` /
  ``FLORENCE_TIMEOUT_WRITE`` / ``FLORENCE_TIMEOUT_POOL``: saniye cinsinden
  timeout override'lari.

Tum endpoint path'leri ``/api/v1`` prefix'i altinda tanimlidir (openapi.json).
"""

from __future__ import annotations

import os

import httpx

__all__ = [
    "API_PREFIX",
    "DEFAULT_API_URL",
    "DEFAULT_HEADERS",
    "DEFAULT_TIMEOUTS",
    "EXPORT_DOWNLOAD_TIMEOUT",
    "KEYRING_SERVICE",
    "get_base_url",
]

#: Backend ana prefix'i (openapi.json'dan birebir).
API_PREFIX = "/api/v1"

#: Uretim API adresi; ``FLORENCE_API_URL`` ile override edilebilir.
DEFAULT_API_URL = "https://api.florencex.com.tr"

#: keyring servis adi (token'lar bu servis altinda saklanir).
KEYRING_SERVICE = "florence-sdk"

#: Her istekte gonderilen varsayilan header'lar.
DEFAULT_HEADERS: dict[str, str] = {
    "Accept": "application/json",
    "User-Agent": "florence-sdk/0.2.0",
}

#: Varsayilan timeout'lar (saniye). Connect 10s, read 30s.
DEFAULT_TIMEOUTS = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)

#: Export indirme gibi uzun surebilen istekler icin timeout (read 300s).
EXPORT_DOWNLOAD_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)


def get_base_url() -> str:
    """Ayarlanmis base URL'i dondurur (env oncelikli, default uretim)."""
    return os.environ.get("FLORENCE_API_URL", DEFAULT_API_URL).rstrip("/")


def get_timeouts() -> httpx.Timeout:
    """Ortam degiskenleriyle override edilebilen timeout seti."""
    connect = float(os.environ.get("FLORENCE_TIMEOUT_CONNECT", DEFAULT_TIMEOUTS.connect))
    read = float(os.environ.get("FLORENCE_TIMEOUT_READ", DEFAULT_TIMEOUTS.read))
    write = float(os.environ.get("FLORENCE_TIMEOUT_WRITE", DEFAULT_TIMEOUTS.write))
    pool = float(os.environ.get("FLORENCE_TIMEOUT_POOL", DEFAULT_TIMEOUTS.pool))
    return httpx.Timeout(connect=connect, read=read, write=write, pool=pool)
