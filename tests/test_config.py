"""Config testleri: env override, default URL, timeout'lar."""

from __future__ import annotations

import httpx

from florence.config import (
    API_PREFIX,
    DEFAULT_API_URL,
    DEFAULT_TIMEOUTS,
    get_base_url,
    get_timeouts,
)


def test_default_api_url():
    assert DEFAULT_API_URL == "https://api.florencex.com.tr"
    assert API_PREFIX == "/api/v1"


def test_get_base_url_env_override(monkeypatch):
    monkeypatch.setenv("FLORENCE_API_URL", "http://localhost:7055")
    assert get_base_url() == "http://localhost:7055"
    # Trailing slash temizlenir.
    monkeypatch.setenv("FLORENCE_API_URL", "http://localhost:7055/")
    assert get_base_url() == "http://localhost:7055"


def test_get_base_url_default(monkeypatch):
    monkeypatch.delenv("FLORENCE_API_URL", raising=False)
    assert get_base_url() == DEFAULT_API_URL


def test_get_timeouts_defaults():
    t = get_timeouts()
    assert t.connect == 10.0
    assert t.read == 30.0


def test_get_timeouts_env_override(monkeypatch):
    monkeypatch.setenv("FLORENCE_TIMEOUT_READ", "7.5")
    t = get_timeouts()
    assert t.read == 7.5
    assert t.connect == 10.0  # digerleri degismedi


def test_default_timeouts_is_httpx_timeout():
    assert isinstance(DEFAULT_TIMEOUTS, httpx.Timeout)
