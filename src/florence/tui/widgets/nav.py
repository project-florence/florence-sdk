"""TUI ortak navigasyon tab barı (NavBar) ve üst başlık (AppHeader).

Ekranlar arası geçiş (tuşlar veya tıklama):
[1] Pano  [2] Hisseler  [3] İzleme  [4] Bülten  [5] Portföy  [6] Ekonomi
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, Tab, Tabs

from ..banner import banner_text

__all__ = [
    "SCREEN_CLASS_NAMES",
    "SCREEN_TO_TAB",
    "TAB_DEFINITIONS",
    "TAB_TO_SCREEN",
    "AppHeader",
    "BannerArt",
    "NavBar",
]

#: Tab tanımları: (kısayol, ekran_adı, etiket, tab_id)
TAB_DEFINITIONS: list[tuple[str, str, str, str]] = [
    ("1", "dashboard", "Pano", "tab-dashboard"),
    ("2", "stocks", "Hisseler", "tab-stocks"),
    ("3", "watchlist", "İzleme", "tab-watchlist"),
    ("4", "digest", "Bülten", "tab-digest"),
    ("5", "portfolio", "Portföy", "tab-portfolio"),
    ("6", "economy", "Ekonomi", "tab-economy"),
]

TAB_TO_SCREEN: dict[str, str] = {
    "tab-dashboard": "dashboard",
    "tab-stocks": "stocks",
    "tab-watchlist": "watchlist",
    "tab-digest": "digest",
    "tab-portfolio": "portfolio",
    "tab-economy": "economy",
}

SCREEN_TO_TAB: dict[str, str] = {v: k for k, v in TAB_TO_SCREEN.items()}

SCREEN_CLASS_NAMES: dict[str, str] = {
    "dashboard": "DashboardScreen",
    "stocks": "StocksScreen",
    "watchlist": "WatchlistScreen",
    "digest": "DigestScreen",
    "portfolio": "PortfolioScreen",
    "economy": "EconomyScreen",
}


class BannerArt(Static):
    """FLORENCE renkli ASCII logo banner'ı (tüm ekranlar için ortak)."""

    DEFAULT_CSS = """
    BannerArt {
        padding: 0 1;
        text-style: bold;
        height: auto;
    }
    """

    def __init__(self, *, id: str | None = "banner-art") -> None:
        super().__init__("", id=id)

    def on_mount(self) -> None:
        theme = getattr(self.app, "theme_variables", None)
        self.update(Text.from_ansi(banner_text(theme)))


class NavBar(Tabs):
    """Textual yerel Tabs bileşeni ile tıklanabilir ve klavye destekli navigasyon çubuğu."""

    DEFAULT_CSS = """
    NavBar {
        dock: top;
        height: 3;
        background: $panel;
        border-bottom: solid $primary 30%;
    }
    """

    def __init__(
        self,
        active: str = "dashboard",
        *,
        id: str | None = "nav-bar",
    ) -> None:
        self.active_screen = active
        tab_id = f"tab-{active}" if active and not active.startswith("tab-") else active
        super().__init__(
            Tab("[1] Pano", id="tab-dashboard"),
            Tab("[2] Hisseler", id="tab-stocks"),
            Tab("[3] İzleme", id="tab-watchlist"),
            Tab("[4] Bülten", id="tab-digest"),
            Tab("[5] Portföy", id="tab-portfolio"),
            Tab("[6] Ekonomi", id="tab-economy"),
            active=tab_id,
            id=id,
        )

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        """Mouse ile sekme tıklandığında veya klavyeyle seçildiğinde ekranı değiştir."""
        if event.tab and event.tab.id:
            screen_name = TAB_TO_SCREEN.get(event.tab.id)
            if screen_name and screen_name != self.active_screen:
                self.app.switch_screen(screen_name)

    def set_active_screen(self, screen_name: str) -> None:
        """Aktif sekme id'sini günceller."""
        self.active_screen = screen_name
        tab_id = SCREEN_TO_TAB.get(screen_name, f"tab-{screen_name}")
        if self.active != tab_id:
            self.active = tab_id


class AppHeader(Vertical):
    """Tüm ekranlar için kalıcı FLORENCE ASCII logo ve navigasyon üst başlığı."""

    DEFAULT_CSS = """
    AppHeader {
        height: auto;
    }
    """

    def __init__(
        self,
        active: str | None = "dashboard",
        *,
        show_nav: bool = True,
        id: str | None = "app-header",
    ) -> None:
        super().__init__(id=id)
        self.active = active
        self.show_nav = show_nav

    def compose(self) -> ComposeResult:
        yield BannerArt(id="banner-art")
        if self.show_nav:
            yield NavBar(active=self.active or "dashboard")

