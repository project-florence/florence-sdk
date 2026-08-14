"""Kimlik cozumleme (mcp-design.md Bölüm 3) ve senkron client factory.

Kimlik zinciri (sunucu baslangicinda, tek sefer — Bölüm 3.1):

1. ``MCP_FLORENCE_BOT=<bot_username>`` -> bot profili: keyring'deki (veya
   ``MCP_FLORENCE_BOT_PASSWORD`` env'indeki) sifreyle ``login_as_bot``.
   Sifre yoksa NET hata: ``AuthError(401, "no_bot_password", ...)`` cozum
   onerisiyle (bots_create / MCP_FLORENCE_BOT_PASSWORD).
2. ``FLORENCE_TOKEN=<jwt>`` -> salt-okunur access token override (SDK'nin
   mevcut davranisi; ``AuthManager.access_token`` env'e oncelik verir).
3. keyring / FileTokenStore -> kalici oturum (``fl login`` ile kurulmus).
4. Hicbiri yoksa -> kimliksiz mod: public tool'lar calisir; JWT isteyen
   tool cagrisi net hata doner (errors.to_tool_error).

Kurallar:
- ``MCP_FLORENCE_BOT`` + ``FLORENCE_TOKEN`` birlikte verilirse bot profili
  kazanir (bot, env token'dan daha spesifik bir kimliktir).
- ``FLORENCE_API_URL`` her durumda saygi gorur (dev ortami).
- Sifre/token ASLA loglanmaz; bot sifresi yalnizca ``MCP_FLORENCE_BOT_PASSWORD``
  veya token store'dan gelir.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from florence import FlorenceClient, KeyringTokenStore, MemoryTokenStore, TokenStore
from florence.errors import AuthError

__all__ = [
    "AuthContext",
    "create_client",
    "resolve_auth_context",
]

#: identity_type degerleri.
IDENTITY_NONE = "none"
IDENTITY_USER = "user"
IDENTITY_BOT = "bot"

#: token_source degerleri.
SOURCE_ENV = "env"
SOURCE_KEYRING = "keyring"
SOURCE_MEMORY = "memory"
SOURCE_NONE = "none"


@dataclass(frozen=True)
class AuthContext:
    """Sunucunun kimlik durumu — ``auth_status`` tool'unun verisi.

    - ``identity_type``: ``bot`` | ``user`` | ``none``
    - ``token_source``: ``env`` | ``keyring`` | ``memory`` | ``none``
    - ``username``: bot profili icin bot adi (varsa).
    """

    identity_type: str = IDENTITY_NONE
    token_source: str = SOURCE_NONE
    username: str | None = None

    @property
    def authenticated(self) -> bool:
        return self.identity_type != IDENTITY_NONE

    def summary(self) -> dict[str, Any]:
        """``auth_status`` tool ciktisi (API cagrisi yapmaz)."""
        return {
            "authenticated": self.authenticated,
            "identity_type": self.identity_type,
            "username": self.username,
            "token_source": self.token_source,
        }


def _store_source(store: TokenStore | None) -> str:
    """Token store'un kaynak etiketini doner (keyring aktifse keyring)."""
    if store is None:
        return SOURCE_NONE
    if isinstance(store, MemoryTokenStore):
        return SOURCE_MEMORY
    # KeyringTokenStore: keyring gercekten calisiyorsa keyring, yoksa memory
    # fallback (SDK'nin sessiz dusme davranisi, Bölüm 3.4).
    keyring_active = getattr(store, "_keyring", None) is not None
    return SOURCE_KEYRING if keyring_active else SOURCE_MEMORY


def resolve_auth_context(token_store: TokenStore | None = None) -> AuthContext:
    """Kimlik zincirini cozer — NETWORK YAPMAZ (saf karar).

    Bot profili seçilmisse kimlik ``bot`` olarak isaretlenir; gercek login
    ``create_client`` icinde yapilir (HTTP gerektirir).
    """
    bot = os.environ.get("MCP_FLORENCE_BOT")
    if bot:
        password = os.environ.get("MCP_FLORENCE_BOT_PASSWORD")
        source = SOURCE_ENV if password else _store_source(token_store)
        return AuthContext(identity_type=IDENTITY_BOT, token_source=source, username=bot)
    if os.environ.get("FLORENCE_TOKEN"):
        return AuthContext(identity_type=IDENTITY_USER, token_source=SOURCE_ENV)
    if token_store is not None and token_store.get_access_token():
        return AuthContext(identity_type=IDENTITY_USER, token_source=_store_source(token_store))
    return AuthContext(identity_type=IDENTITY_NONE, token_source=SOURCE_NONE)


def create_client(
    token_store: TokenStore | None = None,
    base_url: str | None = None,
) -> FlorenceClient:
    """Senkron ``FlorenceClient`` uretir; kimlik zincirini baslangicta uygular.

    - ``MCP_FLORENCE_BOT`` setse: sifre ``MCP_FLORENCE_BOT_PASSWORD`` veya
      token store'dan alinir; yoksa ``AuthError(401, "no_bot_password")``
      firlatilir (Bölüm 3.4 net hata sozlesmesi). Login HTTP istegidir —
      sunucu baslangicinda yapilir.
    - ``FLORENCE_TOKEN`` / store oturumu: ek islem gerekmez (SDK env/access
      token'i otomatik kullanir).
    - Hicbiri yoksa: kimliksiz mod (public tool'lar calisir).
    """
    store = token_store or KeyringTokenStore()
    client = FlorenceClient(base_url=base_url, token_store=store)

    bot = os.environ.get("MCP_FLORENCE_BOT")
    if not bot:
        return client

    password = os.environ.get("MCP_FLORENCE_BOT_PASSWORD") or store.get_password(bot)
    if not password:
        raise AuthError(
            401,
            "no_bot_password",
            f"Bot '{bot}' sifresi bulunamadi; MCP_FLORENCE_BOT_PASSWORD ile "
            "verin veya bots_create ile olusturun (sifre keyring'e yazilir).",
        )
    # Token'lar store'a yazilir; 401'de client otomatik single-flight refresh
    # yapar -> bot oturumu surec boyunca canli kalir (Bölüm 3.3).
    client.auth.login_as_bot(bot, password)
    return client
