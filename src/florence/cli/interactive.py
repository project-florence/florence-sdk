"""Interaktif prompt'lar: gizli sifre (getpass) ve yikici onay [y/N].

Kurallar (tasarim 3.8):
- Sifre prompt'lari getpass ile (echo yok).
- Onay prompt'lari ``[y/N]``; yanlis giris -> iptal (exit 1).
- Prompt yalnizca TTY varsa sorulur; TTY yoksa veya ``--json`` verilmisse
  ``PromptRequiredError`` (exit 2, eksik bayrak mesaji) — script'lerde
  surpriz bekleme olmaz.
"""

from __future__ import annotations

import getpass
import sys
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from .context import CliState

__all__ = [
    "CliRuntimeError",
    "PromptRequiredError",
    "confirm_or_abort",
    "secret_prompt",
]


class PromptRequiredError(Exception):
    """Interaktif prompt gerekli ama ortam uygun degil (--json / TTY yok).

    Exit code 2 (kullanim hatasi): eksik ``--yes`` / ``--password`` bayragi.
    """


class CliRuntimeError(Exception):
    """CLI kaynakli calisma hatasi (exit 1, --json hata bicimi destekli)."""

    def __init__(self, detail: str, code: str = "cli_error", status: int | None = None) -> None:
        self.detail = detail
        self.code = code
        self.status = status
        super().__init__(detail)


def secret_prompt(prompt: str, flag_hint: str = "--password") -> str:
    """Gizli sifre prompt'u; TTY yoksa ``PromptRequiredError``."""
    if not sys.stdin.isatty():
        raise PromptRequiredError(
            f"Bu komut gizli şifre girişi gerektiriyor; {flag_hint} bayrağını kullanın."
        )
    return getpass.getpass(f"{prompt}: ")


def confirm_or_abort(state: CliState, prompt: str, yes: bool) -> None:
    """Yikici islem onayi (T3.6 / bolum 3.8).

    - ``--yes`` verildiyse dogrudan gecer.
    - ``--json`` modunda prompt sorulmaz -> ``PromptRequiredError`` (exit 2).
    - TTY yoksa -> ``PromptRequiredError`` (exit 2).
    - ``y``/``yes`` disinda -> 'İptal edildi' + exit 1.
    """
    if yes:
        return
    if state.effective_json():
        raise PromptRequiredError(
            "Bu komut --json modunda interaktif onay gerektiriyor; --yes bayrağını kullanın."
        )
    if not sys.stdin.isatty():
        raise PromptRequiredError(
            "Bu komut interaktif onay gerektiriyor; --yes bayrağını kullanın."
        )
    answer = input(f"{prompt} [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        print("İptal edildi")
        raise typer.Exit(1)
