"""Resource temsilci testleri: her endpoint grubundan en az 1 (TAMAMEN OFFLINE).

Grup kapsami:
- auth_res: register/change-password/verify-email
- user_res: profile/avatar/preferences/credits
- market_res: companies/price/history/news/status/stats
- economy_res: gold/currency/macroeconomy
- portfolio_res: favorites/portfolios/islemler/analiz
- analysis_res: simulations/reports/fit
- bots_res: create/list/delete
- export_res: ayri dosyada (test_export.py)
- misc_res: ipos/legal/about/version
"""

from __future__ import annotations

import asyncio

import httpx
import respx

from florence import AsyncFlorenceClient, FlorenceClient, MemoryTokenStore
from florence.models import CreditBalance, UserProfile

API = "https://api.florencex.com.tr"
P = f"{API}/api/v1"


# ----------------------------------------------------------------------
# auth_res
# ----------------------------------------------------------------------
def test_auth_res_register_and_verify():
    with respx.mock:
        respx.post(f"{P}/auth/register").mock(
            return_value=httpx.Response(200, json={"message": "Register successful", "user_id": 1, "verification_sent": True})
        )
        respx.get(f"{P}/auth/verify-email").mock(
            return_value=httpx.Response(200, json={"message": "Email verified", "email_verified": True})
        )
        client = FlorenceClient()
        reg = client.auth_res.register("ali", "ali@example.com", "supersecret123")
        ver = client.auth_res.verify_email("tok")
    assert reg["user_id"] == 1
    assert ver["email_verified"] is True


def test_auth_res_change_password_requires_auth():
    with respx.mock:
        route = respx.put(f"{P}/auth/change-password").mock(
            return_value=httpx.Response(200, json={"message": "Password changed successfully"})
        )
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        result = client.auth_res.change_password("eski", "yeni-uzun-sifre")
    assert result["message"].startswith("Password changed")
    assert route.calls.last.request.headers["Authorization"] == "Bearer at-1"


# ----------------------------------------------------------------------
# user_res
# ----------------------------------------------------------------------
def test_user_profile_and_credits():
    profile_json = {
        "username": "ali",
        "email": "ali@example.com",
        "user_type": "user",
        "created_at": "2026-01-01T00:00:00+00:00",
        "email_verified": True,
        "avatar_id": "avatar-3",
        "credits": 24.75,
    }
    with respx.mock:
        respx.get(f"{P}/profile").mock(return_value=httpx.Response(200, json=profile_json))
        respx.get(f"{P}/credits").mock(return_value=httpx.Response(200, json={"credits": 24.75}))
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        profile = client.user.profile()
        balance = client.user.credits()
    assert profile["username"] == "ali"
    # Long-tail pydantic model zorlamasi opsiyonel ve calisiyor:
    assert UserProfile.model_validate(profile).credits == 24.75
    assert CreditBalance.model_validate(balance).credits == 24.75


def test_user_preferences_get_put():
    with respx.mock:
        respx.get(f"{P}/user/preferences").mock(
            return_value=httpx.Response(200, json={"prefs": {"theme": "dark"}})
        )
        respx.put(f"{P}/user/preferences").mock(
            return_value=httpx.Response(200, json={"prefs": {"theme": "dark", "lang": "tr"}})
        )
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        assert client.user.get_preferences()["prefs"]["theme"] == "dark"
        merged = client.user.update_preferences({"lang": "tr"})
        assert merged["prefs"]["lang"] == "tr"


def test_user_update_avatar():
    with respx.mock:
        respx.put(f"{P}/profile/avatar").mock(
            return_value=httpx.Response(200, json={"message": "Avatar updated", "avatar_id": "avatar-5"})
        )
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        result = client.user.update_avatar("avatar-5")
    assert result["avatar_id"] == "avatar-5"


# ----------------------------------------------------------------------
# market_res
# ----------------------------------------------------------------------
def test_market_companies_and_tickers():
    with respx.mock:
        respx.get(f"{P}/bist/companies").mock(
            return_value=httpx.Response(200, json=[{"ticker": "THYAO", "name": "Turk Hava Yollari"}])
        )
        respx.get(f"{P}/bist/tickers").mock(
            return_value=httpx.Response(200, json=[{"ticker": "ASELS"}])
        )
        client = FlorenceClient()
        companies = client.market.companies(sort="popular", limit=10)
        tickers = client.market.tickers()
    assert companies[0]["ticker"] == "THYAO"
    assert tickers[0]["ticker"] == "ASELS"


