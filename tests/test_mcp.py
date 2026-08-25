"""MCP paketi testleri — TAMAMI OFFLINE (respx mock, canli backend yok).

Kapsam (gorev 7):
(a) kimlik zinciri: env override (bot profili), sifre yoksa net hata,
    FLORENCE_TOKEN, kimliksiz mod, store tabanli kullanici.
(b) dosya sozlesmesi: base64 donus, dest_path kisiti, traversal reddi.
(c) temsilci tool'lar: mocked client (respx) ile uctan uca MCP cagrisi —
    confirm kapisi, sifre maskeleme, hata esleme, dest_path yazma.
(d) fastmcp.Client ile server baslat + list_tools smoke (>= 80 tool).

Mevcut 91 testi kirma: src/florence/ ve tests/'teki diger dosyalara
dokunulmaz; bu dosya yalnizca florence_mcp'yi test eder.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx
from fastmcp import Client

from florence import FlorenceClient, MemoryTokenStore
from florence.errors import AuthError
from florence_mcp import create_server
from florence_mcp.auth import (
    IDENTITY_BOT,
    IDENTITY_NONE,
    IDENTITY_USER,
    SOURCE_ENV,
    SOURCE_MEMORY,
    SOURCE_NONE,
    AuthContext,
    create_client,
    resolve_auth_context,
)
from florence_mcp.errors import ToolError
from florence_mcp.files import base64_payload, resolve_dest_path, write_bytes
from florence_mcp.registry import CONFIRM_REQUIRED, GROUPS, TOOLS, enabled_specs

API = "https://api.florencex.com.tr"
PREFIX = f"{API}/api/v1"


def _run(coro):
    """Asenkron test govdesini senkron test icinde calistirir."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------


def _make_server(auth_context: AuthContext | None = None, *, token_store=None):
    client = FlorenceClient(token_store=token_store or MemoryTokenStore())
    return create_server(
        client=client, auth_context=auth_context or AuthContext(IDENTITY_NONE, SOURCE_NONE)
    )


def _login_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": "acc-123",
            "refresh_token": "ref-456",
            "token_type": "bearer",
        },
    )


# ---------------------------------------------------------------------------
# (a) Kimlik zinciri
# ---------------------------------------------------------------------------


def test_auth_chain_bot_env_override(monkeypatch):
    """MCP_FLORENCE_BOT + MCP_FLORENCE_BOT_PASSWORD -> bot profili (env sifre)."""
    monkeypatch.setenv("MCP_FLORENCE_BOT", "bot-1")
    monkeypatch.setenv("MCP_FLORENCE_BOT_PASSWORD", "s3cret")
    monkeypatch.delenv("FLORENCE_TOKEN", raising=False)
    with respx.mock:
        respx.post(f"{PREFIX}/auth/login").mock(return_value=_login_response())
        client = create_client(token_store=MemoryTokenStore())
    ctx = resolve_auth_context(client.auth._store)  # noqa: SLF001 — SDK ic durumu
    assert ctx.identity_type == IDENTITY_BOT
    assert ctx.token_source == SOURCE_ENV
    assert ctx.username == "bot-1"
    assert ctx.authenticated is True
    assert client.auth.access_token() == "acc-123"


def test_auth_chain_bot_without_password_raises(monkeypatch):
    """Bot profili secilmis ama sifre yoksa NET hata (cozum onerili)."""
    monkeypatch.setenv("MCP_FLORENCE_BOT", "bot-1")
    monkeypatch.delenv("MCP_FLORENCE_BOT_PASSWORD", raising=False)
    monkeypatch.delenv("FLORENCE_TOKEN", raising=False)
    with pytest.raises(AuthError) as exc_info:
        create_client(token_store=MemoryTokenStore())
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "no_bot_password"
    assert "MCP_FLORENCE_BOT_PASSWORD" in str(exc_info.value.detail)


def test_auth_chain_env_token(monkeypatch):
    """FLORENCE_TOKEN -> kullanici kimligi, kaynak env (SDK override)."""
    monkeypatch.setenv("FLORENCE_TOKEN", "jwt-env")
    monkeypatch.delenv("MCP_FLORENCE_BOT", raising=False)
    monkeypatch.delenv("MCP_FLORENCE_BOT_PASSWORD", raising=False)
    ctx = resolve_auth_context(MemoryTokenStore())
    assert ctx.identity_type == IDENTITY_USER
    assert ctx.token_source == SOURCE_ENV
    client = FlorenceClient(token_store=MemoryTokenStore())
    assert client.auth.access_token() == "jwt-env"


