"""92 MCP tool handler'i — SDK resource metoduyla 1:1 (mcp-design.md Bölüm 2).

Ilkeler:
- Her tool TEK is yapar: SDK metodunu cagirir, ciktiyi formatlar
  (``format.py``), hatayi ``errors.to_tool_error`` ile cevirir.
- SENKRON ``FlorenceClient`` kullanilir; FastMCP her handler'i
  ``run_in_thread=True`` ile ayri thread'de calistirir -> event loop
  bloklanmaz (mcp-design.md Bölüm 1.3, implementasyon karari).
- ``analysis_generate_report`` per-call ``MCP_REPORT_TIMEOUT`` (default 180s),
  ``analysis_download_report`` ``MCP_REPORT_DOWNLOAD_TIMEOUT`` (default 60s)
  ile korunur (Bölüm 4.1/4.3). Timeout degisimi kilit altinda yapilir
  (eszamanli tool cagrilari guvenli).
- Yikici tool'lar (``confirm`` gerekli) ``confirm=true`` olmadan REDDEDILIR
  (Bölüm 2.4 savunma hatti).
- ``bots_create`` sifresi ciktiya GIRMEZ (``format.mask_bot_password``;
  gercek deger token store'a yazilir).
"""

from __future__ import annotations

import contextlib
import functools
import threading
from collections.abc import Iterator
from typing import Any

import httpx

from .auth import AuthContext
from .config import get_report_download_timeout, get_report_timeout
from .errors import ToolError, to_tool_error
from .files import base64_payload, write_bytes
from .format import json_result, mask_bot_password, text_result
from .registry import TOOLS, ToolSpec, spec_by_name

__all__ = ["ToolHandlers"]

#: Uzun isteklerde degistirilen http timeout'u korumak icin kilit (tek client,
#: eszamanli tool cagrilari olabilir).
_TIMEOUT_LOCK = threading.Lock()


def tool_handler(fn):
    """SDK/beklenmeyen hatalari ``ToolError``'a ceviren handler sarmalayici."""

    @functools.wraps(fn)
    def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(self, *args, **kwargs)
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001 — MCP yuzeyine cevrilir
            raise to_tool_error(exc) from exc

    return wrapper


