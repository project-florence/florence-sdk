"""TICKER DETAY ekrani (DetailScreen) — docs/tui-design.md §2.3 (v2: ccharts).

Layout:
- Ust bar: piyasa durumu + banner (hata/429).
- Fiyat & Kimlik Karti: ``company_info`` (longName + sektor) + ``current_price``
  (fiyat + Δ% — TR BIST renk kurali).
- Gun Ici & OHLC Istatistikleri Karti: acilis, en yuksek, en dusuk, onceki kapanis, hacim, 52H y/d.
- Buyuk grafik: ``CChartLine``/``CChartCandle`` (ccharts, plan v2 K2) —
  ``price_history`` OHLC satirlari; period ``1``/``3``/``6``/``y`` tuslari veya
  tiklanabilir butonlarla 1mo/3mo/6mo/1y degisir, ``c`` tusu veya butonlarla
  cizgi/mum arasi toggle (P6).
  ``show_prices``/``show_times`` ccharts tarafindan cizilir.
- Haberler & Sirket Profili Karti: ``news`` (JWT) + profil ozeti.
- Geri: ``esc`` -> ``pop_screen`` (geldigi ekrana doner).
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
from textual.widgets import Button, Static

from .. import keys
from ..data import DetailSnapshot, delta_style, status_bar_text, tr_delta, tr_number
from ..keys import KEY_BACK, KEY_CHART_TOGGLE
from ..widgets import CChartLine

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
    """TICKER DETAY: bilgi + ohlc istatistikleri + grafik + haberler."""

    BINDINGS = [
        Binding("1", "set_period('1')", "1 Ay", priority=True),
        Binding("3", "set_period('3')", "3 Ay", priority=True),
        Binding("6", "set_period('6')", "6 Ay", priority=True),
        Binding("y", "set_period('y')", "1 Yıl", priority=True),
        Binding(KEY_CHART_TOGGLE, "toggle_chart", "Çizgi/Mum", priority=True),
        Binding(KEY_BACK, "go_back", "Geri", priority=True),
    ]

    DEFAULT_CSS = """
    DetailScreen {
        background: $surface;
        overflow-y: auto;
    }
    #detail-status {
        padding: 0 1;
        text-style: bold;
        background: $panel;
        border-bottom: solid $primary 40%;
        height: 1;
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
    .detail-row {
        height: auto;
        margin: 1 1 0 1;
        padding: 0;
    }
    .detail-card {
        border: round $primary 40%;
        background: $panel 30%;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    #card-identity {
        width: 1fr;
        height: auto;
        min-height: 5;
        margin-right: 1;
    }
    #card-stats {
        width: 1fr;
        height: auto;
        min-height: 5;
    }
    #card-chart {
        height: auto;
        min-height: 15;
        margin: 1 1 0 1;
    }
    #card-news {
        height: 1fr;
        min-height: 7;
        margin: 1 1 1 1;
    }
    .card-header {
        text-style: bold;
        color: $accent;
        padding: 0;
        margin-bottom: 0;
    }
    #detail-info {
        height: auto;
        padding: 0;
    }
    #detail-stats {
        height: auto;
        padding: 0;
    }
    #chart-header-row {
        height: 1;
        width: 100%;
        margin-bottom: 0;
    }
    #chart-title {
        text-style: bold;
        color: $accent;
        width: 32;
        height: 1;
    }
    Button.chart-btn {
        height: 1;
        border: none;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
        margin-right: 1;
    }
    #btn-period-1mo, #btn-period-3mo, #btn-period-6mo, #btn-period-1y {
        width: 6;
        min-width: 6;
    }
    #btn-type-line, #btn-type-candle {
        width: 12;
        min-width: 10;
    }
    Button.chart-btn:hover {
        background: $primary 30%;
        color: $text;
    }
    Button.chart-btn.btn-active {
        background: $primary;
        color: $text;
        text-style: bold;
    }
    .btn-separator {
        width: 3;
        color: $primary 40%;
        text-align: center;
    }
    #detail-chart {
        height: 12;
        padding: 0;
    }
    #detail-profile {
        height: auto;
        color: $text-muted;
        margin-bottom: 0;
    }
    #detail-news {
        height: 1fr;
        color: $text 90%;
    }
    """

    def __init__(
        self, ticker: str, period: str | None = None, chart_type: str | None = None
    ) -> None:
        super().__init__()
        self.ticker = str(ticker).strip().upper()
        self._period: str = period if period in keys.PERIOD_LABELS else keys.DEFAULT_PERIOD
        # P6: baslangic tipi config'ten (``tui_default_chart``) gelir; ``c``
        # tusu ekran ici toggle eder.
        self._chart_type: str = chart_type if chart_type in keys.CHART_LABELS else keys.DEFAULT_CHART
        self._last_snapshot: DetailSnapshot | None = None

    @property
    def period(self) -> str:
        """Aktif grafik period'u — app poll worker'i bu degerle fetch eder."""
        return self._period

    @property
    def chart_type(self) -> str:
        """Aktif grafik tipi (``line``/``candle``) — ``c`` ile toggle (P6)."""
        return self._chart_type

    def compose(self) -> ComposeResult:
        header_text = (
            f"[b]← [Esc] Geri[/b]  │  "
            f"[bold cyan]{self.ticker}[/bold cyan] Detay  │  "
            f"Piyasa durumu yükleniyor…"
        )
        with Vertical(id="detail-root"):
            yield Static(header_text, id="detail-status")
            yield Static("", id="banner")

            # 1. Satır: Fiyat & Kimlik Kartı + Gün İçi & OHLC İstatistikleri Kartı
            with Horizontal(id="detail-summary-row", classes="detail-row"):
                with Vertical(id="card-identity", classes="detail-card"):
                    yield Static("🏢 FİYAT & KİMLİK", classes="card-header")
                    yield Static("Yükleniyor…", id="detail-info")
                with Vertical(id="card-stats", classes="detail-card"):
                    yield Static("📊 GÜN İÇİ & OHLC İSTATİSTİKLERİ", classes="card-header")
                    yield Static("Yükleniyor…", id="detail-stats")

            # 2. Satır: İnteraktif Grafik Kartı
            with Vertical(id="card-chart", classes="detail-card"):
                with Horizontal(id="chart-header-row"):
                    yield Static(self._chart_title_text(), id="chart-title")
                    yield Button("1A", id="btn-period-1mo", classes="chart-btn")
                    yield Button("3A", id="btn-period-3mo", classes="chart-btn")
                    yield Button("6A", id="btn-period-6mo", classes="chart-btn")
                    yield Button("1Y", id="btn-period-1y", classes="chart-btn")
                    yield Static("│", classes="btn-separator")
                    yield Button("📈 Çizgi", id="btn-type-line", classes="chart-btn")
                    yield Button("🕯️ Mum", id="btn-type-candle", classes="chart-btn")
                yield CChartLine(id="detail-chart", show_prices=True, show_times=True)

            # 3. Satır: Haberler & Şirket Profili Kartı
            with Vertical(id="card-news", classes="detail-card"):
                yield Static("📰 HABERLER & ŞİRKET PROFİLİ", classes="card-header")
                yield Static("", id="detail-profile")
                yield Static("Yükleniyor…", id="detail-news")

    # ------------------------------------------------------------------
    # Yasam dongusu: acilinca aninda tick (tasarim §4.2 aktif ekran kurali).
    # ------------------------------------------------------------------
    def on_mount(self) -> None:
        self._update_button_states()
        poll_now = getattr(self.app, "poll_now", None)
        if callable(poll_now):
            poll_now()

    # ------------------------------------------------------------------
    # Mesaj handler'lari
    # ------------------------------------------------------------------
    def on_detail_data_updated(self, message: DetailDataUpdated) -> None:
        self._last_snapshot = message.snapshot
        snap = message.snapshot
        self._render_header(snap.market_status, snap.fetched_at)
        self._render_banner(snap)
        self._render_info(snap)
        self._render_stats(snap)
        self._render_chart(snap)
        self._render_news(snap)
        self._update_button_states()

    def on_detail_data_failed(self, message: DetailDataFailed) -> None:
        if message.retry_after is not None:
            text = f"Rate limit — {message.retry_after:.0f}s sonra tekrar deneniyor"
        else:
            text = message.error
        self._show_banner(text)

    # ------------------------------------------------------------------
    # Buton handler'i
    # ------------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("btn-period-"):
            p_val = btn_id.replace("btn-period-", "")
            rev_map = {"1mo": "1", "3mo": "3", "6mo": "6", "1y": "y"}
            p_key = rev_map.get(p_val, p_val)
            self.action_set_period(p_key)
        elif btn_id == "btn-type-line":
            self.set_chart_type("line")
        elif btn_id == "btn-type-candle":
            self.set_chart_type("candle")

    # ------------------------------------------------------------------
    # Tus eylemleri & Grafik Secimleri
    # ------------------------------------------------------------------
    def action_set_period(self, period_key: str) -> None:
        """``1``/``3``/``6``/``y`` -> 1mo/3mo/6mo/1y; aninda yeniden fetch."""
        period = keys.PERIODS.get(period_key)
        if period is None or period == self._period:
            return
        self._period = period
        self._update_button_states()
        # Grafik once 'yukleniyor' durumuna gecer; veri gelince cizilir.
        self.query_one("#detail-chart", CChartLine).update_data([], chart_type=self._chart_type)
        self.query_one("#chart-title", Static).update(
            f"{self._chart_title()} — [dim]yükleniyor…[/dim]"
        )
        poll_now = getattr(self.app, "poll_now", None)
        if callable(poll_now):
            poll_now()

    def set_chart_type(self, chart_type: str) -> None:
        """Grafik tipini degistirir (line/candle) ve aninda yeniden cizer."""
        if chart_type in ("line", "candle") and chart_type != self._chart_type:
            self._chart_type = chart_type
            self._update_button_states()
            if self._last_snapshot is not None:
                self._render_chart(self._last_snapshot)
            else:
                self.query_one("#chart-title", Static).update(self._chart_title_text())

    def action_toggle_chart(self) -> None:
        """``c`` — cizgi/mum arasi toggle (P6)."""
        next_type = "candle" if self._chart_type == "line" else "line"
        self.set_chart_type(next_type)

    def action_go_back(self) -> None:
        """``esc`` — geldigi ekrana don (pano veya watchlist)."""
        self.app.pop_screen()

    # ------------------------------------------------------------------
    # Render yardimcilari
    # ------------------------------------------------------------------
    def _update_button_states(self) -> None:
        """Dönem ve grafik türü butonlarının aktiflik durumunu günceller."""
        try:
            for p_val in ["1mo", "3mo", "6mo", "1y"]:
                btn = self.query_one(f"#btn-period-{p_val}", Button)
                if self._period == p_val:
                    btn.add_class("btn-active")
                else:
                    btn.remove_class("btn-active")

            btn_line = self.query_one("#btn-type-line", Button)
            btn_candle = self.query_one("#btn-type-candle", Button)
            if self._chart_type == "line":
                btn_line.add_class("btn-active")
                btn_candle.remove_class("btn-active")
            else:
                btn_candle.add_class("btn-active")
                btn_line.remove_class("btn-active")
        except Exception:
            pass

    def _chart_title(self) -> str:
        label = keys.PERIOD_LABELS.get(self._period, self._period)
        chart = keys.CHART_LABELS.get(self._chart_type, self._chart_type)
        return f"GRAFİK ({label} · {chart})"

    def _chart_title_text(self) -> str:
        return self._chart_title()

    def _render_header(self, status: dict[str, Any] | None, fetched_at: datetime) -> None:
        bar = self.query_one("#detail-status", Static)
        status_txt = status_bar_text(status, fetched_at)
        bar.update(f"[b]← [Esc] Geri[/b]  │  [bold cyan]{self.ticker}[/bold cyan] Detay  │  {status_txt}")

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
            text.append(tr_number(quote.get("price")), style="bold")
            text.append(" ₺", style="bold")
            text.append("   Δ: ", style="dim")
            # Static icerigi theme degiskenini cikti olarak cozer (DataTable
            # hucresinden farkli olarak Rich stil adi bekler).
            delta_style_value = self._resolve_color(delta_style(quote.get("change_pct")))
            ch_val = quote.get("change")
            ch_pct = quote.get("change_pct")
            delta_pct_str = tr_delta(ch_pct)
            if ch_val is not None:
                sign = "+" if ch_val > 0 else ("-" if ch_val < 0 else "")
                val_str = f"{sign}{tr_number(abs(ch_val))} ₺"
                text.append(f"{val_str} ({delta_pct_str})", style=delta_style_value)
            else:
                text.append(delta_pct_str, style=delta_style_value)
        else:
            text.append("\nFiyat: ", style="dim")
            text.append("—")
        info.update(text)

    def _render_stats(self, snap: DetailSnapshot) -> None:
        stats_widget = self.query_one("#detail-stats", Static)
        quote = snap.current_price if isinstance(snap.current_price, dict) else {}
        history = (
            snap.price_history
            if isinstance(snap.price_history, list) and snap.price_history
            else []
        )
        info = snap.company_info if isinstance(snap.company_info, dict) else {}

        last_bar = history[-1] if history else {}
        prev_bar = history[-2] if len(history) >= 2 else {}

        open_val = quote.get("open") or quote.get("day_open") or last_bar.get("open")
        high_val = quote.get("high") or quote.get("day_high") or last_bar.get("high")
        low_val = quote.get("low") or quote.get("day_low") or last_bar.get("low")
        prev_close = (
            quote.get("previous_close")
            or quote.get("prev_close")
            or prev_bar.get("close")
        )
        volume = quote.get("volume") or quote.get("day_volume") or last_bar.get("volume")

        h52 = (
            info.get("fiftyTwoWeekHigh")
            or info.get("fifty_two_week_high")
            or info.get("52w_high")
            or quote.get("fiftyTwoWeekHigh")
        )
        l52 = (
            info.get("fiftyTwoWeekLow")
            or info.get("fifty_two_week_low")
            or info.get("52w_low")
            or quote.get("fiftyTwoWeekLow")
        )

        open_str = f"{tr_number(open_val)} ₺" if open_val is not None else "—"
        high_str = f"{tr_number(high_val)} ₺" if high_val is not None else "—"
        low_str = f"{tr_number(low_val)} ₺" if low_val is not None else "—"
        prev_str = f"{tr_number(prev_close)} ₺" if prev_close is not None else "—"

        if isinstance(volume, (int, float)) and volume > 0:
            if volume >= 1_000_000_000:
                vol_str = f"₺{volume / 1_000_000_000:.2f} Mr"
            elif volume >= 1_000_000:
                vol_str = f"₺{volume / 1_000_000:.2f} Mn"
            elif volume >= 1_000:
                vol_str = f"₺{volume / 1_000:.1f} B"
            else:
                vol_str = f"₺{volume:,.0f}"
        else:
            vol_str = "—"

        if h52 is not None and l52 is not None:
            range_52 = f"{tr_number(l52)} - {tr_number(h52)} ₺"
        elif h52 is not None:
            range_52 = f"Yük: {tr_number(h52)} ₺"
        elif l52 is not None:
            range_52 = f"Düş: {tr_number(l52)} ₺"
        else:
            range_52 = "—"

        lines = [
            f"[dim]Açılış:[/] [bold]{open_str}[/]  │  [dim]En Yüksek:[/] [bold]{high_str}[/]",
            f"[dim]En Düşük:[/] [bold]{low_str}[/]  │  [dim]Önc. Kapanış:[/] [bold]{prev_str}[/]",
            f"[dim]Hacim:[/] [bold]{vol_str}[/]  │  [dim]52H Y/D:[/] [bold]{range_52}[/]",
        ]
        stats_widget.update("\n".join(lines))

    def _resolve_color(self, var: str) -> str:
        """``$success`` benzeri tema degiskenini hex renge cevirir (Static icin)."""
        if var.startswith("$"):
            value = self.app.theme_variables.get(var[1:])
            if value:
                return str(value)
        return var

    def _render_chart(self, snap: DetailSnapshot) -> None:
        chart = self.query_one("#detail-chart", CChartLine)
        title = self.query_one("#chart-title", Static)
        base = self._chart_title()
        history = snap.price_history
        if history is None:
            chart.update_data([], chart_type=self._chart_type)
            if snap.errors.get("price_history"):
                title.update(f"{base} — [red]veri alınamadı[/red]")
            else:
                title.update(f"{base} — [dim]yükleniyor…[/dim]")
            return
        if not history:
            chart.update_data([], chart_type=self._chart_type)
            title.update(f"{base} — [dim]bu dönem için veri yok[/dim]")
            return
        chart.update_data(history, chart_type=self._chart_type)
        title.update(base)

    def _render_news(self, snap: DetailSnapshot) -> None:
        profile = self.query_one("#detail-profile", Static)
        if isinstance(snap.company_info, dict):
            desc = (
                snap.company_info.get("summary")
                or snap.company_info.get("description")
                or snap.company_info.get("longBusinessSummary")
                or snap.company_info.get("businessSummary")
                or snap.company_info.get("ozet")
                or ""
            )
            if desc:
                short_desc = desc[:200] + "…" if len(desc) > 200 else desc
                profile.update(f"[dim]{short_desc}[/dim]\n")
                profile.display = True
            else:
                profile.update("")
                profile.display = False
        else:
            profile.update("")
            profile.display = False

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
