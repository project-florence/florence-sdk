# TUI Tasarım Raporu — `fl tui` (Faz 10)

> **Durum:** TASARIM — implementasyon yok. Bu rapor `src/florence/tui/` implementasyonunun ve
> `fl tui` komutunun teknik şartnamesidir.
> **Tarih:** 2026-08-14 · **Faz:** 10 (plan: `.hermes/plans/2026-08-14_144500-florence-sdk.md`)
> **Teknoloji:** Textual (Rich tabanlı, klavye dostu) · **Canlılık:** WebSocket YOK — 30–60s polling
> **Kapsam v1:** Pano + Watchlist + Ticker detay/grafik · **v2 (not):** Portföy ekranı

---

## 1. Giriş

**TUI (Text User Interface)** — terminalde çalışan tam ekran, interaktif bir kullanıcı arayüzüdür.
CLI'ın "bir komut çalıştır, çıktıyı gör" modelinden farklı olarak TUI, ekranı **kalıcı olarak**
kaplar, klavye ile gezilir ve veri **periyodik olarak kendini yeniler**. `fl tui` kullanıcıya,
tarayıcı açmadan veya komutları tekrar tekrar yazmadan BIST'i izleme imkânı verir: piyasa durumu,
öne çıkan hisseler, altın/döviz, favorilerinin canlı fiyatları ve ticker grafikleri tek ekranda.

### 1.1 Neden Textual?

| Kriter | Textual | Alternatifler (blessed, urwid, curses) |
|---|---|---|
| **Klavye dostu** | Yerleşik `BINDINGS` sistemi, `Footer` otomatik ipuçları | Manuel key handling |
| **Widget seti** | `DataTable` (sıralı tablo), `Sparkline`, `Header`, `Footer`, `Static`, `ModalScreen` hazır | Çoğu elle çizilir |
| **Asenkron** | Kendi asyncio event loop'u + `set_interval` + `Worker` deseni | Senkron, bloklayıcı |
| **Test edilebilirlik** | Yerleşik headless test API (`App.run_test()` + `Pilot`) | Yok / zayıf |
| **Ekran yönetimi** | `Screen` sınıfları, `push`/`switch`, screen stack | Yok |
| **Stil** | CSS benzeri Textual CSS, otomatik renk teması (dark/light) | Ham renk kodları |

Textual, Rich üzerine kuruludur; SDK'nın CLI katmanı da Rich kullanacağı için (cli-design.md) ekosistem
aynıdır. WebSocket gerektirmez — veri kaynağı zaten 15 dk gecikmeli olduğundan (kullanıcı kararı,
2026-08-14) 30–60s polling yeterlidir ve dakikalık rate limit bütçesi rahatça karşılanır.

### 1.2 Çağrı: `fl tui`

- Komut: **`fl tui`** (tek komut, argümansız). `fl` alias'ı kullanıcı onayıyla kesinleşti
  (gh/cargo/npm geleneği).
