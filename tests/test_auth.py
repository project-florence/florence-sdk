"""Auth testleri: login, refresh (single-flight), logout, register, bot akisi,
token persist (injectable store), env override. TAMAMEN OFFLINE (respx)."""

from __future__ import annotations

import asyncio
import threading

import httpx
import pytest
import respx

from florence import (
    AsyncFlorenceClient,
    AuthError,
    FlorenceAPIError,
    FlorenceClient,
    MemoryTokenStore,
)
from florence.models import TokenPair

API = "https://api.florencex.com.tr"
P = f"{API}/api/v1"


def _login_response(access: str = "at-1", refresh: str = "rt-1") -> dict:
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


# ----------------------------------------------------------------------
# Login
# ----------------------------------------------------------------------
def test_login_success_stores_tokens():
    store = MemoryTokenStore()
    with respx.mock:
        route = respx.post(f"{P}/auth/login").mock(return_value=httpx.Response(200, json=_login_response()))
        client = FlorenceClient(token_store=store)
        pair = client.auth.login("kullanici", "sifre12345")

    assert isinstance(pair, TokenPair)
    assert pair.access_token == "at-1"
    assert pair.refresh_token == "rt-1"
    assert store.get_access_token() == "at-1"
    assert store.get_refresh_token() == "rt-1"
    # Form-encoded OAuth2 payload dogrulanir.
    body = route.calls.last.request.content.decode()
    assert "username=kullanici" in body
    assert "grant_type=password" in body
    assert "password=sifre12345" in body


def test_login_failure_maps_error_code():
    store = MemoryTokenStore()
    with respx.mock:
        respx.post(f"{P}/auth/login").mock(
            return_value=httpx.Response(400, json={"detail": "error_login_failed"})
        )
        client = FlorenceClient(token_store=store)
        with pytest.raises(FlorenceAPIError) as exc:
            client.auth.login("kullanici", "yanlis-sifre")
    assert exc.value.status_code == 400
    assert exc.value.code == "error_login_failed"
    assert store.get_access_token() is None  # basarisiz login store'a yazmaz


def test_login_verification_required():
    with respx.mock:
        respx.post(f"{P}/auth/login").mock(
            return_value=httpx.Response(403, json={"detail": "error_email_not_verified"})
        )
        client = FlorenceClient()
        with pytest.raises(FlorenceAPIError) as exc:
            client.auth.login("kullanici", "sifre12345")
    assert exc.value.code == "error_email_not_verified"


# ----------------------------------------------------------------------
# Refresh
# ----------------------------------------------------------------------
def test_refresh_rotates_tokens():
    store = MemoryTokenStore()
    store.set_tokens("eski-at", "eski-rt")
    with respx.mock:
        respx.post(f"{P}/auth/refresh").mock(return_value=httpx.Response(200, json=_login_response("yeni-at", "yeni-rt")))
        client = FlorenceClient(token_store=store)
        pair = client.auth.refresh()
    assert pair.access_token == "yeni-at"
    assert pair.refresh_token == "yeni-rt"
    assert store.get_access_token() == "yeni-at"
    assert store.get_refresh_token() == "yeni-rt"


def test_refresh_without_token_raises_auth_error():
    client = FlorenceClient(token_store=MemoryTokenStore())
    with pytest.raises(AuthError):
        client.auth.refresh()


def test_refresh_failure_raises_auth_error():
    store = MemoryTokenStore()
    store.set_tokens("eski-at", "bayat-rt")
    with respx.mock:
        respx.post(f"{P}/auth/refresh").mock(
            return_value=httpx.Response(401, json={"detail": "Invalid or expired refresh token"})
        )
        client = FlorenceClient(token_store=store)
        with pytest.raises(AuthError) as exc:
            client.auth.refresh()
    assert exc.value.code == "Invalid or expired refresh token"


