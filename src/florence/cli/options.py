"""Ortak typer opsiyon fabrikalari: ``--json`` ve ``--verbose`` (global).

Her komut kendi parametrelerinde bu fabrikalari cagirir (taze option
nesnesi) — boylece bayrak komuttan sonra da yazilabilir:
``fl market price THYAO --json``. Grup callback'leri (main app) ayni
bayraklari komuttan ONCE kabul eder: ``fl --json market price THYAO``.
"""

from __future__ import annotations

import typer

__all__ = ["json_opt", "verbose_opt"]


def json_opt() -> typer.Option:
    """``--json`` bayragi: stdout'a tek JSON belgesi (makine-okunur)."""
    return typer.Option(
        False,
        "--json",
        help="Çıktıyı JSON olarak bas (makine-okunur; API şeması birebir).",
    )


def verbose_opt() -> typer.Option:
    """``--verbose`` bayragi: ayrintili loglama (stderr)."""
    return typer.Option(False, "--verbose", help="Ayrıntılı loglama (stderr).")
