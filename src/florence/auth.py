"""Auth yonetimi: user + bot login, single-flight refresh, token saklama.

Token modeli (backend ile birebir):
- Access token: JWT, ~1 saat gecerli. ``Authorization: Bearer <token>`` ile gonderilir.
- Refresh token: opak, ~30 gun gecerli, her refresh'te ROTATE edilir (eski iptal).

Saklama onceligi:
1. ``FLORENCE_TOKEN`` ortam degiskeni (salt-okunur access token override)
2. injectable ``TokenStore`` (testlerde ``MemoryTokenStore``, uretimde ``KeyringTokenStore``)

GUVENLIK: sifre ve token'lar ASLA loglanmaz / print edilmez. Bot sifresi
yalnizca ``POST /bots`` yanitinda TEK SEFERLIK doner; SDK onu keyring'e
kaydeder ve bir daha loglamaz.

Kullanim:
    client = FlorenceClient(token_store=MemoryTokenStore())  # veya keyring default
    client.auth.login("kullanici", "sifre")
    client.auth.create_bot("bot-1")          # sifre keyring'e yazilir
    with client.auth.bot_session("bot-1"):   # bot olarak calis, cikista logout
        ...
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any, Protocol

from .config import API_PREFIX
from .errors import AuthError
from .models import TokenPair

__all__ = [
    "AuthManager",
    "KeyringTokenStore",
    "MemoryTokenStore",
    "TokenStore",
]

logger = logging.getLogger(__name__)

#: keyring icindeki kayit anahtarlari (servis adi: config.KEYRING_SERVICE)
_ACCESS_KEY = "access_token"
_REFRESH_KEY = "refresh_token"


def _bot_password_key(username: str) -> str:
    return f"bot_password:{username}"


class TokenStore(Protocol):
    """Token ve bot sifresi saklayici arayuzu (testlerde inject edilir)."""

    def get_access_token(self) -> str | None: ...
    def get_refresh_token(self) -> str | None: ...
    def set_tokens(self, access_token: str, refresh_token: str) -> None: ...
    def clear(self) -> None: ...
    def get_password(self, username: str) -> str | None: ...
    def set_password(self, username: str, password: str) -> None: ...
    def delete_password(self, username: str) -> None: ...


class MemoryTokenStore:
    """Bellek ici token store — testler ve keyring'in calismadigi ortamlar icin.

    Uretimde keyring tercih edilir; bu store kalici degildir.
    """

    def __init__(self) -> None:
        self._access: str | None = None
        self._refresh: str | None = None
        self._passwords: dict[str, str] = {}

    def get_access_token(self) -> str | None:
        return self._access

    def get_refresh_token(self) -> str | None:
        return self._refresh

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        self._access = access_token
        self._refresh = refresh_token

    def clear(self) -> None:
        self._access = None
        self._refresh = None

    def get_password(self, username: str) -> str | None:
        return self._passwords.get(username)

    def set_password(self, username: str, password: str) -> None:
        self._passwords[username] = password

    def delete_password(self, username: str) -> None:
        self._passwords.pop(username, None)


class KeyringTokenStore:
    """keyring tabanli token store (servis: ``florence-sdk``).

    keyring'in calismadigi headless ortamlarda (ornek: dbus yok) sessizce
    ``MemoryTokenStore`` davranisina duser ve uyari loglar.
    """

    def __init__(self, service: str = "florence-sdk", fallback: TokenStore | None = None) -> None:
        self._service = service
        self._fallback: TokenStore = fallback or MemoryTokenStore()
        self._keyring: Any | None = None
        try:
            import keyring

            # Sadece import degil, gercekten calisip calismadigini da dogrula.
            keyring.get_password(service, "probe")
            self._keyring = keyring
        except Exception:
            logger.warning(
                "keyring kullanilamiyor (%s); tokenlar bellekte tutulacak "
                "(kalici degil). KeyringStore yerine MemoryTokenStore kullanabilirsiniz.",
                service,
            )

    def _get(self, key: str) -> str | None:
        if self._keyring is not None:
            try:
                return self._keyring.get_password(self._service, key)
            except Exception:
                return None
        return self._fallback.get_access_token() if key == _ACCESS_KEY else (
            self._fallback.get_refresh_token() if key == _REFRESH_KEY else None
        )

    def get_access_token(self) -> str | None:
        return self._get(_ACCESS_KEY)

    def get_refresh_token(self) -> str | None:
        return self._get(_REFRESH_KEY)

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        if self._keyring is not None:
            try:
                self._keyring.set_password(self._service, _ACCESS_KEY, access_token)
                self._keyring.set_password(self._service, _REFRESH_KEY, refresh_token)
                return
            except Exception:
                pass
        self._fallback.set_tokens(access_token, refresh_token)

    def clear(self) -> None:
        if self._keyring is not None:
            try:
                self._keyring.delete_password(self._service, _ACCESS_KEY)
                self._keyring.delete_password(self._service, _REFRESH_KEY)
            except Exception:
                pass
        self._fallback.clear()

    def get_password(self, username: str) -> str | None:
        if self._keyring is not None:
            try:
                return self._keyring.get_password(self._service, _bot_password_key(username))
            except Exception:
                return None
        return self._fallback.get_password(username)

    def set_password(self, username: str, password: str) -> None:
        if self._keyring is not None:
            try:
                self._keyring.set_password(self._service, _bot_password_key(username), password)
                return
            except Exception:
                pass
        self._fallback.set_password(username, password)

    def delete_password(self, username: str) -> None:
        if self._keyring is not None:
            try:
                self._keyring.delete_password(self._service, _bot_password_key(username))
                return
            except Exception:
                pass
        self._fallback.delete_password(username)


class AuthManager:
    """User/bot kimlik dogrulama ve token saklama yoneticisi.

    Senkron client: ``login``, ``refresh``, ``logout``, ... metotlari dogrudan
    cagrilir. Asenkron client: ``*_async`` metotlari ``await`` edilir
    (``refresh_async`` tek seferlik (single-flight) asyncio kilitli; senkron
    ``refresh`` threading kilidi kullanir).
    """

    def __init__(
        self,
        client: Any | None = None,
        token_store: TokenStore | None = None,
        keyring_service: str = "florence-sdk",
    ) -> None:
        self._client = client
        self._store: TokenStore = token_store or KeyringTokenStore(keyring_service)
        # Single-flight refresh senkronizasyonu (Condition = Lock + Event).
        self._sync_cond = threading.Condition()
        self._sync_result: TokenPair | None = None
        self._async_future: asyncio.Future[TokenPair] | None = None

    # ------------------------------------------------------------------
    # Token okuma (client header icin kullanir)
    # ------------------------------------------------------------------
    def access_token(self) -> str | None:
        """Gecerli access token; ``FLORENCE_TOKEN`` env'i store'a gore onceliklidir."""
        env_token = os.environ.get("FLORENCE_TOKEN")
        if env_token:
            return env_token
        return self._store.get_access_token()

    def refresh_token(self) -> str | None:
        return self._store.get_refresh_token()

    def is_authenticated(self) -> bool:
        return bool(self.access_token())

    # ------------------------------------------------------------------
    # Ortak yardimcilar
    # ------------------------------------------------------------------
    def _apply_tokens(self, data: dict[str, Any]) -> TokenPair:
        pair = TokenPair.model_validate(data)
        self._store.set_tokens(pair.access_token, pair.refresh_token)
        # Sunucu httpOnly cookie'ler set eder; jar'da bayat access_token
        # kalmasin diye temizle (header auth onceliklidir ama temizlik daha guvenli).
        clear = getattr(self._client, "_clear_cookies", None)
        if callable(clear):
            clear()
        return pair

    def _login_form(self, username: str, password: str) -> dict[str, str]:
        # OAuth2PasswordRequestForm: username, password, grant_type.
        return {"username": username, "password": password, "grant_type": "password"}

    # ------------------------------------------------------------------
    # SENKRON API (senkron client icin)
    # ------------------------------------------------------------------
    def login(self, username: str, password: str) -> TokenPair:
        """POST /api/v1/auth/login — form-encoded, tokenlari store'a yazar."""
        data = self._client.request(
            "POST",
            f"{API_PREFIX}/auth/login",
            data=self._login_form(username, password),
            auth=False,
        )
        return self._apply_tokens(data)

    def refresh(self) -> TokenPair:
        """POST /api/v1/auth/refresh — single-flight (senkron).

        Eszamanli cagrilar ayni refresh sonucunu paylasir: ilk cagri HTTP
        istegini yapar, digerleri onun sonucunu bekler (tek POST).
        """
        with self._sync_cond:
            if self._sync_result is not None:
                # Eszamanli dalga: ilk cagrinin sonucunu tuket ve dondur.
                pair = self._sync_result
                self._sync_result = None
                return pair
            try:
                pair = self._refresh_inner()
                self._sync_result = pair
                return pair
            finally:
                self._sync_cond.notify_all()

    def _refresh_inner(self) -> TokenPair:
        rt = self.refresh_token()
        if not rt:
            raise AuthError(401, "no_refresh_token", "Refresh token yok; tekrar login olun.")
        data = self._client.request(
            "POST",
            f"{API_PREFIX}/auth/refresh",
            json={"refresh_token": rt},
            auth=False,
        )
        return self._apply_tokens(data)

    def logout(self) -> dict[str, Any]:
        """POST /api/v1/auth/logout — refresh token'i iptal eder, store'u temizler."""
        rt = self.refresh_token()
        try:
            if rt:
                return self._client.request(
                    "POST",
                    f"{API_PREFIX}/auth/logout",
                    json={"refresh_token": rt},
                    auth=False,
                )
            return {"message": "Logged out"}
        finally:
            self._store.clear()

    def register(self, username: str, email: str, password: str) -> dict[str, Any]:
        """POST /api/v1/auth/register (public)."""
        return self._client.request(
            "POST",
            f"{API_PREFIX}/auth/register",
            json={"username": username, "email": email, "password": password},
            auth=False,
        )

    def verify_email(self, token: str) -> dict[str, Any]:
        """GET /api/v1/auth/verify-email (public)."""
        return self._client.request(
            "GET",
            f"{API_PREFIX}/auth/verify-email",
            params={"token": token},
            auth=False,
        )

    def resend_verification(self, username_or_email: str) -> dict[str, Any]:
        """POST /api/v1/auth/resend-verification (public)."""
        return self._client.request(
            "POST",
            f"{API_PREFIX}/auth/resend-verification",
            json={"username_or_email": username_or_email},
            auth=False,
        )

    def create_bot(self, username: str, password: str | None = None) -> dict[str, Any]:
        """POST /api/v1/bots — bot olusturur; TEK SEFERLIK sifreyi keyring'e kaydeder.

        Yanit: ``{id, username, email, password}`` — ``password`` yalnizca burada
        doner; SDK onu token store'a yazar ve asla loglamaz.
        """
        data = self._client.request(
            "POST",
            f"{API_PREFIX}/bots",
            json={"username": username, "password": password},
        )
        bot_password = data.get("password")
        if bot_password:
            self._store.set_password(username, str(bot_password))
        return data

    def login_as_bot(self, username: str, password: str | None = None) -> TokenPair:
        """Bot olarak giris yapar.

        ``password`` verilmezse keyring'de saklanan sifre kullanilir.
        """
        pw = password or self._store.get_password(username)
        if not pw:
            raise AuthError(
                401,
                "no_bot_password",
                f"Bot '{username}' sifresi bulunamadi; "
                "create_bot() ile olusturun veya password verin.",
            )
        return self.login(username, pw)

    def bot_session(self, username: str, password: str | None = None) -> BotSession:
        """Bot oturumu context manager'i.

        Senkron: ``with client.auth.bot_session("bot-1"): ...``
        Asenkron: ``async with client.auth.bot_session("bot-1"): ...``
        Cikista her zaman logout yapilir.
        """
        return BotSession(self, username, password)

    # ------------------------------------------------------------------
    # ASENKRON API (asenkron client icin)
    # ------------------------------------------------------------------
    async def login_async(self, username: str, password: str) -> TokenPair:
        """POST /api/v1/auth/login (asenkron)."""
        data = await self._client.request(
            "POST",
            f"{API_PREFIX}/auth/login",
            data=self._login_form(username, password),
            auth=False,
        )
        return self._apply_tokens(data)

    async def refresh_async(self) -> TokenPair:
        """POST /api/v1/auth/refresh — single-flight (asenkron).

        Eszamanli coroutine'ler ayni refresh sonucunu paylasir: ilk cagri HTTP
        istegini baslatir, digerleri ayni task'i bekler (tek POST).
        """
        if self._async_future is None:
            self._async_future = asyncio.create_task(self._refresh_inner_async())
        try:
            return await self._async_future
        finally:
            if self._async_future is not None and self._async_future.done():
                self._async_future = None

    async def _refresh_inner_async(self) -> TokenPair:
        rt = self.refresh_token()
        if not rt:
            raise AuthError(401, "no_refresh_token", "Refresh token yok; tekrar login olun.")
        data = await self._client.request(
            "POST",
            f"{API_PREFIX}/auth/refresh",
            json={"refresh_token": rt},
            auth=False,
        )
        return self._apply_tokens(data)

    async def logout_async(self) -> dict[str, Any]:
        """POST /api/v1/auth/logout (asenkron)."""
        rt = self.refresh_token()
        try:
            if rt:
                return await self._client.request(
                    "POST",
                    f"{API_PREFIX}/auth/logout",
                    json={"refresh_token": rt},
                    auth=False,
                )
            return {"message": "Logged out"}
        finally:
            self._store.clear()

    async def register_async(self, username: str, email: str, password: str) -> dict[str, Any]:
        """POST /api/v1/auth/register (asenkron)."""
        return await self._client.request(
            "POST",
            f"{API_PREFIX}/auth/register",
            json={"username": username, "email": email, "password": password},
            auth=False,
        )

    async def verify_email_async(self, token: str) -> dict[str, Any]:
        """GET /api/v1/auth/verify-email (asenkron)."""
        return await self._client.request(
            "GET",
            f"{API_PREFIX}/auth/verify-email",
            params={"token": token},
            auth=False,
        )

    async def resend_verification_async(self, username_or_email: str) -> dict[str, Any]:
        """POST /api/v1/auth/resend-verification (asenkron)."""
        return await self._client.request(
            "POST",
            f"{API_PREFIX}/auth/resend-verification",
            json={"username_or_email": username_or_email},
            auth=False,
        )

    async def create_bot_async(self, username: str, password: str | None = None) -> dict[str, Any]:
        """POST /api/v1/bots (asenkron); tek seferlik sifre store'a yazilir."""
        data = await self._client.request(
            "POST",
            f"{API_PREFIX}/bots",
            json={"username": username, "password": password},
        )
        bot_password = data.get("password")
        if bot_password:
            self._store.set_password(username, str(bot_password))
        return data

    async def login_as_bot_async(
        self, username: str, password: str | None = None
    ) -> TokenPair:
        """Bot olarak giris (asenkron)."""
        pw = password or self._store.get_password(username)
        if not pw:
            raise AuthError(
                401,
                "no_bot_password",
                f"Bot '{username}' sifresi bulunamadi; "
                "create_bot() ile olusturun veya password verin.",
            )
        return await self.login_async(username, pw)


class BotSession:
    """Bot oturumu: giriste login, cikista logout (sync + async destekli)."""

    def __init__(self, manager: AuthManager, username: str, password: str | None = None) -> None:
        self._manager = manager
        self._username = username
        self._password = password

    def __enter__(self) -> BotSession:
        self._manager.login_as_bot(self._username, self._password)
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        self._manager.logout()
        return False

    async def __aenter__(self) -> BotSession:
        await self._manager.login_as_bot_async(self._username, self._password)
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        await self._manager.logout_async()
        return False