def test_auth_chain_anonymous(monkeypatch):
    """Hicbir kimlik yok -> kimliksiz mod (public tool'lar calisir)."""
    monkeypatch.delenv("MCP_FLORENCE_BOT", raising=False)
    monkeypatch.delenv("MCP_FLORENCE_BOT_PASSWORD", raising=False)
    monkeypatch.delenv("FLORENCE_TOKEN", raising=False)
    ctx = resolve_auth_context(MemoryTokenStore())
    assert ctx.identity_type == IDENTITY_NONE
    assert ctx.token_source == SOURCE_NONE
    assert ctx.authenticated is False
    # create_client kimliksiz modda network yapmadan doner.
    client = create_client(token_store=MemoryTokenStore())
    assert client.auth.access_token() is None


def test_auth_chain_store_user(monkeypatch):
    """Store'da token var -> kullanici kimligi, kaynak memory."""
    monkeypatch.delenv("MCP_FLORENCE_BOT", raising=False)
    monkeypatch.delenv("MCP_FLORENCE_BOT_PASSWORD", raising=False)
    monkeypatch.delenv("FLORENCE_TOKEN", raising=False)
    store = MemoryTokenStore()
    store.set_tokens("acc-store", "ref-store")
    ctx = resolve_auth_context(store)
    assert ctx.identity_type == IDENTITY_USER
    assert ctx.token_source == SOURCE_MEMORY


def test_auth_chain_bot_wins_over_env_token(monkeypatch):
    """Bot + FLORENCE_TOKEN birlikte -> bot profili kazanir (Bölüm 3.1)."""
    monkeypatch.setenv("MCP_FLORENCE_BOT", "bot-1")
    monkeypatch.setenv("MCP_FLORENCE_BOT_PASSWORD", "s3cret")
    monkeypatch.setenv("FLORENCE_TOKEN", "jwt-env")
    ctx = resolve_auth_context(MemoryTokenStore())
    assert ctx.identity_type == IDENTITY_BOT


# ---------------------------------------------------------------------------
# (b) Dosya sozlesmesi (files.py)
# ---------------------------------------------------------------------------


def test_files_base64_payload():
    payload = base64_payload(b"hello", "pdf")
    assert payload["encoding"] == "base64"
    assert payload["size_bytes"] == 5
    assert payload["format"] == "pdf"
    assert payload["data"] == "aGVsbG8="


