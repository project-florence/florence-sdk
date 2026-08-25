"""PANO ekranı (DashboardScreen) — Web benzeri kart yerleşimi.

Layout:
- Üst bar: piyasa durumu (AÇIK/KAPALI/TATİL + next_open_at) + son güncelleme.
- Favoriler Kart Şeridi (FavoritesCard): Yıldızlı takip listesi (Ticker, Fiyat, Δ%, mini trend).
- Orta Satır (2 panel):
  - POPÜLER BİST HİSSELERİ (popular): Ticker, Şirket, Fiyat, Δ%, Hacim
  - GÜNÜN HAREKETLERİ (movers): Yükselenler / Düşenler (`g`/`l`/Tab ile sekme)
- Alt Satır (2 kart):
  - GÜNÜN PİYASA BÜLTENİ (DigestCard): AI bülten özeti + `[3]` veya tıklama ile tam bülten
  - DÖVİZ & ALTIN PİYASASI (EconomyCard): USD, EUR, Gram Altın, Çeyrek Altın kartları
- Navigasyon: Satır seçip `Enter` veya tıklama ile `DetailScreen`'e geçiş.

Yükleme/hata/429 durumları: her panel kendi placeholder'ı ile başlar (`Yükleniyor…`);
hata banner'ı üste çıkar, önceki veri silinmez. Auth yoksa auth-gerektiren bölümler
'Giriş yapın (fl auth login)' uyarısı gösterir.

Veri mantığı: poll worker'ı `DataHub.fetch_dashboard` sonucunu `DashboardDataUpdated`
mesajıyla taşır; bu ekran yalnızca sunum yapar.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import ContentSwitcher, DataTable, Static

from ..banner import banner_text
from ..charts import spark_text
from ..data import (
    DashboardSnapshot,
    delta_style,
    gold_summary,
    status_bar_text,
    tr_delta,
    tr_number,
)
from ..keys import KEY_GAINERS, KEY_LOSERS, KEY_OPEN_DETAIL, KEY_TOGGLE_MOVERS
from ..widgets.nav import AppHeader

__all__ = [
    "DashboardDataFailed",
    "DashboardDataUpdated",
    "DashboardScreen",
    "DataPanel",
    "DigestCard",
    "EconomyCard",
    "FavoritesCard",
]


def _format_volume(val: Any) -> str:
    """Hacim değerini Türkçe finansal gösterime çevirir."""
    if val is None:
        return "—"
    try:
        n = float(val)
    except (TypeError, ValueError):
        return str(val)
    if n >= 1_000_000_000:
        return f"₺{n / 1_000_000_000:.2f} Mr".replace(".", ",")
    if n >= 1_000_000:
        return f"₺{n / 1_000_000:.1f} Mn".replace(".", ",")
    if n >= 1_000:
        return f"₺{n / 1_000:.0f} B".replace(".", ",")
    return f"₺{n:,.0f}".replace(",", ".")


# ----------------------------------------------------------------------
# Poll worker -> ekran mesajlari
# ----------------------------------------------------------------------
class DashboardDataUpdated(Message):
    """Basarili bir tick'in pano snapshot'i."""

    def __init__(self, snapshot: DashboardSnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot


class DashboardDataFailed(Message):
    """Tick toplam hata ile bitti (429 / network / beklenmeyen)."""

    def __init__(self, error: str, retry_after: float | None = None) -> None:
        super().__init__()
        self.error = error
        self.retry_after = retry_after


# ----------------------------------------------------------------------
# DataPanel: baslik + durum (loading/auth/empty/error) + DataTable
# ----------------------------------------------------------------------
class DataPanel(Vertical):
    """Baslik ve durum placeholder'lari olan DataTable paneli.

    Durumlar (ContentSwitcher pane'leri): ``loading`` (Yükleniyor…),
    ``auth`` (Giriş yapın), ``empty`` (Veri yok), ``error`` (Veri alınamadı),
    ``table`` (dolu DataTable).
    """

    DEFAULT_CSS = """
    DataPanel {
        height: 1fr;
        border: round $primary 40%;
        padding: 0 1 1 1;
    }
    DataPanel:focus-within {
        border: round $primary;
    }
    DataPanel > Static.panel-title {
        text-style: bold;
        padding: 0 0 1 0;
    }
    DataPanel > ContentSwitcher {
        height: 1fr;
    }
    DataPanel > ContentSwitcher > Static {
        padding: 1 0;
        color: $text 60%;
    }
    """

    def __init__(
        self,
        title: str,
        table_id: str,
        columns: tuple[str, ...],
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._table_id = table_id
        self._title_static = Static(title, classes="panel-title")
        self._table = DataTable(id=table_id, cursor_type="row", zebra_stripes=True)
        self._table.add_columns(*columns)
        self._switcher = ContentSwitcher(
            Static("Yükleniyor…", id=f"{table_id}-loading"),
            Static("Giriş yapın (fl auth login)", id=f"{table_id}-auth"),
            Static("Veri yok", id=f"{table_id}-empty"),
            Static("Veri alınamadı", id=f"{table_id}-error"),
            self._table,
            initial=f"{table_id}-loading",
            id=f"{table_id}-switcher",
        )

    def compose(self) -> ComposeResult:
        yield self._title_static
        yield self._switcher

    def set_title(self, title: str) -> None:
        self._title_static.update(title)

    def set_state(self, state: str) -> None:
        pane_id = self._table_id if state == "table" else f"{self._table_id}-{state}"
        self._switcher.current = pane_id

    def current_state(self) -> str | None:
        current = self._switcher.current
        if current is None:
            return None
        if current == self._table_id:
            return "table"
        prefix = f"{self._table_id}-"
        if current.startswith(prefix):
            return current[len(prefix) :]
        return current

    @property
    def table(self) -> DataTable:
        return self._table


# ----------------------------------------------------------------------
# Favoriler Kart Şeridi
# ----------------------------------------------------------------------
class FavoritesCard(Vertical):
    """Yıldızlı favori hisseler kart şeridi."""

    DEFAULT_CSS = """
    FavoritesCard {
        height: auto;
        min-height: 3;
        border: round $primary 40%;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    FavoritesCard:focus-within {
        border: round $primary;
    }
    FavoritesCard > Static.card-title {
        text-style: bold;
        color: $accent;
    }
    FavoritesCard > ContentSwitcher {
        height: auto;
    }
    FavoritesCard > ContentSwitcher > Static {
        color: $text 60%;
    }
    """

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._title_static = Static("★ TAKİP LİSTESİ", classes="card-title")
        self._content_static = Static("", id="favorites-content")
        self._switcher = ContentSwitcher(
            Static("Yükleniyor…", id="favorites-loading"),
            Static("Giriş yapın (fl auth login)", id="favorites-auth"),
            Static("★ Henüz favori hisse eklenmedi (fl portfolio favorite add <KOD>)", id="favorites-empty"),
            Static("Veri alınamadı", id="favorites-error"),
            self._content_static,
            initial="favorites-loading",
            id="favorites-switcher",
        )

    def compose(self) -> ComposeResult:
        yield self._title_static
        yield self._switcher

    def set_state(self, state: str) -> None:
        pane_id = "favorites-content" if state == "content" else f"favorites-{state}"
        self._switcher.current = pane_id

    def current_state(self) -> str | None:
        current = self._switcher.current
        if current is None:
            return None
        if current == "favorites-content":
            return "content"
        if current.startswith("favorites-"):
            return current[len("favorites-") :]
        return current

    def update_content(self, text: str) -> None:
        self._content_static.update(text)


# ----------------------------------------------------------------------
# Günün Bülteni Kartı
# ----------------------------------------------------------------------
class DigestCard(Vertical):
    """Günün AI piyasa bülteni özet kartı."""

    DEFAULT_CSS = """
    DigestCard {
        height: 1fr;
        border: round $primary 40%;
        padding: 0 1 1 1;
        margin-right: 1;
    }
    DigestCard:focus-within, DigestCard:hover {
        border: round $accent;
    }
    DigestCard > Static.card-title {
        text-style: bold;
        color: $primary;
        padding: 0 0 1 0;
    }
    DigestCard > ContentSwitcher {
        height: 1fr;
    }
    DigestCard > ContentSwitcher > Static {
        color: $text 60%;
    }
    """

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._title_static = Static("✦ GÜNÜN PİYASA BÜLTENİ", classes="card-title")
        self._content_static = Static("", id="digest-content")
        self._switcher = ContentSwitcher(
            Static("Yükleniyor…", id="digest-loading"),
            Static("Giriş yapın (fl auth login)", id="digest-auth"),
            Static("Bugün için bülten bulunmuyor", id="digest-empty"),
            Static("Bülten alınamadı", id="digest-error"),
            self._content_static,
            initial="digest-loading",
            id="digest-switcher",
        )

    def compose(self) -> ComposeResult:
        yield self._title_static
        yield self._switcher

    def on_click(self) -> None:
        go_digest = getattr(self.app, "action_go_digest", None)
        if callable(go_digest):
            go_digest()

    def set_state(self, state: str) -> None:
        pane_id = "digest-content" if state == "content" else f"digest-{state}"
        self._switcher.current = pane_id

    def current_state(self) -> str | None:
        current = self._switcher.current
        if current is None:
            return None
        if current == "digest-content":
            return "content"
        if current.startswith("digest-"):
            return current[len("digest-") :]
        return current

    def update_content(self, text: str) -> None:
        self._content_static.update(text)


# ----------------------------------------------------------------------
# Döviz & Altın Piyasası Kartı
# ----------------------------------------------------------------------
class EconomyCard(Vertical):
    """Döviz ve Altın piyasası özet kartı."""

    DEFAULT_CSS = """
    EconomyCard {
        height: 1fr;
        border: round $primary 40%;
        padding: 0 1 1 1;
    }
    EconomyCard:focus-within, EconomyCard:hover {
        border: round $primary;
    }
    EconomyCard > Static.card-title {
        text-style: bold;
        padding: 0 0 1 0;
    }
    EconomyCard > ContentSwitcher {
        height: 1fr;
    }
    EconomyCard > ContentSwitcher > Static {
        color: $text 60%;
    }
    """

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._title_static = Static("DÖVİZ & ALTIN PİYASASI", classes="card-title")
        self._content_static = Static("", id="economy-content")
        self._switcher = ContentSwitcher(
            Static("Yükleniyor…", id="economy-loading"),
            Static("Altın/döviz için giriş yapın: fl auth login", id="economy-auth"),
            Static("Veri yok", id="economy-empty"),
            Static("Veri alınamadı", id="economy-error"),
            self._content_static,
            initial="economy-loading",
            id="economy-switcher",
        )

    def compose(self) -> ComposeResult:
        yield self._title_static
        yield self._switcher

    def on_click(self) -> None:
        go_economy = getattr(self.app, "action_go_economy", None)
        if callable(go_economy):
            go_economy()

    def set_state(self, state: str) -> None:
        pane_id = "economy-content" if state == "content" else f"economy-{state}"
        self._switcher.current = pane_id

    def current_state(self) -> str | None:
        current = self._switcher.current
        if current is None:
            return None
        if current == "economy-content":
            return "content"
        if current.startswith("economy-"):
            return current[len("economy-") :]
        return current

    def update_content(self, text: str) -> None:
        self._content_static.update(text)


# ----------------------------------------------------------------------
# Pano ekranı
# ----------------------------------------------------------------------
class DashboardScreen(Screen[None]):
    """PANO: web benzeri kart tasarımlı BİST genel bakış ekranı."""

    BINDINGS = [
        Binding(KEY_GAINERS, "show_gainers", "Yükselenler"),
        Binding(KEY_LOSERS, "show_losers", "Düşenler"),
        Binding(KEY_TOGGLE_MOVERS, "toggle_movers", "Sekme", priority=True),
        Binding(KEY_OPEN_DETAIL, "open_detail", "Detay", priority=True),
    ]

    DEFAULT_CSS = """
    DashboardScreen {
        background: $surface;
    }
    #banner-art {
        padding: 0 1;
        text-style: bold;
    }
    #status-bar {
        padding: 0 1;
        text-style: bold;
        background: $panel;
    }
    #banner {
        display: none;
        padding: 0 1;
        background: $error 25%;
        color: $text;
    }
    #banner.visible {
        display: block;
    }
    #middle-row {
        height: 1fr;
        min-height: 10;
        margin: 0 0 1 0;
    }
    #bottom-row {
        height: auto;
        min-height: 6;
        margin: 0 0 1 0;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._movers_sort = "gainers"
        self._last_snapshot: DashboardSnapshot | None = None
        self._banner_set = False

    def compose(self) -> ComposeResult:
        with Vertical(id="dashboard-root"):
            yield AppHeader(active="dashboard")
            yield Static("Piyasa durumu yükleniyor…", id="status-bar")
            yield FavoritesCard(id="favorites-card")
            yield Static("", id="banner")
            with Horizontal(id="middle-row"):
                yield DataPanel(
                    "POPÜLER BİST HİSSELERİ",
                    "popular-table",
                    ("Ticker", "Şirket", "Fiyat", "Δ%", "Hacim"),
                    id="popular-panel",
                )
                yield DataPanel(
                    "GÜNÜN HAREKETLERİ — Yükselenler",
                    "movers",
                    ("Ticker", "Fiyat", "Δ%"),
                    id="movers-panel",
                )
            with Horizontal(id="bottom-row"):
                yield DigestCard(id="digest-card")
                yield EconomyCard(id="economy-card")

    # ------------------------------------------------------------------
    # Yaşam döngüsü
    # ------------------------------------------------------------------
    def on_mount(self) -> None:
        if not self._banner_set:
            self._banner_set = True
            art = self.query_one("#banner-art", Static)
            art.update(Text.from_ansi(banner_text(self.app.theme_variables)))

    # ------------------------------------------------------------------
    # Mesaj handler'ları
    # ------------------------------------------------------------------
    def on_dashboard_data_updated(self, message: DashboardDataUpdated) -> None:
        self._last_snapshot = message.snapshot
        snap = message.snapshot
        self._render_status(snap.market_status, snap.fetched_at)
        self._render_favorites(snap)
        self._render_popular_panel(snap)
        self._render_movers_panel(snap)
        self._render_digest_card(snap)
        self._render_economy_card(snap)
        self._render_banner(snap)

    def on_dashboard_data_failed(self, message: DashboardDataFailed) -> None:
        if message.retry_after is not None:
            text = f"Rate limit — {message.retry_after:.0f}s sonra tekrar deneniyor"
        else:
            text = message.error
        self._show_banner(text)

    # ------------------------------------------------------------------
    # Tuş ve etkileşim eylemleri
    # ------------------------------------------------------------------
    def action_show_gainers(self) -> None:
        self._movers_sort = "gainers"
        self._refresh_movers()

    def action_show_losers(self) -> None:
        self._movers_sort = "losers"
        self._refresh_movers()

    def action_toggle_movers(self) -> None:
        self._movers_sort = "losers" if self._movers_sort == "gainers" else "gainers"
        self._refresh_movers()

    def action_open_detail(self) -> None:
        """Seçili ticker detay ekranına gider (popular-panel veya movers-panel)."""
        ticker = self._selected_ticker()
        if not ticker:
            return
        open_detail = getattr(self.app, "open_detail", None)
        if callable(open_detail):
            open_detail(ticker)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Tablo üzerinde Enter'a basıldığında veya tıklandığında seçili hissenin Detay ekranını açar."""
        try:
            row = list(event.data_table.get_row_at(event.cursor_row))
            if row:
                val = row[0]
                ticker = str(val.plain if hasattr(val, "plain") else val).strip()
                open_detail = getattr(self.app, "open_detail", None)
                if callable(open_detail):
                    open_detail(ticker)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Render yardımcıları
    # ------------------------------------------------------------------
    def _refresh_movers(self) -> None:
        panel = self.query_one("#movers-panel", DataPanel)
        label = "Yükselenler" if self._movers_sort == "gainers" else "Düşenler"
        panel.set_title(f"GÜNÜN HAREKETLERİ — {label}")
        if self._last_snapshot is not None:
            self._render_movers_panel(self._last_snapshot)

    def _render_status(self, status: dict[str, Any] | None, fetched_at: datetime) -> None:
        bar = self.query_one("#status-bar", Static)
        bar.update(status_bar_text(status, fetched_at))

    def _render_popular_panel(self, snap: DashboardSnapshot) -> None:
        panel = self.query_one("#popular-panel", DataPanel)
        if "popular" in snap.auth_sections:
            panel.set_state("auth")
            return
        if snap.popular is None:
            panel.set_state("error" if snap.errors.get("popular") else "loading")
            return
        if not snap.popular:
            panel.set_state("empty")
            return
        table = panel.table
        table.clear()
        for row in snap.popular:
            ticker = str(row.get("ticker", "—"))
            name = str(row.get("name", "—"))
            name_disp = name[:18] if len(name) > 18 else name
            price = tr_number(row.get("last_price"))
            delta = tr_delta(row.get("change_pct"))
            vol = _format_volume(row.get("volume"))
            table.add_row(
                Text(ticker, style="bold"),
                Text(name_disp),
                price,
                Text(delta, style=delta_style(row.get("change_pct"))),
                vol,
            )
        panel.set_state("table")

    def _render_movers_panel(self, snap: DashboardSnapshot) -> None:
        panel = self.query_one("#movers-panel", DataPanel)
        section = "gainers" if self._movers_sort == "gainers" else "losers"
        if section in snap.auth_sections:
            panel.set_state("auth")
            return
        rows = snap.gainers if section == "gainers" else snap.losers
        if rows is None:
            panel.set_state("error" if snap.errors.get(section) else "loading")
            return
        if not rows:
            panel.set_state("empty")
            return
        table = panel.table
        table.clear()
        for row in rows:
            ticker = str(row.get("ticker", "—"))
            price = tr_number(row.get("last_price"))
            delta = tr_delta(row.get("change_pct"))
            table.add_row(
                Text(ticker, style="bold"),
                price,
                Text(delta, style=delta_style(row.get("change_pct"))),
            )
        panel.set_state("table")

    def _render_favorites(self, snap: DashboardSnapshot) -> None:
        card = self.query_one("#favorites-card", FavoritesCard)
        if "favorites" in snap.auth_sections or "favorites_summary" in snap.auth_sections:
            card.set_state("auth")
            return
        if snap.favorites_summary is None:
            failed = bool(snap.errors.get("favorites_summary") or snap.errors.get("favorites"))
            card.set_state("error" if failed else "loading")
            return
        if not snap.favorites_summary:
            card.set_state("empty")
            return
        items = []
        for c in snap.favorites_summary[:6]:
            ticker = str(c.get("ticker", ""))
            price = tr_number(c.get("last_price"))
            delta = tr_delta(c.get("change_pct"))
            style_name = delta_style(c.get("change_pct"))
            color = self._resolve_color(style_name)
            trend = self._render_mini_trend(c)
            items.append(f"[bold yellow]★ {ticker}[/bold yellow] {price} ([{color}]{delta}[/{color}] {trend})")
        card.update_content("  │  ".join(items))
        card.set_state("content")

    def _render_mini_trend(self, company: dict[str, Any]) -> str:
        spark = company.get("sparkline") or company.get("close_values")
        if isinstance(spark, list) and spark:
            st = spark_text(spark, width=4)
            ch = company.get("change_pct")
            color = self._resolve_color(delta_style(ch))
            return f"[{color}]{st}[/{color}]"
        ch = company.get("change_pct")
        if ch is None or ch == 0:
            return "[grey]▬ ▄▄[/grey]"
        color = self._resolve_color(delta_style(ch))
        if ch > 0:
            bars = " ▃▅" if ch < 2 else ("▃▅▇" if ch < 5 else "▅▆█")
            return f"[{color}]▲ {bars}[/{color}]"
        bars = "▅▃ " if ch > -2 else ("▇▅▃" if ch > -5 else "█▆▅")
        return f"[{color}]▼ {bars}[/{color}]"

    def _render_digest_card(self, snap: DashboardSnapshot) -> None:
        card = self.query_one("#digest-card", DigestCard)
        if "digest" in snap.auth_sections:
            card.set_state("auth")
            return
        if snap.digest is None:
            failed = bool(snap.errors.get("digest"))
            card.set_state("error" if failed else "loading")
            return
        if not snap.digest or not isinstance(snap.digest, dict):
            card.set_state("empty")
            return
        title = snap.digest.get("title", "Piyasa Bülteni")
        slot = str(snap.digest.get("slot", ""))
        slot_map = {"morning": "Sabah (09:30)", "noon": "Öğle (13:00)", "evening": "Akşam Kapanış (18:30)"}
        slot_lbl = slot_map.get(slot, slot.capitalize() if slot else "Günlük")
        content = str(snap.digest.get("content", "")).strip()
        first_line = content.split("\n")[0] if content else "Piyasa özeti hazırlandı."
        if len(first_line) > 100:
            first_line = first_line[:97] + "..."
        text = (
            f"[bold cyan]✦ {title}[/bold cyan] [dim]({slot_lbl})[/dim]\n"
            f"[italic]{first_line}[/italic]\n\n"
            f"[dim cyan]➔ [3] tuşuna basarak veya tıklayarak tam bülteni açın[/dim cyan]"
        )
        card.update_content(text)
        card.set_state("content")

    def _render_economy_card(self, snap: DashboardSnapshot) -> None:
        card = self.query_one("#economy-card", EconomyCard)
        if "gold" in snap.auth_sections or "currency" in snap.auth_sections:
            card.set_state("auth")
            return
        if snap.gold is None and snap.currency is None:
            failed = bool(snap.errors.get("gold") or snap.errors.get("currency"))
            card.set_state("error" if failed else "loading")
            return
        if not snap.gold and not snap.currency:
            card.set_state("empty")
            return

        usd_val = "—"
        eur_val = "—"
        if snap.currency:
            usd_entry = snap.currency.get("USD")
            if isinstance(usd_entry, dict) and usd_entry.get("buying"):
                usd_val = str(usd_entry["buying"])
            eur_entry = snap.currency.get("EUR")
            if isinstance(eur_entry, dict) and eur_entry.get("buying"):
                eur_val = str(eur_entry["buying"])

        gram_val = "—"
        ceyrek_val = "—"
        if snap.gold:
            for label, item in gold_summary(snap.gold):
                if label == "Gram Altın":
                    gram_val = str(item.get("Buying", "—"))
                elif label == "Çeyrek Altın":
                    ceyrek_val = str(item.get("Buying", "—"))

        line1 = f"[bold yellow]USD/TRY[/] {usd_val}    [bold yellow]EUR/TRY[/] {eur_val}"
        line2 = f"[bold yellow]Gram Altın[/] {gram_val}    [bold yellow]Çeyrek Altın[/] {ceyrek_val}"
        line3 = "[dim][6] Ekonomi detayları için [6]'ya basın[/dim]"

        card.update_content(f"{line1}\n{line2}\n\n{line3}")
        card.set_state("content")

    def _resolve_color(self, var: str) -> str:
        if var.startswith("$"):
            value = getattr(self.app, "theme_variables", {}).get(var[1:])
            if value:
                return str(value)
        return var

    def _render_banner(self, snap: DashboardSnapshot) -> None:
        if not snap.errors:
            self._hide_banner()
            return
        msg = next(iter(snap.errors.values()))
        last = getattr(self.app, "data", None)
        suffix = ""
        if last is not None and last.last_update is not None:
            suffix = f" — son veri gösteriliyor ({last.last_update:%H:%M})"
        self._show_banner(f"{msg}{suffix}")

    def _show_banner(self, text: str) -> None:
        banner = self.query_one("#banner", Static)
        banner.update(text)
        banner.add_class("visible")

    def _hide_banner(self) -> None:
        self.query_one("#banner", Static).remove_class("visible")

    def _selected_ticker(self) -> str | None:
        for panel_id in ("popular-panel", "movers-panel"):
            try:
                panel = self.query_one(f"#{panel_id}", DataPanel)
                if panel.current_state() != "table":
                    continue
                if panel.has_focus or any(w.has_focus for w in panel.walk_children()):
                    row = self._table_cursor_row(panel.table)
                    if row:
                        val = row[0]
                        return str(val.plain if hasattr(val, "plain") else val).strip()
            except Exception:
                continue
        for panel_id in ("popular-panel", "movers-panel"):
            try:
                panel = self.query_one(f"#{panel_id}", DataPanel)
                if panel.current_state() != "table":
                    continue
                row = self._table_cursor_row(panel.table)
                if row:
                    val = row[0]
                    return str(val.plain if hasattr(val, "plain") else val).strip()
            except Exception:
                continue
        return None

    @staticmethod
    def _table_cursor_row(table: DataTable) -> list[Any] | None:
        if table.cursor_row is None:
            return None
        try:
            return list(table.get_row_at(table.cursor_row))
        except Exception:  # pragma: no cover — satir kaybolmus olabilir
            return None
