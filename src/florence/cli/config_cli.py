"""CLI yerel ayarlari: ``~/.config/florence/config.toml`` (T3.2c).

Bu modul SDK ``config.py`` ile KARISMAZ: SDK config'i transport icindir
(env + timeout), bu modul CLI tercihleri icindir (api_url override,
default_output, last_username, last_type).

Kurallar:
- ``FLORENCE_API_URL`` env > config ``api_url`` > SDK default.
- ``--json`` bayragi > config ``default_output`` > varsayilan ``table``.
- ``last_username`` / ``last_type`` yalnizca CLI tarafindan otomatik yazilir;
  ``fl config set`` allowlist disi anahtarlari reddeder (exit 2).
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

import typer

__all__ = [
    "ALLOWED_KEYS",
    "CliConfig",
    "default_config_path",
]

#: ``fl config set`` ile degistirilebilen anahtarlar.
ALLOWED_KEYS = frozenset(
    {
        "api_url",
        "default_output",
        # TUI ayarlari (docs/tui-design.md §6.1) — PART 1.
        "tui_refresh_seconds",
        "tui_default_period",
        # TUI ayarlari (plan v2, P6) — detay grafik tipi (line|candle).
        "tui_default_chart",
    }
)

#: CLI tarafindan otomatik yazilan anahtarlar (kullanici set edemez).
AUTO_KEYS = frozenset({"last_username", "last_type"})

DEFAULT_OUTPUTS = frozenset({"table", "json"})

#: TUI detay grafigi period'lari (tui-default-period: 1mo|3mo|6mo|1y).
TUI_DEFAULT_PERIODS = frozenset({"1mo", "3mo", "6mo", "1y"})

#: Detay grafigi tipleri (tui_default_chart: line|candle — P6).
TUI_DEFAULT_CHARTS = frozenset({"line", "candle"})

#: tui_refresh_seconds kabul araligi (disi clamp — tasarim §6.1).
TUI_REFRESH_MIN = 10
TUI_REFRESH_MAX = 600


def default_config_path() -> Path:
    """Varsayilan config yolu: ``$XDG_CONFIG_HOME/florence/config.toml``."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "florence" / "config.toml"


def _toml_quote(value: str) -> str:
    """TOML string guvenli alinti (cift tirnak + kacis)."""
    return json.dumps(str(value))


class CliConfig:
    """CLI config.toml okuyucu/yazici (``[cli]`` tablosu)."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path is not None else default_config_path()
        self._data: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Okuma
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = tomllib.loads(self.path.read_text(encoding="utf-8"))
            self._data = dict(raw.get("cli", {}))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            print(f"Uyarı: config okunamadı ({self.path}): {exc}", file=sys.stderr)

    @property
    def api_url(self) -> str | None:
        return self._data.get("api_url")

    @property
    def default_output(self) -> str:
        value = self._data.get("default_output", "table")
        return value if value in DEFAULT_OUTPUTS else "table"

    @property
    def last_username(self) -> str | None:
        return self._data.get("last_username")

    @property
    def last_type(self) -> str:
        value = self._data.get("last_type", "user")
        return value if value in ("user", "bot") else "user"

    def get(self, key: str) -> Any | None:
        return self._data.get(key)

    # ------------------------------------------------------------------
    # Yazma
    # ------------------------------------------------------------------
    def set(self, key: str, value: str) -> None:
        """Allowlist kontrolu ile config anahtari set eder (exit 2 reddi)."""
        if key not in ALLOWED_KEYS:
            allowed = ", ".join(sorted(ALLOWED_KEYS))
            raise typer.UsageError(
                f"Geçersiz config anahtarı: '{key}' (izin verilenler: {allowed})"
            )
        if key == "default_output" and value not in DEFAULT_OUTPUTS:
            raise typer.UsageError(
                f"default_output değeri '{value}' geçersiz; table veya json olmalı"
            )
        if key == "api_url" and not value.startswith(("http://", "https://")):
            raise typer.UsageError(f"api_url 'http(s)://' ile başlamalı: {value}")
        if key == "tui_refresh_seconds":
            try:
                n = int(value)
            except ValueError:
                raise typer.UsageError(
                    f"tui_refresh_seconds tam sayı olmalı: {value}"
                ) from None
            # 10-600 arasi kabul; disi clamp (tasarim §6.1).
            value = str(max(TUI_REFRESH_MIN, min(TUI_REFRESH_MAX, n)))
        elif key == "tui_default_period" and value not in TUI_DEFAULT_PERIODS:
            raise typer.UsageError(
                f"tui_default_period değeri '{value}' geçersiz; 1mo|3mo|6mo|1y olmalı"
            )
        elif key == "tui_default_chart" and value not in TUI_DEFAULT_CHARTS:
            raise typer.UsageError(
                f"tui_default_chart değeri '{value}' geçersiz; line|candle olmalı"
            )
        self._data[key] = value
        self._save()

    def set_last_login(self, username: str, user_type: str) -> None:
        """Login sonrasi otomatik kayit (T3.2a: tip bilgisi config'te)."""
        self._data["last_username"] = username
        self._data["last_type"] = user_type if user_type in ("user", "bot") else "user"
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["[cli]"]
        for key, value in self._data.items():
            lines.append(f"{key} = {_toml_quote(value)}")
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
