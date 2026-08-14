"""``fl portfolio`` (24 komut): favoriler, portfoy CRUD, islemler, analizler.

Alt varlik kurali (tasarim 1.1):
- ``fl portfolio favorite add|remove|list``
- ``fl portfolio tx add|list|update|undo``
Yikici komutlar (delete, tx undo) onay ister (tasarim 3.8 / karar 6).
"""

from __future__ import annotations

from typing import Any

import typer

from .context import CliState
from .interactive import confirm_or_abort
from .options import json_opt, verbose_opt
from .output import emit_json, render_data
from .util import normalize_ticker

__all__ = ["portfolio_app"]

portfolio_app = typer.Typer(help="Favoriler, portföyler ve işlemler.", no_args_is_help=True)
favorite_app = typer.Typer(help="Favoriler.", no_args_is_help=True)
tx_app = typer.Typer(help="İşlemler.", no_args_is_help=True)

#: Portfoy gecmisi/getiri/risk period degerleri.
_PERIODS = ("1w", "1mo", "3mo", "6mo", "1y", "max")


def _state(ctx: typer.Context) -> CliState:
    return ctx.obj


def _emit(state: CliState, data: Any, human: Any = None) -> None:
    if state.effective_json():
        emit_json(data)
    elif human is not None:
        print(human)
    else:
        render_data(data)


def _validate_period(value: str, default: str = "1mo") -> str:
    if value not in _PERIODS:
        allowed = "|".join(_PERIODS)
        raise typer.UsageError(f"Geçersiz period: '{value}' (izin verilenler: {allowed})")
    return value


