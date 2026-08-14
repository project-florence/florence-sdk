"""Hata hiyerarsisi.

Backend hata formati: ``{"detail": "error_kodu"}`` (i18n kodlari, ornek:
``error_login_failed``, ``error_username_taken``, ``error_bots_not_allowed``).
SDK bu kodu ``FlorenceAPIError.code`` olarak yuzeye cikarir.

Esleme kurallari:
- 4xx/5xx -> ``FlorenceAPIError`` (alt tipleri: ``AuthError`` 401, ``RateLimitError`` 429)
- Baglanti/zaman asimi hatalari -> ``NetworkError``
- ``Retry-After`` header'i varsa ``RateLimitError.retry_after`` (saniye) olarak tasinir.
"""

from __future__ import annotations

import email.utils
from datetime import UTC, datetime
from typing import Any

import httpx

__all__ = [
    "AuthError",
    "FlorenceAPIError",
    "FlorenceError",
    "NetworkError",
    "RateLimitError",
    "build_error",
]


class FlorenceError(Exception):
    """Tum SDK hatalarinin tabani."""


class FlorenceAPIError(FlorenceError):
    """Backend'den gelen HTTP hatasi.

    Attributes:
        status_code: HTTP durum kodu (401, 403, 429, ...).
        code: Backend'in ``detail`` alanindan cikarilan i18n hata kodu
            (orn. ``"error_login_failed"``). ``detail`` bir string degilse ``None``.
        detail: Ham hata detayi (string, dict veya list olabilir).
    """

    def __init__(
        self,
        status_code: int,
        code: str | None = None,
        detail: Any = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.detail = detail
        message = f"Florence API hatasi {status_code}"
        if code:
            message += f": {code}"
        elif detail is not None:
            message += f": {detail!r}"
        super().__init__(message)


class AuthError(FlorenceAPIError):
    """401: kimlik dogrulama basarisiz (token gecersiz/sure dolmus, refresh olmaz)."""


class RateLimitError(FlorenceAPIError):
    """429: rate limit asildi.

    Attributes:
        retry_after: ``Retry-After`` header'indan okunan bekleme suresi (saniye);
            header yoksa ``None``.
    """

    def __init__(
        self,
        status_code: int,
        code: str | None = None,
        detail: Any = None,
        retry_after: float | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(status_code, code, detail)
        if retry_after is not None:
            self.args = (f"{self.args[0]} (retry_after={retry_after}s)",)


class NetworkError(FlorenceError):
    """Baglanti kurulamadi, zaman asimi veya protokol hatasi (httpx tarafi)."""


def _extract_detail(response: httpx.Response) -> tuple[str | None, Any]:
    """Yanittan (code, detail) cikarir. ``detail`` string ise i18n kodu kabul edilir."""
    try:
        body = response.json()
    except ValueError:
        return None, response.text[:300] or None
    if isinstance(body, dict) and "detail" in body:
        detail = body["detail"]
        if isinstance(detail, str):
            return detail, detail
        return None, detail
    return None, body


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """``Retry-After`` header'ini saniyeye cevirir (int veya HTTP-date destegi)."""
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return max(0.0, (dt - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError):
        return None


def build_error(response: httpx.Response) -> FlorenceAPIError:
    """Bir HTTP yanitini uygun hata nesnesine cevirir."""
    code, detail = _extract_detail(response)
    if response.status_code == 429:
        return RateLimitError(
            response.status_code,
            code,
            detail,
            retry_after=_retry_after_seconds(response),
        )
    if response.status_code == 401:
        return AuthError(response.status_code, code, detail)
    return FlorenceAPIError(response.status_code, code, detail)
