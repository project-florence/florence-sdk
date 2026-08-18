"""TUI acilis banner testleri: gradient yardimcisi + DashboardScreen widget'i.

Tasarim (docs/research-banner-tui.md B1/B2/B3): statik gomulu ASCII art +
kendi gradient yardimcisi (yeni bagimlilik YOK); yalnizca ilk acilista
(mount) cizilir, poll tick'lerinde yeniden render edilmez.
"""

from __future__ import annotations

import asyncio

from textual.widgets import Static

from florence.tui import banner
from florence.tui.app import FlorenceTUI

from .conftest import make_handler, wait_for


def _banner_text(app: FlorenceTUI) -> str:
    """Banner widget'inin ANSI'siz duz metni (FLORENCE_ART'a esit olmali)."""
    try:
        # gradient() her satir (sonuncusu dahil) sonuna \n ekler; widget
        # render'i bunu korur — karsilastirma icin uc \n atilir.
        return str(app.screen.query_one("#banner-art", Static).render()).rstrip("\n")
    except Exception:
        return ""


# ----------------------------------------------------------------------
# Birim: gradient yardimcisi (research-banner-tui.md §1.2 modeli)
# ----------------------------------------------------------------------
def test_gradient_interpolates_between_colors():
    out = banner.gradient("AB", "#ff0000", "#0000ff")
    # Her karakter kendi 24-bit ANSI koduna sahip (cfonts -g cikti modeli).
    assert "\x1b[38;2;255;0;0mA" in out
    assert "\x1b[38;2;0;0;255mB" in out


def test_gradient_multiline_keeps_newlines():
    out = banner.gradient("A\nB", "#000000", "#ffffff")
    assert out.count("\n") == 2
    assert out.endswith("B\n")  # her satir (sonuncusu dahil) \n ile biter


def test_banner_text_contains_art_and_uses_theme():
    out = banner.banner_text({"primary": "#ff0000", "secondary": "#0000ff"})
    # Blok font: harfler █ karakterleriyle cizilir; dogrulama ANSI + art icerigiyle.
    assert out.startswith("\x1b[38;2;255;0;0m")  # ilk renk tema primary
    assert out.count("\x1b[38;2;") > 100  # per-karakter truecolor gradient
    assert out.endswith("╝\n")  # art'in son satiri korundu


def test_banner_text_falls_back_defaults_without_theme():
    # Tema yoksa bilinen fallback hex'ler kullanilir (B3) — hata yok.
    default = banner.banner_text(None)
    assert default.startswith("\x1b[38;2;59;130;246m")  # #3b82f6
    assert banner.banner_text({}) == default


def test_hex2rgb_parses_and_tolerates_bad_input():
    assert banner.hex2rgb("#1a8a5c") == (26, 138, 92)
    assert banner.hex2rgb("gecersiz") == (0, 0, 0)


# ----------------------------------------------------------------------
# Widget: yalnizca ilk acilista cizilir, poll'da degismez
# ----------------------------------------------------------------------
def test_banner_rendered_once_on_mount_and_kept_across_ticks(make_app):
    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)):
            await wait_for(app, lambda: _banner_text(app) == banner.FLORENCE_ART)
            first = _banner_text(app)
            # Refresh intervali kisa (0.05s) — birkac poll tick'i beklenir;
            # banner yeniden cizilmemeli (icerik ayni kalir).
            await asyncio.sleep(0.35)
            assert _banner_text(app) == first
            assert first == banner.FLORENCE_ART

    asyncio.run(run())


def test_banner_widget_visible_on_dashboard_layout(make_app):
    async def run() -> None:
        app = make_app(make_handler())
        async with app.run_test(size=(120, 40)):
            await wait_for(app, lambda: _banner_text(app) == banner.FLORENCE_ART)
            # Banner pano duzeninin en ustunde durur (baslik barindan once).
            root = app.screen.query_one("#dashboard-root")
            assert root.children[0].id == "banner-art"

    asyncio.run(run())