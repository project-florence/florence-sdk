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
    "WatchlistRow",
    "WatchlistSnapshot",
    "delta_style",
    "error_message",
    "gold_summary",
    "market_status_text",
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
}

#: Canli backend dogrulamasi: bu pano bolumleri gecerli token ister.
AUTH_REQUIRED_SECTIONS: tuple[str, ...] = (
    "stats_top",
    "gainers",
    "losers",
    "gold",
    "currency",
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
    """Bir poll tick'inin pano icin toplu sonucu.

    ``None`` alanlar: veri yok (hata veya henuz yuklenmedi). ``errors``
    bolum bazli hata mesajlarini tasir; ``auth_sections`` token olmadigi
    icin atlanan bolumleri listeler.
    """

    market_status: dict[str, Any] | None
    stats_top: list[dict[str, Any]] | None
    gainers: list[dict[str, Any]] | None
    losers: list[dict[str, Any]] | None
    gold: list[dict[str, Any]] | None
    currency: dict[str, Any] | None
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
    # Pano toplu fetch'i (poll worker tek cagri yapar)
    # ------------------------------------------------------------------
    async def fetch_dashboard(self) -> DashboardSnapshot:
        """Pano icin tum bolumleri tek tick'te toplar.

        - ``market/status`` her zaman cekilir (public).
        - Auth gerektiren bolumler yalnizca oturum varsa cekilir; yoksa
          ``auth_sections``'ta listelenir (ekran uyari gosterir).
        - Bolum bazli hatalar ``errors``'a yazilir, diger bolumler devam eder.
        - ``RateLimitError`` YAYILIR — app interval uzatmasi ve banner icin
          yakalar (kalan istekler atilir; rate limit'te istek yapilmaz).
        """
        errors: dict[str, str] = {}
        authed = self.is_authenticated()
        status = await self.get_market_status()
        sections: dict[str, Any] = {}
        if authed:
            sections["stats_top"] = await self._fetch_section(
                "stats_top", self.get_stats_top(), errors
            )
            sections["gainers"] = await self._fetch_section(
                "gainers", self.get_companies_summary("gainers"), errors
            )
            sections["losers"] = await self._fetch_section(
                "losers", self.get_companies_summary("losers"), errors
            )
            sections["gold"] = await self._fetch_section(
                "gold", self.get_gold_prices(), errors
            )
            sections["currency"] = await self._fetch_section(
                "currency", self.get_currency(), errors
            )
        return DashboardSnapshot(
            market_status=status,
            stats_top=sections.get("stats_top"),
            gainers=sections.get("gainers"),
            losers=sections.get("losers"),
            gold=sections.get("gold"),
            currency=sections.get("currency"),
            fetched_at=self._clock(),
            errors=errors,
            auth_sections=() if authed else AUTH_REQUIRED_SECTIONS,
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
