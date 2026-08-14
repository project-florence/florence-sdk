"""``fl analysis`` — duzlestirilmis analiz grubu (13 komut).

Kullanici karari (2026-08-14): tasarimdaki ``fl analysis report generate`` /
``fl analysis simulation run`` alt komutlari yerine DUZ form:

- ``fl report <ticker> [--deep] [--purpose ...]`` -> generate
  (``--deep`` yoksa default QUICK) + alt komutlar: search, history, get,
  download, info
- ``fl simulate <ticker> --days N [--bounds 0.05] [--target pct]`` -> run
  + alt komutlar: cost, estimate, history, get
- ``fl fit``, ``fl similar <tickers>``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from .context import CliState
from .options import json_opt, verbose_opt
from .output import emit_json, render_data, render_kv
from .util import extract_rows, normalize_ticker, split_tickers

__all__ = ["analysis_app"]

analysis_app = typer.Typer(help="Raporlar, simülasyonlar ve eşleştirme.", no_args_is_help=True)
report_app = typer.Typer(
    help="Raporlar (fl report <ticker> = generate).",
    invoke_without_command=True,
    no_args_is_help=False,
)
simulate_app = typer.Typer(
    help="Simülasyonlar (fl simulate <ticker> --days N = run).",
    invoke_without_command=True,
    no_args_is_help=False,
)

_REPORT_TYPES = ("quick_report", "deep_report")
_DOWNLOAD_FORMATS = ("md", "docx", "pdf")


def _state(ctx: typer.Context) -> CliState:
    return ctx.obj


def _emit(state: CliState, data: Any) -> None:
    if state.effective_json():
        emit_json(data)
    else:
        render_data(data)


def _validate_days(days: int) -> int:
    if not 1 <= days <= 370:
        raise typer.UsageError("--days 1 ile 370 arasında olmalı")
    return days


# ----------------------------------------------------------------------
# fl report — 6 komut (generate = duz form)
# ----------------------------------------------------------------------
@report_app.callback()
def report_generate_cb(
    ctx: typer.Context,
    ticker: str | None = typer.Argument(None, help="Ticker (rapor üretimi)."),
    deep: bool = typer.Option(False, "--deep", help="Derin rapor (yoksa QUICK)."),
    purpose: str | None = typer.Option(None, "--purpose", help="Kullanıcının sorusu."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Rapor üretir (kredi harcar). Alt komutlar: search, history, get, download, info."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if ctx.invoked_subcommand is not None:
        return
    if ticker is None:
        raise typer.UsageError(
            "Ticker belirtin (fl report ASELS) veya bir alt komut kullanın "
            "(search|history|get|download|info)"
        )
    report_type = "deep_report" if deep else "quick_report"
    data = state.client().analysis.generate_report(
        normalize_ticker(ticker), report_type, purpose=purpose
    )
    if state.effective_json():
        emit_json(data)
        return
    summary = {k: v for k, v in data.items() if k != "report"} if isinstance(data, dict) else {}
    if summary:
        render_kv(summary)
    report = data.get("report") if isinstance(data, dict) else None
    if isinstance(report, str) and report:
        head = report[:2000]
        if len(report) > 2000:
            head += "\n… (tam metin için --json kullanın)"
        print(head)


@report_app.command("search")
def report_search_cmd(
    ctx: typer.Context,
    q: str = typer.Argument(..., help="Arama sorgusu (başlık/içerik)."),
    limit: int = typer.Option(20, "--limit", help="Kayıt sayısı."),
    offset: int = typer.Option(0, "--offset", help="Atlama."),
    sort: str = typer.Option("created_at", "--sort", help="Sıralama alanı."),
    order: str = typer.Option("desc", "--order", help="asc|desc."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Raporlarda ara."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(
        state,
        state.client().analysis.search_reports(
            q, sort=sort, order=order, limit=limit, offset=offset
        ),
    )


@report_app.command("history")
def report_history_cmd(
    ctx: typer.Context,
    sort: str = typer.Option("created_at", "--sort", help="Sıralama alanı."),
    order: str = typer.Option("desc", "--order", help="asc|desc."),
    limit: int = typer.Option(20, "--limit", help="Kayıt sayısı (SDK limitsiz; CLI keser)."),
    offset: int = typer.Option(0, "--offset", help="Atlama."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Rapor geçmişi."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    data = state.client().analysis.report_history(sort=sort, order=order)
    rows = extract_rows(data)
    sliced = rows[offset : offset + limit]
    if state.effective_json():
        emit_json(sliced if rows else data)
    else:
        render_data(sliced if rows else data)


@report_app.command("get")
def report_get_cmd(
    ctx: typer.Context,
    report_id: int = typer.Argument(..., help="Rapor kimliği."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Tek rapor (markdown içerik)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    data = state.client().analysis.get_report(report_id)
    if state.effective_json():
        emit_json(data)
    elif isinstance(data, str):
        print(data)
    elif isinstance(data, dict) and isinstance(data.get("report"), str):
        print(data["report"])
    else:
        render_data(data)


@report_app.command("download")
def report_download_cmd(
    ctx: typer.Context,
    report_id: int = typer.Argument(..., help="Rapor kimliği."),
    format: str = typer.Option(..., "--format", help="md|docx|pdf."),
    output: str | None = typer.Option(None, "--output", help="Hedef dosya yolu."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Raporu dosya olarak indirir (md/docx/pdf)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if format not in _DOWNLOAD_FORMATS:
        raise typer.UsageError("--format md, docx veya pdf olmalı")
    dest = output or f"report-{report_id}.{format}"
    result = state.client().analysis.download_report(report_id, format, dest_path=dest)
    if state.effective_json():
        path = Path(dest)
        emit_json(
            {
                "report_id": report_id,
                "format": format,
                "path": str(path),
                "bytes": path.stat().st_size if path.exists() else None,
            }
        )
    else:
        print(f"İndirildi: {result if isinstance(result, str) else dest}")


@report_app.command("info")
def report_info_cmd(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Rapor maliyetleri ve dokümantasyon."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().analysis.report_info())


# ----------------------------------------------------------------------
# fl simulate — 5 komut (run = duz form)
# ----------------------------------------------------------------------
@simulate_app.callback()
def simulate_run_cb(
    ctx: typer.Context,
    ticker: str | None = typer.Argument(None, help="Ticker (simülasyon)."),
    days: int | None = typer.Option(None, "--days", help="Gün sayısı (1..370)."),
    bounds: float = typer.Option(0.05, "--bounds", help="Bant genişliği (default 0.05)."),
    target: str | None = typer.Option(None, "--target", help="Hedef yüzde (opsiyonel)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Simülasyon çalıştırır (kredi harcar). Alt komutlar: cost, estimate, history, get."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if ctx.invoked_subcommand is not None:
        return
    if ticker is None:
        raise typer.UsageError(
            "Ticker belirtin (fl simulate THYAO --days 30) veya bir alt komut "
            "kullanın (cost|estimate|history|get)"
        )
    if days is None:
        raise typer.UsageError("--days zorunlu (1..370)")
    _validate_days(days)
    _emit(
        state,
        state.client().analysis.simulate(
            normalize_ticker(ticker), days, bounds=str(bounds), target=target
        ),
    )


@simulate_app.command("cost")
def simulate_cost_cmd(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Günlük simülasyon maliyeti."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().analysis.per_day_cost())


@simulate_app.command("estimate")
def simulate_estimate_cmd(
    ctx: typer.Context,
    ticker: str = typer.Argument(..., help="Ticker (ör. ASELS)."),
    days: int = typer.Option(..., "--days", help="Gün sayısı (1..370)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Maliyet tahmini."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _validate_days(days)
    _emit(state, state.client().analysis.estimate_cost(normalize_ticker(ticker), days))


@simulate_app.command("history")
def simulate_history_cmd(
    ctx: typer.Context,
    limit: int = typer.Option(20, "--limit", help="Kayıt sayısı (≤100)."),
    offset: int = typer.Option(0, "--offset", help="Atlama."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Simülasyon geçmişi."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if limit > 100:
        raise typer.UsageError("--limit en fazla 100 olabilir")
    _emit(state, state.client().analysis.simulation_history(limit=limit, offset=offset))


@simulate_app.command("get")
def simulate_get_cmd(
    ctx: typer.Context,
    sim_id: int = typer.Argument(..., help="Simülasyon kimliği."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Tek simülasyon detayı."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().analysis.simulation_detail(sim_id))


# ----------------------------------------------------------------------
# fl analysis fit / similar
# ----------------------------------------------------------------------
@analysis_app.command("fit")
def analysis_fit(
    ctx: typer.Context,
    horizon: str = typer.Option("long", "--horizon", help="Ufuk (ör. long)."),
    profitability: str = typer.Option("high", "--profitability", help="Kârlılık (ör. high)."),
    risk_tolerance: str = typer.Option("medium", "--risk-tolerance", help="Risk toleransı."),
    limit: int = typer.Option(5, "--limit", help="Sonuç sayısı."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Profil kriterlerine göre hisse eşleştirir (advisor)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(
        state,
        state.client().analysis.fit_stocks(
            horizon=horizon,
            profitability=profitability,
            risk_tolerance=risk_tolerance,
            limit=limit,
        ),
    )


@analysis_app.command("similar")
def analysis_similar(
    ctx: typer.Context,
    tickers: str = typer.Argument(..., help="Virgüllü ticker listesi (1–50)."),
    limit: int = typer.Option(5, "--limit", help="Sonuç sayısı (≤50)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Portföye benzer hisseler (advisor)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    ticker_list = split_tickers(tickers)
    if not 1 <= len(ticker_list) <= 50:
        raise typer.UsageError("Ticker sayısı 1 ile 50 arasında olmalı")
    if limit > 50:
        raise typer.UsageError("--limit en fazla 50 olabilir")
    _emit(state, state.client().analysis.portfolio_profile(ticker_list, limit=limit))


analysis_app.add_typer(report_app, name="report")
analysis_app.add_typer(simulate_app, name="simulate")
