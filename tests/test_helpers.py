"""Helper katmani testleri — TAMAMI OFFLINE (respx mock, canli ag yok).

Kapsam (helpers-design.md Bolum 4.5):
- ``fetch_article``: icerik cekimi (stdlib fallback), 404, SSRF (localhost/
  metadata/domain->private IP), redirect->blocked, timeout, too_large,
  unsupported_type, gecersiz sema; asenkron ikiz.
- ``news_digest``: dolu, bos, kismi hata (tek URL 404), no-content, asenkron.
- ``ticker_briefing`` / ``market_pulse`` / ``portfolio_health`` /
  ``macro_briefing``: dolu + bos/kisa + hata senaryolari.
- CLI ``fl helper`` grubu: news-digest --json, article gecersiz sema (exit 2),
  pulse --json.
- MCP: helper_* registry'de, ``MCP_DISABLE_GROUPS=helpers`` kapatir,
  helper_market_pulse uctan uca cagri.

DNS: ``_resolve_host`` autouse fixture ile sabit public IP'ye sabitlenir —
gercek DNS cagrisi YAPILMAZ (offline garantisi). SSRF domain testi kendi
cozumlemesini override eder.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import socket
from pathlib import Path

import httpx
import pytest
import respx

from florence import AuthError, FlorenceAPIError, FlorenceClient, MemoryTokenStore
from florence.cli.app import _run
from florence.helpers import (
    fetch_article,
    fetch_article_async,
    macro_briefing,
    market_pulse,
    news_digest,
    portfolio_health,
    ticker_briefing,
)
from florence.helpers._http import ArticleFetchError

API = "https://api.florencex.com.tr"
P = f"{API}/api/v1"

PAGE_HTML = (
    "<!doctype html><html><head><title>Test Haber</title><style>.x{}</style></head>"
    "<body><nav>Menu</nav><h1>Baslik</h1><p>Ilk paragraf icerik.</p>"
    "<p>Ikinci paragraf.</p><script>var x=1;</script></body></html>"
)

EXPECTED_TEXT = "Baslik\nIlk paragraf icerik.\nIkinci paragraf."


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gercek DNS'i devre disi birakir: tum domain'ler public IP'ye cozulur."""

    def fake_resolve(host: str):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("florence.helpers._http._resolve_host", fake_resolve)


def _html_response(body: str = PAGE_HTML, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        headers={"Content-Type": "text/html; charset=utf-8"},
        content=body.encode("utf-8"),
    )


@pytest.fixture
def cli_env(tmp_path: Path) -> dict[str, str]:
    """CLI'yi tmp dizine yonlendirir (config + Fernet token store)."""
    return {
        "FLORENCE_KEYRING": "0",
        "FLORENCE_TOKEN_STORE_PATH": str(tmp_path / "tokens.json"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
    }


def run_cli(
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """CLI'yi gercek komut agacindan calistirir: (exit_code, stdout, stderr)."""
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = _run(args, prog_name="fl")
    return code, out.getvalue(), err.getvalue()


def _run_async(coro):
    """Asenkron helper govdelerini senkron test icinde calistirir."""
    return asyncio.run(coro)


# ======================================================================
# H2 — fetch_article (icerik cekimi + SSRF + sinirlar)
# ======================================================================
def test_fetch_article_stdlib_fallback_extracts_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """trafilatura yokken stdlib fallback metin cikarir (opsiyonellik garantisi)."""
    monkeypatch.setattr("florence.helpers._extract.TRAFILATURA_AVAILABLE", False)
    with respx.mock:
        respx.get("https://example.com/haber").mock(return_value=_html_response())
        article = fetch_article("https://example.com/haber")
    assert article.content_available is True
    assert article.title == "Test Haber"
    assert article.text == EXPECTED_TEXT
    assert article.error is None
    assert article.resolved_url == "https://example.com/haber"


def test_fetch_article_max_chars_truncates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("florence.helpers._extract.TRAFILATURA_AVAILABLE", False)
    with respx.mock:
        respx.get("https://example.com/uzun").mock(return_value=_html_response())
        article = fetch_article("https://example.com/uzun", max_chars=10)
    assert article.truncated is True
    assert len(article.text) == 10


def test_fetch_article_404_is_result_not_error() -> None:
    with respx.mock:
        respx.get("https://example.com/yok").mock(return_value=httpx.Response(404))
        article = fetch_article("https://example.com/yok")
    assert article.error == "http_404"
    assert article.content_available is False


def test_fetch_article_403_is_result_not_error() -> None:
    with respx.mock:
        respx.get("https://example.com/yasak").mock(return_value=httpx.Response(403))
        article = fetch_article("https://example.com/yasak")
    assert article.error == "http_403"


def test_fetch_article_ssrf_blocks_localhost_and_metadata() -> None:
    for url in (
        "http://localhost/x",
        "http://127.0.0.1/x",
        "http://10.0.0.5/x",
        "http://192.168.1.1/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/x",
    ):
        article = fetch_article(url)
        assert article.error == "blocked_host", url
        assert article.content_available is False


def test_fetch_article_ssrf_blocks_domain_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Domain cozumlemesi private IP'ye ulasirsa engellenir (DNS tabanli SSRF)."""

    def private_resolve(host: str):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))]

    monkeypatch.setattr("florence.helpers._http._resolve_host", private_resolve)
    article = fetch_article("https://ic-sunucu.example/x")
    assert article.error == "blocked_host"


