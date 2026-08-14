"""TICKER DETAY ekrani (DetailScreen) — docs/tui-design.md §2.3.

Layout:
- Ust bar: piyasa durumu + banner (hata/429).
- Bilgi satiri: ``company_info`` (longName + sektor) + ``current_price``
  (fiyat + Δ% — TR BIST renk kurali).
- Buyuk grafik: ``SparklineChart`` (price_history close serisi); period
  ``1``/``3``/``6``/``y`` tuslariyla 1mo/3mo/6mo/1y degisir. Period
  degisince ekran ``app.poll_now()`` ile aninda yeniden fetch eder
  (senkron client YASAK — her sey ``DataHub`` uzerinden).
- Haberler: ``news`` (JWT) — baslik listesi, tiklanamaz, duz metin.
  Oturum yoksa/suresi dolduysa giris onerisi gosterilir.
- Geri: ``esc`` -> ``pop_screen`` (geldigi ekrana doner).

Veri mantigi YOKTUR: poll worker'i ``DataHub.fetch_detail`` sonucunu
``DetailDataUpdated`` mesajiyla tasir; bu ekran yalnizca sunum yapar.
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
from textual.widgets import Static

from .. import keys
from ..data import DetailSnapshot, delta_style, market_status_text, tr_delta, tr_number
from ..keys import KEY_BACK
from ..widgets import SparklineChart

__all__ = ["DetailDataFailed", "DetailDataUpdated", "DetailScreen"]


# ----------------------------------------------------------------------
# Poll worker -> ekran mesajlari
# ----------------------------------------------------------------------
class DetailDataUpdated(Message):
    """Basarili bir tick'in detay snapshot'i."""

    def __init__(self, snapshot: DetailSnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot


class DetailDataFailed(Message):
    """Tick toplam hata ile bitti (429 / network / beklenmeyen)."""

    def __init__(self, error: str, retry_after: float | None = None) -> None:
        super().__init__()
        self.error = error
        self.retry_after = retry_after


#: company_info'da sektor icin denenebilecek alan adlari (openapi'ye
#: toleransli — uydurma alan yok, bulunamazsa sektor gosterilmez).
_SECTOR_KEYS = ("sector", "industry", "sectorName", "industryName", "sektor")


def company_sector(info: dict[str, Any] | None) -> str | None:
    """``company_info``'dan sektor alanini bulur; yoksa ``None``."""
    if not isinstance(info, dict):
        return None
    for key in _SECTOR_KEYS:
        value = info.get(key)
        if value:
            return str(value)
    return None