- **CLI bağlantısı:** `src/florence/cli/` içinde typer komutu olarak eklenir
  (`commands_tui.py` veya `app.py`'ye doğrudan `@app.command("tui")` — bkz. bölüm 7.3).
  CLI `<grup> <komut>` desenine uyar: `tui` tek seviyeli, isim-fiil bir komuttur
  (`fl config` gibi grubu olmayan komutlarla aynı statü).
- **Kurulum:** TUI, CLI ile **birlikte** kurulur (kullanıcı kararı: "CLI kuran TUI'yi de kurar",
  tek install). `pyproject.toml` ana `dependencies`'ine `textual>=0.60` eklenir — ayrı extra
  (`[project.optional-dependencies]`) AÇILMAZ; `fl tui` çalışmayan bir kurulum "yarım kurulum"dur.
- **Çıkış/geri dönüş:** `q` ile TUI'den çıkılır, terminal normal shell'e döner. TUI sırasında
  terminal alternatif ekran buffer'ına geçer (Textual varsayılanı); çıkışta ekran eski haline döner.

### 1.3 Kullanıcı kimliği ve oturum

`fl tui` **kendi login akışı istemez**. `fl auth login` ile girilmiş kalıcı oturum (keyring +
FileTokenStore fallback — bkz. bölüm 6.2) SDK'nın varsayılan token store'undan otomatik okunur.
Auth gerektiren bölümler (watchlist/favoriler, haberler) oturum yoksa ekranda yönlendirme gösterir;
pano (public veri) auth'suz da çalışır.

---

## 2. Ekranlar (v1)

Üç ekran + detay görünümü. Tümü `Screen` alt sınıfı; uygulama `App.SCREENS` kaydı üzerinden
`switch_screen("dashboard" | "watchlist")` ile geçiş yapar, detay ekranı `push_screen` ile açılır
(geri dönüş `esc`/`pop_screen`). Sebep: detay ekranı "üstüne açılan" bir görünümdür; pano ↔ watchlist
ise eşit seviye geçişlerdir (karar noktası K1 — TabbedContent alternatifi bölüm 9'da).

Ortak çerçeve (üç ekranda da):
```
┌──────────────────────────────────────────────────────────────┐
│ Header: Florence · fl tui          [saat]  [piyasa: AÇIK/KAPALI] │  ← Textual Header + PiyasaDurumu
├──────────────────────────────────────────────────────────────┤
│                    (ekran içeriği — aşağıda)                  │
├──────────────────────────────────────────────────────────────┤
│ Footer: [q] Çıkış  [1] Pano  [2] İzleme  [r] Yenile  [h] Yardım │  ← Textual Footer (BINDINGS'ten)
└──────────────────────────────────────────────────────────────┘
```

- **Header:** Textual'ın yerleşik `Header` widget'ı (uygulama adı + saat). Sağına piyasa durumu
  göstergesi eklenir: `market_status()` → `{open, next_open_at, holiday}` (public, 60s backend
  cache). `open=True` → yeşil **AÇIK**; `open=False` → kırmızı **KAPALI** (+ `next_open_at` saati);
  `holiday=True` → sarı **TATİL**. Bu şerit üç ekranda da görünür (App seviyesinde ortak bileşen —
  `widgets/status_bar.py`).
- **Footer:** Textual `Footer`, `BINDINGS` listesinden otomatik doldurulur — elle ipucu yazılmaz.

### 2.1 PANO (`DashboardScreen`)

**Amaç:** Piyasanın 10 saniyelik özeti. Bir bakışta: piyasa açık mı, hangi hisseler öne çıkıyor,
günün hareketleri neler, altın/döviz ne durumda.

**Layout şeması:**
```
┌──────────────────────────────────────────────────────────────┐
│ Header · piyasa durumu şeridi                                 │
├───────────────────────────────┬──────────────────────────────┤
│  ÖNE ÇIKANLAR (stats_top)      │  GÜNÜN HAREKETLERİ           │
│  ┌───────────────────────────┐ │  ┌─────────────────────────┐ │
│  │ Ticker   İlgi             │ │  │ Ticker  Fiyat   Δ%      │ │
│  │ THYAO     99              │ │  │ [gainers tablosu]       │ │
│  │ ASELS     87              │ │  │ ...                     │ │
│  │ ...                       │ │  │ [losers tablosu]        │ │
│  └───────────────────────────┘ │  └─────────────────────────┘ │
│  (DataTable, satır seçilebilir)│  (DataTable; g/l sekmeli —   │
│                                │   Gainers/Losers değiştirme) │
├───────────────────────────────┴──────────────────────────────┤
│  DEĞERLİ MADEN / DÖVİZ ŞERİDİ                                 │
│  Gram Altın 40,25 │ Çeyrek 3.450 │ USD/TRY 42,10 │ EUR/TRY 45,30 │
└──────────────────────────────────────────────────────────────┘
```

**Veri kaynakları (tümü public, auth'suz):**

| Panel | Resource metodu | Parametreler | Poll aralığı |
|---|---|---|---|
| Üst bar: piyasa durumu | `market.market_status()` | — | 60s (backend zaten 60s cache) |
| Öne çıkanlar | `market.stats_top(limit=10)` | `limit=10` | 45s (config `tui_refresh_seconds`) |
| Günün hareketleri | `market.companies_summary(limit=10, sort="gainers")` ve `sort="losers"` | `limit=10` | 45s |
| Maden/döviz şeridi | `economy.gold_prices()` + `economy.currency(symbols="USD,EUR")` | — | 45s (maden) / 45s (döviz) |

- **Öne çıkanlar tablosu:** `stats_top` → `[{"ticker": "THYAO", "count": 99}, ...]`. Sütunlar:
  `Ticker`, `İlgi`. İlgi sütunu count değerine göre kayan renk (yüksek = vurgulu). Bu tablo
  **fiyat bilmez** — yalnızca popülerlik sıralamasıdır; başlıkta "Öne Çıkanlar (ilgi)" yazar,
  fiyat beklentisi yaratılmaz.
- **Günün hareketleri:** `companies_summary` `sort="gainers"` / `sort="losers"` (backend destekli
  sort değerleri — birebir). Sütunlar: `Ticker`, `Fiyat`, `Δ%`. Δ% hücresi **renkli** (yeşil
  yükseliş / kırmızı düşüş — TR BIST konvansiyonu, bölüm 5.3). Varsayılan sekme **Gainers**;
  `g`/`l` tuşları veya Tab ile Gainers↔Losers geçişi. Her iki liste tek `companies_summary` çağrısı
  ailesinden gelir (iki ayrı sort ile 2 istek; aynı tick'ta). Sütun şeması openapi'den gelen alan
  adlarına göre implementasyonda netleşir (`close`/`change_pct` benzeri alanlar; rapor,
  test mock'larında görünen `price`/`change_pct` sözleşmesini esas alır — implementasyon,
  `companies_summary` yanıtının gerçek anahtarlarını birebir kullanır, uydurma alan yok).
- **Maden/döviz şeridi:** Tek satır `Static` — `gold_prices()` (16 kalemden seçilen: gram-altın,
  çeyrek-altın, cumhuriyet-altını — `Type` alanından seçim; backend TR string değer: `"40,25"` —
  gösterimde **olduğu gibi** TR virgülle basılır, sayısal işlem yok) ve `currency()` →
  `{"USD": {"buying": "42,10"}, "EUR": {...}}` (aynı TR string kuralı). Altın kalemleri backend'de
  `Type`/`Buying`/`Selling` anahtarlarıyla gelir (test şemasından birebir); şeritte `Buying`
  (alış) gösterilir. `economy` değerlerinin **string** olması bilinçli bir pitfall'dır
  (economy_res.py docstring): TUI bu değerleri sayıya çevirmez, metin olarak basar — virgül
  dönüşümü yalnızca (v2'de) grafik/karşılaştırma gerekirse `replace(",", ".")` ile yapılır.
- **Satır seçimi → detay:** Öne çıkanlar ve hareketler tablolarında satır seçip `enter` →
  `DetailScreen(ticker)` push edilir (watchlist'teki aynı akış).

**Yükleme / hata / boş durumlar:**

| Durum | Gösterim |
|---|---|
| İlk yükleme | Ekran boş gelmez; her panel kendi `Loading…` placeholder'ı ile başlar, worker bitince dolar |
| Network hatası (`NetworkError`) | Pano üstünde kırmızı banner: `Bağlantı hatası — son veri gösteriliyor (12:04)`. Önceki veri **silinmez**, `son güncelleme` zamanı eklenir |
| 429 (`RateLimitError`) | Banner: `Rate limit — {retry_after}s sonra tekrar deneniyor`. Poll interval geçici uzatılır (bölüm 4.4) |
| Piyasa kapalı | Üst şerit `KAPALI` + `next_open_at`; tablolar yine dolar (son kapanış verisi) |
| Boş yanıt (örn. stats_top boş liste) | Panel: `Veri yok` — tablo değil, kısa metin |
| `FLORENCE_API_URL` yanlış | İlk tick'te `NetworkError` → banner + footer'da ipucu: `fl config set api_url …` |

### 2.2 WATCHLIST (`WatchlistScreen`)

**Amaç:** Kullanıcının favori hisselerinin canlı fiyatları + kısa dönem eğilimi (sparkline).
Satır seç → sağ panelde önizleme; `enter` → tam detay ekranı.

**Layout şeması:**
```
┌──────────────────────────────────────────────────────────────┐
│ Header · piyasa durumu şeridi                                 │
├───────────────────────────────────────┬──────────────────────┤
│  İZLEME LİSTESİ (favoriler)           │  ÖNİZLEME (seçili)   │
│  Ticker  Fiyat   Δ%    Sparkline      │  ┌────────────────┐  │
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
| Favori listesi | `portfolio.favorites()` | JWT | `["THYAO", "ASELS"]` (test şemasından birebir) |
| Satır fiyatı | `market.current_price(ticker)` | public | `{ticker, price, change_pct, market_status}` |
| Sparkline verisi | `market.price_history(ticker, period="1mo", interval="1d")` | public | `close` değerleri → sparkline |
| Önizleme: şirket bilgisi | `market.company_info(ticker)` | public | `longName` vb. |
| Önizleme: mini grafik | aynı `price_history` (önbellekten) | public | 1dk TTL cache ile tek istek |

- **Poll akışı (tek tick):** `favorites()` (1 istek) → her ticker için `current_price` +
  `price_history(1mo)` — N favori için 2N istek. 10 favori = 21 istek / 45s → api rate limit
  (30/s) rahatça karşılanır. **Cache kuralı (bölüm 4.5):** aynı ticker'ın `current_price`'ı 1dk
  TTL; `price_history` 10dk TTL — Watchlist ile Detay ekranı aynı ticker'ı paylaşınca tek istek.
- **Sparkline sütunu:** son 30 işlem günü (`1mo` + `1d`) `close` serisi → mini braille/blok grafik
  (bölüm 5). Sütun dar tutulur (~12 karakter); değerler normalizasyonla `[0,1]`'e çekilir.
- **Δ% rengi:** `change_pct` işaretine göre yeşil/kırmızı; sıfır gri.
- **Fiyat formatı:** TR ondalık ayracı (`313,40`) + binlik ayraç (`1.234,50`) — hedef kitle TR
  BIST yatırımcısı (cli-design.md dil kuralıyla aynı ruh: metinler Türkçe).
- **Satır seç → önizleme:** DataTable satır cursor'ı hareket ettikçe sağ panel
  `company_info(ticker)` + mini grafik ile yenilenir (her hareket istek atmaz — seçili ticker
  değişince yalnızca cache'te olmayan veri çekilir).
- **`enter` → detay:** `DetailScreen(ticker)` push.

**Boş watchlist:** `favorites()` boş liste dönerse tablo yerine ortalanmış mesaj:
```
Favoriniz yok.
CLI'dan ekleyin:  fl portfolio favorite add THYAO
(Pano ekranında bir hisse seçip `f` ile de ekleyebilirsiniz — v1'de öneri metni yeterli)
```
Ek olarak alt satırda ipucu: `fl portfolio favorite add <TICKER>` ile listeye ekleyin; sonra `r`
ile yenileyin.

**Auth yok:** `client.auth.is_authenticated() == False` ise watchlist içeriği yerine uyarı
(bölüm 6.3): `Oturum bulunamadı — 'fl auth login' ile giriş yapın`. Pano etkilenmez.

**Hata durumları:** genel kurallar pano ile aynı (banner + son veri). `favorites()` 401 dönerse
(oturum süresi doldu, refresh başarısız) watchlist ekranında `Oturum süresi doldu — tekrar giriş
yapın (fl auth login)`; SDK client'ı 401'de otomatik single-flight refresh dener, yalnızca o da
başarısızsa bu mesaj görünür.

### 2.3 DETAY / GRAFİK (`DetailScreen`)

**Amaç:** Tek ticker'ın tam görünümü: şirket bilgisi, büyük çizgi grafik (period seçilebilir),
güncel fiyat ve haberler.

**Layout şeması:**
```
┌──────────────────────────────────────────────────────────────┐
│ Header · piyasa durumu şeridi                                 │
├──────────────────────────────────────────────────────────────┤
│  ASELS — Aselsan Elektronik Sanayi (SAVUNMA)                  │
│  Fiyat: 1.234,50   Δ: -1,20%   Piyasa: AÇIK   [dönem: 3mo]   │
├──────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────┐  │
│  │  ÇİZGİ GRAFİK (price_history, period seçilebilir)      │  │
│  │  en yüksek 1.280 ──▄▄▆█▆▄──                            │  │
│  │  son 1.234 ──────────▄▄▆█▄──                           │  │
│  │  en düşük 1.150 ───────▄▄──                            │  │
│  │  [eksen etiketleri: min / son / max]                   │  │
│  └────────────────────────────────────────────────────────┘  │
│  HABERLER (news, JWT — auth yoksa gizlenir)                  │
│  • THYAO haberi (2s önce)                                    │
│  • ...                                                        │
├──────────────────────────────────────────────────────────────┤
│ Footer: [1|3|6|y] dönem  [esc] geri  [r] yenile               │
└──────────────────────────────────────────────────────────────┘
```

**Veri kaynakları:**

| Bileşen | Resource metodu | Auth | Poll aralığı |
|---|---|---|---|
| Şirket bilgisi | `market.company_info(ticker)` | public | Ekran açılışında + her 5 dk |
| Güncel fiyat | `market.current_price(ticker)` | public | 45s |
| Grafik | `market.price_history(ticker, period=<seçili>, interval="1d")` | public | Period değişince + 5 dk |
| Haberler | `market.news(ticker, amount=10)` | **JWT + news feature** | 90s (2. tick'ta) |

- **Üst bilgi satırı:** `company_info` → `longName` + sektör alanı (test şeması `longName`'i
  gösterir; sektör alan adı implementasyonda openapi'den doğrulanır, uydurma yok). Fiyat +
  Δ% `current_price`'tan; piyasa durumu `market_status` (header şeridinden ortak).
- **Period seçimi (klavye):** `1`/`3`/`6`/`y` tuşları → `1mo`/`3mo`/`6mo`/`1y`. Varsayılan
  `tui_default_period` config'inden (default `1mo`). Period değişince grafik `Loading…` gösterir,
  yeni `price_history` gelince çizilir. Period göstergesi grafik başlığında yanar.
  - `interval="1d"` tüm period'lar için sabittir (backend interval kısıtı: `5m..3mo`; 1d tüm
    period'larla uyumludur). Gün içi detay (5m/30m) v1 kapsamı dışı — not.
- **Grafik:** büyük boyutlu çizgi grafik (bölüm 5). Y ekseni etiketleri: dönem içi min/son/max
  değerleri, solda; x ekseni: dönem başı/sonu tarihleri. Grafik widget'ı `widgets/sparkline.py` —
  Textual `Sparkline` sarmalayıcı (blok karakter) + etiket satırları. `summary_function` ile
  son değer vurgusu.
- **Haberler:** `news()` **10/dk rate limit + JWT** (market_res.py docstring'den birebir). Bu
  yüzden haberler 45s'lik ana tick'te değil, **her 2. tick'ta (90s)** çekilir → 0,67 istek/dk,
  limitin çok altında. `news` feature kapalıysa (403/`error_news_not_allowed` benzeri) haber
  paneli sessizce gizlenir, uyarı basılmaz (kullanıcıyı rahatsız etmez; CLI'da da aynı davranış).
  - Auth yoksa (oturum yok) haberler bölümü hiç gösterilmez; yerine tek satır:
    `Haberler için giriş yapın: fl auth login`.
- **Geri dönüş:** `esc` → `pop_screen()` (geldiği ekrana döner: watchlist veya pano).

**Yükleme / hata durumları:** ortak banner kuralları. Grafik verisi yoksa (boş liste) grafik
alanı: `Bu dönem için veri yok`. `current_price` hatasında üst satır gri `—` gösterir, fiyat
silinmez (son bilinen değer + zaman damgası).

### 2.4 v2 NOTU — Portföy ekranı (kapsam dışı)

Portföy ekranı v2'ye bırakılmıştır (kullanıcı kararı). İmplementasyonda bırakılacak genişleme
noktaları (bu raporda sadece not):

- `portfolio.list_portfolios()` → portföy seçimi → `snapshot()` (birleşik özet) + `history(period)`
  grafiği + `performers(top_n)` listesi. Auth zorunlu.
- Ekran kaydına `"portfolio"` eklenir; `4` tuşu ile erişim; pano/watchlist ile aynı polling
  altyapısı (DataService) kullanılır — yeni mimari gerekmez.
- `tui_watchlist_source` benzeri config anahtarları bu fazda netleşir.

---

## 3. Klavye ve Gezinme

### 3.1 Tuş haritası (v1)

| Tuş | Eylem | Kapsam |
|---|---|---|
| `q` / `ctrl+q` | Uygulamadan çık (`action_quit`) | Global |
| `1` | Pano ekranına geç (`switch_screen("dashboard")`) | Global |
| `2` | Watchlist ekranına geç (`switch_screen("watchlist")`) | Global |
| `enter` | Seçili satırın detayını aç (pano/watchlist) | Pano, Watchlist |
| `esc` | Detaydan geri dön (`pop_screen`) | Detay |
| `j` / `down` | Satır aşağı (DataTable cursor) | Pano, Watchlist |
| `k` / `up` | Satır yukarı | Pano, Watchlist |
| `g` / `l` | Günün hareketleri: Gainers ↔ Losers sekmesi | Pano |
| `f` | Seçili ticker'ı favorilere ekle/çıkar (toggle, JWT) | Pano, Watchlist, Detay |
| `r` | Manuel yenile (tüm worker'ları şimdi tetikle) | Global |
| `1` / `3` / `6` / `y` | Grafik period'u: 1mo / 3mo / 6mo / 1y | Detay |
| `h` | Yardım paneli (ModalScreen: tuş haritası + sürüm) | Global |
| `p` | (v2) Portföy ekranı — v1'de yok | — |

> **Not:** `1`/`3`/`6`/`y` çakışması yok — `1` global "Pano" iken detay ekranında "1mo" olarak
> yorumlanır. Textual'da binding çakışması ekran bazlıdır: Detay ekranı kendi `BINDINGS`'ini
> tanımlar (screens/detail.py); `1` Detay'dayken period anlamına gelir. Kullanıcıya Footer'da
> mevcut ekranın binding'leri gösterilir (Footer, aktif screen'in bindings'ini otomatik listeler).

### 3.2 Footer ipuçları

`Footer` widget'ı, **o an aktif ekranın** `BINDINGS` listesinden kısa ipuçlarını otomatik çizer
(`q Çıkış`, `1 Pano`, `2 İzleme`, `r Yenile`, `h Yardım` …). Uygulama seviyesi bindings +
ekran seviyesi bindings birleşir; Detay ekranında Footer'da `esc Geri`, `3 Dönem: 3mo` gibi
ekran-bazlı tuşlar görünür. Açıklamalar Türkçe (cli-design.md dil kuralı: komut adları İngilizce,
**metinler Türkçe**).

### 3.3 Yardım paneli (`h`)

`ModalScreen` tabanlı küçük panel: tuş haritası tablosu + SDK sürümü (`florence.__version__`) +
API adresi (`config.get_base_url()`). `esc`/`q` ile kapanır. Veri isteği yapmaz (offline).

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

- **`set_interval`:** Textual'ın App metodu — event loop'ta zamanlayıcı kurar, callback async
  olabilir. TUI'nin tek zamanlayıcı kaynağıdır (WS yok, ayrı thread yok).
- **`run_worker(group="poll")`:** Her tick bir **Worker** başlatır. `group="poll"` + `exclusive`
  davranışı: önceki worker hâlâ çalışıyorsa (yavaş ağ) yeni tick **atlanır** (üst üste binen
  istek yok — "poll overlap" koruması). Textual `Worker`'lar asyncio task'leridir; `await`'ler
  event loop'u bloklamaz, TUI tuşlara anında yanıt vermeye devam eder.
- **Senkron client YASAK:** `FlorenceClient` (senkron) TUI içinde kullanılmaz — `time.sleep`
  içeren retry'ları ve bloklayan `request()`'i event loop'u dondurur. Yalnızca
  `AsyncFlorenceClient` (bkz. `client.py`: `AsyncFlorenceClient.request` → `await`) kullanılır.
- **Client yaşam döngüsü:** `AsyncFlorenceClient` **bir kez**, `App.on_mount`'ta oluşturulur
  (default token store ile — auth bölüm 6.2); `App.on_unmount`'ta `await client.close()`.
  Her tick'te client yaratılmaz (bağlantı havuzu + auth state korunur).
- **Worker sonucu widget'a nasıl ulaşır:** Worker doğrudan widget'a dokunmaz; `post_message`
  ile ekranın message handler'ına teslim eder (Textual deseni: worker ↔ widget arası mesajlaşma).
  Böylece veri geldiğinde UI güncellenir; hata durumunda hata mesajı taşınır.

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

**Aktif ekran kuralı:** Arka plandaki ekranın verisi çekilmez (pano arka plandayken watchlist
istekleri yapılmaz). Tasarruf + rate limit bütçesi. Ekrana dönüldüğünde (switch) veri hemen
tazelenir (anında tick).

### 4.3 Manuel yenileme (`r`)

`r` → `_on_poll_tick()` doğrudan çağrılır (interval'i beklemez). Aynı `exclusive` worker kuralı
geçerlidir: devam eden bir poll varsa yenileme yeni istek başlatmaz, mevcut sonucu bekler —
"debounce" doğal olarak sağlanır. `r` spam'i 429 riski yaratmaz (client'ın 30/s limitine karşı
zaten güvenli, ama yine de 5s içinde en fazla 1 manuel tick kabul edilir).

### 4.4 Rate limit bilinci (429)

- Client zaten 429'da `Retry-After`'a saygılı retry yapar (client.py: `_retry_after_seconds`,
  `max_retries=2`). TUI seviyesinde ek koruma:
- **Interval uzatma:** `RateLimitError` alındığında poll intervali geçici olarak
  `max(current_interval * 2, retry_after + 10s)` yapılır (üst sınır 300s). Banner gösterilir:
  `Rate limit — {retry_after}s sonra tekrar`. Sonraki 3 başarılı tick'ten sonra interval
  config'teki değere döner.
- **Manuel yenileme kilidi:** interval uzamışken `r` devre dışı bırakılmaz ama `notify`
  (Textual toast) ile bilgi verilir: `Rate limit beklemede — {k}s`.
- **News özel kuralı:** `news` 10/dk limitli olduğundan haber isteği başarısız olursa bir sonraki
  haber denemesi 90s değil 5 dk sonraya ertelenir.

### 4.5 Cache (DataService içi, thread-safe olması gerekmez — tek event loop)

| Veri | TTL | Gerekçe |
|---|---|---|
| `market_status` | 60s | Backend zaten 60s cache'li |
| `current_price` (ticker başına) | 60s | Watchlist + detay aynı ticker'ı paylaşır |
| `price_history` (ticker+period başına) | 10dk | Gün içi değişir ama dakikada bir çekmek anlamsız |
| `company_info` | 5dk | Nadiren değişir |
| `gold_prices` / `currency` | 60s | |
| `news` | 5dk | Rate limit koruması + nadiren değişir |
| `favorites` | 60s | |

Cache, `data.py` içinde basit `dict[key] -> (expires_at, value)` yapısıdır; event loop tek
thread'li olduğundan kilit gerekmez. Aynı tick içinde aynı anahtar ikinci kez istenirse cache'ten
döner — ağ isteği yok.

### 4.6 Piyasa kapalıyken davranış

`market_status.open == False` ise fiyat verileri değişmeyeceği için **fiyat poll'ları otomatik
yavaşlar**: interval geçici olarak 5 dk'ya çıkar (config `tui_market_closed_refresh`, default
300s). Header'daki `KAPALI · 10:00'da açılacak` göstergesi yine güncellenir. Bu, "piyasa kapalıyken
boşuna istek" sorusunun cevabıdır (karar noktası K4).

---

## 5. Sparkline / Çizgi Grafik

### 5.1 Karakter seti: blok (v1) — braille opsiyonel

| Yaklaşım | Karakter | Yoğunluk | Değerlendirme |
|---|---|---|---|
| **Textual `Sparkline` (blok)** | Yarım blok unicode (`▀▄█▌▐` vb.) | 2 veri noktası / sütun | **Hazır widget**: `textual.widgets.Sparkline(data, summary_function=...)` — testli, renkli, terminal uyumlu, `data` reactive property ile güncellenir |
| Custom braille | U+2800–U+28FF (2×4 nokta) | 4 veri noktası / sütun | Daha yoğun (dar terminallerde avantaj) ama custom render + font/terminal desteği riski; Textual'da hazır braille widget yok |

**Öneri (v1):** Her iki kullanımda da **Textual `Sparkline`** (blok karakter). Gerekçe: hazır ve
bakımlı widget, `summary_function` ile uç değer etiketi, renk stilleri CSS ile, watchlist mini
grafiğinden detay ekranının büyük grafiğine kadar aynı bileşen. Braille, yoğun veride (ör. gün içi
5m interval — v1 dışı) düşünülür; `widgets/sparkline.py` içinde soyut bir `render(data)` fonksiyonu
ile ayrılır, implementasyon değişirse widget değişmez (karar noktası K2).

### 5.2 Veri normalizasyonu

- Girdi: `price_history` yanıtından `close` değerleri (test şeması: `[{ts, open, close, volume}]`).
  Eksik `close` (None) olan kayıtlar seriden çıkarılır (backend bazen ara tatil günü boş bırakır).
- Normalizasyon: `v' = (v - min) / (max - min)` → `[0, 1]`. `max == min` (düz seri) ise tüm
  noktalar 0.5'e sabitlenir (ortada düz çizgi) — bölünme hatası yok.
- Sparkline veri boyutu terminal genişliğine göre **örneklenir** (downsample): her sütuna 1 nokta;
  sütun sayısı widget genişliğinden gelir. Watchlist sütunu ~12 karakter → seriden son 12 nokta
  değil, **son 12 sütuna örneklenmiş** tüm seri (eğilim doğru görünür).
- Grafik ekseni (detay): solda min / son / max değerleri (TR format), altta dönem başı–sonu
  tarihleri. `summary_function=min/max` ile Sparkline üstüne uç değer etiketleri.

### 5.3 Renk kuralları (TR BIST konvansiyonu)

- **Yükseliş = yeşil** (`$success`), **düşüş = kırmızı** (`$error`), **değişim yok = gri**.
  (Batı borsalarındaki kırmızı-yükseliş tersine, Türkiye'de yeşil yükseliştir — kullanıcı kararı.)
- Uygulama alanları: Δ% hücreleri (pano hareketleri, watchlist), sparkline çizgisi (dönem başına
  göre son değer yukarıda/aşağıdaysa yeşil/kırmızı), detay grafiği.
- Watchlist sparkline rengi **dönem getirisine** bağlanır (serinin ilk ve son close'u
  karşılaştırılır) — günlük Δ%'den bağımsız, çünkü sparkline 1 aylık eğilimi gösterir.
- Renkler Textual CSS tema değişkenlerinden gelir (dark/light temada otomatik uyum).

### 5.4 Period seçimi (detay)

`1mo`/`3mo`/`6mo`/`1y` → `price_history(ticker, period=X, interval="1d")`. Period haritası:

| Tuş | Period | `interval` | Veri noktası (yaklaşık, iş günü) |
|---|---|---|---|
| `1` | `1mo` | `1d` | ~22 |
| `3` | `3mo` | `1d` | ~65 |
| `6` | `6mo` | `1d` | ~130 |
| `y` | `1y` | `1d` | ~260 |

Backend `interval` kısıtı (`5m..3mo` aralık) `1d` ile her period'da geçerlidir; gün içi
(5m/30m/1h) interval'ler v1'de sunulmaz (period başına iki boyutlu seçim UI karmaşasını artırır —
not olarak bırakılır, `current_price` `interval` parametresi yalnızca SDK varsayılanıyla
kullanılır).

---

## 6. Config ve Auth

### 6.1 Config: `~/.config/florence/config.toml` — TUI anahtarları

cli-design.md'de `fl config set` allowlist'i şu an yalnızca `api_url` / `default_output` içeriyor.
TUI bu listeye **yeni anahtarlar ekler** (CLI ile koordinasyon — cli-design.md'ye eklenecek):

| Anahtar | Tip | Varsayılan | Açıklama |
|---|---|---|---|
| `tui_refresh_seconds` | int | `45` | Ana poll aralığı (saniye). Kullanıcı kararı 30–60; 10–600 arası kabul, dışı clamp |
| `tui_default_period` | str | `"1mo"` | Detay grafiği başlangıç period'u (`1mo`/`3mo`/`6mo`/`1y`) |
| `tui_market_closed_refresh` | int | `300` | Piyasa kapalıyken fiyat poll aralığı (saniye) |
| `tui_watchlist_source` | str | `"favorites"` | Watchlist kaynağı: `favorites` (JWT) \| `local` (yerel dosya listesi — v2, karar noktası K1) |

- Örnek:
  ```toml
  api_url = "https://api.florencex.com.tr"
  default_output = "table"
  tui_refresh_seconds = 45
  tui_default_period = "3mo"
  tui_market_closed_refresh = 300
  tui_watchlist_source = "favorites"
  ```
- **Öncelik:** env (`FLORENCE_API_URL`, `FLORENCE_TOKEN`) > config > SDK default (cli-design.md
  kuralıyla aynı). TUI anahtarları env override gerektirmez (yok); yalnızca config.
- TUI config'i **kendisi yazmaz** (salt-okunur) — değişiklikler `fl config set tui_refresh_seconds 60`
  ile yapılır (CLI entegrasyon notu: `fl config set` allowlist'ine `tui_*` anahtarları eklenmeli;
  `fl config show` da bunları göstermeli). Config yoksa veya anahtar yoksa varsayılanlar kullanılır.

### 6.2 Kalıcı auth yeniden kullanımı

- TUI, `AsyncFlorenceClient()` **default token store**'u ile oluşturulur — yani
  `AuthManager` → `KeyringTokenStore(keyring_service="florence-sdk")`. CLI'nin `fl auth login` ile
  yazdığı access/refresh token'lar keyring'den otomatik okunur; `FLORENCE_TOKEN` env override'ı da
  aynen çalışır (auth.py: `access_token()` env önceliği).
- **Headless fallback:** keyring'in çalışmadığı ortamda CLI fazı T3.2b'nin ekleyeceği
  `FileTokenStore` (Fernet şifreli `~/.config/florence/tokens.json`) devreye girer. TUI hiçbir
  store seçmez — **varsayılanı kullanır**; böylece "CLI'da girilen oturum TUI'de de geçerli"
  garantisi otomatiktir (aynı store zinciri).
- **401 akışı:** `AsyncFlorenceClient` 401'de otomatik single-flight `refresh_async()` dener
  (client.py); TUI'nin ekstra işi yoktur. Refresh de başarısızsa `AuthError` → auth-gerektiren
  ekranlarda yönlendirme mesajı (aşağıda).
- TUI **içinde login yapılmaz** (şifre prompt'u yok, şifre hiçbir zaman TUI'ye girmez) — bu,
  güvenlik kuralıdır: token'lar yalnızca CLI auth akışıyla yazılır.

### 6.3 Auth durumu ekranlara nasıl yansır

| Oturum | Pano | Watchlist | Detay (news) | Detay (fiyat/grafik) |
|---|---|---|---|---|
| Yok | ✅ çalışır (public) | ⚠️ uyarı: `Oturum bulunamadı — 'fl auth login' ile giriş yapın` | Bölüm gizli: `Haberler için giriş yapın` | ✅ çalışır (public) |
| Var (user/bot) | ✅ | ✅ favoriler | ✅ | ✅ |
| Süresi doldu (refresh başarısız) | ✅ | ⚠️ `Oturum süresi doldu — tekrar giriş yapın (fl auth login)` | gizli | ✅ |

- `f` (favori toggle) tuşu auth'suz ortamda `notify("Favoriler için giriş yapın")` gösterir, istek
  atmaz.
- Bot oturumları (bot login ile girilmiş) TUI'de normal oturum gibi çalışır — fark yok
  (auth.py `bot_session` TUI tarafından kullanılmaz; kalıcı bot oturumu CLI'da yapılmışsa store'da
  zaten vardır).

---

## 7. Dosya Düzeni

### 7.1 `src/florence/tui/` paketi

```
src/florence/tui/
├── __init__.py            # public API: main(), FlorenceTUIApp (testler için)
├── app.py                 # FlorenceTUIApp: BINDINGS, SCREENS, client lifecycle,
│                          #   polling yöneticisi (set_interval + worker), hata banner'ları
├── keys.py                # Tuş/action sabitleri (BINDINGS tanımları, period haritası
│                          #   PERIODS = {"1": "1mo", "3": "3mo", "6": "6mo", "y": "1y"})
├── data.py                # DataService: TTL cache + async fetch'ler (poll orkestrasyonu)
│                          #   — ekranlardan ve worker'lardan tek erişim noktası
├── screens/
│   ├── __init__.py
│   ├── dashboard.py       # DashboardScreen (Pano)
│   ├── watchlist.py       # WatchlistScreen (favoriler + önizleme paneli)
│   └── detail.py          # DetailScreen (ticker detay + grafik + haberler)
└── widgets/
    ├── __init__.py
    ├── sparkline.py       # SparklineChart: Textual Sparkline sarmalayıcı + eksen etiketleri
    │                      #   (render(data, width, height) soyutlaması — braille/geçişi burada)
    ├── price_table.py     # Ortak DataTable yardımcıları: TR sayı formatı, renkli Δ% hücresi,
    │                      #   ticker sütunu kuralları (^[A-Z0-9.\-]{1,12}$, büyük harf)
    └── status_bar.py      # Piyasa durumu şeridi (AÇIK/KAPALI/TATİL + next_open_at) — Header
                            #   yanında ortak bileşen (üç ekranda da)
```

**Sorumluluk ayrımı:**

- `app.py` — uygulama iskeleti: client oluşturma/kapama, global BINDINGS, ekran kaydı,
  `set_interval` kurulumu, tick → `run_worker` (exclusive), banner'lar (App seviyesi notify/banner).
- `data.py` — **tek veri erişim noktası**: cache'ler, rate-limit interval yönetimi, worker'ların
  çağırdığı async metodlar. Ekranlar `DataService`'i çağırır; `AsyncFlorenceClient`'a doğrudan
  dokunmaz (test edilebilirlik: service inject edilir, bölüm 8).
- `screens/*` — yalnızca sunum: widget düzeni, tuş eylemleri, `post_message` handler'ları.
  Veri mantığı içermez.
- `widgets/*` — yeniden kullanılabilir görsel bileşenler.
- `keys.py` — sabitler (period haritası, tuş adları); ekranlar arası tutarlılık tek yerden.

### 7.2 Bağımlılık

`pyproject.toml` `[project] dependencies`'ine eklenir:

```toml
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.7",
    "keyring>=25",
    "mcp>=1.2",
    "fastmcp>=2.0",
    "textual>=0.60",   # TUI — CLI ile birlikte kurulur (kullanıcı kararı)
]
```

`textual>=0.60` alt sınırı; mevcut kararlı seri (0.6x–2.x) ile API uyumluluğu korunur (Sparkline,
run_test, set_interval, Worker bu serinin tamamında istikrarlıdır). Ruff (line-length 100) ve
mypy/pyright (Faz 9 CI) kurallarına uyulur — `tui/` paketi de aynı lint/type kapsamında.

### 7.3 `fl tui` CLI bağlantısı

- `fl tui` typer komutu `src/florence/cli/` içinde tanımlanır: `commands_tui.py` modülü bir
  `@app.command("tui")` döndürür (veya doğrudan `app.py`'ye eklenir — CLI subagent'ının dosya
  düzenine göre; cli-design.md'de `commands_*.py` deseni var, `commands_tui.py` bu desene uyar).
- Komut gövdesi tek iş yapar: `from florence.tui.app import main; main()` — typer komutu yalnızca
  **giriş noktasıdır**, TUI mantığı `florence/tui/` içindedir.
- `--json` bayrağı `fl tui` için **yoktur** (TUI zaten tam ekran interaktif; `--json` çıktı modu
  anlamsız — cli-design.md "gereksiz bayrak yok" kuralı). Argüman da yok (v1; opsiyonel
  `--ticker THYAO` doğrudan detay açma karar noktası K5).
- Entry point'ler değişmez: `fl` zaten `florence.cli.app:main`'e gider; `tui` bunun altında komut.
  `florence-mcp` entry point'i ayrıdır, dokunulmaz.
- **Koordinasyon notu (CLI subagent'ı):** `fl tui` komut iskeleti CLI implementasyonuna
  eklenecek; `fl config set/show` allowlist'ine `tui_*` anahtarları işlenecek. Bu rapor yazıldığı
  sırada `src/florence/cli/` henüz yoktu (eşzamanlı subagent'lar) — TUI implementasyonu CLI'nin
  bitmiş haline göre `commands_tui.py`'yi ekler.

### 7.4 Test dosyaları

```
tests/tui/
├── conftest.py            # fake_data fixture'ları (mock transport yanıtları), make_app helper
├── test_data.py           # DataService birim: cache TTL, 429 interval uzatma, dönüşümler
├── test_sparkline.py      # normalizasyon (min-max, düz seri), downsample, renk kuralı
├── test_screens.py        # her ekranın mock veriyle montajı + boş/hata durumları
└── test_app.py            # run_test ile: klavye akışları, ekran geçişleri, polling tick
```

Mevcut test konvansiyonuyla uyumlu: `tests/` kökünde düz pytest (cli-design.md `tests/cli/`
deseninin karşılığı `tests/tui/`).

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

- `run_test` ekranı gerçek terminal olmadan (headless) kurar; `Pilot` API'si (`press`, `pause`,
  `click`, `wait_for_screen`, `wait_for_worker`) klavye/etkileşim simülasyonu sağlar.
- **Network yok:** `DataService`'e testte `AsyncFlorenceClient(transport=httpx.MockTransport(handler))`
  inject edilir — `httpx.AsyncClient`'a `transport` parametresi zaten desteklenir (client.py
  `**httpx_kwargs`). Handler, path'e göre test verisi döndürür (test_resources.py'deki desenin
  aynısı). Hiçbir istek gerçek ağa çıkmaz.
- **App fabrikası:** `tests/tui/conftest.py` → `make_app(handler)` helper'ı: mock transport'lu
  client + `DataService` kurar, `FlorenceTUIApp` döndürür. Tüm testler bunu kullanır.

### 8.2 Test senaryoları

| Alan | Test | Nasıl |
|---|---|---|
| **Ekran montajı** | Pano, watchlist, detay mock veriyle mount olur; hücreler dolu | `run_test` + `app.screen` üzerinde widget sorgusu (`app.query_one(DataTable)`) |
| **Polling worker** | `set_interval` tick'i veriyi günceller; overlap'ta yeni tick atlanır | `pilot.pause()` ile tick atlat; ikinci worker `exclusive` davranışı `wait_for_worker` ile doğrula |
| **Klavye** | `1/2/3` geçiş, `j/k` satır, `enter` detay açılışı, `esc` dönüş, `r` manuel yenile, `q` çıkış, `1/3/6/y` period değişimi | `pilot.press(...)` + sonrası durum assert |
| **Veri dönüşümü** | TR sayı formatı (313,40), Δ% rengi (yukarı yeşil / aşağı kırmızı), economy string virgülünün dokunulmaması | `test_data.py` birim testleri (UI'sız) |
| **Sparkline** | min-max normalizasyon, düz seri (max==min → 0.5), downsample, dönem getirisine göre renk | `test_sparkline.py` saf fonksiyon testleri |
| **Hata / 429** | MockTransport 429 + `Retry-After: 30` döner → banner görünür, interval uzar, sonraki tickler cache'ten | `test_data.py` + `test_app.py` |
| **Network hatası** | MockTransport `httpx.ConnectError` → `NetworkError` → banner + son veri korunur | aynı |
| **Piyasa kapalı** | `market_status` `open:false` → interval 300s'e çıkar; header `KAPALI` gösterir | `test_data.py` |
| **Boş durumlar** | `favorites()` boş → "Favoriniz yok" mesajı; `stats_top` boş → "Veri yok"; `price_history` boş → "Bu dönem için veri yok" | `test_screens.py` |
| **Auth yok** | store boş (MemoryTokenStore) → watchlist uyarısı, pano çalışır, haberler gizli | `make_app` ile boş store |
| **Auth 401/refresh** | İlk istek 401 → client refresh isteği (mock) → yeniden deneme başarılı; refresh de 401 → `AuthError` → oturum uyarısı | `test_app.py` (client'ın testleri test_client.py'de ayrıca var — burada TUI'nin **gösterimi** test edilir) |

### 8.3 Zaman yönetimi (testlerde hız)

- `run_test` gerçek zamanlı çalışır; 45s interval'i testte beklemeyiz. Strateji:
  - `DataService`'in interval'i `make_app`'te kısa (ör. 0.1s) kurulur VEYA `_on_poll_tick()`
    doğrudan çağrılır;
  - `pilot.pause(0.2)` ile tick geçişi beklenir;
  - `wait_for_worker("poll")` ile worker'ın bitmesi beklenir — `pilot.wait_for_worker` API'si.
- Cache TTL'leri testte parametre olarak küçültülür (DataService constructor'ına `ttl_overrides`
  kabul eder) — 10dk TTL'yi testte beklemeyiz.

### 8.4 CI uyumu

- `tests/tui/` normal `pytest` kapsamındadır (Faz 9 CI'da otomatik koşar). `asyncio` testleri
  `pytest-asyncio` veya `asyncio.run` sarmalayıcısıyla (mevcut test_resources.py'deki desen —
  `asyncio.run(run())`) çalışır; yeni dev bağımlılık eklenmemesi için mevcut desen tercih edilir.
- Tüm TUI testleri `FLORENCE_LIVE=1` gerektirmez; canlı smoke (opsiyonel): `fl tui`'yi gerçek
  oturumla elle başlatmak — manuel doğrulama adımı, otomatik değil.

---

## 9. Açık Karar Noktaları

Kullanıcı onayı bekleyen maddeler (implementasyon öncesi netleştirilmeli):

1. **K1 — Watchlist kaynağı:** v1'de yalnızca **favoriler** (JWT `favorites()`) mi, yoksa
   `tui_watchlist_source = "local"` (config'de `~/.config/florence/watchlist.toml` yerel liste) da
   mı? **Öneri:** v1 favoriler; local liste v2 (auth'suz da watchlist çalışsın istenirse eklenir).
2. **K2 — Sparkline karakter seti:** v1'de hazır Textual `Sparkline` (blok karakter) yeterli mi,
   yoksa yoğun braille (U+2800) custom render şart mı? **Öneri:** blok v1; braille v2 (dar
   terminal kullanıcısı talebi olursa).
3. **K3 — Ekran modeli:** Üç ayrı `Screen` (switch/push) mi, tek ekran `TabbedContent` sekmeleri
   mi? **Öneri:** ayrı Screen'ler — detay "üstüne açılan" doğasına uyar, v2 portföy ekranı
   aynı mekanikle eklenir, Footer ekran-bazlı binding'leri net gösterir.
4. **K4 — Piyasa kapalıyken poll:** Fiyat poll'unu 5 dk'ya uzatmak (öneri, bölüm 4.6) doğru mu,
   yoksa her koşulda sabit `tui_refresh_seconds` mi? (Kapalıyken 45s'de bir istek atmak israf;
   uzatmak "açılışı kaçırma" riski taşır — `next_open_at`'e göre otomatik normale dönüş önerisiyle.)
5. **K5 — `fl tui` argümanları:** v1'de sıfır argüman (öneri) mı, yoksa `fl tui --ticker THYAO`
   ile doğrudan detay açma mı? (CLI "gereksiz bayrak yok" kuralı sıfır argümanı destekler;
   güç kullanıcı isteği gelirse eklenir.)

---

## Ek A — Veri sözleşmesi özeti (test şemalarından birebir)

Rapor boyunca atıf yapılan, `tests/test_resources.py`'de doğrulanmış yanıt şekilleri
(implementasyon bunlara göre ayrıştırır; alan adları openapi.json'dan teyit edilir):

| Uç | Şekil |
|---|---|
| `market_status()` | `{"open": bool, "next_open_at": str(ISO), "holiday": bool}` |
| `stats_top(limit)` | `[{"ticker": str, "count": int}]` |
| `current_price(ticker)` | `{"ticker": str, "price": float, "change_pct": float, "market_status": str}` |
| `price_history(ticker, period, interval)` | `[{"ts": str(ISO), "open": float, "close": float, "volume": int}]` |
| `company_info(ticker)` | `{"ticker": str, "longName": str, ...}` (extra alanlara toleranslı) |
| `news(ticker, amount)` | `[{"title": str, "url": str}]` — JWT + news feature, 10/dk |
| `gold_prices()` | `[{"Type": str, "Buying": "40,25", "Selling": "40,75"}]` — TR virgüllü STRING |
| `currency(symbols)` | `{"USD": {"buying": "42,10"}}` — TR virgüllü STRING |
| `favorites()` | `["THYAO", "ASELS"]` — JWT |
| `companies_summary(limit, sort, ...)` | Fiyat/Δ% alanlı özet tablosu; `sort`: popular\|alphabetical\|gainers\|losers\|price_high\|price_low\|volume\|market_cap |

**Pitfall'lar (implementasyonda hatırlanmalı):**
- `economy` değerleri string + TR virgül — sayısal işlem öncesi `replace(",", ".")`; gösterimde olduğu gibi.
- `news` 10/dk + JWT — detay ekranında 90s poll + auth yoksa gizle.
- `market_status` backend 60s cache — daha sık çekme anlamsız.
- `macroeconomy` 24h cache — v1 pano şeridinde kullanılmaz (günlük seri, anlık görünüme uymaz).
- Piyasa kapalıyken `add_transaction` 400 döner — v1'de işlem yok, portföy v2'de bu kural anılır.

## Ek B — Koordinasyon notları (eşzamanlı subagent'lar)

- **CLI subagent'ı:** `fl tui` komut iskeleti + `fl config set/show`'a `tui_*` anahtarları
  entegrasyonu (bu rapor bölüm 7.3). CLI `commands_*.py` deseniyle `commands_tui.py` eklenecek.
- **MCP subagent'ı:** TUI, MCP ile doğrudan ilişki kurmaz (MCP = LLM uygulamalarına tool fişi;
  TUI = insan arayüzü). Çakışma yok; yalnızca `florence_mcp` paketine dokunulmaz.
- **Ortak sözleşme:** TUI yalnızca SDK resource'larını ve `AsyncFlorenceClient`'ı kullanır —
  CLI/MCP'den hiçbir kod paylaşmaz, onların dosyalarına dokunmaz.