def test_fetch_article_redirect_to_blocked_host_rejected() -> None:
    """Public URL -> localhost redirect deseni engellenir (SSRF atlama)."""
    with respx.mock:
        respx.get("https://example.com/yonlendir").mock(
            return_value=httpx.Response(302, headers={"Location": "http://127.0.0.1/evil"})
        )
        article = fetch_article("https://example.com/yonlendir")
    assert article.error == "blocked_host"


def test_fetch_article_unsupported_scheme() -> None:
    article = fetch_article("file:///etc/passwd")
    assert article.error == "unsupported_scheme"
    article = fetch_article("ftp://example.com/x")
    assert article.error == "unsupported_scheme"


def test_fetch_article_network_error_raises() -> None:
    with respx.mock:
        respx.get("https://example.com/kopuk").mock(
            side_effect=httpx.ConnectTimeout("zaman asimi")
        )
        with pytest.raises(ArticleFetchError):
            fetch_article("https://example.com/kopuk")


def test_fetch_article_too_large_rejected() -> None:
    with respx.mock:
        respx.get("https://example.com/buyuk").mock(
            return_value=httpx.Response(
                200,
                headers={"Content-Length": str(2 * 1024 * 1024 + 1)},
                content=b"x" * 100,
            )
        )
        article = fetch_article("https://example.com/buyuk")
    assert article.error == "too_large"


def test_fetch_article_unsupported_type_rejected() -> None:
    with respx.mock:
        respx.get("https://example.com/rapor.pdf").mock(
            return_value=httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=b"%PDF")
        )
        article = fetch_article("https://example.com/rapor.pdf")
    assert article.error == "unsupported_type"


def test_fetch_article_async(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("florence.helpers._extract.TRAFILATURA_AVAILABLE", False)
    with respx.mock:
        respx.get("https://example.com/async").mock(return_value=_html_response())
        article = _run_async(fetch_article_async("https://example.com/async"))
    assert article.content_available is True
    assert article.text == EXPECTED_TEXT


# ======================================================================
# H1 — news_digest
# ======================================================================
def test_news_digest_full(monkeypatch: pytest.MonkeyPatch) -> None:
    """2 haber + icerik cekimi: fetched=2, failed=0 (N'den az -> ne varsa)."""
    monkeypatch.setattr("florence.helpers._extract.TRAFILATURA_AVAILABLE", False)
    with respx.mock:
        respx.get(url__regex=r".*/news/THYAO.*").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"title": "Haber 1", "url": "https://example.com/h1"},
                    {"title": "Haber 2", "url": "https://example.com/h2"},
                ],
            )
        )
        respx.get("https://example.com/h1").mock(
            return_value=_html_response("<html><body><h1>T1</h1><p>Icerik bir.</p></body></html>")
        )
        respx.get("https://example.com/h2").mock(
            return_value=_html_response("<html><body><h1>T2</h1><p>Icerik iki.</p></body></html>")
        )
        client = FlorenceClient()
        result = news_digest(client, "thyao", amount=5)
    assert result.ticker == "THYAO"  # ticker normalize edildi
    assert result.requested == 5
    assert len(result.items) == 2
    assert result.fetched == 2
    assert result.failed == 0
    assert result.items[0].title == "Haber 1"
    assert result.items[0].content_available is True
    assert result.items[0].content == "T1\nIcerik bir."
    assert result.items[0].fetch_error is None


