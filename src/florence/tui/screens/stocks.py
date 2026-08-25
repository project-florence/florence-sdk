"""HİSSELER ekranı (StocksScreen) — BIST şirketleri ve sıralama sekmeleri.

Sıralama modları:
- ``p``: Popüler (popular)
- ``g``: Yükselenler (gainers)
- ``l``: Düşenler (losers)
- ``v``: Hacim (volume)
- ``m``: Piyasa Değeri (market_cap)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import ContentSwitcher, DataTable, Static

from ..data import (
    StocksSnapshot,
    delta_style,
    status_bar_text,
    tr_delta,
    tr_number,
)
from ..keys import KEY_GAINERS, KEY_LOSERS, KEY_OPEN_DETAIL, KEY_POPULAR
from ..widgets.nav import AppHeader

__all__ = ["StocksDataFailed", "StocksDataUpdated", "StocksScreen"]


class StocksDataUpdated(Message):
    def __init__(self, snapshot: StocksSnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot


class StocksDataFailed(Message):
    def __init__(self, error: str, retry_after: float | None = None) -> None:
        super().__init__()
        self.error = error
        self.retry_after = retry_after


class StocksScreen(Screen[None]):
    """BIST Hisseler listesi ve sıralama ekranı."""

    BINDINGS = [
        Binding(KEY_POPULAR, "set_sort('popular')", "Popüler"),
        Binding(KEY_GAINERS, "set_sort('gainers')", "Yükselenler"),
        Binding(KEY_LOSERS, "set_sort('losers')", "Düşenler"),
        Binding("v", "set_sort('volume')", "Hacim"),
        Binding("m", "set_sort('market_cap')", "Piyasa Değeri"),
        Binding("tab", "cycle_sort", "Sırala"),
        Binding(KEY_OPEN_DETAIL, "open_detail", "Detay", priority=True),
    ]

    DEFAULT_CSS = """
    StocksScreen {
        background: $surface;
    }
    #stocks-status {
        padding: 0 1;
        text-style: bold;
        background: $panel;
    }
    #stocks-sort-bar {
        padding: 0 1;
        text-style: bold;
        color: $accent;
    }
    #stocks-table-container {
        height: 1fr;
        padding: 0 1 1 1;
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

    SORT_MODES = ["popular", "gainers", "losers", "volume", "market_cap"]
    SORT_LABELS = {
        "popular": "Popüler",
        "gainers": "Yükselenler",
        "losers": "Düşenler",
        "volume": "Hacim",
        "market_cap": "Piyasa Değeri",
    }

    def __init__(self) -> None:
        super().__init__()
        self._sort = "popular"
        self._last_snapshot: StocksSnapshot | None = None

    @property
    def sort(self) -> str:
        return self._sort

    def compose(self) -> ComposeResult:
        with Vertical(id="stocks-root"):
            yield AppHeader(active="stocks")
            yield Static("Piyasa durumu yükleniyor…", id="stocks-status")
            yield Static("", id="banner")
            yield Static(self._sort_bar_text(), id="stocks-sort-bar")
            with ContentSwitcher(id="stocks-switcher", initial="stocks-loading"):
                yield Static("Yükleniyor…", id="stocks-loading")
                yield Static("Giriş yapın (fl auth login)", id="stocks-auth")
                yield Static("Veri yok", id="stocks-empty")
                table = DataTable(id="stocks-table", cursor_type="row", zebra_stripes=True)
                table.add_columns("Ticker", "Şirket Adı", "Fiyat", "Δ%", "Hacim", "Piyasa Değeri")
                yield table

    def on_mount(self) -> None:
        poll_now = getattr(self.app, "poll_now", None)
        if callable(poll_now):
            poll_now()

    def on_stocks_data_updated(self, message: StocksDataUpdated) -> None:
        self._last_snapshot = message.snapshot
        snap = message.snapshot
        self._render_status(snap.market_status, snap.fetched_at)
        self._render_table(snap)

    def on_stocks_data_failed(self, message: StocksDataFailed) -> None:
        banner = self.query_one("#banner", Static)
        if message.retry_after is not None:
            text = f"Rate limit — {message.retry_after:.0f}s sonra tekrar deneniyor"
        else:
            text = message.error
        banner.update(text)
        banner.add_class("visible")

    def action_set_sort(self, sort_name: str) -> None:
        if sort_name in self.SORT_MODES and sort_name != self._sort:
            self._sort = sort_name
            self.query_one("#stocks-sort-bar", Static).update(self._sort_bar_text())
            poll_now = getattr(self.app, "poll_now", None)
            if callable(poll_now):
                poll_now()

    def action_cycle_sort(self) -> None:
        idx = self.SORT_MODES.index(self._sort)
        next_sort = self.SORT_MODES[(idx + 1) % len(self.SORT_MODES)]
        self.action_set_sort(next_sort)

    def action_open_detail(self) -> None:
        table = self.query_one("#stocks-table", DataTable)
        if table.row_count == 0:
            return
        row = table.get_row_at(table.cursor_row)
        if row:
            ticker = str(row[0])
            open_detail = getattr(self.app, "open_detail", None)
            if callable(open_detail):
                open_detail(ticker)

    def _sort_bar_text(self) -> str:
        items = []
        for s in self.SORT_MODES:
            key_char = {"popular": "p", "gainers": "g", "losers": "l", "volume": "v", "market_cap": "m"}.get(s, s[0])
            label = self.SORT_LABELS[s]
            if s == self._sort:
                items.append(f"[reverse][b] [{key_char}] {label} [/b][/reverse]")
            else:
                items.append(f"[dim][{key_char}] {label}[/dim]")
        return "Sıralama: " + "   ".join(items)

    def _render_status(self, status: dict[str, Any] | None, fetched_at: datetime) -> None:
        bar = self.query_one("#stocks-status", Static)
        bar.update(status_bar_text(status, fetched_at))

    def _render_table(self, snap: StocksSnapshot) -> None:
        switcher = self.query_one("#stocks-switcher", ContentSwitcher)
        if "companies" in snap.auth_sections:
            switcher.current = "stocks-auth"
            return
        if snap.companies is None:
            switcher.current = "stocks-loading"
            return
        if not snap.companies:
            switcher.current = "stocks-empty"
            return

        table = self.query_one("#stocks-table", DataTable)
        table.clear()
        for company in snap.companies:
            ticker = str(company.get("ticker", "—"))
            name = str(company.get("name", "—"))
            last_price = company.get("last_price")
            price_str = tr_number(last_price) if last_price is not None else "—"

            ch = company.get("change_pct")
            delta_val = tr_delta(ch)
            delta_cell = Text(delta_val, style=delta_style(ch))

            vol = company.get("volume")
            vol_str = f"₺{vol:,.0f}" if isinstance(vol, (int, float)) else "—"

            mc = company.get("market_cap")
            mc_str = f"₺{mc:,.0f}" if isinstance(mc, (int, float)) else "—"

            table.add_row(ticker, name, price_str, delta_cell, vol_str, mc_str)

        switcher.current = "stocks-table"