def test_market_price_history_and_current():
    with respx.mock:
        route = respx.get(url__regex=r".*price/history/THYAO.*").mock(
            return_value=httpx.Response(
                200,
                json=[{"ts": "2026-07-15T00:00:00+00:00", "open": 310.5, "close": 313.4, "volume": 12345678}],
            )
        )
        respx.get(f"{P}/price/current").mock(
            return_value=httpx.Response(
                200,
                json={"ticker": "THYAO", "price": 313.4, "change_pct": 0.93, "market_status": "open"},
            )
        )
        client = FlorenceClient()
        history = client.market.price_history("THYAO", period="1mo", interval="1d")
        quote = client.market.current_price("THYAO", interval="5m")
    assert history[0]["close"] == 313.4
    assert quote["market_status"] == "open"
    assert route.called


def test_market_news_requires_auth():
    with respx.mock:
        route = respx.get(url__regex=r".*news/THYAO.*").mock(
            return_value=httpx.Response(200, json=[{"title": "THYAO haberi", "url": "https://x"}])
        )
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        news = client.market.news("THYAO", amount=5)
    assert news[0]["title"] == "THYAO haberi"
    assert route.calls.last.request.headers["Authorization"] == "Bearer at-1"


def test_market_status_and_stats():
    with respx.mock:
        respx.get(f"{P}/market/status").mock(
            return_value=httpx.Response(200, json={"open": True, "next_open_at": "2026-08-15T10:00:00+03:00", "holiday": False})
        )
        respx.get(f"{P}/stats/top").mock(return_value=httpx.Response(200, json=[{"ticker": "THYAO", "count": 99}]))
        respx.get(f"{P}/stats/THYAO").mock(return_value=httpx.Response(200, json={"ticker": "THYAO", "views": 5}))
        client = FlorenceClient()
        status = client.market.market_status()
        top = client.market.stats_top(limit=10)
        stat = client.market.stats("THYAO")
    assert status["open"] is True
    assert top[0]["ticker"] == "THYAO"
    assert stat["views"] == 5


def test_market_company_info_and_search():
    with respx.mock:
        respx.get(f"{P}/companies/search").mock(
            return_value=httpx.Response(200, json=[{"ticker": "THYAO", "name": "Turk Hava Yollari"}])
        )
        respx.get(url__regex=r".*companies/info/ASELS.*").mock(
            return_value=httpx.Response(200, json={"ticker": "ASELS", "longName": "Aselsan"})
        )
        client = FlorenceClient()
        found = client.market.search_companies("hava")
        info = client.market.company_info("ASELS")
    assert found[0]["ticker"] == "THYAO"
    assert info["longName"] == "Aselsan"


# ----------------------------------------------------------------------
# economy_res
# ----------------------------------------------------------------------
def test_economy_gold_currency_macro():
    with respx.mock:
        respx.get(f"{P}/economy/gold-prices").mock(
            return_value=httpx.Response(200, json=[{"Type": "gram-altin", "Buying": "40,25", "Selling": "40,75"}])
        )
        respx.get(f"{P}/economy/currency").mock(
            return_value=httpx.Response(200, json={"USD": {"buying": "42,10"}})
        )
        respx.get(f"{P}/macroeconomy").mock(
            return_value=httpx.Response(200, json={"series": [{"id": "GDP", "value": 1.2}]})
        )
        client = FlorenceClient()
        gold = client.economy.gold_prices()
        usd = client.economy.currency(symbols="USD")
        macro = client.economy.macroeconomy()
    assert gold[0]["Buying"] == "40,25"  # backend TR string degeri korunur
    assert usd["USD"]["buying"] == "42,10"
    assert macro["series"][0]["id"] == "GDP"


def test_economy_precious_metals():
    with respx.mock:
        respx.get(f"{P}/economy/silver-price").mock(return_value=httpx.Response(200, json={"gumus": {"Buying": "30,5"}}))
        respx.get(f"{P}/economy/gram-platinum-price").mock(
            return_value=httpx.Response(200, json={"gram-platin": {"Buying": "950"}})
        )
        respx.get(f"{P}/economy/gram-palladium-price").mock(
            return_value=httpx.Response(200, json={"gram-paladyum": {"Buying": "1100"}})
        )
        client = FlorenceClient()
        assert client.economy.silver_price()["gumus"]["Buying"] == "30,5"
        assert client.economy.platinum_price()["gram-platin"]["Buying"] == "950"
        assert client.economy.palladium_price()["gram-paladyum"]["Buying"] == "1100"