def test_news_digest_empty_is_not_error() -> None:
    """0 haber -> bos liste, hata DEGIL (kullanici ornegindeki davranis)."""
    with respx.mock:
        respx.get(url__regex=r".*/news/THYAO.*").mock(return_value=httpx.Response(200, json=[]))
        client = FlorenceClient()
        result = news_digest(client, "THYAO")
    assert result.items == []
    assert result.requested == 5
    assert result.fetched == 0
    assert result.failed == 0


def test_news_digest_partial_failure_keeps_digest() -> None:
    """Tek URL 404 -> o item fetch_error alir, digest doner (kismi sonuc)."""
    with respx.mock:
        respx.get(url__regex=r".*/news/THYAO.*").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"title": "Iyi", "url": "https://example.com/iyi"},
                    {"title": "Kotu", "url": "https://example.com/kotu"},
                ],
            )
        )
        respx.get("https://example.com/iyi").mock(
            return_value=_html_response("<html><body><p>Icerik.</p></body></html>")
        )
        respx.get("https://example.com/kotu").mock(return_value=httpx.Response(404))
        client = FlorenceClient()
        result = news_digest(client, "THYAO", amount=2)
    assert len(result.items) == 2
    assert result.fetched == 1
    assert result.failed == 1
    assert result.items[0].content_available is True
    assert result.items[1].fetch_error == "http_404"
    assert result.items[1].content is None


def test_news_digest_no_content_skips_fetch() -> None:
    """fetch_content=False: harici HTTP istegi YOK; saf liste modu."""
    with respx.mock:
        respx.get(url__regex=r".*/news/THYAO.*").mock(
            return_value=httpx.Response(
                200, json=[{"title": "H", "url": "https://example.com/h"}]
            )
        )
        client = FlorenceClient()
        result = news_digest(client, "THYAO", fetch_content=False)
    assert len(result.items) == 1
    assert result.items[0].content is None
    assert result.items[0].content_available is False
    assert result.items[0].fetch_error is None
    assert result.failed == 0


def test_news_digest_async(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("florence.helpers._extract.TRAFILATURA_AVAILABLE", False)
    with respx.mock:
        respx.get(url__regex=r".*/news/THYAO.*").mock(
            return_value=httpx.Response(200, json=[{"title": "H", "url": "https://example.com/h"}])
        )
        respx.get("https://example.com/h").mock(return_value=_html_response())
        from florence import AsyncFlorenceClient

        client = AsyncFlorenceClient(token_store=MemoryTokenStore())
        result = _run_async(news_digest_async_call(client))
    assert result.fetched == 1
    assert result.items[0].content_available is True


async def news_digest_async_call(client):
    from florence.helpers import news_digest_async

    return await news_digest_async(client, "THYAO")


# ======================================================================
# H3 — ticker_briefing
# ======================================================================
def test_ticker_briefing_full() -> None:
    with respx.mock:
        respx.get(f"{P}/price/current").mock(
            return_value=httpx.Response(
                200,
                json={"ticker": "THYAO", "price": 313.4, "change_pct": 0.93, "market_status": "open"},
            )
        )
        respx.get(url__regex=r".*companies/info/THYAO.*").mock(
            return_value=httpx.Response(
                200, json={"ticker": "THYAO", "longName": "Turk Hava Yollari", "sector": "Ulastirma"}
            )
        )
        respx.get(url__regex=r".*price/history/THYAO.*").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"ts": "2026-07-01", "close": 300.0},
                    {"ts": "2026-07-02", "close": 310.0},
                    {"ts": "2026-07-03", "close": 315.0},
                ],
            )
        )
        respx.get(url__regex=r".*news/THYAO.*").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"title": "H1", "url": "https://example.com/1"},
                    {"title": "H2", "url": "https://example.com/2"},
                ],
            )
        )
        client = FlorenceClient()
        result = ticker_briefing(client, "thyao", news_amount=3)
    assert result.ticker == "THYAO"
    assert result.quote is not None
    assert result.quote.price == 313.4
    assert result.quote.market_status == "open"
    assert result.company is not None
    assert result.company.name == "Turk Hava Yollari"
    assert result.trend is not None
    assert result.trend.period == "1mo"
    assert result.trend.sparkline == [300.0, 310.0, 315.0]
    assert result.trend.change_pct == pytest.approx(5.0)
    assert len(result.news) == 2