def test_refresh_single_flight_sync():
    """Eszamanli 2 thread -> tek refresh POST'u."""
    store = MemoryTokenStore()
    store.set_tokens("eski-at", "eski-rt")
    refresh_calls = []
    barrier = threading.Barrier(2)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/refresh"):
            refresh_calls.append(1)
            return httpx.Response(200, json=_login_response("yeni-at", "yeni-rt"))
        return httpx.Response(200, json={"ok": True})

    client = FlorenceClient(
        token_store=store,
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )
    results: list[TokenPair] = []
    errors: list[Exception] = []

    def worker() -> None:
        barrier.wait()
        try:
            results.append(client.auth.refresh())
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(refresh_calls) == 1, "single-flight ihlal: birden fazla refresh POST'u"
    assert all(r.access_token == "yeni-at" for r in results)


# ----------------------------------------------------------------------
# Logout / register / verify
# ----------------------------------------------------------------------
def test_logout_revokes_and_clears_store():
    store = MemoryTokenStore()
    store.set_tokens("at-1", "rt-1")
    with respx.mock:
        route = respx.post(f"{P}/auth/logout").mock(return_value=httpx.Response(200, json={"message": "Logged out"}))
        client = FlorenceClient(token_store=store)
        result = client.auth.logout()
    assert result["message"] == "Logged out"
    assert "rt-1" in route.calls.last.request.content.decode()
    assert store.get_access_token() is None
    assert store.get_refresh_token() is None


def test_register_and_verify_email():
    with respx.mock:
        respx.post(f"{P}/auth/register").mock(
            return_value=httpx.Response(200, json={"message": "Register successful", "user_id": 42, "verification_sent": True})
        )
        respx.get(f"{P}/auth/verify-email").mock(
            return_value=httpx.Response(200, json={"message": "Email verified", "email_verified": True})
        )
        client = FlorenceClient()
        reg = client.auth.register("demo", "demo@example.com", "supersecret123")
        ver = client.auth.verify_email("tok-123")
    assert reg["user_id"] == 42
    assert ver["email_verified"] is True


def test_resend_verification():
    with respx.mock:
        respx.post(f"{P}/auth/resend-verification").mock(
            return_value=httpx.Response(200, json={"verification_sent": True})
        )
        client = FlorenceClient()
        result = client.auth.resend_verification("demo")
    assert result["verification_sent"] is True


# ----------------------------------------------------------------------
# Bot akisi
# ----------------------------------------------------------------------
def test_create_bot_stores_one_time_password():
    store = MemoryTokenStore()
    with respx.mock:
        respx.post(f"{P}/bots").mock(
            return_value=httpx.Response(200, json={"id": 7, "username": "bot-1", "email": "bot-1@bot.florencex.com.tr", "password": "gizli-sifre-123"})
        )
        respx.post(f"{P}/auth/login").mock(return_value=httpx.Response(200, json=_login_response("bot-at", "bot-rt")))
        client = FlorenceClient(token_store=store)
        result = client.auth.create_bot("bot-1")
        pair = client.auth.login_as_bot("bot-1")

    assert result["password"] == "gizli-sifre-123"
    assert store.get_password("bot-1") == "gizli-sifre-123"
    assert pair.access_token == "bot-at"
    assert store.get_access_token() == "bot-at"


def test_login_as_bot_without_stored_password_raises():
    client = FlorenceClient(token_store=MemoryTokenStore())
    with pytest.raises(AuthError) as exc:
        client.auth.login_as_bot("bot-yok")
    assert exc.value.code == "no_bot_password"