# ----------------------------------------------------------------------
# portfolio_res
# ----------------------------------------------------------------------
def test_portfolio_favorites_crud():
    with respx.mock:
        respx.post(f"{P}/favorites/THYAO").mock(
            return_value=httpx.Response(200, json={"message": "Added favorite THYAO or already been added"})
        )
        respx.delete(f"{P}/favorites/THYAO").mock(
            return_value=httpx.Response(200, json={"message": "Removed THYAO from favorites"})
        )
        respx.get(f"{P}/favorites").mock(return_value=httpx.Response(200, json=["THYAO", "ASELS"]))
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        assert client.portfolio.add_favorite("THYAO")["message"].startswith("Added favorite")
        assert client.portfolio.remove_favorite("THYAO")["message"].startswith("Removed")
        assert client.portfolio.favorites() == ["THYAO", "ASELS"]


def test_portfolio_crud_and_analytics():
    pid = "port-abc123"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/portfolios") and request.method == "POST":
            return httpx.Response(200, json={"metadata": {"id": pid, "name": "Test", "initial_balance": 100000.0}})
        if path.endswith(f"/portfolios/{pid}/valuation"):
            return httpx.Response(200, json={"total_value": 105000.0, "pnl": 5000.0})
        if path.endswith(f"/portfolios/{pid}/returns"):
            return httpx.Response(200, json={"absolute": 5000.0, "total_pct": 0.05})
        if path.endswith(f"/portfolios/{pid}/risk"):
            return httpx.Response(200, json={"volatility": 0.02, "max_drawdown": -0.04})
        return httpx.Response(404, json={"detail": "unmocked"})

    store = MemoryTokenStore()
    store.set_tokens("at-1", "rt-1")
    client = FlorenceClient(token_store=store, transport=httpx.MockTransport(handler))
    created = client.portfolio.create_portfolio("Test", 100000.0)
    valuation = client.portfolio.valuation(pid)
    returns = client.portfolio.returns(pid, period="1mo")
    risk = client.portfolio.risk(pid, period="1y")
    assert created["metadata"]["id"] == pid
    assert valuation["total_value"] == 105000.0
    assert returns["total_pct"] == 0.05
    assert risk["max_drawdown"] == -0.04


def test_portfolio_transactions_flow():
    pid = "port-1"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith(f"/portfolios/{pid}/transactions") and request.method == "POST":
            body = request.read().decode()
            assert '"ticker":"THYAO"' in body and '"type":"BUY"' in body
            return httpx.Response(200, json={"id": "tx-1", "ticker": "THYAO", "type": "BUY", "quantity": 10})
        if path.endswith(f"/portfolios/{pid}/transactions/undo"):
            return httpx.Response(200, json={"message": "Undone"})
        if path.endswith(f"/portfolios/{pid}/transactions/tx-1") and request.method == "PUT":
            return httpx.Response(200, json={"id": "tx-1", "quantity": 5})
        return httpx.Response(404, json={"detail": "unmocked"})

    store = MemoryTokenStore()
    store.set_tokens("at-1", "rt-1")
    client = FlorenceClient(token_store=store, transport=httpx.MockTransport(handler))
    tx = client.portfolio.add_transaction(pid, "THYAO", "BUY", 10)
    assert tx["id"] == "tx-1"
    assert client.portfolio.update_transaction(pid, "tx-1", quantity=5)["quantity"] == 5
    assert client.portfolio.undo_transaction(pid)["message"] == "Undone"


def test_portfolio_export_csv_raw():
    pid = "port-1"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ticker,quantity,price\nTHYAO,10,310.5\n")

    store = MemoryTokenStore()
    store.set_tokens("at-1", "rt-1")
    client = FlorenceClient(token_store=store, transport=httpx.MockTransport(handler))
    csv_text = client.portfolio.export_csv(pid)
    assert "ticker,quantity,price" in csv_text


