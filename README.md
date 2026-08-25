[English version](./README-en.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/project-florence/web/main/src/assets/florence_logo.svg" width="80" height="80" alt="Florence">
</p>

<h1 align="center">Florence SDK</h1>

<p align="center">
  <a href="https://pypi.org/project/florence-sdk/"><img src="https://img.shields.io/pypi/v/florence-sdk.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/florence-sdk/"><img src="https://img.shields.io/pypi/pyversions/florence-sdk.svg" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPLv3%2B-blue.svg" alt="License: AGPL v3+"></a>
</p>

<p align="center">
  <strong>Florence Platformu için Resmi Python SDK'sı</strong><br>
  HTTP API Wrapper (Sync + Async), Tam Kapsamlı CLI, Zengin TUI (Terminal Arayüzü) ve AI Ajanları için MCP Sunucusu.
</p>

---

Florence; Borsa İstanbul (BIST) hisse senetleri, döviz kurları, kıymetli metaller ve makroekonomik göstergeleri tek bir çatı altında takip edebileceğiniz akıllı bir yatırım ve analiz platformudur. **Florence SDK**, platformun tüm yeteneklerini Python kodlarınızda, terminalinizde ve AI asistanlarınızda kullanmanızı sağlar.

## Özellikler

- **API İstemcisi** — Senkron (`FlorenceClient`) ve Asenkron (`AsyncFlorenceClient`) istemciler ile BIST verileri, teknik/temel analiz, bültenler (`digest`), simülasyon ve portföy yönetimi.
- **Kapsamlı CLI (`fl` / `florence`)** — 95+ komut, zengin Rich tabloları, `--json` makine çıktısı ve yerel şifreli kimlik doğrulama.
- **Zengin Çok Sekmeli TUI (`fl tui`)** — Modern çok sekmeli Terminal Kullanıcı Arayüzü:
  - `[1] Pano` — Büyük Florence renkli ASCII logosu, favoriler, günün hareketleri, piyasa özeti ve bülten vurgusu.
  - `[2] İzleme Listesi` — Gerçek zamanlı favori takibi ve mini trend grafikleri.
  - `[3] Günlük Bülten` — Sabah, öğle ve akşam yapay zeka piyasa bülteni okuyucusu.
  - `[4] Portföy` — Sanal portföyler, varlık dağılımı ve performans analizi.
  - `[5] Hisseler` — Popüler, yükselen, düşen, hacim ve piyasa değerine göre sıralanabilir BIST şirket listesi.
  - `[6] Ekonomi` — Canlı döviz kurları, altın ve kıymetli madenler tablosu.
  - `[Detay Ekranı]` — Çizgi ve çift renkli (yeşil/kırmızı) mum grafikleri (`ccharts`), 1A/3A/6A/1Y dönemleri, şirket profili ve haberler.
- **MCP Sunucusu (`florence-mcp`)** — Cursor, Claude Desktop ve diğer AI ajanları için 99 hazır finans ve piyasa analiz aracı.
- **Bot Hesapları & Güvenli Oturum** — Otomasyon için alt bot hesapları oluşturma ve oturum yönetimi.

---

## Kurulum

### Hızlı Kurulum (Linux / macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/project-florence/florence-sdk/main/install.sh | bash
```

### uv veya pip ile Kurulum

```bash
# uv ile (Önerilen)
uv pip install florence-sdk

# pip ile
pip install florence-sdk
```

### Geliştirici Kurulumu

```bash
git clone https://github.com/project-florence/florence-sdk.git
cd florence-sdk
uv sync
```

---

## Hızlı Başlangıç (Python SDK)

### Senkron Kullanım

```python
from florence import FlorenceClient, MemoryTokenStore

# Token'lar bellekten veya keyring üzerinden yönetilir
with FlorenceClient(token_store=MemoryTokenStore()) as client:
    client.login("kullanici_adi", "sifre")
    
    # Anlık fiyat ve grafik verisi
    price = client.market.current_price("THYAO")
    history = client.market.price_history("THYAO", period="1mo")
    
    # Günlük yapay zeka bülteni
    digest = client.digest.current()
    print(digest["title"])
```

### Asenkron Kullanım

```python
import asyncio
from florence import AsyncFlorenceClient, MemoryTokenStore

async def main() -> None:
    async with AsyncFlorenceClient(token_store=MemoryTokenStore()) as client:
        await client.login_async("kullanici_adi", "sifre")
        
        # Şirket özeti ve piyasa hareketleri
        movers = await client.market.companies_summary(sort="gainers", limit=5)
        print(movers)

asyncio.run(main())
```

---

## CLI Kullanımı (`fl` / `florence`)

```bash
# Kimlik doğrulama
fl auth login <kullanici_adi>
fl auth status

# Piyasa & Fiyat
fl price THYAO
fl price history ASELS 3mo 5m
fl market summary --sort popular

# Günlük Piyasa Bülteni (AI Digest)
fl digest current
fl digest list

# Analiz & Simülasyon
fl report ASELS --deep
fl simulate THYAO --days 30

# Portföy Yönetimi
fl portfolio list
fl portfolio favorite add THYAO

# Tam Ekran Çok Sekmeli TUI
fl tui

# JSON Çıktı Desteği (Script & AI Entegrasyonu için)
fl price THYAO --json
fl digest current --json
```

---

## Model Context Protocol (MCP) Sunucusu

Florence MCP sunucusu, Claude Desktop veya Cursor üzerinden finansal verilere erişmenizi sağlar.

`claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "florence": {
      "command": "uvx",
      "args": ["florence-mcp"]
    }
  }
}
```

---

## Repolar ve Ekosistem

- [project-florence/web](https://github.com/project-florence/web) — Next.js Web Uygulaması
- [project-florence/backend](https://github.com/project-florence/backend) — FastAPI Backend Servisleri
- [project-florence/florence-sdk](https://github.com/project-florence/florence-sdk) — Python SDK, CLI, TUI & MCP
- [project-florence/ccharts](https://github.com/project-florence/ccharts) — Terminal Grafik Çizim Motoru
- [project-florence/api-spec](https://github.com/project-florence/api-spec) — API Şemaları ve Sözleşmeleri

## Lisans

Bu proje [AGPL-3.0](./LICENSE) lisansı ile lisanslanmıştır.
