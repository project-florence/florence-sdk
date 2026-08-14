"""Hata hiyerarsisi testleri: kod esleme, alt tipler, Retry-After."""

from __future__ import annotations

import httpx

from florence.errors import (
    AuthError,
    FlorenceAPIError,
    FlorenceError,
    NetworkError,
    RateLimitError,
    build_error,
)


def test_hierarchy():
    assert issubclass(FlorenceAPIError, FlorenceError)
    assert issubclass(AuthError, FlorenceAPIError)
    assert issubclass(RateLimitError, FlorenceAPIError)
    assert issubclass(NetworkError, FlorenceError)


def test_i18n_code_mapping():
    """Backend ``{"detail": "error_login_failed"}`` -> ``code`` olarak yuzeye cikar."""
    resp = httpx.Response(400, json={"detail": "error_login_failed"})
    err = build_error(resp)
    assert isinstance(err, FlorenceAPIError)
    assert err.status_code == 400
    assert err.code == "error_login_failed"
    assert "error_login_failed" in str(err)


def test_username_taken_code():
    resp = httpx.Response(409, json={"detail": "error_username_taken"})
    err = build_error(resp)
    assert err.code == "error_username_taken"
    assert err.status_code == 409


def test_bots_not_allowed_code():
    resp = httpx.Response(403, json={"detail": "error_bots_not_allowed"})
    err = build_error(resp)
    assert err.code == "error_bots_not_allowed"


def test_401_maps_to_auth_error():
    resp = httpx.Response(401, json={"detail": "Invalid or expired token"})
    err = build_error(resp)
    assert isinstance(err, AuthError)
    assert err.code == "Invalid or expired token"


def test_429_maps_to_rate_limit_error_with_retry_after():
    resp = httpx.Response(429, headers={"Retry-After": "42"}, json={"detail": "Too many requests"})
    err = build_error(resp)
    assert isinstance(err, RateLimitError)
    assert err.retry_after == 42.0
    assert err.status_code == 429


def test_429_without_retry_after():
    resp = httpx.Response(429, json={"detail": "Too many requests. Please slow down."})
    err = build_error(resp)
    assert isinstance(err, RateLimitError)
    assert err.retry_after is None


def test_http_date_retry_after():
    from email.utils import formatdate

    resp = httpx.Response(
        429,
        headers={"Retry-After": formatdate(timeval=86400, usegmt=True)},
        json={"detail": "x"},
    )
    err = build_error(resp)
    assert isinstance(err, RateLimitError)
    assert err.retry_after is not None and err.retry_after >= 0


def test_validation_error_detail_kept():
    """422 gövdesi dict/list ise ``code`` None, ``detail`` ham kalir."""
    resp = httpx.Response(
        422,
        json={"detail": [{"loc": ["body", "year"], "msg": "Input should be a valid integer"}]},
    )
    err = build_error(resp)
    assert err.code is None
    assert isinstance(err.detail, list)


def test_non_json_error_body():
    resp = httpx.Response(500, text="Internal Server Error")
    err = build_error(resp)
    assert err.code is None
    assert err.detail == "Internal Server Error"


def test_plain_4xx_is_florence_api_error():
    resp = httpx.Response(404, json={"detail": "Export not found"})
    err = build_error(resp)
    assert isinstance(err, FlorenceAPIError)
    assert not isinstance(err, AuthError)
    assert not isinstance(err, RateLimitError)