def test_ticker_briefing_all_missing_returns_null_fields() -> None:
    """Hepsi eksik olsa bile briefing doner (alanlar null), hata firlatmaz."""
    with respx.mock:
        respx.get(f"{P}/price/current").mock(
            return_value=httpx.Response(200, json={"ticker": "THYAO", "price": None, "market_status": "closed"})
        )
        respx.get(url__regex=r".*companies/info/THYAO.*").mock(
            return_value=httpx.Response(404, json={"detail": "not_found"})
        )
        respx.get(url__regex=r".*price/history/THYAO.*").mock(return_value=httpx.Response(200, json=[]))
        respx.get(url__regex=r".*news/THYAO.*").mock(return_value=httpx.Response(200, json=[]))
        client = FlorenceClient()
        result = ticker_briefing(client, "THYAO")
    assert result.quote is None  # is_stale / islem yok
    assert result.company is None
    assert result.trend is None
    assert result.news == []


# ======================================================================
# H4 — market_pulse
# ======================================================================
def test_market_pulse_full() -> None:
    with respx.mock:
        respx.get(f"{P}/market/status").mock(
            return_value=httpx.Response(
                200, json={"open": True, "next_open_at": "2026-08-15T10:00:00+03:00", "holiday": False}
            )
        )
        respx.get(f"{P}/companies/summary").mock(
            side_effect=[
                httpx.Response(200, json=[{"ticker": "THYAO", "change_pct": 3.2}, {"ticker": "ASELS", "change_pct": 2.1}]),
                httpx.Response(200, json=[{"ticker": "EREGL", "change_pct": -1.5}]),
                httpx.Response(200, json=[{"ticker": "THYAO", "volume": 12345678}, {"ticker": "ASELS", "volume": 9999999}]),
            ]
        )
        respx.get(f"{P}/stats/top").mock(
            return_value=httpx.Response(200, json=[{"ticker": "THYAO", "count": 99}, {"ticker": "GARAN", "count": 42}])
        )
        client = FlorenceClient()
        result = market_pulse(client, limit=5)
    assert result.market_open is True
    assert result.holiday is False
    assert result.gainers[0].ticker == "THYAO"
    assert result.gainers[0].change_pct == 3.2
    assert result.losers[0].change_pct == -1.5
    assert result.volume_leaders[0].volume == 12345678
    assert result.most_popular[0].count == 99


def test_market_pulse_closed_returns_empty_lists() -> None:
    """Piyasa kapali: market_open false + bos listeler (hata DEGIL)."""
    with respx.mock:
        respx.get(f"{P}/market/status").mock(
            return_value=httpx.Response(200, json={"open": False, "next_open_at": "2026-08-17T10:00:00+03:00", "holiday": False})
        )
        respx.get(f"{P}/companies/summary").mock(
            side_effect=[
                httpx.Response(200, json=[]),
                httpx.Response(200, json=[]),
                httpx.Response(200, json=[]),
            ]
        )
        respx.get(f"{P}/stats/top").mock(return_value=httpx.Response(200, json=[]))
        client = FlorenceClient()
        result = market_pulse(client)
    assert result.market_open is False
    assert result.next_open_at is not None
    assert result.gainers == []
    assert result.losers == []
    assert result.most_popular == []
    assert result.volume_leaders == []


