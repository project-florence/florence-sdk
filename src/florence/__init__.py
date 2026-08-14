"""Florence API SDK — Python HTTP API wrapper.

Senkron + asenkron client, auth yonetimi (user + bot), hata hiyerarsisi,
rate-limit farkindaligi ve typed resource'lar. API gercegi: api-spec
``openapi.json`` (89 path) — tum endpoint path'leri birebir eslenir.

Hizli baslangic (senkron):
    from florence import FlorenceClient, MemoryTokenStore

    client = FlorenceClient(token_store=MemoryTokenStore())
    client.login("kullanici", "sifre")          # tokenlar store'a yazilir
    data = client.market.price_history("THYAO", period="1mo")

Asenkron:
    import asyncio
    from florence import AsyncFlorenceClient, MemoryTokenStore

    async def main():
        async with AsyncFlorenceClient(token_store=MemoryTokenStore()) as client:
            await client.login_async("kullanici", "sifre")
            data = await client.market.price_history("THYAO", period="1mo")

    asyncio.run(main())

Kapsam disi (bilincli): CLI, AI/agent katmani, MCP server, mail istemcisi —
bunlar ilerleyen fazlarda eklenir (bkz. plan). GIT commit/push bu gorevde yapilmadi.
"""

from .auth import AuthManager, KeyringTokenStore, MemoryTokenStore, TokenStore
from .client import AsyncFlorenceClient, FlorenceClient
from .config import API_PREFIX, DEFAULT_API_URL, DEFAULT_TIMEOUTS
from .errors import (
    AuthError,
    FlorenceAPIError,
    FlorenceError,
    NetworkError,
    RateLimitError,
)
from .models import (
    BotRecord,
    CreditBalance,
    ExportRecord,
    TokenPair,
    UserProfile,
)

__version__ = "0.1.0"

__all__ = [
    "API_PREFIX",
    "AsyncFlorenceClient",
    "AuthError",
    "AuthManager",
    "BotRecord",
    "CreditBalance",
    "DEFAULT_API_URL",
    "DEFAULT_TIMEOUTS",
    "ExportRecord",
    "FlorenceAPIError",
    "FlorenceClient",
    "FlorenceError",
    "KeyringTokenStore",
    "MemoryTokenStore",
    "NetworkError",
    "RateLimitError",
    "TokenPair",
    "TokenStore",
    "UserProfile",
    "__version__",
]