def test_files_write_bytes_meta(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_DOWNLOAD_DIR", str(tmp_path))
    meta = write_bytes(b"\x1f\x8bdata", "rapor.pdf", fmt="pdf")
    assert meta["size_bytes"] == 6
    assert meta["format"] == "pdf"
    assert meta["md5"] == "1f3332dedbbf48b9972bf5a910cdf35b"
    target = tmp_path / "rapor.pdf"
    assert target.read_bytes() == b"\x1f\x8bdata"
    assert meta["path"] == str(target.resolve())


def test_files_dest_path_traversal_rejected(tmp_path, monkeypatch):
    """``..`` ve dizin disi absolute path reddedilir."""
    monkeypatch.setenv("MCP_DOWNLOAD_DIR", str(tmp_path))
    with pytest.raises(ToolError):
        resolve_dest_path("../evil.txt")
    with pytest.raises(ToolError):
        resolve_dest_path("/etc/passwd")
    # Dizin icindeki relative path gecerli.
    ok = resolve_dest_path("sub/out.gz")
    assert ok.is_relative_to(tmp_path.resolve())


def test_files_dest_path_relative_joins_download_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_DOWNLOAD_DIR", str(tmp_path))
    resolved = resolve_dest_path("out.csv")
    assert resolved == (tmp_path / "out.csv").resolve()


# ---------------------------------------------------------------------------
# (c) Temsilci tool'lar (mocked client ile uctan uca MCP cagrisi)
# ---------------------------------------------------------------------------


def test_tool_market_price_current_structured():
    with respx.mock:
        respx.get(f"{PREFIX}/price/current").mock(
            return_value=httpx.Response(200, json={"ticker": "THYAO", "price": 312.5})
        )
        server = _make_server()

        async def _call():
            async with Client(server) as client:
                return await client.call_tool("market_price_current", {"ticker": "THYAO"})

        result = _run(_call())
    assert result.is_error is False
    assert result.structured_content == {"ticker": "THYAO", "price": 312.5}
    assert '"price": 312.5' in result.content[0].text


def test_tool_company_info_md_text():
    with respx.mock:
        respx.get(f"{PREFIX}/companies/info/THYAO/md").mock(
            return_value=httpx.Response(200, content="# THYAO\nTurkish Airlines")
        )
        server = _make_server()

        async def _call():
            async with Client(server) as client:
                return await client.call_tool(
                    "market_company_info", {"ticker": "THYAO", "format": "md"}
                )

        result = _run(_call())
    assert result.is_error is False
    assert "Turkish Airlines" in result.content[0].text


def test_mcp_market_digest():
    with respx.mock:
        respx.get(f"{PREFIX}/digest").mock(
            return_value=httpx.Response(
                200,
                json={"id": "d-mcp", "title": "MCP Bülteni", "slot": "noon"},
            )
        )
        server = _make_server()

        async def _call():
            async with Client(server) as client:
                return await client.call_tool("market_digest", {})

        result = _run(_call())
    assert result.is_error is False
    assert result.structured_content["id"] == "d-mcp"



def test_tool_confirm_gate_blocks_and_allows():
    with respx.mock:
        respx.delete(f"{PREFIX}/portfolios/1").mock(
            return_value=httpx.Response(200, json={"message": "Portfolio deleted"})
        )
        server = _make_server()

        async def _call():
            async with Client(server) as client:
                blocked = await client.call_tool(
                    "portfolio_delete", {"portfolio_id": "1"}, raise_on_error=False
                )
                allowed = await client.call_tool(
                    "portfolio_delete", {"portfolio_id": "1", "confirm": True}
                )
                return blocked, allowed

        blocked, allowed = _run(_call())
    assert blocked.is_error is True
    assert "Onay gerekli" in blocked.content[0].text
    assert allowed.is_error is False
    assert allowed.structured_content == {"message": "Portfolio deleted"}


def test_tool_bots_create_password_masked():
    with respx.mock:
        respx.post(f"{PREFIX}/bots").mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "username": "bot-1", "email": "b@x.com", "password": "secret123"},
            )
        )
        server = _make_server()

        async def _call():
            async with Client(server) as client:
                return await client.call_tool("bots_create", {"username": "bot-1"})

        result = _run(_call())
    assert result.structured_content["password"] == "***"
    assert "secret123" not in result.content[0].text


def test_tool_401_maps_to_identity_error():
    with respx.mock:
        respx.post(f"{PREFIX}/reports/generate").mock(
            return_value=httpx.Response(401, json={"detail": "not_authenticated"})
        )
        server = _make_server()

        async def _call():
            async with Client(server) as client:
                return await client.call_tool(
                    "analysis_generate_report",
                    {"ticker": "THYAO", "type": "quick_report"},
                    raise_on_error=False,
                )

        result = _run(_call())
    assert result.is_error is True
    assert "Kimlik hatasi" in result.content[0].text
    assert "Cozum" in result.content[0].text


