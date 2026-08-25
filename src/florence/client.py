"""Senkron + asenkron HTTP transport ve retry/refresh mantigi.

Mimari:
- ``_BaseClient``: ortak durum (base URL, auth, resource katmani) ve saf
  yardimcilar (URL birlestirme, backoff hesabi, hata esleme, JSON normalizasyonu).
- ``FlorenceClient``: senkron (``httpx.Client``) — ``request()`` dogrudan sonuc dondurur.
- ``AsyncFlorenceClient``: asenkron (``httpx.AsyncClient``) — ``request()`` bir
  coroutine dondurur, ``await`` edilir.

Ortak davranislar:
- 429 ve 5xx'te retry: exponential backoff, ``Retry-After`` header'ina saygi,
  ``max_retries`` ayarlanabilir (default 2).
- 401'de tek seferlik single-flight refresh + istegin yeniden denenmesi
  (refresh basarisizsa ``AuthError``).
- ``Authorization: Bearer`` header'i ``AuthManager``'dan otomatik eklenir.
- Loglama: token/sifre asla loglanmaz.

Resource katmani client ustune kurulur: ``client.market.price_history("THYAO")``
gibi; senkron client'ta dogrudan, asenkron client'ta ``await`` ile cagrilir.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from .auth import AuthManager, TokenStore
from .config import DEFAULT_HEADERS, get_base_url, get_timeouts
from .errors import NetworkError, build_error

__all__ = ["AsyncFlorenceClient", "FlorenceClient"]

logger = logging.getLogger(__name__)

#: Retry edilebilir durum kodlari.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

#: Backoff ust siniri (saniye).
MAX_BACKOFF_SECONDS = 8.0

JSONValue = dict[str, Any] | list[Any] | str | int | float | bool | None


def parse_json_body(response: httpx.Response) -> JSONValue:
    """STANDART CIKTI: yanit gövdesini normalize eder.

    - Bos gövde -> ``None``
    - JSON -> dict/list (parse edilmis)
    - JSON degil -> ham metin (str)
    """
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """``Retry-After`` header'ini saniyeye cevirir; yoksa ``None``."""
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _backoff_delay(attempt: int, retry_after: float | None) -> float:
    """Retry oncesi bekleme: ``Retry-After`` varsa ona saygi, yoksa 2^attempt."""
    if retry_after is not None:
        return retry_after
    return min(2.0**attempt, MAX_BACKOFF_SECONDS)


class _BaseClient:
    """Ortak durum ve yardimcilar (transport'u alt siniflar saglar)."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token_store: TokenStore | None = None,
        max_retries: int = 2,
        timeout: httpx.Timeout | None = None,
        headers: dict[str, str] | None = None,
        keyring_service: str = "florence-sdk",
    ) -> None:
        self.base_url = (base_url or get_base_url()).rstrip("/")
        self.max_retries = max(0, max_retries)
        self.timeout = timeout or get_timeouts()
        self._default_headers = {**DEFAULT_HEADERS, **(headers or {})}
        self.auth = AuthManager(
            client=self, token_store=token_store, keyring_service=keyring_service
        )
        self._build_resources()

    # ------------------------------------------------------------------
    # Resource katmani (tek tanim, iki client'ta da ayni)
    # ------------------------------------------------------------------
    def _build_resources(self) -> None:
        from .resources import (  # local import: dongusel bagimliligi onler
            AnalysisResource,
            AuthResource,
            BotsResource,
            DigestResource,
            EconomyResource,
            ExportResource,
            MarketResource,
            MiscResource,
            PortfolioResource,
            UserResource,
        )

        self.auth_res = AuthResource(self)
        self.user = UserResource(self)
        self.market = MarketResource(self)
        self.economy = EconomyResource(self)
        self.portfolio = PortfolioResource(self)
        self.analysis = AnalysisResource(self)
        self.bots = BotsResource(self)
        self.export = ExportResource(self)
        self.misc = MiscResource(self)
        self.digest = DigestResource(self)

    # ------------------------------------------------------------------
    # Yardimcilar
    # ------------------------------------------------------------------
    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}{path}"

    def _auth_headers(self) -> dict[str, str]:
        token = self.auth.access_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def _clear_cookies(self) -> None:
        """Login/refresh sonrasi cookie jar'ini temizler (bayat cookie guvenligi)."""
        try:
            jar = self._http.cookies
            if jar is not None:
                jar.clear()
        except AttributeError:
            pass

    def _handle_response(self, response: httpx.Response, *, raw: bool = False) -> Any:
        if response.status_code >= 400:
            raise build_error(response)
        if raw:
            return response
        return parse_json_body(response)

    # ------------------------------------------------------------------
    # Kullanici dostu auth kisa yollari
    # ------------------------------------------------------------------
    def login(self, username: str, password: str) -> Any:
        """Kisa yol: ``self.auth.login(...)``."""
        return self.auth.login(username, password)

    def logout(self) -> Any:
        return self.auth.logout()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> FlorenceClient:
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        self.close()
        return False


