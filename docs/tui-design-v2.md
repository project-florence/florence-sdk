# TUI Tasarım Raporu v2 — `fl tui` (Faz A–E)

> **Durum:** UYGULANDI — bu rapor `src/florence/tui/` implementasyonunun ve `fl tui`
> komutunun güncel teknik şartnamesidir (tui-design.md'nin revizyonu).
> **Tarih:** 2026-08-18 · **Plan:** `.hermes/plans/2026-08-18_210253-florence-sdk-tui-v2.md`
> **Teknoloji:** Textual (Rich tabanlı, klavye dostu) + **ccharts** (grafik, zorunlu bağımlılık)
> **Canlılık:** WebSocket YOK — 30–60s polling
> **Kapsam:** Pano + Watchlist + Ticker detay/grafik + Portföy (Faz E, P7 onayı)

---

## 1. Giriş

**TUI (Text User Interface)** — terminalde çalışan tam ekran, interaktif bir kullanıcı arayüzüdür.
CLI'ın "bir komut çalıştır, çıktıyı gör" modelinden farklı olarak TUI, ekranı **kalıcı olarak**
kaplar, klavye ile gezilir ve veri **periyodik olarak kendini yeniler**. `fl tui` kullanıcıya,
tarayıcı açmadan veya komutları tekrar tekrar yazmadan BIST'i izleme imkânı verir: piyasa durumu,
öne çıkan hisseler, altın/döviz, favorilerinin canlı fiyatları, ticker grafikleri ve (v2) portföy
görünümü tek ekranda.

### 1.1 Neden Textual?

| Kriter | Textual | Alternatifler (blessed, urwid, curses) |
|---|---|---|
| **Klavye dostu** | Yerleşik `BINDINGS` sistemi, `Footer` otomatik ipuçları | Manuel key handling |
| **Widget seti** | `DataTable`, `Header`, `Footer`, `Static`, `ModalScreen` hazır | Çoğu elle çizilir |
| **Asenkron** | Kendi asyncio event loop'u + `set_interval` + `Worker` deseni | Senkron, bloklayıcı |
| **Test edilebilirlik** | Yerleşik headless test API (`App.run_test()` + `Pilot`) | Yok / zayıf |
| **Ekran yönetimi** | `Screen` sınıfları, `push`/`switch`, screen stack | Yok |
| **Stil** | CSS benzeri Textual CSS, otomatik renk teması (dark/light) | Ham renk kodları |

Textual, Rich üzerine kuruludur; SDK'nın CLI katmanı da Rich kullanır (cli-design.md) — ekosistem
aynıdır. WebSocket gerektirmez — veri kaynağı zaten 15 dk gecikmeli olduğundan (kullanıcı kararı,
2026-08-14) 30–60s polling yeterlidir ve dakikalık rate limit bütçesi rahatça karşılanır.

**Grafikler (v2 revizyonu, P1):** v1 tasarımındaki Textual `Sparkline` tabanlı yaklaşımın yerini
**ccharts** (C ile yazılmış hızlı ANSI chart motoru, PyPI: `ccharts>=0.2.0`) almıştır. ccharts,
SDK'nın **zorunlu ana bağımlılığıdır** — "CLI kuran TUI'yi de kurar" felsefesiyle aynı: TUI
grafikleri her kurulumda çalışır, ayrı extra yok, sessiz fallback yok (Y1). Ekranlar ccharts'ı
**doğrudan import etmez**; `tui/charts.py` adapter katmanı üzerinden geçer (Y2/K2 revizyonu,
bölüm 5).

### 1.2 Çağrı: `fl tui`

- Komut: **`fl tui`** (tek komut, argümansız — K5 kararı). `fl` alias'ı kullanıcı onayıyla
  kesinleşmiştir (gh/cargo/npm geleneği).
- **CLI bağlantısı:** `src/florence/cli/commands_tui.py` — isimsiz `typer.Typer` (`tui_app`)
  `src/florence/cli/app.py` içinde `app.add_typer(commands_tui.tui_app)` ile üst seviyeye eklenir;
  komut `fl tui` olarak görünür. Komut gövdesi tek iş yapar: `from florence.tui.app import main;
  main()` (geç import — dairesel bağımlılık yok). TUI mantığı `florence/tui/` içindedir.
- **Kurulum:** TUI, CLI ile **birlikte** kurulur (kullanıcı kararı: "CLI kuran TUI'yi de kurar",
  tek install). `pyproject.toml` ana `dependencies`'ine `textual>=0.60` ve `ccharts>=0.2.0` eklenir
  — ayrı extra AÇILMAZ; `fl tui` çalışmayan bir kurulum "yarım kurulum"dur (P1).
- **Çıkış/geri dönüş:** `q` ile TUI'den çıkılır, terminal normal shell'e döner. TUI sırasında
  terminal alternatif ekran buffer'ına geçer (Textual varsayılanı); çıkışta ekran eski haline döner.

### 1.3 Kullanıcı kimliği ve oturum

`fl tui` **kendi login akışı istemez**. `fl auth login` ile girilmiş kalıcı oturum (keyring +
FileTokenStore fallback — bkz. bölüm 6.2) SDK'nın varsayılan token store'undan otomatik okunur.
Auth gerektiren bölümler (watchlist/favoriler, haberler, portföy) oturum yoksa ekranda yönlendirme
gösterir; pano (public veri) auth'suz da çalışır.

---

## 2. Ekranlar

Dört ekran (Faz E sonrası): pano, watchlist, portföy + detay görünümü. Pano/watchlist/portföy
`Screen` alt sınıfıdır; uygulama `App.SCREENS` kaydı üzerinden `switch_screen(...)` ile geçiş
yapar, detay ekranı `push_screen` ile açılır (geri dönüş `esc`/`pop_screen`). Sebep: detay ekranı
"üstüne açılan" bir görünümdür; pano ↔ watchlist ↔ portföy ise eşit seviye geçişlerdir (K3 —
TabbedContent alternatifi reddedildi).

Ortak çerçeve (tüm ekranlarda):

```
┌──────────────────────────────────────────────────────────────┐
│ Header: Florence · fl tui          [saat]  [piyasa: AÇIK/KAPALI] │  ← Textual Header + PiyasaDurumu
├──────────────────────────────────────────────────────────────┤
│                    (ekran içeriği — aşağıda)                  │
├──────────────────────────────────────────────────────────────┤
│ Footer: [q] Çıkış  [1] Pano  [2] İzleme  [4] Portföy  [r] Yenile  [h] Yardım │
└──────────────────────────────────────────────────────────────┘
```

- **Header:** Textual'ın yerleşik `Header` widget'ı (uygulama adı + saat). Sağında piyasa durumu
  göstergesi: `market_status()` → `{open, next_open_at, holiday}` (public, 60s backend cache).
  `open=True` → yeşil **AÇIK**; `open=False` → kırmızı **KAPALI** (+ `next_open_at` saati);
  `holiday=True` → sarı **TATİL**. Şerit metni `tui/data.py`'deki `status_bar_text()` /
  `market_status_text()` yardımcılarıyla üretilir (App seviyesinde ortak — tüm ekranlarda görünür).
- **Footer:** Textual `Footer`, `BINDINGS` listesinden otomatik doldurulur — elle ipucu yazılmaz.
  Aktif ekranın bindings'leri + uygulama seviyesi bindings birleşir.

### 2.1 PANO (`DashboardScreen`)

**Amaç:** Piyasanın 10 saniyelik özeti. Bir bakışta: piyasa açık mı, hangi hisseler öne çıkıyor,
günün hareketleri neler, altın/döviz ne durumda.

**Layout şeması:**

```
┌──────────────────────────────────────────────────────────────┐
│ Header · piyasa durumu şeridi                                 │
├───────────────────────────────┬──────────────────────────────┤
│  ÖNE ÇIKANLAR (stats_top)      │  GÜNÜN HAREKETLERİ           │
│  Ticker   İlgi                 │  Ticker  Fiyat   Δ%          │
│  THYAO     99                  │  [gainers/losers tablosu]    │
│  ASELS     87                  │  ...                         │
│  (DataTable, satır seçilebilir)│  (DataTable; g/l sekmeli)    │
├───────────────────────────────┴──────────────────────────────┤
│  DEĞERLİ MADEN / DÖVİZ ŞERİDİ                                 │
│  Gram Altın 40,25 │ Çeyrek 3.450 │ USD/TRY 42,10 │ EUR/TRY 45,30 │
└──────────────────────────────────────────────────────────────┘
```

**Veri kaynakları (tümü public, auth'suz):**

| Panel | Resource metodu | Parametreler | Poll aralığı |
|---|---|---|---|
| Üst bar: piyasa durumu | `market.market_status()` | — | 60s (backend zaten 60s cache) |
| Öne çıkanlar | `market.stats_top(limit)` | `limit` ← config `tui_top_limit` (default 10) | 45s (config `tui_refresh_seconds`) |
| Günün hareketleri | `market.companies_summary(limit, sort=...)` | `limit` ← config `tui_summary_limit` | 45s |
| Maden/döviz şeridi | `economy.gold_prices()` + `economy.currency(symbols="USD,EUR")` | — | 45s |

- **Öne çıkanlar tablosu:** `stats_top` → `[{"ticker": "THYAO", "count": 99}, ...]`. Sütunlar:
  `Ticker`, `İlgi`. İlgi sütunu count değerine göre kayan renk (yüksek = vurgulu). Bu tablo
  **fiyat bilmez** — yalnızca popülerlik sıralamasıdır; başlıkta "Öne Çıkanlar (ilgi)" yazar.
- **Günün hareketleri:** `companies_summary` `sort="gainers"` / `sort="losers"` (backend destekli
  sort değerleri — birebir). Sütunlar: `Ticker`, `Fiyat`, `Δ%`. Δ% hücresi **renkli** (yeşil
  yükseliş / kırmızı düşüş — TR BIST konvansiyonu, bölüm 5.3). Varsayılan sekme **Gainers**;
  `g`/`l` tuşları veya Tab ile Gainers↔Losers geçişi. Her iki liste tek `companies_summary` çağrısı
  ailesinden gelir (iki ayrı sort ile 2 istek). Sütun şeması openapi'den gelen alan adlarına göre
  implementasyonda netleşir — implementasyon, yanıtın gerçek anahtarlarını birebir kullanır,
  uydurma alan yok.
- **Maden/döviz şeridi:** Tek satır `Static` (`tui/data.py::gold_summary` ile seçilen 3 altın
  kalemi + döviz). Gösterimde **olduğu gibi** TR virgüllü string basılır, sayısal işlem yok
  (economy değerlerinin string olması bilinçli bir pitfall'dır — economy_res.py docstring).
- **Satır seçimi → detay:** Öne çıkanlar ve hareketler tablolarında satır seçip `enter` →
  `DetailScreen(ticker)` push edilir (watchlist'teki aynı akış). `f` ile seçili ticker favorilere
  eklenir/çıkarılır (JWT).

**Yükleme / hata / boş durumlar:**

| Durum | Gösterim |
|---|---|
| İlk yükleme | Ekran boş gelmez; her panel kendi `Loading…` placeholder'ı ile başlar, worker bitince dolar |
| Network hatası (`NetworkError`) | Pano üstünde kırmızı banner: `Bağlantı hatası — son veri gösteriliyor (12:04)`. Önceki veri **silinmez** |
| 429 (`RateLimitError`) | Banner: `Rate limit — {retry_after}s sonra tekrar deneniyor`. Poll interval geçici uzatılır (bölüm 4.4) |
| Piyasa kapalı | Üst şerit `KAPALI` + `next_open_at`; tablolar yine dolar (son kapanış verisi) |
| Boş yanıt (örn. stats_top boş liste) | Panel: `Veri yok` — tablo değil, kısa metin |
| `FLORENCE_API_URL` yanlış | İlk tick'te `NetworkError` → banner + footer'da ipucu: `fl config set api_url …` |

### 2.2 WATCHLIST (`WatchlistScreen`)

**Amaç:** Kullanıcının favori hisselerinin canlı fiyatları + kısa dönem eğilimi (watchlist mini
grafiği — ccharts tek satır). Satır seç → sağ panelde önizleme; `enter` → tam detay ekranı.

**Layout şeması:**

```
┌──────────────────────────────────────────────────────────────┐
│ Header · piyasa durumu şeridi                                 │
├───────────────────────────────────────┬──────────────────────┤
│  İZLEME LİSTESİ (favoriler)           │  ÖNİZLEME (seçili)   │
│  Ticker  Fiyat   Δ%    Grafik         │  ┌────────────────┐  │
│  THYAO   313,40  +0,93 ▁▂▃▅▆▇█       │  │ ASELS          │  │
│  ASELS   1.234   -1,20 █▆▅▄▃▂▁       │  │ Aselsan Elektronik│ │
│  ...                                   │  │ [mini grafik]  │  │
│  (DataTable + satır cursor)            │  └────────────────┘  │
│                                        │  (company_info +    │
│                                        │   kısa history)     │
├───────────────────────────────────────┴──────────────────────┤
│ Footer                                                         │
└──────────────────────────────────────────────────────────────┘
```

**Veri kaynakları:**

| Bileşen | Resource metodu | Auth | Not |
|---|---|---|---|
| Favori listesi | `portfolio.favorites()` | JWT | `["THYAO", "ASELS"]` — kaynak config `tui_watchlist_source` (P8: yalnızca `"favorites"` kabul edilir; `"local"` geleceğe genişleme notu) |
| Satır fiyatı | `market.current_price(ticker)` | public | `{ticker, price, change_pct, market_status}` |
| Grafik verisi | `market.price_history(ticker, period="1mo", interval="1d")` | public | `close` değerleri → `tui/charts.py` spark_text / tek satır |
| Önizleme: şirket bilgisi | `market.company_info(ticker)` | public | `longName` vb. |
| Önizleme: mini grafik | aynı `price_history` (önbellekten) | public | 10dk TTL cache ile tek istek |

- **Poll akışı (tek tick):** `favorites()` (1 istek) → her ticker için `current_price` +
  `price_history(1mo)` — N favori için 2N istek. 10 favori = 21 istek / 45s → api rate limit
  (30/s) rahatça karşılanır. **Cache kuralı (bölüm 4.5):** aynı ticker'ın `current_price`'ı 60s
  TTL; `price_history` 10dk TTL — Watchlist ile Detay ekranı aynı ticker'ı paylaşınca tek istek.
- **Grafik sütunu:** son 30 işlem günü (`1mo` + `1d`) `close` serisi → mini braille/blok grafik
  (ccharts tek satır render — bölüm 5). Sütun dar tutulur (~12 karakter); değerler normalizasyonla
  `[0,1]`'e çekilir.
- **Δ% rengi:** `change_pct` işaretine göre yeşil/kırmızı; sıfır gri (`tui/data.py::delta_style`).
  Watchlist grafik rengi **dönem getirisine** bağlanır (serinin ilk ve son close'u karşılaştırılır)
  — günlük Δ%'den bağımsız (bölüm 5.3).
- **Fiyat formatı:** TR ondalık ayracı (`313,40`) + binlik ayraç (`1.234,50`) — `tr_number` /
  `tr_delta` yardımcıları (data.py) — hedef kitle TR BIST yatırımcısı.
- **Satır seç → önizleme:** DataTable satır cursor'ı hareket ettikçe sağ panel
  `company_info(ticker)` + mini grafik ile yenilenir (her hareket istek atmaz — seçili ticker
  değişince yalnızca cache'te olmayan veri çekilir).
- **`enter` → detay:** `DetailScreen(ticker)` push.

**Boş watchlist:**
```
Favoriniz yok.
CLI'dan ekleyin:  fl portfolio favorite add THYAO
(Pano ekranında bir hisse seçip `f` ile de ekleyebilirsiniz)
```
Alt satırda ipucu: `fl portfolio favorite add <TICKER>` ile listeye ekleyin; sonra `r` ile
yenileyin.

**Auth yok:** `client.auth.is_authenticated() == False` ise watchlist içeriği yerine uyarı
(bölüm 6.3): `Oturum bulunamadı — 'fl auth login' ile giriş yapın`. Pano etkilenmez.

**Hata durumları:** genel kurallar pano ile aynı (banner + son veri). `favorites()` 401 dönerse
(oturum süresi doldu, refresh başarısız) watchlist ekranında `Oturum süresi doldu — tekrar giriş
yapın (fl auth login)`; SDK client'ı 401'de otomatik single-flight refresh dener, yalnızca o da
başarısızsa bu mesaj görünür.

### 2.3 DETAY / GRAFİK (`DetailScreen`)

**Amaç:** Tek ticker'ın tam görünümü: şirket bilgisi, büyük grafik (period seçilebilir, tip
line↔candle), güncel fiyat ve haberler.

**Layout şeması:**

```
┌──────────────────────────────────────────────────────────────┐
│ Header · piyasa durumu şeridi                                 │
├──────────────────────────────────────────────────────────────┤
│  ASELS — Aselsan Elektronik Sanayi (SAVUNMA)                  │
│  Fiyat: 1.234,50   Δ: -1,20%   Piyasa: AÇIK   [period: 3 Ay] │
│                                                [tip: mum]    │
├──────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────┐  │
│  │  GRAFİK (3 Ay · mum) — ccharts CChartCandle            │  │
│  │  en yüksek 1.280 ──▄▄▆█▆▄──                            │  │
│  │  son 1.234 ──────────▄▄▆█▄──                           │  │
│  │  [eksen etiketleri: min / son / max]                   │  │
│  └────────────────────────────────────────────────────────┘  │
│  HABERLER (news, JWT — auth yoksa gizlenir)                  │
│  • THYAO haberi (2s önce)                                    │
├──────────────────────────────────────────────────────────────┤
│ Footer: [1|3|6|y] dönem  [c] çizgi/mum  [esc] geri  [r] yenile │
└──────────────────────────────────────────────────────────────┘
```

**Veri kaynakları:**

| Bileşen | Resource metodu | Auth | Poll aralığı |
|---|---|---|---|
| Şirket bilgisi | `market.company_info(ticker)` | public | Ekran açılışında + her 5 dk |
| Güncel fiyat | `market.current_price(ticker)` | public | 45s |
| Grafik | `market.price_history(ticker, period=<seçili>, interval="1d")` | public | Period/tip değişince + 5 dk |
| Haberler | `market.news(ticker, amount=10)` | **JWT + news feature** | 90s (2. tick'ta) |

- **Üst bilgi satırı:** `company_info` → `longName` + sektör alanı. Fiyat + Δ%
  `current_price`'tan; piyasa durumu `market_status` (header şeridinden ortak).
- **Period seçimi (klavye):** `1`/`3`/`6`/`y` tuşları → `1mo`/`3mo`/`6mo`/`1y` (keys.py
  `PERIODS` haritası). Varsayılan `tui_default_period` config'inden (default `1mo`). Period
  değişince grafik `Loading…` gösterir, yeni `price_history` gelince çizilir.
- **Grafik tipi (P6):** `c` tuşu line ↔ candle toggle (`keys.KEY_CHART_TOGGLE`); başlangıç tipi
  config `tui_default_chart` (default `line`). Grafik başlığı tipi gösterir: `GRAFİK (3 Ay · mum)`.
  Period ayrı eksendir — `1/3/6/y` tipi değiştirmez (P6 kararı: iki bağımsız eksen).
- **Grafik:** ccharts tabanlı `CChartLine` / `CChartCandle` widget'ları (`widgets/charts.py`).
  `DataService`'in `get_price_history` → `update_data(rows)` → `ohlc_rows()` → `Chart` →
  `line()/candle()` → `Text.from_ansi` (renk korunur). Y ekseni etiketleri: dönem içi min/son/max
  değerleri (TR format); `show_prices`/`show_times` açık. `high`/`low` alanları openapi şemasında
  boş olabilir → P2 sentez kuralı (bölüm 5.2): `high=max(open, close)`, `low=min(open, close)` —
  "yaklaşık mum", docstring'de nota bağlı.
- **Haberler:** `news()` **10/dk rate limit + JWT** (market_res.py docstring'den birebir). Bu
  yüzden haberler 45s'lik ana tick'te değil, **her 2. tick'ta (90s)** çekilir → 0,67 istek/dk,
  limitin çok altında. `news` feature kapalıysa (403) haber paneli sessizce gizlenir.
  - Auth yoksa haberler bölümü hiç gösterilmez; yerine tek satır: `Haberler için giriş yapın: fl auth login`.
- **Geri dönüş:** `esc` → `pop_screen()` (geldiği ekrana döner: watchlist, pano veya portföy).

**Yükleme / hata durumları:** ortak banner kuralları. Grafik verisi yoksa (boş liste) grafik
alanı: `Bu dönem için veri yok`. `current_price` hatasında üst satır gri `—` gösterir, fiyat
silinmez (son bilinen değer + zaman damgası).

### 2.4 PORTFÖY (`PortfolioScreen`) — v2 KAPSAMDA (P7)

v1 tasarımında "kapsam dışı" notu olan portföy ekranı v2'de **kapsama alınmıştır** (P7 kararı,
Faz E). Bu bölüm v2 tasarım sözleşmesidir; implementasyon Faz E'de tamamlanır.

**Amaç:** Kullanıcının portföylerinin toplam değeri, dönem getirisi, değer geçmişi grafiği ve öne
çıkan pozisyonları.

**Layout şeması:**

```
┌──────────────────────────────────────────────────────────────┐
│ Header · piyasa durumu şeridi                                 │
├──────────────────────────────────────────────────────────────┤
│  PORTFÖY SEÇİMİ (list_portfolios() → DataTable, enter ile seç)│
│  ÖZET: Toplam Değer: 123.456,78 TL   Dönem Getirisi: +4,2%  │
├──────────────────────────────────────────────────────────────┤
│  GRAFİK (history → CChartLine/CChartCandle; 1/3/6/y dönem)   │
├──────────────────────────────────────────────────────────────┤
│  ÖNE ÇIKANLAR (performers top 5: Ticker, Getiri)             │
├──────────────────────────────────────────────────────────────┤
│ Footer: [1|3|6|y] dönem  [esc] geri  [r] yenile               │
└──────────────────────────────────────────────────────────────┘
```

**Veri sözleşmesi (P7):**

| Bileşen | Resource metodu | Auth | Not |
|---|---|---|---|
| Portföy listesi | `portfolio.list_portfolios()` | JWT | Tek portföyse otomatik seçilir |
| Özet + pozisyonlar | `portfolio.snapshot(id)` | JWT | Toplam değer / dönem getirisi (TR format) |
| Grafik | `portfolio.history(id, period)` | JWT | OHLC varsa birebir; yoksa **P2 sentez** (aynı adapter kuralı) |
| Öne çıkanlar | `portfolio.performers(id, top_n=5)` | JWT | Top 5 pozisyon |

- `diversification` / `risk` / `benchmark` v2 portföy ekranında **yoktur** (ikincil — P7 kararı).
- **Auth yok:** `Oturum bulunamadı — 'fl auth login' ile giriş yapın` (watchlist ile aynı desen).
  Boş portföy listesi: `Portföyünüz yok — CLI'dan oluşturun: fl portfolio create 'Benim Portföyüm' 100000`.
- **Tuş:** `4` (global `KEY_PORTFOLIO`; `1`/`2`/`4` arası serbest geçiş — push değil switch).
- **Veri akışı:** `app.poll_now` → `fetch_portfolio(screen.portfolio_id)` → mesaj → render.
  `_poll` ve `_post_failure`'da `PortfolioScreen` dalı; aynı polling altyapısı (DataService) —
  yeni mimari gerekmez (T-E1 notu).

---

## 3. Klavye ve Gezinme

### 3.1 Tuş haritası

| Tuş | Eylem | Kapsam |
|---|---|---|
| `q` / `ctrl+q` | Uygulamadan çık (`action_quit`) | Global |
| `1` | Pano ekranına geç (`switch_screen("dashboard")`) | Global |
| `2` | Watchlist ekranına geç (`switch_screen("watchlist")`) | Global |
| `4` | Portföy ekranına geç (v2, Faz E) | Global |
| `enter` | Seçili satırın detayını aç (`DetailScreen` push) | Pano, Watchlist |
| `esc` | Detaydan geri dön (`pop_screen`) | Detay |
| `j` / `down` | Satır aşağı (DataTable cursor) | Pano, Watchlist |
| `k` / `up` | Satır yukarı | Pano, Watchlist |
| `g` / `l` | Günün hareketleri: Gainers ↔ Losers sekmesi | Pano |
| `tab` | Gainers ↔ Losers sekmesi (alternatif) | Pano |
| `f` | Seçili ticker'ı favorilere ekle/çıkar (toggle, JWT) | Pano, Watchlist, Detay |
| `r` | Manuel yenile (tüm worker'ları şimdi tetikle) | Global |
| `1` / `3` / `6` / `y` | Detay grafik period'u: 1mo / 3mo / 6mo / 1y | Detay |
| `c` | Grafik tipi: çizgi ↔ mum (toggle, P6) | Detay |
| `h` | Yardım paneli (ModalScreen: tuş haritası + sürüm) | Global |

> Tuş sabitleri `tui/keys.py` içinde tek kaynaktan tanımlıdır (`KEY_*`, `PERIODS`,
> `PERIOD_LABELS`, `CHART_LABELS`, `DEFAULT_PERIOD`, `DEFAULT_CHART`).
>
> **Not:** `1`/`3`/`6`/`y` çakışması yok — `1` global "Pano" iken detay ekranında "1mo" olarak
> yorumlanır. Textual'da binding çakışması ekran bazlıdır: Detay ekranı kendi `BINDINGS`'ini
> tanımlar (screens/detail.py); `1` Detay'dayken period anlamına gelir. Footer aktif ekranın
> binding'lerini otomatik listeler.

### 3.2 Footer ipuçları

`Footer` widget'ı, **o an aktif ekranın** `BINDINGS` listesinden kısa ipuçlarını otomatik çizer
(`q Çıkış`, `1 Pano`, `2 İzleme`, `r Yenile`, `h Yardım` …). Uygulama seviyesi bindings + ekran
seviyesi bindings birleşir; Detay ekranında Footer'da `esc Geri`, `c Mum/Çizgi`, `3 Dönem: 3mo`
gibi ekran-bazlı tuşlar görünür. Açıklamalar Türkçe (cli-design.md dil kuralı: komut adları
İngilizce, **metinler Türkçe**).

### 3.3 Yardım paneli (`h`)

`HelpModal` (app.py içinde `ModalScreen` tabanlı): tuş haritası tablosu + SDK sürümü
(`florence.__version__`) + API adresi (`config.get_base_url()`). `esc`/`q` ile kapanır. Veri isteği
yapmaz (offline).

---

## 4. Polling ve Durum Yönetimi

### 4.1 Genel model: interval → worker

```
App.on_mount()
  └─ set_interval(tui_refresh_seconds, self._on_poll_tick)   # App metodu; callback async olabilir
        └─ self.run_worker(self._poll(), group="poll")        # asyncio task — event loop'u BLOKLAMAZ
              └─ DataService._refresh_<ekran>()               # await client.market.current_price(...) vb.
                    └─ screen.post_message(DataUpdated(...))  # sonuç widget'lara mesajla döner
```

- **`set_interval`:** Textual'ın App metodu — event loop'ta zamanlayıcı kurar. TUI'nin tek
  zamanlayıcı kaynağıdır (WS yok, ayrı thread yok).
- **`run_worker(group="poll")`:** Her tick bir **Worker** başlatır. `group="poll"` + `exclusive`
  davranışı: önceki worker hâlâ çalışıyorsa (yavaş ağ) yeni tick **atlanır** ("poll overlap"
  koruması). Worker'lar asyncio task'leridir; `await`'ler event loop'u bloklamaz.
- **Senkron client YASAK:** `FlorenceClient` (senkron) TUI içinde kullanılmaz — `time.sleep`
  içeren retry'ları ve bloklayan `request()`'i event loop'u dondurur. Yalnızca
  `AsyncFlorenceClient` kullanılır.
- **Client yaşam döngüsü:** `AsyncFlorenceClient` **bir kez**, `App.on_mount`'ta oluşturulur
  (default token store ile); `App.on_unmount`'ta `await client.close()`. Her tick'te client
  yaratılmaz (bağlantı havuzu + auth state korunur).
- **Worker sonucu widget'a nasıl ulaşır:** Worker doğrudan widget'a dokunmaz; `post_message` ile
  ekranın message handler'ına teslim eder (Textual deseni). Böylece veri geldiğinde UI güncellenir;
  hata durumunda hata mesajı taşınır.

### 4.2 Ekran bazlı poll planı (tek tick = 45s varsayılan)

| Veri | İstek/tick | Aralık | Not |
|---|---|---|---|
| `market_status` | 1 | 60s (backend cache'e uyum) | Ayrı interval; header şeridi |
| Pano: stats_top + gainers + losers | 3 | `tui_refresh_seconds` | gainers/losers cache'te tek sort çağrısı ailesi |
| Pano: gold + currency | 2 | `tui_refresh_seconds` | |
| Watchlist: favorites | 1 | `tui_refresh_seconds` | Yalnızca watchlist aktifken |
| Watchlist: N × (current_price + history) | 2N | `tui_refresh_seconds` | history 10dk cache (tekrar istek yok) |
| Detay: current_price | 1 | `tui_refresh_seconds` | Yalnızca detay aktifken |
| Detay: history (seçili period) | 1 | 5dk cache | Period değişince anında |
| Detay: news | 1 | **90s** (2. tick) | 10/dk rate limit güvenliği |
| Portföy: list + snapshot + history + performers (v2) | 1 + 1 + 1 + 1 | `tui_refresh_seconds` | Yalnızca portföy aktifken |

**Aktif ekran kuralı:** Arka plandaki ekranın verisi çekilmez (pano arka plandayken watchlist
istekleri yapılmaz — Faz D keşif #8 testiyle sabitlenmiştir). Tasarruf + rate limit bütçesi. Ekrana
dönüldüğünde (switch) veri hemen tazelenir (anında tick).

### 4.3 Manuel yenileme (`r`)

`r` → `_on_poll_tick()` doğrudan çağrılır (interval'i beklemez). Aynı `exclusive` worker kuralı
geçerlidir: devam eden bir poll varsa yenileme yeni istek başlatmaz, mevcut sonucu bekler —
"debounce" doğal olarak sağlanır. `r` spam'i 429 riski yaratmaz (5s içinde en fazla 1 manuel tick).

### 4.4 Rate limit bilinci (429)

- Client zaten 429'da `Retry-After`'a saygılı retry yapar (client.py, `max_retries=2`). TUI
  seviyesinde ek koruma (`DataService.register_rate_limit` / `register_success`):
- **Interval uzatma:** `RateLimitError` alındığında poll intervali geçici olarak
  `max(current_interval * 2, retry_after + 10s)` yapılır (üst sınır 300s). Banner gösterilir:
  `Rate limit — {retry_after}s sonra tekrar`. Sonraki 3 başarılı tick'ten sonra interval
  config'teki değere döner.
- **Manuel yenileme kilidi:** interval uzamışken `r` notif ile bilgi verir: `Rate limit beklemede — {k}s`.
- **News özel kuralı:** haber isteği başarısız olursa bir sonraki haber denemesi 90s değil 5 dk
  sonraya ertelenir.

### 4.5 Cache (`DataService` içi, thread-safe olması gerekmez — tek event loop)

`DEFAULT_TTL` (data.py) — `dict[key] -> (expires_at, value)`; `ttl_overrides` ile testlerde
küçültülebilir:

| Veri | TTL | Gerekçe |
|---|---|---|
| `market_status` | 60s | Backend zaten 60s cache'li |
| `current_price` (ticker başına) | 60s | Watchlist + detay aynı ticker'ı paylaşır |
| `price_history` (ticker+period başına) | 10dk | Gün içi değişir ama dakikada bir çekmek anlamsız |
| `company_info` | 5dk | Nadiren değişir |
| `gold_prices` / `currency` | 60s | |
| `news` | 5dk | Rate limit koruması + nadiren değişir |
| `favorites` | 60s | |
| `portfolio_*` (v2) | liste/snapshot 60s · history 10dk | Portföy ekranı (T-E1) |

Cache, `data.py` içinde basit yapıdır; event loop tek thread'li olduğundan kilit gerekmez. Aynı tick
içinde aynı anahtar ikinci kez istenirse cache'ten döner — ağ isteği yok.

### 4.6 Piyasa kapalıyken davranış

`market_status.open == False` ise fiyat verileri değişmeyeceği için **fiyat poll'ları otomatik
yavaşlar**: interval geçici olarak config `tui_market_closed_refresh`'e çıkar (default 300s).
Header'daki `KAPALI · 10:00'da açılacak` göstergesi yine güncellenir (K4 kararı).

---

## 5. Grafik: ccharts (v2 revizyonu)

### 5.1 Mimari: adapter katmanı (Y2/K2)

v1 tasarımındaki Textual `Sparkline` + `widgets/sparkline.py` yaklaşımı, Faz A'da **ccharts'a
taşınmıştır** (K2 revizyonu):

```
price_history satırları ([{ts, open, high, low, close}, ...])
        │
        ▼
tui/charts.py  (ADAPTER — ccharts import'u YALNIZCA BURADA, Y2)
  ohlc_rows(rows, fill_hl=True) → ccharts JSON stringi (P2 sentez kuralı)
  render_line / render_candle → Chart(payload).line()/.candle() → ANSI string
  single_row → DataTable hücresi için tek satır (mini grafik, P5)
  theme_ansi → Textual tema değişkenini 24-bit ANSI'e çevirir (P4)
  period_colors → TR BIST: dönem getirisi rise/fall renk çifti
  normalize / downsample / spark_text / SPARK_CHARS → eski sparkline fallback (Y3)
        │
        ▼
tui/widgets/charts.py  (CChartLine / CChartCandle — Static alt sınıfı)
  update_data(rows) → adapter → Text.from_ansi (renk korunur)
        │
        ▼
screens/...  (dashboard/watchlist/detail/portföy — ccharts'ı DOĞRUDAN import etmez)
```

**Karar özeti:**

| Karar | Sonuç |
|---|---|
| **P1** | ccharts zorunlu ana bağımlılık: `ccharts>=0.2.0` (PyPI). Path dep yalnızca yayın öncesi geçiciydi, Faz F'de pin'e dönüldü. |
| **Y2 / K2** | Ekranlar ccharts'ı doğrudan import etmez; `tui/charts.py` adapter'ı tek geçiş noktasıdır. Render stratejisi değişirse ekranlar etkilenmez. |
| **P2** | `high`/`low` openapi şemasında boş olabilir → `ohlc_rows(fill_hl=True)`: `high=max(open, close)`, `low=min(open, close)` — "yaklaşık mum", docstring'de nota bağlı. Gerçek high/low varsa birebir korunur. |
| **P3** | ccharts render'ı saf C (~µs–ms) — adapter fonksiyonları senkron çağrılır; `asyncio.to_thread` GEREKMEZ (ölçüm testi: 500 kayıt + 60×14 grafik 50ms altında). |
| **P4** | Renkler Textual `theme_variables`'tan (`$success`/`$error` hex) `theme_ansi` ile 24-bit ANSI'ye çevrilir — dark/light temada otomatik uyum. |
| **P5** | ccharts `height=1` mini hücrede kısıtlıysa `single_row()` fallback'i yalnızca mini hücrede devreye girer; büyük grafikler etkilenmez. |
| **P6** | `c` tuşu line ↔ candle toggle; başlangıç tipi config `tui_default_chart`. Period ayrı eksen (`1/3/6/y`). |

### 5.2 Veri normalizasyonu ve OHLC sözleşmesi

- Girdi: `price_history` yanıtı `[{ts, open, close, volume}]` (high/low backend'de opsiyonel —
  P2). Eksik `close` (None) olan kayıtlar seriden çıkarılır (backend ara tatil günü boş bırakır).
- ccharts **null değer kabul etmez** (blok karakter kaydırma): sayı yoksa ya sentezlenir
  (`fill_hl`) ya da alan yazılmaz — `null` asla üretilmez (adapter docstring pitfall'ı).
- Normalizasyon (`normalize`): `v' = (v - min) / (max - min)` → `[0, 1]`. `max == min` (düz seri)
  ise tüm noktalar 0.5'e sabitlenir — bölünme hatası yok.
- Sparkline/tek satır veri boyutu terminal genişliğine göre **örneklenir** (`downsample`): her
  sütuna 1 nokta; watchlist mini grafikte son 12 sütuna örneklenmiş tüm seri (eğilim doğru görünür).
- Grafik ekseni: solda min / son / max değerleri (TR format), altta dönem başı–sonu tarihleri
  (`show_prices`, `show_times`).

### 5.3 Renk kuralları (TR BIST konvansiyonu)

- **Yükseliş = yeşil** (`$success`), **düşüş = kırmızı** (`$error`), **değişim yok = gri**.
  (Batı borsalarındaki kırmızı-yükseliş tersine, Türkiye'de yeşil yükseliştir — kullanıcı kararı.)
- Watchlist grafik rengi **dönem getirisine** bağlanır (`period_return(first, last)` →
  `period_colors`) — günlük Δ%'den bağımsız, çünkü grafik 1 aylık eğilimi gösterir. ccharts tek
  renk modu (`single_color=True`) ile çizilir.
- Renkler Textual CSS tema değişkenlerinden gelir (P4) — dark/light temada otomatik uyum.

### 5.4 Period seçimi (detay)

`PERIODS` (keys.py): `1mo`/`3mo`/`6mo`/`1y` → `price_history(ticker, period=X, interval="1d")`.

| Tuş | Period | `interval` | Veri noktası (yaklaşık, iş günü) |
|---|---|---|---|
| `1` | `1mo` | `1d` | ~22 |
| `3` | `3mo` | `1d` | ~65 |
| `6` | `6mo` | `1d` | ~130 |
| `y` | `1y` | `1d` | ~260 |

Backend `interval` kısıtı (`5m..3mo` aralık) `1d` ile her period'da geçerlidir; gün içi
(5m/30m/1h) interval'ler v2 kapsamı dışıdır. Portföy grafiğinde aynı period tusları kullanılır
(Faz E).

---

## 6. Config ve Auth

### 6.1 Config: `~/.config/florence/config.toml` — TUI anahtarları

`fl config set/show` allowlist'i (config_cli.py) TUI anahtarlarını içerir (Faz D genişletmesi):

| Anahtar | Tip | Varsayılan | Açıklama | Kabul aralığı |
|---|---|---|---|---|
| `tui_refresh_seconds` | int | `45` | Ana poll aralığı (saniye) | 10–600 (dışı clamp) |
| `tui_default_period` | str | `"1mo"` | Detay grafiği başlangıç period'u | `1mo`/`3mo`/`6mo`/`1y` |
| `tui_default_chart` | str | `"line"` | Detay grafiği başlangıç tipi (P6) | `line`/`candle` |
| `tui_market_closed_refresh` | int | `300` | Piyasa kapalıyken fiyat poll aralığı (saniye) | 60–3600 (dışı clamp) |
| `tui_watchlist_source` | str | `"favorites"` | Watchlist kaynağı (P8: yalnızca `favorites`; `local` geleceğe genişleme notu) | yalnızca `"favorites"` |
| `tui_top_limit` | int | `10` | Pano öne çıkanlar limiti | 1–50 (dışı clamp) |
| `tui_summary_limit` | int | `10` | Pano günün hareketleri limiti | 1–50 (dışı clamp) |

- Örnek:
  ```toml
  api_url = "https://api.florencex.com.tr"
  default_output = "table"
  tui_refresh_seconds = 45
  tui_default_period = "3mo"
  tui_default_chart = "candle"
  tui_market_closed_refresh = 300
  tui_watchlist_source = "favorites"
  tui_top_limit = 10
  tui_summary_limit = 10
  ```
- **Öncelik:** env (`FLORENCE_API_URL`, `FLORENCE_TOKEN`) > config > SDK default (cli-design.md
  kuralıyla aynı). TUI anahtarları env override gerektirmez (yok); yalnızca config.
- TUI config'i **kendisi yazmaz** (salt-okunur) — değişiklikler `fl config set tui_refresh_seconds 60`
  ile yapılır (`fl config set` allowlist'e tüm `tui_*` anahtarlarını kabul eder; `fl config show`
  da bunları gösterir). Config yoksa veya anahtar yoksa varsayılanlar kullanılır.
- Config okuma: `tui/app.py` `on_mount`'ta `cli.config_cli` üzerinden tek seferde okur; her anahtar
  kendi doğrulama/clamp kuralına tabidir.

### 6.2 Kalıcı auth yeniden kullanımı

- TUI, `AsyncFlorenceClient()` **default token store**'u ile oluşturulur — yani `AuthManager` →
  `KeyringTokenStore(keyring_service="florence-sdk")`. CLI'nin `fl auth login` ile yazdığı
  access/refresh token'lar keyring'den otomatik okunur; `FLORENCE_TOKEN` env override'ı aynen
  çalışır (auth.py env önceliği).
- **Headless fallback:** keyring'in çalışmadığı ortamda `FileTokenStore` (Fernet şifreli
  `~/.config/florence/tokens.json`) devreye girer. TUI hiçbir store seçmez — **varsayılanı
  kullanır**; "CLI'da girilen oturum TUI'de de geçerli" garantisi otomatiktir.
- **401 akışı:** `AsyncFlorenceClient` 401'de otomatik single-flight `refresh_async()` dener;
  TUI'nin ekstra işi yoktur. Refresh de başarısızsa `AuthError` → auth-gerektiren ekranlarda
  yönlendirme mesajı.
- TUI **içinde login yapılmaz** (şifre prompt'u yok) — güvenlik kuralı: token'lar yalnızca CLI
  auth akışıyla yazılır.

### 6.3 Auth durumu ekranlara nasıl yansır

| Oturum | Pano | Watchlist | Portföy (v2) | Detay (news) | Detay (fiyat/grafik) |
|---|---|---|---|---|---|
| Yok | ✅ çalışır (public) | ⚠️ uyarı: `Oturum bulunamadı — 'fl auth login' ile giriş yapın` | ⚠️ aynı uyarı | Bölüm gizli: `Haberler için giriş yapın` | ✅ çalışır (public) |
| Var (user/bot) | ✅ | ✅ favoriler | ✅ | ✅ | ✅ |
| Süresi doldu (refresh başarısız) | ✅ | ⚠️ `Oturum süresi doldu — tekrar giriş yapın (fl auth login)` | ⚠️ aynı | gizli | ✅ |

- `f` (favori toggle) tuşu auth'suz ortamda `notify("Favoriler için giriş yapın")` gösterir, istek
  atmaz.
- Bot oturumları (bot login ile girilmiş) TUI'de normal oturum gibi çalışır — fark yok.

---

## 7. Dosya Düzeni

### 7.1 `src/florence/tui/` paketi (gerçek yapı)

```
src/florence/tui/
├── __init__.py            # public API: main(), FlorenceTUIApp (testler için)
├── app.py                 # FlorenceTUIApp: BINDINGS, SCREENS, client lifecycle,
│                          #   polling yöneticisi (set_interval + worker), hata banner'ları,
│                          #   HelpModal, açılış banner'ı tetikleme
├── banner.py              # Statik FLORENCE art-banner + gradyan yardımcısı (Faz D keşif #3)
├── charts.py              # ccharts ADAPTER katmanı — ccharts import'u YALNIZCA burada (Y2):
│                          #   ohlc_rows, render_line, render_candle, single_row, theme_ansi,
│                          #   period_colors, normalize, downsample, spark_text, SPARK_CHARS
├── data.py                # DataService: DEFAULT_TTL cache + async fetch'ler (poll orkestrasyonu);
│                          #   format yardımcıları (tr_number, tr_delta, delta_style,
│                          #   status_bar_text, market_status_text, error_message, gold_summary)
├── keys.py                # Tuş/aksiyon sabitleri: KEY_*, PERIODS, PERIOD_LABELS,
│                          #   CHART_LABELS, DEFAULT_PERIOD, DEFAULT_CHART
├── screens/
│   ├── __init__.py
│   ├── dashboard.py       # DashboardScreen (Pano)
│   ├── watchlist.py       # WatchlistScreen (favoriler + önizleme paneli)
│   ├── detail.py          # DetailScreen (ticker detay + grafik + haberler)
│   └── portfolio.py       # PortfolioScreen (v2, Faz E — P7)
└── widgets/
    ├── __init__.py
    ├── charts.py          # ccharts tabanlı Textual widget'ları: CChartLine / CChartCandle
    │                      #   (Static alt sınıfı; update_data(rows) → adapter → Text.from_ansi)
    └── sparkline.py       # Eski Textual Sparkline sarmalayıcısı: Y3 sonrası yalnızca fallback
                            #   (saf yardımcılar charts.py'den re-export edilir)
```

**Sorumluluk ayrımı:**

- `app.py` — uygulama iskeleti: client oluşturma/kapama, global BINDINGS, ekran kaydı,
  `set_interval` kurulumu, tick → `run_worker` (exclusive), banner'lar, HelpModal.
- `data.py` — **tek veri erişim noktası**: cache'ler, rate-limit interval yönetimi, worker'ların
  çağırdığı async metodlar, TR format yardımcıları. Ekranlar `DataService`'i çağırır;
  `AsyncFlorenceClient`'a doğrudan dokunmaz (test edilebilirlik: service inject edilir, bölüm 8).
- `charts.py` — ccharts adapter'ı: veri dönüşümü + ANSI render. Ekranlar/widget'lar buradan geçer.
- `screens/*` — yalnızca sunum: widget düzeni, tuş eylemleri, `post_message` handler'ları.
  Veri/görsel mantığı içermez.
- `widgets/*` — yeniden kullanılabilir görsel bileşenler (grafik widget'ları + eski sparkline).
- `keys.py` — sabitler; ekranlar arası tutarlılık tek yerden.

### 7.2 Bağımlılık

`pyproject.toml` `[project] dependencies` (ana bağımlılıklar — extra yok, P1):

```toml
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.7",
    "keyring>=25",
    "mcp>=1.2",
    "fastmcp>=2.0",
    "typer>=0.12",
    "rich>=13.7",
    "cryptography>=42",
    "textual>=0.60",    # TUI — CLI ile birlikte kurulur (kullanıcı kararı)
    "ccharts>=0.2.0",   # TUI grafikleri — zorunlu (P1)
]
```

`textual>=0.60` alt sınırı; `ccharts>=0.2.0` PyPI yayını Faz F'de pin'e dönüştürülmüştür (0.2.0
öncesi geliştirme path dep ile yapıldı — geçici, artık kaldırıldı). Ruff (line-length 120) kuralları
uygulanır — `tui/` paketi de aynı lint kapsamında.

### 7.3 `fl tui` CLI bağlantısı

- `fl tui` typer komutu `src/florence/cli/commands_tui.py` içinde tanımlıdır: `tui_app` isimsiz
  `typer.Typer` — `src/florence/cli/app.py` `app.add_typer(commands_tui.tui_app)` ile üst seviyeye
  eklenir, böylece komut `fl tui` olarak görünür (`commands_*.py` deseni).
- Komut gövdesi tek iş yapar: `from florence.tui.app import main; main()` — typer komutu yalnızca
  **giriş noktasıdır**, TUI mantığı `florence/tui/` içindedir (geç import: dairesel bağımlılık yok).
- `--json` bayrağı `fl tui` için **yoktur** (TUI tam ekran interaktif; cli-design.md "gereksiz
  bayrak yok" kuralı). Argüman da yoktur (K5).
- Entry point'ler: `fl` → `florence.cli.app:main`; `florence-mcp` ayrıdır, dokunulmaz.
- `fl config set/show` allowlist'ine tüm `tui_*` anahtarları işlenmiştir (config_cli.py — Faz D).

### 7.4 Test dosyaları

```
tests/tui/
├── conftest.py            # fake_data fixture'ları (mock transport yanıtları), make_app helper
├── test_app.py            # run_test: klavye akışları, ekran geçişleri, polling tick, banner
├── test_banner.py         # açılış banner'ı render'ı
├── test_chart_widgets.py  # CChartLine/CChartCandle widget davranışı (gerçek ccharts ile)
├── test_charts.py         # adapter birim testleri: ohlc_rows, render_*, single_row, theme_ansi,
│                          #   period_colors, normalize/downsample (gerçek ccharts ile)
├── test_dashboard.py      # DashboardScreen mock veriyle montaj + boş/hata durumları
├── test_data.py           # DataService birim: cache TTL, 429 interval uzatma, dönüşümler
├── test_detail.py         # DetailScreen: grafik, period/tip değişimi, haberler
├── test_sparkline.py      # fallback sparkline saf fonksiyonları
├── test_watchlist.py      # WatchlistScreen: listeleme, önizleme, boş/auth durumları
└── test_portfolio.py      # PortfolioScreen (v2, Faz E — P7)
```

ccharts zorunlu dep olduğundan chart testleri **gerçek ccharts ile** koşar (ImportError = fail
loud, sessiz fallback yok). Ekran render'ı kırılgan string eşleşmelerinden kaçınır: widget/chart
çıktısı ya karakter varlığı (`▁`, `│`, `\x1b[`) ya da ccharts'ın kendi çıktı formatından alınan
sabitlenmiş küçük beklentilerle test edilir. ccharts sınır davranışları (height=1, width≤0,
CC_MAX_CELLS) tek noktada test edilir (Faz A/B) — ccharts kendi testinde de vardır, tekrar yok.

---

## 8. Test Stratejisi (OFFLINE)

**İlke:** Tüm TUI testleri **canlı backend gerektirmez** — Textual'ın yerleşik headless test
API'si + httpx `MockTransport` ile tamamen offline. SDK'nın genel test ilkesiyle birebir
(plan: "tüm akışlar mock").

### 8.1 Altyapı: `App.run_test()` (Textual'ın kendi test API'si)

```python
async def test_klavye_ekran_gecisi():
    async with app.run_test(size=(100, 30)) as pilot:   # headless; boyut verilebilir
        await pilot.press("2")                          # watchlist'e geç
        assert app.screen.id == "watchlist"
        await pilot.press("1")
        assert app.screen.id == "dashboard"
        await pilot.press("q")                          # çıkış
```

- `run_test` ekranı gerçek terminal olmadan kurar; `Pilot` API'si (`press`, `pause`, `click`,
  `wait_for_screen`, `wait_for_worker`) klavye/etkileşim simülasyonu sağlar.
- **Network yok:** `DataService`'e testte `AsyncFlorenceClient(transport=httpx.MockTransport(handler))`
  inject edilir; handler, path'e göre test verisi döndürür. Hiçbir istek gerçek ağa çıkmaz.
- **App fabrikası:** `tests/tui/conftest.py` → `make_app(handler)` helper'ı: mock transport'lu
  client + `DataService` kurar, `FlorenceTUIApp` döndürür. Tüm testler bunu kullanır.

### 8.2 Test senaryoları

| Alan | Test | Nasıl |
|---|---|---|
| **Ekran montajı** | Pano, watchlist, detay mock veriyle mount olur; hücreler dolu | `run_test` + `app.screen` üzerinde widget sorgusu |
| **Polling worker** | `set_interval` tick'i veriyi günceller; overlap'ta yeni tick atlanır | `pilot.pause()` + `wait_for_worker` |
| **Klavye** | `1/2` geçiş, `j/k` satır, `enter` detay açılışı, `esc` dönüş, `r` manuel yenile, `q` çıkış, `1/3/6/y` period değişimi, `c` tip değişimi | `pilot.press(...)` + sonrası durum assert |
| **Veri dönüşümü** | TR sayı formatı (313,40), Δ% rengi, economy string virgülünün dokunulmaması | `test_data.py` birim testleri (UI'sız) |
| **Chart adapter** | `ohlc_rows` (null üretmez), sentez (P2), render line/candle, `single_row`, `theme_ansi`, renkler | `test_charts.py` — gerçek ccharts ile |
| **Chart widget** | `update_data([])` → `Veri yok`; veri gelince ANSI render | `test_chart_widgets.py` |
| **Hata / 429** | MockTransport 429 + `Retry-After: 30` → banner görünür, interval uzar, sonraki tickler cache'ten | `test_data.py` + `test_app.py` |
| **Network hatası** | MockTransport `httpx.ConnectError` → `NetworkError` → banner + son veri korunur | aynı |
| **Piyasa kapalı** | `market_status` `open:false` → interval `tui_market_closed_refresh`'e çıkar; header `KAPALI` gösterir | `test_data.py` |
| **Boş durumlar** | `favorites()` boş → "Favoriniz yok"; `stats_top` boş → "Veri yok"; `price_history` boş → "Bu dönem için veri yok" | ekran testleri |
| **Auth yok** | store boş → watchlist/portföy uyarısı, pano çalışır, haberler gizli | `make_app` ile boş store |
| **Auth 401/refresh** | İlk istek 401 → client refresh isteği (mock) → yeniden deneme; refresh de 401 → oturum uyarısı | `test_app.py` |
| **Aktif ekran kuralı** | Arka plandaki ekranın verisi çekilmez (fetch dispatch yalnızca aktif ekranda) | Faz D keşif #8 testi |

### 8.3 Zaman yönetimi (testlerde hız)

- `run_test` gerçek zamanlı çalışır; uzun interval'leri testte beklemeyiz: `DataService`'in
  interval'i `make_app`'te kısa kurulur VEYA `_on_poll_tick()` doğrudan çağrılır; `pilot.pause(0.2)`
  ile tick geçişi beklenir; `wait_for_worker("poll")` ile iş bitimi beklenir.
- Cache TTL'leri testte parametre olarak küçültülür (`ttl_overrides` constructor parametresi) —
  10dk TTL'yi testte beklemeyiz.
- **Zaman-bağımlı testler dinamiktir:** conftest `_NEXT_OPEN_AT` bugüne göre +1 gün üretir —
  sabit tarih yok (CI'da gününe bağlı flake yok).

### 8.4 CI uyumu (P9)

- `tests/tui/` normal `pytest` kapsamındadır (CI'da otomatik koşar); ayrı marker gerektirmez.
- ccharts zorunlu dep olduğundan import her zaman çalışır (sessiz fallback yok).
- `asyncio` testleri `asyncio.run` sarmalayıcısıyla çalışır; yeni dev bağımlılık eklenmez.
- Tüm TUI testleri `FLORENCE_LIVE=1` gerektirmez; canlı smoke (opsiyonel): `fl tui`'yi gerçek
  oturumla elle başlatmak — manuel doğrulama, otomatik değil.
- CI: `.github/workflows/ci.yml` — `ruff check` + `pytest`, 3.12 + 3.13 matrix, uv cache
  (süre bütçesi ~89s; Faz F). Zaman-bağımlı testler dinamik olduğundan matrix'te flake riski yok.

---

## 9. Karar Noktaları — Sonuçlar (P1–P9)

| Karar | Soru | Sonuç |
|---|---|---|
| **P1** | ccharts nasıl paketlenir? | **Zorunlu ana bağımlılık** `ccharts>=0.2.0` (PyPI, Faz F pin'i). Grafikler her kurulumda çalışır; extra yok; sessiz fallback yok. |
| **P2** | `high`/`low` kaynağı? | Openapi şeması boş olabilir → `ohlc_rows(fill_hl=True)` sentezi: `high=max(open, close)`, `low=min(open, close)` — "yaklaşık mum", docstring notu. Gerçek değerler varsa birebir. |
| **P3** | Adapter senkron mu, `to_thread` mu? | ccharts render'ı saf C (~µs–ms) → **senkron** çağrı; `asyncio.to_thread` gerekmez (ölçüm testiyle doğrulandı). |
| **P4** | Renkler temaya nasıl uyar? | `theme_ansi`: Textual `theme_variables` (`$success`/`$error` hex) → 24-bit ANSI; dark/light otomatik uyum. |
| **P5** | ccharts height=1 mini hücrede bozulursa? | `single_row()` fallback yalnızca mini hücrede devreye girer; büyük grafikler etkilenmez. |
| **P6** | Detay grafik period ↔ tip çaprazı? | `c` tuşuyla line/candle toggle; period ayrı eksen (`1/3/6/y`); config `tui_default_chart`. İki bağımsız, tahmin edilebilir eksen. |
| **P7** | Portföy ekranı veri sözleşmesi? | `list_portfolios()` → seçim → `snapshot(id)` + `history(id, period)` + `performers(id, top_n=5)`; grafik = history'den ccharts line/candle; üstte özet. `diversification`/`risk`/`benchmark` v2'de YOK. Alan adları canlı şemadan (uydurma yok). |
| **P8** | `tui_watchlist_source = "local"` eklensin mi? | **HAYIR (v2'de değil)** — favorites tek kaynak; anahtar config'te tanımlı ama yalnızca `"favorites"` kabul edilir (geleceğe genişleme notu). |
| **P9** | TUI testleri CI'da nasıl koşar? | **GitHub Actions** (Faz F): `ruff check` + `pytest`, 3.12 + 3.13 matrix, ubuntu-latest, uv cache; ~89s bütçe. TUI testleri suite'in parçasıdır; `-m "not live"` kuralı korunur. Ayrıca opsiyonel `publish.yml` (tag → `uv publish`) workflow dosyası yazıldı, tag/deploy zinciri SDK'da yoktur. |

**Varsayılanla ilerleyen kararlar (P3/P4/P5):** önerilen varsayılanlar uygulandı.

---

## Ek A — Veri sözleşmesi özeti (test şemalarından birebir)

| Uç | Şekil |
|---|---|
| `market_status()` | `{"open": bool, "next_open_at": str(ISO), "holiday": bool}` |
| `stats_top(limit)` | `[{"ticker": str, "count": int}]` |
| `current_price(ticker)` | `{"ticker": str, "price": float, "change_pct": float, "market_status": str}` |
| `price_history(ticker, period, interval)` | `[{"ts": str(ISO), "open": float, "close": float, "volume": int}]` (high/low opsiyonel — P2) |
| `company_info(ticker)` | `{"ticker": str, "longName": str, ...}` (extra alanlara toleranslı) |
| `news(ticker, amount)` | `[{"title": str, "url": str}]` — JWT + news feature, 10/dk |
| `gold_prices()` | `[{"Type": str, "Buying": "40,25", "Selling": "40,75"}]` — TR virgüllü STRING |
| `currency(symbols)` | `{"USD": {"buying": "42,10"}}` — TR virgüllü STRING |
| `favorites()` | `["THYAO", "ASELS"]` — JWT |
| `companies_summary(limit, sort, ...)` | Fiyat/Δ% alanlı özet tablosu; `sort`: popular\|alphabetical\|gainers\|losers\|price_high\|price_low\|volume\|market_cap |
| `list_portfolios()` / `snapshot(id)` / `history(id, period)` / `performers(id, top_n)` (v2) | Portföy veri sözleşmesi — canlı şemadan doğrulanır, alan adları birebir (P7) |

**Pitfall'lar (implementasyonda hatırlanmalı):**
- `economy` değerleri string + TR virgül — sayısal işlem öncesi `replace(",", ".")`; gösterimde olduğu gibi.
- `news` 10/dk + JWT — detay ekranında 90s poll + auth yoksa gizle.
- `market_status` backend 60s cache — daha sık çekme anlamsız.
- ccharts null kabul etmez — adapter asla `null` üretmez (sent ez veya alanı at).
- Piyasa kapalıyken `add_transaction` 400 döner — portföy ekranı işlem yapmaz (yalnızca görüntüleme).

---

## Ek B — Koordinasyon notları (eşzamanlı subagent'lar)

- **CLI:** `fl tui` komutu + `fl config set/show`'a `tui_*` anahtarları entegre — commands_tui.py,
  config_cli.py (Faz D keşif #5/#6).
- **MCP:** TUI, MCP ile doğrudan ilişki kurmaz (MCP = LLM uygulamalarına tool fişi; TUI = insan
  arayüzü). `florence_mcp` paketine dokunulmaz.
- **Ortak sözleşme:** TUI yalnızca SDK resource'larını ve `AsyncFlorenceClient`'ı kullanır —
  CLI/MCP'den hiçbir kod paylaşmaz.
- **Faz E (portföy):** `PortfolioScreen` + `4` tuşu + `data.py` portföy fetch'leri ayrı worktree'de
  tamamlanır (T-E1..T-E4); bu rapor §2.4/§4.2'deki sözleşme o implementasyonun şartnamesidir.
- **Faz F:** sürüm 0.2.0 bump + ccharts PyPI pin'i + CI (P9) + README/CHANGELOG — bu raporla
  eşzamanlı.