"""IZLEME LISTESI ekrani (WatchlistScreen) — docs/tui-design.md §2.2.

Layout:
- Ust bar: piyasa durumu (AÇIK/KAPALI/TATİL) + son guncelleme.
- Tablo: favori ticker'lari — Ticker / Fiyat / Δ% / Trend (mini sparkline).
  Satir sec + ``enter`` -> ``app.open_detail(ticker)`` (DetailScreen push).

Durumlar (ContentSwitcher): loading / auth (oturum yok veya suresi doldu) /
empty (``Favoriniz yok — fl portfolio favorite add THYAO``) / error /
table. Kismi hata toleransi: tek ticker'in fiyati cekilemezse o satir
'—' gosterir, tum liste dusmez (veri mantigi ``DataHub.fetch_watchlist``'te).

Veri mantigi YOKTUR: poll worker'i ``DataHub.fetch_watchlist`` sonucunu
``WatchlistDataUpdated`` mesajiyla tasir; bu ekran yalnizca sunum yapar.
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

from ..data import WatchlistSnapshot, delta_style, market_status_text, tr_delta, tr_number
from ..keys import KEY_OPEN_DETAIL
from ..widgets import period_return, spark_text, sparkline_color

__all__ = ["WatchlistDataFailed", "WatchlistDataUpdated", "WatchlistScreen"]


# ----------------------------------------------------------------------
# Poll worker -> ekran mesajlari
# ----------------------------------------------------------------------
class WatchlistDataUpdated(Message):
    """Basarili bir tick'in watchlist snapshot'i."""

    def __init__(self, snapshot: WatchlistSnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot


class WatchlistDataFailed(Message):
    """Tick toplam hata ile bitti (429 / network / beklenmeyen)."""

    def __init__(self, error: str, retry_after: float | None = None) -> None:
        super().__init__()
        self.error = error
        self.retry_after = retry_after


#: Trend sutunu genisligi (mini sparkline karakter sayisi).
SPARK_WIDTH = 12


class WatchlistScreen(Screen[None]):
    """IZLEME LISTESI: favoriler + canli fiyat + mini sparkline (tasarim §2.2)."""

    BINDINGS = [
        # priority=True: odakli DataTable 'enter' tusunu yutar — ekran
        # binding'i once calismali (Textual 8.2.8).
        Binding(KEY_OPEN_DETAIL, "open_detail", "Detay", priority=True),
    ]

    DEFAULT_CSS = """
    WatchlistScreen {
        background: $surface;
    }
    #watchlist-status {
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
    #watchlist-title {
        text-style: bold;
        padding: 1 1 0 1;
    }
    #watchlist-switcher {
        height: 1fr;
    }
    #watchlist-switcher > Static {
        padding: 1;
        color: $text 60%;
    }
    #watchlist-table {
        height: 1fr;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._last_snapshot: WatchlistSnapshot | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="watchlist-root"):
            yield Static("Piyasa durumu yükleniyor…", id="watchlist-status")
            yield Static("", id="banner")
            yield Static("İZLEME LİSTESİ (favoriler)", id="watchlist-title")
            table = DataTable(id="watchlist-table", cursor_type="row", zebra_stripes=True)
            table.add_columns("Ticker", "Fiyat", "Δ%", "Trend")
            yield ContentSwitcher(
                Static("Yükleniyor…", id="watchlist-loading"),
                Static("Oturum bulunamadı — 'fl auth login' ile giriş yapın", id="watchlist-auth"),
                Static(
                    "Favoriniz yok.\n"
                    "CLI'dan ekleyin: fl portfolio favorite add THYAO\n"
                    "Ekledikten sonra [b]r[/] ile yenileyin.",
                    id="watchlist-empty",
                ),
                Static("Veri alınamadı", id="watchlist-error"),
                table,
                initial="watchlist-loading",
                id="watchlist-switcher",
            )

    # ------------------------------------------------------------------
    # Yasam dongusu: ekrana donulunce aninda tick (tasarim §4.2).
    # ------------------------------------------------------------------
    def on_mount(self) -> None:
        poll_now = getattr(self.app, "poll_now", None)
        if callable(poll_now):
            poll_now()

    # ------------------------------------------------------------------
    # Mesaj handler'lari
    # ------------------------------------------------------------------
    def on_watchlist_data_updated(self, message: WatchlistDataUpdated) -> None:
        self._last_snapshot = message.snapshot
        snap = message.snapshot
        self._render_status(snap.market_status, snap.fetched_at)
        self._render_banner(snap)
        self._render_table(snap)

    def on_watchlist_data_failed(self, message: WatchlistDataFailed) -> None:
        if message.retry_after is not None:
            text = f"Rate limit — {message.retry_after:.0f}s sonra tekrar deneniyor"
        else:
            text = message.error
        self._show_banner(text)

    # ------------------------------------------------------------------
    # Tus eylemleri
    # ------------------------------------------------------------------
    def action_open_detail(self) -> None:
        """Seçili satirin ticker'i ile detay ekranini acar."""
        ticker = self._selected_ticker()
        if not ticker:
            return
        open_detail = getattr(self.app, "open_detail", None)
        if callable(open_detail):
            open_detail(ticker)

    # ------------------------------------------------------------------
    # Render yardimcilari
    # ------------------------------------------------------------------
    def _selected_ticker(self) -> str | None:
        table = self.query_one("#watchlist-table", DataTable)
        if table.cursor_row is None:
            return None
        try:
            row = list(table.get_row_at(table.cursor_row))
        except Exception:  # pragma: no cover — satir kaybolmus olabilir
            return None
        return str(row[0]) if row else None

    def _render_status(self, status: dict[str, Any] | None, fetched_at: datetime) -> None:
        bar = self.query_one("#watchlist-status", Static)
        bar.update(f"{market_status_text(status)}  ·  Son güncelleme: {fetched_at:%H:%M:%S}")

    def _render_table(self, snap: WatchlistSnapshot) -> None:
        switcher = self.query_one("#watchlist-switcher", ContentSwitcher)
        if "favorites" in snap.auth_sections:
            msg = snap.errors.get(
                "favorites", "Oturum bulunamadı — 'fl auth login' ile giriş yapın"
            )
            self.query_one("#watchlist-auth", Static).update(msg)
            switcher.current = "watchlist-auth"
            return
        if snap.favorites is None:
            switcher.current = "watchlist-error"
            return
        if not snap.favorites:
            switcher.current = "watchlist-empty"
            return
        table = self.query_one("#watchlist-table", DataTable)
        table.clear()
        for row in snap.rows:
            values = row.close_values
            spark = Text(
                spark_text(values, width=SPARK_WIDTH),
                style=sparkline_color(period_return(values)),
            )
            table.add_row(
                row.ticker,
                tr_number(row.price),
                Text(tr_delta(row.change_pct), style=delta_style(row.change_pct)),
                spark,
            )
        switcher.current = "watchlist-table"

    def _render_banner(self, snap: WatchlistSnapshot) -> None:
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