# ======================================================================
# H5 — portfolio_health
# ======================================================================
def test_portfolio_health_full() -> None:
    pid = "p-1"
    with respx.mock:
        respx.get(f"{P}/portfolios/{pid}/snapshot").mock(
            return_value=httpx.Response(200, json={"total_value": 152340.5, "pnl": 12340.5, "pnl_pct": 8.8})
        )
        respx.get(f"{P}/portfolios/{pid}/performers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "top": [{"ticker": "THYAO", "return_pct": 12.3}],
                    "bottom": [{"ticker": "EREGL", "return_pct": -4.2}],
                },
            )
        )
        respx.get(f"{P}/portfolios/{pid}/risk").mock(
            return_value=httpx.Response(200, json={"volatility": 0.02, "max_drawdown": -0.04, "sharpe": 1.2})
        )
        respx.get(f"{P}/portfolios/{pid}/benchmark").mock(
            return_value=httpx.Response(
                200, json={"ticker": "XU100", "portfolio_return_pct": 8.8, "benchmark_return_pct": 6.1, "diff_pct": 2.7}
            )
        )
        respx.get(f"{P}/portfolios/{pid}/diversification").mock(
            return_value=httpx.Response(200, json={"stocks": 70.0, "forex": 20.0, "metals": 10.0})
        )
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        result = portfolio_health(client, pid)
    assert result.portfolio_id == pid
    assert result.total_value == 152340.5
    assert result.pnl == 12340.5
    assert result.pnl_pct == 8.8
    assert result.performers is not None
    assert result.performers.top[0].ticker == "THYAO"
    assert result.performers.top[0].return_pct == 12.3
    assert result.performers.bottom[0].return_pct == -4.2
    assert result.risk is not None
    assert result.risk.sharpe == 1.2
    assert result.benchmark is not None
    assert result.benchmark.diff_pct == 2.7
    assert result.diversification is not None
    assert result.diversification.stocks == 70.0


def test_portfolio_health_empty_and_partial() -> None:
    """Bos portfoy: 400 -> total 0; analiz ucu 400 -> alan None (paket doner)."""
    pid = "p-bos"
    with respx.mock:
        respx.get(f"{P}/portfolios/{pid}/snapshot").mock(
            return_value=httpx.Response(400, json={"detail": "empty portfolio"})
        )
        respx.get(f"{P}/portfolios/{pid}/performers").mock(
            return_value=httpx.Response(200, json={"top": [], "bottom": []})
        )
        respx.get(f"{P}/portfolios/{pid}/risk").mock(
            return_value=httpx.Response(400, json={"detail": "empty portfolio"})
        )
        respx.get(f"{P}/portfolios/{pid}/benchmark").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.get(f"{P}/portfolios/{pid}/diversification").mock(
            return_value=httpx.Response(200, json={})
        )
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        result = portfolio_health(client, pid)
    assert result.total_value == 0.0
    assert result.performers is not None
    assert result.performers.top == []
    assert result.risk is None  # 400 -> null alan, paket dusmedi
    assert result.benchmark is not None  # bos dict -> null alanlar
    assert result.benchmark.ticker == "XU100"


def test_portfolio_health_not_found_raises() -> None:
    """Portfoy yoksa (404) GERCEK hata — sessizce yutulmaz."""
    pid = "p-yok"
    with respx.mock:
        respx.get(f"{P}/portfolios/{pid}/snapshot").mock(
            return_value=httpx.Response(404, json={"detail": "error_not_found"})
        )
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        with pytest.raises(FlorenceAPIError) as exc_info:
            portfolio_health(client, pid)
    assert exc_info.value.status_code == 404


