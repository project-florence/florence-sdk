"""``fl misc`` (14) ve ``fl config`` (2) komutlari.

Misc grubu SDK ``MiscResource``'un ince cagiricisidir (tasarim 2.9):
``ipo`` alt varligi (upcoming/draft/active/get), legal/legal-all/about,
version, contact, contributors, maintenance, health ve ``announcement``
alt varligi (list/get — JWT; yazma uclari KAPSAM DISI).

Config grubu (tasarim 2.10) SDK endpoint'i DEGILDIR: ``~/.config/florence/
config.toml`` uzerinde calisir (allowlist: ``api_url``, ``default_output``).
``last_username``/``last_type`` yalnizca CLI tarafindan otomatik yazilir.
NOT: TUI anahtarlari (``tui_refresh_seconds``, ``tui_default_period``)
ileride eklenecek — simdilik allowlist'e dahil degil (``config_cli``).
"""

from __future__ import annotations

import os
from typing import Any

import typer

from .context import CliState, build_store
from .interactive import CliRuntimeError
from .options import json_opt, verbose_opt
from .output import emit_json, render_data, render_kv

__all__ = ["config_app", "misc_app"]

misc_app = typer.Typer(help="Halka arz, yasal ve meta bilgiler.", no_args_is_help=True)
ipo_app = typer.Typer(help="Halka arzlar.", no_args_is_help=True)
announcement_app = typer.Typer(help="Duyurular (JWT).", no_args_is_help=True)
config_app = typer.Typer(help="CLI yerel ayarları.", no_args_is_help=True)

_LEGAL_POLICIES = ("terms", "privacy_policy", "cookie_policy", "disclaimer")
_LANGS = ("tr", "en")

#: Metin agirlikli yanitlarin insan modunda dogrudan basilacagi anahtarlar.
_TEXT_KEYS = ("content", "about", "contact", "text", "message", "version")


def _state(ctx: typer.Context) -> CliState:
    return ctx.obj


def _emit(state: CliState, data: Any) -> None:
    if state.effective_json():
        emit_json(data)
    else:
        render_data(data)


def _emit_text(state: CliState, data: Any) -> None:
    """Metin agirlikli yanitlar: --json birebir; insan modunda duz metin."""
    if state.effective_json():
        emit_json(data)
        return
    if isinstance(data, dict):
        for key in _TEXT_KEYS:
            value = data.get(key)
            if isinstance(value, str):
                print(value)
                return
    render_data(data)


def _validate_lang(lang: str) -> None:
    if lang not in _LANGS:
        raise typer.UsageError(f"--lang tr veya en olmalı (gelen: {lang})")


