"""Ortak test fixture'lari.

Tum testler OFFLINE: canli backend yok, butun HTTP istekleri respx ile
mocklanir. Varsayilan base URL: ``https://api.florencex.com.tr``.
"""

from __future__ import annotations

import pytest

API = "https://api.florencex.com.tr"
PREFIX = f"{API}/api/v1"


@pytest.fixture
def base_url() -> str:
    return API


@pytest.fixture
def api_prefix() -> str:
    return PREFIX
