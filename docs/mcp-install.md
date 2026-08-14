# Florence MCP Otomatik Kurulum Rehberi

`scripts/install-mcp.sh`, Florence MCP sunucusunu (`florence-mcp`) makinenizdeki
popüler AI ajanlarına **otomatik olarak kaydeder** — tespit eder, konfigürasyon
dosyasına `florence` MCP kaydını ekler (kimlik env'leriyle birlikte) ve sonucu
doğrular. Aynı script ile kayıtları kaldırabilir (`--remove`) veya ne
yapacağını önceden görebilirsiniz (`--dry-run`).

Manuel kurulum tercih ederseniz: `docs/mcp-setup.md` (Claude Desktop, Claude
Code, Cursor için hazır JSON örnekleri). MCP tasarımı: `docs/mcp-design.md`.

---

## 1. Ön koşul

`florence-mcp` komutu `PATH`'te olmalıdır (MCP kayıtları bu komutu çalıştırır):

```bash
florence-mcp --help        # var mı kontrol et
```

Yoksa önce SDK'yı kurun:

```bash
cd florence-sdk
./install.sh               # veya: pipx install 'florence-sdk' / uv tool install 'florence-sdk'
```

> `--remove` modu bu kontrolü **atlar** — SDK kaldırıldıktan sonra bile
> ajanlardaki eski MCP kayıtlarını temizleyebilirsiniz.

## 2. Hızlı başlangıç

```bash
# Kimliksiz kurulum (public tool'lar çalışır; kimlik sonradan doldurulur)
./scripts/install-mcp.sh

# Bot profiliyle kurulum (şifre sorulur; boş bırakılırsa keyring kullanılır)
./scripts/install-mcp.sh --bot bot-1

# Kullanıcı kimliğiyle kurulum (FLORENCE_TOKEN)
./scripts/install-mcp.sh --token "JWT_ACCESS_TOKEN"

# Bot + indirme dizini
./scripts/install-mcp.sh --bot bot-1 --download-dir "$HOME/Downloads/florence"

# Önce ne yapacağını gör (hiçbir dosya değişmez)
./scripts/install-mcp.sh --dry-run

# Tüm ajanlardan 'florence' kaydını kaldır
./scripts/install-mcp.sh --remove

# Mevcut kayıt farklıysa sormadan güncelle
./scripts/install-mcp.sh --token "..." --yes
```

## 3. Kimlik seçenekleri ve ortam değişkenleri

Kimlik, MCP kaydına **env olarak** yazılır. Öncelik zinciri
(`docs/mcp-design.md` Bölüm 3.1): `MCP_FLORENCE_BOT` → `FLORENCE_TOKEN` →
keyring oturumu → kimliksiz mod.

| Bayrak | Env | Açıklama |
|---|---|---|
| `--bot <kullanıcı>` | `MCP_FLORENCE_BOT` | Bot profili: sunucu bu bot olarak login olur. Şifre çalışma anında sorulur; verilirse `MCP_FLORENCE_BOT_PASSWORD` olarak yazılır, boş bırakılırsa keyring kullanılır. |
| `--token <JWT>` | `FLORENCE_TOKEN` | Hazır access token (CI/headless, salt-okunur override). |
| `--download-dir <yol>` | `MCP_DOWNLOAD_DIR` | `export_download` / `analysis_download_report` için varsayılan indirme dizini. |
| (hiçbiri) | — | Kimliksiz mod: public tool'lar (market/economy/misc okuma) çalışır; JWT isteyen tool'lar çözüm önerili hata döner. |

Kurallar:

- `--bot` ve `--token` **birlikte verilemez** (script hata verir).
- `--bot` ile şifre TTY olmayan ortamda sorulamaz; bu durumda
  `MCP_FLORENCE_BOT_PASSWORD` ortam değişkeni kullanılır, o da yoksa keyring'e
  güvenilir (script bunu açıkça belirtir).
- Çoklu kimlik (aynı anda kullanıcı + bot) tek MCP kaydıyla desteklenmez —
  `docs/mcp-setup.md` Bölüm 3.4'teki gibi iki ayrı kayıt tanımlayın.

## 4. Desteklenen ajanlar

| Ajan | Tespit | Yazılan konfigürasyon | Format |
|---|---|---|---|
| **Claude Code** | `claude` binary varsa CLI yolu; yoksa `~/.claude.json` | `claude mcp add florence --scope user --env ... -- florence-mcp` (binary varsa) veya `~/.claude.json` içinde `mcpServers.florence` | CLI / JSON |
| **Codex** (OpenAI) | `codex` binary veya `~/.codex/` | `~/.codex/config.toml` içinde `[mcp_servers.florence]` (`command`, `env`) | TOML |
| **OpenCode** | `opencode` binary veya `~/.config/opencode/` | `~/.config/opencode/opencode.json` (yoksa `.jsonc`) içinde `mcp.florence` (`type: "local"`, `command: ["florence-mcp"]`, `environment`) | JSONC |
| **Cursor** | `~/.cursor/` dizini | `~/.cursor/mcp.json` içinde `mcpServers.florence` | JSON |
| **Hermes** (Nous) | `hermes` binary | `hermes mcp add florence --command florence-mcp --env ...` (best-effort) | CLI |

> **Hermes notu:** Hermes MCP kayıtları `hermes mcp add` komutuyla yapılır
> (yapılandırma YAML'da, el ile düzenleme güvenli değildir). Bu komut sunucuya
> bağlanıp tool'larını **keşfeder** — `florence-mcp` çalışabilir olmalıdır;
> başarısız olursa script hata vermez, el ile ekleme komutunu gösterir.
> Hermes'in eski sürümlerinde `mcp add` yoksa script net bir mesajla atlar.

**Tespit edilmeyen ajanlar hata değildir:** script her ajan için
"tespit edildi / edilmedi" satırı basar; makinede kurulu olmayan ajanlar sessizce
atlanır.

## 5. Nasıl çalışır

1. `florence-mcp` PATH'te mi? (yoksa kurulum yönlendirmesi + çıkış 1)
2. Hedef ajanlar tespit edilir (`claude` / `codex` / `opencode` / `cursor` / `hermes`).
3. Kimlik seçimi: `--bot` (şifre sorar), `--token`, veya kimliksiz.
4. Her tespit edilen ajana `florence` kaydı eklenir:
   - **İdempotent:** kayıt zaten varsa ve içeriği aynıysa dokunulmaz
     ("zaten kurulu ve güncel").
   - Kayıt farklıysa **güncelleme sorulur** (`e/H`); TTY yoksa atlanır,
     `--yes` ile zorlanır.
5. **Güvenli düzenleme:** JSON/JSONC/TOML dosyaları `python3` ile düzenlenir —
   dosyanın tamamı yeniden yazılmaz; yalnızca ilgili anahtar eklenir/güncellenir/
   kaldırılır. Kullanıcının yorumları (`// ...`, `/* ... */`), boşlukları ve
   diğer anahtarları **aynen korunur** (OpenCode `.jsonc` dosyalarındaki
   yorumlar dahil).
6. **Doğrulama:** yazılan her dosyanın geçerliliği `python3` ile (JSONC için
   yorum temizleyerek, TOML için `tomllib`) kontrol edilir; JSON dosyaları için
   `jq` varsa ek kontrol yapılır.
7. `--dry-run`: hiçbir dosya değişmez; tespit + plan çıktısı verilir.
   `--remove`: tüm tespit edilen ajanlardan `florence` kaydını kaldırır
   (boş kalan üst anahtar da temizlenir; içinde yorum varsa dokunulmaz).

## 6. Kurulum sonrası doğrulama

1. Ajanı (Claude Code / Cursor / OpenCode vb.) yeniden başlatın.
2. `auth_status` tool'unu çağırın — hangi kimlikle bağlandığınızı söyler
   (`identity_type`: user/bot/none, `token_source`: env/keyring/memory).
3. Public bir tool deneyin: `market_price_current` (ticker: `THYAO`).
4. Kimlikli akış: `account_profile` → profil + kredi bilgisi.
5. Kredi harcayan tool'lar öncesi `account_credits`; yıkıcı tool'lar
   (`auth_delete_account`, `portfolio_delete`, ...) `confirm=true` ister.

## 7. Sık karşılaşılan sorunlar

| Belirti | Çözüm |
|---|---|
| `'florence-mcp' PATH'te bulunamadi` | Önce SDK'yı kurun: `./install.sh` (veya `pipx install 'florence-sdk'`). |
| `... okunamadi / gecersiz JSON — atlandi` | Konfigürasyon dosyası bozuk; ajanı kapatıp dosyayı kontrol edin (el ile düzeltin), sonra scripti tekrar çalıştırın. |
| `mevcut 'florence' kaydi farkli — guncellenmedi` | Kayıt başka araçla değiştirilmiş. `--yes` ile zorlayın veya soruyu TTY'de yanıtlayın. |
| Claude Code: `claude mcp add basarisiz` | Eski Claude sürümü `--scope` desteklemiyor olabilir; script otomatik olarak `~/.claude.json`'a doğrudan yazar. |
| Hermes: `hermes mcp add basarisiz` | `florence-mcp` çalışmıyor olabilir (SDK kurulu mu?) veya ağ/keşif sorunu. Scriptin gösterdiği el ile komutu çalıştırın. |
| `python3 >= 3.11 gerekli (tomllib)` | Codex TOML düzenlemesi Python 3.11+ ister (JSON düzenlemesi 3.8+ ile çalışır). |
| Windows | Desteklenmez — WSL2 veya Docker önerilir. |
| Tool 503 dönerse | `misc_maintenance` ile devre dışı özellik listesini kontrol edin. |

## 8. Güvenlik notları

- Token/şifre, istemci konfigürasyon dosyalarına **düz metin** yazılır
  (Claude Code'un kendi davranışı; `claude mcp add --env` da aynıdır).
  Scriptin **oluşturduğu** yeni dosyalar `chmod 600` yapılır; mevcut dosyaların
  izinlerine dokunulmaz.
- Mümkünse bot şifresini dosyaya yazmak yerine **keyring**'e kaydedin
  (`fl bots create` veya `fl login` ile) — `--bot` sorusuna boş cevap verin,
  script `MCP_FLORENCE_BOT_PASSWORD` yazmaz ve sunucu keyring'den okur.
- `.mcp.json` gibi **repo'ya sızabilecek** proje dosyalarına token koymayın;
  bu script yalnızca kullanıcı düzeyindeki konfigürasyonları düzenler.
- `--dry-run` çıktısı dahil hiçbir adım token'ı loglamaz (komut görüntüsünde
  env değerleri gösterilmez; `%q` ile kaçışlı plan satırı yalnızca dry-run'dadır
  ve değerleri içerir — paylaşmayın).
