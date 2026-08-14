"""Kalici, sifreli token store (``FileTokenStore``).

Keyring'in calismadigi ortamlar (sunucu, CI, container — dbus/SecretService
yok) icin kalici fallback. Tasarim karari T3.2b (2026-08-14, kullanici onayi):

- Dosya: ``~/.config/florence/tokens.json`` (``FLORENCE_TOKEN_STORE_PATH``
  ortam degiskeni ile override edilebilir), chmod 600.
- Icerik **Fernet (symmetric) ile sifrelenir**: ``{"v": 1, "data": <fernet>}``.
  Access/refresh token, username ve bot sifreleri tek sifreli blokta durur.
- Anahtar makineden turetilir: ``/etc/machine-id`` (fallback:
  ``/var/lib/dbus/machine-id``) + kullanici home + sabit tuz -> PBKDF2.
- HASH YOK (kullanici karari): degerler yalnizca Fernet ile korunur,
  ayrica hash'lenmez (yeniden gonderilecek kimlik bilgileri icin hash
  kullanilamaz zaten).
- Anahtar yoksa/bozuksa GUVENLI hata (``AuthError``) — sessiz bellek
  fallback'i YOKTUR: CLI kaliciligi asla sessizce kaybetmez.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .errors import AuthError

__all__ = ["FileTokenStore", "derive_file_key"]

#: Dosya semasi surumu.
_SCHEMA_VERSION = 1

#: PBKDF2 iterasyon sayisi (makul guvenlik/performans dengesi).
_KEY_ITERATIONS = 200_000

#: Sabit tuz (anahtar turetiminde; dosya icerigi degildir).
_SALT = b"florence-sdk-file-token-store-v1"

_MACHINE_ID_SOURCES = ("/etc/machine-id", "/var/lib/dbus/machine-id")


def _default_store_path() -> Path:
    """Varsayilan token dosya yolu (env override destekli)."""
    env_path = os.environ.get("FLORENCE_TOKEN_STORE_PATH")
    if env_path:
        return Path(env_path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "florence" / "tokens.json"


def _machine_id() -> str | None:
    """Makine kimligi; yoksa ``None`` (guvenli hata icin)."""
    for source in _MACHINE_ID_SOURCES:
        try:
            value = Path(source).read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            continue
    return None


def derive_file_key(key_material: str | None = None) -> bytes:
    """Fernet anahtari turetir (makine kimligi + home + tuz -> PBKDF2).

    ``key_material`` test/dev icin acik anahtar maddesi kabul eder;
    verilmezse makine kimligi kullanilir. Makine kimligi yoksa
    ``AuthError`` firlatilir (sessiz memory fallback YOK).
    """
    material = key_material or _machine_id()
    if not material:
        raise AuthError(
            0,
            "no_machine_key",
            "Makine anahtari turetilmedi (/etc/machine-id yok). FileTokenStore "
            "icin makine kimligi gerekir.",
        )
    home = str(Path.home()).encode("utf-8")
    key = hashlib.pbkdf2_hmac(
        "sha256", material.encode("utf-8") + home, _SALT, _KEY_ITERATIONS, dklen=32
    )
    return base64.urlsafe_b64encode(key)


class FileTokenStore:
    """Fernet sifreli, dosya tabanli token store (T3.2b)."""

    backend = "file"

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        key_material: str | None = None,
    ) -> None:
        from cryptography.fernet import Fernet

        self._path = Path(path) if path is not None else _default_store_path()
        self._fernet = Fernet(derive_file_key(key_material))
        self._cache: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Dahili: sifreli dosya okuma/yazma
    # ------------------------------------------------------------------
    def _load(self) -> dict[str, Any]:
        if self._cache is not None:
            return self._cache
        if not self._path.exists():
            self._cache = {}
            return self._cache
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            payload = self._fernet.decrypt(raw["data"].encode("utf-8"))
            self._cache = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise AuthError(
                0,
                "token_store_corrupt",
                f"Token dosyasi okunamadi/sifresi cozulemedi: {self._path}. "
                "Dosyayi silip tekrar login olun.",
            ) from exc
        return self._cache

    def _save(self) -> None:
        payload = json.dumps(self._load(), ensure_ascii=False).encode("utf-8")
        token = self._fernet.encrypt(payload).decode("utf-8")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomik yazim: once tmp, sonra replace; her ikisinde de chmod 600.
        tmp = self._path.with_name(f"{self._path.name}.tmp")
        tmp.write_text(
            json.dumps({"v": _SCHEMA_VERSION, "data": token}), encoding="utf-8"
        )
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._path)
        try:
            os.chmod(self._path, 0o600)
        except OSError:  # pragma: no cover - egzotik dosya sistemleri
            pass

    # ------------------------------------------------------------------
    # TokenStore protokolu
    # ------------------------------------------------------------------
    def get_access_token(self) -> str | None:
        return self._load().get("access_token")

    def get_refresh_token(self) -> str | None:
        return self._load().get("refresh_token")

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        data = self._load()
        data["access_token"] = access_token
        data["refresh_token"] = refresh_token
        self._save()

    def clear(self) -> None:
        data = self._load()
        data.pop("access_token", None)
        data.pop("refresh_token", None)
        data.pop("username", None)
        self._save()

    # ------------------------------------------------------------------
    # T3.2a: username (opsiyonel protokol metotlari)
    # ------------------------------------------------------------------
    def get_username(self) -> str | None:
        return self._load().get("username")

    def set_username(self, username: str) -> None:
        data = self._load()
        data["username"] = username
        self._save()

    def clear_username(self) -> None:
        data = self._load()
        data.pop("username", None)
        self._save()

    # ------------------------------------------------------------------
    # Bot sifreleri
    # ------------------------------------------------------------------
    def get_password(self, username: str) -> str | None:
        return self._load().get(f"bot_password:{username}")

    def set_password(self, username: str, password: str) -> None:
        data = self._load()
        data[f"bot_password:{username}"] = password
        self._save()

    def delete_password(self, username: str) -> None:
        data = self._load()
        data.pop(f"bot_password:{username}", None)
        self._save()
