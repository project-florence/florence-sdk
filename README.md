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

### Hızlı kurulum (Linux/macOS) — `install.sh`

Paket henüz PyPI'da değil; tek komutla repo'dan kurulum (Linux/macOS; Windows desteklenmez — WSL2 veya Docker önerilir):

```bash
curl -fsSL https://raw.githubusercontent.com/project-florence/florence-sdk/main/install.sh | bash
```

Script şunları yapar:

- Paket yöneticisini algılar: `apt` / `dnf` / `pacman` / `zypper` / `apk`; macOS: `brew`
- Python ≥ 3.12 yoksa sistem genelinde kurar (apt: `python3.12`, Ubuntu'da deadsnakes PPA opsiyonu; brew: `python@3.12`)
- `uv` yoksa kurar (astral.sh standalone kurucu)
- Paketi öncelik sırasıyla kurar: `uv tool install` → `pipx` → `pip --user`
- `fl` / `florence` binary yolunu `~/.bashrc` / `~/.zshrc` / fish `config.fish`'e **idempotent** ekler (tekrar çalıştırmak çift satır oluşturmaz)
- Başarıda `fl --version` ile doğrular ve FLORENCE banner'ı basar

Seçenekler:

| Bayrak | Açıklama |
| --- | --- |
| `--dry-run`, `--check` | Hiçbir şey değiştirmez; yapılacakları gösterir |
| `--uninstall` | PATH satırlarını ve kurulu paketi kaldırır |
| `--source <yol\|url>` | Yerel dizin veya git URL (varsayılan: GitHub repo) |
| `-y`, `--yes` | Onay sorusu sormadan devam eder |

Örnekler:

```bash
bash install.sh --dry-run                              # planı gör, değişiklik yok
bash install.sh --source /path/to/florence-sdk         # yerel repo'dan kur
bash install.sh --uninstall                            # kaldır
```

### Geliştirici kurulumu

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

## CLI (`fl` / `florence`)

```bash
fl auth login <kullanici_adi>      # kalıcı oturum (keyring/şifreli dosya)
fl auth status                     # kim olarak bağlı
fl price THYAO                     # güncel fiyat
fl price history ASELS 3mo 5m      # konumsal period + interval
fl market summary --sort gainers   # günün hareketleri
fl report ASELS                    # hızlı rapor (default quick; --deep ile derin)
fl simulate THYAO --days 30        # simülasyon
fl portfolio list                  # portföyler
fl export fetch 2025               # yıllık veri (sipariş → bekle → indir)
fl download ASELS 3mo              # hisse mumlarını CSV'ye indir
fl tui                             # TUI (yakında)

# Makine/AI dostu çıktı:
fl price THYAO --json
```

Tüm komutlar `--json` destekler; çıktı kuralı: stdout = veri, stderr = hata,
exit kodları 0/1/2. Detaylı tasarım: `docs/cli-design.md`.
