"""TUI acilis banner'i (docs/research-banner-tui.md B1/B2/B3 kararlari).

Statik gomulu ASCII art + kucuk gradient yardimcisi — yeni bagimlilik YOK
(B1: pyfiglet/cfonts yok); per-karakter 24-bit truecolor interpolasyon
(cfonts ``-g`` cikti modeli, §1.2). Banner yalnizca ilk acilista (mount)
cizilir; poll tick'lerinde yeniden render edilmez (B2).

``banner_text`` renkleri Textual tema degiskenlerinden alir; bulunamazsa
bilinen fallback hex'ler kullanilir (B3 varsayilani: mavi -> magenta).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["FLORENCE_ART", "banner_text", "gradient", "hex2rgb"]

#: cfonts ``block`` fontu ile uretilmis statik "FLORENCE" art (6 satir).
FLORENCE_ART = """\
███████╗ ██╗       ██████╗  ██████╗  ███████╗ ███╗   ██╗  ██████╗ ███████╗
██╔════╝ ██║      ██╔═══██╗ ██╔══██╗ ██╔════╝ ████╗  ██║ ██╔════╝ ██╔════╝
█████╗   ██║      ██║   ██║ ██████╔╝ █████╗   ██╔██╗ ██║ ██║      █████╗
██╔══╝   ██║      ██║   ██║ ██╔══██╗ ██╔══╝   ██║╚██╗██║ ██║      ██╔══╝
██║      ███████╗ ╚██████╔╝ ██║  ██║ ███████╗ ██║ ╚████║ ╚██████╗ ███████╗
╚═╝      ╚══════╝  ╚═════╝  ╚═╝  ╚═╝ ╚══════╝ ╚═╝  ╚═══╝  ╚═════╝ ╚══════╝"""

#: Varsayilan gradient uclari (B3: kullanici begenisi mavi -> magenta).
_DEFAULT_GRADIENT = ("#3b82f6", "#c026d3")


def hex2rgb(color: str) -> tuple[int, int, int]:
    """'#rrggbb' -> (r, g, b); gecersizse (0, 0, 0)."""
    value = str(color).lstrip("#")
    try:
        return (
            int(value[0:2], 16),
            int(value[2:4], 16),
            int(value[4:6], 16),
        )
    except ValueError:
        return (0, 0, 0)


def gradient(text: str, c1: str, c2: str) -> str:
    """Per-karakter truecolor gradient (cfonts ``-g`` ile ayni cikti modeli).

    Her karakter kendi ``ESC[38;2;R;G;Bm`` kodunu tasir; renkler satir
    boyunca c1 -> c2 arasinda dogrusal akar (research-banner-tui.md §1.2).
    """
    a, b = hex2rgb(c1), hex2rgb(c2)
    out: list[str] = []
    for line in text.split("\n"):
        n = max(len(line) - 1, 1)
        for i, ch in enumerate(line):
            t = i / n
            r, g, bl = (round(a[k] + (b[k] - a[k]) * t) for k in range(3))
            out.append(f"\x1b[38;2;{r};{g};{bl}m{ch}")
        out.append("\n")
    return "".join(out)


def banner_text(theme: Mapping[str, Any] | None = None) -> str:
    """Tema renkleriyle gradient'li FLORENCE art (``Text.from_ansi`` icin).

    ``primary`` -> ``secondary`` (yoksa ``accent``) arasi gradient; tema
    yoksa/eksikse ``_DEFAULT_GRADIENT`` fallback (B3).
    """
    t = theme or {}
    c1 = t.get("primary") or _DEFAULT_GRADIENT[0]
    c2 = t.get("secondary") or t.get("accent") or _DEFAULT_GRADIENT[1]
    return gradient(FLORENCE_ART, str(c1), str(c2))