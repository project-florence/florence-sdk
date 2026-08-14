"""``fl bots`` (3) ve ``fl export`` (5) komutlari.

Bot akisi (tasarim 2.7): ``create`` (tek seferlik sifre ``AuthManager.create_bot``
ile otomatik store'a — keyring/FileTokenStore — yazilir ve ekrana BASILMAZ;
``--show-password`` ile bir kez gosterilir) -> ``list`` -> ``delete`` (yikici:
onay promptu; store'daki bot sifresi de temizlenir).

Export akisi (tasarim 2.8, poll tabanli): ``create`` (202, idempotent) ->
``status`` -> ``download`` (public token). ``fl export fetch`` belgelenmis
kompozittir (create -> wait -> download) — tek niyet "bu yilin verisini indir".
Poll progress'i stderr'e basilir (stdout = veri, stderr = progress kurali).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import typer

from .context import CliState
from .interactive import CliRuntimeError, confirm_or_abort
from .options import json_opt, verbose_opt
from .output import emit_json, render_data
from .util import extract_rows

__all__ = ["bots_app", "export_app"]

bots_app = typer.Typer(help="Bot hesapları.", no_args_is_help=True)
export_app = typer.Typer(help="Veri dışa aktarım (yıllık).", no_args_is_help=True)

_EXPORT_FORMATS = ("csv", "json")

#: Poll isleminde terminal durumlar (SDK ``export_res`` ile birebir).
_TERMINAL_STATUSES = frozenset({"ready", "sent", "error"})

#: --json'da tek seferlik sifre maskesi (--show-password ile acilir).
_PASSWORD_MASK = "***"


def _state(ctx: typer.Context) -> CliState:
    return ctx.obj


def _emit(state: CliState, data: Any, human: str | None = None) -> None:
    """Ortak cikti: --json'da birebir, insan modunda mesaj/tablo."""
    if state.effective_json():
        emit_json(data)
    elif human is not None:
        print(human)
    else:
        render_data(data)


def _mask_bot_password(data: Any, show_password: bool) -> Any:
    """Bot create yanitinda tek seferlik sifreyi maskeler (varsayilan)."""
    if show_password or not isinstance(data, dict) or "password" not in data:
        return data
    payload = dict(data)
    payload["password"] = _PASSWORD_MASK
    return payload


# ----------------------------------------------------------------------
# fl bots — 3 komut
# ----------------------------------------------------------------------
@bots_app.command("create")
def bots_create(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="Bot kullanıcı adı (max 5 bot)."),
    password: str | None = typer.Option(
        None, "--password", help="Bot şifresi (yoksa backend üretir)."
    ),
    show_password: bool = typer.Option(
        False, "--show-password", help="Tek seferlik şifreyi ekrana bas."
    ),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Bot hesabı oluşturur; tek seferlik şifre güvenli depoya yazılır."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    data = state.client().auth.create_bot(username, password)
    if state.effective_json():
        emit_json(_mask_bot_password(data, show_password))
        return
    bot_id = data.get("id") if isinstance(data, dict) else None
    print(f"Bot oluşturuldu: {username} (id {bot_id}) — şifre güvenli depoya kaydedildi")
    if show_password and isinstance(data, dict) and data.get("password"):
        print(f"Şifre (tek seferlik): {data['password']}")


@bots_app.command("list")
def bots_list(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Kendi bot hesaplarını listeler (JWT)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().bots.list())


