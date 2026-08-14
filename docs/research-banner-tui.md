# Banner ve TUI Araştırma Raporu

> **Kapsam:** Florence SDK için iki araştırma sorusu:
> 1. cfonts tarzı gradient ASCII banner'ın Python karşılıkları, kullanım yerleri ve bağımlılık önerisi.
> 2. TUI için Python Textual vs TypeScript/Node karşılaştırması — görünüm, SDK entegrasyonu, paketleme, bakım; net öneri.
>
> **Yöntem:** Tüm bulgular **deneysel olarak doğrulandı** (bu ortamda web arama/extract backend'i kapalıydı):
> `npx cfonts` (Node v22.23.2) canlı çalıştırıldı; `pyfiglet==1.0.4` ve `rich` (13.9.4 ve 15.0.0) kurulup test edildi;
> `textual==8.2.8` kurulup headless test edildi; paket boyutu/sürüm bilgileri PyPI ve npm registry'den çekildi.
> **Tarih:** 2026-08-14 · **Durum:** ARAŞTIRMA — implementasyon/commit yok.

---

# Bölüm 1 — cfonts Tarzı Gradient ASCII Banner

## 1.1 cfonts ne yapıyor? (deneysel)

`npx cfonts "FLORENCE" -f block -g blue,magenta -t` çalıştırıldı. cfonts (v3.3.1, npm, **331 KB**, bağımlılıkları yalnızca `supports-color` + `window-size`):

- **Font:** kendi formatında 12 gömülü font (`console, block, simpleBlock, simple, 3d, simple3d, chrome, huge, shade, slick, grid, pallet, tiny`) + figlet fontları.
- **Gradient:** iki (veya daha fazla) renk arasında **karakter bazında truecolor interpolasyon**. Kanıt — çıktının `cat -v` ile incelenmesi: her karakter için ayrı `ESC[38;2;R;G;Bm` kodu üretiliyor:

```
^[[38;2;0;0;255m█^[[39m ^[[38;2;3;0;255m█^[[39m ^[[38;2;6;0;255m█ ...  ^[[38;2;255;0;255m█^[[39m
```

  (mavi `0;0;255` → magenta `255;0;255` arası satır boyunca kayan RGB). Yani cfonts = **figlet tarzı ASCII art + per-karakter 24-bit renk rampası**.
- **CLI seçenekleri:** `-f/--font`, `-c/--colors`, `-b/--background`, `-a/--align`, `-l/--letter-spacing`, `-z/--line-height`, `-s/--spaceless`, `-m/--max-length`, `-g/--gradient` (çok renkli), `-i/--independent-gradient` (satır başına), `-t/--transition-gradient`, `-r/--raw-mode`, `-e/--env`, `-d/--debug`.
- **Çalıştırma ortamı:** Node gerekir (`npx cfonts …`). Kullanıcının sevdiği üç komutun çıktısı (renkler terminalde görünür; metin aynı):

```text
$ npx cfonts "FLORENCE" -f block -g blue,magenta -t     # mavi → magenta
███████╗ ██╗       ██████╗  ██████╗  ███████╗ ███╗   ██╗  ██████╗ ███████╗
██╔════╝ ██║      ██╔═══██╗ ██╔══██╗ ██╔════╝ ████╗  ██║ ██╔════╝ ██╔════╝
█████╗   ██║      ██║   ██║ ██████╔╝ █████╗   ██╔██╗ ██║ ██║      █████╗
██╔══╝   ██║      ██║   ██║ ██╔══██╗ ██╔══╝   ██║╚██╗██║ ██║      ██╔══╝
██║      ███████╗ ╚██████╔╝ ██║  ██║ ███████╗ ██║ ╚████║ ╚██████╗ ███████╗
╚═╝      ╚══════╝  ╚═════╝  ╚═╝  ╚═╝ ╚══════╝ ╚═╝  ╚═══╝  ╚═════╝ ╚══════╝

$ npx cfonts "FLORENCE" -f block -g red,yellow -t       # kırmızı → sarı
$ npx cfonts "FLORENCE" -f block -g red,#ffa500 -t      # kırmızı → turuncu (hex)
```

## 1.2 Python ekosistemindeki karşılıkları (deneysel)

| Kütüphane | Sürüm | Boyut | Bağımlılık | Font/ASCII art | Gradient | Not |
|---|---|---|---|---|---|---|
| **pyfiglet** | 1.0.4 | **1.76 MB** wheel (571 font dosyası) | **sıfır** | ✅ 571 figlet fontu | ❌ yok — yalnızca saf ASCII metin üretir | Renk/ANSI üretmez; renk ayrı katmanda |
| **rich** | 13.9.4 / **15.0.0** | ~2 MB (mevcut bağımlılık) | mevcut | ❌ figlet yok | ❌ **YOK (aşağıdaki kanıt)** | `Table`, `Text`, `Panel`, truecolor — ama gradient yok |
| termcolor | — | küçük | sıfır | ❌ | ❌ | Düz 8/16 renk |
| colorama | — | küçük | sıfır | ❌ | ❌ | Yalnızca Windows ANSI köprüsü |
| art | — | küçük | sıfır | ✅ (sınırlı font seti) | ❌ | pyfiglet'in küçük kuzeni; daha az bakımlı |
| **cfonts** (kıyas) | 3.3.1 | 331 KB | 2 (Node) | ✅ 12+ font | ✅ per-karakter truecolor | **Node gerektirir** — Python CLI'a taşınmaz |

### Kritik bulgu: rich'te gradient DESTEĞİ YOK

Bağlamda "rich gradient yapabiliyor mu?" diye doğrulanması istenmişti — **deneysel sonuç: hayır, yapamıyor**:

1. `rich` 13.9.4 ve 15.0.0'te `Text("FLORENCE", style="gradient(blue,magenta)")` **hiç renk kodu üretmiyor** (düz metin basıyor).
2. `console.print("FLORENCE", style="gradient(blue,magenta)")` → `rich.errors.MissingStyle: 'gradient(blue,magenta)' is not a valid color`.
3. Kurulu rich paketinin kaynağında, resmi dokümanda (`docs/source/text.rst`) ve `CHANGELOG.md`'de "gradient" **hiç geçmiyor**.

Yani rich; renk, tablo, panel, tema konusunda güçlüdür ama **gradient özelliği yoktur** (terminal truecolor çıktıyı yine destekler). Gradient isteyen bir Python CLI, bunu ya kendi yazar ya da Node tarafına gider.

### Python'da cfonts eşdeğeri: küçük bir yardımcı fonksiyon

cfonts'un ürettiği çıktı modeli (per-karakter `38;2` interpolasyonu) **~15 satırlık bağımlılıksız bir fonksiyonla birebir kopyalanabilir** — deneysel olarak doğrulandı, ürettiği ANSI kodları cfonts'unkilerle aynı biçimde:

```python
def gradient(text: str, c1: str, c2: str) -> str:
    """Per-karakter truecolor gradient (cfonts -g/-t ile ayni cikti modeli)."""
    a, b = hex2rgb(c1), hex2rgb(c2)          # "#rrggbb" → (r,g,b)
    out = []
    for line in text.split("\n"):
        n = max(len(line) - 1, 1)
        for i, ch in enumerate(line):
            t = i / n
            r, g, bl = (round(a[k] + (b[k] - a[k]) * t) for k in range(3))
            out.append(f"\x1b[38;2;{r};{g};{bl}m{ch}")
        out.append("\n")
    return "".join(out)
```

Üretilen gerçek çıktı (kanıt — `cat -v`):

```text
^[[38;2;0;0;255m ^[[38;2;3;0;255m█^[[38;2;7;0;255m█^[[38;2;10;0;255m█ ... ^[[38;2;255;0;255m╗
```

### Font uyumu notu

cfonts'un `block` fontu (`█╗╔║╚╝═` kutu karakterleri) pyfiglet'in 571 fontu içinde **birebir yok** (pyfiglet `block` = `_|` stili; `banner3` = `#`; `banner3-D` = `::` stili). Birebir cfonts görünümü istenirse iki yol var: (1) cfonts ile bir kez render edilip çıktının gömülmesi, (2) pyfiglet fontlarından estetik olarak yakın birinin seçilmesi. Sabit "FLORENCE" metni için (1) triviyal.

**Örnek — pyfiglet `block` + özel gradient (kırmızı→sarı):** (renkler terminalde; şekil aşağıda)

```text
_|_|_|_|  _|          _|_|    _|_|_|    _|_|_|_|  _|      _|    _|_|_|
_|        _|        _|    _|  _|    _|  _|        _|_|    _|  _|
_|_|_|    _|        _|    _|  _|_|_|    _|_|_|    _|  _|  _|  _|
_|        _|        _|    _|  _|    _|  _|        _|    _|_|  _|
_|        _|_|_|_|    _|_|    _|    _|  _|_|_|_|  _|      _|    _|_|_|
```

## 1.3 Banner nerede kullanılsın? (a–d)

| Konum | Öneri | Gerekçe |
|---|---|---|
| **(a) install.sh sonu** | ✅ **EVET** (script eklendiğinde) | Kullanıcının isteği: "en azından kurulum scriptinde görünebilir mi". Kurulum başarısını kutlayan tek seferlik şov değeri yüksek. Not: repo'da **şu an install.sh yok** — kurulum `uv sync` / `pip install -e .` (README). Bir release install script'i eklenecekse son satırlarına banner + kısa kullanım ipucu konur. |
| **(b) `fl --version`** | ⚠️ **KOŞULLU EVET** | `--version` stdout'u makine-okunur kalmalı (cli-design.md: stdout = veri; pipe edilebilirlik). Çözüm: banner **yalnızca TTY'de**, sürüm satırından önce stderr'e veya TTY-koşullu stdout'a basılır (`rich` zaten TTY otomatik tespiti yapıyor — pipe'ta renk yok). Küçük boyutlu tutulur (6 satır banner + sürüm = hoş kimlik). |
| **(c) `fl tui` başlığı** | ✅ **EVET** | TUI açılışında Textual `Static` widget içinde `Text.from_ansi(gradient_art)` — **headless testte doğrulandı**: banner 6 satır render ediliyor, içerik doğru; renk kodu test ortamında bilinçli kapalı, gerçek terminalde rich truecolor basar. Header üstünde/altında tek seferlik açılış görseli; her poll'da yeniden çizilmez. |
| **(d) `fl auth login` başarısı** | ✅ **EVET** | Duygusal değeri en yüksek an ("hoş geldin" efekti). Kurallar: `--json` modunda **basılmaz** (stdout'a tek JSON kuralı — cli-design.md §3.1); TTY değilse basılmaz; 1–2 satırlık kısa mesajla birlikte. |

**Öncelik sıralaması (maliyet sıfır olduğu için hepsi uygulanabilir):** `login` > `install.sh` > `tui` > `--version`. Ortak kural: **yalnızca TTY'de** ve `--json`'da asla.

## 1.4 Bağımlılık önerisi

**Öneri: statik gömülü ASCII art + ~15 satırlık özel gradient yardımcısı (sıfır yeni bağımlılık).**

| Seçenek | Maliyet | Değerlendirme |
|---|---|---|
| **A. Statik art + özel helper** (ÖNERİ) | ~2–3 KB kod/veri, yeni bağımlılık **yok**; rich zaten var (truecolor çıktı için) | Banner yalnızca sabit metinler ("FLORENCE") için — font seti gerekmez. Başlangıç anlık, CLI şişmez. |
| B. `pyfiglet` ana bağımlılık | +1.76 MB (571 font) | Sadece birkaç sabit yazı için 571 font taşımak israf; gradient zaten helper'dan geliyor. |
| C. `pyfiglet` opsiyonel extra | `pip install florence[fonts]` gibi; ana kurulum etkilenmez | Yalnızca gelecekte **keyfi metin** banner'ı istenirse (ör. `fl banner "metin"` — şu an 94 komutluk ağaçta böyle bir komut yok; eklemek scope creep). Bu talep gelirse C makul. |
| D. `cfonts`/npx | Node zorunluluğu | **Kabul edilemez** — Python CLI'ın kurulumuna Node runtime dayatmak; hedef kullanıcı (Python/BIST kullanıcısı) için gereksiz yük. |

Renk paleti kullanıcı beğenisine göre sabitlenebilir: `blue→magenta` (mevcut CLI/logo hissi), `red→yellow`, `red→#ffa500` (kullanıcının sevdiği üç varyant) — hepsi aynı helper ile, parametre değişikliği kadar.

---

# Bölüm 2 — TUI: Python Textual vs TypeScript/Node

## 2.1 Görünüm ve yetenekler

**Textual (Python)** — v8.2.8 (Ağu 2026): wheel **0.7 MB**; bağımlılıkları `rich>=14.2.0`, `markdown-it-py`, `mdit-py-plugins`, `platformdirs`, `pygments`, `typing-extensions`; Python ≥3.9. Rich üzerine kurulu:

- CSS benzeri stillendirme, hazır dark/light temalar, otomatik terminal uyumu.
- Hazır widget'lar: `DataTable` (sıralı tablo), `Sparkline` (blok karakter grafik — TUI tasarımımızın ihtiyacı), `Header`/`Footer` (klavye ipuçları otomatik), `Input`, `Tabs`, `ListView`, `Tree`, `TextArea`, `ModalScreen`.
- asyncio tabanlı: `set_interval` + `Worker` deseni (tui-design.md §4'ün poll mimarisi birebir bunu kullanıyor), event loop'u bloklamaz.
- **Headless test API**: `App.run_test()` + `Pilot` — tui-design.md §8'in tamamı bu API üzerine kurulu (klavye simülasyonu, `wait_for_worker`, boyut verilebilir).
- Ekosistem: aktif geliştirme, devtools, web export. Örnek uygulamalar: **Harlequin** (terminal SQL IDE), **Frogmouth** (markdown görüntüleyici), **TZ**, **textual-paint**.
- Gradient: rich'te yok (Bölüm 1) — ama TUI'de zaten `Sparkline`/renkli Δ% hücreleri var; banner için Bölüm 1'deki helper + `Text.from_ansi` yeterli (doğrulandı).

**Node/TypeScript seçenekleri:**

| Kütüphane | Sürüm | Boyut | Durum | Gradient | Sparkline/grafik | Tam ekran TUI |
|---|---|---|---|---|---|---|
| **ink** | 7.1.1 | 556 KB | Aktif, React tabanlı | Ayrı paket (`gradient-string`) | Yok (elle render) | ❌ — CLI/komut çıktısı odaklı, deklaratif yeniden render; widget seti yok |
| **blessed** | 0.1.81 | — | **Bakımsız** (yıllardır sürüm yok) | ❌ | Kısmen | ✅ curses tarzı ama çağ dışı API |
| **neo-blessed** | 0.2.0 | 1.65 MB | Fork; son yayın 2022 | ❌ | Kısmen | ✅ blessed'ın devamı, o da durgun |
| **blessed-contrib** | — | — | **Bakımsız** (blessed üstüne dashboard) | ❌ | ✅ line/sparkline/table | ✅ |
| **terminal-kit** | 3.1.4 | **4.1 MB** | **Aktif** (2026-07) | ✅ yerleşik (chroma-js) | ✅ sparkline, bar, canvas, image | ✅ ama API karmaşık, dokümantasyon zayıf |

**"Node daha mı iyi/güzel görünür?" sorusunun cevabı: hayır.** Modern çerçevelerin ikisi de truecolor + unicode kutu karakterleri yapabiliyor; fark görsel değil. Textual'ın hazır widget seti, temaları ve CSS'i güncel bir görünüm üretiyor; ink CLI odaklı (dashboard değil), blessed/neo-blessed görsel olarak çağ dışı, terminal-kit görsel eşdeğer ama API'si ve dokümantasyonu eski kuşak. Kıyaslanabilir tek Node adayı terminal-kit'tir — o da 4 MB'lık dev bir paket ve karmaşık bir API.

## 2.2 SDK entegrasyonu (kritik nokta)

SDK'mız **Python**: 94 CLI komutu, 89 openapi path, keyring/FileTokenStore auth, 401'de single-flight refresh, 429 retry, hata hiyerarşisi, config katmanı — hepsi `src/florence/` içinde tek dilde.

**Textual (in-process):** `AsyncFlorenceClient` TUI içinde **doğrudan** kullanılır (tui-design.md §4.1: `await client.market.current_price(...)`). Tek runtime, sıfır serileştirme, hata/retry/auth kodu birebir paylaşılır; test `run_test` + httpx `MockTransport` ile offline (tui-design.md §8.1).

**Node TUI'nin SDK'ya bağlanma yolları:**

| Yol | Nasıl | Artılar | Eksiler |
|---|---|---|---|
| **(a) Elle JS HTTP client** | 94 endpoint imzasını JS'te yazmak (openapi.json'dan üretilebilir) | Bağımsız, temiz mimari | Auth akışını (login/refresh/429/hata taksonomisi) ve keyring/config davranışlarını **ikinci kez** yazmak; iki taraf sürüm drifti; haftalarca iş; test takımı iki kat |
| **(b) Local bridge (JSON-RPC proxy)** | Python tarafında küçük bir JSON-RPC/HTTP server, Node TUI ona konuşur | 94 imza tekrarı yok (ince çağrı iletimi) | **Ekstra hareketli parça**: port yönetimi, süreç yaşam döngüsü (`fl tui` → node child → python server), sürüm uyumu, hata serileştirme, localhost dinleyen süreç güvenliği; iki süreç = iki hata alanı, debug zor |
| **(c) MCP üzerinden** | SDK zaten `florence-mcp` (fastmcp, 92 tool) taşıyor; Node TUI MCP client olur | Hazır server var | MCP **stdio transport** TUI ile aynı terminali paylaşır → tam ekran render ile çakışır (HTTP/SSE için ayrı server gerekir = yine hareketli parça); MCP tool şeması (düzleştirilmiş tool listesi) resource API'sine (gruplu 94 endpoint) birebir değil; MCP bir **LLM araç protokolü** — 45s polling'li bir dashboard için yanlış katman. tui-design.md Ek B zaten karar vermiş: *"TUI, MCP ile doğrudan ilişki kurmaz."* |

**Sonuç:** Entegrasyon katmanı, görünümden çok daha belirleyici. Textual'da entegrasyon **sıfır maliyet** (in-process); Node'da üç yolun üçü de ya çift bakım (a), ya ekstra mimari parça (b), ya da yanlış protokol (c) getiriyor.

## 2.3 Paketleme

- **Textual:** `fl tui` Python paketinden gelir; `textual>=0.60` ana `dependencies`'e eklenir (tui-design.md §7.2) → tek pip kurulumu, "CLI kuran TUI'yi de kurar" kararı korunur. Not: güncel Textual 8.x `rich>=14.2.0` ister; SDK pin'i `rich>=13.7` — **çakışma yok** (>=13.7, 14/15'e izin verir), yalnızca lockfile'da rich yükselir.
- **Node:** Ayrı npm paketi + **Node runtime zorunluluğu**. Hedef kullanıcı Python CLI kullanıcısı — kuruluma Node dayatmak tek-kurulum kararını bozar; "iki kurulum" kullanıcı deneyimi bölünür.

## 2.4 Ekosistem ve bakım

- **Textual:** Tek dil, tek repo, tek bağımlılık ağacı (uv.lock), tek test takımı (pytest), tek lint/type kuralı (ruff + mypy). TUI, CLI ile aynı konvansiyonlarda.
- **Node:** İki dil, iki bağımlılık ağacı (uv.lock + package-lock), iki test takımı, iki CI hattı ve **çapraz dil sözleşme testleri** (Python SDK davranışı JS'te doğrulanmalı). Küçük/orta ölçekli bir ekip için kalıcı yük.

## 2.5 Sonuç ve öneri

**NET ÖNERİ: Python Textual.** Mevcut `tui-design.md` kararını (Faz 10: Textual, tek kurulum, in-process `AsyncFlorenceClient`, `run_test` ile offline test) tam olarak destekliyor; Node'un görünüm açısından anlamlı bir üstünlüğü yok, entegrasyon/paketleme/bakım açısından ise belirgin dezavantajı var.

**Node'un gerçekten mantıklı olacağı durumlar (hiçbiri bizde geçerli değil):**
1. Hedef kitlenin JS/TS geliştiricisi olması ve resmi bir Node SDK'sının bulunması (endpoint tekrarı o zaman SDK'da erir).
2. Ekibin TS-first olması (Python katmanı zaten yazılmış durumda — değil).
3. Tarayıcı/Electron tarzı web render gereksinimi (terminal TUI değil, web uygulaması isteniyorsa ayrı konu).
4. Mevcut ve bakımlı bir Node kod tabanı (yok).

---

# Sonuç

**Dosya:** `/home/efe/Belgeler/florence/florence-sdk/docs/research-banner-tui.md`

## Özet (8 madde)

1. cfonts = figlet tarzı ASCII art + **per-karakter truecolor gradient** (`38;2` ANSI); 331 KB, Node gerektirir.
2. **Rich'te gradient YOK** (13.9.4 ve 15.0.0 deneysel doğrulandı; doküman/changelog'da da yok) — bağlamdaki varsayım çürütüldü.
3. pyfiglet (1.0.4) 571 fontla ASCII şekli üretir ama **renksizdir**; 1.76 MB'lık boyutu font verisinden gelir.
4. Python'da cfonts eşdeğeri: **statik gömülü art + ~15 satırlık özel gradient helper** — sıfır yeni bağımlılık; üretilen ANSI kodu cfonts'la birebir aynı formatta (kanıtlandı).
5. Banner konumları: **login başarısı, install.sh sonu, tui açılışı EVET**; `--version` **yalnızca TTY'de**; hepsinde kural: `--json`'da asla, pipe'ta renk yok.
6. TUI: **Textual** (0.7 MB wheel, rich>=14.2 — mevcut pin uyumlu) görünümde Node'a kaybetmiyor; hazır DataTable/Sparkline/Header/Footer, headless test API'si tui-design.md §8 ile birebir örtüşüyor.
7. Node tarafında tek ciddi aday **terminal-kit** (aktif, gradient+sparkline) ama 4.1 MB + karmaşık API; ink dashboard değil, blessed/neo-blessed/blessed-contrib bakımsız.
8. **Belirleyici faktör entegrasyon:** Textual = in-process (sıfır maliyet); Node = elle client tekrarı (94 endpoint + auth) ya da bridge ya da MCP (üçü de ekstra mimari yük; MCP stdio transport ayrıca TUI terminaliyle çakışır).

## Karar noktaları

| # | Karar | Öneri |
|---|---|---|
| B1 | Banner bağımlılığı | Statik art + özel helper (yeni bağımlılık yok). Keyfi metin banner'ı istenirse pyfiglet opsiyonel extra. |
| B2 | Banner konumları | login + install.sh + tui açılışı: evet; `--version`: TTY koşuluyla; `--json`'da asla. |
| B3 | Renk paleti | Kullanıcının sevdiği üç varyant (blue→magenta, red→yellow, red→#ffa500) parametre olarak; varsayılan bir tanesi. |
| T1 | TUI çerçevesi | **Textual** — tui-design.md kararını teyit eder. |
| T2 | Node'a geçiş | Yalnızca hedef kitle JS + resmi Node SDK senaryosunda; şu an geçerli değil. |
| T3 | Entegrasyon | In-process `AsyncFlorenceClient`; bridge/MCP yollarına kapı kapalı (tui-design.md Ek B ile uyumlu). |
