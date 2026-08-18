"""PANO ekrani (DashboardScreen) — docs/tui-design.md §2.1.

Layout:
- Ust bar: piyasa durumu (AÇIK/KAPALI/TATİL + next_open_at) + son guncelleme.
- Orta (2 panel): ONE CIKANLAR (stats_top) ve GUNUN HAREKETLERI
  (companies_summary gainers/losers; ``g``/``l``/Tab ile sekme).
- Alt serit: altin (gold_prices) + doviz (currency) ozeti.

Yukleme/hata/429 durumlari: her panel kendi placeholder'i ile baslar
(``Yükleniyor…``); hata banner'i uste cikar, onceki veri silinmez.
Auth yoksa auth-gerektiren bolumler 'Giris yapin (fl auth login)' uyarisi
gosterir (canli backend dogrulamasi: stats_top/companies_summary/economy
allowlist'te degil).

Veri mantigi YOKTUR: poll worker'i ``DataHub.fetch_dashboard`` sonucunu
``DashboardDataUpdated`` mesajiyla tasir; bu ekran yalnizca sunum yapar.
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

from ..data import DashboardSnapshot, delta_style, gold_summary, tr_delta, tr_number
from ..keys import KEY_GAINERS, KEY_LOSERS, KEY_OPEN_DETAIL, KEY_TOGGLE_MOVERS

__all__ = ["DashboardDataFailed", "DashboardDataUpdated", "DashboardScreen"]


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
        self._title_static = Static(title, classes="panel-title")
        self._table = DataTable(id=table_id, cursor_type="row", zebra_stripes=True)
        self._table.add_columns(*columns)
        # ContentSwitcher pane'leri cocuk id'leriyle adreslenir; tablo pane'i
        # kendi id'siyle ("table" durumu) secilir.
        self._switcher = ContentSwitcher(
            Static("Yükleniyor…", id=f"{table_id}-loading"),
            Static("Giriş yapın (fl auth login)", id=f"{table_id}-auth"),
            Static("Veri yok", id=f"{table_id}-empty"),
            Static("Veri alınamadı", id=f"{table_id}-error"),
            self._table,
            initial=f"{table_id}-loading",
        )

    def compose(self) -> ComposeResult:
        yield self._title_static
        yield self._switcher

    def set_title(self, title: str) -> None:
        self._title_static.update(title)

    def set_state(self, state: str) -> None:
        pane_id = self._table.id if state == "table" else f"{self._table.id}-{state}"
        self._switcher.current = pane_id

    def current_state(self) -> str | None:
        current = self._switcher.current
        if current is None:
            return None
        if current == self._table.id:
            return "table"
        prefix = f"{self._table.id}-"
        if current.startswith(prefix):
            return current[len(prefix) :]
        return current

    @property
    def table(self) -> DataTable:
        return self._table


# ----------------------------------------------------------------------
# Pano ekrani
# ----------------------------------------------------------------------
class DashboardScreen(Screen[None]):
    """PANO: piyasanin 10 saniyelik ozeti (tasarim §2.1)."""

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
    #panels-row {
        height: 1fr;
    }
    #economy-strip {
        padding: 0 1;
        border-top: solid $primary 40%;
        background: $panel;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._movers_sort = "gainers"
        self._last_snapshot: DashboardSnapshot | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="dashboard-root"):
            yield Static("Piyasa durumu yükleniyor…", id="status-bar")
            yield Static("", id="banner")
            with Horizontal(id="panels-row"):
                yield DataPanel(
                    "ÖNE ÇIKANLAR (ilgi)",
                    "stats-top",
                    ("Ticker", "İlgi"),
                    id="stats-panel",
                )
                yield DataPanel(
                    "GÜNÜN HAREKETLERİ — Yükselenler",
                    "movers",
                    ("Ticker", "Fiyat", "Δ%"),
                    id="movers-panel",
                )
            yield Static("", id="economy-strip")

    # ------------------------------------------------------------------
    # Mesaj handler'lari
    # ------------------------------------------------------------------
    def on_dashboard_data_updated(self, message: DashboardDataUpdated) -> None:
        self._last_snapshot = message.snapshot
        snap = message.snapshot
        self._render_status(snap.market_status, snap.fetched_at)
        self._render_stats_panel(snap)
        self._render_movers_panel(snap)
        self._render_economy(snap)
        self._render_banner(snap)

    def on_dashboard_data_failed(self, message: DashboardDataFailed) -> None:
        if message.retry_after is not None:
            text = f"Rate limit — {message.retry_after:.0f}s sonra tekrar deneniyor"
        else:
            text = message.error
        self._show_banner(text)

    # ------------------------------------------------------------------
    # Tus eylemleri
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
        """PART 2 kancasi: seçili ticker detay ekranina gider."""
        ticker = self._selected_ticker()
        if not ticker:
            return
        open_detail = getattr(self.app, "open_detail", None)
        if callable(open_detail):
            open_detail(ticker)

    # ------------------------------------------------------------------
    # Render yardimcilari
    # ------------------------------------------------------------------
    def _refresh_movers(self) -> None:
        panel = self.query_one("#movers-panel", DataPanel)
        label = "Yükselenler" if self._movers_sort == "gainers" else "Düşenler"
        panel.set_title(f"GÜNÜN HAREKETLERİ — {label}")
        if self._last_snapshot is not None:
            self._render_movers_panel(self._last_snapshot)

    def _render_status(self, status: dict[str, Any] | None, fetched_at: datetime) -> None:
        bar = self.query_one("#status-bar", Static)
        if not isinstance(status, dict):
            bar.update("[grey]Piyasa durumu alınamadı[/]")
            return
        if status.get("holiday"):
            state = "[yellow]TATİL[/]"
        elif status.get("open"):
            state = "[green]AÇIK[/]"
        else:
            state = "[red]KAPALI[/]"
            nxt = status.get("next_open_at")
            if nxt:
                state += f" · {_format_open_time(nxt)}'da açılacak"
        bar.update(f"Piyasa: {state}  ·  Son güncelleme: {fetched_at:%H:%M:%S}")

    def _render_stats_panel(self, snap: DashboardSnapshot) -> None:
        panel = self.query_one("#stats-panel", DataPanel)
        if "stats_top" in snap.auth_sections:
            panel.set_state("auth")
            return
        if snap.stats_top is None:
            panel.set_state("error" if snap.errors.get("stats_top") else "loading")
            return
        if not snap.stats_top:
            panel.set_state("empty")
            return
        table = panel.table
        table.clear()
        for i, row in enumerate(snap.stats_top):
            ticker = str(row.get("ticker", "—"))
            # Gercek backend semasi: {"ticker", "name", ..., "total"} — toplam ilgi.
            total = row.get("total") or 0
            cell = Text(str(total), style="$primary" if i == 0 else "")
            table.add_row(ticker, cell)
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
            # Gercek backend semasi: "last_price" (companies/summary).
            price = tr_number(row.get("last_price"))
            delta = tr_delta(row.get("change_pct"))
            table.add_row(ticker, price, Text(delta, style=delta_style(row.get("change_pct"))))
        panel.set_state("table")

    def _render_economy(self, snap: DashboardSnapshot) -> None:
        strip = self.query_one("#economy-strip", Static)
        if "gold" in snap.auth_sections:
            strip.update("[grey]Altın/döviz için giriş yapın: fl auth login[/]")
            return
        if snap.gold is None and snap.currency is None:
            failed = bool(snap.errors.get("gold") or snap.errors.get("currency"))
            strip.update("[grey]Veri alınamadı[/]" if failed else "[grey]Yükleniyor…[/]")
            return
        parts: list[str] = []
        for label, item in gold_summary(snap.gold or []):
            parts.append(f"{label} {item.get('Buying', '—')}")
        if snap.currency:
            for sym in ("USD", "EUR"):
                entry = snap.currency.get(sym)
                if isinstance(entry, dict) and entry.get("buying"):
                    parts.append(f"{sym}/TRY {entry['buying']}")
        strip.update("  │  ".join(parts) if parts else "[grey]Veri yok[/]")

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
        for panel_id in ("stats-panel", "movers-panel"):
            panel = self.query_one(f"#{panel_id}", DataPanel)
            if panel.current_state() != "table":
                continue
            row = self._table_cursor_row(panel.table)
            if row:
                return str(row[0])
        return None

    @staticmethod
    def _table_cursor_row(table: DataTable) -> list[Any] | None:
        if table.cursor_row is None:
            return None
        try:
            return list(table.get_row_at(table.cursor_row))
        except Exception:  # pragma: no cover — satir kaybolmus olabilir
            return None


def _format_open_time(raw: Any) -> str:
    """ISO next_open_at -> yerel saat ('10:00'); gecersizse ham metin."""
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.astimezone().strftime("%H:%M")
    except ValueError:
        return str(raw)
