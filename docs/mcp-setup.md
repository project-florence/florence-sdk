# Florence MCP Kurulum Rehberi

Florence MCP sunucusu (`florence-mcp`), `florence-sdk` reposundaki MCP paketinin
stdio entry point'idir: Claude Desktop, Claude Code, Cursor gibi MCP destekleyen
istemcilere Florence'ın 92 tool'unu sunar (tasarım: `docs/mcp-design.md`,
kararlar: Bölüm 9).

## 1. Ön koşul: paket kurulumu

Repo içinden (geliştirme):

```bash
cd florence-sdk
uv sync                       # mcp + fastmcp bağımlılıkları kurulur
uv run florence-mcp           # stdio sunucusu başlar (test: ctrl-c)
```

Yayınlanmış paketten (pip/pipx/uv tool):

```bash
uv tool install 'florence-sdk'        # veya pipx install 'florence-sdk'
florence-mcp --help
```

Doğrulama (stdio initialize):

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | florence-mcp
```

## 2. Ortam değişkenleri

| Değişken | Zorunlu | Açıklama |
|---|---|---|
| `FLORENCE_TOKEN` | hayır¹ | Hazır JWT access token (CI/headless; salt-okunur override) |
| `MCP_FLORENCE_BOT` | hayır¹ | Bot profili: sunucu bu bot olarak login olur (keyring şifresiyle) |
| `MCP_FLORENCE_BOT_PASSWORD` | hayır | Bot şifresi (geçici/CI; yoksa keyring'deki kayıt kullanılır) |
| `MCP_DOWNLOAD_DIR` | hayır | `dest_path` için varsayılan dizin (traversal korumalı; yoksa çalışma dizini) |
| `MCP_REPORT_TIMEOUT` | hayır | `analysis_generate_report` read timeout, saniye (default 180) |
| `MCP_REPORT_DOWNLOAD_TIMEOUT` | hayır | `analysis_download_report` read timeout, saniye (default 60) |
| `MCP_DISABLE_GROUPS` | hayır | Virgüllü grup listesi: bu grupların tool'ları kaydedilmez (örn. `auth,export`) |
| `FLORENCE_API_URL` | hayır | API taban URL'i (dev ortamı override'ı; default üretim) |

¹ Kimlik zinciri (mcp-design.md Bölüm 3.1): `MCP_FLORENCE_BOT` → `FLORENCE_TOKEN`
→ keyring oturumu (`fl login`) → kimliksiz mod (public tool'lar). Hiçbir kimlik
yoksa sunucu **yine başlar**; JWT isteyen tool çağrıları çözüm önerili net hata
döner.

> **Güvenlik:** Token/şifre istemci config dosyasına değil, mümkünse keyring'e
> veya kabuk ortamına yazılır (Claude Code: `export FLORENCE_TOKEN=…`).
> `.mcp.json` repo'ya sızabilir — oraya token koymayın.

## 3. İstemci kurulumları

### 3.1 Claude Desktop

`claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`,
Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "florence": {
      "command": "florence-mcp",
      "args": [],
      "env": {
        "FLORENCE_TOKEN": "…",
        "MCP_DOWNLOAD_DIR": "/home/ben/Downloads/florence"
      }
    }
  }
}
```

Bot profiliyle (şifre keyring'de kayıtlıysa `MCP_FLORENCE_BOT_PASSWORD` gerekmez):

```json
{
  "mcpServers": {
    "florence-bot": {
      "command": "florence-mcp",
      "env": {
        "MCP_FLORENCE_BOT": "bot-1"
      }
    }
  }
}
```

### 3.2 Claude Code

Proje köküne `.mcp.json` (takımla paylaşılabilir — token koymadan):

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

Kullanıcı düzeyinde token eklemek için:

```bash
claude mcp add florence --env FLORENCE_TOKEN=…
# veya kabukta: export FLORENCE_TOKEN=…  (Claude Code mevcut env'i geçirir)
```

### 3.3 Cursor

`~/.cursor/mcp.json` (global) veya proje `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "florence": {
      "command": "florence-mcp",
      "args": [],
      "env": {
        "FLORENCE_TOKEN": "…",
        "MCP_DOWNLOAD_DIR": "/home/ben/Downloads/florence"
      }
    }
  }
}
```

### 3.4 Çoklu kimlik (v1)

Tek process = tek kimlik kuralı gereği (mcp-design.md Bölüm 3.1/6.4), aynı
istemcide hem kullanıcı hem bot istiyorsanız iki ayrı blok:

```json
{
  "mcpServers": {
    "florence-user": { "command": "florence-mcp", "env": { "FLORENCE_TOKEN": "…" } },
    "florence-bot":  { "command": "florence-mcp", "env": { "MCP_FLORENCE_BOT": "bot-1" } }
  }
}
```

## 4. Kurulum sonrası doğrulama

1. İstemciyi yeniden başlatın; tool listesinde 92 tool görünmeli
   (grup kapatıldıysa daha az).
2. `auth_status` tool'unu çağırın — hangi kimlikle bağlandığınızı söyler
   (`identity_type`: user/bot/none, `token_source`: env/keyring/memory).
3. Public bir tool deneyin: `market_price_current` (ticker: `THYAO`).
4. Kimlikli akış: `account_profile` → profil + kredi bilgisi.
5. Kredi harcayan tool'lar öncesi `account_credits`; yıkıcı tool'lar
   (`auth_delete_account`, `portfolio_delete`, `portfolio_undo_transaction`,
   `bots_delete`) `confirm=true` ister.

## 5. Sık karşılaşılan sorunlar

| Belirti | Çözüm |
|---|---|
| `Kimlik hatası (401)` | `FLORENCE_TOKEN` ayarlayın, `fl login` ile keyring'e oturum açın veya `MCP_FLORENCE_BOT` + bot şifresi verin |
| `Rate limit aşıldı (429)` | `retry_after` saniyesini bekleyin (news 10/dk, auth 5/dk, export 3/saat) |
| `dest_path MCP_DOWNLOAD_DIR dışına çıkamaz` | `MCP_DOWNLOAD_DIR` içinde bir yol verin (traversal koruması) |
| Bot profili: `no_bot_password` | `MCP_FLORENCE_BOT_PASSWORD` verin veya `bots_create` ile bot oluşturup şifreyi keyring'e yazdırın |
| Tool 503 dönerse | `misc_maintenance` ile devre dışı özellik listesini kontrol edin |
