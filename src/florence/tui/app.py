"""FlorenceTUI — ``fl tui`` Textual uygulamasi (docs/tui-design.md).

Sorumluluklar:
- Client yasam dongusu: ``AsyncFlorenceClient`` on_mount'ta kurulur (default
  token store — CLI'nin ``fl auth login`` oturumu otomatik okunur),
  on_unmount'ta kapatilir. SENKRON CLIENT KULLANILMAZ (event loop'u bloklar).
- Polling: ``set_interval`` -> ``run_worker(group="poll", exclusive=True)`` —
  onceki worker surerken yeni tick atlanir (overlap korumasi). Her tick
  sonrasi ``DataHub.next_poll_delay()`` ile bir sonraki gecikme yeniden
  kurulur (429 uzatmasi / K4 kapali piyasa planlamasi).
- Ilk istek her zaman yapilir (K4): mount sonrasi ``call_after_refresh`` ile
  aninda tick baslar.
- Auth yoksa pano yine calisir: ``market/status`` public; auth-gerektiren
  bolumler (stats_top/companies_summary/economy) icin DataHub bolumleri
  atlar, ekran 'Giris yapin (fl auth login)' uyarisi gosterir.
"""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Footer, Header, Static
from textual.worker import Worker

from .. import __version__
from ..cli.config_cli import CliConfig
from ..client import AsyncFlorenceClient
from ..errors import FlorenceError, RateLimitError
from . import keys
from .data import DataHub, error_message
from .screens.dashboard import DashboardDataFailed, DashboardDataUpdated, DashboardScreen
from .screens.detail import DetailDataFailed, DetailDataUpdated, DetailScreen
from .screens.watchlist import WatchlistDataFailed, WatchlistDataUpdated, WatchlistScreen

__all__ = ["FlorenceTUI", "HelpModal", "main"]


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    """Config degerini [lo, hi] araligina clamp eder; gecersizse default."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _valid_period(value: Any) -> str:
    """Gecerli bir period degilse varsayilana doner."""
    if value in keys.PERIOD_LABELS:
        return str(value)
    return keys.DEFAULT_PERIOD


def _valid_chart(value: Any) -> str:
    """Gecerli bir grafik tipi (line|candle) degilse varsayilana doner (P6)."""
    if value in keys.CHART_LABELS:
        return str(value)
    return keys.DEFAULT_CHART



class HelpModal(ModalScreen[None]):
    """Yardim paneli: tus haritasi + surum (offline, veri istegi yok)."""

    BINDINGS = [
        Binding("escape", "dismiss_help", "Kapat"),
        Binding("q", "dismiss_help", "Kapat"),
        Binding("h", "dismiss_help", "Kapat"),
    ]

    DEFAULT_CSS = """
    HelpModal {
        align: center middle;
    }
    #help-box {
        width: 62;
        height: auto;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        lines = [
            "[b]fl tui — tuş haritası[/]",
            "",
            "[b]q[/] Çıkış      [b]1[/] Pano      [b]2[/] İzleme listesi",
            "[b]r[/] Yenile     [b]h[/] Bu yardım",
            "[b]j[/]/[b]k[/] Satır  [b]enter[/] Detay  [b]g[/]/[b]l[/] Yükselen/Düşen",
            "[b]1[/]/[b]3[/]/[b]6[/]/[b]y[/] Grafik dönemi (detay)",
            "[b]c[/] Çizgi/Mum (detay)          [b]esc[/] Geri",
            "",
            f"Sürüm: {__version__}",
            f"API: {self.app.data.base_url}",  # type: ignore[attr-defined]
        ]
        yield Vertical(Static("\n".join(lines)), id="help-box")

    def action_dismiss_help(self) -> None:
        self.dismiss(None)


