"""Typer uygulamasi: gruplarin kaydi, global ``--json``/``--verbose``,
hata yakalayici ve entry point'ler (``florence`` + ``fl``).

Exit code'lar (tasarim 3.2):
- 0: basari
- 1: calisma hatasi (FlorenceError, CliRuntimeError, export timeout, ...)
- 2: kullanim hatasi (bilinmeyen komut/bayrak, eksik arguman, prompt
  gerektigi halde ``--json``/TTY yok, config allowlist disi anahtar)
- 130: Ctrl+C (standart)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

try:  # typer >= 0.16: click vendored (typer._click)
    import typer._click as click  # type: ignore[attr-defined]
    import typer._click.exceptions as click_exceptions  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover — typer < 0.16: gercek click
    import click
    import click.exceptions as click_exceptions  # type: ignore[no-redef]

from .. import __version__
from ..errors import FlorenceError
from .config_cli import CliConfig
from .context import CliState
from .interactive import CliRuntimeError, PromptRequiredError
from .options import json_opt, verbose_opt
from .output import emit_error

__all__ = ["app", "main"]

app = typer.Typer(
    name="florence",
    help="Florence CLI — BIST verisi, portföy, analiz ve veri dışa aktarım komutları.",
    no_args_is_help=True,
    invoke_without_command=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)

#: En son kurulan durum — hata raporlama icin (--json modunu bilmek gerek).
_last_state: CliState | None = None


@app.callback(invoke_without_command=True)
def _main_callback(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False, "--json", help="Çıktıyı JSON olarak bas (makine-okunur)."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Ayrıntılı loglama (stderr)."),
    version: bool = typer.Option(False, "--version", help="Yerel paket sürümünü göster."),
) -> None:
    """Global bayraklar her komuttan önce yazilabilir: ``fl --json <komut>``."""
    global _last_state
    state = CliState(json_output=json_output, verbose=verbose, config=CliConfig())
    _last_state = state
    ctx.obj = state
    if version:
        print(f"florence-sdk {__version__}")
        raise typer.Exit()


# ----------------------------------------------------------------------
# Grup kaydi (11 grup + price kisa yolu)
# ----------------------------------------------------------------------
from . import (  # noqa: E402  (dairesel bagimliligi onlemek icin sonra import)
    commands_analysis,
    commands_auth,
    commands_digest,
    commands_export,
    commands_helpers,
    commands_market,
    commands_misc,
    commands_portfolio,
    commands_tui,
)

app.add_typer(commands_auth.auth_app, name="auth", help="Kimlik doğrulama ve hesap yönetimi.")
app.add_typer(commands_auth.account_app, name="account", help="Profil, tercihler ve kredi.")
app.add_typer(commands_market.market_app, name="market", help="BIST piyasa verisi.")
app.add_typer(commands_market.economy_app, name="economy", help="Altın, döviz ve makro ekonomi.")
app.add_typer(
    commands_market.price_app,
    name="price",
    help="Fiyat kısa yolu (fl price THYAO / fl price history ASELS 3mo 5m).",
)
app.add_typer(
    commands_portfolio.portfolio_app,
    name="portfolio",
    help="Favoriler, portföyler ve işlemler.",
)
app.add_typer(
    commands_analysis.analysis_app,
    name="analysis",
    help="Raporlar, simülasyonlar ve eşleştirme.",
)
app.add_typer(commands_export.bots_app, name="bots", help="Bot hesapları.")
app.add_typer(commands_export.export_app, name="export", help="Veri dışa aktarım (yıllık).")
app.add_typer(commands_misc.misc_app, name="misc", help="Halka arz, yasal ve meta bilgiler.")
app.add_typer(commands_misc.config_app, name="config", help="CLI yerel ayarları.")
app.add_typer(
    commands_helpers.helper_app,
    name="helper",
    help="Semantik yardımcı kompozitler (tek niyet = tek komut).",
)
app.add_typer(
    commands_digest.digest_app,
    name="digest",
    help="Piyasa bülteni (fl digest / fl digest --slot morning).",
)
# Duzlestirilmis analiz gruplari (karar 2026-08-14): fl report <ticker> =
# generate, fl simulate <ticker> --days N = run (alt komutlariyla birlikte).
app.add_typer(
    commands_analysis.report_app,
    name="report",
    help="Raporlar (fl report <ticker> = generate).",
)
app.add_typer(
    commands_analysis.simulate_app,
    name="simulate",
    help="Simülasyonlar (fl simulate <ticker> --days N = run).",
)
# ``fl tui`` — isimsiz add_typer: komut ust seviyeye eklenir (K5: sifir arguman).
app.add_typer(commands_tui.tui_app)


@app.command("download")
def _download_command(
    ctx: typer.Context,
    ticker: str = typer.Argument(..., help="Ticker (ör. THYAO)."),
    period: str = typer.Argument(..., help="Periyot (ör. 3mo, 6mo, 1y)."),
    interval: str = typer.Option("1d", "--interval", help="Mum aralığı (ör. 5m, 1h, 1d)."),
    output: str | None = typer.Option(
        None, "--output", help="Hedef CSV dosya yolu (yoksa <TICKER>-<period>.csv)."
    ),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Hisse mum verisini CSV olarak indirir (fiyat geçmişi → CSV)."""
    ctx.obj.apply_flags(json_output, verbose)
    commands_market.download_impl(ctx, ticker, period, interval, output)


