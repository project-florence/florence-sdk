"""Veri erisim noktasi (DataHub): TTL cache + async fetch'ler + poll planlama.

Tasarim (docs/tui-design.md §4-§5, Ek A):
- Cache: ``dict[key] -> (expires_at, value)``; tek event loop oldugu icin kilit
  gerekmez. Hafif piyasa verisi 1dk TTL, agir veri (price_history) 10dk.
- Rate limit (429): ``RateLimitError.retry_after``'a gore interval gecici
  uzatma ``max(interval*2, retry_after+10)`` (ust sinir 300s); 3 basarili
  tick sonrasi config degerine donus (tasarim §4.4).
- Piyasa kapali (K4): sonraki poll ``next_open_at + ~1dk pay``; ``next_open_at``
  yoksa 5dk fallback. ILK istek her zaman yapilir (henuz durum bilinmiyorken
  planlama yapilmaz).
- Auth: canli backend dogrulamasi (2026-08-14) — yalnizca ``market/status``
  public; ``stats_top`` / ``companies_summary`` / ``economy`` gecerli token
  ister (backend PUBLIC_PATHS allowlist'i). Token yoksa bu bolumler atlanir
  ve ekran 'Giris yapin (fl auth login)' uyarisi gosterir.

Yalnizca ``AsyncFlorenceClient`` kullanilir (senkron client YASAK — event
loop'u bloklar). Testlerde ``httpx.MockTransport``'lu client inject edilir.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..client import AsyncFlorenceClient
from ..errors import AuthError, FlorenceAPIError, FlorenceError, NetworkError, RateLimitError

__all__ = [
    "AUTH_REQUIRED_SECTIONS",
    "DEFAULT_TTL",
    "DashboardSnapshot",
    "DataHub",
    "DetailSnapshot",
    "DigestSnapshot",
    "EconomySnapshot",
    "PortfolioPosition",
    "PortfolioSnapshot",
    "PortfolioSummary",
    "StocksSnapshot",
    "WatchlistRow",
    "WatchlistSnapshot",
    "delta_style",
    "error_message",
    "gold_summary",
    "market_status_text",
    "status_bar_text",
    "tr_delta",
    "tr_number",
]

# ----------------------------------------------------------------------
# Sabitler
# ----------------------------------------------------------------------

#: Varsayilan TTL'ler (saniye). Hafif piyasa verisi 1dk; agir veri 10dk.
DEFAULT_TTL: dict[str, float] = {
    "market_status": 60.0,
    "stats_top": 60.0,
    "companies_summary": 60.0,
    "gold_prices": 60.0,
    "currency": 60.0,
    "current_price": 60.0,
    "favorites": 60.0,
    "company_info": 300.0,
    "news": 300.0,
    "price_history": 600.0,
    "digest_current": 300.0,
    # Faz E (P7): portfoy listesi/ozet/performans hafif -> 1dk; gecmis agir -> 10dk.
    "portfolios": 60.0,
    "portfolio_snapshot": 60.0,
    "portfolio_history": 600.0,
    "portfolio_performers": 60.0,
}

#: Canli backend dogrulamasi: bu pano bolumleri gecerli token ister.
AUTH_REQUIRED_SECTIONS: tuple[str, ...] = (
    "stats_top",
    "gainers",
    "losers",
    "gold",
    "currency",
    "popular",
    "favorites",
    "digest",
)

#: Rate limit sonrasi uzatilmis interval ust siniri (tasarim §4.4).
RATE_LIMIT_MAX_INTERVAL = 300.0

#: Rate limit sonrasi kac basarili tick ile normale donulur (§4.4: 3).
RATE_LIMIT_RECOVERY_TICKS = 3

#: Piyasa kapaliyken next_open_at'e eklenen pay (K4: ~1dk).
OPEN_BUFFER_SECONDS = 60.0

#: Kapali piyasa planlama alt/ust sinirlari (K4).
MIN_CLOSED_POLL_DELAY = 30.0
MAX_POLL_DELAY = 3600.0

#: Altin seridinde gosterilecek kalemler (Type alanindan eslesme, Ek A).
GOLD_LABELS: tuple[tuple[str, str], ...] = (
    ("gram-altin", "Gram Altın"),
    ("ceyrek-altin", "Çeyrek Altın"),
    ("cumhuriyet-altini", "Cumhuriyet Altını"),
)


# ----------------------------------------------------------------------
# Pano anlik gorunumu (poll worker -> ekran mesajiyla tasinir)
# ----------------------------------------------------------------------
@dataclass
class DashboardSnapshot:
    """Bir poll tick'inin pano icin toplu sonucu."""

    market_status: dict[str, Any] | None
    stats_top: list[dict[str, Any]] | None
    gainers: list[dict[str, Any]] | None
    losers: list[dict[str, Any]] | None
    gold: list[dict[str, Any]] | None
    currency: dict[str, Any] | None
    fetched_at: datetime
    popular: list[dict[str, Any]] | None = None
    favorites_summary: list[dict[str, Any]] | None = None
    digest: dict[str, Any] | None = None
    errors: dict[str, str] = field(default_factory=dict)
    auth_sections: tuple[str, ...] = ()


