"""``fl helper`` — semantik yardimci kompozitler (tek niyet = tek komut).

Endpoint komutlarinin UZERINE biner (helpers-design.md Bolum 4.2): komutlar
``florence/helpers/`` cekirdegini cagirir; is mantigi CLI'da YOKTUR.

Exit code'lar:
- 0: basari (bos/kisa/kismi sonuc DAHIL)
- 1: altyapi hatasi (ag, kimlik, ozellik yok) — ``_run`` FlorenceError'i yonetir
- 2: kullanim hatasi (gecersiz URL semasi/hostu — ``typer.BadParameter``)

``--json`` ciktisi helper modelinin birebir serilestirilmisidir
(``model_dump()`` = MCP semasi ile ayni kaynak).
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console

from ..helpers import (
    fetch_article,
    macro_briefing,
    market_pulse,
    news_digest,
    portfolio_health,
    ticker_briefing,
    validate_fetch_url,
)
from .context import CliState
from .options import json_opt, verbose_opt
from .output import emit_json, render_table, tr_number
from .util import normalize_ticker

__all__ = ["helper_app"]

helper_app = typer.Typer(
    help="Semantik yardımcı kompozitler (tek niyet = tek komut).",
    no_args_is_help=True,
)

console = Console()


def _state(ctx: typer.Context) -> CliState:
    return ctx.obj


def _ticker_rows(rows: list[Any], *keys: str) -> list[dict[str, Any]]:
    """PulseRow/PerformerRow listesini tablo satirina cevirir (bos -> bos liste)."""
    return [
        {key: getattr(row, key) for key in keys if getattr(row, key, None) is not None}
        for row in rows
    ]


def _section(title: str, rows: list[dict[str, Any]]) -> None:
    """Bolum basligi + tablo (bos satirlar icin 'Kayıt yok' cikar)."""
    console.print(f"[bold]{title}[/bold]")
    render_table(rows)


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"%{tr_number(value)}"


# ----------------------------------------------------------------------
# H1 — news-digest
# ----------------------------------------------------------------------
@helper_app.command("news-digest")
def helper_news_digest(
    ctx: typer.Context,
    ticker: str = typer.Argument(..., help="Ticker (ör. THYAO)."),
    amount: int = typer.Option(5, "--amount", min=1, max=10, help="Haber adedi (1-10; news 10/dk)."),
    no_content: bool = typer.Option(False, "--no-content", help="İçerik çekme (saf liste modu)."),
    max_chars: int = typer.Option(6000, "--max-chars", help="Haber başına azami karakter."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Haber özeti + içerik (JWT + news feature gerekir; N harici HTTP isteği)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    result = news_digest(
        state.client(),
        normalize_ticker(ticker),
        amount=amount,
        fetch_content=not no_content,
        max_chars=max_chars,
    )
    if state.effective_json():
        emit_json(result.model_dump())
        return
    for item in result.items:
        console.print(f"[bold]{item.title or '(başlık yok)'}[/bold]")
        if item.url:
            console.print(f"  [dim]{item.url}[/dim]")
        if item.content:
            console.print(f"  {item.content[:400]}")
        elif item.fetch_error:
            console.print(f"  [yellow]içerik alınamadı: {item.fetch_error}[/yellow]")
    console.print(f"[cyan]{result.fetched} haber çekildi ({result.failed} başarısız)[/cyan]")


# ----------------------------------------------------------------------
# H2 — article
# ----------------------------------------------------------------------
@helper_app.command("article")
def helper_article(
    ctx: typer.Context,
    url: str = typer.Argument(..., help="Makale URL'si (yalnızca http/https)."),
    max_chars: int = typer.Option(8000, "--max-chars", help="Azami karakter."),
    timeout: float = typer.Option(15.0, "--timeout", help="Okuma zaman aşımı (saniye)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """URL'deki makaleyi düz metin olarak çeker (SSRF korumalı)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if validate_fetch_url(url) is not None:
        raise typer.BadParameter("Yalnızca http/https URL'leri desteklenir (şema/host engelli).")
    article = fetch_article(url, max_chars=max_chars, timeout=timeout)
    if state.effective_json():
        emit_json(article.model_dump())
        return
    if article.error:
        console.print(f"[yellow]İçerik alınamadı: {article.error}[/yellow]")
        return
    if not article.content_available:
        console.print("[yellow]İçerik çıkarılamadı (JS ile render ediliyor olabilir).[/yellow]")
        return
    if article.title:
        console.print(f"[bold]{article.title}[/bold]")
    print(article.text)


