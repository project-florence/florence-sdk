"""Harici sayfa cekimi: guvenli GET (sema/SSRF guard, redirect dogrulamasi, boyut kesme).

Tasarim (helpers-design.md Bolum 3):
- Yalnizca ``http://`` / ``https://``; diger semalar reddedilir.
- Host engelleme: localhost, ``127.0.0.0/8``, ``::1``, ``10/8``, ``172.16/12``,
  ``192.168/16``, ``169.254/16`` (metadata IP'si), ``.local`` TLD. Domain ise
  cozumlenir ve tum IP'ler kontrol edilir (``_resolve_host`` — test noktasi).
- Redirect zinciri elle izlenir: **her atlama hedefi istek oncesi ayni
  guard'dan gecer** (SSRF atlama deseni: public URL -> localhost).
- Timeout: connect 5s + read varsayilan 15s (ust sinir 60s).
- Boyut: 2MB cap — ``Content-Length`` kontrolu + stream kesme (bellek guvenligi).
- TLS dogrulama acik; retry yok; UA tarayici benzeri (``FLORENCE_NEWS_UA`` ile degisir).

Altyapi hatalari (DNS/TLS/timeout/ag) ``ArticleFetchError`` firlatir
(``NetworkError`` alt tipi — CLI/MCP hata yuzeyleriyle uyumlu). Semantik
sonuclar (404, engelli host, boyut, tip) hata kodu olarak sonuc nesnesinde
doner: ``{"url", "resolved_url", "error"}``.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from ..errors import NetworkError

__all__ = [
    "ArticleFetchError",
    "DEFAULT_TIMEOUT",
    "MAX_PAGE_BYTES",
    "MAX_REDIRECTS",
    "fetch_page",
    "fetch_page_async",
    "validate_fetch_url",
]

#: Sayfa boyutu ust siniri (2MB — tasarim 3.3).
MAX_PAGE_BYTES = 2 * 1024 * 1024

#: Azami redirect atlamasi (tasarim 3.4: max 5).
MAX_REDIRECTS = 5

#: Varsayilan okuma zaman asimi (saniye; tasarim 3.3: 15s).
DEFAULT_TIMEOUT = 15.0

#: Zaman asimi ust siniri.
MAX_TIMEOUT = 60.0

_ALLOWED_SCHEMES = frozenset({"http", "https"})

#: Kabul edilen icerik tipleri (PDF/image cekilmez — v1 kapsam disi).
_HTML_TYPES = ("text/html", "application/xhtml+xml")

#: Redirect durum kodlari.
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

#: Engellenen aglar (localhost + ozel aglar + metadata).
_BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = tuple(
    ipaddress.ip_network(net)
    for net in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",  # metadata: 169.254.169.254
        "100.64.0.0/10",  # carrier-grade NAT
        "::1/128",
        "fc00::/7",  # IPv6 unique-local
        "fe80::/10",  # IPv6 link-local
    )
)


class ArticleFetchError(NetworkError):
    """Harici sayfa cekiminde altyapi hatasi (DNS/TLS/timeout/ag)."""


def _default_user_agent() -> str:
    """Tarayici benzeri User-Agent (bazi haber siteleri bot UA'yi reddeder)."""
    return os.environ.get("FLORENCE_NEWS_UA") or (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )


def _resolve_host(host: str) -> list[Any]:
    """Host adini IP'lere cozer (testlerde monkeypatch noktasi)."""
    return socket.getaddrinfo(host, None)


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(ip in net for net in _BLOCKED_NETWORKS)


def _host_is_blocked(host: str) -> bool:
    """Host engelli bir aga isaret ediyor mu? (literal veya DNS cozumleme)."""
    cleaned = (host or "").strip().strip("[]").lower().rstrip(".")
    if not cleaned:
        return True
    if cleaned == "localhost" or cleaned == "local" or cleaned.endswith(".local"):
        return True
    if cleaned.endswith(".localhost") or cleaned.endswith(".internal"):
        return True
    try:
        ip = ipaddress.ip_address(cleaned)
    except ValueError:
        ip = None
    if ip is not None:
        return _ip_is_blocked(ip)
    try:
        infos = _resolve_host(cleaned)
    except OSError:
        return False  # DNS cozulemedi -> httpx NetworkError olarak yuzeye cikar
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except (ValueError, IndexError):
            continue
        if _ip_is_blocked(addr):
            return True
    return False


def validate_fetch_url(url: str) -> str | None:
    """URL'yi sema + SSRF guard'indan gecirir; sorun varsa hata kodu doner.

    Dondurulen kodlar: ``"unsupported_scheme"`` | ``"blocked_host"`` | ``None``.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return "unsupported_scheme"
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return "unsupported_scheme"
    if not parsed.hostname:
        return "blocked_host"
    if _host_is_blocked(parsed.hostname):
        return "blocked_host"
    return None


def _http_client(read_timeout: float, user_agent: str | None) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(connect=5.0, read=read_timeout, write=10.0, pool=10.0),
        follow_redirects=False,
        verify=True,
        headers={
            "User-Agent": user_agent or _default_user_agent(),
            "Accept": "text/html,application/xhtml+xml",
        },
    )


def _async_http_client(read_timeout: float, user_agent: str | None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=read_timeout, write=10.0, pool=10.0),
        follow_redirects=False,
        verify=True,
        headers={
            "User-Agent": user_agent or _default_user_agent(),
            "Accept": "text/html,application/xhtml+xml",
        },
    )


def _bounded_timeout(timeout: float) -> float:
    return max(1.0, min(float(timeout), MAX_TIMEOUT))


def _status_error(status: int) -> str:
    """HTTP durum kodundan semantik hata kodu (404/403 oncelikli)."""
    if status == 404:
        return "http_404"
    if status == 403:
        return "http_403"
    return f"http_{status}"


def _content_type_of(response: httpx.Response) -> str:
    return (response.headers.get("content-type") or "").split(";")[0].strip().lower()


def _consume(response: httpx.Response, original: str, final_url: str) -> dict[str, Any]:
    """Yaniti okur: durum/tip/boyut kontrolleri + 2MB cap'li gövde okuma."""
    if response.status_code >= 400:
        return {"url": original, "resolved_url": final_url, "error": _status_error(response.status_code)}
    content_type = _content_type_of(response)
    if content_type and content_type not in _HTML_TYPES and not content_type.startswith("text/"):
        return {"url": original, "resolved_url": final_url, "error": "unsupported_type"}
    length_header = response.headers.get("content-length")
    if length_header:
        try:
            if int(length_header) > MAX_PAGE_BYTES:
                return {"url": original, "resolved_url": final_url, "error": "too_large"}
        except ValueError:
            pass
    chunks: list[bytes] = []
    total = 0
    too_large = False
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > MAX_PAGE_BYTES:
            too_large = True
            break
        chunks.append(chunk)
    if too_large:
        return {"url": original, "resolved_url": final_url, "error": "too_large"}
    html = b"".join(chunks).decode("utf-8", errors="replace")
    return {"url": original, "resolved_url": final_url, "html": html, "error": None}


async def _consume_async(response: httpx.Response, original: str, final_url: str) -> dict[str, Any]:
    """Asenkron yanit okuma (``_consume`` ile ayni kurallar)."""
    if response.status_code >= 400:
        return {"url": original, "resolved_url": final_url, "error": _status_error(response.status_code)}
    content_type = _content_type_of(response)
    if content_type and content_type not in _HTML_TYPES and not content_type.startswith("text/"):
        return {"url": original, "resolved_url": final_url, "error": "unsupported_type"}
    length_header = response.headers.get("content-length")
    if length_header:
        try:
            if int(length_header) > MAX_PAGE_BYTES:
                return {"url": original, "resolved_url": final_url, "error": "too_large"}
        except ValueError:
            pass
    chunks: list[bytes] = []
    total = 0
    too_large = False
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_PAGE_BYTES:
            too_large = True
            break
        chunks.append(chunk)
    if too_large:
        return {"url": original, "resolved_url": final_url, "error": "too_large"}
    html = b"".join(chunks).decode("utf-8", errors="replace")
    return {"url": original, "resolved_url": final_url, "html": html, "error": None}


def fetch_page(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str | None = None,
) -> dict[str, Any]:
    """Guvenli sayfa GET'i (senkron).

    Altyapi hatasi -> ``ArticleFetchError``. Sonuc nesnesi her durumda
    ``{"url", "resolved_url", "error"}`` icerir; hata yoksa ek ``"html"`` alani
    (UTF-8, ``errors="replace"`` ile cozulmus metin) mevcuttur.
    """
    current = url
    error = validate_fetch_url(url)
    if error:
        return {"url": url, "resolved_url": url, "error": error}
    read_timeout = _bounded_timeout(timeout)
    with _http_client(read_timeout, user_agent) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            error = validate_fetch_url(current)
            if error:
                return {"url": url, "resolved_url": url, "error": error}
            try:
                with client.stream("GET", current) as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("Location")
                        if not location:
                            return {
                                "url": url,
                                "resolved_url": current,
                                "error": _status_error(response.status_code),
                            }
                        current = urljoin(current, location)
                        continue
                    return _consume(response, url, current)
            except httpx.HTTPError as exc:
                raise ArticleFetchError(f"Sayfa cekilemedi ({current}): {exc}") from exc
    return {"url": url, "resolved_url": current, "error": "too_many_redirects"}


async def fetch_page_async(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str | None = None,
) -> dict[str, Any]:
    """Guvenli sayfa GET'i (asenkron) — ``fetch_page`` ile ayni kurallar."""
    current = url
    error = validate_fetch_url(url)
    if error:
        return {"url": url, "resolved_url": url, "error": error}
    read_timeout = _bounded_timeout(timeout)
    async with _async_http_client(read_timeout, user_agent) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            error = validate_fetch_url(current)
            if error:
                return {"url": url, "resolved_url": url, "error": error}
            try:
                async with client.stream("GET", current) as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("Location")
                        if not location:
                            return {
                                "url": url,
                                "resolved_url": current,
                                "error": _status_error(response.status_code),
                            }
                        current = urljoin(current, location)
                        continue
                    return await _consume_async(response, url, current)
            except httpx.HTTPError as exc:
                raise ArticleFetchError(f"Sayfa cekilemedi ({current}): {exc}") from exc
    return {"url": url, "resolved_url": current, "error": "too_many_redirects"}
