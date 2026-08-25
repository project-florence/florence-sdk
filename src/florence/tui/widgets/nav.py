"""TUI ortak navigasyon tab bari (NavBar).

Ekranlar arasi gecis (tuslar veya tiklama):
[1] Pano  [2] İzleme  [3] Bülten  [4] Portföy  [5] Hisseler  [6] Ekonomi
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

__all__ = ["NavBar"]

TABS = [
    ("1", "dashboard", "Pano"),
    ("2", "watchlist", "İzleme"),
    ("3", "digest", "Bülten"),
    ("4", "portfolio", "Portföy"),
    ("5", "stocks", "Hisseler"),
    ("6", "economy", "Ekonomi"),
]


class NavBar(Static):
    """Ortak sekmeler (tabs) cubugu."""

    DEFAULT_CSS = """
    NavBar {
        padding: 0 1;
        height: 1;
        background: $panel;
        border-bottom: solid $primary 30%;
    }
    """

    def __init__(self, active: str = "dashboard", *, id: str | None = "nav-bar") -> None:
        super().__init__(id=id)
        self.active = active

    def render(self) -> Text:
        text = Text()
        text.append("SEKMELER: ", style="bold dim")
        for key_num, screen_name, label in TABS:
            is_active = (screen_name == self.active)
            if is_active:
                text.append(f" [{key_num}] {label} ", style="bold reverse")
            else:
                text.append(f" [{key_num}] {label} ", style="dim")
            text.append(" ")
        return text