class FlorenceClient(_BaseClient):
    """Senkron Florence API client (httpx.Client tabanli).

    Ornek:
        with FlorenceClient(token_store=MemoryTokenStore()) as client:
            client.login("kullanici", "sifre")
            data = client.market.price_history("THYAO", period="1mo")
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token_store: TokenStore | None = None,
        max_retries: int = 2,
        timeout: httpx.Timeout | None = None,
        headers: dict[str, str] | None = None,
        **httpx_kwargs: Any,
    ) -> None:
        super().__init__(
            base_url=base_url,
            token_store=token_store,
            max_retries=max_retries,
            timeout=timeout,
            headers=headers,
        )
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self._default_headers,
            **httpx_kwargs,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
        timeout: httpx.Timeout | float | None = None,
        retry: bool = True,
        raw: bool = False,
    ) -> Any:
        """Senkron istek; normalized JSON (veya ``raw=True`` ise ``httpx.Response``) dondurur."""
        method = method.upper()
        refreshed = False
        attempt = 0
        while True:
            req_headers: dict[str, str] = {}
            if auth:
                req_headers.update(self._auth_headers())
            if headers:
                req_headers.update(headers)
            try:
                response = self._http.request(
                    method,
                    self._url(path),
                    params=params,
                    json=json,
                    data=data,
                    headers=req_headers or None,
                    timeout=timeout,
                )
            except httpx.HTTPError as exc:
                if retry and attempt < self.max_retries:
                    time.sleep(_backoff_delay(attempt, None))
                    attempt += 1
                    continue
                raise NetworkError(f"Baglanti hatasi: {exc}") from exc

            if response.status_code == 401 and auth and not refreshed:
                # Refresh sonrasi yeniden deneme retry hakkini tuketmez.
                refreshed = True
                self.auth.refresh()  # basarisizsa AuthError yukselir
                continue
            if (
                retry
                and response.status_code in RETRYABLE_STATUSES
                and attempt < self.max_retries
            ):
                time.sleep(_backoff_delay(attempt, _retry_after_seconds(response)))
                attempt += 1
                continue
            return self._handle_response(response, raw=raw)

    # ------------------------------------------------------------------
    # Senkron kisa yollar
    # ------------------------------------------------------------------
    def refresh(self) -> Any:
        return self.auth.refresh()


class AsyncFlorenceClient(_BaseClient):
    """Asenkron Florence API client (httpx.AsyncClient tabanli).

    TUM metotlar ``await`` edilir; istekler asla senkron bloklamaz.

    Ornek:
        async with AsyncFlorenceClient(token_store=MemoryTokenStore()) as client:
            await client.login_async("kullanici", "sifre")
            data = await client.market.price_history("THYAO", period="1mo")
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token_store: TokenStore | None = None,
        max_retries: int = 2,
        timeout: httpx.Timeout | None = None,
        headers: dict[str, str] | None = None,
        **httpx_kwargs: Any,
    ) -> None:
        super().__init__(
            base_url=base_url,
            token_store=token_store,
            max_retries=max_retries,
            timeout=timeout,
            headers=headers,
        )
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self._default_headers,
            **httpx_kwargs,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
        timeout: httpx.Timeout | float | None = None,
        retry: bool = True,
        raw: bool = False,
    ) -> Any:
        """Asenkron istek; normalized JSON (veya ``raw=True`` ise ``httpx.Response``)."""
        method = method.upper()
        refreshed = False
        attempt = 0
        while True:
            req_headers: dict[str, str] = {}
            if auth:
                req_headers.update(self._auth_headers())
            if headers:
                req_headers.update(headers)
            try:
                response = await self._http.request(
                    method,
                    self._url(path),
                    params=params,
                    json=json,
                    data=data,
                    headers=req_headers or None,
                    timeout=timeout,
                )
            except httpx.HTTPError as exc:
                if retry and attempt < self.max_retries:
                    await asyncio.sleep(_backoff_delay(attempt, None))
                    attempt += 1
                    continue
                raise NetworkError(f"Baglanti hatasi: {exc}") from exc

            if response.status_code == 401 and auth and not refreshed:
                # Refresh sonrasi yeniden deneme retry hakkini tuketmez.
                refreshed = True
                await self.auth.refresh_async()  # basarisizsa AuthError yukselir
                continue
            if (
                retry
                and response.status_code in RETRYABLE_STATUSES
                and attempt < self.max_retries
            ):
                await asyncio.sleep(_backoff_delay(attempt, _retry_after_seconds(response)))
                attempt += 1
                continue
            return self._handle_response(response, raw=raw)

    # ------------------------------------------------------------------
    # Asenkron kisa yollar
    # ------------------------------------------------------------------
    async def login_async(self, username: str, password: str) -> Any:
        return await self.auth.login_async(username, password)

    async def refresh_async(self) -> Any:
        return await self.auth.refresh_async()

    async def logout_async(self) -> Any:
        return await self.auth.logout_async()

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncFlorenceClient:
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        await self.close()
        return False