# ----------------------------------------------------------------------
# analysis_res
# ----------------------------------------------------------------------
def test_analysis_simulations():
    with respx.mock:
        respx.get(f"{P}/simulations/per-day-cost").mock(return_value=httpx.Response(200, json={"per_day_cost": 0.005}))
        respx.get(url__regex=r".*simulations/estimate-cost/THYAO.*").mock(
            return_value=httpx.Response(200, json={"estimated_cost": 0.15, "days": 30})
        )
        respx.get(url__regex=r".*simulations/THYAO.*").mock(
            return_value=httpx.Response(
                200,
                json={
                    "prob_above": 0.62,
                    "prob_below": 0.38,
                    "confidence": {"min": 95.2, "max": 118.4, "percent": 0.9, "days": 30, "bounds": "0.05"},
                    "direction": "up",
                    "simulation_id": 9,
                    "ticker": "THYAO",
                    "days": 30,
                    "target": None,
                    "bounds": "0.05",
                    "credits_spend": 0.15,
                    "remaining_credits": 24.6,
                },
            )
        )
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        cost = client.analysis.per_day_cost()
        est = client.analysis.estimate_cost("THYAO", days=30)
        sim = client.analysis.simulate("THYAO", days=30, bounds="0.05")
    assert cost["per_day_cost"] == 0.005
    assert est["days"] == 30
    assert sim["prob_above"] == 0.62
    assert sim["confidence"]["percent"] == 0.9


def test_analysis_reports_generate_and_download():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/reports/generate"):
            return httpx.Response(
                200,
                json={"success": True, "report_id": 12, "credits_spend": 0.25, "remaining_credits": 17.75, "report": "# Rapor", "type": "quick_report"},
            )
        if path.endswith("/reports/download"):
            return httpx.Response(200, content=b"%PDF-1.4 mock", headers={"Content-Type": "application/pdf"})
        return httpx.Response(404, json={"detail": "unmocked"})

    store = MemoryTokenStore()
    store.set_tokens("at-1", "rt-1")
    client = FlorenceClient(token_store=store, transport=httpx.MockTransport(handler))
    gen = client.analysis.generate_report("THYAO", type="quick_report", purpose="Kisa analiz")
    assert gen["report_id"] == 12
    assert gen["credits_spend"] == 0.25

    content = client.analysis.download_report(12, ftype="pdf")
    assert content == b"%PDF-1.4 mock"


def test_analysis_report_history_search():
    with respx.mock:
        respx.get(f"{P}/reports/history").mock(
            return_value=httpx.Response(200, json=[{"id": 1, "ticker": "THYAO", "type": "quick_report", "created_at": "2026-08-01T10:00:00+00:00"}])
        )
        respx.get(f"{P}/reports/search").mock(
            return_value=httpx.Response(200, json=[{"id": 2, "ticker": "ASELS", "title": "Aselsan analizi", "type": "deep_report"}])
        )
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        history = client.analysis.report_history(sort="ticker", order="asc")
        found = client.analysis.search_reports("asels", limit=5)
    assert history[0]["ticker"] == "THYAO"
    assert found[0]["title"] == "Aselsan analizi"


def test_analysis_fit_stocks():
    with respx.mock:
        respx.post(f"{P}/stocks/fit").mock(
            return_value=httpx.Response(200, json={"results": [{"ticker": "ASELS", "similarity": 0.87}]})
        )
        store = MemoryTokenStore()
        store.set_tokens("at-1", "rt-1")
        client = FlorenceClient(token_store=store)
        result = client.analysis.fit_stocks(horizon="long", profitability="high", risk_tolerance="medium", limit=3)
    assert result["results"][0]["ticker"] == "ASELS"


# ----------------------------------------------------------------------
# bots_res
# ----------------------------------------------------------------------
def test_bots_resource_crud():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/bots") and request.method == "POST":
            return httpx.Response(200, json={"id": 3, "username": "bot-1", "email": "bot-1@bot.florencex.com.tr", "password": "tek-seferlik-sifre"})
        if path.endswith("/bots") and request.method == "GET":
            return httpx.Response(200, json={"bots": [{"id": 3, "username": "bot-1", "created_at": "2026-08-01T00:00:00+00:00", "last_login": None}]})
        if path.endswith("/bots/3") and request.method == "DELETE":
            return httpx.Response(200, json={"message": "Bot 3 deleted"})
        return httpx.Response(404, json={"detail": "unmocked"})

    store = MemoryTokenStore()
    store.set_tokens("at-1", "rt-1")
    client = FlorenceClient(token_store=store, transport=httpx.MockTransport(handler))
    created = client.bots.create("bot-1")
    listed = client.bots.list()
    deleted = client.bots.delete(3)
    assert created["password"] == "tek-seferlik-sifre"
    assert listed["bots"][0]["username"] == "bot-1"
    assert deleted["message"] == "Bot 3 deleted"
    # Not: resource create() durumsuzdur (endpoint'i birebir sarar); sifrenin
    # keyring'e yazilmasi icin auth.create_bot() kisa yolunu kullanin.


