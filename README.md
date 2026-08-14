# florence-sdk

Florence platformu için Python SDK — HTTP API wrapper (senkron + asenkron), CLI,
AI araçları, MCP server ve built-in agent'lar.

Python SDK for the Florence platform — HTTP API wrapper (sync + async), CLI,
AI tools, MCP server and built-in agents.

## Durum / Status

- [x] Faz 0 — Repo iskeleti (pyproject, paket yapısı)
- [x] Faz 1 — Çekirdek client: config, errors, transport, auth
- [x] Faz 2 — Typed resource'lar (endpoint grupları)
- [ ] Faz 3 — CLI (`florence` / `fl`)
- [ ] Faz 4+ — AI katmanı, agent'lar, MCP, skills, release

Detaylı plan: `.hermes/plans/2026-08-14_144500-florence-sdk.md` (workspace)

## Kurulum / Install

```bash
uv sync           # geliştirme ortamı (veya: pip install -e .)
```

## İlk kullanım / Quick start

### Senkron / Sync

```python
from florence import FlorenceClient, MemoryTokenStore

# Token'lar bellekten yönetilir (varsayılan: keyring, `FLORENCE_TOKEN` env override).
with FlorenceClient(token_store=MemoryTokenStore()) as client:
    client.login("kullanici_adi", "sifre")          # POST /api/v1/auth/login
    print(client.user.credits())                    # kredi bakiyesi
    print(client.market.current_price("THYAO"))     # güncel fiyat
    print(client.market.price_history("THYAO", period="3mo"))
```

### Asenkron / Async

```python
import asyncio
from florence import AsyncFlorenceClient, MemoryTokenStore

async def main() -> None:
    async with AsyncFlorenceClient(token_store=MemoryTokenStore()) as client:
        await client.login_async("kullanici_adi", "sifre")
        print(await client.market.price_history("ASELS", period="1mo"))

asyncio.run(main())
```

### Bot hesabı / Bot accounts

```python
from florence import FlorenceClient, MemoryTokenStore

with FlorenceClient(token_store=MemoryTokenStore()) as client:
    client.login("sahip_kullanici", "sifre")
    client.auth.create_bot("bot-1")            # tek seferlik şifre keyring'e yazılır
    with client.auth.bot_session("bot-1"):     # bot olarak giriş + çıkışta logout
        print(client.user.credits())           # bot, sahibinin kredisinden harcar
```

### Export (veri indirme) / Data export

```python
with FlorenceClient(token_store=MemoryTokenStore()) as client:
    client.login("kullanici_adi", "sifre")
    exp = client.export.create_export(year=2025, format="csv")   # POST /data/export
    ready = client.export.wait_export(exp["id"])                 # poll: ready/sent
    client.export.download(ready["download_url"], "/tmp/florence-2025.csv.gz")
```

## API dokümanları / API docs

Güncel API referansı (TR/EN), gerçek `openapi.json` ve AI context dosyası
`api-spec` reposundadır: `/home/efe/Belgeler/florence/api-spec/docs/`

## Hata yönetimi / Error handling

```python
from florence.errors import FlorenceAPIError, RateLimitError, AuthError, NetworkError

try:
    client.market.current_price("THYAO")
except RateLimitError as e:      # 429 — e.retry_after saniye cinsinden
    print(f"rate limit: {e.retry_after}s bekleyin")
except AuthError as e:           # 401 — refresh başarısız
    print(f"auth: {e.code}")
except FlorenceAPIError as e:    # diğer 4xx/5xx — e.code i18n hata kodu
    print(f"API {e.status_code}: {e.code}")
except NetworkError as e:        # bağlantı/zaman aşımı
    print(f"network: {e}")
```
