"""``fl auth`` (10 komut) ve ``fl account`` (6 komut) gruplari.

Auth komutlari SDK ``AuthManager`` (durumlu) + ``AuthResource`` (durumsuz)
uzerine ince cagiricidir. Kalici oturum T3.2a-e: login -> store'a token +
username, config'e last_username/last_type; logout -> store temizligi.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import typer

from ..errors import AuthError
from .context import CliState
from .interactive import secret_prompt
from .options import json_opt, verbose_opt
from .output import emit_json, render_kv

__all__ = ["account_app", "auth_app"]

auth_app = typer.Typer(help="Kimlik doğrulama ve hesap yönetimi.", no_args_is_help=True)
account_app = typer.Typer(help="Profil, tercihler ve kredi.", no_args_is_help=True)

#: ``fl account preferences`` (okuma) + ``fl account preferences set`` (yazma)
preferences_app = typer.Typer(
    help="Kullanıcı tercihleri.", invoke_without_command=True, no_args_is_help=False
)

_MIN_PASSWORD_LEN = 10

_MUTABLE_HINT = "Mevcut şifre"


def _state(ctx: typer.Context) -> CliState:
    state: CliState = ctx.obj
    return state


def _message_or_emit(state: CliState, data: Any, fallback: str) -> None:
    """API yanitini insan modunda mesaj olarak, --json'da birebir basar."""
    if state.effective_json():
        emit_json(data)
        return
    if isinstance(data, dict) and data.get("message"):
        print(str(data["message"]))
    else:
        print(fallback)


# ----------------------------------------------------------------------
# fl auth — 10 komut
# ----------------------------------------------------------------------
@auth_app.command("login")
def auth_login(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="Kullanıcı adı."),
    bot: bool = typer.Option(False, "--bot", help="Bot hesabı olarak giriş yap."),
    password: str | None = typer.Option(
        None,
        "--password",
        help="Şifreyi bayrakla ver (komut geçmişi riski; yoksa gizli prompt).",
    ),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Giriş yapar; oturum kalıcıdır (keyring/şifreli dosya)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    client = state.client()
    if bot:
        try:
            pair = client.auth.login_as_bot(username)
        except AuthError as exc:
            if exc.code == "no_bot_password":
                hint = (
                    f"Bot '{username}' şifresi güvenli depoda yok; "
                    f"önce 'fl bots create {username}' çalıştırın."
                )
                if state.effective_json():
                    payload = {
                        "error": {"code": exc.code, "status": exc.status_code, "detail": hint}
                    }
                    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
                else:
                    print(f"Hata: {hint}", file=sys.stderr)
                raise typer.Exit(1) from None
            raise
    else:
        pw = password if password is not None else secret_prompt(f"{username} şifresi")
        pair = client.auth.login(username, pw)
    if state.config is not None:
        state.config.set_last_login(username, "bot" if bot else "user")
    if state.effective_json():
        emit_json(pair.model_dump() if hasattr(pair, "model_dump") else pair)
    else:
        print(f"Giriş yapıldı: {username} ({'bot' if bot else 'user'})")