class DetailScreen(Screen[None]):
    """TICKER DETAY: bilgi + buyuk grafik + haberler (tasarim §2.3)."""

    BINDINGS = [
        Binding("1", "set_period('1')", "1 Ay"),
        Binding("3", "set_period('3')", "3 Ay"),
        Binding("6", "set_period('6')", "6 Ay"),
        Binding("y", "set_period('y')", "1 Yıl"),
        Binding(KEY_BACK, "go_back", "Geri"),
    ]

    DEFAULT_CSS = """
    DetailScreen {
        background: $surface;
    }
    #detail-status {
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
    #detail-info {
        padding: 1 1 0 1;
        height: auto;
    }
    #chart-title {
        padding: 1 1 0 1;
        text-style: bold;
    }
    #detail-chart {
        height: 14;
        padding: 0 1;
    }
    #detail-news {
        height: 1fr;
        padding: 0 1 1 1;
        color: $text 90%;
    }
    """

    def __init__(self, ticker: str, period: str | None = None) -> None:
        super().__init__()
        self.ticker = str(ticker).strip().upper()
        self._period: str = period if period in keys.PERIOD_LABELS else keys.DEFAULT_PERIOD
        self._last_snapshot: DetailSnapshot | None = None

    @property
    def period(self) -> str:
        """Aktif grafik period'u — app poll worker'i bu degerle fetch eder."""
        return self._period

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-root"):
            yield Static("Piyasa durumu yükleniyor…", id="detail-status")
            yield Static("", id="banner")
            yield Static("Yükleniyor…", id="detail-info")
            yield Static(self._chart_title(), id="chart-title")
            yield SparklineChart(id="detail-chart")
            yield Static("Yükleniyor…", id="detail-news")

    # ------------------------------------------------------------------
    # Yasam dongusu: acilinca aninda tick (tasarim §4.2 aktif ekran kurali).
    # ------------------------------------------------------------------
    def on_mount(self) -> None:
        poll_now = getattr(self.app, "poll_now", None)
        if callable(poll_now):
            poll_now()

    # ------------------------------------------------------------------
    # Mesaj handler'lari
    # ------------------------------------------------------------------
    def on_detail_data_updated(self, message: DetailDataUpdated) -> None:
        self._last_snapshot = message.snapshot
        snap = message.snapshot
        self._render_status(snap.market_status, snap.fetched_at)
        self._render_banner(snap)
        self._render_info(snap)
        self._render_chart(snap)
        self._render_news(snap)

    def on_detail_data_failed(self, message: DetailDataFailed) -> None:
        if message.retry_after is not None:
            text = f"Rate limit — {message.retry_after:.0f}s sonra tekrar deneniyor"
        else:
            text = message.error
        self._show_banner(text)

    # ------------------------------------------------------------------
    # Tus eylemleri
    # ------------------------------------------------------------------
    def action_set_period(self, period_key: str) -> None:
        """``1``/``3``/``6``/``y`` -> 1mo/3mo/6mo/1y; aninda yeniden fetch.

        Poll interval'i beklenmez — ``app.poll_now()`` exclusive worker ile
        yeni period'da detay ceker (tasarim §5.4).
        """
        period = keys.PERIODS.get(period_key)
        if period is None or period == self._period:
            return
        self._period = period
        # Grafik once 'yukleniyor' durumuna gecer; veri gelince cizilir.
        self.query_one("#detail-chart", SparklineChart).update_data([])
        self.query_one("#chart-title", Static).update(
            f"{self._chart_title()} — yükleniyor…"
        )
        poll_now = getattr(self.app, "poll_now", None)
        if callable(poll_now):
            poll_now()

    def action_go_back(self) -> None:
        """``esc`` — geldigi ekrana don (pano veya watchlist)."""
        self.app.pop_screen()

    # ------------------------------------------------------------------
    # Render yardimcilari
    # ------------------------------------------------------------------
    def _chart_title(self) -> str:
        label = keys.PERIOD_LABELS.get(self._period, self._period)
        return f"ÇİZGİ GRAFİK ({label})"

    def _render_status(self, status: dict[str, Any] | None, fetched_at: datetime) -> None:
        bar = self.query_one("#detail-status", Static)
        bar.update(f"{market_status_text(status)}  ·  Son güncelleme: {fetched_at:%H:%M:%S}")

    def _render_info(self, snap: DetailSnapshot) -> None:
        info = self.query_one("#detail-info", Static)
        if snap.company_info is None and snap.current_price is None:
            info.update("[grey]Şirket bilgisi alınamadı[/]")
            return
        text = Text()
        text.append(self.ticker, style="bold")
        if isinstance(snap.company_info, dict):
            name = snap.company_info.get("longName") or snap.company_info.get("name")
            if name:
                text.append(f" — {name}")
            sector = company_sector(snap.company_info)
            if sector:
                text.append(f" ({sector})", style="dim")
        quote = snap.current_price if isinstance(snap.current_price, dict) else None
        if quote is not None and quote.get("price") is not None:
            text.append("\nFiyat: ", style="dim")
            text.append(tr_number(quote.get("price")))
            text.append("   Δ: ", style="dim")
            # Static icerigi theme degiskenini cikti olarak cozer (DataTable
            # hucresinden farkli olarak Rich stil adi bekler).
            delta_style_value = self._resolve_color(delta_style(quote.get("change_pct")))
            text.append(tr_delta(quote.get("change_pct")), style=delta_style_value)
        else:
            text.append("\nFiyat: ", style="dim")
            text.append("—")
        info.update(text)

    def _resolve_color(self, var: str) -> str:
        """``$success`` benzeri tema degiskenini hex renge cevirir (Static icin)."""
        if var.startswith("$"):
            value = self.app.theme_variables.get(var[1:])
            if value:
                return str(value)
        return var

    def _render_chart(self, snap: DetailSnapshot) -> None:
        chart = self.query_one("#detail-chart", SparklineChart)
        title = self.query_one("#chart-title", Static)
        base = self._chart_title()
        history = snap.price_history
        if history is None:
            chart.update_data([])
            if snap.errors.get("price_history"):
                title.update(f"{base} — veri alınamadı")
            else:
                title.update(f"{base} — yükleniyor…")
            return
        if not history:
            chart.update_data([])
            title.update(f"{base} — bu dönem için veri yok")
            return
        closes: list[float | None] = [
            item.get("close") for item in history if isinstance(item, dict)
        ]
        chart.update_data(closes)
        values = [float(v) for v in closes if v is not None]
        if values:
            title.update(
                f"{base} — en yüksek {tr_number(max(values))} · "
                f"son {tr_number(values[-1])} · en düşük {tr_number(min(values))}"
            )
        else:
            title.update(base)

    def _render_news(self, snap: DetailSnapshot) -> None:
        news = self.query_one("#detail-news", Static)
        if "news" in snap.auth_sections:
            news.update("[grey]Haberler için giriş yapın: fl auth login[/]")
            return
        if snap.news is None:
            news.update(
                "[grey]Haberler alınamadı[/]"
                if snap.errors.get("news")
                else "[grey]Haberler yükleniyor…[/]"
            )
            return
        if not snap.news:
            news.update("[grey]Haber yok[/]")
            return
        lines: list[str] = []
        for item in snap.news:
            if not isinstance(item, dict):
                continue
            headline = item.get("title") or item.get("headline") or ""
            url = item.get("url", "")
            if headline:
                suffix = f"  [dim]{url}[/dim]" if url else ""
                lines.append(f"• {headline}{suffix}")
        news.update("\n".join(lines) if lines else "[grey]Haber yok[/]")

    def _render_banner(self, snap: DetailSnapshot) -> None:
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