# ----------------------------------------------------------------------
# Hata yakalayici + entry point
# ----------------------------------------------------------------------
def _patch_flat_groups(cmd: click.Command) -> None:
    """Duzlestirilmis gruplari (report/simulate/price) ozel gruba cevirir."""
    from .flat import make_flat_group

    for name in ("report", "simulate", "price"):
        group = cmd.commands.get(name)  # type: ignore[attr-defined]
        if group is not None:
            make_flat_group(group)


def _build_command() -> click.Command:
    cmd = typer.main.get_command(app)
    _patch_flat_groups(cmd)
    return cmd


def _report_cli_error(exc: BaseException, code: str, status: int | None) -> None:
    """CLI kaynakli hatalar (PromptRequiredError / CliRuntimeError)."""
    state = _last_state
    json_mode = state is not None and state.effective_json()
    if json_mode:
        payload = {"error": {"code": code, "status": status, "detail": str(exc)}}
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
    else:
        print(f"Hata: {exc}", file=sys.stderr)


def _run(args: list[str] | None, prog_name: str = "florence") -> int:
    global _last_state
    _last_state = None
    try:
        _build_command().main(args=args or [], prog_name=prog_name, standalone_mode=False)
    except click_exceptions.Exit as exc:
        return exc.exit_code
    except click_exceptions.ClickException as exc:
        exc.show()
        return exc.exit_code
    except KeyboardInterrupt:
        return 130
    except PromptRequiredError as exc:
        _report_cli_error(exc, code="prompt_required", status=None)
        return 2
    except CliRuntimeError as exc:
        _report_cli_error(exc, code=exc.code, status=exc.status)
        return 1
    except FlorenceError as exc:
        state = _last_state
        emit_error(exc, json_mode=state is not None and state.effective_json())
        return 1
    return 0


def main(args: list[str] | None = None) -> Any:
    """Entry point (``florence`` ve ``fl`` ayni fonksiyon).

    ``args=None`` iken ``sys.argv[1:]`` kullanilir ve prog_name komut
    adindan (``fl`` / ``florence``) alinir.
    """
    prog_name = "florence"
    if args is None:
        args = sys.argv[1:]
        if sys.argv and sys.argv[0]:
            prog_name = Path(sys.argv[0]).name or "florence"
    raise SystemExit(_run(args, prog_name=prog_name))
