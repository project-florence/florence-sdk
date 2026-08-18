# Changelog

Bu projede [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) biçimi ve
[SemVer](https://semver.org/lang/tr/) sürümleme kullanılır.

## [0.2.0] — 2026-08-18

### Eklendi (Added)

- **TUI v2 (`fl tui`)** — tam ekran, klavye dostu BIST izleyici (Faz A–E):
  - **Pano:** öne çıkanlar (`stats_top`), günün hareketleri (gainers/losers sekmeli),
    altın/döviz şeridi, piyasa durumu göstergesi (AÇIK/KAPALI/TATİL).
  - **İzleme listesi:** favoriler + mini grafik, satır önizleme paneli, `f` ile favori toggle.
  - **Ticker detayı:** ccharts çizgi/mum grafiği (`c` ile tip değişimi, `1/3/6/y` period),
    haberler (90s poll, rate-limit güvenli), `esc` ile geri dönüş.
  - **Portföy ekranı:** portföy listesi/seçim, toplam değer + dönem getirisi özeti, değer
    geçmişi grafiği, öne çıkan pozisyonlar (Faz E).
- **ccharts entegrasyonu (P1/P2/Y2):** TUI grafikleri zorunlu `ccharts>=0.2.0` bağımlılığıyla
  çalışır; `florence/tui/charts.py` adapter katmanı üzerinden (`ohlc_rows`, `render_line`/
  `render_candle`, `single_row`, `theme_ansi`, `period_colors`) — ekranlar ccharts'ı doğrudan
  import etmez. `high`/`low` yoksa "yaklaşık mum" sentezi (P2).
- **Yeni TUI config anahtarları:** `tui_refresh_seconds`, `tui_default_period`,
  `tui_default_chart`, `tui_market_closed_refresh`, `tui_watchlist_source` (yalnızca
  `favorites`), `tui_top_limit`, `tui_summary_limit` (`fl config set/show` allowlist'inde).
- **Akıllı polling:** ekran-bazlı fetch (arka plan ekranına istek yok), 429'da interval
  uzatma, piyasa kapalıyken `tui_market_closed_refresh`'e yavaşlama, TTL cache (60s–10dk).
- **CI (P9):** `.github/workflows/ci.yml` — ruff check + pytest, Python 3.12/3.13 matrix,
  ubuntu-latest, uv cache (~89s bütçe).
- **Opsiyonel publish workflow:** `.github/workflows/publish.yml` (v* tag'ı → `uv build` +
  `uv publish`, trusted publishing). SDK'da tag/deploy zinciri yoktur — workflow yalnızca
  elle tag açılırsa tetiklenir.
- **Dokümantasyon:** `docs/tui-design-v2.md` (güncel TUI şartnamesi; eski `docs/tui-design.md`
  geçmiş kaydı olarak korunur), README durum/badge güncellemesi, CHANGELOG.

### Değişti (Changed)

- Sürüm `0.1.0` → **`0.2.0`**; `src/florence/__init__.py::__version__` senkron.
- `pyproject.toml`: geçici ccharts path bağımlılığı
  (`ccharts @ file:///home/efe/Belgeler/ccharts`) kaldırıldı → **`ccharts>=0.2.0`** PyPI
  pin'ine çevrildi (P1). `[tool.hatch.metadata] allow-direct-references` temizlendi.
- `fl tui` artık portföy ekranını da kapsar.

### Sabitlendi (Fixed)

- — (0.2.0 sürüm notu; geçmiş değişiklikler için git geçmişine bakınız.)

### Altyapı (Infrastructure)

- `uv.lock` ccharts 0.2.0 (PyPI registry) ile güncellendi; wheel + sdist `uv build` ile
  üretilip temiz venv'de import smoke testi doğrulandı (354 test geçiyor, ruff temiz).

## [0.1.0] — 2026-08-14

İlk sürüm: HTTP API wrapper (sync + async), typed resource'lar, CLI (`fl`/`florence`),
MCP server (`florence-mcp`), semantic helpers ve bot hesap desteği. TUI tasarımı v1
(`docs/tui-design.md`) bu sürümde yazıldı; implementasyon 0.2.0'da tamamlandı.