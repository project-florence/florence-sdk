# Florence MCP Server — Tasarım Raporu

> **Durum:** Tasarım (implementasyon yok) · **Tarih:** 2026-08-14
> **Kapsam:** `florence-sdk` tek reposunda paketlenen MCP (Model Context Protocol) sunucusu (`florence-mcp` entry point).
> **Kaynaklar:** `src/florence/resources/*.py` (9 resource grubu), `src/florence/{auth,client,errors,config}.py`, `api-spec/openapi.json` (89 path), `api-spec/docs/ai-context.md`, plan `2026-08-14_144500-florence-sdk.md` (Faz 6), **`docs/cli-design.md` (eşzamanlı CLI tasarımı, yayınlandı)**.
> **CLI uyum notu:** Bu rapor yazılırken CLI tasarımı (`cli-design.md`) eşzamanlı üretiliyordu; rapor tamamlanmadan önce dosya yayınlandı ve **hizalama geçişi (alignment pass)** uygulandı. MCP tool adları CLI komut ağacıyla birebir uyumludur (aynı iş = aynı isim; grup düzeyinde **her grubun tool sayısı CLI komut sayısıyla eşittir**): `user_*` → `account_*` (CLI grubu `account`), `auth_refresh` kaldırıldı (CLI kararı: refresh otomatiktir, komut yok), `market_company_info_md` → `market_company_info(format=...)` ile birleştirildi (CLI `info --md` bayrağı), `export_get` → `export_status` (CLI `fl export status`). Ayrıntılı eşleme Bölüm 2.6'dadır.

---

## 1. Giriş

### 1.1 MCP nedir (kısa)

Model Context Protocol (MCP), LLM uygulamalarının (Claude Desktop, Claude Code, Cursor, diğer ajanlar) harici araçlara ve servislere **standart bir protokolle** bağlanmasını sağlayan açık bir standarttır. Bir MCP sunucusu, üzerinde çalıştığı makinede `stdio` veya HTTP üzerinden çalışır ve "tool" (araç) tanımlar; MCP destekleyen her istemci bu tool'ları keşfedip çağırabilir. LLM, tool listesini görür, göreve uygun olanı seçer, parametrelerini doldurur ve sonucu yapılandırılmış olarak geri alır.

**Kısacası: MCP server = SDK'nın ince bir adaptörü.** SDK'nın resource metotları (zaten senkron/asenkron HTTP sarmalayıcıları) MCP tool'ları olarak kaydedilir; LLM ajanları Florence verilerine erişir, analiz çalıştırır, rapor üretir, portföy yönetir — hepsi bot hesabı kimliğiyle.

### 1.2 Bu server neyi çözer

Kullanıcı vizyonu: **"bot hesaplarla kullanılabilecek AI entegrasyonları"** — LLM ajanları Florence platformuna erişip işlem yapabilsin; bot hesapları birinci sınıf vatandaş (bot olarak çalışan ajan). Bu server:

- SDK'nın **tüm** resource metodlarını (92 tool — Bölüm 2) LLM'lerin keşfedebileceği semantic tool'lara dönüştürür.
- Kimliği env/keyring'den alır; `MCP_FLORENCE_BOT` ile **bot profili** seçilebilir (Bölüm 3).
- Yapılandırılmış JSON çıktı verir; SDK hata hiyerarşisini MCP hata sözleşmesine çevirir (Bölüm 5).
- Uzun süren işlemler (rapor üretimi, export) için net bir sözleşme tanımlar (Bölüm 4).

### 1.3 Teknoloji ve protokol seçimi

| Karar | Seçim | Gerekçe |
|---|---|---|
| MCP kütüphanesi | Resmi `mcp` Python paketi (modelcontextprotocol/python-sdk), **FastMCP** API katmanı | Bakımı resmi ekibin yaptığı, tüm istemcilerle uyumlu tek standart uygulama. FastMCP, tool/schema/transport soyutlamasını tek decorator ile verir; SDK'nın pydantic v2 altyapısıyla doğal uyumlu. |
| Transport | **stdio birincil** (HTTP streamable opsiyonel, v2) | Claude Desktop / Claude Code / Cursor'un tamamı stdio'yu yerel olarak destekler; tek komut + env ile kurulur (Bölüm 6). HTTP transport sonradan eklenebilir (ayrı `florence-mcp --transport http` girişi), tasarım buna izin verir (server factory). |
| Protokol revizyonu | 2024-11-05 (stabil) | FastMCP bu revizyonu soyutlar; istemcilerin tamamı geriye dönük uyumlu. |
| Eşzamanlılık | `AsyncFlorenceClient` (asenkron) | MCP tool handler'ları async olabilir; asenkron client event loop'u bloklamadan çalışır; `export_wait` gibi poll'lar `asyncio.sleep` ile yapılır. |

### 1.4 Tasarım ilkeleri

1. **İnce adaptör:** Tool katmanı iş mantığı içermez; SDK metodu çağırır, çıktıyı formatlar, hatayı çevirir.
2. **Her tool tek iş yapar:** Tek resource metodu = tek tool (istisnalar gerekçeli, Bölüm 2.3).
3. **Gereksizlik yok:** Aynı işi yapan iki tool tanımlanmaz; isim çakışması domain önekiyle çözülür. CLI'ın "bir işin tek yolu" kuralı aynen uygulanır.
4. **CLI uyumu:** Aynı iş/eylem aynı isim — MCP tool'u, CLI komutunun düz (flat) karşılığıdır; CLI grup adı = MCP domain öneki (`account`, `market`, `portfolio`, `analysis`, `bots`, `export`, `misc`, `auth`, `economy`).
5. **Bot-first:** Kimlik çözümleme bot profiline öncelik tanır; tek seferlik bot şifresi asla loglanmaz (SDK garantisi, MCP aynen devralır).
6. **LLM için net sözleşme:** Tool açıklamaları "ne zaman kullanılır, hangi krediyi harcar, hangi uyarıyı taşır" bilgisini içerir.

---

## 2. Tool Envanteri (92 tool — tam kapsam)

### 2.1 İsimlendirme deseni

```
<domain>_<eylem>[_<nesne>]
```