# ----------------------------------------------------------------------
# misc_res
# ----------------------------------------------------------------------
def test_misc_ipos_and_legal():
    with respx.mock:
        respx.get(f"{P}/ipos/upcoming").mock(return_value=httpx.Response(200, json=[{"slug": "x", "name": "X A.S."}]))
        respx.get(f"{P}/legal").mock(return_value=httpx.Response(200, json={"policy": "terms", "content": "..."}))
        respx.get(f"{P}/about").mock(return_value=httpx.Response(200, json={"about": "Florence"}))
        respx.get(f"{P}/version").mock(return_value=httpx.Response(200, json={"version": "0.5.7"}))
        client = FlorenceClient()
        upcoming = client.misc.ipos_upcoming()
        terms = client.misc.legal("terms", lang="tr")
        about = client.misc.about(lang="en")
        version = client.misc.version()
    assert upcoming[0]["slug"] == "x"
    assert terms["policy"] == "terms"
    assert about["about"] == "Florence"
    assert version["version"] == "0.5.7"


def test_misc_maintenance_health():
    with respx.mock:
        respx.get(f"{P}/maintenance").mock(return_value=httpx.Response(200, json={"disabled": ["news"]}))
        respx.get(f"{API}/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
        client = FlorenceClient()
        assert client.misc.maintenance()["disabled"] == ["news"]
        assert client.misc.health()["status"] == "ok"


# ----------------------------------------------------------------------
# digest_res
# ----------------------------------------------------------------------
def test_digest_resource_methods():
    with respx.mock:
        respx.get(f"{P}/digest").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "d-1",
                    "date": "2026-08-25",
                    "slot": "morning",
                    "title": "Sabah Özeti",
                    "content": "Piyasalar güne pozitif başladı.",
                    "sections": [{"heading": "BIST 100", "body": "Endeks 10.000 üzerinde."}],
                },
            )
        )
        respx.get(f"{P}/digest?date=2026-08-25&slot=morning").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "d-1",
                    "date": "2026-08-25",
                    "slot": "morning",
                    "title": "Sabah Özeti",
                    "content": "Piyasalar güne pozitif başladı.",
                    "sections": [{"heading": "BIST 100", "body": "Endeks 10.000 üzerinde."}],
                },
            )
        )
        client = FlorenceClient()
        cur = client.digest.current()
        assert cur["id"] == "d-1"
        assert cur["slot"] == "morning"

        by_slot = client.digest.by_date_slot("2026-08-25", "morning")
        assert by_slot["title"] == "Sabah Özeti"


# ----------------------------------------------------------------------
# Asenkron resource kullanim ornekleri
# ----------------------------------------------------------------------
def test_async_resource_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/bist/companies"):
            return httpx.Response(200, json=[{"ticker": "THYAO"}])
        if path.endswith("/economy/gold-prices"):
            return httpx.Response(200, json=[{"Type": "gram-altin", "Buying": "40,25"}])
        if path.endswith("/digest"):
            return httpx.Response(200, json={"id": "d-async", "title": "Bülten"})
        if path.endswith("/auth/login"):
            return httpx.Response(200, json={"access_token": "at-9", "refresh_token": "rt-9", "token_type": "bearer"})
        return httpx.Response(404, json={"detail": "unmocked"})

    async def run() -> None:
        async with AsyncFlorenceClient(transport=httpx.MockTransport(handler)) as client:
            companies = await client.market.companies()
            gold = await client.economy.gold_prices()
            digest = await client.digest.current()
            assert companies[0]["ticker"] == "THYAO"
            assert gold[0]["Buying"] == "40,25"
            assert digest["id"] == "d-async"

    asyncio.run(run())