@dataclass
class DigestSnapshot:
    """Bir poll tick'inin piyasa bülteni (digest) için toplu sonucu."""

    market_status: dict[str, Any] | None
    current_digest: dict[str, Any] | None
    fetched_at: datetime
    errors: dict[str, str] = field(default_factory=dict)
    auth_sections: tuple[str, ...] = ()


@dataclass
class StocksSnapshot:
    """Hisseler ekranı için toplu sonuç."""

    market_status: dict[str, Any] | None
    sort: str
    companies: list[dict[str, Any]] | None
    fetched_at: datetime
    errors: dict[str, str] = field(default_factory=dict)
    auth_sections: tuple[str, ...] = ()


@dataclass
class EconomySnapshot:
    """Ekonomi ekranı için toplu sonuç."""

    market_status: dict[str, Any] | None
    gold: list[dict[str, Any]] | None
    currency: dict[str, Any] | None
    metals: dict[str, Any] | None
    fetched_at: datetime
    errors: dict[str, str] = field(default_factory=dict)
    auth_sections: tuple[str, ...] = ()



@dataclass
class WatchlistRow:
    """Watchlist tablosundaki tek satir (bir favori ticker)."""

    ticker: str
    price: float | None = None
    change_pct: float | None = None
    #: Sparkline icin ham ``close`` serisi (``price_history`` — 10dk cache).
    close_values: list[float | None] = field(default_factory=list)


@dataclass
class WatchlistSnapshot:
    """Bir poll tick'inin watchlist icin toplu sonucu.

    ``favorites is None`` -> liste alinamadi (hata); ``favorites == []`` ->
    gercekten bos liste (ekran 'Favoriniz yok' gosterir). Satirlar favori
    sirasinda; tek ticker'in fiyati cekilemezse o satir ``price=None`` kalir
    (kismi hata toleransi — tum liste dusmez).
    """

    market_status: dict[str, Any] | None
    favorites: list[str] | None
    rows: list[WatchlistRow]
    fetched_at: datetime
    errors: dict[str, str] = field(default_factory=dict)
    auth_sections: tuple[str, ...] = ()


@dataclass
class DetailSnapshot:
    """Bir poll tick'inin ticker detayi icin toplu sonucu.

    Kismi hatalarda ilgili alan ``None`` olur (``errors`` mesaj tasir);
    diger alanlar etkilenmez. ``news`` JWT ister: oturum yoksa veya oturum
    suresi dolduysa ``auth_sections`` icinde ``"news"`` bulunur (ekran
    giris onerisi gosterir).
    """

    ticker: str
    period: str
    market_status: dict[str, Any] | None
    company_info: dict[str, Any] | None
    current_price: dict[str, Any] | None
    price_history: list[dict[str, Any]] | None
    news: list[dict[str, Any]] | None
    fetched_at: datetime
    errors: dict[str, str] = field(default_factory=dict)
    auth_sections: tuple[str, ...] = ()


@dataclass
class PortfolioSummary:
    """``GET /portfolios`` listesindeki tek portfoy satiri (Faz E — P7).

    Alan adlari plan T0.2'nin canli sema notundan alinamadi (bu makinede
    backend kalkik degil) — kod okumasi + helpers-design.md H5 sozlesmesinden
    mock sema kuruldu; ``id``/``portfolio_id`` esnekligi toleranslidir
    (uydurma alan yok). Canli dogrulama Faz F'ye ertelendi (plan risk 7).
    """

    portfolio_id: str
    name: str
    initial_balance: float | None = None


@dataclass
class PortfolioPosition:
    """Performers girislerinden biri (Ticker + donem getirisi)."""

    ticker: str
    return_pct: float | None = None
    pnl: float | None = None


@dataclass
class PortfolioSnapshot:
    """Bir poll tick'inin portfoy ekrani icin toplu sonucu.

    ``summaries is None`` -> liste alinamadi (hata); ``summaries == []`` ->
    gercekten bos liste (ekran 'Portfoyunuz yok' gosterir). ``summary``
    secili portfoyun snapshot'idir (``total_value``/``pnl``/``pnl_pct`` —
    H5 sozlesmesi); kismi hatada ``None`` kalir (``errors`` mesaj tasir) ve
    liste/history/performers etkilenmez. ``portfolio_id`` otomatik secilen
    portfoyu yansitir (cagiriya verilen id yoksa tek portfoy otomatik
    secilir; birden fazlaysa ``None`` — ekran secim bekler).
    """

    portfolio_id: str | None
    summaries: list[PortfolioSummary] | None
    summary: dict[str, Any] | None
    history: list[dict[str, Any]] | None
    performers: list[PortfolioPosition] | None
    market_status: dict[str, Any] | None
    fetched_at: datetime
    errors: dict[str, str] = field(default_factory=dict)
    auth_sections: tuple[str, ...] = ()