@bots_app.command("delete")
def bots_delete(
    ctx: typer.Context,
    bot_id: int = typer.Argument(..., help="Bot kimliği."),
    yes: bool = typer.Option(False, "--yes", help="Onay istemeden sil (zorunlu: --json)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Botu siler (yıkıcı — onay gerekir; store'daki şifre de temizlenir)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    confirm_or_abort(state, f"Bot {bot_id} kalıcı silinecek, onaylıyor musunuz?", yes)
    # Best-effort: silinecek botun kullanici adini bul (store sifre temizligi icin).
    username: str | None = None
    try:
        for bot in extract_rows(state.client().bots.list()):
            if str(bot.get("id")) == str(bot_id):
                username = bot.get("username")
                break
    except Exception:
        username = None
    result = state.client().bots.delete(bot_id)
    if username:
        state.store().delete_password(username)
    _emit(state, result, f"Bot silindi: {bot_id}")


# ----------------------------------------------------------------------
# fl export — 5 komut
# ----------------------------------------------------------------------
@export_app.command("create")
def export_create(
    ctx: typer.Context,
    year: int = typer.Argument(..., help="Yıl (ör. 2025)."),
    format: str = typer.Option("csv", "--format", help="csv|json."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Export siparişi verir (idempotent; aktif kayıt varsa mevcut id döner)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if format not in _EXPORT_FORMATS:
        raise typer.UsageError(f"--format csv veya json olmalı (gelen: {format})")
    _emit(state, state.client().export.create_export(year, format))


@export_app.command("status")
def export_status(
    ctx: typer.Context,
    export_id: int = typer.Argument(..., help="Export kimliği."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Tek export kaydını gösterir."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().export.get_export(export_id))


@export_app.command("list")
def export_list(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Export geçmişini listeler."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().export.list_exports())


def _poll_export(
    state: CliState, export_id: int, poll_interval: float, timeout: float
) -> dict[str, Any]:
    """Terminal duruma (ready/sent/error) ulasana kadar poll eder.

    Her poll'daki durumu stderr'e basar (stdout = veri kurali); ``timeout``
    asilirsa ``CliRuntimeError`` (code=``timeout``) firlatir. SDK
    ``wait_export`` ile ayni terminal durum setini kullanir.
    """
    deadline = time.monotonic() + timeout
    while True:
        record = state.client().export.get_export(export_id)
        status = record.get("status")
        if status in _TERMINAL_STATUSES:
            return record
        print(f"Bekleniyor… durum: {status}", file=sys.stderr)
        if time.monotonic() >= deadline:
            raise CliRuntimeError(
                f"Export {export_id} {timeout:.0f}s içinde hazır olmadı (son durum: {status})",
                code="timeout",
            )
        time.sleep(max(0.0, poll_interval))


def _default_export_path(export_id: int, record: dict[str, Any]) -> str:
    """``--output`` verilmezse: cwd'ye ``export-<id>.<fmt>``."""
    fmt = record.get("format") if isinstance(record, dict) else None
    fmt = fmt if fmt in _EXPORT_FORMATS else "csv"
    return f"export-{export_id}.{fmt}"


def _export_error(export_id: int, record: dict[str, Any]) -> CliRuntimeError:
    detail = record.get("error") or "bilinmeyen hata"
    return CliRuntimeError(f"Export {export_id} hata durumunda: {detail}", code="export_error")


def _emit_download_result(state: CliState, export_id: int, status: str, path: str) -> None:
    """Indirme sonucu: insan -> dosya yolu; --json -> {export_id, status, path, bytes}."""
    dest = Path(path)
    if state.effective_json():
        emit_json(
            {
                "export_id": export_id,
                "status": status,
                "path": str(dest),
                "bytes": dest.stat().st_size if dest.exists() else None,
            }
        )
    else:
        print(f"İndirildi: {dest}")


@export_app.command("download")
def export_download(
    ctx: typer.Context,
    export_id: int = typer.Argument(..., help="Export kimliği."),
    output: str | None = typer.Option(
        None, "--output", help="Hedef dosya yolu (yoksa export-<id>.<fmt>)."
    ),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Hazır olana dek bekle (varsayılan açık)."
    ),
    poll_interval: float = typer.Option(3.0, "--poll-interval", help="Poll aralığı (sn)."),
    timeout: float = typer.Option(300.0, "--timeout", help="Bekleme sınırı (sn)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Export'u indirir; --wait ile hazır olana dek bekler (progress stderr)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if wait:
        record = _poll_export(state, export_id, poll_interval, timeout)
    else:
        record = state.client().export.get_export(export_id)
    status = record.get("status")
    if status == "error":
        raise _export_error(export_id, record)
    if status not in ("ready", "sent") or not record.get("download_url"):
        if state.effective_json():
            emit_json({"export_id": export_id, "status": status, "path": None, "bytes": None})
        else:
            print(
                f"Export {export_id} henüz hazır değil (durum: {status}); "
                "--wait ile bekleyin veya daha sonra tekrar deneyin.",
                file=sys.stderr,
            )
        return
    dest = output or _default_export_path(export_id, record)
    path = state.client().export.download(record["download_url"], dest)
    _emit_download_result(state, export_id, status, path)


@export_app.command("fetch")
def export_fetch(
    ctx: typer.Context,
    year: int = typer.Argument(..., help="Yıl (ör. 2025)."),
    format: str = typer.Option("csv", "--format", help="csv|json."),
    output: str | None = typer.Option(None, "--output", help="Hedef dosya yolu."),
    poll_interval: float = typer.Option(3.0, "--poll-interval", help="Poll aralığı (sn)."),
    timeout: float = typer.Option(300.0, "--timeout", help="Bekleme sınırı (sn)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Kompozit: create → bekle → indir (tek niyet: yılın verisini al)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if format not in _EXPORT_FORMATS:
        raise typer.UsageError(f"--format csv veya json olmalı (gelen: {format})")
    created = state.client().export.create_export(year, format)
    export_id = None
    if isinstance(created, dict):
        export_id = created.get("export_id") or created.get("id")
    if export_id is None:
        raise CliRuntimeError(
            "Export oluşturma yanıtında export_id bulunamadı", code="export_error"
        )
    record = _poll_export(state, export_id, poll_interval, timeout)
    status = record.get("status")
    if status == "error":
        raise _export_error(export_id, record)
    if not record.get("download_url"):
        raise CliRuntimeError(
            f"Export {export_id} indirilebilir değil (durum: {status})", code="export_error"
        )
    dest = output or _default_export_path(export_id, record)
    path = state.client().export.download(record["download_url"], dest)
    _emit_download_result(state, export_id, status, path)
