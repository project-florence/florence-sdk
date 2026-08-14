"""``fl market`` (11), ``fl economy`` (6), ``fl price`` (kisa yol) ve
``fl download`` (hisse mum CSV'si) komutlari.

``fl price`` / ``fl price history``, ``fl market price`` / ``fl market
history`` ile AYNI isi yapar (kisa yol — es anlamli ayri komut degil).
``fl download <ticker> <period>`` = fiyat gecmisi -> CSV dosyasi (yillik
veri export'u karisikligi yok: o is ``fl export``'un).
"""

from __future__ import annotations

from typing import Any

import typer

from .context import CliState
from .interactive import CliRuntimeError
from .options import json_opt, verbose_opt
from .output import emit_json, normalize_economy, render_data
from .util import default_download_path, extract_rows, normalize_ticker, parse_period, write_csv

__all__ = ["download_impl", "economy_app", "market_app", "price_app"]

market_app = typer.Typer(help="BIST piyasa verisi.", no_args_is_help=True)
economy_app = typer.Typer(help="Altın, döviz ve makro ekonomi.", no_args_is_help=True)
price_app = typer.Typer(
    help="Fiyat kısa yolu (fl price THYAO / fl price history ASELS 3mo 5m).",
    invoke_without_command=True,
    no_args_is_help=False,
)


def _state(ctx: typer.Context) -> CliState:
    return ctx.obj


def _output(state: CliState, data: Any, *, economy: bool = False) -> None:
    """Ortak cikti: --json'da birebir (ekonomi normalize), insan tablo."""
    if economy:
        data = normalize_economy(data)
    if state.effective_json():
        emit_json(data)
    else:
        render_data(data)