# ----------------------------------------------------------------------
# H3 — briefing
# ----------------------------------------------------------------------
@helper_app.command("briefing")
def helper_briefing(
    ctx: typer.Context,
    ticker: str = typer.Argument(..., help="Ticker (ör. THYAO)."),
    news_amount: int = typer.Option(3, "--news-amount", min=1, max=10, help="Haber adedi (1-10)."),
    trend_period: str = typer.Option("1mo", "--trend-period", help="Trend periyodu (ör. 1mo, 3mo)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Ticker tek bakışta: fiyat + profil + trend + son haberler (4 backend çağrısı)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    result = ticker_briefing(
        state.client(),
        normalize_ticker(ticker),
        news_amount=news_amount,
        trend_period=trend_period,
    )
    if state.effective_json():
        emit_json(result.model_dump())
        return
    lines: list[str] = []
    if result.quote:
        lines.append(
            f"Fiyat: {tr_number(result.quote.price)}   "
            f"Değişim: {_fmt_pct(result.quote.change_pct)}   "
            f"Piyasa: {result.quote.market_status or '—'}"
        )
    else:
        lines.append("Fiyat: — (işlem yok / veri alınamadı)")
    if result.company:
        lines.append(f"Şirket: {result.company.name or '—'}   Sektör: {result.company.sector or '—'}")
    if result.trend:
        spark = " ".join(
            "▁▂▃▄▅▆▇█"[min(7, int((v - lo) / (hi - lo + 1e-9) * 7))]
            for v, lo, hi in _spark_windows(result.trend.sparkline)
        )
        lines.append(f"Trend ({result.trend.period}): {_fmt_pct(result.trend.change_pct)}  {spark}")
    lines.append(f"Haberler ({len(result.news)}):")
    for headline in result.news:
        lines.append(f"  • {headline.title or '(başlık yok)'} — {headline.url}")
    from rich.panel import Panel

    console.print(Panel("\n".join(lines), title=f"{result.ticker} — Tek Bakışta", border_style="cyan"))


def _spark_windows(values: list[float]):
    """Sparkline karakterlerini ureten yardimci: (deger, min, max) uclusu."""
    if not values:
        return []
    low, high = min(values), max(values)
    if high - low < 1e-9:
        high = low + 1.0
    return [(value, low, high) for value in values]


# ----------------------------------------------------------------------
# H4 — pulse
# ----------------------------------------------------------------------
@helper_app.command("pulse")
def helper_pulse(
    ctx: typer.Context,
    limit: int = typer.Option(5, "--limit", min=1, max=50, help="Her liste icin kayit sayisi."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Piyasa durumu: açık mı, kazananlar, kaybedenler, popülerler (5 public çağrı)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    result = market_pulse(state.client(), limit=limit)
    if state.effective_json():
        emit_json(result.model_dump())
        return
    durum = "Açık" if result.market_open else ("Kapalı" if result.market_open is False else "Bilinmiyor")
    status_line = f"Piyasa: {durum}"
    if result.next_open_at:
        status_line += f"   Sonraki açılış: {result.next_open_at}"
    console.print(f"[bold]{status_line}[/bold]")
    _section("Kazananlar", _ticker_rows(result.gainers, "ticker", "change_pct"))
    _section("Kaybedenler", _ticker_rows(result.losers, "ticker", "change_pct"))
    _section("Hacim Liderleri", _ticker_rows(result.volume_leaders, "ticker", "volume"))
    _section("En Popülerler", _ticker_rows(result.most_popular, "ticker", "count"))


# ----------------------------------------------------------------------
# H5 — portfolio-health
# ----------------------------------------------------------------------
@helper_app.command("portfolio-health")
def helper_portfolio_health(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy ID'si."),
    risk_period: str = typer.Option("1y", "--risk-period", help="Risk periyodu (1w..1y)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Portföy sağlığı: değer, kazanan/kaybeden, risk, benchmark (JWT gerekir)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    result = portfolio_health(state.client(), portfolio_id, risk_period=risk_period)
    if state.effective_json():
        emit_json(result.model_dump())
        return
    console.print(
        f"[bold]Portföy {result.portfolio_id}: {tr_number(result.total_value)} TL[/bold]"
        f"   Kâr/Zarar: {tr_number(result.pnl) if result.pnl is not None else '—'} TL"
        f" ({_fmt_pct(result.pnl_pct)})"
    )
    if result.performers:
        _section("En İyiler", _ticker_rows(result.performers.top, "ticker", "return_pct"))
        _section("En Kötüler", _ticker_rows(result.performers.bottom, "ticker", "return_pct"))
    if result.risk:
        console.print(
            f"[bold]Risk:[/bold] oynaklık {_fmt_pct(result.risk.volatility)}"
            f"   maks. düşüş {_fmt_pct(result.risk.max_drawdown)}"
            f"   sharpe {result.risk.sharpe if result.risk.sharpe is not None else '—'}"
        )
    if result.benchmark:
        console.print(
            f"[bold]Benchmark ({result.benchmark.ticker}):[/bold]"
            f" portföy {_fmt_pct(result.benchmark.portfolio_return_pct)}"
            f"   endeks {_fmt_pct(result.benchmark.benchmark_return_pct)}"
            f"   fark {_fmt_pct(result.benchmark.diff_pct)}"
        )
    if result.diversification:
        console.print(
            f"[bold]Dağılım:[/bold] hisse {_fmt_pct(result.diversification.stocks)}"
            f"   döviz {_fmt_pct(result.diversification.forex)}"
            f"   metal {_fmt_pct(result.diversification.metals)}"
        )


# ----------------------------------------------------------------------
# H6 — macro-briefing
# ----------------------------------------------------------------------
@helper_app.command("macro-briefing")
def helper_macro_briefing(
    ctx: typer.Context,
    symbols: str = typer.Option("USD,EUR,GBP", "--symbols", help="Virgüllü döviz filtresi."),
    macro_series: str | None = typer.Option(None, "--macro-series", help="Virgüllü FRED seri kodu filtresi."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Makro manzara: döviz + altın + FRED serileri (3 backend çağrısı, JWT)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    result = macro_briefing(state.client(), symbols=symbols, macro_series=macro_series)
    if state.effective_json():
        emit_json(result.model_dump())
        return
    if result.currency:
        _section("Döviz", [{"kur": key, "değer": value} for key, value in result.currency.items()])
    if result.gold:
        _section("Altın", [{"kalem": key, "fiyat": value} for key, value in result.gold.items()])
    if result.macro:
        _section("Makro Seriler", [{"seri": key, "değer": value} for key, value in result.macro.items()])
    if not (result.currency or result.gold or result.macro):
        console.print("Makro veri alınamadı (kimlik gerekli olabilir).")
