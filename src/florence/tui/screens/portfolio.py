"""PORTFÖY ekrani (PortfolioScreen) — Faz E (P7), docs/tui-design.md §2.4 v2 notu.

Layout (plan T-E2):
- Ust bar: piyasa durumu (AÇIK/KAPALI/TATİL) + son guncelleme.
- Portfoy secimi: ``list_portfolios()`` -> DataTable (satir sec + ``enter``);
  tek portfoy varsa otomatik secilir (``fetch_portfolio`` id verilmezse).
- Ozet satiri: toplam deger + donem getirisi (snapshot) — TR format.
- Grafik: ``history`` -> ccharts ``CChartLine``/``CChartCandle``; period
  ``1``/``3``/``6``/``y`` tuslari DETAY EKRANIYLA AYNI haritada (``keys.py``),
  ``c`` tusu cizgi/mum toggle (P6, detay davranisinin aynisi).
- Performers: ``performers(top_n=5)`` tablosu — Ticker / Getiri.

Veri akisi (plan): ``app.poll_now`` -> ``DataHub.fetch_portfolio(screen.portfolio_id,
period)`` -> ``PortfolioDataUpdated`` -> render. Auth yoksa hic portfoy
istegi atilmaz (``auth_sections`` icinde ``"portfolio"``) — ekran giris
oneri si gosterir. Portfoy yoksa CLI ile olusturma yonlendirmesi cikar.

Grafik veri beslemesi (T-E3): ``history`` OHLC iceriyorsa ``ohlc_rows``
birebir; degilse ``{ts, value}`` serisi ``portfolio_chart_rows`` ile
``{ts, open, close}`` sentezlenir (P2 — high/low sentezini adapter yapar:
``max/min(open, close)``). ``show_prices``/``show_times`` ccharts cizer.

Veri mantigi YOKTUR: poll worker'i ``DataHub.fetch_portfolio`` sonucunu
``PortfolioDataUpdated`` mesajiyla tasir; bu ekran yalnizca sunum yapar.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import ContentSwitcher, DataTable, Static

from .. import keys
from ..data import PortfolioSnapshot, delta_style, status_bar_text, tr_delta, tr_number
from ..keys import KEY_BACK, KEY_CHART_TOGGLE, KEY_OPEN_DETAIL, PERIODS
from ..widgets import CChartLine, NavBar

__all__ = [
    "PortfolioDataFailed",
    "PortfolioDataUpdated",
    "PortfolioScreen",
    "portfolio_chart_rows",
]


# ----------------------------------------------------------------------
# Poll worker -> ekran mesajlari
# ----------------------------------------------------------------------
class PortfolioDataUpdated(Message):
    """Basarili bir tick'in portfoy snapshot'i."""

    def __init__(self, snapshot: PortfolioSnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot


class PortfolioDataFailed(Message):
    """Tick toplam hata ile bitti (429 / network / beklenmeyen)."""

    def __init__(self, error: str, retry_after: float | None = None) -> None:
        super().__init__()
        self.error = error
        self.retry_after = retry_after


#: Deger serisinde denenebilecek alan adlari (mock sema: ``value``; canli
#: dogrulama olmadigindan toleransli — uydurma alan yok, P7 risk notu).
_VALUE_KEYS = ("value", "total_value", "balance", "price")


def portfolio_chart_rows(history: Any) -> list[dict[str, Any]]:
    """Portfoy ``history`` yanitini ccharts OHLC satirlarina hazirlar (T-E3).

    - OHLC anahtari (``open``/``close``) iceren satir varsa LISTE BIREBIR
      korunur (high/low sentezlenmez — P2 tercihi; adapter yine de
      eksik alanlari doldurur).
    - Degilse ``{ts, value}`` deger serisi sentezlenir: ``open`` = onceki
      kaydin ``close``'u (ilk kayitta kendi close'u — watchlist ``trend_cell``
      deseni), ``close`` = deger. ``ts`` korunur -> ``show_times`` dogru basar.
    - Gecersiz deger (None/bool/parse edilemeyen) satirlari ATILIR (ccharts
      null kabul etmez); bos girdi -> ``[]`` (ekran 'veri yok' gosterir).
    """
    rows = [r for r in history if isinstance(r, dict)] if isinstance(history, list) else []
    if any("open" in r or "close" in r for r in rows):
        return rows
    out: list[dict[str, Any]] = []
    prev: float | None = None
    for row in rows:
        raw = row.get("value", row.get("total_value", row.get("balance", row.get("price"))))
        if raw is None or isinstance(raw, bool):
            continue
        try:
            close = float(raw)
        except (TypeError, ValueError):
            continue
        entry: dict[str, Any] = {"open": close if prev is None else prev, "close": close}
        ts = row.get("ts", row.get("date"))
        if ts is not None:
            entry["ts"] = ts
        prev = close
        out.append(entry)
    return out


class PortfolioScreen(Screen[None]):
    """PORTFÖY: secim + ozet + grafik + performers (tasarim §2.4 v2)."""

    BINDINGS = [
        # Period tuslari detayla AYNI (keys.PERIODS: 1/3/6/y -> 1mo/3mo/6mo/1y).
        Binding("1", "set_period('1')", "1 Ay"),
        Binding("3", "set_period('3')", "3 Ay"),
        Binding("6", "set_period('6')", "6 Ay"),
        Binding("y", "set_period('y')", "1 Yıl"),
        Binding(KEY_CHART_TOGGLE, "toggle_chart", "Çizgi/Mum"),
        # priority=True: odakli DataTable 'enter' tusunu yutar — ekran
        # binding'i once calismali (watchlist deseni, Textual 8.2.8).
        Binding(KEY_OPEN_DETAIL, "select_portfolio", "Seç", priority=True),
        Binding(KEY_BACK, "go_back", "Geri"),
    ]

    DEFAULT_CSS = """
    PortfolioScreen {
        background: $surface;
    }
    #portfolio-status {
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
    #portfolio-title {
        text-style: bold;
        padding: 1 1 0 1;
    }
    #portfolio-switcher {
        height: 1fr;
    }
    #portfolio-switcher > Static {
        padding: 1;
        color: $text 60%;
    }
    #portfolio-content {
        height: 1fr;
    }
    #portfolio-select-label {
        padding: 1 1 0 1;
        text-style: bold;
    }
    #portfolio-table {
        height: 5;
        margin: 0 1;
    }
    #portfolio-summary {
        padding: 0 1;
        text-style: bold;
    }
    #portfolio-chart-title {
        padding: 1 1 0 1;
        text-style: bold;
    }
    #portfolio-chart {
        height: 10;
        padding: 0 1;
    }
    #performers-title {
        padding: 1 1 0 1;
        text-style: bold;
    }
    #performers-table {
        height: 6;
        margin: 0 1 1 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._portfolio_id: str | None = None
        self._period: str | None = None
        self._chart_type: str | None = None
        self._last_snapshot: PortfolioSnapshot | None = None

    # ------------------------------------------------------------------
    # Ekran state'i (app poll worker'i bu degerlerle fetch eder)
    # ------------------------------------------------------------------
    @property
    def portfolio_id(self) -> str | None:
        """Secili portfoy id'si (``None`` -> ekran secim bekler)."""
        return self._portfolio_id

    @property
    def period(self) -> str:
        """Aktif grafik period'u — app poll worker'i bu degerle fetch eder."""
        if self._period is None:
            default = getattr(getattr(self, "app", None), "default_period", None)
            self._period = default if default in keys.PERIOD_LABELS else keys.DEFAULT_PERIOD
        return self._period  # type: ignore[return-value]  # if dalinda atandi

    @property
    def chart_type(self) -> str:
        """Aktif grafik tipi (``line``/``candle``) — ``c`` ile toggle (P6)."""
        if self._chart_type is None:
            default = getattr(getattr(self, "app", None), "default_chart", None)
            self._chart_type = default if default in keys.CHART_LABELS else keys.DEFAULT_CHART
        return self._chart_type  # type: ignore[return-value]  # if dalinda atandi

    # ------------------------------------------------------------------
    # Yasam dongusu: ekrana donulunce aninda tick (tasarim §4.2).
    # ------------------------------------------------------------------
    def on_mount(self) -> None:
        poll_now = getattr(self.app, "poll_now", None)
        if callable(poll_now):
            poll_now()

    def compose(self) -> ComposeResult:
        table = DataTable(id="portfolio-table", cursor_type="row", zebra_stripes=True)
        table.add_columns("ID", "Ad", "Başlangıç")
        performers = DataTable(id="performers-table", cursor_type="row", zebra_stripes=True)
        performers.add_columns("Ticker", "Getiri")
        with Vertical(id="portfolio-root"):
            yield NavBar(active="portfolio")
            yield Static("Piyasa durumu yükleniyor…", id="portfolio-status")
            yield Static("", id="banner")
            yield Static("PORTFÖY", id="portfolio-title")
            yield ContentSwitcher(
                Static("Yükleniyor…", id="portfolio-loading"),
                Static("Oturum bulunamadı — 'fl auth login' ile giriş yapın", id="portfolio-auth"),
                Static(
                    "Portföyünüz yok.\n"
                    "CLI'dan oluşturun: fl portfolio create \"Benim Portföyüm\" 100000\n"
                    "Oluşturduktan sonra [b]r[/] ile yenileyin.",
                    id="portfolio-empty",
                ),
                Static("Veri alınamadı", id="portfolio-error"),
                Vertical(
                    Static("Portföy seçimi (enter ile aç)", id="portfolio-select-label"),
                    table,
                    Static("", id="portfolio-summary"),
                    Static("GRAFİK", id="portfolio-chart-title"),
                    # show_prices/show_times etiketlerini ccharts cizer (T-E3).
                    CChartLine(id="portfolio-chart", show_prices=True, show_times=True),
                    Static("ÖNE ÇIKAN POZİSYONLAR", id="performers-title"),
                    performers,
                    id="portfolio-content",
                ),
                initial="portfolio-loading",
                id="portfolio-switcher",
            )

    # ------------------------------------------------------------------
    # Mesaj handler'lari
    # ------------------------------------------------------------------
    def on_portfolio_data_updated(self, message: PortfolioDataUpdated) -> None:
        self._last_snapshot = message.snapshot
        snap = message.snapshot
        # Otomatik secim (tek portfoy) veya kullanici secimi senkronize edilir.
        if snap.portfolio_id is not None:
            self._portfolio_id = snap.portfolio_id
        self._render_status(snap.market_status, snap.fetched_at)
        self._render_banner(snap)
        self._render_snapshot(snap)

    def on_portfolio_data_failed(self, message: PortfolioDataFailed) -> None:
        if message.retry_after is not None:
            text = f"Rate limit — {message.retry_after:.0f}s sonra tekrar deneniyor"
        else:
            text = message.error
        self._show_banner(text)

    # ------------------------------------------------------------------
    # Tus eylemleri
    # ------------------------------------------------------------------
    def action_select_portfolio(self) -> None:
        """``enter`` — secili satirdaki portfoyu secer ve aninda yeniden ceker."""
        pid = self._selected_portfolio_id()
        if not pid:
            return
        self._portfolio_id = pid
        # Secim sonrasi ozet/grafik/performers gecikmeden gelsin (poll beklenmez).
        poll_now = getattr(self.app, "poll_now", None)
        if callable(poll_now):
            poll_now()

    def action_set_period(self, period_key: str) -> None:
        """``1``/``3``/``6``/``y`` -> 1mo/3mo/6mo/1y; aninda yeniden fetch."""
        period = PERIODS.get(period_key)
        if period is None or period == self._period:
            return
        self._period = period
        # Grafik once 'yukleniyor' durumuna gecer; veri gelince cizilir.
        self.query_one("#portfolio-chart", CChartLine).update_data(
            [], chart_type=self.chart_type
        )
        self.query_one("#portfolio-chart-title", Static).update(
            f"{self._chart_title()} — yükleniyor…"
        )
        poll_now = getattr(self.app, "poll_now", None)
        if callable(poll_now):
            poll_now()

    def action_toggle_chart(self) -> None:
        """``c`` — cizgi/mum arasi toggle (P6, detay davranisi).

        Period degismediginden veri yeniden istenmez: son snapshot'tan aninda
        yeniden cizilir (history cache'te — istek sayisi degismez).
        """
        self._chart_type = "candle" if self.chart_type == "line" else "line"
        if self._last_snapshot is not None and self._last_snapshot.history:
            self._render_chart(self._last_snapshot)
        else:
            self.query_one("#portfolio-chart-title", Static).update(self._chart_title())

    def action_go_back(self) -> None:
        """``esc`` — geldigi ekrana doner (portfoy PUSH DEGIL — switch).

        App ``action_go_portfolio`` geldigi EKRAN NESNESINI
        ``_screen_before_portfolio`` icinde saklar; bilinmiyorsa pano.
        """
        prev = getattr(self.app, "_screen_before_portfolio", None)
        target = prev if prev is not None else "dashboard"
        switch = getattr(self.app, "switch_screen", None)
        if callable(switch):
            switch(target)

    # ------------------------------------------------------------------
    # Render yardimcilari
    # ------------------------------------------------------------------
    def _chart_title(self) -> str:
        label = keys.PERIOD_LABELS.get(self.period, self.period)
        chart = keys.CHART_LABELS.get(self.chart_type, self.chart_type)
        return f"GRAFİK ({label} · {chart})"

    def _selected_portfolio_id(self) -> str | None:
        table = self.query_one("#portfolio-table", DataTable)
        if table.cursor_row is None:
            return None
        try:
            row = list(table.get_row_at(table.cursor_row))
        except Exception:  # pragma: no cover — satir kaybolmus olabilir
            return None
        return str(row[0]) if row else None

    def _render_status(self, status: dict[str, Any] | None, fetched_at: datetime) -> None:
        bar = self.query_one("#portfolio-status", Static)
        bar.update(status_bar_text(status, fetched_at))

    def _render_snapshot(self, snap: PortfolioSnapshot) -> None:
        switcher = self.query_one("#portfolio-switcher", ContentSwitcher)
        if "portfolio" in snap.auth_sections:
            msg = snap.errors.get(
                "portfolios", "Oturum bulunamadı — 'fl auth login' ile giriş yapın"
            )
            self.query_one("#portfolio-auth", Static).update(msg)
            switcher.current = "portfolio-auth"
            return
        if snap.summaries is None:
            switcher.current = "portfolio-error"
            return
        if not snap.summaries:
            switcher.current = "portfolio-empty"
            return
        self._render_selection(snap.summaries)
        self._render_summary(snap)
        self._render_chart(snap)
        self._render_performers(snap)
        switcher.current = "portfolio-content"

    def _render_selection(self, summaries: Sequence[Any]) -> None:
        table = self.query_one("#portfolio-table", DataTable)
        table.clear()
        for summary in summaries:
            pid = getattr(summary, "portfolio_id", "")
            balance = getattr(summary, "initial_balance", None)
            table.add_row(
                str(pid),
                str(getattr(summary, "name", pid)),
                tr_number(balance) if balance is not None else "—",
            )

    def _render_summary(self, snap: PortfolioSnapshot) -> None:
        summary = self.query_one("#portfolio-summary", Static)
        snap_data = snap.summary if isinstance(snap.summary, dict) else None
        if snap_data is None:
            if snap.portfolio_id is None:
                summary.update("[grey]Grafik ve özet için bir portföy seçin (enter)[/]")
            elif snap.errors.get("portfolio_snapshot"):
                summary.update("[grey]Özet alınamadı[/]")
            else:
                summary.update("[grey]Özet yükleniyor…[/]")
            return
        text = Text()
        text.append("Toplam: ", style="dim")
        text.append(tr_number(snap_data.get("total_value")))
        text.append("   Δ: ", style="dim")
        style = self._resolve_color(delta_style(snap_data.get("pnl_pct")))
        text.append(tr_delta(snap_data.get("pnl_pct")), style=style)
        summary.update(text)

    def _render_chart(self, snap: PortfolioSnapshot) -> None:
        chart = self.query_one("#portfolio-chart", CChartLine)
        title = self.query_one("#portfolio-chart-title", Static)
        base = self._chart_title()
        history = snap.history
        if snap.portfolio_id is None:
            chart.update_data([], chart_type=self.chart_type)
            title.update(f"{base} — portföy seçin (enter)")
            return
        if history is None:
            chart.update_data([], chart_type=self.chart_type)
            if snap.errors.get("portfolio_history"):
                title.update(f"{base} — veri alınamadı")
            else:
                title.update(f"{base} — yükleniyor…")
            return
        if not history:
            chart.update_data([], chart_type=self.chart_type)
            title.update(f"{base} — bu dönem için veri yok")
            return
        # OHLC varsa birebir; degilse value serisi sentezlenir (T-E3).
        rows = portfolio_chart_rows(history)
        chart.update_data(rows, chart_type=self.chart_type)
        title.update(base)

    def _render_performers(self, snap: PortfolioSnapshot) -> None:
        table = self.query_one("#performers-table", DataTable)
        table.clear()
        if snap.performers is None:
            if snap.errors.get("portfolio_performers"):
                self.query_one("#performers-title", Static).update(
                    "ÖNE ÇIKAN POZİSYONLAR — alınamadı"
                )
            else:
                self.query_one("#performers-title", Static).update(
                    "ÖNE ÇIKAN POZİSYONLAR — yükleniyor…"
                )
            return
        self.query_one("#performers-title", Static).update("ÖNE ÇIKAN POZİSYONLAR")
        for pos in snap.performers:
            table.add_row(
                pos.ticker,
                Text(tr_delta(pos.return_pct), style=delta_style(pos.return_pct)),
            )

    def _render_banner(self, snap: PortfolioSnapshot) -> None:
        if not snap.errors:
            self._hide_banner()
            return
        msg = next(iter(snap.errors.values()))
        last = getattr(self.app, "data", None)
        suffix = ""
        if last is not None and last.last_update is not None:
            suffix = f" — son veri gösteriliyor ({last.last_update:%H:%M})"
        self._show_banner(f"{msg}{suffix}")

    def _resolve_color(self, var: str) -> str:
        """``$success`` benzeri tema degiskenini hex renge cevirir (Static icin)."""
        if var.startswith("$"):
            value = self.app.theme_variables.get(var[1:])
            if value:
                return str(value)
        return var

    def _show_banner(self, text: str) -> None:
        banner = self.query_one("#banner", Static)
        banner.update(text)
        banner.add_class("visible")

    def _hide_banner(self) -> None:
        self.query_one("#banner", Static).remove_class("visible")