def _jsonable(data: Any) -> Any:
    """Pydantic modelleri (TokenPair vb.) JSON serilestirilebilir hale getirir."""
    if hasattr(data, "model_dump"):
        return data.model_dump()
    if isinstance(data, dict):
        return {k: _jsonable(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_jsonable(item) for item in data]
    return data


def _result_for(data: Any):
    """Metin veya JSON donusu ayirt eder (SDK normalize edilmis donus)."""
    if isinstance(data, str):
        return text_result(data)
    return json_result(_jsonable(data))


def _require_confirm(confirm: bool, spec: ToolSpec) -> None:
    """``confirm=true`` zorunlulugunu uygular (Bölüm 2.4 savunma hatti)."""
    if not confirm:
        raise ToolError(
            f"Onay gerekli: '{spec.name}' kalici/geri alinamaz bir islemdir; "
            "kullanici onayi olmadan cagirma. confirm=true ile tekrar dene."
        )


@contextlib.contextmanager
def _client_read_timeout(client: Any, seconds: float) -> Iterator[None]:
    """Tek cagri icin http read timeout'unu gecici olarak degistirir."""
    http = client._http  # httpx.Client / AsyncClient
    with _TIMEOUT_LOCK:
        old = http.timeout
        http.timeout = httpx.Timeout(
            connect=old.connect, read=seconds, write=old.write, pool=old.pool
        )
        try:
            yield
        finally:
            http.timeout = old


class ToolHandlers:
    """92 tool handler'i — her metod adi registry'deki tool adiyla birebir."""

    def __init__(self, client: Any, auth_context: AuthContext) -> None:
        self.client = client
        self.auth = auth_context

    # ------------------------------------------------------------------
    # Auth (10)
    # ------------------------------------------------------------------
    @tool_handler
    def auth_login(self, username: str, password: str):
        """Kullanici adi + sifre ile oturum ac; token'lar store'a yazilir."""
        return json_result(_jsonable(self.client.auth.login(username, password)))

    @tool_handler
    def auth_logout(self):
        """Oturumu kapat; refresh token'i iptal et, store'u temizle."""
        return json_result(_jsonable(self.client.auth.logout()))

    @tool_handler
    def auth_register(self, username: str, email: str, password: str):
        """Yeni kullanici kaydi (public)."""
        return json_result(_jsonable(self.client.auth_res.register(username, email, password)))

    @tool_handler
    def auth_verify_email(self, token: str):
        """E-posta dogrulama token'ini onayla (public)."""
        return json_result(_jsonable(self.client.auth_res.verify_email(token)))

    @tool_handler
    def auth_resend_verification(self, username_or_email: str):
        """Dogrulama mailini yeniden gonder (public)."""
        return json_result(_jsonable(self.client.auth_res.resend_verification(username_or_email)))

    @tool_handler
    def auth_change_password(self, current_password: str, new_password: str):
        """Sifre degistir; tum refresh token'lar iptal olur."""
        return json_result(
            _jsonable(self.client.auth_res.change_password(current_password, new_password))
        )

    @tool_handler
    def auth_change_email(self, new_email: str, current_password: str):
        """E-posta degistir; tum refresh token'lar iptal olur."""
        return json_result(
            _jsonable(self.client.auth_res.change_email(new_email, current_password))
        )

    @tool_handler
    def auth_change_username(self, new_username: str, current_password: str):
        """Kullanici adi degistir; tum refresh token'lar iptal olur."""
        return json_result(
            _jsonable(self.client.auth_res.change_username(new_username, current_password))
        )

    @tool_handler
    def auth_delete_account(self, confirm: bool = False):
        """Hesabi kalici olarak siler — confirm=true zorunludur."""
        _require_confirm(confirm, _spec("auth_delete_account"))
        return json_result(_jsonable(self.client.auth_res.delete()))

    @tool_handler
    def auth_status(self):
        """Bagli olunan kimligi soyler (API cagrisi yapmaz)."""
        return json_result(self.auth.summary())

    # ------------------------------------------------------------------
    # Account (6)
    # ------------------------------------------------------------------
    @tool_handler
    def account_profile(self):
        return json_result(_jsonable(self.client.user.profile()))

    @tool_handler
    def account_update_avatar(self, avatar_id: str):
        return json_result(_jsonable(self.client.user.update_avatar(avatar_id)))

    @tool_handler
    def account_get_preferences(self):
        return json_result(_jsonable(self.client.user.get_preferences()))

    @tool_handler
    def account_update_preferences(self, prefs: dict[str, Any]):
        return json_result(_jsonable(self.client.user.update_preferences(prefs)))

    @tool_handler
    def account_credits(self):
        return json_result(_jsonable(self.client.user.credits()))

    @tool_handler
    def account_export_data(self):
        return json_result(_jsonable(self.client.user.export_data()))

    # ------------------------------------------------------------------
    # Market (11)
    # ------------------------------------------------------------------
    @tool_handler
    def market_list_companies(self, sort: str = "alphabetical", offset: int = 0, limit: int = 50):
        return json_result(
            _jsonable(self.client.market.companies(sort=sort, offset=offset, limit=limit))
        )

    @tool_handler
    def market_list_tickers(self, sort: str = "alphabetical", offset: int = 0, limit: int = 50):
        return json_result(
            _jsonable(self.client.market.tickers(sort=sort, offset=offset, limit=limit))
        )

    @tool_handler
    def market_search_companies(self, query: str):
        return json_result(_jsonable(self.client.market.search_companies(query)))

    @tool_handler
    def market_company_info(self, ticker: str, format: str = "json"):
        if format == "md":
            return _result_for(self.client.market.company_info_md(ticker))
        return json_result(_jsonable(self.client.market.company_info(ticker)))

    @tool_handler
    def market_companies_summary(
        self, limit: int = 50, offset: int = 0, sort: str = "popular", tickers: str | None = None
    ):
        return json_result(
            _jsonable(
                self.client.market.companies_summary(
                    limit=limit, offset=offset, sort=sort, tickers=tickers
                )
            )
        )

    @tool_handler
    def market_news(self, ticker: str, amount: int = 10):
        return json_result(_jsonable(self.client.market.news(ticker, amount=amount)))

    @tool_handler
    def market_price_current(self, ticker: str, interval: str = "5m"):
        return json_result(_jsonable(self.client.market.current_price(ticker, interval=interval)))

    @tool_handler
    def market_price_history(self, ticker: str, period: str = "1mo", interval: str = "1d"):
        return json_result(
            _jsonable(self.client.market.price_history(ticker, period=period, interval=interval))
        )

    @tool_handler
    def market_status(self):
        return json_result(_jsonable(self.client.market.market_status()))

    @tool_handler
    def market_stats_top(self, limit: int = 50):
        return json_result(_jsonable(self.client.market.stats_top(limit=limit)))

    @tool_handler
    def market_stats(self, ticker: str):
        return json_result(_jsonable(self.client.market.stats(ticker)))

    # ------------------------------------------------------------------
    # Economy (6)
    # ------------------------------------------------------------------
    @tool_handler
    def economy_gold_prices(self):
        return json_result(_jsonable(self.client.economy.gold_prices()))

    @tool_handler
    def economy_silver_price(self):
        return json_result(_jsonable(self.client.economy.silver_price()))

    @tool_handler
    def economy_platinum_price(self):
        return json_result(_jsonable(self.client.economy.platinum_price()))

    @tool_handler
    def economy_palladium_price(self):
        return json_result(_jsonable(self.client.economy.palladium_price()))

    @tool_handler
    def economy_currency(self, symbols: str | None = None):
        return json_result(_jsonable(self.client.economy.currency(symbols=symbols)))

    @tool_handler
    def economy_macroeconomy(self):
        return json_result(_jsonable(self.client.economy.macroeconomy()))

    # ------------------------------------------------------------------
    # Portfolio (24)
    # ------------------------------------------------------------------
    @tool_handler
    def portfolio_add_favorite(self, ticker: str):
        return json_result(_jsonable(self.client.portfolio.add_favorite(ticker)))

    @tool_handler
    def portfolio_remove_favorite(self, ticker: str):
        return json_result(_jsonable(self.client.portfolio.remove_favorite(ticker)))

    @tool_handler
    def portfolio_list_favorites(self):
        return json_result(_jsonable(self.client.portfolio.favorites()))

    @tool_handler
    def portfolio_create(self, name: str, initial_balance: float):
        return json_result(_jsonable(self.client.portfolio.create_portfolio(name, initial_balance)))

    @tool_handler
    def portfolio_list(self):
        return json_result(_jsonable(self.client.portfolio.list_portfolios()))

    @tool_handler
    def portfolio_get(self, portfolio_id: str):
        return json_result(_jsonable(self.client.portfolio.get_portfolio(portfolio_id)))

    @tool_handler
    def portfolio_rename(self, portfolio_id: str, name: str):
        return json_result(_jsonable(self.client.portfolio.rename_portfolio(portfolio_id, name)))

    @tool_handler
    def portfolio_delete(self, portfolio_id: str, confirm: bool = False):
        _require_confirm(confirm, _spec("portfolio_delete"))
        return json_result(_jsonable(self.client.portfolio.delete_portfolio(portfolio_id)))

    @tool_handler
    def portfolio_duplicate(self, portfolio_id: str, name: str):
        return json_result(_jsonable(self.client.portfolio.duplicate_portfolio(portfolio_id, name)))

    @tool_handler
    def portfolio_list_transactions(
        self,
        portfolio_id: str,
        ticker: str | None = None,
        tx_type: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ):
        return json_result(
            _jsonable(
                self.client.portfolio.get_transactions(
                    portfolio_id, ticker=ticker, tx_type=tx_type, start=start, end=end
                )
            )
        )

    @tool_handler
    def portfolio_add_transaction(self, portfolio_id: str, ticker: str, type: str, quantity: float):
        return json_result(
            _jsonable(
                self.client.portfolio.add_transaction(
                    portfolio_id, ticker, type=type, quantity=quantity
                )
            )
        )

    @tool_handler
    def portfolio_update_transaction(
        self,
        portfolio_id: str,
        tx_id: str,
        price: float | None = None,
        quantity: float | None = None,
    ):
        return json_result(
            _jsonable(
                self.client.portfolio.update_transaction(
                    portfolio_id, tx_id, price=price, quantity=quantity
                )
            )
        )

    @tool_handler
    def portfolio_undo_transaction(self, portfolio_id: str, confirm: bool = False):
        _require_confirm(confirm, _spec("portfolio_undo_transaction"))
        return json_result(_jsonable(self.client.portfolio.undo_transaction(portfolio_id)))

    @tool_handler
    def portfolio_valuation(self, portfolio_id: str):
        return json_result(_jsonable(self.client.portfolio.valuation(portfolio_id)))

    @tool_handler
    def portfolio_diversification(self, portfolio_id: str):
        return json_result(_jsonable(self.client.portfolio.diversification(portfolio_id)))

    @tool_handler
    def portfolio_performers(self, portfolio_id: str, top_n: int = 5):
        return json_result(_jsonable(self.client.portfolio.performers(portfolio_id, top_n=top_n)))

    @tool_handler
    def portfolio_history(self, portfolio_id: str, period: str = "1mo"):
        return json_result(_jsonable(self.client.portfolio.history(portfolio_id, period=period)))

    @tool_handler
    def portfolio_returns(self, portfolio_id: str, period: str = "1mo"):
        return json_result(_jsonable(self.client.portfolio.returns(portfolio_id, period=period)))

    @tool_handler
    def portfolio_risk(self, portfolio_id: str, period: str = "1y"):
        return json_result(_jsonable(self.client.portfolio.risk(portfolio_id, period=period)))

    @tool_handler
    def portfolio_benchmark(self, portfolio_id: str, ticker: str = "XU100"):
        return json_result(_jsonable(self.client.portfolio.benchmark(portfolio_id, ticker=ticker)))

    @tool_handler
    def portfolio_performance(self, portfolio_id: str):
        return json_result(_jsonable(self.client.portfolio.performance(portfolio_id)))

    @tool_handler
    def portfolio_stats(self, portfolio_id: str):
        return json_result(_jsonable(self.client.portfolio.stats(portfolio_id)))

    @tool_handler
    def portfolio_snapshot(self, portfolio_id: str):
        return json_result(_jsonable(self.client.portfolio.snapshot(portfolio_id)))

    @tool_handler
    def portfolio_export_csv(self, portfolio_id: str):
        """Ham CSV metni doner (JSON degil)."""
        return _result_for(self.client.portfolio.export_csv(portfolio_id))

    # ------------------------------------------------------------------
    # Analysis (13)
    # ------------------------------------------------------------------
    @tool_handler
    def analysis_per_day_cost(self):
        return json_result(_jsonable(self.client.analysis.per_day_cost()))

    @tool_handler
    def analysis_estimate_cost(self, ticker: str, days: int):
        return json_result(_jsonable(self.client.analysis.estimate_cost(ticker, days)))

    @tool_handler
    def analysis_list_simulations(self, limit: int = 20, offset: int = 0):
        return json_result(
            _jsonable(self.client.analysis.simulation_history(limit=limit, offset=offset))
        )

    @tool_handler
    def analysis_get_simulation(self, sim_id: int):
        return json_result(_jsonable(self.client.analysis.simulation_detail(sim_id)))

    @tool_handler
    def analysis_simulate(
        self, ticker: str, days: int, bounds: str = "0.05", target: str | None = None
    ):
        return json_result(
            _jsonable(self.client.analysis.simulate(ticker, days, bounds=bounds, target=target))
        )

    @tool_handler
    def analysis_generate_report(self, ticker: str, type: str, purpose: str | None = None):
        """Rapor uretir — kredi harcar; MCP_REPORT_TIMEOUT (default 180s)."""
        with _client_read_timeout(self.client, get_report_timeout()):
            return json_result(
                _jsonable(self.client.analysis.generate_report(ticker, type, purpose=purpose))
            )

    @tool_handler
    def analysis_report_info(self):
        return json_result(_jsonable(self.client.analysis.report_info()))

    @tool_handler
    def analysis_list_reports(self, sort: str = "created_at", order: str = "desc"):
        return json_result(
            _jsonable(self.client.analysis.report_history(sort=sort, order=order))
        )

    @tool_handler
    def analysis_search_reports(
        self,
        q: str,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = 20,
        offset: int = 0,
    ):
        return json_result(
            _jsonable(
                self.client.analysis.search_reports(
                    q, sort=sort, order=order, limit=limit, offset=offset
                )
            )
        )

    @tool_handler
    def analysis_get_report(self, report_id: int):
        return json_result(_jsonable(self.client.analysis.get_report(report_id)))

    @tool_handler
    def analysis_download_report(self, report_id: int, ftype: str, dest_path: str | None = None):
        """Raporu indir: md metin, docx/pdf base64; dest_path verilirse yazilir."""
        with _client_read_timeout(self.client, get_report_download_timeout()):
            content = self.client.analysis.download_report(report_id, ftype)
        if dest_path:
            return json_result(write_bytes(content, dest_path, fmt=ftype))
        if ftype == "md":
            return text_result(content.decode("utf-8", errors="replace"))
        return json_result(base64_payload(content, ftype))

    @tool_handler
    def analysis_fit_stocks(
        self,
        horizon: str = "long",
        profitability: str = "high",
        risk_tolerance: str = "medium",
        limit: int = 5,
    ):
        return json_result(
            _jsonable(
                self.client.analysis.fit_stocks(
                    horizon=horizon,
                    profitability=profitability,
                    risk_tolerance=risk_tolerance,
                    limit=limit,
                )
            )
        )

    @tool_handler
    def analysis_portfolio_profile(self, tickers: list[str], limit: int = 5):
        return json_result(
            _jsonable(self.client.analysis.portfolio_profile(tickers, limit=limit))
        )

    # ------------------------------------------------------------------
    # Bots (3)
    # ------------------------------------------------------------------
    @tool_handler
    def bots_create(self, username: str, password: str | None = None):
        """Bot olusturur; tek seferlik sifre ciktiya GIRMEZ (store'a yazilir)."""
        data = self.client.bots.create(username, password=password)
        return json_result(mask_bot_password(_jsonable(data)))

    @tool_handler
    def bots_list(self):
        return json_result(_jsonable(self.client.bots.list()))

    @tool_handler
    def bots_delete(self, bot_id: int, confirm: bool = False):
        _require_confirm(confirm, _spec("bots_delete"))
        return json_result(_jsonable(self.client.bots.delete(bot_id)))

    # ------------------------------------------------------------------
    # Export (5)
    # ------------------------------------------------------------------
    @tool_handler
    def export_create(self, year: int, format: str = "csv"):
        return json_result(_jsonable(self.client.export.create_export(year, format=format)))

    @tool_handler
    def export_status(self, export_id: int):
        return json_result(_jsonable(self.client.export.get_export(export_id)))

    @tool_handler
    def export_list(self):
        return json_result(_jsonable(self.client.export.list_exports()))

    @tool_handler
    def export_wait(self, export_id: int, poll_interval: float = 3.0, timeout: float = 300.0):
        """Ready/sent olana kadar poll eder; timeout asilirsa ToolError."""
        return json_result(
            _jsonable(
                self.client.export.wait_export(
                    export_id, poll_interval=poll_interval, timeout=timeout
                )
            )
        )

    @tool_handler
    def export_download(self, token_or_url: str, dest_path: str | None = None):
        """Public token ile indir; dest_path verilirse yazilir, yoksa base64."""
        content = self.client.export.download(token_or_url)
        if dest_path:
            return json_result(write_bytes(content, dest_path, fmt="gzip"))
        return json_result(base64_payload(content, "gzip"))

    # ------------------------------------------------------------------
    # Misc (14)
    # ------------------------------------------------------------------
    @tool_handler
    def misc_ipos_upcoming(self, after: str | None = None):
        return json_result(_jsonable(self.client.misc.ipos_upcoming(after=after)))

    @tool_handler
    def misc_ipos_draft(self, after: str | None = None):
        return json_result(_jsonable(self.client.misc.ipos_draft(after=after)))

    @tool_handler
    def misc_ipos_active(self, after: str | None = None):
        return json_result(_jsonable(self.client.misc.ipos_active(after=after)))

    @tool_handler
    def misc_ipo_detail(self, slug: str):
        return json_result(_jsonable(self.client.misc.ipo_detail(slug)))

    @tool_handler
    def misc_legal(self, policy: str, lang: str = "tr"):
        return _result_for(self.client.misc.legal(policy, lang=lang))

    @tool_handler
    def misc_legal_all(self, lang: str = "tr"):
        return _result_for(self.client.misc.legal_all(lang=lang))

    @tool_handler
    def misc_about(self, lang: str = "tr"):
        return _result_for(self.client.misc.about(lang=lang))

    @tool_handler
    def misc_version(self):
        return json_result(_jsonable(self.client.misc.version()))

    @tool_handler
    def misc_contact(self):
        return json_result(_jsonable(self.client.misc.contact()))

    @tool_handler
    def misc_contributors(self):
        return json_result(_jsonable(self.client.misc.contributors()))

    @tool_handler
    def misc_maintenance(self):
        return json_result(_jsonable(self.client.misc.maintenance()))

    @tool_handler
    def misc_health(self):
        return json_result(_jsonable(self.client.misc.health()))

    @tool_handler
    def misc_announcements(self):
        return json_result(_jsonable(self.client.misc.announcements()))

    @tool_handler
    def misc_announcement(self, announcement_id: int):
        return json_result(_jsonable(self.client.misc.announcement(announcement_id)))


def _spec(name: str) -> ToolSpec:
    """Registry'den spec; eksikse ic hata (gelistirme hatasi)."""
    spec = spec_by_name(name)
    if spec is None:
        raise ToolError(f"Ic hata: '{name}' registry'de yok.")
    return spec


#: Registry ile handler eslesmesini dogrula (import zamani, gelistirme guvencesi).
def _validate_handlers() -> None:
    """Her registry tool'unun bir handler metodu oldugunu dogrular."""
    missing = [spec.name for spec in TOOLS if not hasattr(ToolHandlers, spec.name)]
    if missing:
        raise RuntimeError(f"Handler eksik: {missing}")


_validate_handlers()
