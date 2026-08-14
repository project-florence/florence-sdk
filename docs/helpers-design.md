# Florence SDK — Yardımcı Tool (Helper) Kataloğu Tasarım Raporu

> **Durum:** Tasarım (implementasyon yok) · **Tarih:** 2026-08-14
> **Kapsam:** Endpoint'lerin birebir üstüne kurulan **semantik kompozit yardımcı tool'lar** — kullanıcı/AI dostu, tek niyet = tek çağrı. Ham SDK metodlarının (76 metod → 94 CLI komutu → 92 MCP tool) yerini ALMAZ; onların üstüne biner.
> **Kaynaklar:** `src/florence/resources/*.py` (9 modül), `src/florence/{client,auth,errors,config}.py`, `src/florence/cli/*` (komut desenleri), `src/florence_mcp/*` (tool desenleri), `docs/cli-design.md`, `docs/mcp-design.md`, `pyproject.toml` (bağımlılıklar), `tests/` (haber item şeması: `{title, url, ...}`).
> **Bu doküman SADECE tasarımdır** — kod içermez; implementasyon ayrı bir fazda yapılır. COMMIT/PUSH YOK.
> **Dil kuralı:** komut/tool adları İngilizce (teknik standart); açıklamalar, yardımlar ve hata mesajları Türkçe (hedef kitle: Türkçe BIST yatırımcısı + AI ajanları).

---

## 1. Amaç ve Tasarım Felsefesi

### 1.1 Neden helper'lar?

Mevcut yüzey (CLI + MCP + SDK) **endpoint envanterini** eksiksiz sunar: her SDK metodu = tam bir komut/tool. Ama kullanıcının zihnindeki işler **tek endpoint'e sığmaz**:

- *"THYAO hakkında son 5 haberin içeriğini ver"* → `GET /news/THYAO` (başlık+link döner) **+ 5 ayrı URL çekimi** (hiçbir SDK metodu bunu yapmaz — harici HTTP gerekir).
- *"Portföyüm nasıl?"* → valuation + risk + performers + benchmark = **4 ayrı çağrı**, kullanıcı 4 komut bilmek zorunda.
- *"Piyasa ne durumda?"* → status + gainers/losers + top = 3 çağrı.

Helper kataloğu bu boşluğu doldurur: **tek kullanıcı niyeti → tek çağrı → birleşik, stabil şemalı sonuç.** Kullanıcı örneği (birebir ilham): *"haberleri direkt içeriklerini çekip text olarak veren tool — link olabilir veya direkt ASELS hakkında ilk 5 haberi verir; haber yoksa veya 5'ten azsa hata vermez, çıktı verir veya boş çıktı döner."*

### 1.2 Semantik kompozit nedir (ve ne değildir)

| | Endpoint komutu (mevcut) | Helper (yeni) |
|---|---|---|
| Kaynak | Tek SDK metodu = tek endpoint | 1..N SDK metodu + 0..N harici HTTP |
| Çıktı şeması | API şeması birebir (`--json` = API) | **Helper'ın kendi stabil şeması** (kompozit istisnası — cli-design.md §2.0'daki kurala dayanır) |
| Boş sonuç | "Kayıt yok" / `[]` | Boş liste/null alan **+ kısmi sonuç toleransı** (tek URL 404 → tüm digest çökmez) |
| Durum | Salt-okuma + yazma | **v1'de tamamı salt-okuma** (yazma kompozit yok) |
| Nerede yaşar | `resources/` → `cli/commands_*` → `florence_mcp/` | **`florence/helpers/` çekirdeği** → CLI/MCP ince bağlar |

### 1.3 Tasarım ilkeleri

1. **Tek niyet = tek helper.** Helper, kullanıcının zihnindeki işi adlandırır (`news_digest`, `portfolio_health`); endpoint path'ini kopyalamaz.
2. **Helper endpoint'i kopyalamaz, kompoze eder.** `market_news` (ham liste) ile `news_digest` (içerikli özet) birlikte yaşar — biri temel katman, diğeri semantik katman. Gereksizlik kuralı helper katmanında **çakışan niyet** için geçerlidir (iki helper aynı niyeti kompoze edemez).
3. **Boş/kısa sonuç asla hata değildir.** 0 haber → boş liste; 5'ten az haber → ne varsa o; tek URL çekilemez → o item'da `fetch_error`, digest devam; exit code her zaman `0`. Yalnızca **altyapı hataları** (ağ, kimlik, özellik yok) exit `1` üretir.
4. **Kısmi sonuç, tam sonuç kadar değerlidir.** Çok parçalı kompozitlerde tek parçanın hatası tüm paketi düşürmez; ilgili alan `null`/hata kodu alır.
5. **Üç seviye tek çekirdekten beslenir.** CLI ve MCP yalnızca ince bağlayıcıdır; iş mantığı `florence/helpers/` fonksiyonlarında yaşar. İki yerde ayrı ayrı yazılmış mantık YOKTUR.
6. **Rate limit farkındalığı:** `news` 10/dk, export 3/saat. Helper açıklamaları kaç çağrı yapacağını söyler; çok çağrılı helper'lar (news_search) kısmi sonuç + `rate_limited: true` döner, hata fırlatmaz.
7. **Helper'lar kredi harcamaz (v1).** `analysis.generate_report` / `simulate` kompozitlere **girmez** (kredi + uzun süre + ayrı akış; zaten CLI/MCP'de kendi desenleri var).

### 1.4 Kimlik gereksinimleri (helper matrisi)

