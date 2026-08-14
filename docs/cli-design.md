# Florence CLI — Tam Tasarım Raporu (Faz 3)

> **Kapsam:** `fl` / `florence` CLI komut ağacının tam tasarımı. Kaynak: `src/florence/resources/*` (9 modül, 76 metod), `src/florence/{client,auth,errors,config}.py`, plan `2026-08-14_144500-florence-sdk.md` Faz 3 + "Kalıcı auth (CLI) — ZORUNLU GEREKSİNİMLER" (T3.2a–e). Kapsam doğrulaması: `api-spec/openapi.json` (89 path).
> **Bu doküman SADECE tasarımdır** — kod içermez, implementasyon Faz 3'te yapılır.
> **Dil kuralı:** komut adları ve bayraklar İngilizce (teknik standart); yardım metinleri, açıklamalar ve hata mesajları Türkçe (hedef kitle: Türkçe BIST yatırımcısı).

---

## 1. Tasarım Felsefesi

### 1.1 İsimlendirme deseni: `<grup> <komut>` (iki seviyeli ağaç)

Tek desen: **her komut bir gruba aittir; komut seviyesinde hiçbir şey durmaz.**

```
fl <grup> <komut> [argümanlar] [opsiyonlar]
```

- **Grup** = kaynak alanı ismi (`auth`, `account`, `market`, `economy`, `portfolio`, `analysis`, `bots`, `export`, `misc`, `config`). Grup adları SDK resource modül adlarıyla birebir hizalıdır (tek istisna: `config` — CLI yerel ayarları, SDK endpoint'i değildir).
- **Komut** = iki türden biri:
  - **Fiil** (eylem): `create`, `delete`, `login`, `set`, `undo`… — durum değiştiren, kredi harcayan veya akış başlatan işlemler.
  - **İsim** (görünüm): `price`, `history`, `gold`, `valuation`, `status`… — salt-okuma uçları. Kural: **okuma ucu isimle, yazma ucu fiille adlandırılır** (`git status`, `docker ps` geleneği).
- **Alt varlık kuralı** (3. seviye, yalnızca çok eylemli alt kaynaklarda): `fl portfolio favorite add <ticker>`, `fl analysis report generate …` — `git remote add` deseni. Tek eylemli varlıklar asla 3. seviye açmaz.

### 1.2 Semantic ilkeler

1. **Komut = kullanıcı niyeti, path değil.** Komut adı endpoint path'ini kopyalamaz; kullanıcının zihnindeki işi söyler. `POST /stocks/fit` → `fl analysis fit`; `GET /portfolio/profile` → `fl analysis similar`; `GET /companies/info/{ticker}/md` → `fl market info ASELS --md`.
2. **Her komut tek bir iş yapar.** Tek komutta iki farklı endpoint'e giden dallanma yoktur. Tek istisna, kullanıcı iş akışı olarak *tek niyet* sayılan **belgelenmiş kompozitlerdir** (`fl export fetch` = create→wait→download; `fl market info --md` = aynı kaynağın farklı serileştirmesi).
3. **Bir işin tek yolu vardır.** Eş anlamlı/paralel komut yoktur: bot login yalnızca `fl auth login --bot`; portföy silme yalnızca `fl portfolio delete`; fiyat yalnızca `fl market price`.
4. **Her komut iki çıktı moduna sahiptir:** `--json` (saf, makine-okunur) ve normal (insan-okur, rich tablo). Bayrak her komutta ortaktır (global), ayrı bir `--format` çıktı bayrağı YOKTUR.
5. **Komut ağacı = SDK envanteri.** Her SDK metodu tam olarak bir komuta karşılık gelir; açıkta endpoint kalmaz, komut fazlası olmaz (bölüm 2.11 kapsam tablosu).

### 1.3 "Güçlü / efektif / net" nasıl sağlanır

| Nitelik | Uygulama |
|---|---|
| **Güçlü** | Tüm 89 path'in erişilebilirliği (6 bilinçli kapsam dışı hariç); kompozit akışlar (`export fetch` = sipariş+poll+indir) tek komutta; kalıcı auth (keyring/FileTokenStore) ile komutlar arası oturum; 0/1/2 exit code disiplini. |
| **Efektif** | En sık işler en kısa yolda: `fl market price THYAO`, `fl account credits`, `fl auth login` — 2 seviye, ekstra alt menü yok. İnsan ve makine aynı komutu kullanır (`--json`). |
| **Net** | stdout = veri, stderr = hata/progress; `--json`'da hatalar da makine-okunur; kısa bayrak yok (çakışma imkânsız); her komutun yardımı Türkçe ve tek cümleyle ne yaptığını söyler. |

### 1.4 Gereksizlikten kaçınma kuralları

1. **Eş anlamlı komut yok** — iki komut aynı endpoint'e gitmez (kapsam tablosu bunu garantiler; tek istisna: aynı kaynağın farklı formatı `--md`/`--format` bayrağıyla, ayrı komut değil).
2. **Alias yoğunluğu yok** — tek istisna, kullanıcının onayladığı entry-point ikilisi: `florence` (ana) + `fl` (kısa). Komut seviyesinde hiçbir kısaltma/alias yok (`fav`, `prefs`, `sim` vb. kullanılmaz).
3. **Gereksiz bayrak yok** — SDK'da parametresi olmayan şey bayrak olmaz (ör. `--cash` EKLENMEZ: `fit_stocks` horizon/profitability/risk_tolerance/limit alır). Varsayılanı SDK'dan devralan bayrak yazılmaz; SDK varsayılanı yeterliyse bayrak yoktur.
4. **Çıktı formatı tek eksen** — veri formatı (`--format csv|json|md|docx|pdf` — *içerik* biçimi) ile çıktı modu (`--json` — *ekran* biçimi) asla karışmaz, iki farklı isimle ayrılır (bölüm 5).
5. **Kısa bayrak yok** — tek harfli bayraklar hiç kullanılmaz; typer'ın ürettiği `--help` dışında kısaltma yoktur.

---

## 2. Tam Komut Ağacı

### 2.0 Genel şema

```
fl [--json] [--verbose] <grup> <komut> [arg] [opsiyonlar]
fl --version | --help

Gruplar (10): auth  account  market  economy  portfolio  analysis  bots  export  misc  config
```

- `--json` ve `--verbose` **global** opsiyonlardır (her komuttan önce veya sonra yazılabilir).
- `fl --version` → yerel paket sürümü (ağ yok). API sürümü için: `fl misc version` (ağ var). İkisi farklı işlerdir, karışmaz.
- Toplam **94 komut** (yaprak).

**Ortak çıktı kuralı (tüm komutlar):**
- **İnsan modu:** rich tablo / anahtar-değer blok; uzun metinler 40 karakterde kırpılır; sayılar TR binlik ayracı + 2 ondalık.
- **`--json` modu:** stdout'a **API yanıtının normalize edilmiş hali birebir** (tek JSON belgesi: nesne veya dizi). İlke: *"JSON çıktısı = API şeması"* — AI/script tüketicileri openapi.json ile CLI arasında çeviri yapmaz. Tek istisnalar: yerel durum üreten komutlar (`auth status`, `config show`) ve kompozitler (`export fetch`) kendi stabil şemalarını tanımlar (aşağıda belirtildi).
- Exit code: 0 başarı, 1 çalışma hatası, 2 kullanım hatası (bölüm 3).

---

### 2.1 `fl auth` — kimlik doğrulama ve hesap yönetimi (10 komut)

Karşılık: `AuthManager` (durumlu) + `AuthResource` (durumsuz). Token yaşam döngüsü SDK `AuthManager`'da; CLI yalnızca ince çağırıcıdır.

| Komut | Syntax | Argümanlar / Opsiyonlar | SDK / Endpoint | Örnek |
|---|---|---|---|---|
| `login` | `fl auth login <username> [--bot] [--password <pwd>]` | `<username>` zorunlu. `--bot`: bot olarak giriş (şifre keyring'den okunur; yoksa hata + `fl bots create` önerisi). `--password`: şifreyi bayrakla ver (komut geçmişi riski; yoksa **gizli prompt**, getpass). | `AuthManager.login` → `POST /auth/login`; `login_as_bot` → aynı endpoint, bot kimliği | `fl auth login efe` / `fl auth login --bot bot-1` |
| `logout` | `fl auth logout` | — | `AuthManager.logout` → `POST /auth/logout` + store temizle | `fl auth logout` |
| `status` | `fl auth status` | — (yerel, ağ yok) | Yerel: store + config. `username`, `user_type` (config'e yazılan son giriş tipi: user/bot), `store` (keyring/file/env), `authenticated`, `env_override` (FLORENCE_TOKEN ise) | `fl auth status` |
| `register` | `fl auth register <username> <email>` | `<username>`, `<email>` zorunlu. Şifre gizli prompt ×2 (min 10 karakter, eşleşme kontrolü) | `AuthManager.register` → `POST /auth/register` | `fl auth register efe efe@mail.com` |
| `verify` | `fl auth verify <token>` | `<token>` zorunlu | `AuthManager.verify_email` → `GET /auth/verify-email` | `fl auth verify abc123` |
| `resend` | `fl auth resend <username-or-email>` | zorunlu | `AuthManager.resend_verification` → `POST /auth/resend-verification` | `fl auth resend efe@mail.com` |
| `change-password` | `fl auth change-password` | Mevcut + yeni şifre gizli prompt (yeni ×2) | `AuthResource.change_password` → `PUT /auth/change-password` | `fl auth change-password` |
| `change-email` | `fl auth change-email <new-email>` | `<new-email>` zorunlu; mevcut şifre gizli prompt | `AuthResource.change_email` → `PUT /auth/change-email` | `fl auth change-email yeni@mail.com` |
| `change-username` | `fl auth change-username <new-username>` | zorunlu; mevcut şifre gizli prompt | `AuthResource.change_username` → `PUT /auth/change-username` | `fl auth change-username efe2` |
| `delete` | `fl auth delete [--yes]` | **Yıkıcı**: onay prompt'u ("Hesabınız kalıcı silinecek, onaylıyor musunuz? [y/N]"); `--yes` ile atla. `--json` modunda prompt sorulmaz → `--yes` zorunlu | `AuthResource.delete` → `DELETE /auth/delete` | `fl auth delete --yes` |

**Notlar:** `refresh` komutu YOKTUR — refresh, 401'de client tarafında otomatik (single-flight) yapılır; kullanıcıya açık değildir (gereksizlik). `fl bots login` komutu da YOKTUR — bot girişinin tek yolu `fl auth login --bot`'tur (eş anlamlılık yasağı).

**Çıktı:**
- İnsan: `login` → "Giriş yapıldı: efe (user)"; `status` → anahtar-değer blok; `logout/verify/resend/change-*` → API mesajı; `delete` → onay mesajı.
- `--json`: `login/register` → API yanıtı; `status` → `{"authenticated": true, "username": "efe", "user_type": "user", "store": "keyring", "env_override": false}`; `logout/delete` → API yanıtı.

---

### 2.2 `fl account` — profil, tercihler, kredi (6 komut)

Karşılık: `UserResource`.

| Komut | Syntax | Argümanlar / Opsiyonlar | SDK / Endpoint | Örnek |
|---|---|---|---|---|
| `credits` | `fl account credits` | — | `UserResource.credits` → `GET /credits` | `fl account credits` |
| `profile` | `fl account profile` | — | `UserResource.profile` → `GET /profile` | `fl account profile` |
| `avatar` | `fl account avatar <avatar-id>` | `<avatar-id>` zorunlu | `UserResource.update_avatar` → `PUT /profile/avatar` | `fl account avatar 3` |
| `preferences` | `fl account preferences` | — (okuma) | `UserResource.get_preferences` → `GET /user/preferences` | `fl account preferences` |
| `preferences set` | `fl account preferences set <key>=<value> ...` | 1+ adet `key=value`; PUT mevcut prefs ile birleştirir (SDK davranışı) | `UserResource.update_preferences` → `PUT /user/preferences` | `fl account preferences set language=tr theme=dark` |
| `export` | `fl account export [--output <path>]` | `--output`: JSON dump'ı dosyaya yaz (yoksa stdout) | `UserResource.export_data` → `GET /user/export` | `fl account export --output veri.json` |

**Çıktı:** `credits` insan modu → `Kredi: 123.45`; `profile` → anahtar-değer tablo; `preferences` → `key: value` listesi; `--json` → API yanıtı birebir.

---

### 2.3 `fl market` — BIST verisi (11 komut)

Karşılık: `MarketResource` (hepsi `auth=False`, public — giriş gerektirmez; tek istisna `news` JWT ister).

| Komut | Syntax | Argümanlar / Opsiyonlar | SDK / Endpoint | Örnek |
|---|---|---|---|---|
| `price` | `fl market price <ticker> [--interval 5m\|30m\|1h\|1d]` | `<ticker>` zorunlu (tek). `--interval` default `5m` | `MarketResource.current_price` → `GET /price/current` | `fl market price THYAO` |
| `history` | `fl market history <ticker> [--period 1mo] [--interval 1d]` | `--period` default `1mo`; `--interval` default `1d` | `MarketResource.price_history` → `GET /price/history/{ticker}` | `fl market history ASELS --period 3m` |
| `companies` | `fl market companies [--sort alphabetical] [--limit 50] [--offset 0]` | `--sort`: alphabetical (SDK) | `MarketResource.companies` → `GET /bist/companies` | `fl market companies --limit 20` |
| `tickers` | `fl market tickers [--sort alphabetical] [--limit 50] [--offset 0]` | aynı | `MarketResource.tickers` → `GET /bist/tickers` | `fl market tickers` |
| `search` | `fl market search <query>` | `<query>` zorunlu (alias destekli) | `MarketResource.search_companies` → `GET /companies/search` | `fl market search aselsan` |
| `info` | `fl market info <ticker> [--md]` | `--md`: markdown profil (`/md` ucu) — aynı kaynak, farklı serileştirme | `MarketResource.company_info` / `company_info_md` → `GET /companies/info/{ticker}` (+`/md`) | `fl market info THYAO` / `fl market info THYAO --md` |
| `summary` | `fl market summary [--sort popular] [--limit 50] [--offset 0] [--tickers THYAO,ASELS]` | `--sort`: popular\|alphabetical\|gainers\|losers\|price_high\|price_low\|volume\|market_cap; `--tickers`: virgüllü filtre | `MarketResource.companies_summary` → `GET /companies/summary` | `fl market summary --sort gainers --limit 10` |
| `news` | `fl market news <ticker> [--amount 10]` | JWT gerekir (news feature) | `MarketResource.news` → `GET /news/{ticker}` | `fl market news THYAO --amount 5` |
| `status` | `fl market status` | — | `MarketResource.market_status` → `GET /market/status` | `fl market status` |
| `stats` | `fl market stats <ticker>` | `<ticker>` zorunlu | `MarketResource.stats` → `GET /stats/{ticker}` | `fl market stats TUPRS` |
| `top` | `fl market top [--limit 50]` | — | `MarketResource.stats_top` → `GET /stats/top` | `fl market top --limit 10` |

**Çıktı:** liste komutları (`companies`, `summary`, `news`, `top`) rich tablo; `price`/`status` anahtar-değer; `history` zaman serisi tablosu (sütun: tarih, açılış, kapanış, hacim…); `info --md` → ham markdown (stdout, `--json`'da `{"markdown": "…"}`). `--json` → API yanıtı birebir.

---

### 2.4 `fl economy` — altın, kıymetli maden, döviz, makro (6 komut)

Karşılık: `EconomyResource` (hepsi public). **Backend pitfall:** değerler string + Türk virgüllü ondalıktır (`"40,25"`) — CLI, insan tablosunda ve `--json`'da **sayıya normalize eder** (`"40,25"` → `40.25`), çünkü makine tüketicisi string istemez. (SDK ham string döndürür; CLI sunum katmanında çevirir — veri katmanına dokunmaz.)

| Komut | Syntax | Argümanlar / Opsiyonlar | SDK / Endpoint | Örnek |
|---|---|---|---|---|
| `gold` | `fl economy gold` | — | `EconomyResource.gold_prices` → `GET /economy/gold-prices` | `fl economy gold` |
| `silver` | `fl economy silver` | — | `EconomyResource.silver_price` → `GET /economy/silver-price` | `fl economy silver` |
| `platinum` | `fl economy platinum` | — | `EconomyResource.platinum_price` → `GET /economy/gram-platinum-price` | `fl economy platinum` |
| `palladium` | `fl economy palladium` | — | `EconomyResource.palladium_price` → `GET /economy/gram-palladium-price` | `fl economy palladium` |
| `currency` | `fl economy currency [--symbols USD,EUR]` | `--symbols`: virgüllü filtre (yoksa hepsi) | `EconomyResource.currency` → `GET /economy/currency` | `fl economy currency --symbols USD,EUR` |
| `macro` | `fl economy macro` | — | `EconomyResource.macroeconomy` → `GET /macroeconomy` | `fl economy macro` |

**Çıktı:** tek değerli komutlar (`silver`, `platinum`, `palladium`) anahtar-değer; `gold`/`currency`/`macro` tablo. `--json` → normalize edilmiş sayılarla API yapısı.

---

### 2.5 `fl portfolio` — favoriler, portföyler, işlemler, analizler (24 komut)

Karşılık: `PortfolioResource` (tamamı JWT). En kalabalık grup; alt varlık kuralı burada uygulanır:

```
fl portfolio favorite  add|remove|list
fl portfolio           create|list|get|rename|delete|duplicate
fl portfolio tx        add|list|update|undo
fl portfolio           valuation|diversification|performers|history|returns|risk|benchmark|performance|stats|snapshot|export
```

#### Favoriler (3)

| Komut | Syntax | SDK / Endpoint | Örnek |
|---|---|---|---|
| `favorite add` | `fl portfolio favorite add <ticker>` | `add_favorite` → `POST /favorites/{ticker}` (idempotent) | `fl portfolio favorite add ASELS` |
| `favorite remove` | `fl portfolio favorite remove <ticker>` | `remove_favorite` → `DELETE /favorites/{ticker}` | `fl portfolio favorite remove ASELS` |
| `favorite list` | `fl portfolio favorite list` | `favorites` → `GET /favorites` | `fl portfolio favorite list` |

#### Portföy CRUD (6)

| Komut | Syntax | Argümanlar / Opsiyonlar | SDK / Endpoint | Örnek |
|---|---|---|---|---|
| `create` | `fl portfolio create <name> --balance <float>` | `<name>` zorunlu; `--balance` zorunlu (>0) | `create_portfolio` → `POST /portfolios` | `fl portfolio create "Ana Portföy" --balance 100000` |
| `list` | `fl portfolio list` | — | `list_portfolios` → `GET /portfolios` | `fl portfolio list` |
| `get` | `fl portfolio get <portfolio-id>` | zorunlu | `get_portfolio` → `GET /portfolios/{id}` | `fl portfolio get 7` |
| `rename` | `fl portfolio rename <portfolio-id> <name>` | zorunlu | `rename_portfolio` → `PUT /portfolios/{id}` | `fl portfolio rename 7 "Yeni Ad"` |
| `delete` | `fl portfolio delete <portfolio-id> [--yes]` | yıkıcı; onay promptu / `--yes` | `delete_portfolio` → `DELETE /portfolios/{id}` | `fl portfolio delete 7 --yes` |
| `duplicate` | `fl portfolio duplicate <portfolio-id> <name>` | zorunlu | `duplicate_portfolio` → `POST /portfolios/{id}/duplicate` | `fl portfolio duplicate 7 "Kopya"` |

#### İşlemler (4)

| Komut | Syntax | Argümanlar / Opsiyonlar | SDK / Endpoint | Örnek |
|---|---|---|---|---|
| `tx add` | `fl portfolio tx add <portfolio-id> <ticker> --type BUY\|SELL --qty <float>` | `--type`, `--qty` zorunlu (>0). Piyasa kapalıysa 400 (SDK mesajı) | `add_transaction` → `POST /portfolios/{id}/transactions` | `fl portfolio tx add 7 THYAO --type BUY --qty 100` |
| `tx list` | `fl portfolio tx list <portfolio-id> [--ticker X] [--type BUY\|SELL] [--start ISO] [--end ISO]` | hepsi opsiyonel filtre | `get_transactions` → `GET /portfolios/{id}/transactions` | `fl portfolio tx list 7 --ticker THYAO` |
| `tx update` | `fl portfolio tx update <portfolio-id> <tx-id> [--price <f>] [--qty <f>]` | en az biri zorunlu | `update_transaction` → `PUT /portfolios/{id}/transactions/{tx_id}` | `fl portfolio tx update 7 12 --price 315.50` |
| `tx undo` | `fl portfolio tx undo <portfolio-id>` | yıkıcı; onay promptu | `undo_transaction` → `DELETE /portfolios/{id}/transactions/undo` | `fl portfolio tx undo 7` |

#### Analizler (11 — salt-okuma, isim komutları)

| Komut | Syntax | Opsiyonlar | SDK / Endpoint | Örnek |
|---|---|---|---|---|
| `valuation` | `fl portfolio valuation <portfolio-id>` | — | `valuation` → `GET …/valuation` | `fl portfolio valuation 7` |
| `diversification` | `fl portfolio diversification <portfolio-id>` | — | `diversification` → `GET …/diversification` | `fl portfolio diversification 7` |
| `performers` | `fl portfolio performers <portfolio-id> [--top 5]` | `--top` default 5 | `performers` → `GET …/performers` | `fl portfolio performers 7 --top 10` |
| `history` | `fl portfolio history <portfolio-id> [--period 1mo]` | `--period`: 1w\|1mo\|3mo\|6mo\|1y\|max | `history` → `GET …/history` | `fl portfolio history 7 --period 6mo` |
| `returns` | `fl portfolio returns <portfolio-id> [--period 1mo]` | — | `returns` → `GET …/returns` | `fl portfolio returns 7` |
| `risk` | `fl portfolio risk <portfolio-id> [--period 1y]` | — | `risk` → `GET …/risk` | `fl portfolio risk 7` |
| `benchmark` | `fl portfolio benchmark <portfolio-id> [--ticker XU100]` | — | `benchmark` → `GET …/benchmark` | `fl portfolio benchmark 7` |
| `performance` | `fl portfolio performance <portfolio-id>` | — | `performance` → `GET …/performance` | `fl portfolio performance 7` |
| `stats` | `fl portfolio stats <portfolio-id>` | — | `stats` → `GET …/stats` | `fl portfolio stats 7` |
| `snapshot` | `fl portfolio snapshot <portfolio-id>` | — | `snapshot` → `GET …/snapshot` | `fl portfolio snapshot 7` |
| `export` | `fl portfolio export <portfolio-id> [--output <path>]` | `--output`: CSV'yi dosyaya yaz (yoksa stdout'a ham CSV) | `export_csv` → `GET …/export/csv` (RAW çıktı) | `fl portfolio export 7 --output portfoy.csv` |

**Çıktı:** analizler anahtar-değer veya küçük tablo; `tx list`/`favorite list` tablo; `export` ham CSV (insan modunda olduğu gibi `--json`'da da CSV metni `{"csv": "…"}` içinde — raw istisna). `--json` → API yanıtı birebir.

---

### 2.6 `fl analysis` — raporlar, simülasyonlar, hisse eşleştirme (13 komut)

Karşılık: `AnalysisResource`. Alt varlıklar: `report`, `simulation`. Kredi harcayanlar: `report generate`, `simulation run`.

```
fl analysis report      generate|info|history|search|get|download
fl analysis simulation  run|cost|estimate|history|get
fl analysis             fit|similar
```

#### Raporlar (6)

| Komut | Syntax | Argümanlar / Opsiyonlar | SDK / Endpoint | Örnek |
|---|---|---|---|---|
| `report generate` | `fl analysis report generate <ticker> --type quick\|deep [--purpose "<soru>"]` | `--type` zorunlu (quick_report/deep_report); `--purpose` opsiyonel (kullanıcının sorusu) | `generate_report` → `POST /reports/generate` (kredi harcar, job-slot 900s) | `fl analysis report generate ASELS --type quick` |
| `report info` | `fl analysis report info` | — (maliyetler + dokümantasyon) | `report_info` → `GET /reports/info` | `fl analysis report info` |
| `report history` | `fl analysis report history [--sort created_at] [--order desc]` | — | `report_history` → `GET /reports/history` | `fl analysis report history` |
| `report search` | `fl analysis report search <q> [--limit 20] [--offset 0] [--sort created_at] [--order desc]` | `<q>` zorunlu (başlık/içerik ILIKE) | `search_reports` → `GET /reports/search` | `fl analysis report search "ASELS çeyrek"` |
| `report get` | `fl analysis report get <report-id>` | zorunlu (markdown içerik) | `get_report` → `GET /reports/{report_id}` | `fl analysis report get 42` |
| `report download` | `fl analysis report download <report-id> --format md\|docx\|pdf [--output <path>]` | `--format` zorunlu; `--output` yoksa cwd'ye `report-<id>.<fmt>` | `download_report` → `POST /reports/download` (RAW dosya) | `fl analysis report download 42 --format pdf` |

#### Simülasyonlar (5)

| Komut | Syntax | Argümanlar / Opsiyonlar | SDK / Endpoint | Örnek |
|---|---|---|---|---|
| `simulation run` | `fl analysis simulation run <ticker> --days <1..370> [--bounds 0.05] [--target <pct>]` | `--days` zorunlu; `--bounds` default `0.05`; `--target` opsiyonel | `simulate` → `GET /simulations/{ticker}` (kredi harcar) | `fl analysis simulation run THYAO --days 30` |
| `simulation cost` | `fl analysis simulation cost` | — (günlük sabit maliyet) | `per_day_cost` → `GET /simulations/per-day-cost` | `fl analysis simulation cost` |
| `simulation estimate` | `fl analysis simulation estimate <ticker> --days <1..370>` | `--days` zorunlu | `estimate_cost` → `GET /simulations/estimate-cost/{ticker}` | `fl analysis simulation estimate ASELS --days 60` |
| `simulation history` | `fl analysis simulation history [--limit 20] [--offset 0]` | `--limit` ≤100 (SDK) | `simulation_history` → `GET /simulations/history` | `fl analysis simulation history` |
| `simulation get` | `fl analysis simulation get <sim-id>` | zorunlu | `simulation_detail` → `GET /simulations/history/{sim_id}` | `fl analysis simulation get 123` |

#### Eşleştirme (2)

| Komut | Syntax | Argümanlar / Opsiyonlar | SDK / Endpoint | Örnek |
|---|---|---|---|---|
| `fit` | `fl analysis fit [--horizon long] [--profitability high] [--risk-tolerance medium] [--limit 5]` | hepsi opsiyonel; SDK default'ları | `fit_stocks` → `POST /stocks/fit` (advisor feature) | `fl analysis fit --risk-tolerance low --limit 10` |
| `similar` | `fl analysis similar <tickers> [--limit 5]` | `<tickers>` zorunlu: virgüllü 1–50 adet (SDK büyük harfe çevirir); `--limit` default 5 | `portfolio_profile` → `POST /portfolio/profile` | `fl analysis similar THYAO,ASELS --limit 10` |

**Çıktı:** `report generate` insan modu → özet blok (report_id, credits_spend, kalan kredi) + raporun markdown'ı (uzunsa başı/sonu, tam metin `--json`'da); `simulation run` → olasılık özeti (prob_above, direction, confidence…); `--json` → API yanıtı birebir. `report get` insan modu → markdown doğrudan stdout.

---

### 2.7 `fl bots` — bot hesapları (3 komut)

Karşılık: `BotsResource` (+ `AuthManager.create_bot` şifre saklama).

| Komut | Syntax | Argümanlar / Opsiyonlar | SDK / Endpoint | Örnek |
|---|---|---|---|---|
| `create` | `fl bots create <username> [--password <pwd>] [--show-password]` | `<username>` zorunlu (max 5 bot/kullanıcı). Şifre verilmezse backend üretir; tek seferlik şifre **güvenli depoya (keyring/FileTokenStore) otomatik kaydedilir ve varsayılan olarak ekrana basılmaz**; `--show-password` ile bir kez gösterilir | `AuthManager.create_bot` → `POST /bots` | `fl bots create bot-1` |
| `list` | `fl bots list` | — | `BotsResource.list` → `GET /bots` | `fl bots list` |
| `delete` | `fl bots delete <bot-id> [--yes]` | yıkıcı; onay promptu / `--yes`; store'daki ilgili şifre de temizlenir | `BotsResource.delete` → `DELETE /bots/{bot_id}` | `fl bots delete 3 --yes` |

**Not:** `login` komutu bu grupta YOKTUR — tek yol `fl auth login --bot <username>` (bölüm 1.2 kural 3). `bot_session` SDK yardımcısı CLI'a yansımaz (süreç içi kavramdır).

**Çıktı:** `create` insan → "Bot oluşturuldu: bot-1 (id 5) — şifre güvenli depoya kaydedildi"; `list` → tablo (id, username, created_at, last_login); `--json` → API yanıtı (`create`'de `password` alanı varsayılan **maskelenir**: `"password": "***"` — tek seferlik şifre `--show-password` ile açılır).

---

### 2.8 `fl export` — veri dışa aktarım (5 komut)

Karşılık: `ExportResource` (poll tabanlı akış). **Akış:** `create` (202, idempotent) → `status` (poll) → `download` (public token). Durumlar: `queued | processing | ready | sent | error`; süresi dolmuş/hazır değilse backend 410.

| Komut | Syntax | Argümanlar / Opsiyonlar | SDK / Endpoint | Örnek |
|---|---|---|---|---|
| `create` | `fl export create <year> [--format csv\|json]` | `<year>` zorunlu; `--format` default `csv` (idempotent: aktif kayıt varsa mevcut id döner; 3 export/saat limiti) | `create_export` → `POST /data/export` | `fl export create 2025` |
| `status` | `fl export status <export-id>` | zorunlu | `get_export` → `GET /data/export/{export_id}` | `fl export status 9` |
| `list` | `fl export list` | — | `list_exports` → `GET /data/export` | `fl export list` |
| `download` | `fl export download <export-id> [--output <path>] [--wait] [--poll-interval 3] [--timeout 300]` | `--wait` (default açık): `ready`/`sent` olana dek poll (SDK `wait_export`); `--output` yoksa cwd'ye `export-<id>.<fmt>`; progress mesajları **stderr**'e | `wait_export` + `download` → `GET /data/export/{id}` + `GET /data/export/download/{token}` | `fl export download 9 --output ./veri.csv` |
| `fetch` | `fl export fetch <year> [--format csv\|json] [--output <path>] [--poll-interval 3] [--timeout 300]` | **Belgelenmiş kompozit**: create (idempotent) → bekle → indir. Tek niyet: "bu yılın verisini indir" | `create_export` + `wait_export` + `download` | `fl export fetch 2025 --format json` |

**Çıktı:** `create` → `{export_id, status}` blok; `status` → kayıt tablosu (id, year, format, status, row_count, size, expires_at…); `list` → tablo; `download`/`fetch` → indirilen dosya yolu (insan) / `{"export_id": 9, "status": "ready", "path": "…", "bytes": 12345}` (JSON). `--json` modunda poll progress'i yine stderr'de kalır; stdout yalnızca sonuç JSON'udur.

---

### 2.9 `fl misc` — halka arz, yasal, meta (14 komut)

Karşılık: `MiscResource`. Alt varlıklar: `ipo`, `announcement`.

| Komut | Syntax | Argümanlar / Opsiyonlar | SDK / Endpoint | Örnek |
|---|---|---|---|---|
| `ipo upcoming` | `fl misc ipo upcoming [--after ISO]` | opsiyonel | `ipos_upcoming` → `GET /ipos/upcoming` | `fl misc ipo upcoming` |
| `ipo draft` | `fl misc ipo draft [--after ISO]` | opsiyonel | `ipos_draft` → `GET /ipos/draft` | `fl misc ipo draft` |
| `ipo active` | `fl misc ipo active [--after ISO]` | opsiyonel | `ipos_active` → `GET /ipos/active` | `fl misc ipo active` |
| `ipo get` | `fl misc ipo get <slug>` | zorunlu (yoksa 404) | `ipo_detail` → `GET /ipos/{slug}` | `fl misc ipo get turkiye-varlik-fonu` |
| `legal` | `fl misc legal <policy> [--lang tr\|en]` | `policy`: terms\|privacy_policy\|cookie_policy\|disclaimer | `legal` → `GET /legal` | `fl misc legal terms` |
| `legal-all` | `fl misc legal-all [--lang tr\|en]` | — | `legal_all` → `GET /legal/all` | `fl misc legal-all` |
| `about` | `fl misc about [--lang tr\|en]` | — | `about` → `GET /about` | `fl misc about` |
| `version` | `fl misc version` | — (API sürümü; yerel sürüm: `fl --version`) | `version` → `GET /version` | `fl misc version` |
| `contact` | `fl misc contact` | — | `contact` → `GET /contact` | `fl misc contact` |
| `contributors` | `fl misc contributors` | — | `contributors` → `GET /contributors` | `fl misc contributors` |
| `maintenance` | `fl misc maintenance` | — | `maintenance` → `GET /maintenance` | `fl misc maintenance` |
| `health` | `fl misc health` | — (prefix'siz kök endpoint) | `health` → `GET /health` | `fl misc health` |
| `announcement list` | `fl misc announcement list` | — (son 7 gün, JWT) | `announcements` → `GET /announcements` | `fl misc announcement list` |
| `announcement get` | `fl misc announcement get <id>` | zorunlu (JWT) | `announcement` → `GET /announcements/{id}` | `fl misc announcement get 3` |

**Çıktı:** `ipo upcoming/draft/active` ve `announcement list` tablo; `legal`/`about`/`contact` metin (uzun metin 40 karakter kırpması YALNIZCA tablo sütunlarında — tam metin her zaman döner); `health` → `Durum: ok`; `--json` → API yanıtı birebir.

---

### 2.10 `fl config` — CLI yerel ayarları (2 komut)

Karşılık: **yok** (SDK endpoint'i değil; `~/.config/florence/config.toml`). T3.2c ile uyumlu.

| Komut | Syntax | Argümanlar / Opsiyonlar | Kaynak | Örnek |
|---|---|---|---|---|
| `show` | `fl config show` | —; etkin değerleri gösterir (config + env + varsayılan birleşimi, kaynağıyla) | config.toml + env | `fl config show` |
| `set` | `fl config set <key> <value>` | `key`: `api_url` (dev override) \| `default_output` (table\|json) | config.toml | `fl config set api_url http://localhost:7055` / `fl config set default_output json` |

**Kurallar:** `last_username`/`last_user_type` config'e CLI tarafından otomatik yazılır (kullanıcı `set` ile dokunmaz — allowlist dışı anahtarlar reddedilir, exit 2). Öncelik: `FLORENCE_API_URL` env > config `api_url` > SDK default; `--json` bayrağı > config `default_output` > varsayılan `table`. `fl config set default_output json` yazmak yerine her komutta `--json` da kullanılabilir — iki yol değildir, biri kalıcı ayar diğeri tek seferlik geçersiz kılmadır.

**Çıktı:** `show` insan → anahtar-değer tablo; `--json` → `{"api_url": {"value": "…", "source": "env"}, "default_output": {"value": "table", "source": "config"}, "last_username": "efe", "store": "keyring"}`.

---

### 2.11 Kapsam doğrulaması — openapi.json (89 path) → komut

İlke: **her path en az bir komutla erişilebilir**; SDK'da bilinçli kapsam dışı bırakılmış path'ler CLI'a da yansımaz (CLI, SDK'nın ince katmanıdır — SDK'da olmayan uca CLI gidemez). İstisnalar aşağıda açıkça işaretlidir.

| openapi.json path | Metod(lar) | Komut |
|---|---|---|
| `/` | GET | `fl misc health` ile aynı uygulama kökü (ayrı komut yok — kök boş nesne döner, `health` yeterli)¹ |
| `/health` | GET | `fl misc health` |
| `/api/v1/about` | GET | `fl misc about` |
| `/api/v1/analytics/event` | POST | **KAPSAM DIŞI (bilinçli)** — fire-and-forget izleme; SDK'da TODO, CLI'da yok |
| `/api/v1/announcements` | GET / POST | GET → `fl misc announcement list`; POST → **KAPSAM DIŞI** (yazma, SDK'da TODO) |
| `/api/v1/announcements/read` | POST | **KAPSAM DIŞI** (okundu işaretleme, SDK'da TODO) |
| `/api/v1/announcements/{id}` | GET / PUT / DELETE | GET → `fl misc announcement get <id>`; PUT/DELETE → **KAPSAM DIŞI** (yazma) |
| `/api/v1/auth/change-email` | PUT | `fl auth change-email` |
| `/api/v1/auth/change-password` | PUT | `fl auth change-password` |
| `/api/v1/auth/change-username` | PUT | `fl auth change-username` |
| `/api/v1/auth/delete` | DELETE | `fl auth delete` |
| `/api/v1/auth/login` | POST | `fl auth login` (+ `--bot`) |
| `/api/v1/auth/logout` | POST | `fl auth logout` |
| `/api/v1/auth/refresh` | POST | (otomatik — CLI komutu yok, client 401'de yapar) |
| `/api/v1/auth/register` | POST | `fl auth register` |
| `/api/v1/auth/resend-verification` | POST | `fl auth resend` |
| `/api/v1/auth/verify-email` | GET | `fl auth verify` |
| `/api/v1/bist/companies` | GET | `fl market companies` |
| `/api/v1/bist/tickers` | GET | `fl market tickers` |
| `/api/v1/bots` | POST / GET | POST → `fl bots create`; GET → `fl bots list` |
| `/api/v1/bots/{bot_id}` | DELETE | `fl bots delete` |
| `/api/v1/companies/info/{ticker}` | GET | `fl market info` |
| `/api/v1/companies/info/{ticker}/md` | GET | `fl market info --md` |
| `/api/v1/companies/search` | GET | `fl market search` |
| `/api/v1/companies/summary` | GET | `fl market summary` |
| `/api/v1/contact` | GET | `fl misc contact` |
| `/api/v1/contributors` | GET | `fl misc contributors` |
| `/api/v1/credits` | GET | `fl account credits` |
| `/api/v1/data/daily/{year}` | GET | **KAPSAM DIŞI (bilinçli)** — 410 Gone, deprecated; SDK'da TODO |
| `/api/v1/data/export` | POST / GET | POST → `fl export create`; GET → `fl export list` |
| `/api/v1/data/export/download/{token}` | GET | `fl export download` (dahili) / `fl export fetch` |
| `/api/v1/data/export/{export_id}` | GET | `fl export status` (+ `download --wait` poll'u) |
| `/api/v1/economy/currency` | GET | `fl economy currency` |
| `/api/v1/economy/gold-prices` | GET | `fl economy gold` |
| `/api/v1/economy/gram-palladium-price` | GET | `fl economy palladium` |
| `/api/v1/economy/gram-platinum-price` | GET | `fl economy platinum` |
| `/api/v1/economy/silver-price` | GET | `fl economy silver` |
| `/api/v1/favorites` | GET | `fl portfolio favorite list` |
| `/api/v1/favorites/{ticker}` | POST / DELETE | POST → `fl portfolio favorite add`; DELETE → `fl portfolio favorite remove` |
| `/api/v1/ipos/active` | GET | `fl misc ipo active` |
| `/api/v1/ipos/draft` | GET | `fl misc ipo draft` |
| `/api/v1/ipos/upcoming` | GET | `fl misc ipo upcoming` |
| `/api/v1/ipos/{slug}` | GET | `fl misc ipo get` |
| `/api/v1/legal` | GET | `fl misc legal` |
| `/api/v1/legal/all` | GET | `fl misc legal-all` |
| `/api/v1/macroeconomy` | GET | `fl economy macro` |
| `/api/v1/maintenance` | GET | `fl misc maintenance` |
| `/api/v1/market/status` | GET | `fl market status` |
| `/api/v1/meta/avatars` | GET | **KAPSAM DIŞI (bilinçli)** — statik varlık listesi; SDK'da TODO |
| `/api/v1/news/{ticker}` | GET | `fl market news` |
| `/api/v1/portfolio/profile` | POST | `fl analysis similar` |
| `/api/v1/portfolios` | POST / GET | POST → `fl portfolio create`; GET → `fl portfolio list` |
| `/api/v1/portfolios/{id}` | GET / PUT / DELETE | GET → `fl portfolio get`; PUT → `fl portfolio rename`; DELETE → `fl portfolio delete` |
| `/api/v1/portfolios/{id}/benchmark` | GET | `fl portfolio benchmark` |
| `/api/v1/portfolios/{id}/diversification` | GET | `fl portfolio diversification` |
| `/api/v1/portfolios/{id}/duplicate` | POST | `fl portfolio duplicate` |
| `/api/v1/portfolios/{id}/export/csv` | GET | `fl portfolio export` |
| `/api/v1/portfolios/{id}/history` | GET | `fl portfolio history` |
| `/api/v1/portfolios/{id}/performance` | GET | `fl portfolio performance` |
| `/api/v1/portfolios/{id}/performers` | GET | `fl portfolio performers` |
| `/api/v1/portfolios/{id}/returns` | GET | `fl portfolio returns` |
| `/api/v1/portfolios/{id}/risk` | GET | `fl portfolio risk` |
| `/api/v1/portfolios/{id}/snapshot` | GET | `fl portfolio snapshot` |
| `/api/v1/portfolios/{id}/stats` | GET | `fl portfolio stats` |
| `/api/v1/portfolios/{id}/transactions` | GET / POST | GET → `fl portfolio tx list`; POST → `fl portfolio tx add` |
| `/api/v1/portfolios/{id}/transactions/undo` | DELETE | `fl portfolio tx undo` |
| `/api/v1/portfolios/{id}/transactions/{tx_id}` | PUT | `fl portfolio tx update` |
| `/api/v1/portfolios/{id}/valuation` | GET | `fl portfolio valuation` |
| `/api/v1/price/current` | GET | `fl market price` |
| `/api/v1/price/history/{ticker}` | GET | `fl market history` |
| `/api/v1/profile` | GET | `fl account profile` |
| `/api/v1/profile/avatar` | PUT | `fl account avatar` |
| `/api/v1/reports/download` | POST | `fl analysis report download` |
| `/api/v1/reports/generate` | POST | `fl analysis report generate` |
| `/api/v1/reports/history` | GET | `fl analysis report history` |
| `/api/v1/reports/info` | GET | `fl analysis report info` |
| `/api/v1/reports/search` | GET | `fl analysis report search` |
| `/api/v1/reports/{report_id}` | GET | `fl analysis report get` |
| `/api/v1/simulations/estimate-cost/{ticker}` | GET | `fl analysis simulation estimate` |
| `/api/v1/simulations/history` | GET | `fl analysis simulation history` |
| `/api/v1/simulations/history/{sim_id}` | GET | `fl analysis simulation get` |
| `/api/v1/simulations/per-day-cost` | GET | `fl analysis simulation cost` |
| `/api/v1/simulations/{ticker}` | GET | `fl analysis simulation run` |
| `/api/v1/stats/top` | GET | `fl market top` |
| `/api/v1/stats/{ticker}` | GET | `fl market stats` |
| `/api/v1/stocks/fit` | POST | `fl analysis fit` |
| `/api/v1/user/export` | GET | `fl account export` |
| `/api/v1/user/preferences` | GET / PUT | GET → `fl account preferences`; PUT → `fl account preferences set` |
| `/api/v1/version` | GET | `fl misc version` |
| *(admin uygulaması — X-Admin-Token, ayrı FastAPI app)* | — | **KAPSAM DIŞI** (openapi.json'da yok) |

¹ Kök path `/` için ayrı komut eklemek gereksizliktir (boş nesne döner); erişim `fl misc health` ile aynı transport üzerinden sağlanır. İstenirse `fl misc health` çıktısına kök erişim testi eklenebilir — komut sayısı artmaz.

**Kapsam dışı özet (6 path / 10 metod):** `analytics/event` (1), `announcements` yazma + `read` (4), `announcements/{id}` PUT+DELETE (2), `meta/avatars` (1), `data/daily/{year}` (1), admin app (openapi dışı). Hepsi `misc_res.py` TODO notlarıyla SDK'da bilinçli dışarıda — CLI aynı sınırı korur.

---

## 3. Global Kurallar

### 3.1 `--json` davranışı

- Her komutta geçerli (global). `--json` verildiğinde **stdout'a yalnızca tek bir JSON belgesi** yazılır (nesne veya dizi) — başka hiçbir şey stdout'a karışmaz.
- **Veri:** API yanıtının normalize edilmiş hali birebir ("JSON çıktısı = API şeması" ilkesi, bölüm 2.0). Yerel durum komutları (`auth status`, `config show`) ve kompozitler (`export fetch`) kendi stabil şemalarını tanımlar.
- **Hata (çalışma):** `--json` modunda hatalar da makine-okunur olmalıdır — **stderr**'e tek JSON satırı:

  ```json
  {"error": {"code": "error_login_failed", "status": 401, "detail": "Kullanıcı adı veya şifre hatalı"}}
  ```

  - `code`: SDK `FlorenceAPIError.code` (backend i18n kodu, ör. `error_login_failed`) — veya yerel kodlar: `not_authenticated` (401/refresh yok), `rate_limited` (429), `network` (bağlantı), `timeout` (export poll vb.), `not_found` (404).
  - `status`: HTTP durum kodu (yerel hatalarda `null` veya 0 yerine yoksa alan `null`).
  - `detail`: Türkçe, insan-okur açıklama (SDK mesajı veya CLI tarafı).
  - exit code yine 1'dir (kullanım hataları 2, aşağıda).
- **Kullanım hatası (exit 2):** typer'ın standart hata çıktısı stderr'e gider; `--json`'da da aynı kural geçerlidir (makine tüketicisi exit code 2'yi "komut yanlış kullanıldı" olarak okur). İstisna: prompt gerektiren durumda `--json` modunda prompt SORULMAZ — "Bu komut interaktif onay gerektiriyor; `--yes`/`--password` bayrağını kullanın" biçiminde JSON hata + exit 2.

### 3.2 Exit code'lar

| Code | Anlam | Örnekler |
|---|---|---|
| `0` | Başarı | her komut, `--json` dahil |
| `1` | Çalışma hatası | `AuthError`, `RateLimitError`, `NetworkError`, `FlorenceAPIError`, export timeout, keyring/FileTokenStore açılamadı |
| `2` | Kullanım hatası | bilinmeyen komut/bayrak, eksik zorunlu argüman, geçersiz `--type`/`--period`/`--format` değeri, config `set`'te allowlist dışı anahtar, `--json`+prompt çakışması |

Sinyal/kesinti (Ctrl+C) → 130 (standart), ayrıca ele alınmaz.

### 3.3 stdout = veri / stderr = hata

- **stdout:** yalnızca komutun ürettiği veri (tablo, metin veya `--json` belgesi).
- **stderr:** hatalar, uyarılar, progress/poll mesajları (`fl export download`'ın "Bekleniyor… durum: processing" satırları), loglar (`--verbose`).
- Bu ayrım `--json` için zorunludur (pipe edilebilirlik: `fl market price THYAO --json | jq '.price'` her zaman çalışır).

### 3.4 Tablo çıktı kuralları

- rich `Table`; sütun seçimi her komut için sabittir (yukarıda her grupta belirtildi).
- **Uzun metin:** tablo hücrelerinde 40 karakterde kırpılır + `…`; tam değer her zaman `--json`'da veya tek-kayıt komutlarında (`fl market info`) döner.
- **Sayılar:** 2 ondalık, TR binlik ayracı (nokta) — `1.234,50`. Fiyat/hacim gibi büyük değerler `--json`'da ham sayı (çeviri yok).
- **Ekonomi değerleri:** backend string + Türk virgüllü (`"40,25"`) → insan tablosunda aynen, `--json`'da **float** (`40.25`). CLI bunu sunum katmanında yapar, SDK'ya dokunmaz.
- **Renk:** sadece TTY'de; pipe'ta renk kapalı (rich auto-detect).
- **Boş liste:** "Kayıt yok" mesajı, tablo basılmaz; `--json`'da boş dizi `[]`.

### 3.5 Pagination / limit

- Listeleme komutları `--limit` / `--offset` taşır; varsayılanlar SDK'dan birebir: `market companies|summary|top` 50, `market news` 10, `analysis report search` 20, `analysis simulation history` 20, `report history` (SDK'da limitsiz — CLI `--limit` ekler, default 20).
- Backend sınırları korunur: `simulation estimate --days` 1–370, `simulation history --limit` ≤100, `similar --limit` ≤50, `similar` ticker adedi 1–50.
- Sayfalama görünümü: `--limit 20 --offset 40` (offset tabanlı, backend böyle).

### 3.6 Ticker doğrulama

- Tüm `<ticker>` argümanları CLI'da **büyük harfe çevrilir** (backend zaten alias destekler; CLI küçük harf görürse uyarı: "Ticker büyük harfe çevrildi: thyao → THYAO" — stderr).
- Biçim kontrolü: `^[A-Z0-9.\-]{1,12}$` (BIST: `THYAO`, `TUPRS`, `XU100`, `.E` sonekleri vb.). Uymayan değer hard-fail DEĞİLDİR — backend'e bırakılır (alias'lar olabilir), sadece uyarı.
- Virgüllü ticker listeleri (`--tickers`, `similar`) aynı kuralı her öğeye uygular.

### 3.7 Config dosyası ve env önceliği

`~/.config/florence/config.toml` (T3.2c):

```toml
[cli]
api_url = "https://api.florencex.com.tr"   # dev override
default_output = "table"                    # table | json
last_username = "efe"                       # CLI tarafından otomatik yazılır
last_user_type = "user"                     # user | bot (auth status için)
```

**Öncelik sırası (yüksekten düşüğe):**
1. `FLORENCE_API_URL` env → 2. config `api_url` → 3. SDK default (`https://api.florencex.com.tr`).
2. `FLORENCE_TOKEN` env (salt-okunur access token override, token store'dan önce).
3. `FLORENCE_KEYRING=0` (veya dbus yok) → `FileTokenStore` (`~/.config/florence/tokens.json`, Fernet şifreli, chmod 600 — T3.2b). Keyring çalışıyorsa `KeyringTokenStore` (servis `florence-sdk`).
4. `--json` bayrağı → config `default_output` → varsayılan `table`.
5. `FLORENCE_TIMEOUT_*` env'leri SDK'ya olduğu gibi devreder.

**Güvenlik:** token'lar config.toml'a YAZILMAZ (config yalnızca tercih; token'lar keyring/şifreli dosyada). Şifre/token hiçbir komutta loglanmaz/print edilmez (SDK kuralı CLI'da da geçerli).

### 3.8 İnteraktif prompt kuralları

- Şifre prompt'ları `getpass` (gizli, echo yok): `login` (kullanıcı), `register` (çift), `change-password` (mevcut+yeni çift), `change-email`/`change-username` (mevcut şifre).
- Onay prompt'ları (yıkıcı): `auth delete`, `portfolio delete`, `portfolio tx undo`, `bots delete` → `[y/N]`, yanlış girişte iptal (exit 1, "İptal edildi").
- Prompt yalnızca **TTY varsa** sorulur; TTY yoksa veya `--json` verilmişse prompt yerine hata (exit 2, eksik bayrak mesajı) — script'lerde sürpriz bekleme olmaz.
- `--password`/`--yes` bayrakları prompt'ları baypas eder (script/AI dostu).

---

## 4. Dosya Düzeni (`src/florence/cli/`)

Planın önerdiği iskeletin (commands_auth/data/analysis/export) refine edilmiş hali — her modül tek sorumluluk:

```
src/florence/cli/
├── __init__.py           # boş (paket işareti)
├── app.py                # Typer app kurulumu: grupların kaydı, global --json/--verbose,
│                         # hata yakalayıcı (FlorenceError → exit 1 + --json hata formatı),
│                         # entry point'ler: main() (florence + fl aynı fonksiyon)
├── context.py            # ClientFactory: config/env/FLORENCE_KEYRING'den FlorenceClient üretimi,
│                         # store seçimi (keyring / FileTokenStore / env override), bağlam nesnesi
├── output.py             # Çıktı katmanı: emit_json() (stdout tek JSON), render_table() (rich),
│                         # normalize_* yardımcıları (ekonomi string→float, TR sayı, kırpma),
│                         # format_error() → {error:{code,status,detail}} (stderr)
├── interactive.py        # getpass sarmalayıcıları, confirm() [y/N], TTY/--json denetimi
├── config_cli.py         # CLI config.toml: yükle/birleştir/kaydet, allowlist (api_url,
│                         # default_output), last_username/last_user_type yazımı; SDK config.py ile
│                         # KARIŞMAZ (o transport içindir)
├── commands_auth.py      # auth grubu (10 komut) + account grubu (6 komut)
├── commands_market.py    # market grubu (11 komut) + economy grubu (6 komut)
├── commands_portfolio.py # portfolio grubu (24 komut)
├── commands_analysis.py  # analysis grubu (13 komut)
├── commands_export.py    # export grubu (5 komut, poll akışı) + bots grubu (3 komut)
└── commands_misc.py      # misc grubu (14 komut) + config grubu (2 komut)
```

- Her `commands_*.py` bir typer `Typer()` alt-uygulaması döndürür; `app.py` hepsini `app.add_typer(..., name=...)` ile bağlar. Komutlar yalnızca SDK'yı çağırır; SDK olmayan tek mantık: çıktı sunumu, prompt, config, kompozit akış (`export fetch`).
- Testler `tests/` altında `cli/` klasörü: CliRunner + mock transport; `--json` çıktısı `json.loads` ile doğrulanır.
- `pyproject.toml` entry point ikilisi:
  ```toml
  [project.scripts]
  florence = "florence.cli.app:main"
  fl = "florence.cli.app:main"
  ```

---

## 5. Anti-Patterns / Kaçınılanlar

| Anti-pattern | Örnek (KAÇINILDI) | Tasarımdaki çözüm |
|---|---|---|
| **Alias isimlendirme tutarsızlığı** | `fl price` ile `fl market price`'ın birlikte var olması; `fl sim` gibi kısaltmalar | Tek desen `<grup> <komut>`; komut seviyesinde alias yok; tek istisna onaylı `fl`/`florence` entry-point ikilisi |
| **`--json` ile `--format` çakışması** | `--json` (çıktı modu) ile `--format json` (içerik formatı) aynı şey sanılır | Çıktı modu yalnızca global `--json`; `--format` yalnızca **içerik** biçimi (report download md/docx/pdf, export csv/json) — asla çıktı biçimi değil |
| **Gereksiz bayrak** | plan taslağındaki `fl scout fit --cash 100000` — SDK `fit_stocks`'ta `cash` yok | SDK parametresi olmayan bayrak eklenmez; `fit` yalnızca horizon/profitability/risk-tolerance/limit alır |
| **Aynı işi yapan iki komut** | `fl bots login` + `fl auth login --bot`; `fl export create` + `fl export fetch`'in ayrı niyet olmadan çiftlenmesi | Bot girişinin tek yolu `fl auth login --bot`; `fetch` = belgelenmiş kompozit (create→wait→download), `create` değil |
| **Kısa bayrak karmaşası** | `-p`, `-t`, `-f` tek harflerinin komutlar arasında farklı anlamlar taşıması | Kısa bayrak hiç yok; tüm bayraklar uzun ve açık (`--type`, `--period`, `--format`) |
| **İnteraktif sürpriz** | `--json` modunda şifre/onay prompt'unun script'i kilitlemesi | `--json` + TTY yoksa prompt sorulmaz; zorunlu bayrakla hata + exit 2 |
| **stdout kirliliği** | progress/log'ların veriyle aynı akışa karışması (`fl export download` çıktısı `jq`'ya giremez) | stdout=veri, stderr=progress/hata; `--json`'da tek JSON belgesi kuralı |
| **Path kopyalama isimlendirme** | `fl misc legal-all` yerine `fl legal all`; `fl portfolio export-csv` yerine teknik ad | Komut = kullanıcı niyeti; endpoint path'i yalnızca kapsam tablosunda referanstır |
| **Şema drift'i** | CLI'ın kendi "temiz" JSON şeması icat edip openapi'den kopması | "JSON çıktısı = API şeması" ilkesi; tek JSON belgesi, ek sarma yok |

---

## 6. Açık Karar Noktaları (kullanıcı onayı)

1. **Rapor tipi komutu:** `fl analysis report generate ASELS --type quick` (öneri — tek komut, tip bayrağı; "her komut tek iş" ilkesine uyar) **mi**, yoksa kullanıcının hayalindeki `fl report quick ASELS` / `fl report deep ASELS` alt komut deseni mi? Öneri: `--type` bayrağı; alt komut deseni seçilirse `quick`/`deep` komutları `generate --type …`'ın eş anlamlısı olur (anti-pattern riski).
2. **`fl download ASELS 3m` hayali:** Bu kalıp tek endpoint'e birebir oturmuyor — veri dışa aktarımı **yıllık** (`/data/export`, `fl export fetch 2025`), hisse bazlı değil. Seçenekler: (a) yalnızca `fl export fetch <year>` (öneri — SDK gerçeğiyle birebir), (b) ayrıca `fl market history ASELS --period 3m --output file.csv` kompoziti (hisse bazlı indirme; SDK'da doğrudan CSV ucu yok, CLI tarafında tablo→CSV yazımı gerekir — ek iş). Hangi kapsam?
3. **`fl auth status`'ta tip (user/bot) bilgisi:** öneri — login sırasında `last_user_type`'ı config'e yaz (çevrimdışı, T3.2d'yi karşılar). Alternatif: status her çağrıda `GET /profile`'dan canlı `user_type` okur (doğru ama ağ ister). Hangisi?
4. **Kısa bayrak yasağı:** hiç kısa bayrak yok (öneri). `-j` gibi tek istisna istenir mi? (Öneri: hayır — tutarlılık, çakışma imkânsızlığı.)
5. **Yıkıcı komut onayları:** `auth delete`, `portfolio delete`, `portfolio tx undo`, `bots delete` → onay promptu + `--yes`; `--json` modunda prompt yerine hata. Bu set yeterli mi, `favorite remove` gibi hafif işlemlere de onay istenir mi? (Öneri: hayır, listedeki 4 komut yeterli.)
6. **`default_output` varsayılanı:** `table` (öneri — insan öncelikli; script'ler her zaman `--json`) mi, `json` mu?

---

### Ek: Komut sayısı özeti

| Grup | Komut |
|---|---|
| auth | 10 |
| account | 6 |
| market | 11 |
| economy | 6 |
| portfolio | 24 |
| analysis | 13 |
| bots | 3 |
| export | 5 |
| misc | 14 |
| config | 2 |
| **Toplam** | **94** |

---

## 8. KARARLAR (2026-08-14 — kullanıcı onayı)

1. **Analysis grubu DÜZLEŞTİRİLDİ:** `fl report <ticker> [--deep]` (default quick) +
  alt komutlar (search/history/get/download/info); `fl simulate <ticker> --days N` +
  alt komutlar (cost/estimate/history/get); `fl fit`, `fl similar` üst seviyede.
  Diğer gruplar tasarımdaki gibi (çakışma gerekçesiyle: status/history/version/export).
2. **`fl price` kısa yolu:** `fl price <ticker> [--interval]` (güncel) ve
  `fl price history <ticker> [period] [interval]` — period/interval KONUMSAL olabilir
  (örn. `fl price history ASELS 3mo 5m`), `--period/--interval` bayrakları da var;
  default period 3mo, interval 5m. `fl market price/history` de çalışır.
3. **`fl download <ticker> <period>` = HİSSE MUM CSV'si** (price history → CSV dosyası).
  Yıllık veri export'u ayrıdır: `fl export ...`.
4. **Kalıcı auth:** username store'a yazılır (T3.2a); FileTokenStore Fernet şifreli
  (T3.2b); config.toml api_url/default_output/last_username/last_type (T3.2c);
  `fl auth login --bot` (T3.2d); akış testleri (T3.2e).
5. **Kısa bayrak yok** (tek-harf bayrak kullanılmaz).
6. **Yıkıcı onay seti:** auth delete, portfolio delete, tx undo, bots delete
  (prompt + `--yes`; `--json`'da `--yes` zorunlu).
7. **`default_output` = table** (insan öncelikli; script'ler `--json`).
8. **Ekonomi değerleri** `"40,25"` → `40.25` normalize (sunum katmanında; SDK ham döndürür).
9. **Canlı backend doğrulaması (2026-08-14):** middleware /api/v1'in tamamını korur —
  public allowlist DIŞINDAKİ tüm uçlar token ister. Market (market/status hariç),
  economy ve ipo resource'ları `auth=True`'a çevrildi.
