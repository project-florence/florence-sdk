"""FastMCP sunucu kurulumu: ``create_server()`` factory + stdio ``main()``.

- ``create_server()``: 92 tool'u registry'den kaydeder (``MCP_DISABLE_GROUPS``
  filtreli), kimlik zincirini baslangicta kurar, rate limit tablosunu MCP
  ``instructions`` alanina koyar (mcp-design.md Bölüm 5.3), shutdown hook'unda
  bot oturumu logout'u yapar (Bölüm 3.3.4).
- ``main()``: ``florence-mcp`` entry point'i — stdio transport ile calisir.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP

from .auth import AuthContext, create_client, resolve_auth_context
from .config import get_disabled_groups
from .registry import enabled_specs
from .tools import ToolHandlers

__all__ = ["INSTRUCTIONS", "SERVER_NAME", "create_server", "main"]

SERVER_NAME = "florence"

#: MCP ``instructions`` — LLM'in tool cagri sikligini ayarlayabilmesi icin
#: backend rate limit tablosu (mcp-design.md Bölüm 5.3).
INSTRUCTIONS: str = (
    "Florence API MCP server. Tum tool'lar tek bir kimlikle calisir "
    "(auth_status ile kontrol edin; kimlik zinciri: MCP_FLORENCE_BOT -> "
    "FLORENCE_TOKEN -> keyring -> kimliksiz).\n\n"
    "RATE LIMITS (backend, asilirsa 429 + retry_after):\n"
    "- auth login/refresh: 5/dk\n"
    "- auth register: 3/dk\n"
    "- auth resend-verification: 3/saat\n"
    "- market news: 10/dk\n"
    "- export create: 3/saat\n"
    "- analysis generate_report: job-slot 900s (tek rapor ~90s, kredi harcar)\n"
    "- analysis simulate: job-slot 600s (kredi harcar)\n\n"
    "Kredi harcayan tool'lar oncesi account_credits / analysis_report_info / "
    "analysis_per_day_cost ile bakiyeyi kontrol edin. Yikici tool'lar "
    "(auth_delete_account, portfolio_delete, portfolio_undo_transaction, "
    "bots_delete) confirm=true gerektirir — kullanici onayi olmadan cagirmayin. "
    "helper_* tool'lari semantik kompozitlerdir (tek niyet = tek cagri): "
    "helper_ticker_briefing = fiyat+profil+trend+haber; helper_market_pulse = "
    "piyasa durumu + kazananlar/kaybedenler; helper_fetch_article harici URL "
    "ceker (SSRF korumali). Haber yoksa helper_* bos liste dondurur — hata "
    "degildir. "
    "dosya indirme tool'larinda (export_download, analysis_download_report) "
    "dest_path verilmezse icerik base64 doner; buyuk dosyalar icin dest_path "
    "kullanin (MCP_DOWNLOAD_DIR icinde, traversal korumali)."
)


def _make_lifespan(client: Any):
    """Shutdown hook'u: bot oturumunda refresh token'i iptal et (Bölüm 3.3.4)."""

    @asynccontextmanager
    async def _lifespan(server: FastMCP):
        yield
        try:
            # Token yoksa logout HTTP cagrisi yapmaz (sadece store temizligi).
            await asyncio.to_thread(client.auth.logout)
        except Exception:  # noqa: BLE001 — shutdown hatalari sessizce gecilir
            pass

    return _lifespan


def create_server(
    *,
    client: Any | None = None,
    auth_context: AuthContext | None = None,
) -> FastMCP:
    """FastMCP sunucusu kurar; tum tool'lari registry'den kaydeder.

    ``client`` / ``auth_context`` verilmezse kimlik zinciri env'den cozulur
    (``auth.create_client`` — bot profili secilmisse login yapilir).
    """
    state_client = client if client is not None else create_client()
    state_auth = auth_context or resolve_auth_context(
        getattr(state_client.auth, "_store", None)
    )
    handlers = ToolHandlers(state_client, state_auth)

    server = FastMCP(
        SERVER_NAME,
        instructions=INSTRUCTIONS,
        lifespan=_make_lifespan(state_client),
    )
    for spec in enabled_specs(get_disabled_groups()):
        handler = getattr(handlers, spec.name)
        server.tool(name=spec.name, description=spec.llm_description())(handler)
    return server


def main() -> None:
    """``florence-mcp`` entry point: stdio transport ile sunucuyu baslatir."""
    server = create_server()
    server.run()
