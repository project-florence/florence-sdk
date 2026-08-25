"""EKONOMİ ekranı (EconomyScreen) — Altın, Döviz ve Kıymetli Madenler.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import ContentSwitcher, DataTable, Static

from ..data import EconomySnapshot, status_bar_text
from ..widgets.nav import AppHeader

__all__ = ["EconomyDataFailed", "EconomyDataUpdated", "EconomyScreen"]


class EconomyDataUpdated(Message):
    def __init__(self, snapshot: EconomySnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot


class EconomyDataFailed(Message):
    def __init__(self, error: str, retry_after: float | None = None) -> None:
        super().__init__()
        self.error = error
        self.retry_after = retry_after


class EconomyScreen(Screen[None]):
    """Ekonomi, Altın ve Döviz oranları ekranı."""

    DEFAULT_CSS = """
    EconomyScreen {
        background: $surface;
    }
    #economy-status {
        padding: 0 1;
        text-style: bold;
        background: $panel;
    }
    #economy-tables {
        height: 1fr;
    }
    .econ-panel {
        height: 1fr;
        padding: 0 1 1 1;
        border: round $primary 40%;
    }
    .econ-title {
        text-style: bold;
        padding: 0 0 1 0;
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
    """

    def __init__(self) -> None:
        super().__init__()
        self._last_snapshot: EconomySnapshot | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="economy-root"):
            yield AppHeader(active="economy")
            yield Static("Piyasa durumu yükleniyor…", id="economy-status")
            yield Static("", id="banner")
            with Horizontal(id="economy-tables"):
                with Vertical(classes="econ-panel"):
                    yield Static("DÖVİZ KURLARI", classes="econ-title")
                    with ContentSwitcher(id="currency-switcher", initial="currency-loading"):
                        yield Static("Yükleniyor…", id="currency-loading")
                        yield Static("Giriş yapın", id="currency-auth")
                        yield Static("Veri yok", id="currency-empty")
                        curr_table = DataTable(id="currency-table", cursor_type="row", zebra_stripes=True)
                        curr_table.add_columns("Döviz Kodu", "Alış", "Satış", "Δ%")
                        yield curr_table
                with Vertical(classes="econ-panel"):
                    yield Static("ALTIN & KIYMETLİ METALLER", classes="econ-title")
                    with ContentSwitcher(id="gold-switcher", initial="gold-loading"):
                        yield Static("Yükleniyor…", id="gold-loading")
                        yield Static("Giriş yapın", id="gold-auth")
                        yield Static("Veri yok", id="gold-empty")
                        gold_table = DataTable(id="gold-table", cursor_type="row", zebra_stripes=True)
                        gold_table.add_columns("Maden", "Alış (₺)", "Satış (₺)")
                        yield gold_table

    def on_mount(self) -> None:
        poll_now = getattr(self.app, "poll_now", None)
        if callable(poll_now):
            poll_now()

    def on_economy_data_updated(self, message: EconomyDataUpdated) -> None:
        self._last_snapshot = message.snapshot
        snap = message.snapshot
        self._render_status(snap.market_status, snap.fetched_at)
        self._render_currency(snap)
        self._render_gold(snap)

    def on_economy_data_failed(self, message: EconomyDataFailed) -> None:
        banner = self.query_one("#banner", Static)
        if message.retry_after is not None:
            text = f"Rate limit — {message.retry_after:.0f}s sonra tekrar deneniyor"
        else:
            text = message.error
        banner.update(text)
        banner.add_class("visible")

    def _render_status(self, status: dict[str, Any] | None, fetched_at: datetime) -> None:
        bar = self.query_one("#economy-status", Static)
        bar.update(status_bar_text(status, fetched_at))

    def _render_currency(self, snap: EconomySnapshot) -> None:
        switcher = self.query_one("#currency-switcher", ContentSwitcher)
        if "currency" in snap.auth_sections:
            switcher.current = "currency-auth"
            return
        if snap.currency is None:
            switcher.current = "currency-loading"
            return
        if not snap.currency:
            switcher.current = "currency-empty"
            return

        table = self.query_one("#currency-table", DataTable)
        table.clear()
        rates = snap.currency.get("rates", snap.currency)
        if isinstance(rates, dict):
            for symbol, details in rates.items():
                if isinstance(details, dict):
                    buying = details.get("buying", details.get("buying_str", "—"))
                    selling = details.get("selling", details.get("selling_str", "—"))
                    ch = details.get("change_rate", details.get("change_pct", "—"))
                    table.add_row(symbol, str(buying), str(selling), str(ch))
                elif isinstance(details, (int, float, str)):
                    table.add_row(symbol, str(details), "—", "—")
        switcher.current = "currency-table"

    def _render_gold(self, snap: EconomySnapshot) -> None:
        switcher = self.query_one("#gold-switcher", ContentSwitcher)
        if "gold" in snap.auth_sections:
            switcher.current = "gold-auth"
            return
        if snap.gold is None:
            switcher.current = "gold-loading"
            return
        if not snap.gold:
            switcher.current = "gold-empty"
            return

        table = self.query_one("#gold-table", DataTable)
        table.clear()
        for item in snap.gold:
            if isinstance(item, dict):
                name = item.get("Type", item.get("name", "—"))
                buying = str(item.get("Buying", item.get("buying", "—")))
                selling = str(item.get("Selling", item.get("selling", "—")))
                table.add_row(name, buying, selling)
        switcher.current = "gold-table"