# ======================================================================
# H6 — macro_briefing
# ======================================================================
def test_macro_briefing_normalizes_tr_decimals() -> None:
    """Backend string/Turk virgullu degerler float'a normalize edilir."""
    with respx.mock:
        respx.get(f"{P}/economy/currency").mock(
            return_value=httpx.Response(200, json={"USD": {"buying": "42,10"}, "EUR": {"buying": "45,50"}})
        )
        respx.get(f"{P}/economy/gold-prices").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"Type": "gram-altin", "Buying": "2.890,50"},
                    {"Type": "ceyrek-altin", "Buying": "4.850,00"},
                ],
            )
        )
        respx.get(f"{P}/macroeconomy").mock(
            return_value=httpx.Response(
                200, json={"series": [{"id": "us10y", "value": "4,20"}, {"id": "turkey_cpi", "value": 44.3}]}
            )
        )
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        result = macro_briefing(client)
    assert result.currency == {"USD": 42.1, "EUR": 45.5}
    assert result.gold["gram-altin"] == 2890.5
    assert result.gold["ceyrek-altin"] == 4850.0
    assert result.macro["us10y"] == 4.2
    assert result.macro["turkey_cpi"] == 44.3


def test_macro_briefing_series_filter() -> None:
    with respx.mock:
        respx.get(f"{P}/economy/currency").mock(return_value=httpx.Response(200, json={"USD": {"buying": "42,10"}}))
        respx.get(f"{P}/economy/gold-prices").mock(return_value=httpx.Response(200, json=[]))
        respx.get(f"{P}/macroeconomy").mock(
            return_value=httpx.Response(200, json={"series": [{"id": "us10y", "value": "4,20"}, {"id": "cpi", "value": 60.0}]})
        )
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        result = macro_briefing(client, macro_series="us10y")
    assert list(result.macro.keys()) == ["us10y"]
    assert result.macro["us10y"] == 4.2


def test_macro_briefing_missing_auth_raises() -> None:
    """Kimlik yoksa ekonomi (JWT) AuthError firlatir — sessizce yutulmaz."""
    with respx.mock:
        respx.get(f"{P}/economy/currency").mock(
            return_value=httpx.Response(401, json={"detail": "not_authenticated"})
        )
        # Bos store: refresh token da yok -> 401 sonrasi otomatik refresh, HTTP
        # istegi ATILMADAN AuthError yukseltir (keyring/makine bagimsiz).
        client = FlorenceClient(token_store=MemoryTokenStore())
        with pytest.raises(AuthError):
            macro_briefing(client)


