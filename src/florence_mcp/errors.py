"""SDK hata hiyerarsisi -> MCP tool error eslemesi.

Tool handler'lari icinden ``ToolError`` firlatilir; MCP sunucusu bunu
``isError=true`` tool sonucuna cevirir. Mesajlar LLM'in aksiyon alabilmesi
icin cozum onerisi tasir (mcp-design.md Bölüm 5.1).

Esleme:
- ``AuthError`` (401)  -> kimlik cozum onerisi
- ``RateLimitError`` (429) -> ``retry_after`` + bekleme onerisi
- ``NetworkError``    -> ``FLORENCE_API_URL`` dogrulama onerisi
- ``TimeoutError``    -> ``export_status`` ile yeniden sorgulama onerisi
- ``FlorenceAPIError`` (diger 4xx/5xx) -> status + i18n kodu
- Beklenmeyen         -> genel mesaj (detay sunucu logunda)
"""

from __future__ import annotations

from typing import Any

from florence.errors import (
    AuthError,
    FlorenceAPIError,
    NetworkError,
    RateLimitError,
)

try:  # helpers kurulu degilse bile MCP ayakta kalir (savunmacı import)
    from florence.helpers._http import ArticleFetchError
except ImportError:  # pragma: no cover
    ArticleFetchError = NetworkError  # type: ignore[misc,assignment]

__all__ = ["ToolError", "to_tool_error"]


class ToolError(Exception):
    """MCP tool hatasi — mesaj dogrudan istemciye ``isError`` olarak gider."""


def to_tool_error(exc: BaseException) -> ToolError:
    """Bir SDK/beklenmeyen hatayi LLM dostu ``ToolError`` mesajina cevirir."""
    if isinstance(exc, ArticleFetchError):
        return ToolError(
            f"Ağ hatası (harici içerik çekimi): {exc} | "
            "URL erişilebilir mi? (SSRF korumasi: localhost/özel ağlar engelli)."
        )
    if isinstance(exc, AuthError):
        code = exc.code or "not_authenticated"
        detail = _detail_text(exc.detail)
        return ToolError(
            f"Kimlik hatasi (401): {code} — {detail} | "
            "Cozum: FLORENCE_TOKEN ayarlayin, keyring'de oturum acin (fl login) "
            "veya MCP_FLORENCE_BOT=<bot> ile bot profili secin."
        )
    if isinstance(exc, RateLimitError):
        retry = exc.retry_after
        retry_part = f"retry_after: {retry:.0f}s" if retry is not None else "retry_after: yok"
        return ToolError(
            f"Rate limit asildi (429): {exc.code or 'rate_limited'} — {retry_part} | "
            "Bekleyip tekrar deneyin (orn. news 10/dk, auth 5/dk, export 3/saat)."
        )
    if isinstance(exc, NetworkError):
        return ToolError(
            f"Ağ hatasi: {exc} | FLORENCE_API_URL dogru mu, API erisilebilir mi?"
        )
    if isinstance(exc, TimeoutError):
        return ToolError(
            f"Zaman asimi: {exc} | export_status ile tekrar sorgulayin."
        )
    if isinstance(exc, FlorenceAPIError):
        code = exc.code or "api_error"
        detail = _detail_text(exc.detail)
        return ToolError(f"Florence API hatasi {exc.status_code}: {code} — {detail}")
    return ToolError(f"Beklenmeyen hata: {exc!r} (detay sunucu logunda)")


def _detail_text(detail: Any) -> str:
    """Hata detayini kisa metne cevirir (token/sifre asla gecmez)."""
    if detail is None:
        return "detay yok"
    return str(detail)[:300]