@auth_app.command("logout")
def auth_logout(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Çıkış yapar; token'ları ve oturum kimliğini temizler."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    result = state.client().auth.logout()
    _message_or_emit(state, result, "Çıkış yapıldı")


@auth_app.command("status")
def auth_status(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Oturum durumunu gösterir (yerel; ağ gerektirmez)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    store = state.store()
    client = state.client()
    env_override = bool(__import__("os").environ.get("FLORENCE_TOKEN"))
    username = store.get_username() or (state.config.last_username if state.config else None)
    user_type = (state.config.last_type if state.config else None) or "user"
    authenticated = client.auth.is_authenticated()
    data = {
        "authenticated": authenticated,
        "username": username,
        "user_type": user_type,
        "store": getattr(store, "backend", "memory"),
        "env_override": env_override,
    }
    if state.effective_json():
        emit_json(data)
        return
    human = {
        "Durum": "Giriş yapıldı" if authenticated else "Giriş yapılmadı",
        "Kullanıcı": username or "—",
        "Tip": "bot" if user_type == "bot" else "kullanıcı",
        "Depo": data["store"],
        "Env override": "evet" if env_override else "hayır",
    }
    render_kv(human)


@auth_app.command("register")
def auth_register(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="Yeni kullanıcı adı."),
    email: str = typer.Argument(..., help="E-posta adresi."),
    password: str | None = typer.Option(
        None, "--password", help="Şifre (yoksa gizli prompt ×2)."
    ),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Yeni hesap kaydı (şifre min 10 karakter)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if password is None:
        first = secret_prompt("Yeni şifre (min 10 karakter)")
        second = secret_prompt("Yeni şifre (tekrar)")
        if first != second:
            raise typer.UsageError("Şifreler eşleşmiyor")
        password = first
    if len(password) < _MIN_PASSWORD_LEN:
        raise typer.UsageError("Şifre en az 10 karakter olmalı")
    result = state.client().auth.register(username, email, password)
    _message_or_emit(state, result, "Kayıt tamamlandı; e-posta doğrulaması gönderildi")


@auth_app.command("verify")
def auth_verify(
    ctx: typer.Context,
    token: str = typer.Argument(..., help="Doğrulama token'ı."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """E-posta doğrulama token'ını işler."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    result = state.client().auth.verify_email(token)
    _message_or_emit(state, result, "E-posta doğrulandı")


@auth_app.command("resend")
def auth_resend(
    ctx: typer.Context,
    username_or_email: str = typer.Argument(..., help="Kullanıcı adı veya e-posta."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Doğrulama e-postasını yeniden gönderir."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    result = state.client().auth.resend_verification(username_or_email)
    _message_or_emit(state, result, "Doğrulama e-postası gönderildi")


@auth_app.command("change-password")
def auth_change_password(
    ctx: typer.Context,
    password: str | None = typer.Option(None, "--password", help="Mevcut şifre."),
    new_password: str | None = typer.Option(None, "--new-password", help="Yeni şifre."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Mevcut şifreyi değiştirir (tüm refresh token'lar iptal olur)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    current = password if password is not None else secret_prompt(_MUTABLE_HINT)
    if new_password is None:
        first = secret_prompt("Yeni şifre (min 10 karakter)")
        second = secret_prompt("Yeni şifre (tekrar)")
        if first != second:
            raise typer.UsageError("Şifreler eşleşmiyor")
        new_password = first
    if len(new_password) < _MIN_PASSWORD_LEN:
        raise typer.UsageError("Şifre en az 10 karakter olmalı")
    result = state.client().auth_res.change_password(current, new_password)
    _message_or_emit(state, result, "Şifre değiştirildi")


@auth_app.command("change-email")
def auth_change_email(
    ctx: typer.Context,
    new_email: str = typer.Argument(..., help="Yeni e-posta adresi."),
    password: str | None = typer.Option(None, "--password", help="Mevcut şifre."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """E-posta adresini değiştirir."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    current = password if password is not None else secret_prompt(_MUTABLE_HINT)
    result = state.client().auth_res.change_email(new_email, current)
    _message_or_emit(state, result, "E-posta değiştirildi")


@auth_app.command("change-username")
def auth_change_username(
    ctx: typer.Context,
    new_username: str = typer.Argument(..., help="Yeni kullanıcı adı."),
    password: str | None = typer.Option(None, "--password", help="Mevcut şifre."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Kullanıcı adını değiştirir."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    current = password if password is not None else secret_prompt(_MUTABLE_HINT)
    result = state.client().auth_res.change_username(new_username, current)
    _message_or_emit(state, result, "Kullanıcı adı değiştirildi")


@auth_app.command("delete")
def auth_delete(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", help="Onay istemeden sil (zorunlu: --json)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Hesabı kalıcı olarak siler (yıkıcı — onay gerekir)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    from .interactive import confirm_or_abort

    confirm_or_abort(state, "Hesabınız kalıcı silinecek, onaylıyor musunuz?", yes)
    result = state.client().auth_res.delete()
    _message_or_emit(state, result, "Hesap silindi")


# ----------------------------------------------------------------------
# fl account — 6 komut
# ----------------------------------------------------------------------
@account_app.command("credits")
def account_credits(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Kredi bakiyesini gösterir."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    data = state.client().user.credits()
    if state.effective_json():
        emit_json(data)
        return
    from .output import tr_number

    credits = data.get("credits") if isinstance(data, dict) else data
    if isinstance(credits, (int, float)):
        print(f"Kredi: {tr_number(float(credits))}")
    else:
        print(f"Kredi: {credits}")


@account_app.command("profile")
def account_profile(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Profil ve kredi bilgisini gösterir."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    data = state.client().user.profile()
    if state.effective_json():
        emit_json(data)
        return
    from .output import render_kv

    render_kv(data if isinstance(data, dict) else {"profil": data})


@account_app.command("avatar")
def account_avatar(
    ctx: typer.Context,
    avatar_id: str = typer.Argument(..., help="Avatar kimliği (ör. 3)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Profil avatarını günceller."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    result = state.client().user.update_avatar(avatar_id)
    _message_or_emit(state, result, f"Avatar güncellendi: {avatar_id}")


@preferences_app.callback()
def preferences_get_cb(
    ctx: typer.Context,
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Kullanıcı tercihlerini gösterir (okuma)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    if ctx.invoked_subcommand is not None:
        return
    data = state.client().user.get_preferences()
    if state.effective_json():
        emit_json(data)
        return
    if isinstance(data, dict) and data:
        for key, value in data.items():
            print(f"{key}: {value}")
    else:
        print("Kayıt yok")


@preferences_app.command("set")
def preferences_set_cmd(
    ctx: typer.Context,
    pairs: list[str] = typer.Argument(..., help="key=value çiftleri (1+)."),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Tercihleri günceller (PUT mevcut prefs ile birleştirir)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    prefs: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise typer.UsageError(f"'{pair}' geçersiz; key=value biçimi beklenir")
        key, value = pair.split("=", 1)
        prefs[key.strip()] = value.strip()
    result = state.client().user.update_preferences(prefs)
    _message_or_emit(state, result, "Tercihler güncellendi")


account_app.add_typer(preferences_app, name="preferences")


@account_app.command("export")
def account_export(
    ctx: typer.Context,
    output: str | None = typer.Option(
        None, "--output", help="JSON dump'ını dosyaya yaz (yoksa stdout)."
    ),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Hesabınızın tüm verisinin JSON dump'ını alır."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    data = state.client().user.export_data()
    if output:
        from pathlib import Path

        dest = Path(output)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        if state.effective_json():
            emit_json({"path": str(dest), "bytes": dest.stat().st_size})
        else:
            print(f"Veri yazıldı: {dest}")
        return
    if state.effective_json():
        emit_json(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
