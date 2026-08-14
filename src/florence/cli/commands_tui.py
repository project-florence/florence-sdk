"""``fl tui`` komutu (docs/tui-design.md §7.3).

Typer komutu yalnizca giris noktasidir: TUI mantigi ``florence.tui.app``
icindedir. Arguman yoktur (K5: v1 sifir arguman); ``--json`` yoktur
(tam ekran interaktif — cli-design.md 'gereksiz bayrak yok' kurali).
``tui_app`` isimsiz ``add_typer`` ile ana CLI'a eklenir; boylece komut
``fl tui`` olarak ust seviyede gorunur (``commands_*.py`` deseni).
"""

from __future__ import annotations

import typer

__all__ = ["tui_app"]

tui_app = typer.Typer(
    help="Tam ekran terminal arayüzü (pano, izleme listesi, detay/grafik).",
    no_args_is_help=True,
)


@tui_app.command("tui")
def tui_command() -> None:
    """Tam ekran TUI'yi başlatır: pano, izleme listesi ve ticker detay/grafik."""
    # Gec import: dairesel bagimlilik yok (tui.app -> cli.config_cli) ve
    # ``fl --help`` gibi hafif akislar TUI'yi yuklemez.
    from florence.tui.app import main as tui_main

    tui_main()