| Veri kaynağı | Kimlik |
|---|---|
| `market.*` (news hariç), `misc.*` (announcements hariç) | Public |
| `market.news` | JWT + **news feature'ı** (10/dk) |
| `economy.*` | **JWT** (backend allowlist'inde değil — economy_res.py notu) |
| `portfolio.*`, `export.*`, `analysis.*`, announcements | JWT |
| Harici URL çekimi (`fetch_article`) | Kimliksiz (harici site) |

Helper'lar JWT gerektiren kaynak kullandığında kimlik yoksa `AuthError` → exit 1 (net hata: "kimlik gerekli — fl auth login / FLORENCE_TOKEN / MCP_FLORENCE_BOT").

---

## 2. Yardımcı Tool Kataloğu (13 helper)

### 2.0 Özet tablo

| # | Helper | Kullanıcı niyeti | Çekirdek veri kaynakları | CLI (`fl helper …`) | MCP tool | Öncelik | Efor |
|---|---|---|---|---|---|---|---|
| H1 | `news_digest` | "THYAO son haberlerinin içeriği" | `market.news` + `fetch_article`×N | `news-digest THYAO` | `helper_news_digest` | **v1** | M |
| H2 | `fetch_article` | "Bu URL'nin düz metni" | harici httpx + trafilatura/stdlib | `article <url>` | `helper_fetch_article` | **v1** | M |
| H3 | `ticker_briefing` | "THYAO tek bakışta" | `current_price` + `company_info` + `price_history` + `news` | `briefing THYAO` | `helper_ticker_briefing` | **v1** | M |
| H4 | `market_pulse` | "Piyasa ne durumda?" | `market_status` + `companies_summary` + `stats_top` | `pulse` | `helper_market_pulse` | **v1** | S |
| H5 | `portfolio_health` | "Portföyüm nasıl?" | `snapshot` + `performers` + `risk` + `benchmark` + `diversification` | `portfolio-health <id>` | `helper_portfolio_health` | **v1** | M |
| H6 | `macro_briefing` | "Makro manzara" | `economy.currency` + `gold_prices` + `macroeconomy` | `macro-briefing` | `helper_macro_briefing` | **v1** | S |
| H7 | `compare_tickers` | "Şu hisseleri karşılaştır" | `current_price`×N + `price_history`×N + `companies_summary` | `compare THYAO,ASELS` | `helper_compare_tickers` | v1.5 | S-M |
| H8 | `watchlist_report` | "Takip listem ne durumda?" | `portfolio.favorites` + `current_price`×N (+ sparkline) | `watchlist` | `helper_watchlist_report` | v1.5 | S |
| H9 | `price_alerts` | "Hedef fiyat alarmı" | yerel `alerts.json` + `current_price`×N | `alerts [--set THYAO:320]` | `helper_price_alerts` | v1.5 | M |
| H10 | `export_watch` | "Export'larım ne durumda?" | `export.list_exports` + (`wait_export`) | `export-watch [--wait <id>]` | `helper_export_watch` | v1.5 | S |
| H11 | `ipo_watch` | "Halka arz manzarası" | `misc.ipos_upcoming` + `ipos_active` + `ipos_draft` | `ipo-watch` | `helper_ipo_watch` | v1.5 | S |
| H12 | `news_search` | "Anahtar kelimeyle haber ara" | `stats_top` + `market.news`×M (başlık eşleşmesi) | `news-search <q>` | `helper_news_search` | v2 | M |
| H13 | `news_summary` | "Haberlerin LLM özeti" | H1 çıktısı + opsiyonel OpenAI-uyumlu LLM | `news-summary THYAO` | `helper_news_summary` | v2 | L |

Efor dağılımı: **S×5, M×7, L×1.** v1 = 6 helper (H1–H6), v1.5 = 5 (H7–H11), v2 = 2 (H12–H13).

---

### 2.1 H1 — `news_digest` (haber özeti + içerik) ⭐ v1 · Efor M

- **Kullanıcı niyeti:** *"ASELS hakkında ilk 5 haberi, içerikleri düz metin olarak ver."* Haber yoksa veya 5'ten azsa hata vermez.
- **Girdi:** `ticker` (zor), `amount` (default 5, 1–10), `fetch_content` (default `true`), `max_chars` (default 6000/haber).
- **Çıktı (stabil şema):**
  ```json
  {
    "ticker": "THYAO", "generated_at": "…",
    "items": [
      {"title": "…", "url": "https://…", "published_at": null,
       "content": "düz metin…", "content_available": true, "fetch_error": null}
    ],
    "requested": 5, "fetched": 4, "failed": 1
  }
  ```
- **Veri kaynakları:** `MarketResource.news(ticker, amount)` → 1 çağrı (10/dk); her item'ın `url`'si için `fetch_article` → N harici GET. `--no-content` ile içerik çekimi atlanır (saf liste modu — `market_news` ile aynı veri, farklı paketleme değil; `--no-content` yalnızca hız/rate-limit kullanımı için).
- **Boş/kısa davranış:** 0 haber → `{"items": [], "requested": 5, "fetched": 0, "failed": 0}` (exit 0). 3 haber geldi → 3 item, `fetched: 3` (exit 0). Tek URL 404/JS-render → o item `content: null, content_available: false, fetch_error: "http_404"`, `failed` artar, **digest döner**. **İstisna (gerçek hata, exit 1):** `news` endpoint'i 401 (kimlik yok / news feature yok) veya 429 limit aşımı → helper hata fırlatır; çünkü ana kaynak erişilemez.
- **CLI:** `fl helper news-digest THYAO [--amount 5] [--no-content] [--max-chars 6000]` — insan modunda başlık + ilk ~400 karakter özet blokları; `--json`'da şema birebir.
- **Kütüphane:** `from florence.helpers import news_digest` → `NewsDigest` (pydantic); `news_digest_async(client_async, …)`.
- **MCP:** `helper_news_digest(ticker, amount=5, fetch_content=True)` — açıklamada "N harici HTTP isteği yapar; news 10/dk rate limiti" notu.

---

### 2.2 H2 — `fetch_article` (URL → düz metin) ⭐ v1 · Efor M — H1'in alt yapısı

- **Kullanıcı niyeti:** *"Şu linkteki makalenin metnini ver."* (Kullanıcı örneğindeki "link olabilir" kısmı.)
- **Girdi:** `url` (zor, yalnızca `http://`/`https://`), `max_chars` (default 8000), `timeout` (default 15s).
- **Çıktı:**
  ```json
  {"url": "…", "resolved_url": "…", "title": "…", "text": "…",
   "content_available": true, "needs_js": false, "error": null}
  ```
- **Veri kaynakları:** Harici `httpx.GET` (SDK zaten httpx bağımlısı — yeni bağımlılık yok) + HTML metin çıkarımı (Bölüm 3: trafilatura opsiyonel / stdlib fallback).
- **Boş/kısa davranış:** İçerik çıkarılamadı (JS-render, boş sayfa) → `{"text": "", "content_available": false, "needs_js": true}` (exit 0). 404/403 → `error: "http_404"` / `"http_403"` (exit 0 — sonuç nesnesidir, hata değil). Şema http/https değil → **kullanım hatası** (exit 2). Ağ hatası (DNS/TLS/timeout) → `NetworkError` → exit 1 (altyapı).
- **CLI:** `fl helper article <url> [--max-chars 8000] [--timeout 15]` — insan modunda metin stdout'a; `--json`'da şema.
- **Kütüphane:** `fetch_article(url, …) -> Article`; `fetch_article_async(url, …)`.
- **MCP:** `helper_fetch_article(url, max_chars=8000)` — SSRF korumalı (Bölüm 3.4), LLM'in verdiği URL'ler de aynı guard'dan geçer.

---

### 2.3 H3 — `ticker_briefing` ⭐ v1 · Efor M

- **Kullanıcı niyeti:** *"THYAO hakkında tek bakışta özet: fiyat, profil, trend, son haberler."*
- **Girdi:** `ticker` (zor), `news_amount` (default 3), `trend_period` (default `1mo`).
- **Çıktı:**
  ```json
  {"ticker": "THYAO", "generated_at": "…",
   "quote": {"price": 313.4, "change_pct": 0.93, "market_status": "open"},
   "company": {"name": "…", "sector": "…"},
   "trend": {"period": "1mo", "change_pct": 4.2, "sparkline": [301.1, 303.0, …]},
   "news": [{"title": "…", "url": "…"}]}
  ```
- **Veri kaynakları:** `current_price` (1) + `company_info` (1) + `price_history` (1, sparkline = son 30 kapanış fiyatı, `close` serisi) + `news` (1, 3 haber). Toplam **4 backend çağrısı** — açıklamada belirtilir.
- **Boş/kısa davranış:** Fiyat yok (`is_stale`/işlem yok) → `quote: null`, geri kalan döner. Haber yok → `news: []`. Şirket profili yok → `company: null`. Hepsi eksik olsa bile briefing **döner** (alanlar null), exit 0.
- **CLI:** `fl helper briefing THYAO` — insan modunda panel: fiyat bloğu + sparkline (rich) + haber listesi.
- **Kütüphane:** `ticker_briefing(client, ticker, …) -> TickerBriefing`.
- **MCP:** `helper_ticker_briefing(ticker, news_amount=3)` — LLM "X hissesi hakkında ne biliyorsun?" sorusunu tek çağrıyla çözer.

---

### 2.4 H4 — `market_pulse` ⭐ v1 · Efor S

- **Kullanıcı niyeti:** *"Piyasa şu an ne durumda? Açık mı, kazananlar, kaybedenler, popülerler."*
- **Girdi:** `limit` (default 5, her liste için).
- **Çıktı:**
  ```json
  {"market_open": true, "next_open_at": "…", "holiday": false,
   "gainers": [{"ticker": "…", "change_pct": …}],
   "losers":  [{"ticker": "…", "change_pct": …}],
   "most_popular": [{"ticker": "…", "count": …}],
   "volume_leaders": [{"ticker": "…", "volume": …}],
   "generated_at": "…"}
  ```
- **Veri kaynakları:** `market_status` (1) + `companies_summary(sort="gainers")` (1) + `companies_summary(sort="losers")` (1) + `companies_summary(sort="volume")` (1) + `stats_top` (1) = **5 backend çağrısı** (hepsi public).
- **Boş/kısa davranış:** Piyasa kapalı → `market_open: false` + `next_open_at`, listeler yine döner (son işlem günü verisi — backend davranışı). Hiç veri yok → boş listeler. Exit 0.
- **CLI:** `fl helper pulse [--limit 5]`.
- **Kütüphane:** `market_pulse(client, limit=5) -> MarketPulse`.
- **MCP:** `helper_market_pulse(limit=5)`.

---

### 2.5 H5 — `portfolio_health` ⭐ v1 · Efor M

- **Kullanıcı niyeti:** *"Portföyüm nasıl? Değer, risk, en iyi/kötü, endekse göre durum."*
- **Girdi:** `portfolio_id` (zor), `risk_period` (default `1y`).
- **Çıktı:**
  ```json
  {"portfolio_id": 7, "total_value": 152340.5, "pnl": 12340.5, "pnl_pct": 8.8,
   "performers": {"top": [{"ticker": "…", "return_pct": …}],
                  "bottom": [{"ticker": "…", "return_pct": …}]},
   "risk": {"volatility": …, "max_drawdown": …, "sharpe": …},
   "benchmark": {"ticker": "XU100", "portfolio_return_pct": …, "benchmark_return_pct": …, "diff_pct": …},
   "diversification": {"stocks": …, "forex": …, "metals": …}}
  ```
- **Veri kaynakları:** `snapshot` (veya `valuation`) (1) + `performers(top_n=5)` (1) + `risk` (1) + `benchmark` (1) + `diversification` (1) = **5 backend çağrısı** (tamamı JWT).
- **Boş/kısa davranış:** İşlemsiz portföy → `total_value: 0, performers: {top: [], bottom: []}`. Backend bazı analiz uçlarında boş portföy için 400 döndürebilir → helper o **alanı yakalar, `null` yapar, paketi düşürmez** (kısmi sonuç ilkesi). Portföy yoksa (404) → gerçek hata (exit 1). Kimlik yok → `AuthError` (exit 1).
- **CLI:** `fl helper portfolio-health <id> [--risk-period 1y]`.
- **Kütüphane:** `portfolio_health(client, portfolio_id, …) -> PortfolioHealth`.
- **MCP:** `helper_portfolio_health(portfolio_id)` — LLM "portföyümü özetle" dediğinde tek çağrı.

---

### 2.6 H6 — `macro_briefing` ⭐ v1 · Efor S

- **Kullanıcı niyeti:** *"Makro manzara: döviz, altın, faiz/enflasyon serileri tek pakette."*
- **Girdi:** `symbols` (default `"USD,EUR,GBP"`), `macro_series` (ops, virgüllü FRED kodu filtresi).
- **Çıktı:**
  ```json
  {"currency": {"USD": 34.25, "EUR": 37.1},
   "gold": {"gram-altin": 2890.5, "ceyrek-altin": …},
   "macro": {"us10y": …, "turkey_cpi": …},
   "generated_at": "…"}
  ```
  ⚠️ Ekonomi değerleri backend'de string + Türk virgüllü (`"40,25"`) — helper **float'a normalize eder** (CLI `normalize_economy` davranışı helper çekirdeğine taşınır).
- **Veri kaynakları:** `economy.currency(symbols)` (1) + `economy.gold_prices()` (1) + `economy.macroeconomy()` (1) = **3 backend çağrısı** (hepsi **JWT** — economy allowlist'te değil).
- **Boş/kısa davranış:** Seri yok → ilgili alan `{}`; exit 0. Kimlik yok → `AuthError` (exit 1).
- **CLI:** `fl helper macro-briefing [--symbols USD,EUR]`.
- **Kütüphane:** `macro_briefing(client, …) -> MacroBriefing`.
- **MCP:** `helper_macro_briefing(symbols="USD,EUR,GBP")`.

---

### 2.7 H7 — `compare_tickers` · v1.5 · Efor S-M

- **Kullanıcı niyeti:** *"THYAO, ASELS, SAHOL'u yan yana karşılaştır."*
- **Girdi:** `tickers` (virgüllü, **2–10**), `period` (default `1mo`).
- **Çıktı:**
  ```json
  {"period": "1mo", "generated_at": "…",
   "rows": [{"ticker": "THYAO", "name": "Türk Hava Yolları", "price": 313.4,
             "change_pct": 0.93, "period_return_pct": 4.2, "volume": …}],
   "invalid": ["XXXX"]}
  ```
- **Veri kaynakları:** `current_price`×N + `price_history`×N (dönem getirisi: ilk/son kapanış) + `companies_summary(tickers="A,B,C")` (1 çağrı, isim/market_cap zenginleştirme) = **2N+1 backend çağrısı**.
- **Boş/kısa davranış:** 1 ticker → **kullanım hatası** (exit 2, "en az 2 ticker"). Geçersiz ticker → `invalid` listesinde, kalanlarla devam. Hepsi geçersiz → `rows: []` (exit 0). Tek ticker'ın fiyatı yok → o satır `price: null`.
- **CLI:** `fl helper compare THYAO,ASELS,SAHOL [--period 1mo]`.
- **Kütüphane:** `compare_tickers(client, tickers, …) -> CompareResult`.
- **MCP:** `helper_compare_tickers(tickers: list[str], period="1mo")`.

---

### 2.8 H8 — `watchlist_report` · v1.5 · Efor S

- **Kullanıcı niyeti:** *"Takip listemdeki her hisse ne durumda?"*
- **Girdi:** `tickers` (ops — verilmezse **favoriler** kaynağı), `sparkline` (bool, default `false`).
- **Çıktı:**
  ```json
  {"source": "favorites", "rows": [{"ticker": "THYAO", "price": 313.4,
    "change_pct": 0.93, "sparkline": null}], "generated_at": "…"}
  ```
- **Veri kaynakları:** `portfolio.favorites` (1, JWT — yalnızca `tickers` verilmediyse) + `current_price`×N + (sparkline ise `price_history`×N).
- **Boş/kısa davranış:** Favori yok ve `--tickers` verilmedi → `rows: []` + stderr notu ("Favori yok; --tickers ile liste verin"), **exit 0**. Tek ticker fiyatı yok → `price: null`.
- **CLI:** `fl helper watchlist [--tickers THYAO,ASELS] [--sparkline]`.
- **Kütüphane:** `watchlist_report(client, tickers=None, …) -> WatchlistReport`.
- **MCP:** `helper_watchlist_report(tickers=None, sparkline=False)`.

---

### 2.9 H9 — `price_alerts` · v1.5 · Efor M

- **Kullanıcı niyeti:** *"Hedef fiyata ulaşan hisseleri kontrol et."* — SDK'da alarm endpoint'i **yok**; eşikler **yerel** tanımlanır.
- **Girdi (modlar):** kontrol: `tickers` (ops — yoksa favoriler + eşikli ticker'lar); yönetim: `--set THYAO:320.0` (ekle/güncelle), `--clear THYAO`, `--list`.
- **Çıktı:**
  ```json
  {"alerts": [{"ticker": "THYAO", "threshold": 320.0, "price": 325.5,
               "direction": "above", "triggered": true}],
   "checked": ["THYAO", "ASELS"], "thresholds": {"THYAO": 320.0}}
  ```
- **Veri kaynakları:** yerel `~/.config/florence/alerts.json` (durum, `AlertStore` — cli-design §3.7 config dosyasından **ayrı** dosya; config allowlist'i bozulmaz) + `current_price`×N.
- **Boş/kısa davranış:** Eşik yok / hiçbiri tetiklenmedi → `alerts: []` (exit 0). Fiyat yok → `price: null, triggered: false`. Geçersiz eşik formatı (`--set THYAO:abc`) → exit 2.
- **CLI:** `fl helper alerts` / `fl helper alerts --set THYAO:320 --list` (yönetim modları stdout'a yerel durumu basar).
- **Kütüphane:** `price_alerts(client, …) -> AlertResult` + `AlertStore` (okuma/yazma; CLI ve MCP aynı store'u kullanır).
- **MCP:** `helper_price_alerts(action="check"|"set"|"clear"|"list", ticker=None, threshold=None)` — tek tool, dört eylem (kontrol niyeti ağırlıklı).

---

### 2.10 H10 — `export_watch` · v1.5 · Efor S

- **Kullanıcı niyeti:** *"Export'larım ne durumda? Bekleyen var mı?"* (ops: biri hazır olana dek bekle.)
- **Girdi:** `export_id` (ops), `wait` (bool, default `false`), `timeout` (default 300).
- **Çıktı:**
  ```json
  {"exports": [{"export_id": 9, "year": 2025, "format": "csv", "status": "ready",
                "row_count": …, "size": …, "ready": true}],
   "pending": 0}
  ```
- **Veri kaynakları:** `export.list_exports` (1, JWT) + (`wait` ise `export.wait_export(id)` — mevcut SDK poll'u, bloklayan; stderr progress).
- **Boş/kısa davranış:** Hiç export yok → `exports: []` + stderr notu, exit 0. `wait` + timeout → `TimeoutError` → exit 1 (altyapı — cli-design ile aynı). **Not:** `export_wait`/`export_download` zaten mevcut tool'lar; bu helper onları kopyalamaz — liste + durum özeti kompozisyonu yapar, `wait` yalnızca kolaylık modudur.
- **CLI:** `fl helper export-watch [--wait <id>] [--timeout 300]`.
- **Kütüphane:** `export_watch(client, export_id=None, wait=False, …) -> ExportWatch`.
- **MCP:** `helper_export_watch(export_id=None, wait=False, timeout=300)`.

---

### 2.11 H11 — `ipo_watch` · v1.5 · Efor S

- **Kullanıcı niyeti:** *"Yaklaşan/aktif halka arzlar: tarih, fiyat aralığı tek paket."*
- **Girdi:** `after` (ISO, ops).
- **Çıktı:**
  ```json
  {"upcoming": [{"slug": "…", "name": "…", "start_date": …, "price_range": …}],
   "active": [], "draft": []}
  ```
- **Veri kaynakları:** `misc.ipos_upcoming` + `misc.ipos_active` + `misc.ipos_draft` (3 çağrı, public).
- **Boş/kısa davranış:** IPO yok → boş listeler; exit 0.
- **CLI:** `fl helper ipo-watch [--after 2026-09-01]`.
- **Kütüphane:** `ipo_watch(client, after=None) -> IpoWatch`.
- **MCP:** `helper_ipo_watch(after=None)`.

---

### 2.12 H12 — `news_search` (anahtar kelime) · v2 · Efor M

- **Kullanıcı niyeti:** *"'Aselsan ihale' ile ilgili haber bul."* — SDK'da haber **arama** endpoint'i yok; yalnızca ticker bazlı `news` var. Yaklaşım: ticker seti üzerinde başlık eşleşmesi.
- **Girdi:** `query` (zor), `tickers` (ops — default: `stats_top(10)`), `amount_per_ticker` (default 3, 1–5), `limit` (default 10).
- **Çıktı:**
  ```json
  {"query": "aselsan ihale", "scanned_tickers": ["ASELS", "THYAO", …],
   "results": [{"ticker": "ASELS", "title": "…", "url": "…", "matched": ["aselsan", "ihale"]}],
   "total": 3, "rate_limited": false, "partial": false}
  ```
- **Veri kaynakları:** `stats_top` (1) + `market.news`×M (M ≤ ticker sayısı; 10/dk limiti!). Eşleşme: başlıkta case-insensitive substring + Türkçe karakter normalizasyonu (`i/İ/ı`, `ç`, `ş` …).
- **Boş/kısa davranış:** Eşleşme yok → `results: [], total: 0` (exit 0). **Rate limit (429) aşımı** → taranan ticker sayısını kısalt, `rate_limited: true, partial: true` ile dön — **hata değil**. Varsayılan 10 ticker × 3 haber = 30 çağrı > 10/dk → helper **içeriden** 8 çağrıda durur ve kısmi döner; kullanıcı `--tickers` ile daraltabilir.
- **CLI:** `fl helper news-search "aselsan ihale" [--tickers ASELS]`.
- **Kütüphane:** `news_search(client, query, …) -> NewsSearchResult`.
- **MCP:** `helper_news_search(query, tickers=None, amount_per_ticker=3)`.
- **v2 gerekçesi:** v1'de `news_digest` yeterli; arama, çok çağrılı ve rate-limit hassas olduğu için ikinci dalgaya bırakılır.

---

### 2.13 H13 — `news_summary` (LLM'li özet) · v2 · Efor L

- **Kullanıcı niyeti:** *"Son haberlerin 3-5 maddelik özeti."*
- **Girdi:** `ticker` (zor), `amount` (default 5), `max_points` (default 5), LLM ucu env'den (`FLORENCE_LLM_URL` + `FLORENCE_LLM_API_KEY` — OpenAI-uyumlu `/chat/completions`).
- **Çıktı:**
  ```json
  {"ticker": "THYAO", "articles": [{"title": "…", "url": "…", "content_excerpt": "…"}],
   "summary": {"points": ["…", "…"], "llm": "openai-compatible", "model": "…"} | null,
   "llm_available": true}
  ```
- **Veri kaynakları:** H1 `news_digest` çıktısı (içerikler zaten çekilir) + opsiyonel harici LLM çağrısı (yeni `helpers/_llm.py` — OpenAI-uyumlu tek POST; SDK'ya LLM bağımlılığı EKLENMEZ, yalnızca opsiyonel env yapılandırması).
- **Boş/kısa davranış:** LLM yapılandırılmamış → `summary: null, llm_available: false` — **hata değil**, digest çıktısı döner (düşüş = H1). LLM çağrısı başarısız → aynı düşüş + `llm_error` alanı. Haber yok → `articles: [], summary: null`.
- **CLI:** `fl helper news-summary THYAO [--amount 5]`.
- **Kütüphane:** `news_summary(client, ticker, …) -> NewsSummary`.
- **MCP:** `helper_news_summary(ticker, amount=5)` — açıklamada "harici LLM maliyeti olabilir; LLM yoksa digest döner" notu.
- **v2 gerekçesi:** LLM kararı açık karar noktası #2'ye bağlı; LLM'siz v1 (`news_digest`) bu helper'ın güvenli düşüşüdür.

---

## 3. İçerik Çekimi (News Fetch) Detayı

### 3.1 Yaklaşım

```
url → şema/SSRF guard → httpx.GET (follow_redirects=True, timeout, boyut sınırı)
     → content-type kontrolü → HTML → metin çıkarımı (trafilatura | stdlib fallback)
     → temizlik (boşluk sıkıştırma) → max_chars kırpma → Article
```

- **Transport:** `httpx` (SDK'nın mevcut bağımlılığı — yeni bağımlılık yok). `florence/clients/` diye ayrı bir paket **açılmaz** (açık karar #4); ilk sürüm `florence/helpers/_http.py` içinde özel amaçlı tek fonksiyon.
- **Bağımsız client:** `FlorenceClient`'a harici GET metodu **EKLENMEZ** — SDK sözleşmesi backend'e bağlıdır; harici çekim ayrı, izole bir transport'tur (kendi timeout, kendi UA, kendi hata tipi `ArticleFetchError`).
- **User-Agent:** tarayıcı benzeri (`Mozilla/5.0 … Chrome/…`) — birçok BIST haber sitesi (foreks, investing, şirket PR sayfaları) bot UA'yı reddeder. Yapılandırılabilir (`FLORENCE_NEWS_UA` env).
- **Cookie/oturum:** yok. **Retry:** yok (harici siteye retry eklemez; tek deneme + timeout).

### 3.2 HTML metin çıkarımı: trafilatura mı, stdlib mi?

| Aday | Artılar | Eksiler |
|---|---|---|
| **trafilatura** (önerilen) | Tek saf-Python bağımlılık (lxml gerektirmez, ~100KB), makale metni + başlık çıkarımında en iyi açık kaynak sonuç; reklam/nav/menü temizliği yerleşik; BIST haber siteleri dahil çoğu Türkçe haber sayfasında çalışır | Yeni bağımlılık (ağır değil ama sıfır değil); her site %100 değil |
| `readability-lxml` | Mozilla algoritması, iyi sonuç | **lxml = C extension** bağımlılığı (ağır, build riski); bakımı durgun |
| **stdlib `html.parser`** (fallback) | Sıfır bağımlılık; `<p>`/`<h1-6>` biriktirme yeterli | Reklam/nav temizliği yok — kalite düşük; elle kural yazmak gerekir |

**Karar önerisi:** **trafilatura opsiyonel extra** (`pip install florence-sdk[news]`) + **stdlib fallback**. Çekirdek, `import trafilatura` denemesi yapar; yoksa basit `html.parser` metin toplayıcıya düşer. Böylece:
- `florence-sdk` temel kurulumu bağımlılık şişirmez (mevcut felsefe: httpx+rich+typer minimal),
- helper katmanı trafilatura yokken de çalışır (kalite düşer, davranış bozulmaz),
- MCP/CLI'da `--no-content` zaten içeriksiz mod sunar.

Fallback çıkarıcı: `HTMLParser` ile `<h1..h6>, <p>, <li>, <blockquote>` metinlerini topla, `alt` etiketleri atla, boşlukları sıkıştır — "düz metin" niyeti için yeterli minimum.

### 3.3 Zaman/boyut sınırları

- **Timeout:** connect 5s + read 15s (varsayılan; `--timeout` ile artırılabilir, üst sınır 60s).
- **Boyut:** `Content-Length > 2MB` → reddet (`error: "too_large"`); chunked/uzun yanıtlarda stream okuyup **2MB'ta kes** (bellek güvenliği).
- **Çıktı limiti:** `max_chars` (default 8000) — metin kırpılır, `truncated: true` alanı eklenir.
- **Content-Type:** `text/html` (ve `application/xhtml+xml`) değilse → `content_available: false, error: "unsupported_type"` — PDF/image çekilmez (v1 kapsamı dışı, belgelenir).

### 3.4 Güvenlik (SSRF + şema guard)

Kullanıcı URL'si verirken risk düşüktür; ama **MCP'de URL'yi LLM de verebilir** → guard zorunludur:

1. **Şema allowlist:** yalnızca `http://` / `https://`. `file://`, `ftp://`, `data://`, `gopher://` → kullanım hatası (exit 2 / `error: "unsupported_scheme"`).
2. **Host engelleme:** localhost, `127.0.0.0/8`, `::1`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16` (metadata: `169.254.169.254`), `.local` TLD → reddet (`error: "blocked_host"`). IP literal ise doğrudan kontrol; domain ise **redirect sonrası yeniden çözümle** (aşağıda).
3. **Redirect zinciri:** `follow_redirects=True` (max 5) — **her ara/varış URL'si aynı guard'dan geçer** (SSRF atlama deseni: public URL → localhost'a redirect).
4. **TLS doğrulama:** açık (`verify=True`); otomatik sertifika kabulü YOK.
5. **Log:** çekilen URL ve durum loglanır; yanıt gövdesi asla loglanmaz (gizli veri sızıntısı).

### 3.5 Hata durumları özeti

| Durum | Sonuç | Exit |
|---|---|---|
| 404 / 403 | `error: "http_404"` / `"http_403"` | 0 (sonuç nesnesi) |
| JS-render/SPA (metin çıkarılamadı) | `content_available: false, needs_js: true` | 0 |
| 2MB+ sayfa | `error: "too_large"` | 0 |
| PDF/image | `error: "unsupported_type"` | 0 |
| Şema/host engelli | `error: "unsupported_scheme"/"blocked_host"` | 2 (kullanım) / 0 (sonuç, bağlama göre) |
| DNS/TLS/timeout/ağ | `ArticleFetchError` (NetworkError benzeri) | 1 (altyapı) |
| `news` endpoint 401/429 (digest içinde) | `FlorenceAPIError` | 1 (ana kaynak erişilemez) |

---

## 4. Üç Seviye Entegrasyon Deseni

### 4.1 Çekirdek: `src/florence/helpers/` (tek doğruluk kaynağı)

```
src/florence/helpers/
├── __init__.py      # public yüzey: news_digest, fetch_article, ticker_briefing, …
├── models.py        # pydantic sonuç modelleri (NewsDigest, Article, Briefing, Pulse, …)
│                    #   — _Lenient(extra="allow") deseni (models.py ile aynı); model_dump() = --json/MCP şeması
├── _http.py         # harici GET: timeout, 2MB cap, UA, şema/SSRF guard, redirect doğrulama
├── _extract.py      # trafilatura (opsiyonel import) + stdlib html.parser fallback
├── _llm.py          # (v2) OpenAI-uyumlu özet POST (FLORENCE_LLM_URL env)
├── _alerts_store.py # (H9) alerts.json okuma/yazma (chmod 600)
├── news.py          # H1 news_digest (+ H12 news_search, H13 news_summary)
├── article.py       # H2 fetch_article
├── briefing.py      # H3 ticker_briefing
├── pulse.py         # H4 market_pulse
├── portfolio.py     # H5 portfolio_health
├── macro.py         # H6 macro_briefing
├── compare.py       # H7 compare_tickers
├── watchlist.py     # H8 watchlist_report
├── alerts.py        # H9 price_alerts
├── export_watch.py  # H10 export_watch
└── ipos.py          # H11 ipo_watch
```

**İmza deseni:** client **enjeksiyonlu** saf fonksiyonlar — modül seviyesinde global client YOK:

```python
def news_digest(client: FlorenceClient, ticker: str, amount: int = 5,
                fetch_content: bool = True, max_chars: int = 6000) -> NewsDigest: ...
async def news_digest_async(client: AsyncFlorenceClient, …) -> NewsDigest: ...
```

- Senkron + asenkron **ikiz** imzalar (SDK'nın `FlorenceClient`/`AsyncFlorenceClient` ikiliğiyle aynı desen).
- `florence/__init__.py`'ye helpers export'u: `from .helpers import news_digest` (SDK seviyesinde erişilebilir).
- `client.helpers` property **eklenmez** (karar: açık fonksiyon çağrısı > gizli property; resource katmanı endpoint'lere, helpers katmanı niyetlere hizmet eder — karıştırılmaz).

### 4.2 CLI: `src/florence/cli/commands_helper.py` — yeni `helper` grubu

- `helper_app = typer.Typer(help="Semantik yardımcı kompozitler (tek niyet = tek komut).")`
- `app.py`'ye kayıt → **11. grup**: `app.add_typer(commands_helper.helper_app, name="helper", …)`.
- **Komut adları (kebab-case, mevcut isimlerle çakışmaz):** `news-digest`, `article`, `briefing`, `pulse`, `portfolio-health`, `macro-briefing`, `compare`, `watchlist`, `alerts`, `export-watch`, `ipo-watch`, `news-search`, `news-summary`.
- **Komut deseni (mevcut commands_market.py ile birebir):** `state = _state(ctx)` → `state.apply_flags(json_output, verbose)` → `helper_sonuc = news_digest(state.client(), …)` → `--json` ise `emit_json(sonuc.model_dump())`, değilse helper'a özel insan render'ı.
- **İnsan render'ı:** kompozit çıktı tek tablo değildir → rich **panel/bölüm** düzeni (ör. briefing: fiyat KV bloğu + sparkline + haber listesi). Tablo kırpma (40 karakter), TR sayı biçimi, boş liste "kayıt yok" kuralları cli-design §3.4'ten devralınır.
- **Exit code'lar:** 0 başarı (boş/kısa/kısmi sonuç dahil) · 1 altyapı hatası (ağ, auth, özellik yok) · 2 kullanım (geçersiz URL şeması, tek ticker compare, kötü eşik formatı). `--json` hataları stderr'de tek JSON satırı (cli-design §3.1).
- **`--no-content` / `--timeout` / `--max-chars`** gibi helper'a özgü bayraklar yalnızca ilgili komutta (gereksiz bayrak yasağı korunur).

### 4.3 MCP: `helper_*` domaini

- `florence_mcp/registry.py`: `GROUPS` tuple'ına `"helpers"` eklenir (MCP_DISABLE_GROUPS=helpers ile kapatılabilir — mevcut filtre mekanizması bedavaya çalışır).
- Her helper → `ToolSpec(name="helper_<isim>", group="helpers", description="…")`. Tool adı CLI komutunun düz karşılığı: `news-digest` → `helper_news_digest` (mcp-design §2.1 isimlendirme deseni).
- `florence_mcp/tools.py` → `ToolHandlers`'a metotlar; hepsi `tool_handler` sarmalayıcılı, `json_result(sonuc.model_dump())` ile döner. **İş mantığı YOK** — helpers fonksiyonunu çağırır (mcp-design ilke 1: ince adaptör).
- `server.py` kayıt döngüsü değişmez (registry'den geçer) → helper'lar otomatik 93+ tool olur.
- **Açıklamalara gömülen notlar:** çağrı sayısı ("5 backend + N harici HTTP isteği"), rate limit uyarısı (news 10/dk → news_digest/news_search), LLM maliyeti (news_summary — 🔵 `EXTERNAL` işareti önerilir: "harici servis çağırır", kredi değil), boş-sonuç davranışı ("haber yoksa boş liste döner, hata değil").
- **Yıkıcılık:** helper'lar salt-okuma → danger/credit/confirm işaretleri yok; `write` yok.

### 4.4 Çakışma / gereksizlik kuralları (CLI tasarım ilkeleriyle hizalı)

1. **Endpoint komutları dokunulmaz.** `fl market news`, `fl market price`, `fl portfolio risk` vb. aynen kalır; helper onların **üstüne** biner. `fl market news` (ham liste) ↔ `fl helper news-digest` (içerikli) farkı tool açıklamasında/yardımda netleştirilir.
2. **İki helper aynı niyeti kompoze edemez.** `news_summary`, `news_digest`'ın içine gömülmez (LLM opsiyonel olduğu için ayrı helper); `watchlist_report` + `price_alerts` aynı veriyi farklı niyetle sunar (görüntü vs eşik kontrolü) — çakışma değil.
3. **`--json` şeması = helper modeli.** API şemasından bağımsızdır (kompozit istisnası — cli-design §2.0). Helper modeli değişirse `--json` ve MCP çıktısı **birlikte** değişir (tek kaynak: `helpers/models.py`).
4. **Ad disiplini:** komut seviyesinde alias yok (cli-design §1.4-2); helper adları İngilizce kebab-case (CLI) / snake_case (MCP), yardım Türkçe; `normalize_ticker` helper'ların tüm ticker girdilerinde uygulanır.
5. **Yeni helper ekleme kuralı:** niyet → mevcut SDK metotlarıyla karşılanıyor mu? (karşılanıyorsa helper değil, komut); en az 2 kaynak kompoze ediyor mu? (tek kaynak ise helper değil — endpoint komutu yeterli); boş-sonuç davranışı tanımlı mı? → üçü de evet ise kataloğa girer.

### 4.5 Test stratejisi (tasarım notu)

- Helper'lar saf fonksiyon → `respx` ile mock (mevcut test altyapısı): her helper için "normal", "boş", "kısmi hata", "auth yok" senaryosu.
- `_http.py`: SSRF guard + redirect doğrulama + boyut kesme için ayrı testler (güvenlik kritik).
- `_extract.py`: trafilatura yokken fallback çıktısı testi (bağımlılık opsiyonelliğinin garantisi).

---

## 5. Öncelik Sırası

### 5.1 v1 — çekirdek (6 helper, LLM'siz)

| Sıra | Helper | Efor | Neden önce |
|---|---|---|---|
| 1 | `fetch_article` (H2) | M | Tüm içerik işlerinin alt yapısı; önce taşınmazsa news_digest yazılamaz |
| 2 | `news_digest` (H1) | M | Kullanıcı örneğinin birebir karşılığı — katalogun amiral gemisi |
| 3 | `ticker_briefing` (H3) | M | En sık soru ("X hissesi nasıl?") tek çağrıya iner |
| 4 | `market_pulse` (H4) | S | Sabah rutini; tamamı public (kimliksiz bile çalışır) |
| 5 | `portfolio_health` (H5) | M | Portföy özeti — en değerli JWT helper'ı |
| 6 | `macro_briefing` (H6) | S | Ekonomi paketi; string→float normalizasyonu tek yerde |

### 5.2 v1.5 — ikinci dalga (5 helper)

| Sıra | Helper | Efor | Not |
|---|---|---|---|
| 7 | `compare_tickers` (H7) | S-M | 2N+1 çağrı; rate-limit riski yok |
| 8 | `watchlist_report` (H8) | S | H7 ile aynı `current_price` loop'unu paylaşır |
| 9 | `price_alerts` (H9) | M | Yerel durum dosyası ekler (alerts.json) — tek "durumlu" helper |
| 10 | `export_watch` (H10) | S | Mevcut SDK metotlarının kompozisyonu, neredeyse bedava |
| 11 | `ipo_watch` (H11) | S | 3 public çağrı; halka arz meraklısı hedef kitle |

### 5.3 v2 — LLM'li / çok çağrılı (2 helper)

| Sıra | Helper | Efor | Bağımlılık |
|---|---|---|---|
| 12 | `news_search` (H12) | M | Rate-limit yönetimi (kısmi sonuç); LLM gerekmez |
| 13 | `news_summary` (H13) | L | Karar noktası #2'ye bağlı (LLM ucu); düşüşü H1 |

**v1 gerekçesi:** LLM'siz kalır — kullanıcı örneği ("haber yoksa hata vermez, boş çıktı döner") içerik çekimi + boş davranışı gerektirir, özetleme gerektirmez. AI tüketiciler (MCP) zaten dışarıdaki LLM'leriyle digest çıktısını kendileri özetleyebilir.

---

## 6. Açık Karar Noktaları

| # | Karar | Seçenekler | Öneri |
|---|---|---|---|
| 1 | **trafilatura bağımlılığı** | (a) Zorunlu bağımlılık · (b) Opsiyonel extra `florence-sdk[news]` + stdlib fallback · (c) Sadece stdlib | **(b)** — temel kurulum minimal kalır, davranış her koşulda çalışır, kalite trafilatura ile yükselir |
| 2 | **news digest/summary LLM'li mi?** | (a) v1'den LLM'li (harici OpenAI-uyumlu çağrı) · (b) LLM'siz v1 + LLM'li v2 (`news_summary`, env ile kapatılabilir) · (c) SDK'ya LLM bağımlılığı ekle | **(b)** — SDK'ya LLM bağımlılığı EKLENMEZ; v1'de `news_digest` ham içerik verir, MCP'de LLM zaten dışarıda, CLI'da kullanıcı çıktıyı kendi AI'ına verebilir. Backend `generate_report` haber özeti için KULLANILMAZ (rapor ≠ haber özeti, kredi harcar) |
| 3 | **CLI'da yeni grup mu, mevcut gruplara dağıtım mı?** | (a) Yeni `fl helper …` grubu · (b) Mevcut gruplar (`fl market briefing`, `fl portfolio health`) · (c) Flat üst-komutlar (`fl digest`, `fl pulse`) | **(a)** — kompozitler cli-design §1.2-5 "komut ağacı = SDK envanteri" kuralını bilinçli olarak aşar; ayrı grup bu ayrımı netleştirir, `MCP_DISABLE_GROUPS=helpers` simetrisi korunur, isim çakışması riski sıfırlanır |
| 4 | **Harici HTTP client nerede yaşar?** | (a) `florence/helpers/_http.py` (özel amaçlı) · (b) Yeni `florence/clients/` paketi (genel amaçlı) | **(a)** önce — tek tüketici var (fetch_article ailesi); ihtiyaç (ör. LLM ucu + haber çekimi birlikte büyürse) artarsa `clients/`'a taşınır. `FlorenceClient`'a harici GET EKLENMEZ (sözleşme) |
| 5 | **MCP isimlendirme** | (a) `helper_*` öneki + GROUPS'a "helpers" · (b) Mevcut domain'lere dağıt (`market_news_digest`, `portfolio_health`) | **(a)** — kompozit doğasını LLM'e belli eder; tek kapatma anahtarı (`MCP_DISABLE_GROUPS=helpers`); domain dağılımı `market_*`/`portfolio_*` isim alanını şişirir |
| 6 | **`price_alerts` yerel durumu** | (a) Ayrı `~/.config/florence/alerts.json` · (b) config.toml `[alerts]` bölümü | **(a)** — cli-design §3.7 config allowlist'i (`api_url`, `default_output`) bozulmaz; `fl config set` kapsamı genişlemez; eşikler kullanıcı verisi, config ayarı değil |

---

## 7. Kapsam Dışı (bilinçli)

- **Yazma kompozitleri:** "portföye ekle + işlem kaydet" gibi çok adımlı yazma akışları helper değildir (kullanıcı niyeti tek endpoint'le karşılanır; kompozit yazma = hata yüzeyini büyütür).
- **Kredi harcayan kompozit:** `generate_report` + `simulate` helper'a girmez (maliyet/uzunluk/onay semantiği ayrı katmandır — mcp-design §4).
- **Haber kaynağı ekleme:** SDK'ya RSS/harici haber toplayıcı EKLENMEZ; helper yalnızca backend'in verdiği `news` item'larının URL'lerini çeker (kullanıcı örneğindeki "link olabilir" modu H2 ile karşılanır).
- **PDF/OCR içerik çekimi:** `unsupported_type` (v1); talep olursa v2 adayı.
- **Gerçek zamanlı alarm/push:** `price_alerts` yalnızca **talep üzerine kontrol** (poll); push/daemon CLI v1 kapsamı dışı (TUI/ajan katmanının işi).

---

## 8. Özet

- **13 helper** (10–15 aralığında): 6'sı v1, 5'i v1.5, 2'si v2; efor S×5 / M×7 / L×1.
- Üç seviye tek çekirdekten: `florence/helpers/` (fonksiyonlar + pydantic modeller) → `fl helper <komut>` (11. CLI grubu) → `helper_*` MCP tool'ları (GROUPS'a "helpers").
- Boş/kısa/kısmi sonuç disiplini: boş = exit 0 + boş liste/null; kısmi = ilgili alanda hata kodu, paket döner; yalnızca altyapı hatası = exit 1.
- İçerik çekimi: httpx (mevcut bağımlılık) + trafilatura (opsiyonel) / stdlib fallback; timeout 15s, 2MB cap, şema+SSRF+redirect guard.
- Açık kararlar: trafilatura (öneri: opsiyonel extra), LLM (öneri: v2, SDK'ya bağımlılık yok), CLI grubu (öneri: yeni `helper`), harici client yeri (öneri: `helpers/_http.py`), MCP öneki (öneri: `helper_*`), alerts durumu (öneri: ayrı `alerts.json`).