def test_bot_session_context_manager():
    store = MemoryTokenStore()
    login_calls = []
    logout_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/auth/login"):
            login_calls.append(1)
            return httpx.Response(200, json=_login_response("bot-at", "bot-rt"))
        if path.endswith("/auth/logout"):
            logout_calls.append(1)
            return httpx.Response(200, json={"message": "Logged out"})
        if path.endswith("/bots"):
            return httpx.Response(200, json={"id": 7, "username": "bot-1", "email": "x@bot.florencex.com.tr", "password": "sifre-12345"})
        return httpx.Response(200, json={"ok": True})

    client = FlorenceClient(token_store=store, transport=httpx.MockTransport(handler))
    with client.auth.bot_session("bot-1", password="sifre-12345") as session:
        assert session is not None
        assert store.get_access_token() == "bot-at"
    assert login_calls == [1]
    assert logout_calls == [1]
    assert store.get_access_token() is None  # logout store'u temizledi


def test_bots_not_allowed_error_code():
    with respx.mock:
        respx.post(f"{P}/bots").mock(
            return_value=httpx.Response(403, json={"detail": "error_bots_not_allowed"})
        )
        client = FlorenceClient()
        with pytest.raises(FlorenceAPIError) as exc:
            client.auth.create_bot("bot-1")
    assert exc.value.code == "error_bots_not_allowed"


# ----------------------------------------------------------------------
# Token persist + env override
# ----------------------------------------------------------------------
def test_token_persist_across_clients_with_injectable_store():
    """Ayni MemoryTokenStore iki client arasinda paylasilir -> ikinci client login'siz calisir."""
    store = MemoryTokenStore()
    with respx.mock:
        respx.post(f"{P}/auth/login").mock(return_value=httpx.Response(200, json=_login_response("at-1", "rt-1")))
        client1 = FlorenceClient(token_store=store)
        client1.auth.login("kullanici", "sifre12345")

    client2 = FlorenceClient(token_store=store)
    assert client2.auth.access_token() == "at-1"
    assert client2.auth.is_authenticated() is True


def test_florence_token_env_override(monkeypatch):
    monkeypatch.setenv("FLORENCE_TOKEN", "env-token-xyz")
    client = FlorenceClient(token_store=MemoryTokenStore())
    assert client.auth.access_token() == "env-token-xyz"
    assert client.auth.is_authenticated() is True


def test_no_token_not_authenticated(monkeypatch):
    monkeypatch.delenv("FLORENCE_TOKEN", raising=False)
    client = FlorenceClient(token_store=MemoryTokenStore())
    assert client.auth.is_authenticated() is False


# ----------------------------------------------------------------------
# Asenkron auth
# ----------------------------------------------------------------------
def test_async_login_and_bot_session():
    store = MemoryTokenStore()
    logout_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/auth/login"):
            return httpx.Response(200, json=_login_response("at-a", "rt-a"))
        if path.endswith("/auth/logout"):
            logout_calls.append(1)
            return httpx.Response(200, json={"message": "Logged out"})
        return httpx.Response(404, json={"detail": "unmocked"})

    async def run() -> None:
        async with AsyncFlorenceClient(token_store=store, transport=httpx.MockTransport(handler)) as client:
            pair = await client.auth.login_async("kullanici", "sifre12345")
            assert pair.access_token == "at-a"
            async with client.auth.bot_session("bot-x", password="sifre-12345"):
                assert store.get_access_token() == "at-a"

    asyncio.run(run())
    assert logout_calls == [1]


def test_async_refresh_single_flight():
    """Eszamanli 2 coroutine -> tek refresh POST'u."""
    store = MemoryTokenStore()
    store.set_tokens("eski-at", "eski-rt")
    refresh_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/refresh"):
            refresh_calls.append(1)
            return httpx.Response(200, json=_login_response("yeni-at", "yeni-rt"))
        return httpx.Response(200, json={"ok": True})

    async def run() -> None:
        async with AsyncFlorenceClient(
            token_store=store, transport=httpx.MockTransport(handler), max_retries=0
        ) as client:
            await asyncio.gather(client.auth.refresh_async(), client.auth.refresh_async())

    asyncio.run(run())
    assert len(refresh_calls) == 1, "single-flight ihlal (async)"
    assert store.get_access_token() == "yeni-at"