- **Domain öneki zorunludur** — iki farklı `stats` metodu var (`market.stats` → `/stats/{ticker}` ve `portfolio.stats` → `/portfolios/{id}/stats`); öneksiz isimler çakışır. Önekler aynı zamanda LLM'in tool listesini taramasını kolaylaştırır (domain'e göre gruplama).
- **Fiil+isim deseni:** liste için `list_*`, tekil için `get_*`, oluşturma için `create_*`/`add_*`, güncelleme `update_*`/`rename_*`, silme `delete_*`/`remove_*`. CLI'ın okuma=isim / yazma=fiil kuralı MCP'de fiil öneki olarak korunur.
- **Domain önekleri = CLI grupları:** `auth`, `account` (SDK `UserResource` → CLI `account`), `market`, `economy`, `portfolio`, `analysis`, `bots`, `export`, `misc`. (CLI'ın `config` grubu CLI-yereldir; MCP karşılığı yoktur.)
- **İsim çakışması önleme:** `market_status` (piyasa açık/kapalı) ile `misc_health` (API sağlığı) farklı işlerdir — isimler de farklı.

**Risk işaretleri (tool açıklamasına gömülür, Bölüm 2.4):**

| İşaret | Anlam | Tool'lar |
|---|---|---|
| 🔴 `DANGER` | Kalıcı/kritik yan etki — istemci onayı önerilir | `auth_delete_account`, `auth_change_password`, `auth_change_email`, `auth_change_username` |
| 🟠 `CREDIT` | Kredi harcar — LLM açıklamada maliyeti görür | `analysis_simulate`, `analysis_generate_report` |
| 🟡 `WRITE` | Veri yazar (idempotent/geri alınabilir) | tüm `create/update/delete/add/remove/rename` tool'ları |

### 2.2 Tool tablosu (SDK metodundan birebir)

Her satır: **tool adı** · açıklama (LLM için) · girdi şeması · çıktı · karşılık gelen SDK metodu / endpoint.

#### Auth (`auth` domaini — 10 tool)

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 1 | `auth_login` | 🔴 Kullanıcı adı + şifre ile **oturum aç** (form-encoded login). Şifre LLM bağlamına girer — tercihen env/keyring ile önceden kimlik tanımlanmış olmalı. Bot girişi de aynı tool ile yapılır (CLI `fl auth login --bot` karşılığı: bot kimliği `MCP_FLORENCE_BOT` ile sunucu başlangıcında kurulur, Bölüm 3.3). Token'lar store'a yazılır (keyring/FileTokenStore). | `username: str` (zor), `password: str` (zor) | `{access_token, refresh_token, token_type}` | `AuthManager.login` / `POST /auth/login` |
| 2 | `auth_logout` | Mevcut oturumu kapat; refresh token'ı iptal et, store'u temizle. | — | `{message}` | `AuthManager.logout` / `POST /auth/logout` |
| 3 | `auth_register` | Yeni kullanıcı kaydı (public). Şifre min 10 karakter; doğrulama maili tetiklenir. | `username` (zor), `email` (zor), `password` (zor) | `{message, user_id, verification_sent}` | `AuthResource.register` / `POST /auth/register` |
| 4 | `auth_verify_email` | E-posta doğrulama token'ını onayla (public). | `token: str` (zor) | `{message, email_verified}` | `AuthResource.verify_email` / `GET /auth/verify-email` |
| 5 | `auth_resend_verification` | Doğrulama mailini yeniden gönder (public; 3/saat limitli). | `username_or_email: str` (zor) | `{message}` | `AuthResource.resend_verification` / `POST /auth/resend-verification` |
| 6 | `auth_change_password` | 🔴 Şifre değiştir; **tüm refresh token'lar iptal olur** (yeniden login gerekir). | `current_password` (zor), `new_password` (zor, min 10) | `{message}` | `AuthResource.change_password` / `PUT /auth/change-password` |
| 7 | `auth_change_email` | 🔴 E-posta değiştir; tüm refresh token'lar iptal. | `new_email` (zor), `current_password` (zor) | `{message}` | `AuthResource.change_email` / `PUT /auth/change-email` |
| 8 | `auth_change_username` | 🔴 Kullanıcı adı değiştir; tüm refresh token'lar iptal. | `new_username` (zor), `current_password` (zor) | `{message}` | `AuthResource.change_username` / `PUT /auth/change-username` |
| 9 | `auth_delete_account` | 🔴🔴 **Hesabı kalıcı olarak siler — geri alınamaz.** İstemci onayı şart (CLI: `fl auth delete --yes`). | — | `{message}` | `AuthResource.delete` / `DELETE /auth/delete` |
| 10 | `auth_status` | ⭐ Uzantı (SDK'dan doğrudan türemez): hangi kimlikle bağlı olduğunu söyler — `authenticated`, `identity_type` (`user`/`bot`/`none`), `username`, `token_source` (`env`/`keyring`/`file`). API çağrısı yapmaz; CLI `fl auth status` karşılığı. | — | kimlik özeti | `AuthManager.is_authenticated` + sunucu durumu |

> **Gereksizlik notu (auth):** `refresh` tool'u **yoktur** — CLI ile aynı karar: 401'de client otomatik (single-flight) refresh yapar; elle refresh LLM'e ek değer katmaz. `AuthResource.refresh(refresh_token)` (durumsuz) ile `AuthManager.refresh` (stateful) aynı endpoint'i çağırır; ikisi de bilinçli olarak MCP yüzeyine çıkarılmadı. Aynı şekilde `AuthResource.logout` (durumsuz) `auth_logout` (stateful) içinde birleştirildi. `fl bots login` gibi eş anlamlı komut da yoktur — bot girişi `auth_login` + `MCP_FLORENCE_BOT` modudur.

#### Account (`account` domaini — 6 tool; SDK: `UserResource`)

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 11 | `account_profile` | Profil + kredi bilgisi: username, email, user_type, email_verified, avatar, credits. Kimlik doğrulamak için kullan. | — | profil objesi | `UserResource.profile` / `GET /profile` |
| 12 | `account_update_avatar` | Avatar değiştir (`avatar-1`..`avatar-12`). | `avatar_id: str` (zor) | `{message}` | `UserResource.update_avatar` / `PUT /profile/avatar` |
| 13 | `account_get_preferences` | Kullanıcı tercihlerini oku (JSONB). | — | prefs objesi | `UserResource.get_preferences` / `GET /user/preferences` |
| 14 | `account_update_preferences` | Tercihleri güncelle; **PUT mevcut prefs ile birleştirir** (kısmi güncelleme güvenli). | `prefs: object` (zor) | güncel prefs | `UserResource.update_preferences` / `PUT /user/preferences` |
| 15 | `account_credits` | Kredi bakiyesi — kredi harcayan tool'lar öncesi/sonrası kontrol için. | — | `{credits: float}` | `UserResource.credits` / `GET /credits` |
| 16 | `account_export_data` | Kullanıcının tüm verisinin JSON dump'i: profile, favorites, reports, token_usage, simulations. | — | kapsamlı JSON | `UserResource.export_data` / `GET /user/export` |

#### Market (`market` domaini — 11 tool)

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 17 | `market_list_companies` | BIST şirket listesi (public). | `sort: "alphabetical"\|"popular"` (opt, dflt alphabetical), `offset: int` (opt, 0), `limit: int` (opt, 50, ≤500) | şirket listesi | `MarketResource.companies` / `GET /bist/companies` |
| 18 | `market_list_tickers` | BIST ticker listesi (public). | aynı parametreler | ticker listesi | `MarketResource.tickers` / `GET /bist/tickers` |
| 19 | `market_search_companies` | Şirket ara — alias destekli (public). | `query: str` (zor) | eşleşen şirketler | `MarketResource.search_companies` / `GET /companies/search` |
| 20 | `market_company_info` | Tek şirketin profili (public; yfinance). `format="json"` → yapılandırılmış profil; `format="md"` → markdown metni (CLI `fl market info --md` karşılığı; aynı kaynak, farklı serileştirme). | `ticker: str` (zor), `format: "json"\|"md"` (opt, "json") | profil objesi veya markdown metin | `MarketResource.company_info` / `GET /companies/info/{ticker}` (+ `/md`) |
| 21 | `market_companies_summary` | Özet tablo: gainers/losers/price_high/volume/market_cap sıralamaları, virgüllü ticker filtresi. | `limit` (opt 50), `offset` (opt 0), `sort` (opt "popular"), `tickers` (opt, CSV) | özet satırları | `MarketResource.companies_summary` / `GET /companies/summary` |
| 22 | `market_news` | 🟡 Hisse haberleri — **news feature'ı gerekir, 10/dk rate limit** (JWT). | `ticker` (zor), `amount: int` (opt 10, 1-50) | haber listesi | `MarketResource.news` / `GET /news/{ticker}` |
| 23 | `market_price_current` | Anlık fiyat/quote (public). `is_stale` ve `change_pct: null` semantiğine dikkat (piyasa açıkken intraday veri yoksa). | `ticker` (zor), `interval: "5m"\|"30m"\|"1h"\|"1d"` (opt, 5m) | quote objesi | `MarketResource.current_price` / `GET /price/current` |
| 24 | `market_price_history` | Fiyat geçmişi (public; 60s cache). `period`/`interval` kısıtları backend'de (5m..3mo interval). | `ticker` (zor), `period` (opt "1mo", 1d..max), `interval` (opt "1d", 5m..3mo) | OHLCV serisi | `MarketResource.price_history` / `GET /price/history/{ticker}` |
| 25 | `market_status` | Piyasa açık mı: `{open, next_open_at, holiday}` (60s cache). İşlem öncesi kontrol için. | — | durum objesi | `MarketResource.market_status` / `GET /market/status` |
| 26 | `market_stats_top` | Aktiviteye göre popüler ticker'lar (public). | `limit: int` (opt 50) | ticker listesi | `MarketResource.stats_top` / `GET /stats/top` |
| 27 | `market_stats` | Tek ticker'ın sayaçları (public). **`portfolio_stats` ile karıştırma.** | `ticker: str` (zor) | sayaç objesi | `MarketResource.stats` / `GET /stats/{ticker}` |

#### Economy (`economy` domaini — 6 tool)

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 28 | `economy_gold_prices` | Altın fiyatları (16 kalem; public). ⚠️ Değerler STRING + Türk virgüllü ondalık (`"40,25"`) — sayısal işlem öncesi `,`→`.` dönüşümü gerekir. | — | altın fiyat listesi | `EconomyResource.gold_prices` / `GET /economy/gold-prices` |
| 29 | `economy_silver_price` | Gümüş fiyatı. | — | `{"gumus": ...}` | `EconomyResource.silver_price` / `GET /economy/silver-price` |
| 30 | `economy_platinum_price` | Gram platin fiyatı. | — | `{"gram-platin": ...}` | `EconomyResource.platinum_price` / `GET /economy/gram-platinum-price` |
| 31 | `economy_palladium_price` | Gram paladyum fiyatı. | — | `{"gram-paladyum": ...}` | `EconomyResource.palladium_price` / `GET /economy/gram-palladium-price` |
| 32 | `economy_currency` | Döviz kurları; `symbols` filtresi virgüllü (`USD,EUR`). | `symbols: str` (opt) | kur listesi | `EconomyResource.currency` / `GET /economy/currency` |
| 33 | `economy_macroeconomy` | FRED makro serileri (14 seri, 24h cache). | — | makro seriler | `EconomyResource.macroeconomy` / `GET /macroeconomy` |

#### Portfolio (`portfolio` domaini — 24 tool)

Favoriler (3):

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 34 | `portfolio_add_favorite` | 🟡 Favorilere ekle (idempotent). | `ticker` (zor) | `{message}` | `PortfolioResource.add_favorite` / `POST /favorites/{ticker}` |
| 35 | `portfolio_remove_favorite` | 🟡 Favorilerden çıkar. | `ticker` (zor) | `{message}` | `PortfolioResource.remove_favorite` / `DELETE /favorites/{ticker}` |
| 36 | `portfolio_list_favorites` | Favori listesi. | — | liste | `PortfolioResource.favorites` / `GET /favorites` |

Portföyler CRUD (6):

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 37 | `portfolio_create` | 🟡 Sanal portföy oluştur. `initial_balance > 0`. | `name` (zor), `initial_balance: float` (zor, >0) | `{metadata, transactions}` | `PortfolioResource.create_portfolio` / `POST /portfolios` |
| 38 | `portfolio_list` | Portföy listesi. | — | liste | `PortfolioResource.list_portfolios` / `GET /portfolios` |
| 39 | `portfolio_get` | Tek portföy. | `portfolio_id` (zor) | portföy objesi | `PortfolioResource.get_portfolio` / `GET /portfolios/{id}` |
| 40 | `portfolio_rename` | 🟡 Yeniden adlandır. | `portfolio_id` (zor), `name` (zor) | `{message}` | `PortfolioResource.rename_portfolio` / `PUT /portfolios/{id}` |
| 41 | `portfolio_delete` | 🟡 Portföyü sil — **işlemler dahil kalıcıdır.** | `portfolio_id` (zor) | `{message}` | `PortfolioResource.delete_portfolio` / `DELETE /portfolios/{id}` |
| 42 | `portfolio_duplicate` | 🟡 İşlemleriyle kopyala. | `portfolio_id` (zor), `name` (zor) | yeni portföy | `PortfolioResource.duplicate_portfolio` / `POST /portfolios/{id}/duplicate` |

İşlemler (4):

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 43 | `portfolio_list_transactions` | İşlem listesi; filtreler: `ticker`, `tx_type` (BUY/SELL), `start`/`end` ISO. | `portfolio_id` (zor), `ticker` (opt), `tx_type` (opt), `start` (opt), `end` (opt) | işlem listesi | `PortfolioResource.get_transactions` / `GET /portfolios/{id}/transactions` |
| 44 | `portfolio_add_transaction` | 🟡 İşlem ekle — **piyasa açık olmalı** (kapalıysa 400 "Market is closed"), fiyat piyasadan otomatik alınır, komisyon işler. | `portfolio_id` (zor), `ticker` (zor), `type: "BUY"\|"SELL"` (zor), `quantity: float` (zor, >0) | işlem kaydı | `PortfolioResource.add_transaction` / `POST /portfolios/{id}/transactions` |
| 45 | `portfolio_update_transaction` | 🟡 İşlemi güncelle (manuel fiyat/miktar; en az biri). Piyasa-açık kontrolünden muaftır. | `portfolio_id` (zor), `tx_id` (zor), `price` (opt, >0), `quantity` (opt, >0) | güncel işlem | `PortfolioResource.update_transaction` / `PUT /portfolios/{id}/transactions/{tx_id}` |
| 46 | `portfolio_undo_transaction` | 🟡 Son işlemi geri al. | `portfolio_id` (zor) | `{message}` | `PortfolioResource.undo_transaction` / `DELETE /portfolios/{id}/transactions/undo` |

Analizler (11):

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 47 | `portfolio_valuation` | Değerleme: total_value, pnl, varlık kırılımı. | `portfolio_id` (zor) | değerleme objesi | `PortfolioResource.valuation` / `GET .../valuation` |
| 48 | `portfolio_diversification` | Çeşitlendirme (stock/forex/metal dağılımı). | `portfolio_id` (zor) | dağılım objesi | `PortfolioResource.diversification` / `GET .../diversification` |
| 49 | `portfolio_performers` | En iyi/en kötü hisseler. | `portfolio_id` (zor), `top_n: int` (opt 5) | performans listesi | `PortfolioResource.performers` / `GET .../performers` |
| 50 | `portfolio_history` | Değer geçmişi. `period`: 1w/1mo/3mo/6mo/1y/max. | `portfolio_id` (zor), `period` (opt "1mo") | zaman serisi | `PortfolioResource.history` / `GET .../history` |
| 51 | `portfolio_returns` | Getiri (abs/total/CAGR). | `portfolio_id` (zor), `period` (opt "1mo") | getiri objesi | `PortfolioResource.returns` / `GET .../returns` |
| 52 | `portfolio_risk` | Risk: volatility, max_drawdown, sharpe. | `portfolio_id` (zor), `period` (opt "1y") | risk objesi | `PortfolioResource.risk` / `GET .../risk` |
| 53 | `portfolio_benchmark` | XU100 karşılaştırma (default ticker XU100). | `portfolio_id` (zor), `ticker` (opt "XU100") | karşılaştırma | `PortfolioResource.benchmark` / `GET .../benchmark` |
| 54 | `portfolio_performance` | Verimlilik skoru. | `portfolio_id` (zor) | skor objesi | `PortfolioResource.performance` / `GET .../performance` |
| 55 | `portfolio_stats` | İşlem istatistikleri. **`market_stats` ile karıştırma.** | `portfolio_id` (zor) | istatistik objesi | `PortfolioResource.stats` / `GET .../stats` |
| 56 | `portfolio_snapshot` | Birleşik özet (hızlı genel bakış için). | `portfolio_id` (zor) | özet objesi | `PortfolioResource.snapshot` / `GET .../snapshot` |
| 57 | `portfolio_export_csv` | Portföy işlemlerini CSV olarak indir — **ham CSV metni döner** (JSON değil). | `portfolio_id` (zor) | CSV metni | `PortfolioResource.export_csv` / `GET .../export/csv` |

#### Analysis (`analysis` domaini — 13 tool)

Simülasyonlar (5):

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 58 | `analysis_per_day_cost` | Günlük simülasyon maliyeti (0.005 kredi/gün). Maliyet hesaplamak için önce bunu oku. | — | `{per_day_cost}` | `AnalysisResource.per_day_cost` / `GET /simulations/per-day-cost` |
| 59 | `analysis_estimate_cost` | Simülasyon maliyet tahmini. | `ticker` (zor), `days: int` (zor, 1..370) | `{cost, ...}` | `AnalysisResource.estimate_cost` / `GET /simulations/estimate-cost/{ticker}` |
| 60 | `analysis_list_simulations` | Simülasyon geçmişi (limit ≤ 100). | `limit` (opt 20), `offset` (opt 0) | kayıt listesi | `AnalysisResource.simulation_history` / `GET /simulations/history` |
| 61 | `analysis_get_simulation` | Tek simülasyon detayı (sonuç JSONB dahil). | `sim_id: int` (zor) | simülasyon kaydı | `AnalysisResource.simulation_detail` / `GET /simulations/history/{sim_id}` |
| 62 | `analysis_simulate` | 🟠💰 **Monte Carlo simülasyonu çalıştırır — maliyet = gün × 0.005 kredi.** Job-slot 600s. `days` 1..370, `bounds` "0.05", `target` opsiyonel. | `ticker` (zor), `days: int` (zor), `bounds: str` (opt "0.05"), `target: str` (opt) | `{prob_above, prob_below, confidence, direction, simulation_id, credits_spend, remaining_credits, ...}` | `AnalysisResource.simulate` / `GET /simulations/{ticker}` |

Raporlar (6):

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 63 | `analysis_generate_report` | 🟠💰 **Rapor üretir — kredi harcar** (quick ~0.25, deep daha fazla; tahsilat token bazlı). ⏳ **90 saniyeye kadar sürebilir** (job-slot 900s) — istemci timeout'una dikkat (Bölüm 4). | `ticker` (zor), `type: "quick_report"\|"deep_report"` (zor), `purpose: str` (opt — kullanıcının sorusu) | `{success, report_id, credits_spend, remaining_credits, report(md), sentiments, ...}` | `AnalysisResource.generate_report` / `POST /reports/generate` |
| 64 | `analysis_report_info` | Rapor maliyetleri + endpoint dokümantasyonu. | — | maliyet/doküman objesi | `AnalysisResource.report_info` / `GET /reports/info` |
| 65 | `analysis_list_reports` | Rapor geçmişi (sort/order allowlist'li). | `sort` (opt "created_at"), `order` (opt "desc") | kayıt listesi | `AnalysisResource.report_history` / `GET /reports/history` |
| 66 | `analysis_search_reports` | Raporda ara (`q` başlık/içerik ILIKE). | `q` (zor), `sort` (opt), `order` (opt), `limit` (opt 20), `offset` (opt 0) | eşleşen raporlar | `AnalysisResource.search_reports` / `GET /reports/search` |
| 67 | `analysis_get_report` | Tek rapor (owner-only; markdown içerik). | `report_id: int` (zor) | rapor objesi (md içerik) | `AnalysisResource.get_report` / `GET /reports/{report_id}` |
| 68 | `analysis_download_report` | Raporu indir: `ftype` md/docx/pdf. **docx/pdf binary'dir** — `dest_path` verilirse sunucuya yazılır ve yol döner; verilmezse md metin, binary'ler base64 döner (Bölüm 4/5). | `report_id: int` (zor), `ftype: "md"\|"docx"\|"pdf"` (zor), `dest_path: str` (opt) | yol+meta veya içerik | `AnalysisResource.download_report` / `POST /reports/download` |

Danışman (2):

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 69 | `analysis_fit_stocks` | Profil kriterlerine göre hisse eşleştir (advisor feature'ı gerekir). | `horizon: "short"\|"medium"\|"long"` (opt "long"), `profitability` (opt "high"), `risk_tolerance` (opt "medium"), `limit: int` (opt 5, 1-100) | benzer hisseler | `AnalysisResource.fit_stocks` / `POST /stocks/fit` |
| 70 | `analysis_portfolio_profile` | Portföye benzer hisseler (Euclidean; ticker'lar büyük harfe çevrilir). | `tickers: list[str]` (zor, 1-50), `limit` (opt 5, 1-50) | benzer hisseler | `AnalysisResource.portfolio_profile` / `POST /portfolio/profile` |

#### Bots (`bots` domaini — 3 tool)

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 71 | `bots_create` | 🟡 Bot hesabı oluştur (max 5/kullanıcı). **Yanıttaki `password` TEK SEFERLİKTİR** — SDK onu otomatik keyring'e yazar; MCP çıktısında maskelenir (Bölüm 3.4). Bot owner'ın kredisinden harcar. | `username` (zor, 3-255), `password` (opt, min 10) | `{id, username, email, password}` (password maskeli) | `BotsResource.create` / `POST /bots` |
| 72 | `bots_list` | Kendi botlarını listele. | — | `{bots: [...]}` | `BotsResource.list` / `GET /bots` |
| 73 | `bots_delete` | 🟡 Botu sil (owner-only; kalıcı; store'daki şifresi de temizlenir). | `bot_id: int` (zor) | `{message}` | `BotsResource.delete` / `DELETE /bots/{bot_id}` |

> **`bot_session` bir tool değil, kimlik modudur:** `AuthManager.bot_session(username)` context manager'ı (girişte login, çıkışta logout) MCP'de **sunucu başlangıç modu** olarak kullanılır — `MCP_FLORENCE_BOT=bot-1` ile server ayağa kalkarken bot olarak login olur (Bölüm 3.3). CLI'daki gibi ayrı bir `bots login` tool'u **yoktur** (eş anlamlılık yasağı); bot girişi `auth_login` ile veya sunucu başlangıcında otomatik yapılır.

#### Export (`export` domaini — 5 tool)

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 74 | `export_create` | Export siparişi ver (202, idempotent: aynı user+year+format aktif kaydı varsa mevcut id döner; 3/saat limit). | `year: int` (zor), `format: "csv"\|"json"` (opt "csv") | `{export_id, status}` | `ExportResource.create_export` / `POST /data/export` |
| 75 | `export_status` | Tek export kaydı durumu (owner-only). Status: queued/processing/ready/sent/error. | `export_id: int` (zor) | kayıt objesi | `ExportResource.get_export` / `GET /data/export/{id}` |
| 76 | `export_list` | Export kayıtları listesi. | — | liste | `ExportResource.list_exports` / `GET /data/export` |
| 77 | `export_wait` | Export ready/sent olana kadar **poll eder** (senkron, bloklar). `timeout` aşılırsa `TimeoutError` → tool hatası (Bölüm 4). LLM kendi poll döngüsünü `export_status` ile de yazabilir. | `export_id` (zor), `poll_interval: float` (opt 3.0), `timeout: float` (opt 300.0) | terminal kayıt | `ExportResource.wait_export` / poll `GET /data/export/{id}` |
| 78 | `export_download` | **Public** token ile indir (auth gerekmez; gzip dosya). `token_or_url` ham token veya download_url olabilir. `dest_path` verilirse sunucuya yazılır, yol döner; yoksa base64. | `token_or_url` (zor), `dest_path` (opt) | yol+meta veya içerik | `ExportResource.download` / `GET /data/export/download/{token}` |

#### Misc (`misc` domaini — 14 tool)

| # | Tool | Açıklama (LLM için) | Girdi | Çıktı | SDK / Endpoint |
|---|---|---|---|---|---|
| 79 | `misc_ipos_upcoming` | Yaklaşan halka arzlar (public). | `after: str` (opt, ISO) | IPO listesi | `MiscResource.ipos_upcoming` / `GET /ipos/upcoming` |
| 80 | `misc_ipos_draft` | Taslak halka arzlar (public). | `after` (opt) | IPO listesi | `MiscResource.ipos_draft` / `GET /ipos/draft` |
| 81 | `misc_ipos_active` | Aktif halka arzlar (public). | `after` (opt) | IPO listesi | `MiscResource.ipos_active` / `GET /ipos/active` |
| 82 | `misc_ipo_detail` | Tek halka arz detayı (yoksa 404). | `slug: str` (zor) | IPO objesi | `MiscResource.ipo_detail` / `GET /ipos/{slug}` |
| 83 | `misc_legal` | Tek politika metni: terms/privacy_policy/cookie_policy/disclaimer. | `policy` (zor), `lang: "tr"\|"en"` (opt "tr") | metin | `MiscResource.legal` / `GET /legal` |
| 84 | `misc_legal_all` | Tüm politikalar. | `lang` (opt "tr") | metin seti | `MiscResource.legal_all` / `GET /legal/all` |
| 85 | `misc_about` | Platform hakkında metni. | `lang` (opt "tr") | metin | `MiscResource.about` / `GET /about` |
| 86 | `misc_version` | API sürüm bilgisi. | — | `{version}` | `MiscResource.version` / `GET /version` |
| 87 | `misc_contact` | İletişim bilgileri. | — | bilgi objesi | `MiscResource.contact` / `GET /contact` |
| 88 | `misc_contributors` | Katkıda bulunanlar. | — | liste | `MiscResource.contributors` / `GET /contributors` |
| 89 | `misc_maintenance` | Devre dışı özellik listesi — bir tool 503 dönerse önce bunu kontrol et. | — | kapalı özellikler | `MiscResource.maintenance` / `GET /maintenance` |
| 90 | `misc_health` | API sağlık kontrolü (public; `{"status":"ok"}`). **`market_status` ile karıştırma** (piyasa açık/kapalı ≠ API sağlığı). | — | `{status}` | `MiscResource.health` / `GET /health` |
| 91 | `misc_announcements` | Son 7 günün duyuruları (JWT). | — | duyuru listesi | `MiscResource.announcements` / `GET /announcements` |
| 92 | `misc_announcement` | Tek duyuru (JWT). | `announcement_id: int` (zor) | duyuru objesi | `MiscResource.announcement` / `GET /announcements/{id}` |

### 2.3 Bilinçli dışarıda bırakılanlar ve birleştirmeler

| Madde | Karar | Gerekçe |
|---|---|---|
| `MiscResource.root` (`GET /`) | **Tool YOK** | Yanıt boş objedir (`{}`); LLM'e sıfır bilgi değeri. `misc_health` aynı ihtiyacı (sunucu erişilebilir mi) karşılar — CLI ile aynı karar (`fl misc health` kökü de kapsar). |
| `AuthManager.refresh` / `AuthResource.refresh` (`POST /auth/refresh`) | **Tool YOK** | CLI kararıyla birebir: refresh 401'de client'ta otomatik (single-flight) yapılır; elle refresh LLM'e ek değer katmaz, gereksizliktir. |
| `AuthResource.logout` (durumsuz) | `auth_logout` içinde birleştirildi | Aynı endpoint; stateful varyant store'u da temizler. |
| `AuthManager.create_bot` ↔ `BotsResource.create` | Tek tool: `bots_create` | Aynı endpoint (`POST /bots`); `create_bot` kısayolu keyring kaydını da yapar — bu davranış MCP'de korunur. |
| `MarketResource.company_info_md` | `market_company_info(format="md")` içinde birleştirildi | CLI `fl market info --md` ile aynı karar: aynı kaynak, farklı serileştirme (izin verilen tek istisna). Tek tool, `format` parametresi. |
| Announcements yazma uçları (`POST /announcements`, `PUT/DELETE /announcements/{id}`, `POST /announcements/read`) | **Tool YOK** | SDK'da bilinçli olarak sarılmamış (admin/yazma tarafı; `misc_res.py` TODO). MCP, SDK'nın kapsamını aşmaz. |
| `POST /analytics/event`, `GET /meta/avatars`, `GET /data/daily/{year}`, admin app (`X-Admin-Token`) | **Tool YOK** | SDK kapsam dışı (fire-and-forget izleme, statik varlık listesi, 410 Gone deprecated, ayrı admin uygulaması). |
| CLI `config` grubu (`fl config show/set`) | **MCP karşılığı YOK** | CLI-yerel ayar (config.toml); MCP yapılandırması env ile yapılır (Bölüm 3.2). |

### 2.4 Onay/uyarı semantiği (MCP'de nasıl yapılır)

MCP protokolünde tool çağrısı öncesi zorunlu onay mekanizması yoktur; onay **istemci tarafında** yapılır (Claude Desktop/Claude Code tool kullanımını kullanıcıya gösterir/onaylatır). Server tarafında yapılabilecekler:

1. **Tool açıklamasına uyarı gömme:** 🔴/🟠 işaretleri ve "kredi harcar", "kalıcıdır", "geri alınamaz" ifadeleri açıklamanın **ilk satırına** yazılır — LLM tool seçerken bunu görür ve kullanıcıya sorar; istemci de açıklamayı onay ekranında gösterir.
2. **Ekstra zorunlu parametre (savunma hattı):** Yıkıcı tool'lara `confirm: bool` (zorunlu) parametresi eklenir; LLM bunu `true` yapmadan çağrı reddedilir. Bu, LLM'in kazara çağırmasını ve istemcinin gözden kaçırmasını engeller. (CLI'daki onay promptu + `--yes` deseninin MCP karşılığı.)
3. **Kredi maliyeti ön-bilgisi:** `analysis_simulate`/`analysis_generate_report` için açıklamada maliyet formülü ve "önce `account_credits` / `analysis_estimate_cost` / `analysis_per_day_cost` ile bakiyeyi kontrol et" yönlendirmesi.
4. **Maskeleme:** `bots_create` yanıtındaki tek seferlik şifre, çıktı formatlama katmanında (`format.py`) `"***"` ile maskelenir ve ayrıca keyring'e yazıldığı belirtilir — şifre LLM bağlamına düşmez. (SDK zaten loglamaz; MCP çıktısı da aynı disiplini uygular; CLI `--show-password` karşılığı MCP'de yoktur — güvenlik.)

### 2.5 Kapsam doğrulama tablosu (openapi.json → tool)

89 path'in tamamı aşağıda eşlenmiştir. `POST /auth/login`, `GET /health` ve `GET /` SDK'da resource dışında ama client'ta sarılmıştır (AuthManager / MiscResource) — eşleme bunu gösterir. **Temel ilke CLI ile aynı:** "her path en az bir tool'la erişilebilir; SDK'da bilinçli kapsam dışı bırakılmış path'ler MCP'ye de yansımaz."

| Path (openapi.json) | Metod(lar) | Tool |
|---|---|---|
| `/` | GET | ❌ hariç (gerekçe: boş obje; `misc_health` yeterli) |
| `/health` | GET | `misc_health` |
| `/api/v1/about` | GET | `misc_about` |
| `/api/v1/analytics/event` | POST | ❌ SDK kapsam dışı |
| `/api/v1/announcements` | GET / POST | `misc_announcements` / ❌ yazma hariç |
| `/api/v1/announcements/read` | POST | ❌ SDK kapsam dışı |
| `/api/v1/announcements/{announcement_id}` | GET / PUT / DELETE | `misc_announcement` / ❌ yazma hariç |
| `/api/v1/auth/change-email` | PUT | `auth_change_email` |
| `/api/v1/auth/change-password` | PUT | `auth_change_password` |
| `/api/v1/auth/change-username` | PUT | `auth_change_username` |
| `/api/v1/auth/delete` | DELETE | `auth_delete_account` |
| `/api/v1/auth/login` | POST | `auth_login` |
| `/api/v1/auth/logout` | POST | `auth_logout` |
| `/api/v1/auth/refresh` | POST | (otomatik — tool yok, client 401'de yapar) |
| `/api/v1/auth/register` | POST | `auth_register` |
| `/api/v1/auth/resend-verification` | POST | `auth_resend_verification` |
| `/api/v1/auth/verify-email` | GET | `auth_verify_email` |
| `/api/v1/bist/companies` | GET | `market_list_companies` |
| `/api/v1/bist/tickers` | GET | `market_list_tickers` |
| `/api/v1/bots` | POST / GET | `bots_create` / `bots_list` |
| `/api/v1/bots/{bot_id}` | DELETE | `bots_delete` |
| `/api/v1/companies/info/{ticker}` | GET | `market_company_info` (format="json") |
| `/api/v1/companies/info/{ticker}/md` | GET | `market_company_info` (format="md") |
| `/api/v1/companies/search` | GET | `market_search_companies` |
| `/api/v1/companies/summary` | GET | `market_companies_summary` |
| `/api/v1/contact` | GET | `misc_contact` |
| `/api/v1/contributors` | GET | `misc_contributors` |
| `/api/v1/credits` | GET | `account_credits` |
| `/api/v1/data/daily/{year}` | GET | ❌ 410 Gone (deprecated) |
| `/api/v1/data/export` | POST / GET | `export_create` / `export_list` |
| `/api/v1/data/export/download/{token}` | GET | `export_download` |
| `/api/v1/data/export/{export_id}` | GET | `export_status` |
| `/api/v1/economy/currency` | GET | `economy_currency` |
| `/api/v1/economy/gold-prices` | GET | `economy_gold_prices` |
| `/api/v1/economy/gram-palladium-price` | GET | `economy_palladium_price` |
| `/api/v1/economy/gram-platinum-price` | GET | `economy_platinum_price` |
| `/api/v1/economy/silver-price` | GET | `economy_silver_price` |
| `/api/v1/favorites` | GET | `portfolio_list_favorites` |
| `/api/v1/favorites/{ticker}` | POST / DELETE | `portfolio_add_favorite` / `portfolio_remove_favorite` |
| `/api/v1/ipos/active` | GET | `misc_ipos_active` |
| `/api/v1/ipos/draft` | GET | `misc_ipos_draft` |
| `/api/v1/ipos/upcoming` | GET | `misc_ipos_upcoming` |
| `/api/v1/ipos/{slug}` | GET | `misc_ipo_detail` |
| `/api/v1/legal` | GET | `misc_legal` |
| `/api/v1/legal/all` | GET | `misc_legal_all` |
| `/api/v1/macroeconomy` | GET | `economy_macroeconomy` |
| `/api/v1/maintenance` | GET | `misc_maintenance` |
| `/api/v1/market/status` | GET | `market_status` |
| `/api/v1/meta/avatars` | GET | ❌ statik varlık listesi |
| `/api/v1/news/{ticker}` | GET | `market_news` |
| `/api/v1/portfolio/profile` | POST | `analysis_portfolio_profile` |
| `/api/v1/portfolios` | POST / GET | `portfolio_create` / `portfolio_list` |
| `/api/v1/portfolios/{portfolio_id}` | GET / PUT / DELETE | `portfolio_get` / `portfolio_rename` / `portfolio_delete` |
| `/api/v1/portfolios/{portfolio_id}/benchmark` | GET | `portfolio_benchmark` |
| `/api/v1/portfolios/{portfolio_id}/diversification` | GET | `portfolio_diversification` |
| `/api/v1/portfolios/{portfolio_id}/duplicate` | POST | `portfolio_duplicate` |
| `/api/v1/portfolios/{portfolio_id}/export/csv` | GET | `portfolio_export_csv` |
| `/api/v1/portfolios/{portfolio_id}/history` | GET | `portfolio_history` |
| `/api/v1/portfolios/{portfolio_id}/performance` | GET | `portfolio_performance` |
| `/api/v1/portfolios/{portfolio_id}/performers` | GET | `portfolio_performers` |
| `/api/v1/portfolios/{portfolio_id}/returns` | GET | `portfolio_returns` |
| `/api/v1/portfolios/{portfolio_id}/risk` | GET | `portfolio_risk` |
| `/api/v1/portfolios/{portfolio_id}/snapshot` | GET | `portfolio_snapshot` |
| `/api/v1/portfolios/{portfolio_id}/stats` | GET | `portfolio_stats` |
| `/api/v1/portfolios/{portfolio_id}/transactions` | GET / POST | `portfolio_list_transactions` / `portfolio_add_transaction` |
| `/api/v1/portfolios/{portfolio_id}/transactions/undo` | DELETE | `portfolio_undo_transaction` |
| `/api/v1/portfolios/{portfolio_id}/transactions/{tx_id}` | PUT | `portfolio_update_transaction` |
| `/api/v1/portfolios/{portfolio_id}/valuation` | GET | `portfolio_valuation` |
| `/api/v1/price/current` | GET | `market_price_current` |
| `/api/v1/price/history/{ticker}` | GET | `market_price_history` |
| `/api/v1/profile` | GET | `account_profile` |
| `/api/v1/profile/avatar` | PUT | `account_update_avatar` |
| `/api/v1/reports/download` | POST | `analysis_download_report` |
| `/api/v1/reports/generate` | POST | `analysis_generate_report` |
| `/api/v1/reports/history` | GET | `analysis_list_reports` |
| `/api/v1/reports/info` | GET | `analysis_report_info` |
| `/api/v1/reports/search` | GET | `analysis_search_reports` |
| `/api/v1/reports/{report_id}` | GET | `analysis_get_report` |
| `/api/v1/simulations/estimate-cost/{ticker}` | GET | `analysis_estimate_cost` |
| `/api/v1/simulations/history` | GET | `analysis_list_simulations` |
| `/api/v1/simulations/history/{sim_id}` | GET | `analysis_get_simulation` |
| `/api/v1/simulations/per-day-cost` | GET | `analysis_per_day_cost` |
| `/api/v1/simulations/{ticker}` | GET | `analysis_simulate` |
| `/api/v1/stats/top` | GET | `market_stats_top` |
| `/api/v1/stats/{ticker}` | GET | `market_stats` |
| `/api/v1/stocks/fit` | POST | `analysis_fit_stocks` |
| `/api/v1/user/export` | GET | `account_export_data` |
| `/api/v1/user/preferences` | GET / PUT | `account_get_preferences` / `account_update_preferences` |
| `/api/v1/version` | GET | `misc_version` |

**Özet:** 89 path → 88'i kapsanır (bazıları birden çok metotla), hariç tutulan 8 uç SDK kapsam dışıdır (gerekçeleri yukarıda). **Tool sayısı: 92** (10 auth + 6 account + 11 market + 6 economy + 24 portfolio + 13 analysis + 3 bots + 5 export + 14 misc).

### 2.6 CLI ↔ MCP eşleme tablosu (uyum doğrulaması)

CLI tasarımı (`cli-design.md`) yayınlandıktan sonra uygulanan hizalama geçişi sonrası, her CLI grubunun komut sayısı MCP tool sayısıyla **birebir eşittir** (CLI `config` grubu hariç — CLI-yereldir). Örnek eşlemeler:

| CLI komutu | MCP tool'u | Not |
|---|---|---|
| `fl auth login` / `fl auth login --bot` | `auth_login` | `--bot` → MCP'de `MCP_FLORENCE_BOT` sunucu modu (Bölüm 3.3) |
| `fl auth status` | `auth_status` | aynı yerel kimlik özeti |
| `fl auth delete --yes` | `auth_delete_account` | onay: CLI prompt/`--yes`, MCP `confirm` param + istemci onayı |
| `fl account profile` / `credits` / `export` | `account_profile` / `account_credits` / `account_export_data` | SDK `UserResource`; grup adı CLI'dan (`account`) |
| `fl market price` / `history` / `info --md` | `market_price_current` / `market_price_history` / `market_company_info(format="md")` | `--md` bayrağı → `format` parametresi |
| `fl economy gold` / `macro` | `economy_gold_prices` / `economy_macroeconomy` | aynı iş |
| `fl portfolio favorite add` / `tx add` / `valuation` | `portfolio_add_favorite` / `portfolio_add_transaction` / `portfolio_valuation` | alt varlık (favorite/tx) → fiil+nesne adı |
| `fl analysis report generate` / `simulation run` / `fit` | `analysis_generate_report` / `analysis_simulate` / `analysis_fit_stocks` | alt varlık+fiil → fiil önce gelecek şekilde düzleştirildi |
| `fl bots create` / `list` / `delete` | `bots_create` / `bots_list` / `bots_delete` | birebir |
| `fl export status` / `download --wait` | `export_status` / `export_wait` + `export_download` | CLI `download --wait` kompoziti MCP'de iki ayrı tool (LLM akışı kendisi yönetir) |
| `fl misc ipo upcoming` / `legal-all` / `announcement list` | `misc_ipos_upcoming` / `misc_legal_all` / `misc_announcements` | aynı iş |

---

## 3. Auth ve Kimlik Tasarımı

### 3.1 Kimlik çözümleme önceliği (sunucu başlangıcında, tek sefer)

```
1. MCP_FLORENCE_BOT=<bot_username>  →  bot profili: keyring'deki bot şifresiyle login_as_bot
                                      (şifre yoksa net hata: "bots_create ile oluşturun veya MCP_FLORENCE_BOT_PASSWORD verin")
2. FLORENCE_TOKEN=<jwt>              →  salt-okunur access token override (SDK'nın mevcut davranışı, sıfır kod)
3. keyring / FileTokenStore          →  kalıcı oturum (Faz 3 "Kalıcı auth": KeyringTokenStore + Fernet'li
                                      FileTokenStore fallback; MCP bunu aynen devralır)
4. Hiçbiri yoksa                     →  kimliksiz mod: public tool'lar (market/economy/misc okuma) çalışır;
                                      JWT isteyen tool çağrısı net hata döner (Bölüm 5)
```

- `FLORENCE_API_URL` her durumda saygı görür (dev ortamı).
- `MCP_FLORENCE_BOT` + `FLORENCE_TOKEN` birlikte verilirse: **bot profili kazanır** (bot, env token'dan daha spesifik bir kimliktir). Bu kural raporda açıkça yazılır.
- Çoklu kimlik (örn. hem kullanıcı hem bot aynı anda) v1'de **desteklenmez** — gerekçe: tek stdio process = tek `AsyncFlorenceClient` = tek token store. Çoklu kimlik ihtiyacı **istemci tarafında** çözülür: Claude Desktop/Cursor'da aynı sunucu için farklı env'li ayrı MCP blokları tanımlanır (Bölüm 6.4). Bu, MCP'nin doğal modeliyle birebir örtüşür ve server'a karmaşıklık eklemez. (Açık karar noktası #2.)

### 3.2 Token kaynağı: env mi, keyring mi, config mi?

| Kaynak | Öncelik | Ne zaman |
|---|---|---|
| `MCP_FLORENCE_BOT` + keyring bot şifresi | 1 | "Bot olarak çalışan ajan" senaryosu — asıl kullanım |
| `FLORENCE_TOKEN` | 2 | CI/geçici token, keyring'in olmadığı headless ortam |
| `KeyringTokenStore` (servis `florence-sdk`) | 3 | Makinede `fl login` yapılmış, oturum kalıcı |
| `FileTokenStore` (Fernet şifreli, chmod 600) | 4 | keyring yoksa (plan Faz 3 T3.2b — sessiz memory fallback YOK) |
| Config dosyası (`~/.config/florence/config.toml`) | — | Yalnızca `api_url` gibi **kimliksiz** ayarlar için; token config'e **yazılmaz** (CLI kuralıyla aynı) |

### 3.3 Bot profili (`MCP_FLORENCE_BOT`) semantiği

`MCP_FLORENCE_BOT=bot-1` ile başlayan server:

1. Başlangıçta `AuthManager.login_as_bot("bot-1")` çağırır (şifre keyring'den; yoksa `MCP_FLORENCE_BOT_PASSWORD` env'i kabul edilir — geçici/CI kullanımı).
2. Token'lar store'a yazılır; 401'de client otomatik single-flight refresh yapar → **bot oturumu süreç boyunca canlı kalır**.
3. `auth_status` tool'u `identity_type: "bot"` döner — LLM, bot kimliğiyle çalıştığını bilir.
4. Kapatışta logout: MCP server'ın shutdown hook'unda `auth_logout()` çağrılır (refresh token iptali). Shutdown ani olursa token store'da kalan refresh token 30 gün TTL'iyle backend'de yaşlanır — güvenlik riski değil, kabul edilir.
5. Bot, owner'ın kredisinden harcar — `account_credits` tool'u bot modunda da owner bakiyesini gösterir (backend `_resolve_owner` davranışı; SDK olduğu gibi aktarır).

**Bot-first disiplini:** `bots_create` yanıtındaki tek seferlik şifre format katmanında maskelenir (Bölüm 2.4/5); şifreler/loglar asla token içermez (SDK garantisi MCP tarafında da korunur).

### 3.4 Token yoksa ne olur (net hata sözleşmesi)

- **Başlangıçta kimlik yoksa server YİNE başlar** (public tool'lar kullanılabilir) — ayrı bir "kimliksiz mod" gerekli çünkü market/economy/legal verisi public.
- JWT isteyen bir tool kimliksiz çağrılırsa: SDK `AuthError(401, ...)` fırlatır → MCP tarafında açıklayıcı hata (Bölüm 5), ör.:
  ```
  Kimlik gerekli: FLORENCE_TOKEN ayarlayın, keyring'de oturum açın (fl login)
  veya MCP_FLORENCE_BOT=<bot> ile bot profili seçin.
  ```
- Bot profili seçilmiş ama şifre bulunamazsa (keyring boş): `AuthError(401, "no_bot_password", ...)` → aynı kanaldan, çözüm önerisiyle birlikte.
- **Asla sessiz fallback yok:** keyring çalışmıyorsa FileTokenStore'a düşer; o da yoksa "kimliksiz mod" net olarak `auth_status`'ta görünür.

### 3.5 Güvenlik notları

- Şifre/token içeren hiçbir parametre `auth_login` dışında tool girdisine girmez (birincil kimlik env/keyring).
- `auth_login`'in açıklamasında "şifre LLM bağlamına girebilir" uyarısı + `confirm` param önerilir (Bölüm 2.4).
- Server logları `LOG_LEVEL=debug`'da bile token/sifre filtreler (SDK `logging` altyapısı + MCP tarafında çıktı maskeleme).
- Çıktıda `refresh_token` yalnızca `auth_login`'de döner; diğer hiçbir tool çıktısında token yoktur (backend sözleşmesi).

---

## 4. Uzun Süren İşlemler

İki uzun işlem ailesi var; ikisi de farklı doğada:

### 4.1 Rapor üretimi (`analysis_generate_report`) — senkron (API zorunlu kılıyor)

Backend `POST /reports/generate` **senkron** döner: rapor hazır olana kadar istek açık kalır (job-slot 900s; yanıt içinde `report(md)` vardır). "Başlat + durum sorgula" deseni backend'de **yok** — ayrı bir job endpoint'i mevcut değil (rapor history'den `analysis_get_report` ile sonradan alınabilir ama generate çağrısı kendisi bekler).

**Tasarım kararı: senkron tool + uzatılmış timeout.**
- SDK default read timeout 30s — `analysis_generate_report` için **read timeout 180s** ayarlanır (config'te `MCP_REPORT_TIMEOUT`, default 180).
- Tool açıklamasında net uyarı: "90 saniyeye kadar sürebilir; kredi harcar".
- İstemci tarafı (Claude Desktop vb.) kendi tool timeout'uyla keserse, LLM sonucu `analysis_list_reports`/`analysis_get_report` ile kurtarabilir — bu akış açıklamaya yazılır.
- Kredi öncesi bakiye kontrolü yönlendirmesi: "önce `account_credits`".

### 4.2 Export akışı — gerçek "başlat + durum" deseni (iki uçlu)

Backend export'u **asenkron** işler (queued → processing → ready/sent → error). Burada doğal olarak üç aşama var ve SDK bunları ayrı metotlarla sunuyor:

```
export_create (202, hızlı döner)
      │
      ▼
export_status (tek durum sorgusu) ──┐  LLM kendi poll döngüsünü yazabilir
      │                             │  (LLM-driven polling: "şimdi hazır mı?" × N)
      ▼                             │
export_wait (bloklayan poll,        │  veya tek çağrıda bekle:
            poll_interval +         │  timeout parametresiyle senkron dönüş
            timeout param)          │
      ▼
export_download (public token; dest_path ile sunucuya yaz veya base64)
```

**Tasarım kararı: ikisi de var — `export_wait` bloklayan kolaylık, `export_status` LLM'in kendi kararını verebildiği döngü.**
- Gerekçe: `export_wait` LLM'in "bekle, sonra indir" niyetini tek çağrıda ifade etmesini sağlar (`timeout` sınırı net); ama uzun kuyruklarda (3 export/saat, yoğun yıllar) bloklayıcı çağrı istemci timeout'una takılabilir — bu durumda LLM `export_status` ile aralıklı yoklama yapar. İki tool, iki strateji; aynı işi **kopyalamazlar** (biri poll'u sunucuda, diğeri istemcide yapar).
- `export_wait` timeout aşımı → `TimeoutError` → MCP hata mesajı: "Export hazır değil (son durum: X). export_status ile tekrar deneyin."
- `export_download` `dest_path` alırsa dosyayı **sunucunun çalıştığı makineye** yazar ve `{path, size_bytes, md5}` döner; almazsa gzip'i base64 döner (LLM küçük dosyalarda içeriği görebilir; büyükler için dest_path önerilir). `dest_path` varsayılan dizin: env `MCP_DOWNLOAD_DIR` (yoksa çalışma dizini) — güvenlik: path traversal'e karşı normalize edilir (açık karar noktası #6'da).

### 4.3 Diğer "uzun" adaylar

- `analysis_download_report` (docx/pdf pandoc üretimi): normalde saniyeler; `MCP_REPORT_DOWNLOAD_TIMEOUT` (default 60s) ile korunur.
- `portfolio_export_csv`, `account_export_data`: hızlı, standart timeout.

### 4.4 Özet karar

| İşlem | Desen | Gerekçe |
|---|---|---|
| `analysis_generate_report` | Senkron + 180s timeout | Backend senkron; start/poll alternatifi yok |
| `export_create` → `export_status` | Başlat + durum sorgula (LLM yönlü) | Backend asenkron; LLM akışı kontrol eder |
| `export_create` → `export_wait` | Başlat + bloklayan bekleme (kolaylık) | Tek çağrıda tamamlanan akış |
| `export_download` | Senkron; dest_path veya base64 | Public token; hızlı |

---

## 5. Hata ve Çıktı Formatı

### 5.1 Hata eşleme (SDK → MCP)

SDK hata hiyerarşisi (`errors.py`): `FlorenceError` → `FlorenceAPIError(status_code, code, detail)` → `AuthError` (401), `RateLimitError` (429, `retry_after`), `NetworkError`.

MCP tarafında FastMCP, handler içinden fırlatılan hatayı **tool error** olarak istemciye iletir. Eşleme:

| SDK hatası | MCP yüzeyi | Mesaj formatı (LLM'in anlayacağı) |
|---|---|---|
| `FlorenceAPIError` (4xx/5xx) | Tool error (`isError=true`) | `Florence API hatası <status>: <code> — <detail>` (örn. `error_bots_not_allowed`) |
| `AuthError` (401) | Tool error | `Kimlik hatası (401): <code> — <detail> | Çözüm: FLORENCE_TOKEN / keyring oturumu / MCP_FLORENCE_BOT` |
| `RateLimitError` (429) | Tool error | `Rate limit aşıldı (429): <code> — retry_after: <N>s | Bekleyip tekrar deneyin (örn. news 10/dk, auth 5/dk, export 3/saat)` |
| `NetworkError` | Tool error | `Ağ hatası: <mesaj> | FLORENCE_API_URL doğru mu, API erişilebilir mi?` |
| `TimeoutError` (export_wait) | Tool error | `Zaman aşımı: Export <id> <T>s içinde hazır olmadı (son durum: X) | export_status ile tekrar sorgulayın` |
| Beklenmeyen | Tool error + log | `Beklenmeyen hata: <exc> (detay sunucu logunda)` |

İlkeler:
- **Hata kodu korunur:** backend'in i18n `detail` kodu (`error_*`) mesaja girer — LLM bilinen kodları tanıyabilir (CLI `--json` hata formatıyla aynı `code` disiplini: `error_*` / `not_authenticated` / `rate_limited` / `network` / `timeout` / `not_found`).
- **Çözüm önerisi mesaja gömülür:** LLM hata mesajından aksiyonu çıkarabilmeli (bekle ve dene, kimlik kur, farklı parametre dene).
- Token/sifre **asla** hata mesajına girmez.
- SDK'nın 429/5xx retry + backoff'u MCP'de de geçerlidir (client zaten yapar); `retry_after` header'ına saygı otomatik. Retry tükenince `RateLimitError` yukarıdaki gibi yüzeye çıkar.

### 5.2 Başarılı çıktı formatı

Tüm tool'lar tek, tutarlı content blok yapısı döner:

```json
{
  "content": [
    {
      "type": "text",
      "text": "<JSON: pretty-printed, ensure_ascii=false, indent=2>"
    }
  ],
  "structuredContent": { "...": "aynı veri, yapılandırılmış (istemci destekliyorsa)" }
}
```

- **JSON tool'ları:** SDK'nın standart çıktısı (parse edilmiş JSON) `format.py`'de `json.dumps(data, ensure_ascii=False, indent=2)` ile metin bloğuna dönüşür. Türkçe karakterler korunur (`ensure_ascii=False`). İlke CLI ile aynıdır: **"çıktı = API şeması"** — openapi.json ile tool çıktısı arasında çeviri yoktur. `structuredContent` (MCP 2025-03-26+) istemci destekliyorsa aynı veriyi yapılandırılmış olarak taşır — LLM'in JSON parse etmesine gerek kalmaz.
- **Metin tool'ları** (`market_company_info` format="md", `portfolio_export_csv`, `analysis_get_report` md içerik, `misc_legal` vb.): düz metin olarak `text` bloğuna.
- **Dosya tool'ları** (`export_download`, `analysis_download_report`):
  - `dest_path` verildiyse → `{path, size_bytes, md5, format}` meta JSON'u (LLM dosyanın nereye yazıldığını bilir).
  - `dest_path` verilmediyse → `md` için düz metin; binary (docx/pdf/gzip) için `base64` + `{encoding: "base64", size_bytes, format}` meta notu. LLM base64'i decode edemiyorsa `dest_path` kullanması açıklamada belirtilir.
- **Maskeleme:** `bots_create` çıktısındaki `password` alanı `"***"` olarak maskelenir (değer yalnızca keyring'e yazılır) — `format.py`'de alan bazlı kural.

### 5.3 Rate limit'in LLM'e anlatımı

- **Otomatik:** SDK 429'da `Retry-After`'a saygılı backoff yapar; tükenirse `RateLimitError.retry_after` (saniye) hata mesajına girer.
- **Manuel bilgi:** `misc_maintenance` (devre dışı özellikler) ve `analysis_report_info` (maliyetler) tool'ları LLM'in ön kontrol yapmasını sağlar.
- **Sistem düzeyi ipucu (opsiyonel):** Server, MCP `instructions` alanına (FastMCP `instructions=` veya bir `florence_guidelines` resource'u) rate limit tablosunu koyabilir: `news 10/dk`, `auth 5/dk`, `export 3/saat`, `login 5/dk` — LLM çağrı sıklığını buna göre ayarlar. Bu, "429'u LLM'e anlatmanın" en etkili yolu: önlemek, hata mesajından daha iyidir. (Öneri olarak sunulur; açık karar noktası #5.)

---

## 6. İstemci Kurulumu

> Ön koşul: paket kurulu — `uv tool install 'florence-sdk[mcp]'` (veya `pipx install 'florence-sdk[mcp]'`, veya repo içinden `uv run florence-mcp`). Entry point: `florence-mcp`. Doğrulama: `florence-mcp --help` / `echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | florence-mcp`.

### 6.1 Claude Desktop

`claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "florence": {
      "command": "florence-mcp",
      "args": [],
      "env": {
        "FLORENCE_TOKEN": "…",                    // seçenek A: hazır token
        "MCP_FLORENCE_BOT": "bot-1",              // seçenek B: bot profili (keyring şifresiyle)
        "FLORENCE_API_URL": "https://api.florencex.com.tr"   // opsiyonel (dev override)
      }
    }
  }
}
```

### 6.2 Claude Code

Proje köküne `.mcp.json` (proje düzeyinde, takımla paylaşılabilir — token koymadan):

```json
{
  "mcpServers": {
    "florence": {
      "type": "stdio",
      "command": "florence-mcp",
      "env": {
        "MCP_FLORENCE_BOT": "bot-1"
      }
    }
  }
}
```

Kullanıcı düzeyinde token eklemek için `claude mcp add florence --env FLORENCE_TOKEN=…` veya kabukta `export FLORENCE_TOKEN=…` (Claude Code mevcut env'i geçirir). Not: `.mcp.json`'a token **yazılmaz** (repo'ya sızabilir) — env/`claude mcp add` tercih edilir.

### 6.3 Cursor

`~/.cursor/mcp.json` (global) veya proje `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "florence": {
      "command": "florence-mcp",
      "args": [],
      "env": {
        "FLORENCE_TOKEN": "…"
      }
    }
  }
}
```

### 6.4 Çoklu kimlik deseni (v1)

Aynı istemcide hem kullanıcı hem bot profili istiyorsanız iki ayrı sunucu bloğu (her biri kendi env'iyle — Bölüm 3.1'deki "tek process = tek kimlik" kuralı):

```json
{
  "mcpServers": {
    "florence-user": { "command": "florence-mcp", "env": { "FLORENCE_TOKEN": "…" } },
    "florence-bot":  { "command": "florence-mcp", "env": { "MCP_FLORENCE_BOT": "bot-1" } }
  }
}
```

---

## 7. Dosya Düzeni

### 7.1 Paket yapısı (`src/florence_mcp/`)

```
src/florence_mcp/
├── __init__.py          # create_server() factory + __version__ (SDK sürümüyle senkron)
├── server.py            # FastMCP kurulumu; stdio transport; shutdown hook (logout);
│                        #   main() entry (florence-mcp)
├── tools.py             # 92 tool tanımı: SDK resource çağrısı + girdi/çıktı şeması;
│                        #   her tool tek fonksiyon (SDK metoduyla 1:1)
├── registry.py          # tool envanteri meta: isim, açıklama, risk işareti (DANGER/CREDIT/WRITE),
│                        #   confirm-gerekli mi, grup (domain); gruplara göre kapatma anahtarı
├── auth.py              # kimlik çözümleme: MCP_FLORENCE_BOT → login_as_bot; env → keyring → file;
│                        #   MCP_FLORENCE_BOT_PASSWORD; auth_status verisi
├── format.py            # çıktı normalizasyonu: JSON pretty (ensure_ascii=False), metin, base64,
│                        #   dest_path yazma + md5, bot şifresi maskeleme, hata → ToolError mesajı
├── config.py            # MCP_* env'ler: MCP_FLORENCE_BOT, MCP_DOWNLOAD_DIR, MCP_REPORT_TIMEOUT,
│                        #   MCP_FLORENCE_BOT_PASSWORD, MCP_DISABLE_GROUPS
└── long_running.py      # [opsiyonel] export_wait poll / timeout yardımcıları (asyncio)
```

Sorumluluk ayrımı: `tools.py` **yalnızca SDK çağrısı** yapar; tüm dönüşüm `format.py`'de; kimlik `auth.py`'de; kayıt/denetim `registry.py`'de. Böylece SDK metoduna eklenen her yeni endpoint → `tools.py` + `registry.py`'ye tek satır ekleme = otomatik MCP tool'u.

### 7.2 pyproject entegrasyonu

```toml
[project.scripts]
florence = "florence.cli.app:main"      # mevcut (Faz 3)
fl = "florence.cli.app:main"            # mevcut (Faz 3)
florence-mcp = "florence_mcp.server:main"   # YENİ

[project.optional-dependencies]
mcp = ["mcp>=1.2"]                      # YENİ (öneri: opsiyonel extra)

[tool.hatch.build.targets.wheel]
packages = ["src/florence", "src/florence_mcp"]   # güncellenir
```

### 7.3 mcp bağımlılığı: opsiyonel extra mi, ana bağımlılık mı? — **Öneri: opsiyonel extra (`florence-sdk[mcp]`)**

| Seçenek | Artı | Eksi |
|---|---|---|
| **Opsiyonel extra (öneri)** | Çekirdek SDK hafif kalır (curl/script kullanıcıları mcp indirmez); MCP isteyenler `[mcp]` ile kurar; `uv tool install 'florence-sdk[mcp]'` tek satır. | `florence-mcp` komutu extra'sız kurulumda yoktur (net hata: "mcp extra'sı gerekli") |
| Ana bağımlılık | Her kurulumda komut hazır | Çekirdeğe gereksiz ağırlık; SDK'yı sadece veri çekmek için kullananlar mcp'yi de yükler |

Not: Plan Faz 0 (T0.2) `mcp`'yi bağımlılık olarak listeler — bu öneri, mcp'nin **projede** bulunmasını (dev grubu dahil) korur ama **yayınlanan çekirdeğe** taşımaz. CLI raporu/uygulama aşamasında planla uyum için bu karar kullanıcıya sunulur (açık karar noktası #4).

---

## 8. Açık Karar Noktaları (kullanıcı onayı bekler)

1. **Uzun işlem deseni:** `analysis_generate_report` senkron + 180s timeout (öneri — backend senkron olduğu için alternatifi yok); export için hem `export_wait` (bloklayan) hem `export_status` (LLM poll'ü). Onay: senkron + uzun timeout kabul mü, yoksa istemci tarafı kesinti + `analysis_list_reports` kurtarma akışı mı birincil?
2. **Bot profili seçimi:** `MCP_FLORENCE_BOT` env ile mi (öneri — istemci config'lerinde açık, paylaşılabilir), yoksa config dosyasına (`~/.config/florence/config.toml`) yazılsın mı? Çoklu kimlik v1'de "çoklu MCP bloğu" deseniyle mi çözülsün (öneri)?
3. **Tool kapsamı:** 92 tool'un tamamı mı açılsın (öneri — adaptör maliyeti düşük, SDK kapsamını birebir yansıtır, CLI ile birebir uyumludur), yoksa küratörlü alt küme mi? Kuratörlük istenirse: `MCP_DISABLE_GROUPS=admin,export` gibi grup bazlı kapatma anahtarı (öneri) yeterli mi?
4. **`mcp` bağımlılığı:** opsiyonel extra `[mcp]` (öneri) mi, ana bağımlılık mı? (Plan T0.2 ile çelişki notu Bölüm 7.3.)
5. **Rate limit rehberliği:** MCP `instructions`/resource ile sistem prompt'una rate limit tablosu enjekte edilsin mi (öneri: evet — LLM 429'u önler)?
6. **Dosya yazma güvenliği:** `dest_path` için varsayılan dizin `MCP_DOWNLOAD_DIR` ve path-normalizasyon (traversal koruması) kabul mü? `analysis_download_report`/`export_download` binary'lerde base64 mi, dest_path mi birincil?

---

## 9. KARARLAR (2026-08-14)

Implementasyon tamamlandı; aşağıdaki kararlar bu rapordaki önerilerin
**onaylanmış** halleridir ve gerçek uygulama bunlara göredir.

| # | Karar | Açıklama / Uygulama |
|---|---|---|
| 1 | **Ayrı paket: `florence_mcp`** | `src/florence_mcp/` bağımsız paket; `pyproject.toml` `[project.scripts] florence-mcp = "florence_mcp.server:main"` ve wheel `packages = ["src/florence", "src/florence_mcp"]`. `mcp>=1.2` + `fastmcp>=2.0` ana bağımlılık olarak eklendi (opsiyonel extra yerine — CLI subagent'ı ile eşzamanlı yürütüldü, mevcut pyproject korundu). |
| 2 | **180s rapor timeout'u** | `analysis_generate_report` senkron + `MCP_REPORT_TIMEOUT` (default 180s); `analysis_download_report` `MCP_REPORT_DOWNLOAD_TIMEOUT` (default 60s). Per-call http read timeout kilit altında değiştirilir (`tools._client_read_timeout`) — eşzamanlı tool çağrıları güvenli. |
| 3 | **Kimlik zinciri sırası** | `MCP_FLORENCE_BOT` (+ `MCP_FLORENCE_BOT_PASSWORD` veya keyring şifresi) → `FLORENCE_TOKEN` → keyring/FileTokenStore → **kimliksiz mod**. Bot + env token birlikteyse **bot kazanır**. Şifre yoksa `AuthError(401, "no_bot_password")` net hata: "MCP_FLORENCE_BOT_PASSWORD ile verin veya bots_create ile oluşturun". |
| 4 | **92 tool tamamı** | Envanterin tamamı kayıtlı (10 auth + 6 account + 11 market + 6 economy + 24 portfolio + 13 analysis + 3 bots + 5 export + 14 misc). `MCP_DISABLE_GROUPS=auth,export` ile grup bazlı kapatma çalışır. İsimler CLI eşleme tablosuyla (Bölüm 2.6) birebir. |
| 5 | **Rate limit instructions** | FastMCP `instructions=` alanına backend limit tablosu yazıldı: login/refresh 5/dk, register 3/dk, resend-verification 3/saat, news 10/dk, export 3/saat, report job-slot 900s, simulation 600s. LLM 429'u önceden önler. |
| 6 | **base64 + `dest_path`** | `export_download` / `analysis_download_report`: `dest_path` verilirse dosya sunucuya yazılır (`{path, size_bytes, md5, format}` döner); verilmezse md → metin, binary → `{format, encoding: "base64", size_bytes, data}`. `dest_path` yalnızca `MCP_DOWNLOAD_DIR` (yoksa cwd) içinde normalize edilir; traversal `ToolError` ile reddedilir (`files.resolve_dest_path`). SDK'ya `dest_path` **verilmez** — yazma MCP katmanında yapılır (traversal koruması SDK'yı atlamaz). |
| 7 | **confirm + maskeleme** | `confirm: bool` zorunlu savunma hattı 4 tool'da: `auth_delete_account`, `portfolio_delete`, `portfolio_undo_transaction`, `bots_delete` — `false` ile çağrı reddedilir ("Onay gerekli..."). `bots_create` yanıtındaki tek seferlik şifre `"***"` ile maskelenir (`format.mask_bot_password`); gerçek değer yalnızca token store'a yazılır. Risk işaretleri (🔴 DANGER / 🟠 CREDIT / 🟡 WRITE) açıklamanın ilk satırında. |
| 8 | **`structuredContent` sözleşmesi** | Tasarımdaki `structuredContent` alanı FastMCP `ToolResult.structured_content` ile karşılanır; JSON tool'ları pretty metin + aynı veriyi yapılandırılmış taşır. Pydantic modeller (`TokenPair`) `model_dump()` ile serileştirilir. |
| 9 | **Senkron client + `run_in_thread`** | Bölüm 1.3'teki `AsyncFlorenceClient` önerisi uygulamada **senkron `FlorenceClient`** oldu: FastMCP tool handler'ları `run_in_thread=True` ile ayrı thread'de çalıştığı için event loop bloklanmaz; SDK'nın tek transport kodu (retry/refresh) aynen kullanılır. `export_wait` gibi bloklayan poll'lar thread içinde doğal çalışır. |
| 10 | **Shutdown logout** | FastMCP lifespan kapanış hook'unda `auth.logout()` çağrılır (bot oturumu refresh token iptali, Bölüm 3.3.4). Token yoksa HTTP çağrısı yapılmaz; hatalar sessizce geçilir. |
| 11 | **`analysis_get_report` dönüşü** | Bölüm 5.2'deki "metin tool'ları" listesinden farklı olarak **JSON obje** döner (SDK `GET /reports/{report_id}` kaydını parse eder; md içerik `report` alanındadır). "Çıktı = API şeması" ilkesine uyar; LLM içerikten md'yi okur. |

**Küçük sapmalar:** SDK'da `FileTokenStore` henüz yok — token kaynağı `keyring` aktifse `keyring`, değilse `memory` olarak raporlanır (`auth_status.token_source`); `mcp` paketi 1.x + ayrı `fastmcp` 3.x kurulur (tasarımdaki `mcp>=1.2` constraint'i korunur, `structured_content` iki pakette de destekli). CLI eşzamanlı subagent'ı `pyproject.toml`'a `typer/rich/cryptography` + `florence`/`fl` script'leri ekledi — korundu, silinmedi.

---

## Ek A — Kaynak kod haritası (referans)

| SDK dosyası | İçerik | MCP etkisi |
|---|---|---|
| `resources/auth_res.py` | 9 metod (register…change_username) | auth domaini (login/logout AuthManager'dan; refresh otomatik, tool yok) |
| `resources/user_res.py` | 6 metod | account domaini (CLI grup adıyla uyum) |
| `resources/market_res.py` | 12 metod (info_md dahil) | market domaini (md, `format` parametresinde) |
| `resources/economy_res.py` | 6 metod | economy domaini |
| `resources/portfolio_res.py` | 24 metod | portfolio domaini (favorites+portfolios+transactions+analizler) |
| `resources/analysis_res.py` | 13 metod | analysis domaini (simülasyon, rapor, danışman) |
| `resources/bots_res.py` | 3 metod + bot_session | bots domaini + kimlik modu |
| `resources/export_res.py` | 5 metod (poll dahil) | export domaini (başlat/durum/indir) |
| `resources/misc_res.py` | 15 metod (root hariç 14 kullanışlı) | misc domaini |
| `auth.py` | AuthManager, TokenStore'lar, BotSession | kimlik çözümleme, bot profili |
| `client.py` | sync/async transport, retry, auto-refresh | MCP handler'ların çağırdığı katman |
| `errors.py` | hata hiyerarşisi, Retry-After | Bölüm 5 eşlemesi |
| `config.py` | env'ler, timeout'lar | MCP config alt kümesi |
| `models.py` | pydantic modeller (opsiyonel) | tool çıktı dokümantasyonu |

## Ek B — Doğrulama planı (implementasyon sonrası, Faz 6 T6.3)

1. `uv run florence-mcp` başlar; `mcp` python paketinin istemcisiyle `tools/list` → 92 tool döner.
2. `market_price_current` çağrısı (mock transport ile) → yapılandırılmış JSON content bloğu.
3. Kimliksiz ortamda `account_profile` → açıklayıcı 401 hata mesajı (Bölüm 3.4).
4. `MCP_FLORENCE_BOT=bot-1` ile başlat → `auth_status` `identity_type: "bot"`; bot tool çağrıları başarılı.
5. 429 mock'u → retry_after'lı hata mesajı.
6. `export_create` → `export_wait` (mock) → `export_download(dest_path)` akışı; base64 fallback.
7. `analysis_generate_report` 180s timeout mock'u ile uzun yanıt testi.
8. CLI eşleme kontrolü: `cli-design.md` kapsam tablosuyla çapraz doğrulama (Bölüm 2.6).