class FlorenceTUI(App[None]):
    """``fl tui`` uygulamasi (pano + izleme listesi + detay/grafik)."""

    TITLE = "Florence · fl tui"
    SUB_TITLE = "BIST canlı özet"

    CSS = """
    Screen {
        background: $surface;
    }
    """

    BINDINGS = [
        Binding(keys.KEY_QUIT, "quit", "Çıkış"),
        Binding(keys.KEY_DASHBOARD, "go_dashboard", "Pano"),
        Binding(keys.KEY_WATCHLIST, "go_watchlist", "İzleme", show=False),
        Binding(keys.KEY_REFRESH, "refresh", "Yenile"),
        Binding(keys.KEY_HELP, "help", "Yardım"),
    ]

    #: Ekran kaydi — watchlist switch ile acilir; detay push ile (K3).
    SCREENS = {"dashboard": DashboardScreen, "watchlist": WatchlistScreen}

    def __init__(
        self,
        *,
        client: AsyncFlorenceClient | None = None,
        config: CliConfig | None = None,
        refresh_seconds: float | None = None,
        default_period: str | None = None,
        default_chart: str | None = None,
        market_closed_refresh: float | None = None,
        ttl_overrides: dict[str, float] | None = None,
    ) -> None:
        super().__init__()
        cfg = config if config is not None else CliConfig()
        # Config yoksa/gecersizse varsayilanlar (10-600 araligi, disi clamp).
        self.refresh_seconds: float = (
            refresh_seconds
            if refresh_seconds is not None
            else float(_clamp_int(cfg.get("tui_refresh_seconds"), 10, 600, 45))
        )
        self.default_period: str = (
            default_period
            if default_period is not None
            else _valid_period(cfg.get("tui_default_period"))
        )
        self.default_chart: str = (
            default_chart
            if default_chart is not None
            else _valid_chart(cfg.get("tui_default_chart"))
        )
        closed: float = (
            market_closed_refresh
            if market_closed_refresh is not None
            else float(_clamp_int(cfg.get("tui_market_closed_refresh"), 60, 3600, 300))
        )
        self.data = DataHub(
            client=client if client is not None else AsyncFlorenceClient(),
            refresh_seconds=self.refresh_seconds,
            market_closed_refresh=closed,
            # DataHub limitleri config'ten (keşif #6): anahtar VARSA okunur,
            # yoksa/gecersizse DataHub varsayilani (10).
            top_limit=_clamp_int(cfg.get("tui_top_limit"), 1, 50, 10),
            summary_limit=_clamp_int(cfg.get("tui_summary_limit"), 1, 50, 10),
            ttl_overrides=ttl_overrides,
        )
        self._poll_timer: Timer | None = None
        self._poll_worker: Worker[Any] | None = None

    # ------------------------------------------------------------------
    # Yasam dongusu
    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen("dashboard")
        self._poll_timer = self.set_interval(
            self.data.next_poll_delay(), self._on_poll_tick
        )
        # ILK istek her zaman yapilir (K4): ekran mount olunca aninda tick.
        self.call_after_refresh(self._on_poll_tick)

    async def on_unmount(self) -> None:
        await self.data.close()

    # ------------------------------------------------------------------
    # Polling: interval -> exclusive worker
    # ------------------------------------------------------------------
    def _on_poll_tick(self) -> None:
        self.poll_now()

    def poll_now(self) -> Worker[Any]:
        """Manuel yenileme / tick: exclusive poll worker baslatir.

        ``exclusive=True`` oldugundan surmakte olan bir poll varsa yeni istek
        baslamaz — mevcut worker doner (overlap korumasi, tasarim §4.1/§4.3).
        """
        if self._poll_worker is not None and self._poll_worker.is_running:
            self.notify("Yenileme zaten sürüyor…")
            return self._poll_worker
        self._poll_worker = self.run_worker(
            self._poll(), group="poll", exclusive=True
        )
        return self._poll_worker

    async def _poll(self) -> None:
        # Textual 8.x: worker mount sirasinda erken baslarsa screen stack henuz
        # bos olabilir (self.screen okumak ScreenStackError firlatir). Ekran yoksa
        # bu tick atlanir — _schedule_next() yine de bir sonraki tik'i kurar.
        if not self.screen_stack:
            return
        screen = self.screen
        try:
            if isinstance(screen, DashboardScreen):
                snapshot = await self.data.fetch_dashboard()
                screen.post_message(DashboardDataUpdated(snapshot))
                self.data.register_success()
            elif isinstance(screen, WatchlistScreen):
                snapshot = await self.data.fetch_watchlist()
                screen.post_message(WatchlistDataUpdated(snapshot))
                self.data.register_success()
            elif isinstance(screen, DetailScreen):
                snapshot = await self.data.fetch_detail(screen.ticker, screen.period)
                screen.post_message(DetailDataUpdated(snapshot))
                self.data.register_success()
        except RateLimitError as exc:
            self.data.register_rate_limit(exc.retry_after)
            self._post_failure(screen, "Rate limit", exc.retry_after)
        except FlorenceError as exc:
            self._post_failure(screen, error_message(exc), None)
        except Exception as exc:  # pragma: no cover — beklenmeyen
            self._post_failure(screen, str(exc), None)
        finally:
            self._schedule_next()

    def _post_failure(self, screen: Any, message: str, retry_after: float | None) -> None:
        if isinstance(screen, DashboardScreen):
            screen.post_message(DashboardDataFailed(message, retry_after))
        elif isinstance(screen, WatchlistScreen):
            screen.post_message(WatchlistDataFailed(message, retry_after))
        elif isinstance(screen, DetailScreen):
            screen.post_message(DetailDataFailed(message, retry_after))

    def _schedule_next(self) -> None:
        """Sonraki tick'i DataHub'in planladigi gecikmeyle kurar (429/K4)."""
        delay = self.data.next_poll_delay()
        if self._poll_timer is not None:
            self._poll_timer.stop()
        self._poll_timer = self.set_interval(delay, self._on_poll_tick)

    # ------------------------------------------------------------------
    # Global eylemler
    # ------------------------------------------------------------------
    # Not: "q" -> "quit" base App.action_quit'e gider (exit). Ctrl+q da base'de var.
    def action_go_dashboard(self) -> None:
        self.switch_screen("dashboard")

    def action_go_watchlist(self) -> None:
        self.switch_screen("watchlist")

    def action_refresh(self) -> None:
        self.poll_now()

    def action_help(self) -> None:
        self.push_screen(HelpModal())

    def open_detail(self, ticker: str) -> None:
        """Seçili ticker'in detay ekranini acar (push — geri donus ``esc``).

        ``DetailScreen`` varsayilan period ve grafik tipiyle baslar
        (config: ``tui_default_period`` / ``tui_default_chart``); ``1/3/6/y``
        tuslari period'u, ``c`` tusu grafik tipini (cizgi/mum) degistirir.
        """
        self.push_screen(
            DetailScreen(
                ticker,
                period=self.default_period,
                chart_type=self.default_chart,
            )
        )


def main() -> None:
    """``fl tui`` giris noktasi (CLI ``commands_tui`` bu fonksiyonu cagirir)."""
    FlorenceTUI().run()