# ----------------------------------------------------------------------
# fl market — 11 komut
# ----------------------------------------------------------------------
@market_app.command("price")
def market_price(
    ctx: typer.Context,
    ticker: str = typer.Argument(..., help="Ticker (ör. THYAO)."),
    interval: str = typer.Option("5m", "--interval", help="Aralık: 5m|30m|1h|1d."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Güncel fiyat (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(state, state.client().market.current_price(normalize_ticker(ticker), interval))


@market_app.command("history")
def market_history(
    ctx: typer.Context,
    ticker: str = typer.Argument(..., help="Ticker (ör. ASELS)."),
    period: str | None = typer.Argument(None, help="Periyot (konumsal: 3mo, 6mo, 1y)."),
    interval: str | None = typer.Argument(None, help="Aralık (konumsal: 5m, 1d)."),
    period_opt: str | None = typer.Option(None, "--period", help="Periyot (bayrak: 3mo)."),
    interval_opt: str | None = typer.Option(None, "--interval", help="Aralık (bayrak: 5m)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Fiyat geçmişi (mum verisi, public). Varsayılan: 3mo / 5m."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _price_history(state, ticker, period, interval, period_opt, interval_opt)


def _price_history(
    state: CliState,
    ticker: str,
    period_arg: str | None,
    interval_arg: str | None,
    period_opt: str | None = None,
    interval_opt: str | None = None,
) -> None:
    t = normalize_ticker(ticker)
    period = parse_period(period_arg or period_opt or "3mo")
    interval = interval_arg or interval_opt or "5m"
    data = state.client().market.price_history(t, period, interval)
    _output(state, data)


@market_app.command("companies")
def market_companies(
    ctx: typer.Context,
    sort: str = typer.Option("alphabetical", "--sort", help="Sıralama (alphabetical)."),
    limit: int = typer.Option(50, "--limit", help="Kayıt sayısı."),
    offset: int = typer.Option(0, "--offset", help="Atlama."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """BIST şirket listesi (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(state, state.client().market.companies(sort=sort, offset=offset, limit=limit))


@market_app.command("tickers")
def market_tickers(
    ctx: typer.Context,
    sort: str = typer.Option("alphabetical", "--sort", help="Sıralama (alphabetical)."),
    limit: int = typer.Option(50, "--limit", help="Kayıt sayısı."),
    offset: int = typer.Option(0, "--offset", help="Atlama."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """BIST ticker listesi (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(state, state.client().market.tickers(sort=sort, offset=offset, limit=limit))


@market_app.command("search")
def market_search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Arama sorgusu (alias destekli)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Şirket ara (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(state, state.client().market.search_companies(query))


@market_app.command("info")
def market_info(
    ctx: typer.Context,
    ticker: str = typer.Argument(..., help="Ticker (ör. THYAO)."),
    md: bool = typer.Option(False, "--md", help="Markdown profil çıktısı."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Şirket profili (--md: markdown serileştirme)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    t = normalize_ticker(ticker)
    if md:
        data = state.client().market.company_info_md(t)
        if state.effective_json():
            emit_json({"markdown": data} if isinstance(data, str) else data)
        else:
            print(data if isinstance(data, str) else str(data))
        return
    _output(state, state.client().market.company_info(t))


@market_app.command("summary")
def market_summary(
    ctx: typer.Context,
    sort: str = typer.Option(
        "popular",
        "--sort",
        help="popular|alphabetical|gainers|losers|price_high|price_low|volume|market_cap.",
    ),
    limit: int = typer.Option(50, "--limit", help="Kayıt sayısı."),
    offset: int = typer.Option(0, "--offset", help="Atlama."),
    tickers: str | None = typer.Option(None, "--tickers", help="Virgüllü ticker filtresi."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Şirket özet tablosu (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(
        state,
        state.client().market.companies_summary(
            limit=limit, offset=offset, sort=sort, tickers=tickers
        ),
    )


@market_app.command("news")
def market_news(
    ctx: typer.Context,
    ticker: str = typer.Argument(..., help="Ticker (ör. THYAO)."),
    amount: int = typer.Option(10, "--amount", help="Haber adedi."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Hisse haberleri (JWT gerekir)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(state, state.client().market.news(normalize_ticker(ticker), amount=amount))


@market_app.command("status")
def market_status(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Piyasa durumu (public; 60s cache)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    data = state.client().market.market_status()
    if state.effective_json():
        emit_json(data)
        return
    if isinstance(data, dict):
        from .output import render_kv

        render_kv(data)
    else:
        render_data(data)


@market_app.command("stats")
def market_stats(
    ctx: typer.Context,
    ticker: str = typer.Argument(..., help="Ticker (ör. TUPRS)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Ticker bazlı sayaçlar (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(state, state.client().market.stats(normalize_ticker(ticker)))


@market_app.command("top")
def market_top(
    ctx: typer.Context,
    limit: int = typer.Option(50, "--limit", help="Kayıt sayısı."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Popüler ticker'lar (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(state, state.client().market.stats_top(limit=limit))


# ----------------------------------------------------------------------
# fl price — kisa yol (flat grup: THYAO -> current, history -> gecmis)
# ----------------------------------------------------------------------
@price_app.callback()
def price_callback(
    ctx: typer.Context,
    ticker: str | None = typer.Argument(None, help="Ticker (güncel fiyat)."),
    interval: str = typer.Option("5m", "--interval", help="Aralık: 5m|30m|1h|1d."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Güncel fiyat (kısa yol). Geçmiş için: fl price history <ticker> [period] [interval]."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if ctx.invoked_subcommand is not None:
        return
    if ticker is None:
        raise typer.UsageError("Ticker belirtin veya 'history' alt komutunu kullanın")
    _output(state, state.client().market.current_price(normalize_ticker(ticker), interval))


@price_app.command("history")
def price_history_cmd(
    ctx: typer.Context,
    ticker: str = typer.Argument(..., help="Ticker (ör. ASELS)."),
    period: str | None = typer.Argument(None, help="Periyot (konumsal: 3mo, 6mo, 1y)."),
    interval: str | None = typer.Argument(None, help="Aralık (konumsal: 5m, 1d)."),
    period_opt: str | None = typer.Option(None, "--period", help="Periyot (bayrak: 3mo)."),
    interval_opt: str | None = typer.Option(None, "--interval", help="Aralık (bayrak: 5m)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Fiyat geçmişi (kısa yol). Varsayılan: 3mo / 5m."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _price_history(state, ticker, period, interval, period_opt, interval_opt)


# ----------------------------------------------------------------------
# fl economy — 6 komut (backend "40,25" -> CLI float normalizasyonu)
# ----------------------------------------------------------------------
@economy_app.command("gold")
def economy_gold(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Altın fiyatları (16 kalem)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(state, state.client().economy.gold_prices(), economy=True)


@economy_app.command("silver")
def economy_silver(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Gümüş fiyatı."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(state, state.client().economy.silver_price(), economy=True)


@economy_app.command("platinum")
def economy_platinum(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Gram platin fiyatı."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(state, state.client().economy.platinum_price(), economy=True)


@economy_app.command("palladium")
def economy_palladium(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Gram paladyum fiyatı."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(state, state.client().economy.palladium_price(), economy=True)


@economy_app.command("currency")
def economy_currency(
    ctx: typer.Context,
    symbols: str | None = typer.Option(None, "--symbols", help="Virgüllü filtre (USD,EUR)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Döviz kurları."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(state, state.client().economy.currency(symbols=symbols), economy=True)


@economy_app.command("macro")
def economy_macro(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """FRED makro serileri (14 seri)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _output(state, state.client().economy.macroeconomy(), economy=True)


# ----------------------------------------------------------------------
# fl download — hisse mum CSV'si (app.py'den cagrilir)
# ----------------------------------------------------------------------
def download_impl(
    ctx: typer.Context,
    ticker: str,
    period: str,
    interval: str,
    output: str | None,
) -> None:
    """Fiyat gecmisini ceker, CSV dosyasina yazar (hisse mum verisi)."""
    state = _state(ctx)
    t = normalize_ticker(ticker)
    normalized = parse_period(period)
    data = state.client().market.price_history(t, normalized, interval)
    rows = extract_rows(data)
    if not rows:
        raise CliRuntimeError(
            f"Fiyat verisi alınamadı ({t} {normalized}); yanıt boş.",
            code="empty_data",
        )
    dest = output or default_download_path(t, normalized)
    path = write_csv(rows, dest)
    if state.effective_json():
        emit_json(
            {
                "ticker": t,
                "period": normalized,
                "interval": interval,
                "path": str(path),
                "rows": len(rows),
                "bytes": path.stat().st_size,
            }
        )
    else:
        print(f"CSV yazıldı: {path} ({len(rows)} satır)")