def market_status_text(status: dict[str, Any] | None) -> str:
    """Piyasa durumu metni: ``Piyasa: AÇIK`` / ``Piyasa: KAPALI · 10:00'da açılacak``."""
    if not isinstance(status, dict):
        return "[grey]Piyasa durumu alınamadı[/]"
    if status.get("holiday"):
        state = "[yellow]TATİL[/]"
    elif status.get("open"):
        state = "[green]AÇIK[/]"
    else:
        state = "[red]KAPALI[/]"
        nxt = status.get("next_open_at")
        if nxt:
            state += f" · {_format_open_time(nxt)}'da açılacak"
    return f"Piyasa: {state}"


def status_bar_text(status: dict[str, Any] | None, fetched_at: datetime) -> str:
    """Ust bar satiri: piyasa durumu + son guncelleme (Faz D — DRY).

    Dashboard/watchlist/detail ekranlari bu ortak yardimciyi kullanir;
    ``market_status_text`` tek kaynak (keşif #2: dashboard'daki kopya
    implementasyon kaldirildi).
    """
    return f"{market_status_text(status)}  ·  Son güncelleme: {fetched_at:%H:%M:%S}"


def _format_open_time(raw: Any) -> str:
    """ISO next_open_at -> yerel saat ('10:00'); gecersizse ham metin."""
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.astimezone().strftime("%H:%M")
    except ValueError:
        return str(raw)


# ----------------------------------------------------------------------
# Format yardimcilari (UI'siz — birim testleri dogrudan kullanir)
# ----------------------------------------------------------------------
def tr_number(value: Any, decimals: int = 2) -> str:
    """TR sayi formati: 1234.5 -> ``'1.234,50'``; gecersiz deger -> ``'—'``."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    s = f"{num:,.{decimals}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def tr_delta(value: Any) -> str:
    """Delta yuzdesi: ``+0,93%`` / ``-1,20%`` / ``0,00%``."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "+" if num > 0 else ""
    return f"{sign}{tr_number(num)}%"


def delta_style(value: Any) -> str:
    """TR BIST renk kurali: yukari ``$success`` / asagi ``$error`` / sifir gri."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "$foreground"
    if num > 0:
        return "$success"
    if num < 0:
        return "$error"
    return "$foreground"


def error_message(exc: BaseException) -> str:
    """Hata nesnesini kisa, ekran dostu Turkce mesaja cevirir."""
    if isinstance(exc, NetworkError):
        return "Bağlantı hatası"
    if isinstance(exc, FlorenceAPIError):
        return f"API hatası {exc.status_code}"
    return str(exc)


_TR_TABLE = str.maketrans("ıİğĞüÜşŞöÖçÇ", "iigguussoocc")


def _norm_key(value: str) -> str:
    """Turkce karakterleri ascii'ye cevirir; tire/bosluk atar (eslesme icin)."""
    return value.translate(_TR_TABLE).replace("-", "").replace(" ", "").lower()