def test_tool_export_download_dest_path(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_DOWNLOAD_DIR", str(tmp_path))
    with respx.mock:
        respx.get(f"{PREFIX}/data/export/download/TOK").mock(
            return_value=httpx.Response(200, content=b"\x1f\x8b fake-gzip")
        )
        server = _make_server()

        async def _call():
            async with Client(server) as client:
                return await client.call_tool(
                    "export_download", {"token_or_url": "TOK", "dest_path": "out.gz"}
                )

        result = _run(_call())
    meta = result.structured_content
    assert meta["format"] == "gzip"
    assert meta["size_bytes"] == 12
    assert (tmp_path / "out.gz").read_bytes() == b"\x1f\x8b fake-gzip"
    assert meta["path"] == str((tmp_path / "out.gz").resolve())


def test_tool_export_download_base64_fallback():
    with respx.mock:
        respx.get(f"{PREFIX}/data/export/download/TOK").mock(
            return_value=httpx.Response(200, content=b"\x1f\x8b gzip")
        )
        server = _make_server()

        async def _call():
            async with Client(server) as client:
                return await client.call_tool("export_download", {"token_or_url": "TOK"})

        result = _run(_call())
    payload = result.structured_content
    assert payload["encoding"] == "base64"
    assert payload["size_bytes"] == 7
    assert payload["data"] == "H4sgZ3ppcA=="


def test_tool_auth_status_reports_bot_identity():
    server = _make_server(AuthContext(IDENTITY_BOT, SOURCE_ENV, username="bot-1"))

    async def _call():
        async with Client(server) as client:
            return await client.call_tool("auth_status", {})

    result = _run(_call())
    assert result.structured_content == {
        "authenticated": True,
        "identity_type": IDENTITY_BOT,
        "username": "bot-1",
        "token_source": SOURCE_ENV,
    }


def test_tool_error_mapping_429():
    """RateLimitError -> retry_after'li mesaj (Bölüm 5.1)."""
    with respx.mock:
        respx.get(f"{PREFIX}/news/THYAO").mock(
            return_value=httpx.Response(
                429, headers={"Retry-After": "30"}, json={"detail": "rate_limited"}
            )
        )
        server = _make_server()

        async def _call():
            async with Client(server) as client:
                # Client retry'i biter, RateLimitError yuzeye cikar.
                return await client.call_tool(
                    "market_news", {"ticker": "THYAO"}, raise_on_error=False
                )

        result = _run(_call())
    assert result.is_error is True
    assert "Rate limit" in result.content[0].text
    assert "retry_after" in result.content[0].text


# ---------------------------------------------------------------------------
# (d) Server smoke: list_tools + grup kapatma
# ---------------------------------------------------------------------------


def test_server_list_tools_smoke():
    server = _make_server()

    async def _list():
        async with Client(server) as client:
            return await client.list_tools()

    tools = _run(_list())
    names = {tool.name for tool in tools}
    assert len(tools) >= 80
    assert len(tools) == len(TOOLS) == 99
    assert names == {spec.name for spec in TOOLS}
    # Temsilci isimler (CLI uyumlu, Bölüm 2.6).
    for expected in (
        "market_price_current",
        "analysis_generate_report",
        "portfolio_add_transaction",
        "export_status",
        "bots_create",
        "auth_status",
        "helper_news_digest",
        "helper_market_pulse",
        "market_digest",
    ):
        assert expected in names


def test_server_disabled_groups(monkeypatch):
    """MCP_DISABLE_GROUPS=export -> export_* tool'lari kayit disi."""
    monkeypatch.setenv("MCP_DISABLE_GROUPS", "export")
    server = _make_server()

    async def _list():
        async with Client(server) as client:
            return await client.list_tools()

    tools = _run(_list())
    names = {tool.name for tool in tools}
    assert not any(n.startswith("export_") for n in names)
    assert len(names) == len(enabled_specs({"export"})) == 94


def test_server_instructions_mention_rate_limits():
    server = _make_server()
    instructions = server.instructions or ""
    assert "rate limits" in instructions.lower()
    for token in ("login", "news", "export", "900", "600"):
        assert token in instructions


# ---------------------------------------------------------------------------
# Registry tutarliligi
# ---------------------------------------------------------------------------


def test_registry_has_99_tools_and_invariants():
    names = [spec.name for spec in TOOLS]
    assert len(names) == 99
    assert len(set(names)) == 99  # benzersiz
    for spec in TOOLS:
        assert spec.group in GROUPS
    # Helper tool'lari "helpers" grubunda ve salt-okuma.
    helper_names = [spec.name for spec in TOOLS if spec.group == "helpers"]
    assert helper_names == [
        "helper_news_digest",
        "helper_fetch_article",
        "helper_ticker_briefing",
        "helper_market_pulse",
        "helper_portfolio_health",
        "helper_macro_briefing",
    ]
    for spec in TOOLS:
        if spec.group == "helpers":
            assert not spec.write and not spec.danger and not spec.credit and not spec.confirm
    assert CONFIRM_REQUIRED == frozenset(
        {"auth_delete_account", "portfolio_delete", "portfolio_undo_transaction", "bots_delete"}
    )
    # Handler eslesmesi: her tool adi ToolHandlers'ta metod olarak var.
    from florence_mcp.tools import ToolHandlers

    missing = [name for name in names if not hasattr(ToolHandlers, name)]
    assert missing == []