# ----------------------------------------------------------------------
# fl misc ipo — 4 komut
# ----------------------------------------------------------------------
@ipo_app.command("upcoming")
def misc_ipo_upcoming(
    ctx: typer.Context,
    after: str | None = typer.Option(None, "--after", help="ISO tarih filtresi."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Yaklaşan halka arzlar (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().misc.ipos_upcoming(after=after))


@ipo_app.command("draft")
def misc_ipo_draft(
    ctx: typer.Context,
    after: str | None = typer.Option(None, "--after", help="ISO tarih filtresi."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Taslak halka arzlar (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().misc.ipos_draft(after=after))


@ipo_app.command("active")
def misc_ipo_active(
    ctx: typer.Context,
    after: str | None = typer.Option(None, "--after", help="ISO tarih filtresi."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Aktif halka arzlar (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().misc.ipos_active(after=after))


@ipo_app.command("get")
def misc_ipo_get(
    ctx: typer.Context,
    slug: str = typer.Argument(..., help="Halka arz slug'ı (yoksa 404)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Tek halka arz detayı (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().misc.ipo_detail(slug))


misc_app.add_typer(ipo_app, name="ipo")


# ----------------------------------------------------------------------
# fl misc — legal / statik / meta (10 komut)
# ----------------------------------------------------------------------
@misc_app.command("legal")
def misc_legal(
    ctx: typer.Context,
    policy: str = typer.Argument(..., help="terms|privacy_policy|cookie_policy|disclaimer."),
    lang: str = typer.Option("tr", "--lang", help="tr|en."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Tek politika metnini gösterir (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if policy not in _LEGAL_POLICIES:
        allowed = "|".join(_LEGAL_POLICIES)
        raise typer.UsageError(f"Geçersiz policy: '{policy}' (izin verilenler: {allowed})")
    _validate_lang(lang)
    _emit_text(state, state.client().misc.legal(policy, lang))


@misc_app.command("legal-all")
def misc_legal_all(
    ctx: typer.Context,
    lang: str = typer.Option("tr", "--lang", help="tr|en."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Tüm politikaları gösterir (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _validate_lang(lang)
    _emit(state, state.client().misc.legal_all(lang))


@misc_app.command("about")
def misc_about(
    ctx: typer.Context,
    lang: str = typer.Option("tr", "--lang", help="tr|en."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Platform hakkındaki metni gösterir (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _validate_lang(lang)
    _emit_text(state, state.client().misc.about(lang))


@misc_app.command("version")
def misc_version(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """API sürümünü gösterir (ağ ister; yerel sürüm: fl --version)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit_text(state, state.client().misc.version())


@misc_app.command("contact")
def misc_contact(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """İletişim bilgilerini gösterir (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit_text(state, state.client().misc.contact())


@misc_app.command("contributors")
def misc_contributors(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Katkıda bulunanları listeler (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().misc.contributors())


@misc_app.command("maintenance")
def misc_maintenance(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Devre dışı özellik listesini gösterir (public)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().misc.maintenance())


@misc_app.command("health")
def misc_health(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Sağlık kontrolü (public; kök seviye endpoint)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    data = state.client().misc.health()
    if state.effective_json():
        emit_json(data)
        return
    if isinstance(data, dict) and data.get("status") == "ok":
        print("Durum: ok")
    else:
        render_data(data)


# ----------------------------------------------------------------------
# fl misc announcement — 2 komut (JWT; yazma uclari kapsam disi)
# ----------------------------------------------------------------------
@announcement_app.command("list")
def misc_announcement_list(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Son 7 günün duyuruları (JWT)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().misc.announcements())


@announcement_app.command("get")
def misc_announcement_get(
    ctx: typer.Context,
    announcement_id: int = typer.Argument(..., help="Duyuru kimliği."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Tek duyuru (JWT)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    _emit(state, state.client().misc.announcement(announcement_id))


misc_app.add_typer(announcement_app, name="announcement")


# ----------------------------------------------------------------------
# fl config — 2 komut (SDK endpoint'i DEGIL; CLI yerel ayarlari)
# ----------------------------------------------------------------------
@config_app.command("show")
def config_show(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Etkin ayarları kaynağıyla gösterir (config + env + varsayılan)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    from ..config import DEFAULT_API_URL

    config = state.config
    env_api = os.environ.get("FLORENCE_API_URL")
    api_value = env_api or (config.api_url if config else None) or DEFAULT_API_URL
    api_source = "env" if env_api else ("config" if config and config.api_url else "default")
    do_value = config.default_output if config else "table"
    do_source = "config" if config and config.get("default_output") else "default"
    data = {
        "api_url": {"value": api_value, "source": api_source},
        "default_output": {"value": do_value, "source": do_source},
        "last_username": config.last_username if config else None,
        "store": build_store().backend,
    }
    if state.effective_json():
        emit_json(data)
        return
    render_kv(
        {
            "API URL": f"{api_value} ({api_source})",
            "Varsayılan çıktı": f"{do_value} ({do_source})",
            "Son kullanıcı": data["last_username"] or "—",
            "Token deposu": data["store"],
        }
    )


@config_app.command("set")
def config_set(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="api_url|default_output."),
    value: str = typer.Argument(..., help="Değer."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Config anahtarı ayarlar (allowlist: api_url, default_output)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if state.config is None:
        raise CliRuntimeError("Config kullanılamıyor", code="config_error")
    state.config.set(key, value)  # allowlist disi anahtar -> exit 2
    if state.effective_json():
        emit_json({"key": key, "value": value, "path": str(state.config.path)})
    else:
        print(f"config güncellendi: {key} = {value}")
