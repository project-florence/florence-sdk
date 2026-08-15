[English version](./README-en.md)

<<<<<<< HEAD
[![PyPI version](https://img.shields.io/pypi/v/florence-sdk.svg)](https://pypi.org/project/florence-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/florence-sdk.svg)](https://pypi.org/project/florence-sdk/)
[![License: AGPL v3+](https://img.shields.io/badge/License-AGPLv3%2B-blue.svg)](LICENSE)

Florence platformu için Python SDK — HTTP API wrapper (senkron + asenkron), CLI,
AI araçları, MCP server, built-in agent'lar ve tam ekran TUI.

Python SDK for the Florence platform — HTTP API wrapper (sync + async), CLI,
AI tools, MCP server, built-in agents and a full-screen TUI.
=======
<p align="center">
  <img src="https://raw.githubusercontent.com/project-florence/web/main/src/assets/florence_logo.svg" width="80" height="80" alt="Florence">
</p>

<h1 align="center">Florence SDK</h1>
>>>>>>> f0c3c80 (docs: rewrite README (showcase layout, TR+EN))

<p align="center">
  <strong>Florence API'si için resmi SDK</strong> — terminalden kullanım, kod entegrasyonu ve AI ajanları için MCP sunucusu.
</p>

<<<<<<< HEAD
- [x] Faz 0–2 — Repo iskeleti, çekirdek client (config, errors, transport, auth), typed resource'lar
- [x] Faz 3 — CLI (`florence` / `fl`) + semantic helpers (briefing, pulse, haber)
- [x] Faz 4+ — AI katmanı, agent'lar, MCP server (`florence-mcp`)
- [x] TUI v2 — `fl tui`: pano, izleme listesi, ticker detay/grafik + portföy ekranı (Faz A–E)
- [x] ccharts entegrasyonu — TUI grafikleri zorunlu `ccharts>=0.2.0` bağımlılığıyla (adapter katmanı)
- [x] Sürüm 0.2.0 — paketleme, CI (GitHub Actions), dokümantasyon (Faz F)

Detaylı plan: `.hermes/plans/2026-08-18_210253-florence-sdk-tui-v2.md` (workspace) · TUI tasarımı: `docs/tui-design-v2.md`

### TUI (`fl tui`)

Tam ekran, klavye dostu BIST izleyici: **Pano** (öne çıkanlar, günün hareketleri, altın/döviz),
**İzleme listesi** (favoriler + mini grafik), **Ticker detayı** (ccharts çizgi/mum grafiği,
period seçimi, haberler) ve **Portföy** (toplam değer, dönem getirisi, değer grafiği, öne çıkan
pozisyonlar). Veri 30–60s polling ile tazelenir; oturum CLI'ın kalıcı auth'uyla ortak (`fl auth
login`). Tasarım ve klavye haritası: `docs/tui-design-v2.md`.
=======
---

Florence; hisse senetleri, döviz kurları, kıymetli metaller ve makroekonomik göstergeleri tek bir ekranda takip edebileceğiniz akıllı bir yatırım asistanıdır. Florence SDK; platformu terminalden ve kod içinden kullanmanızı sağlayan resmi araç setidir. CLI ile fiyat sorgulama, rapor üretme ve portföy yönetimi yapabilir; MCP sunucusu sayesinde AI asistanlarınızı Florence'a bağlayabilirsiniz.
>>>>>>> f0c3c80 (docs: rewrite README (showcase layout, TR+EN))

## Ekran Görüntüleri

<<<<<<< HEAD
Paket PyPI yayını **hazırlığındadır** (v0.2.0 wheel + sdist `uv build` ile üretilir; publish
workflow'u `.github/workflows/publish.yml`); tek komutla repo'dan kurulum (Linux/macOS; Windows
desteklenmez — WSL2 veya Docker önerilir):

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
fl tui                             # tam ekran TUI (pano, izleme, detay/grafik, portföy)

# Makine/AI dostu çıktı:
=======
<p align="center">
  <img src="docs/screenshots/cli-demo.png" width="600" alt="CLI örneği — komut çıktısı">
</p>

CLI örneği — terminalde fiyat sorgulama çıktısı

## Özellikler

- **API İstemcisi** — Senkron ve asenkron istemcilerle Florence API'sini doğrudan kod içinden kullanın: fiyat sorgulama, rapor üretme ve portföy işlemleri
- **Komut Satırı Arayüzü** — 94 komutla terminalden Florence: `fl price THYAO` ile anlık fiyat, rapor ve portföy yönetimi; tüm komutlarda `--json` çıktı desteği
- **MCP Sunucusu** — Claude, Cursor gibi AI ajanlarının Florence'a güvenli erişimi; 92 hazır araç
- **Bot Hesapları** — Otomatik işlemler için bot hesapları oluşturun ve yönetin
- **Güvenli Oturum Yönetimi** — Oturum token'ları şifreli olarak saklanır

## Hızlı Başlangıç

Kurulum: Linux/macOS için tek komut — `curl -fsSL https://raw.githubusercontent.com/project-florence/florence-sdk/main/install.sh | bash`. PyPI yayını yakında.

```bash
>>>>>>> f0c3c80 (docs: rewrite README (showcase layout, TR+EN))
fl price THYAO --json
```

MCP sunucusunu Claude, Cursor gibi AI ajanlarınıza bağlayarak Florence'ı doğrudan asistanınızın içinden kullanabilirsiniz.

## Repolar

- [web](https://github.com/project-florence/web) — Web uygulaması
- [desktop](https://github.com/project-florence/desktop) — Masaüstü uygulaması
- [mobile](https://github.com/project-florence/mobile) — Mobil uygulama
- [backend](https://github.com/project-florence/backend) — API sunucusu
- [api-spec](https://github.com/project-florence/api-spec) — API spesifikasyonu ve referansları

## Lisans

[AGPL-3.0](./LICENSE)