# ======================================================================
# CLI — fl helper grubu
# ======================================================================
def test_cli_helper_news_digest_json(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    with respx.mock:
        respx.get(url__regex=r".*/news/THYAO.*").mock(
            return_value=httpx.Response(200, json=[{"title": "H", "url": "https://example.com/h"}])
        )
        respx.get("https://example.com/h").mock(
            return_value=_html_response("<html><body><h1>T</h1><p>Icerik metni.</p></body></html>")
        )
        code, out, err = run_cli(monkeypatch, ["helper", "news-digest", "THYAO", "--json"], env=cli_env)
    assert code == 0
    data = json.loads(out)
    assert data["ticker"] == "THYAO"
    assert data["items"][0]["title"] == "H"
    assert data["items"][0]["content_available"] is True
    assert "Icerik metni." in data["items"][0]["content"]


def test_cli_helper_news_digest_empty_exit_zero(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    """0 haber -> exit 0 + bos liste (kullanici ornegi)."""
    with respx.mock:
        respx.get(url__regex=r".*/news/THYAO.*").mock(return_value=httpx.Response(200, json=[]))
        code, out, err = run_cli(monkeypatch, ["helper", "news-digest", "THYAO", "--json"], env=cli_env)
    assert code == 0
    assert json.loads(out)["items"] == []


def test_cli_helper_article_bad_scheme_exit_2(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    """Gecersiz sema -> kullanim hatasi (exit 2)."""
    code, out, err = run_cli(monkeypatch, ["helper", "article", "file:///etc/passwd"], env=cli_env)
    assert code == 2


def test_cli_helper_article_blocked_host_exit_2(
    monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]
) -> None:
    code, out, err = run_cli(monkeypatch, ["helper", "article", "http://127.0.0.1/x"], env=cli_env)
    assert code == 2


def test_cli_helper_article_ok_json(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    with respx.mock:
        respx.get("https://example.com/makale").mock(
            return_value=_html_response("<html><body><p>Makale metni.</p></body></html>")
        )
        code, out, err = run_cli(
            monkeypatch, ["helper", "article", "https://example.com/makale", "--json"], env=cli_env
        )
    assert code == 0
    data = json.loads(out)
    assert data["content_available"] is True
    assert data["text"] == "Makale metni."


def test_cli_helper_pulse_json(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> None:
    with respx.mock:
        respx.get(f"{P}/market/status").mock(
            return_value=httpx.Response(200, json={"open": True, "next_open_at": "x", "holiday": False})
        )
        respx.get(f"{P}/companies/summary").mock(
            side_effect=[
                httpx.Response(200, json=[{"ticker": "THYAO", "change_pct": 3.2}]),
                httpx.Response(200, json=[]),
                httpx.Response(200, json=[]),
            ]
        )
        respx.get(f"{P}/stats/top").mock(return_value=httpx.Response(200, json=[]))
        code, out, err = run_cli(monkeypatch, ["helper", "pulse", "--json"], env=cli_env)
    assert code == 0
    data = json.loads(out)
    assert data["market_open"] is True
    assert data["gainers"][0]["ticker"] == "THYAO"


def test_cli_helper_group_registered() -> None:
    """``fl helper`` grubu komut agacinda kayitli (11. grup)."""
    from typer.testing import CliRunner

    from florence.cli.app import app

    runner = CliRunner()
    result = runner.invoke(app, ["helper", "--help"])
    assert result.exit_code == 0
    for name in ("news-digest", "article", "briefing", "pulse", "portfolio-health", "macro-briefing"):
        assert name in result.output


# ======================================================================
# MCP — helper_* tool'lari
# ======================================================================
def test_mcp_helper_tools_in_registry() -> None:
    from florence_mcp.registry import GROUPS, TOOLS

    assert "helpers" in GROUPS
    helper_specs = [spec for spec in TOOLS if spec.group == "helpers"]
    assert [spec.name for spec in helper_specs] == [
        "helper_news_digest",
        "helper_fetch_article",
        "helper_ticker_briefing",
        "helper_market_pulse",
        "helper_portfolio_health",
        "helper_macro_briefing",
    ]
    # Hepsi salt-okuma: risk isaretleri yok.
    for spec in helper_specs:
        assert not spec.write and not spec.danger and not spec.credit and not spec.confirm


def test_mcp_disable_helpers_group(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_DISABLE_GROUPS", "helpers")
    from florence_mcp.config import get_disabled_groups
    from florence_mcp.registry import enabled_specs

    specs = enabled_specs(get_disabled_groups())
    assert not any(spec.name.startswith("helper_") for spec in specs)


def test_mcp_helper_market_pulse_end_to_end() -> None:
    from fastmcp import Client

    from florence_mcp import create_server
    from florence_mcp.auth import IDENTITY_NONE, SOURCE_NONE, AuthContext

    with respx.mock:
        respx.get(f"{P}/market/status").mock(
            return_value=httpx.Response(200, json={"open": True, "next_open_at": "x", "holiday": False})
        )
        respx.get(f"{P}/companies/summary").mock(
            side_effect=[
                httpx.Response(200, json=[{"ticker": "THYAO", "change_pct": 3.2}]),
                httpx.Response(200, json=[]),
                httpx.Response(200, json=[]),
            ]
        )
        respx.get(f"{P}/stats/top").mock(return_value=httpx.Response(200, json=[]))
        client = FlorenceClient(token_store=MemoryTokenStore())
        server = create_server(client=client, auth_context=AuthContext(IDENTITY_NONE, SOURCE_NONE))

        async def _call():
            async with Client(server) as mcp:
                return await mcp.call_tool("helper_market_pulse", {"limit": 3})

        result = _run_async(_call())
    assert result.is_error is False
    assert result.structured_content["market_open"] is True
    assert result.structured_content["gainers"][0]["ticker"] == "THYAO"
