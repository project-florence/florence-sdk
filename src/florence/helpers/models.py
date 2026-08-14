"""Helper sonuc modelleri — stabil cikti semalari (helpers-design.md Bolum 2).

``_Lenient`` deseni (``models.py`` ile ayni): ``extra="allow"`` ile backend'in
ekledigi yeni alanlar modele zarar vermez. ``model_dump()`` = ``--json`` / MCP
semasi (tek dogruluk kaynagi).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = [
    "Article",
    "Benchmark",
    "Company",
    "Diversification",
    "MacroBriefing",
    "MarketPulse",
    "NewsDigest",
    "NewsDigestItem",
    "NewsHeadline",
    "PerformerRow",
    "Performers",
    "PortfolioHealth",
    "PulseRow",
    "Quote",
    "Risk",
    "TickerBriefing",
    "Trend",
]


class _Lenient(BaseModel):
    """Bilinmeyen alanlara toleransli temel model."""

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# H2 — fetch_article
# ---------------------------------------------------------------------------


class Article(_Lenient):
    """URL -> duz metin sonucu.

    ``error`` alanlari: ``unsupported_scheme``, ``blocked_host``, ``http_404``,
    ``http_403``, ``http_<status>``, ``too_large``, ``unsupported_type``.
    Icerik cikarilamazsa (JS render) ``content_available: false, needs_js: true``.
    """

    url: str
    resolved_url: str | None = None
    title: str | None = None
    text: str = ""
    content_available: bool = False
    needs_js: bool = False
    truncated: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# H1 — news_digest
# ---------------------------------------------------------------------------


class NewsDigestItem(_Lenient):
    """Tek haber + (opsiyonel) cekilmis icerik."""

    title: str | None = None
    url: str | None = None
    published_at: str | None = None
    content: str | None = None
    content_available: bool = False
    fetch_error: str | None = None


class NewsDigest(_Lenient):
    """Ticker haber ozeti. 0 haber -> ``items: []`` (hata DEGIL)."""

    ticker: str
    generated_at: str
    items: list[NewsDigestItem] = []
    requested: int = 0
    fetched: int = 0
    failed: int = 0


# ---------------------------------------------------------------------------
# H3 — ticker_briefing
# ---------------------------------------------------------------------------


class Quote(_Lenient):
    """Anlik fiyat ozeti (is_stale / islem yoksa tum alanlar ``None``)."""

    price: float | None = None
    change_pct: float | None = None
    market_status: str | None = None


class Company(_Lenient):
    """Sirket profili ozeti."""

    name: str | None = None
    sector: str | None = None


class Trend(_Lenient):
    """Donem trendi: degisim yuzdesi + sparkline (son 30 kapanis)."""

    period: str | None = None
    change_pct: float | None = None
    sparkline: list[float] = []


class NewsHeadline(_Lenient):
    """Baslik + link (iceriksiz — briefing hiz odaklidir)."""

    title: str | None = None
    url: str | None = None


class TickerBriefing(_Lenient):
    """Ticker tek bakista: fiyat + profil + trend + son haberler (4 backend cagrisi)."""

    ticker: str
    generated_at: str
    quote: Quote | None = None
    company: Company | None = None
    trend: Trend | None = None
    news: list[NewsHeadline] = []


# ---------------------------------------------------------------------------
# H4 — market_pulse
# ---------------------------------------------------------------------------


class PulseRow(_Lenient):
    """Ozet satiri (kazanan/kaybeden/hacim/populer)."""

    ticker: str | None = None
    change_pct: float | None = None
    volume: float | None = None
    count: int | None = None


class MarketPulse(_Lenient):
    """Piyasa durumu: acik/kapali + kazananlar + kaybedenler + populer + hacim."""

    market_open: bool | None = None
    next_open_at: str | None = None
    holiday: bool | None = None
    gainers: list[PulseRow] = []
    losers: list[PulseRow] = []
    most_popular: list[PulseRow] = []
    volume_leaders: list[PulseRow] = []
    generated_at: str


# ---------------------------------------------------------------------------
# H5 — portfolio_health
# ---------------------------------------------------------------------------


class PerformerRow(_Lenient):
    """En iyi/en kotu hisse satiri."""

    ticker: str | None = None
    return_pct: float | None = None


class Performers(_Lenient):
    """En iyi / en kotu hisseler."""

    top: list[PerformerRow] = []
    bottom: list[PerformerRow] = []


class Risk(_Lenient):
    """Risk metrikleri: oynaklik, maksimum dusus, sharpe."""

    volatility: float | None = None
    max_drawdown: float | None = None
    sharpe: float | None = None


class Benchmark(_Lenient):
    """XU100 karsilastirmasi."""

    ticker: str | None = None
    portfolio_return_pct: float | None = None
    benchmark_return_pct: float | None = None
    diff_pct: float | None = None


class Diversification(_Lenient):
    """Varlik sinifi dagilimi (yuzde)."""

    stocks: float | None = None
    forex: float | None = None
    metals: float | None = None


class PortfolioHealth(_Lenient):
    """Portfoy sagligi ozeti (5 backend cagrisi, JWT).

    Kismi sonuc ilkesi: tek analiz ucu basarisizsa ilgili alan ``None`` olur,
    paket doner. Portfoy yoksa (404) helper gercek hata firlatir.
    """

    portfolio_id: str
    total_value: float = 0.0
    pnl: float | None = None
    pnl_pct: float | None = None
    performers: Performers | None = None
    risk: Risk | None = None
    benchmark: Benchmark | None = None
    diversification: Diversification | None = None


# ---------------------------------------------------------------------------
# H6 — macro_briefing
# ---------------------------------------------------------------------------


class MacroBriefing(_Lenient):
    """Makro manzara: doviz + altin + FRED serileri (3 backend cagrisi, JWT).

    Backend degerleri string + Turk virgullu olabilir; helper float'a
    normalize eder (``"40,25"`` -> ``40.25``).
    """

    currency: dict[str, float] = {}
    gold: dict[str, float] = {}
    macro: dict[str, float] = {}
    generated_at: str