def gold_summary(gold: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Altin listesinden (16 kalem) oncelikli kalemleri secer (Type eslesmesi).

    Backend Type degerleri TR string olabilir (``'Gram Altın'``); eslesme
    normalizasyonlu yapilir. Bulunamazsa bos liste doner (ekran 'Veri yok'
    gosterir).
    """
    by_key = {
        _norm_key(str(item.get("Type", ""))): item
        for item in gold
        if item.get("Type")
    }
    found: list[tuple[str, dict[str, Any]]] = []
    for key, label in GOLD_LABELS:
        item = by_key.get(_norm_key(key))
        if item is not None:
            found.append((label, item))
    return found


# ----------------------------------------------------------------------
# DataHub
# ----------------------------------------------------------------------
class DataHub:
    """TTL cache + async fetch + poll planlama (tek veri erisim noktasi).

    Ekranlar client'a dokunmaz; ``fetch_dashboard`` gibi metotlari cagirir.
    Client enjeksiyonu testlerde ``httpx.MockTransport`` verilmesini saglar.
    """

    def __init__(
        self,
        client: AsyncFlorenceClient,
        *,
        refresh_seconds: float = 45.0,
        market_closed_refresh: float = 300.0,
        top_limit: int = 10,
        summary_limit: int = 10,
        ttl_overrides: dict[str, float] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client
        self.refresh_seconds = float(refresh_seconds)
        self.market_closed_refresh = float(market_closed_refresh)
        self.top_limit = top_limit
        self.summary_limit = summary_limit
        self._ttl: dict[str, float] = {**DEFAULT_TTL, **(ttl_overrides or {})}
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        self._cache: dict[str, tuple[float, Any]] = {}

        # Rate limit durumu (§4.4)
        self._rate_limit_ticks = 0
        self._rate_limit_retry_after: float | None = None
        self._rate_limit_backoff_until = 0.0

        # Piyasa durumu (K4)
        self._market_status_fetched = False
        self._market_open = True
        self._holiday = False
        self._next_open_at: datetime | None = None

        #: Son basarili veri getirme zamani (banner 'son veri' ibaresi icin).
        self.last_update: datetime | None = None

    # ------------------------------------------------------------------
    # Genel yardimcilar
    # ------------------------------------------------------------------
    @property
    def base_url(self) -> str:
        return self._client.base_url

    def is_authenticated(self) -> bool:
        """Gecerli bir oturum var mi (env override dahil)."""
        return bool(self._client.auth.is_authenticated())

    def _now_mono(self) -> float:
        return time.monotonic()

    def _ttl_for(self, key: str) -> float:
        # Cache anahtarlari parametre icerebilir (``stats_top:5``); override
        # taban anahtarla verilir (``ttl_overrides={"stats_top": ...}``).
        return self._ttl.get(key, self._ttl.get(key.split(":", 1)[0], 60.0))

    async def close(self) -> None:
        """Client'i kapatir (App.on_unmount)."""
        await self._client.close()

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    _CACHE_MISS = object()

    def _get_cached(self, key: str) -> Any:
        item = self._cache.get(key)
        if item is None:
            return self._CACHE_MISS
        expires_at, value = item
        if expires_at <= self._now_mono():
            self._cache.pop(key, None)
            return self._CACHE_MISS
        return value

    def _set_cached(self, key: str, value: Any, ttl: float | None = None) -> Any:
        self._cache[key] = (self._now_mono() + (ttl if ttl is not None else self._ttl_for(key)), value)
        self.last_update = self._clock()
        return value

    # ------------------------------------------------------------------
    # Rate limit / poll planlama (§4.4, K4)
    # ------------------------------------------------------------------
    def register_rate_limit(self, retry_after: float | None) -> None:
        """429 sonrasi cagrilir: interval uzatma + backoff penceresi kurar."""
        self._rate_limit_retry_after = retry_after
        self._rate_limit_ticks = RATE_LIMIT_RECOVERY_TICKS
        base = retry_after if retry_after is not None else self.refresh_seconds
        self._rate_limit_backoff_until = self._now_mono() + base

    def register_success(self) -> None:
        """Basarili tick: uzatilmis interval sayacini azaltir."""
        if self._rate_limit_ticks > 0:
            self._rate_limit_ticks -= 1

    def register_market_status(self, status: dict[str, Any] | None) -> None:
        """Basarili ``market_status`` fetch'i sonrasi K4 durumunu kaydeder."""
        self._market_status_fetched = True
        if not isinstance(status, dict):
            self._market_open = False
            self._holiday = False
            self._next_open_at = None
            return
        self._market_open = bool(status.get("open", False))
        self._holiday = bool(status.get("holiday", False))
        self._next_open_at = _parse_dt(status.get("next_open_at"))

    def next_poll_delay(self) -> float:
        """Bir sonraki poll tick'inin gecikmesi (saniye).

        Oncelik: (1) rate limit uzatilmasi, (2) kapali piyasada next_open_at
        planlamasi (K4), (3) normal config intervali. ``_market_status_fetched``
        False iken (ilk istek oncesi) her zaman normal interval doner — K4'teki
        'ILK istek her zaman yapilir' garantisi.
        """
        if self._rate_limit_ticks > 0:
            base = (
                self._rate_limit_retry_after
                if self._rate_limit_retry_after is not None
                else self.refresh_seconds
            )
            delay = max(self.refresh_seconds * 2.0, base + 10.0)
            backoff_left = self._rate_limit_backoff_until - self._now_mono()
            if backoff_left > 0:
                delay = max(delay, backoff_left + 1.0)
            return min(RATE_LIMIT_MAX_INTERVAL, delay)
        if self._market_status_fetched and not self._market_open:
            if self._next_open_at is not None:
                delta = (self._next_open_at - self._clock()).total_seconds() + OPEN_BUFFER_SECONDS
                # K4: piyasa acilana kadar bekle — ust sinir YOK (hafta sonu
                # dahil); yalnizca alt sinir (donem icin asiri kisa gecikme).
                return max(MIN_CLOSED_POLL_DELAY, delta)
            return float(self.market_closed_refresh)
        return float(self.refresh_seconds)

    # ------------------------------------------------------------------
    # Fetch metotlari (TTL cache'li; yalnizca AsyncFlorenceClient)
    # ------------------------------------------------------------------
    async def get_market_status(self) -> dict[str, Any] | None:
        """``market/status`` (public, 60s TTL). K4 durumunu da gunceller."""
        cached = self._get_cached("market_status")
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.market.market_status()
        result = data if isinstance(data, dict) else {}
        self._set_cached("market_status", result)
        self.register_market_status(result)
        return result

    async def get_stats_top(self, limit: int | None = None) -> list[dict[str, Any]] | None:
        """``stats/top`` — one cikanlar (auth ister; 60s TTL)."""
        limit = limit if limit is not None else self.top_limit
        key = f"stats_top:{limit}"
        cached = self._get_cached(key)
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.market.stats_top(limit=limit)
        rows = data if isinstance(data, list) else []
        return self._set_cached(key, rows)

    async def get_companies_summary(
        self, sort: str, limit: int | None = None
    ) -> list[dict[str, Any]] | None:
        """``companies/summary`` — gainers/losers (auth ister; 60s TTL)."""
        limit = limit if limit is not None else self.summary_limit
        key = f"companies_summary:{sort}:{limit}"
        cached = self._get_cached(key)
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.market.companies_summary(limit=limit, sort=sort)
        if isinstance(data, dict):
            # Backend {"data": [...], "total": n} dondurur — TUI listeyi kullanir.
            inner = data.get("data")
            rows = inner if isinstance(inner, list) else []
        else:
            rows = data if isinstance(data, list) else []
        return self._set_cached(key, rows)

    async def get_gold_prices(self) -> list[dict[str, Any]] | None:
        """``economy/gold-prices`` (auth ister; 60s TTL)."""
        cached = self._get_cached("gold_prices")
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.economy.gold_prices()
        rows = data if isinstance(data, list) else []
        return self._set_cached("gold_prices", rows)

    async def get_currency(self) -> dict[str, Any] | None:
        """``economy/currency?symbols=USD,EUR`` (auth ister; 60s TTL)."""
        cached = self._get_cached("currency")
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.economy.currency(symbols="USD,EUR")
        result = data if isinstance(data, dict) else {}
        return self._set_cached("currency", result)

    async def get_favorites(self) -> list[str] | None:
        """``/favorites`` — favori ticker listesi (JWT; 60s TTL).

        Yanit duz string listesi olabilecegi gibi ``{"favorites": [...]}``
        biciminde de gelebilir (Ek A sozlesmesi listeyi esas alir; dict'e
        tolerans).
        """
        cached = self._get_cached("favorites")
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.portfolio.favorites()
        if isinstance(data, dict):
            data = data.get("favorites", [])
        rows = data if isinstance(data, list) else []
        return self._set_cached("favorites", [str(t) for t in rows])

    async def get_current_price(self, ticker: str) -> dict[str, Any] | None:
        """``/price/current`` — anlik fiyat (public; 60s TTL)."""
        key = f"current_price:{ticker}"
        cached = self._get_cached(key)
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.market.current_price(ticker)
        result = data if isinstance(data, dict) else {}
        return self._set_cached(key, result)

    async def get_company_info(self, ticker: str) -> dict[str, Any] | None:
        """``/companies/info/{ticker}`` — sirket profili (public; 5dk TTL)."""
        key = f"company_info:{ticker}"
        cached = self._get_cached(key)
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.market.company_info(ticker)
        result = data if isinstance(data, dict) else {}
        return self._set_cached(key, result)

    async def get_price_history(
        self, ticker: str, period: str = "1mo", interval: str = "1d"
    ) -> list[dict[str, Any]] | None:
        """``/price/history/{ticker}`` (public; 10dk TTL — tasarim §4.5)."""
        key = f"price_history:{ticker}:{period}:{interval}"
        cached = self._get_cached(key)
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.market.price_history(ticker, period=period, interval=interval)
        rows = data if isinstance(data, list) else []
        return self._set_cached(key, rows)

    async def get_news(self, ticker: str, amount: int = 5) -> list[dict[str, Any]] | None:
        """``/news/{ticker}`` — haberler (JWT + news feature; 5dk TTL).

        TTL 5dk, backend 10/dk limitinin cok altinda kalir (tasarim §4.4
        news ozel kurali).
        """
        key = f"news:{ticker}:{amount}"
        cached = self._get_cached(key)
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.market.news(ticker, amount=amount)
        rows = data if isinstance(data, list) else []
        return self._set_cached(key, rows)

    # ------------------------------------------------------------------
    # Portfoy fetch'leri (Faz E — P7; tumu JWT ister)
    # ------------------------------------------------------------------
    async def get_portfolio_list(self) -> list[PortfolioSummary] | None:
        """``/portfolios`` — portfoy listesi (JWT; 60s TTL)."""
        cached = self._get_cached("portfolios")
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.portfolio.list_portfolios()
        rows = data if isinstance(data, list) else []
        summaries = [s for s in (_portfolio_summary(r) for r in rows) if s is not None]
        return self._set_cached("portfolios", summaries)

    async def get_portfolio_snapshot(self, portfolio_id: str) -> dict[str, Any] | None:
        """``/portfolios/{id}/snapshot`` — birlesik ozet (JWT; 60s TTL)."""
        key = f"portfolio_snapshot:{portfolio_id}"
        cached = self._get_cached(key)
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.portfolio.snapshot(portfolio_id)
        result = data if isinstance(data, dict) else {}
        return self._set_cached(key, result)

    async def get_portfolio_history(
        self, portfolio_id: str, period: str = "1mo"
    ) -> list[dict[str, Any]] | None:
        """``/portfolios/{id}/history`` — deger gecmisi (JWT; 10dk TTL)."""
        key = f"portfolio_history:{portfolio_id}:{period}"
        cached = self._get_cached(key)
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.portfolio.history(portfolio_id, period=period)
        rows = data if isinstance(data, list) else []
        return self._set_cached(key, rows)

    async def get_portfolio_performers(
        self, portfolio_id: str, top_n: int = 5
    ) -> list[PortfolioPosition] | None:
        """``/portfolios/{id}/performers`` — en iyi/en kotu N (JWT; 60s TTL).

        Yanit ``{top: [...], bottom: [...]}`` (H5 sozlesmesi) veya duz liste
        olabilir — ekran usti bilgi icin ``top`` listesi esas alinir.
        """
        key = f"portfolio_performers:{portfolio_id}:{top_n}"
        cached = self._get_cached(key)
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.portfolio.performers(portfolio_id, top_n=top_n)
        result = _portfolio_positions(data)
        return self._set_cached(key, result)

    async def get_current_digest(self) -> dict[str, Any] | None:
        """``/digest`` — en güncel piyasa bülteni (JWT; 300s TTL)."""
        cached = self._get_cached("digest_current")
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.digest.current()
        result = data if isinstance(data, dict) else {}
        return self._set_cached("digest_current", result, ttl=300.0)

    async def get_favorites_summary(self, limit: int = 10) -> list[dict[str, Any]] | None:
        """Favori hisselerin özet bilgilerini çeker (JWT; 60s TTL)."""
        favs = await self.get_favorites()
        if not favs:
            return []
        tickers = ",".join(favs[:limit])
        key = f"favs_summary:{tickers}"
        cached = self._get_cached(key)
        if cached is not self._CACHE_MISS:
            return cached
        data = await self._client.market.companies_summary(tickers=tickers, limit=limit)
        if isinstance(data, dict):
            inner = data.get("data")
            rows = inner if isinstance(inner, list) else []
        else:
            rows = data if isinstance(data, list) else []
        return self._set_cached(key, rows)

    # ------------------------------------------------------------------
    # Pano toplu fetch'i (poll worker tek cagri yapar)
    # ------------------------------------------------------------------
    async def fetch_dashboard(self) -> DashboardSnapshot:
        """Pano icin tum bolumleri tek tick'te toplar."""
        errors: dict[str, str] = {}
        authed = self.is_authenticated()
        status = await self.get_market_status()
        sections: dict[str, Any] = {}
        if authed:
            names = (
                "stats_top",
                "gainers",
                "losers",
                "gold",
                "currency",
                "popular",
                "favorites_summary",
                "digest",
            )
            results = await asyncio.gather(
                self._fetch_section("stats_top", self.get_stats_top(), errors),
                self._fetch_section(
                    "gainers", self.get_companies_summary("gainers"), errors
                ),
                self._fetch_section(
                    "losers", self.get_companies_summary("losers"), errors
                ),
                self._fetch_section("gold", self.get_gold_prices(), errors),
                self._fetch_section("currency", self.get_currency(), errors),
                self._fetch_section(
                    "popular", self.get_companies_summary("popular"), errors
                ),
                self._fetch_section(
                    "favorites_summary", self.get_favorites_summary(), errors
                ),
                self._fetch_section("digest", self.get_current_digest(), errors),
            )
            sections = dict(zip(names, results, strict=True))
        return DashboardSnapshot(
            market_status=status,
            stats_top=sections.get("stats_top"),
            gainers=sections.get("gainers"),
            losers=sections.get("losers"),
            gold=sections.get("gold"),
            currency=sections.get("currency"),
            fetched_at=self._clock(),
            popular=sections.get("popular"),
            favorites_summary=sections.get("favorites_summary"),
            digest=sections.get("digest"),
            errors=errors,
            auth_sections=() if authed else AUTH_REQUIRED_SECTIONS,
        )

    async def fetch_digest(self) -> DigestSnapshot:
        """Piyasa bülteni ekranı için tek tick'te bülten çeker."""
        errors: dict[str, str] = {}
        authed = self.is_authenticated()
        status = await self.get_market_status()
        digest = None
        if authed:
            digest = await self._fetch_section("digest", self.get_current_digest(), errors)
        return DigestSnapshot(
            market_status=status,
            current_digest=digest,
            fetched_at=self._clock(),
            errors=errors,
            auth_sections=() if authed else ("digest",),
        )

    async def fetch_stocks(self, sort: str = "popular") -> StocksSnapshot:
        """Hisseler ekranı için sıralı şirket listesi çeker."""
        errors: dict[str, str] = {}
        authed = self.is_authenticated()
        status = await self.get_market_status()
        companies = None
        if authed:
            companies = await self._fetch_section(
                "companies", self.get_companies_summary(sort, limit=30), errors
            )
        return StocksSnapshot(
            market_status=status,
            sort=sort,
            companies=companies,
            fetched_at=self._clock(),
            errors=errors,
            auth_sections=() if authed else ("companies",),
        )

    async def fetch_economy(self) -> EconomySnapshot:
        """Ekonomi ekranı için altın ve döviz verilerini çeker."""
        errors: dict[str, str] = {}
        authed = self.is_authenticated()
        status = await self.get_market_status()
        gold = None
        currency = None
        if authed:
            gold = await self._fetch_section("gold", self.get_gold_prices(), errors)
            currency = await self._fetch_section("currency", self.get_currency(), errors)
        return EconomySnapshot(
            market_status=status,
            gold=gold,
            currency=currency,
            metals=None,
            fetched_at=self._clock(),
            errors=errors,
            auth_sections=() if authed else ("gold", "currency"),
        )

    async def _fetch_section(
        self,
        section: str,
        coro: Awaitable[Any],
        errors: dict[str, str],
        auth_sections: set[str] | None = None,
    ) -> Any:
        """Tek bolumu guvenle ceker; hata mesajini ``errors``'a yazar.

        ``auth_sections`` verilirse AuthError (oturum suresi doldu) o
        bolumu kumeye ekler — ekran bolumu gizleyip giris onerir.
        """
        try:
            return await coro
        except RateLimitError:
            raise  # tum tick iptal — app uzatma/banner yonetir
        except AuthError:
            errors[section] = "Oturum süresi doldu — tekrar giriş yapın (fl auth login)"
            if auth_sections is not None:
                auth_sections.add(section)
            return None
        except FlorenceError as exc:
            errors[section] = error_message(exc)
            return None
        except Exception as exc:  # pragma: no cover — beklenmeyen hata
            errors[section] = str(exc)
            return None

    # ------------------------------------------------------------------
    # Watchlist toplu fetch'i (poll worker tek cagri yapar)
    # ------------------------------------------------------------------
    async def fetch_watchlist(self) -> WatchlistSnapshot:
        """Watchlist icin tek tick'te: status + favoriler + N x (fiyat + seri).

        - Auth yoksa favori bolumu HIC istek atmaz: ``auth_sections``
          icinde ``"favorites"`` (ekran 'fl auth login' uyarisi gosterir).
        - Tek ticker'in fiyati/serisi cekilemezse o satir ``None`` alanlarla
          kalir (ekran '—' basar), tum liste dusmez — kismi hata toleransi.
        - ``RateLimitError`` YAYILIR — app interval uzatmasi ve banner icin
          yakalar (tasarim §4.4).
        """
        errors: dict[str, str] = {}
        auth_sections: set[str] = set()
        status = await self.get_market_status()
        if not self.is_authenticated():
            auth_sections.add("favorites")
            return WatchlistSnapshot(
                market_status=status,
                favorites=None,
                rows=[],
                fetched_at=self._clock(),
                errors=errors,
                auth_sections=("favorites",),
            )
        favorites = await self._fetch_section(
            "favorites", self.get_favorites(), errors, auth_sections
        )
        tickers = favorites or []
        rows: list[WatchlistRow] = []
        for ticker in tickers:
            row = WatchlistRow(ticker=ticker)
            quote = await self._fetch_section(
                f"price:{ticker}", self.get_current_price(ticker), errors
            )
            if isinstance(quote, dict):
                row.price = quote.get("price")
                row.change_pct = quote.get("change_pct")
            history = await self._fetch_section(
                f"history:{ticker}",
                self.get_price_history(ticker, period="1mo", interval="1d"),
                errors,
            )
            if isinstance(history, list):
                row.close_values = [
                    item.get("close") for item in history if isinstance(item, dict)
                ]
            rows.append(row)
        return WatchlistSnapshot(
            market_status=status,
            favorites=tickers,
            rows=rows,
            fetched_at=self._clock(),
            errors=errors,
            auth_sections=tuple(sorted(auth_sections)),
        )

    # ------------------------------------------------------------------
    # Detay toplu fetch'i (poll worker tek cagri yapar)
    # ------------------------------------------------------------------
    async def fetch_detail(self, ticker: str, period: str) -> DetailSnapshot:
        """Ticker detayi: status + company_info + current_price + history + news.

        - Kismi hatalar ilgili alani ``None`` yapar (``errors`` mesaj
          tasir), diger alanlar etkilenmez.
        - ``news`` JWT ister: oturum yoksa hic istek atilmaz ve
          ``auth_sections`` icinde ``"news"`` bulunur; oturum suresi
          dolduysa (AuthError) ayni sekilde gizlenir. ``RateLimitError``
          yayilir (app yonetir).
        """
        errors: dict[str, str] = {}
        auth_sections: set[str] = set()
        authed = self.is_authenticated()
        status = await self.get_market_status()
        info = await self._fetch_section(
            "company_info", self.get_company_info(ticker), errors
        )
        quote = await self._fetch_section(
            "current_price", self.get_current_price(ticker), errors
        )
        history = await self._fetch_section(
            "price_history",
            self.get_price_history(ticker, period=period, interval="1d"),
            errors,
        )
        news: list[dict[str, Any]] | None = None
        if not authed:
            auth_sections.add("news")
        else:
            news = await self._fetch_section(
                "news", self.get_news(ticker, amount=5), errors, auth_sections
            )
        return DetailSnapshot(
            ticker=ticker,
            period=period,
            market_status=status,
            company_info=info,
            current_price=quote,
            price_history=history,
            news=news,
            fetched_at=self._clock(),
            errors=errors,
            auth_sections=tuple(sorted(auth_sections)),
        )

    # ------------------------------------------------------------------
    # Portfoy toplu fetch'i (poll worker tek cagri yapar)
    # ------------------------------------------------------------------
    async def fetch_portfolio(
        self, portfolio_id: str | None, period: str = "1mo"
    ) -> PortfolioSnapshot:
        """Portfoy ekrani icin tek tick'te: liste (+ secili ozet/history/performers).

        - Auth yoksa HIC portfoy istegi atilmaz: ``auth_sections`` icinde
          ``\"portfolio\"`` (ekran 'fl auth login' uyarisi gosterir).
        - Toplam hata toleransi: snapshot/history/performers bolum bazli
          hatalarda ilgili alan ``None`` olur (``errors`` mesaj tasir),
          PORTFÖY LISTESI KALIR — kismi hata toleransi (plan T-E1).
        - ``portfolio_id`` verilmezse tek portfoy otomatik secilir; birden
          fazla portfoy varsa secim ekrana birakilir (``portfolio_id=None``).
        - ``RateLimitError`` YAYILIR — app interval uzatmasi ve banner icin
          yakalar (tasarim §4.4).
        """
        errors: dict[str, str] = {}
        auth_sections: set[str] = set()
        status = await self.get_market_status()
        if not self.is_authenticated():
            auth_sections.add("portfolio")
            return PortfolioSnapshot(
                portfolio_id=None,
                summaries=None,
                summary=None,
                history=None,
                performers=None,
                market_status=status,
                fetched_at=self._clock(),
                errors=errors,
                auth_sections=("portfolio",),
            )
        summaries = await self._fetch_section(
            "portfolios", self.get_portfolio_list(), errors, auth_sections
        )
        selected_id = portfolio_id
        if selected_id is None and isinstance(summaries, list) and len(summaries) == 1:
            # Tek portfoy: otomatik secim (ekrandan enter beklenmez).
            selected_id = summaries[0].portfolio_id
        summary: dict[str, Any] | None = None
        history: list[dict[str, Any]] | None = None
        performers: list[PortfolioPosition] | None = None
        if selected_id is not None:
            # Parca istekleri PARALEL cekilir; tek tek dusebilir (kismi
            # tolerans), RateLimitError gather ile yayilir (429'da istek yok).
            summary, history, performers = await asyncio.gather(
                self._fetch_section(
                    "portfolio_snapshot",
                    self.get_portfolio_snapshot(selected_id),
                    errors,
                    auth_sections,
                ),
                self._fetch_section(
                    "portfolio_history",
                    self.get_portfolio_history(selected_id, period=period),
                    errors,
                    auth_sections,
                ),
                self._fetch_section(
                    "portfolio_performers",
                    self.get_portfolio_performers(selected_id),
                    errors,
                    auth_sections,
                ),
            )
        return PortfolioSnapshot(
            portfolio_id=selected_id,
            summaries=summaries,
            summary=summary if isinstance(summary, dict) else None,
            history=history,
            performers=performers,
            market_status=status,
            fetched_at=self._clock(),
            errors=errors,
            auth_sections=tuple(sorted(auth_sections)),
        )


def _portfolio_summary(item: Any) -> PortfolioSummary | None:
    """Ham liste satirini ``PortfolioSummary``'a cevirir; gecersizse ``None``.

    Alan adlari toleransli: ``id`` veya ``portfolio_id``; ad yoksa id
    gosterilir (uydurma alan yok — P7 risk notu). ``initial_balance``
    sayisal degilse ``None``.
    """
    if not isinstance(item, dict):
        return None
    pid = item.get("id", item.get("portfolio_id"))
    if pid is None:
        return None
    return PortfolioSummary(
        portfolio_id=str(pid),
        name=str(item.get("name") or item.get("title") or pid),
        initial_balance=_to_float_value(item.get("initial_balance")),
    )


def _portfolio_positions(data: Any) -> list[PortfolioPosition] | None:
    """Performers yanitini ``PortfolioPosition`` listesine cevirir.

    ``{top: [...], bottom: [...]}`` (H5 sozlesmesi) veya duz liste kabul
    edilir; ekran 'top 5' bilgisi icin ``top`` esas alinir. Giris liste
    degil ve ``top`` anahtari yoksa ``None`` (ekran 'Veri yok' gosterir).
    """
    if isinstance(data, dict):
        rows = data.get("top")
    elif isinstance(data, list):
        rows = data
    else:
        return None
    out: list[PortfolioPosition] = []
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        ticker = item.get("ticker")
        if not ticker:
            continue
        out.append(
            PortfolioPosition(
                ticker=str(ticker),
                return_pct=_to_float_value(
                    item.get("return_pct", item.get("pnl_pct", item.get("change_pct")))
                ),
                pnl=_to_float_value(item.get("pnl", item.get("unrealized_pnl"))),
            )
        )
    return out


def _to_float_value(value: Any) -> float | None:
    """Sayisal degeri float'a cevirir; bool/None/gecersiz -> ``None``."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> datetime | None:
    """ISO tarih metnini UTC datetime'a cevirir; gecersizse ``None``."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