# ----------------------------------------------------------------------
# Favoriler (3)
# ----------------------------------------------------------------------
@favorite_app.command("add")
def favorite_add(
    ctx: typer.Context,
    ticker: str = typer.Argument(..., help="Ticker (ör. ASELS)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Favoriye ekle (idempotent)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.add_favorite(normalize_ticker(ticker)),
          f"Favoriye eklendi: {normalize_ticker(ticker)}")


@favorite_app.command("remove")
def favorite_remove(
    ctx: typer.Context,
    ticker: str = typer.Argument(..., help="Ticker (ör. ASELS)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Favoriden çıkar."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.remove_favorite(normalize_ticker(ticker)),
          f"Favoriden çıkarıldı: {normalize_ticker(ticker)}")


@favorite_app.command("list")
def favorite_list(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Favori listesi."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.favorites())


# ----------------------------------------------------------------------
# Portfoy CRUD (6)
# ----------------------------------------------------------------------
@portfolio_app.command("create")
def portfolio_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Portföy adı."),
    balance: float = typer.Option(..., "--balance", help="Başlangıç bakiyesi (>0)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Yeni portföy oluşturur."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if balance <= 0:
        raise typer.UsageError("--balance 0'dan büyük olmalı")
    _emit(state, state.client().portfolio.create_portfolio(name, balance))


@portfolio_app.command("list")
def portfolio_list(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Portföy listesi."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.list_portfolios())


@portfolio_app.command("get")
def portfolio_get(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Tek portföy detayı."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.get_portfolio(portfolio_id))


@portfolio_app.command("rename")
def portfolio_rename(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    name: str = typer.Argument(..., help="Yeni ad."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Portföyü yeniden adlandırır."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.rename_portfolio(portfolio_id, name),
          f"Portföy yeniden adlandırıldı: {name}")


@portfolio_app.command("delete")
def portfolio_delete(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    yes: bool = typer.Option(False, "--yes", help="Onay istemeden sil (zorunlu: --json)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Portföyü siler (yıkıcı — onay gerekir)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    confirm_or_abort(state, f"Portföy {portfolio_id} kalıcı silinecek, onaylıyor musunuz?", yes)
    _emit(state, state.client().portfolio.delete_portfolio(portfolio_id),
          f"Portföy silindi: {portfolio_id}")


@portfolio_app.command("duplicate")
def portfolio_duplicate(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    name: str = typer.Argument(..., help="Kopya adı."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Portföyü işlemleriyle kopyalar."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.duplicate_portfolio(portfolio_id, name))


# ----------------------------------------------------------------------
# Islemler (4)
# ----------------------------------------------------------------------
@tx_app.command("add")
def tx_add(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    ticker: str = typer.Argument(..., help="Ticker (ör. THYAO)."),
    type: str = typer.Option(..., "--type", help="İşlem tipi: BUY|SELL."),
    qty: float = typer.Option(..., "--qty", help="Miktar (>0)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """İşlem ekler (piyasa açık olmalı)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if type not in ("BUY", "SELL"):
        raise typer.UsageError("--type BUY veya SELL olmalı")
    if qty <= 0:
        raise typer.UsageError("--qty 0'dan büyük olmalı")
    _emit(
        state,
        state.client().portfolio.add_transaction(portfolio_id, normalize_ticker(ticker), type, qty),
    )


@tx_app.command("list")
def tx_list(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    ticker: str | None = typer.Option(None, "--ticker", help="Ticker filtresi."),
    type: str | None = typer.Option(None, "--type", help="Tip filtresi (BUY|SELL)."),
    start: str | None = typer.Option(None, "--start", help="Başlangıç (ISO)."),
    end: str | None = typer.Option(None, "--end", help="Bitiş (ISO)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """İşlem listesi (filtreli)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(
        state,
        state.client().portfolio.get_transactions(
            portfolio_id, ticker=ticker, tx_type=type, start=start, end=end
        ),
    )


@tx_app.command("update")
def tx_update(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    tx_id: str = typer.Argument(..., help="İşlem kimliği."),
    price: float | None = typer.Option(None, "--price", help="Yeni fiyat."),
    qty: float | None = typer.Option(None, "--qty", help="Yeni miktar."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """İşlemi günceller (en az bir alan zorunlu)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if price is None and qty is None:
        raise typer.UsageError("En az biri gerekli: --price veya --qty")
    _emit(
        state,
        state.client().portfolio.update_transaction(portfolio_id, tx_id, price=price, quantity=qty),
    )


@tx_app.command("undo")
def tx_undo(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    yes: bool = typer.Option(False, "--yes", help="Onay istemeden geri al (zorunlu: --json)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Son işlemi geri alır (yıkıcı — onay gerekir)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    confirm_or_abort(
        state, f"Portföy {portfolio_id} son işlemi geri alınacak, onaylıyor musunuz?", yes
    )
    _emit(state, state.client().portfolio.undo_transaction(portfolio_id), "Son işlem geri alındı")


# ----------------------------------------------------------------------
# Analizler (11 — salt-okuma)
# ----------------------------------------------------------------------
@portfolio_app.command("valuation")
def portfolio_valuation(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Değerleme."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.valuation(portfolio_id))


@portfolio_app.command("diversification")
def portfolio_diversification(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Çeşitlendirme."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.diversification(portfolio_id))


@portfolio_app.command("performers")
def portfolio_performers(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    top: int = typer.Option(5, "--top", help="Gösterilecek adet."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """En iyi/en kötü hisseler."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.performers(portfolio_id, top_n=top))


@portfolio_app.command("history")
def portfolio_history(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    period: str = typer.Option("1mo", "--period", help="1w|1mo|3mo|6mo|1y|max."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Değer geçmişi."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.history(portfolio_id, _validate_period(period)))


@portfolio_app.command("returns")
def portfolio_returns(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    period: str = typer.Option("1mo", "--period", help="1w|1mo|3mo|6mo|1y|max."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Getiri (abs/total/CAGR)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.returns(portfolio_id, _validate_period(period)))


@portfolio_app.command("risk")
def portfolio_risk(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    period: str = typer.Option("1y", "--period", help="1w|1mo|3mo|6mo|1y|max."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Risk (volatility/drawdown/sharpe)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.risk(portfolio_id, _validate_period(period)))


@portfolio_app.command("benchmark")
def portfolio_benchmark(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    ticker: str = typer.Option("XU100", "--ticker", help="Karşılaştırma endeksi."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """XU100 karşılaştırması."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.benchmark(portfolio_id, ticker=ticker))


@portfolio_app.command("performance")
def portfolio_performance(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Verimlilik skoru."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.performance(portfolio_id))


@portfolio_app.command("stats")
def portfolio_stats(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """İşlem istatistikleri."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.stats(portfolio_id))


@portfolio_app.command("snapshot")
def portfolio_snapshot(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Birleşik özet."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().portfolio.snapshot(portfolio_id))


@portfolio_app.command("export")
def portfolio_export(
    ctx: typer.Context,
    portfolio_id: str = typer.Argument(..., help="Portföy kimliği."),
    output: str | None = typer.Option(None, "--output", help="CSV'yi dosyaya yaz."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """İşlemleri CSV olarak dışa aktarır (ham CSV)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    csv_text = state.client().portfolio.export_csv(portfolio_id)
    if output:
        from pathlib import Path

        dest = Path(output)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(csv_text, encoding="utf-8")
        if state.effective_json():
            emit_json({"path": str(dest), "bytes": dest.stat().st_size})
        else:
            print(f"CSV yazıldı: {dest}")
        return
    if state.effective_json():
        emit_json({"csv": csv_text})
    else:
        print(csv_text)


portfolio_app.add_typer(favorite_app, name="favorite")
portfolio_app.add_typer(tx_app, name="tx")
