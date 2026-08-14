#!/usr/bin/env bash
# =============================================================================
# install-mcp.sh — Florence MCP sunucusunun AI ajanlarina otomatik kurulumu
#
# Populer AI ajanlarini (Claude Code, Codex, OpenCode, Cursor, Hermes) tespit
# eder ve her birine 'florence' MCP sunucusu kaydini ekler (florence-mcp
# komutu + kimlik env'leri). Idempotent: mevcut kayit ayniysa hicbir sey
# degistirmez; farkliysa guncellemeyi sorar.
#
# Konfigurasyon dosyalari (JSON / JSONC / TOML) python3 ile GUVENLI duzenlenir:
# dosyanin geri kalanini byte-byte koruyan cerrahi ekleme/guncelleme yapilir
# (yorumlar ve bicimlendirme bozulmaz).
#
# Kullanim:
#   scripts/install-mcp.sh                 # kimliksiz (public tool'lar)
#   scripts/install-mcp.sh --bot bot-1     # bot profili (sifre sorar)
#   scripts/install-mcp.sh --token JWT...  # FLORENCE_TOKEN ile
#   scripts/install-mcp.sh --dry-run       # plan gosterir, hicbir sey yazmaz
#   scripts/install-mcp.sh --remove        # tum ajanlardan kaydi kaldirir
#
# Desteklenen ajanlar:
#   Claude Code  -> claude mcp add (binary varsa) / ~/.claude.json
#   Codex        -> ~/.codex/config.toml ([mcp_servers.florence])
#   OpenCode     -> ~/.config/opencode/opencode.json[c] (mcp.florence)
#   Cursor       -> ~/.cursor/mcp.json (mcpServers.florence)
#   Hermes       -> hermes mcp add (best-effort; emin degilse net mesaj + atla)
#
# Windows desteklenmez (WSL2 veya Docker onerilir).
# =============================================================================
set -euo pipefail

# --- Sabitler ----------------------------------------------------------------
MCP_NAME="florence"
MCP_CMD="florence-mcp"

# --- Durum degiskenleri ------------------------------------------------------
DRY_RUN=0
DO_REMOVE=0
ASSUME_YES=0
BOT_USER=""
TOKEN=""
DOWNLOAD_DIR=""
IDENTITY_SUMMARY=""
ENV_LINES=()
WRITTEN_FILES=()

CLAUDE_MODE=none; CLAUDE_CFG=""
CODEX_MODE=none
OPENCODE_MODE=none; OPENCODE_CFG=""
CURSOR_MODE=none; CURSOR_CFG="$HOME/.cursor/mcp.json"
HERMES_MODE=none

# --- Renkler (bagimlilik yok; NO_COLOR / TTY olmayan ortamda kapanir) --------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-}" != "dumb" ]; then
    C_RESET=$'\033[0m'
    C_DIM=$'\033[2m'
    C_RED=$'\033[31m'
    C_GREEN=$'\033[32m'
    C_YELLOW=$'\033[33m'
    C_CYAN=$'\033[36m'
else
    C_RESET=""; C_DIM=""; C_RED=""; C_GREEN=""; C_YELLOW=""; C_CYAN=""
fi

# --- Log yardimcilari --------------------------------------------------------
info() { printf '%s==>%s %s\n' "$C_CYAN" "$C_RESET" "$*"; }
ok()   { printf '%s[OK]%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%s[!]%s %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
err()  { printf '%s[HATA]%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; }
dry()  { printf '%s[dry-run]%s %s\n' "$C_DIM" "$C_RESET" "$*"; }
die()  { err "$*"; exit 1; }

# --- Kullanim ----------------------------------------------------------------
usage() {
    cat <<'EOF'
install-mcp.sh — Florence MCP sunucusunu AI ajanlarina otomatik kurar

Kullanim:
  install-mcp.sh [SECENEKLER]

Secenekler:
  --bot <kullanici>     Bot profili: MCP_FLORENCE_BOT=<kullanici>. Sifre sorar;
                        bos birakilirsa keyring'deki kayit kullanilir.
  --token <JWT>         Kullanici kimligi: FLORENCE_TOKEN=<JWT>.
  --download-dir <yol>  MCP_DOWNLOAD_DIR=<yol> (export indirme dizini).
  --dry-run, --check    Hicbir dosyayi degistirmez; tespit + plan gosterir.
  --remove, --uninstall Tum tespit edilen ajanlardan 'florence' kaydini kaldirir.
  -y, --yes             Mevcut 'florence' kaydi farkliysa sormadan gunceller.
  -h, --help            Bu yardimi gosterir.

Desteklenen ajanlar:
  Claude Code  (claude mcp add / ~/.claude.json)
  Codex        (~/.codex/config.toml)
  OpenCode     (~/.config/opencode/opencode.json[c])
  Cursor       (~/.cursor/mcp.json)
  Hermes       (hermes mcp add — best-effort)

Kimlik env'leri: FLORENCE_TOKEN, MCP_FLORENCE_BOT, MCP_FLORENCE_BOT_PASSWORD,
MCP_DOWNLOAD_DIR. Oncelik (docs/mcp-design.md Bolum 3.1): bot > token > keyring
> kimliksiz mod. Windows desteklenmez. Detaylar: docs/mcp-install.md
EOF
}

# --- Arguman ayristirma ------------------------------------------------------
parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --bot)
                BOT_USER="${2:-}"
                [ -n "$BOT_USER" ] || die "--bot <kullanici> gerekli"
                shift 2
                ;;
            --token)
                TOKEN="${2:-}"
                [ -n "$TOKEN" ] || die "--token <JWT> gerekli"
                shift 2
                ;;
            --download-dir)
                DOWNLOAD_DIR="${2:-}"
                [ -n "$DOWNLOAD_DIR" ] || die "--download-dir <yol> gerekli"
                shift 2
                ;;
            --dry-run|--check) DRY_RUN=1; shift ;;
            --remove|--uninstall) DO_REMOVE=1; shift ;;
            -y|--yes) ASSUME_YES=1; shift ;;
            -h|--help) usage; exit 0 ;;
            *) die "Bilinmeyen secenek: $1 (--help)" ;;
        esac
    done
    if [ -n "$BOT_USER" ] && [ -n "$TOKEN" ]; then
        die "--bot ve --token birlikte verilemez (tek kimlik secin)"
    fi
}

# =============================================================================
# Python yardimcisi: JSON/JSONC/TOML guvenli duzenleme
#
# JSON/JSONC icin cerrahi (byte-koruyan) duzenleme: dosyanin tamamini yeniden
# yazmaz; yalnizca ilgili anahtari ekler/gunceller/kaldirir. Boylece kullanicinin
# yorumlari, bosluklari ve diger anahtarlari aynen korunur.
#
# Kullanim:
#   pycfg check  <yol> <topkey> <ad> <shape> <jsonc:0|1> [K=V...]  -> absent|same|diff
#   pycfg has    <yol> <topkey> <ad> <jsonc:0|1>                   -> present|absent
#   pycfg set    <yol> <topkey> <ad> <shape> [K=V...]
#   pycfg remove <yol> <topkey> <ad>
#   pycfg json_valid <yol> <jsonc:0|1>                             -> valid
#   pycfg toml_check  <yol> <ad> [K=V...]                          -> absent|same|diff
#   pycfg toml_has    <yol> <ad>                                   -> present|absent
#   pycfg toml_set    <yol> <ad> [K=V...]
#   pycfg toml_remove <yol> <ad>
#   pycfg toml_valid  <yol>                                        -> valid
# =============================================================================
pycfg() {
    python3 - "$@" <<'PYEOF'
"""install-mcp.sh yardimcisi: JSON/JSONC/TOML konfigurasyonlarini guvenli duzenler."""
import json
import os
import sys

MCP_CMD = "florence-mcp"


def strip_jsonc(text):
    """JSONC -> JSON: string disindaki // ve /* */ yorumlarini ve sondaki
    virgulleri kaldirir (string iceriklerine dokunmaz)."""
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if c in "}]":
            j = len(out) - 1
            while j >= 0 and out[j] in " \t\r\n":
                j -= 1
            if j >= 0 and out[j] == ",":
                out[j] = " "
        out.append(c)
        i += 1
    return "".join(out)


def load_json(path, jsonc):
    with open(path, "r", encoding="utf-8-sig") as fh:
        text = fh.read()
    if jsonc:
        text = strip_jsonc(text)
    return json.loads(text)


def first_open_brace(text):
    """Yorum/string disindaki ilk '{' karakterinin indeksi (yoksa -1)."""
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if c == "{":
            return i
        i += 1
    return -1


def value_end(text, start, n):
    """start'taki degerin bittigi indeksi doner (nesne/dizi/string/skalar)."""
    c = text[start]
    if c in "{[":
        close = "}" if c == "{" else "]"
        depth = 1
        i = start + 1
        in_str = False
        while i < n:
            ch = text[i]
            if in_str:
                if ch == "\\":
                    i += 2
                    continue
                if ch == '"':
                    in_str = False
                i += 1
                continue
            if ch == '"':
                in_str = True
            elif ch == c:
                depth += 1
            elif ch == close:
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        raise ValueError("duzensiz JSON: kapanis '%s' yok" % close)
    if c == '"':
        i = start + 1
        while i < n:
            if text[i] == "\\":
                i += 2
                continue
            if text[i] == '"':
                return i + 1
            i += 1
        raise ValueError("duzensiz JSON: kapanis '\"' yok")
    i = start
    while i < n and text[i] not in ",}]":
        i += 1
    return i


def find_key(text, key, start=0, end=None):
    """'\"key\"' anahtarini (string disinda) bulur.
    Donus: (colon_idx, value_start, value_end) veya None."""
    n = len(text) if end is None else end
    target = '"' + key + '"'
    i = start
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            if text.startswith(target, i):
                j = i + len(target)
                while j < n and text[j] in " \t\r\n":
                    j += 1
                if j < n and text[j] == ":":
                    j += 1
                    while j < n and text[j] in " \t\r\n":
                        j += 1
                    if j < n:
                        return (j, j, value_end(text, j, n))
                i += len(target)
                continue
            in_str = True
            i += 1
            continue
        i += 1
    return None


def line_indent(text, pos):
    start = text.rfind("\n", 0, pos) + 1
    i = start
    while i < pos and text[i] in " \t":
        i += 1
    return text[start:i]


def build_server(shape, env):
    if shape == "claude":
        return {"type": "stdio", "command": MCP_CMD, "env": env}
    if shape == "cursor":
        return {"command": MCP_CMD, "args": [], "env": env}
    if shape == "opencode":
        return {"type": "local", "command": [MCP_CMD], "enabled": True, "environment": env}
    raise ValueError("bilinmeyen shape: %s" % shape)


def env_from(items):
    env = {}
    for it in items:
        k, sep, v = it.partition("=")
        if sep and k:
            env[k] = v
    return env


def set_server(text, topkey, name, server_obj):
    """'topkey.name' anahtarini ekler/gunceller; geri kalan baytlari korur."""
    span = find_key(text, topkey)
    if span is None:
        # topkey yok: ilk '{' sonrasina yeni anahtar ekle
        block = json.dumps({topkey: {name: server_obj}}, indent=2, ensure_ascii=False)
        body = block[1:-1].rstrip()
        idx = first_open_brace(text)
        if idx == -1:
            raise ValueError("gecersiz JSON: nesne yok")
        p = idx + 1
        while p < len(text) and text[p] in " \t\r\n":
            p += 1
        after = text[p:]
        if after.startswith("}"):
            return text[:p] + body + "\n" + text[p:]
        return text[:p] + body + ",\n" + text[p:]
    _colon, vstart, vend = span
    if text[vstart] != "{":
        raise ValueError('"%s" degeri nesne degil — duzenlenemez' % topkey)
    nspan = find_key(text, name, vstart, vend)
    if nspan is None:
        # topkey var, name yok: topkey nesnesinin icine ekle
        inner = json.dumps({name: server_obj}, indent=2, ensure_ascii=False)
        body = inner[1:-1].rstrip()
        indent = line_indent(text, vstart)
        body = "\n".join((indent + "  " + l) if l else l for l in body.splitlines())
        p = vstart + 1
        while p < len(text) and text[p] in " \t\r\n":
            p += 1
        after = text[p:]
        if after.startswith("}"):
            return text[:p] + "\n" + body + "\n" + indent + text[p:]
        return text[:p] + "\n" + body + ",\n" + indent + text[p:]
    # name var: degerini degistir
    _ncolon, nvstart, nvend = nspan
    new_val = json.dumps(server_obj, indent=2, ensure_ascii=False)
    indent = line_indent(text, nvstart)
    lines = new_val.splitlines()
    repl = lines[0] + "\n" + "\n".join(indent + l for l in lines[1:])
    return text[:nvstart] + repl + text[nvend:]


def remove_server(text, topkey, name):
    """'topkey.name' anahtarini kaldirir. Donus: (yeni_metin, degisti_mi)."""
    span = find_key(text, topkey)
    if span is None:
        return text, False
    _colon, vstart, vend = span
    if text[vstart] != "{":
        return text, False
    nspan = find_key(text, name, vstart, vend)
    if nspan is None:
        return text, False
    _ncolon, nvstart, nvend = nspan
    key_start = text.rfind('"%s"' % name, vstart, nvstart)
    if key_start == -1:
        key_start = nvstart - len('"%s"' % name)
    end = nvend
    j = end
    while j < len(text) and text[j] in " \t\r\n":
        j += 1
    if j < len(text) and text[j] == ",":
        end = j + 1
    else:
        k = key_start - 1
        while k >= 0 and text[k] in " \t\r\n":
            k -= 1
        if k >= 0 and text[k] == ",":
            key_start = k
    new_text = text[:key_start] + text[end:]
    # topkey bos kaldiysa onu da kaldir (iceride yorum varsa dokunma)
    span2 = find_key(new_text, topkey)
    if span2 is not None:
        _c2, vs2, ve2 = span2
        if new_text[vs2] == "{" and not new_text[vs2 + 1:ve2 - 1].strip():
            key_start2 = new_text.rfind('"%s"' % topkey, 0, vs2)
            if key_start2 == -1:
                key_start2 = vs2 - len('"%s"' % topkey)
            end2 = ve2
            j = end2
            while j < len(new_text) and new_text[j] in " \t\r\n":
                j += 1
            if j < len(new_text) and new_text[j] == ",":
                end2 = j + 1
            else:
                k = key_start2 - 1
                while k >= 0 and new_text[k] in " \t\r\n":
                    k -= 1
                if k >= 0 and new_text[k] == ",":
                    key_start2 = k
            new_text = new_text[:key_start2] + new_text[end2:]
    return new_text, True


# --- TOML (Codex) -------------------------------------------------------------
def toml_load(path):
    import tomllib
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def toml_env_line(env):
    items = ", ".join("%s = %s" % (k, json.dumps(v, ensure_ascii=True)) for k, v in env.items())
    return "env = { %s }" % items


def toml_table(name, env):
    return '[mcp_servers.%s]\ncommand = "%s"\n%s\n' % (name, MCP_CMD, toml_env_line(env))


def toml_span(text, name):
    tbl = "[mcp_servers.%s]" % name
    start = text.find(tbl)
    if start == -1:
        return None
    end = len(text)
    nl = text.find("\n", start)
    while nl != -1:
        nxt = nl + 1
        if nxt < len(text) and text[nxt] == "[":
            end = nxt
            break
        nl = text.find("\n", nxt)
    return start, end


def toml_env_match(env, existing):
    if not isinstance(existing, dict):
        return False
    for k, v in env.items():
        if existing.get(k) != v:
            return False
    return True


# --- Komut dagitici -----------------------------------------------------------
def main():
    args = sys.argv[1:]
    if not args:
        raise SystemExit("op gerekli")
    op = args[0]

    if op == "check":
        path, topkey, name, shape = args[1], args[2], args[3], args[4]
        jsonc = args[5] == "1"
        env = env_from(args[6:])
        data = load_json(path, jsonc)
        existing = data.get(topkey)
        if not isinstance(existing, dict) or name not in existing:
            print("absent")
            return
        cur = existing[name]
        if not isinstance(cur, dict):
            print("diff")
            return
        server = build_server(shape, env)
        for k, v in server.items():
            if cur.get(k) != v:
                print("diff")
                return
        print("same")

    elif op == "has":
        path, topkey, name = args[1], args[2], args[3]
        jsonc = args[4] == "1"
        data = load_json(path, jsonc)
        print("present" if isinstance(data.get(topkey), dict) and name in data[topkey] else "absent")

    elif op == "set":
        path, topkey, name, shape = args[1], args[2], args[3], args[4]
        env = env_from(args[5:])
        server = build_server(shape, env)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as fh:
                text = fh.read()
        else:
            text = ""
        if not text.strip():
            new_text = json.dumps({topkey: {name: server}}, indent=2, ensure_ascii=False) + "\n"
        else:
            new_text = set_server(text, topkey, name, server)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        print("written")

    elif op == "remove":
        path, topkey, name = args[1], args[2], args[3]
        if not os.path.exists(path):
            print("absent")
            return
        with open(path, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
        new_text, changed = remove_server(text, topkey, name)
        if changed:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new_text)
        print("removed" if changed else "absent")

    elif op == "json_valid":
        path, jsonc = args[1], args[2] == "1"
        load_json(path, jsonc)
        print("valid")

    elif op == "toml_check":
        path, name = args[1], args[2]
        env = env_from(args[3:])
        data = toml_load(path)
        srv = data.get("mcp_servers", {}).get(name)
        if srv is None:
            print("absent")
            return
        if srv.get("command") != MCP_CMD:
            print("diff")
            return
        print("same" if toml_env_match(env, srv.get("env")) else "diff")

    elif op == "toml_has":
        path, name = args[1], args[2]
        data = toml_load(path)
        print("present" if name in data.get("mcp_servers", {}) else "absent")

    elif op == "toml_set":
        path, name = args[1], args[2]
        env = env_from(args[3:])
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            text = ""
        else:
            with open(path, "r", encoding="utf-8-sig") as fh:
                text = fh.read()
        span = toml_span(text, name)
        table = toml_table(name, env)
        if span is None:
            if text and not text.endswith("\n"):
                text += "\n"
            text += "\n" + table
        else:
            start, end = span
            text = text[:start] + table + text[end:]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("written")

    elif op == "toml_remove":
        path, name = args[1], args[2]
        with open(path, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
        span = toml_span(text, name)
        if span is None:
            print("absent")
            return
        start, end = span
        s = start
        while s > 0 and text[s - 1] in " \t\r\n":
            s -= 1
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text[:s] + text[end:])
        print("removed")

    elif op == "toml_valid":
        toml_load(args[1])
        print("valid")

    else:
        raise SystemExit("bilinmeyen op: %s" % op)


if __name__ == "__main__":
    main()
PYEOF
}

# =============================================================================
# Yardimci kabuk fonksiyonlari
# =============================================================================

# dry-run'da komutu %q ile yazar, gercekte calistirir
plan_cmd() {
    local q="" a
    for a in "$@"; do q+="$(printf '%q ' "$a")"; done
    dry "calistirilacak: ${q% }"
}
exec_cmd() {
    printf '  %s%s%s\n' "$C_DIM" "\$ $*" "$C_RESET"
    "$@"
}

env_add() { ENV_LINES+=("$1=$2"); }

# Mevcut 'florence' kaydi farkliysa guncelleme onayi; 0 = evet
ask_update() {
    local agent="$1"
    if [ "$ASSUME_YES" = 1 ]; then return 0; fi
    if [ ! -t 0 ]; then
        warn "$agent: mevcut '$MCP_NAME' kaydi farkli — TTY yok, guncellenmedi (--yes ile zorlayin)"
        return 1
    fi
    printf '%s[?]%s %s: mevcut %s kaydi farkli. Guncelle? [e/H] ' \
        "$C_YELLOW" "$C_RESET" "$agent" "$MCP_NAME"
    local ans=""
    read -r ans
    case "${ans:-h}" in
        e|E|y|Y) return 0 ;;
        *) return 1 ;;
    esac
}

# Kimlik env'lerini olusturur
build_identity_env() {
    ENV_LINES=()
    if [ -n "$BOT_USER" ]; then
        IDENTITY_SUMMARY="bot profili (MCP_FLORENCE_BOT=$BOT_USER)"
        env_add "MCP_FLORENCE_BOT" "$BOT_USER"
        if [ "$DRY_RUN" = 0 ]; then
            local pw=""
            if [ -t 0 ]; then
                printf '%s[?]%s Bot sifresi (bos = keyring kullanilir): ' "$C_YELLOW" "$C_RESET"
                read -rs pw
                printf '\n'
            elif [ -n "${MCP_FLORENCE_BOT_PASSWORD:-}" ]; then
                pw="$MCP_FLORENCE_BOT_PASSWORD"
                warn "TTY yok; MCP_FLORENCE_BOT_PASSWORD ortam degiskeni kullanildi"
            else
                warn "TTY yok, sifre sorulamadi — keyring'de kayit varsa kullanilir"
            fi
            if [ -n "$pw" ]; then
                env_add "MCP_FLORENCE_BOT_PASSWORD" "$pw"
            fi
        fi
    elif [ -n "$TOKEN" ]; then
        IDENTITY_SUMMARY="kullanici kimligi (FLORENCE_TOKEN)"
        env_add "FLORENCE_TOKEN" "$TOKEN"
    else
        IDENTITY_SUMMARY="kimliksiz — public tool'lar calisir; sonra --bot/--token ile doldurun"
    fi
    if [ -n "$DOWNLOAD_DIR" ]; then
        env_add "MCP_DOWNLOAD_DIR" "$DOWNLOAD_DIR"
    fi
}

# --- Ajan tespiti -------------------------------------------------------------
detect_all() {
    # Claude Code: binary oncelikli; yoksa ~/.claude.json
    if command -v claude >/dev/null 2>&1; then
        CLAUDE_MODE=cli
    elif [ -f "$HOME/.claude.json" ]; then
        CLAUDE_MODE=json
        CLAUDE_CFG="$HOME/.claude.json"
    fi
    # Codex (OpenAI)
    if command -v codex >/dev/null 2>&1 || [ -d "$HOME/.codex" ]; then
        CODEX_MODE=toml
    fi
    # OpenCode
    local oc_dir="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
    if command -v opencode >/dev/null 2>&1 || [ -d "$oc_dir" ]; then
        if [ -f "$oc_dir/opencode.json" ]; then
            OPENCODE_CFG="$oc_dir/opencode.json"
        elif [ -f "$oc_dir/opencode.jsonc" ]; then
            OPENCODE_CFG="$oc_dir/opencode.jsonc"
        else
            OPENCODE_CFG="$oc_dir/opencode.json"
        fi
        OPENCODE_MODE=jsonc
    fi
    # Cursor
    if [ -d "$HOME/.cursor" ]; then
        CURSOR_MODE=json
    fi
    # Hermes (best-effort)
    if command -v hermes >/dev/null 2>&1; then
        HERMES_MODE=cli
    fi
}

# --- JSON/JSONC ajan duzenleyicileri ------------------------------------------
# $1=ajan adi  $2=cfg  $3=topkey  $4=shape  $5=jsonc(0|1)
json_apply() {
    local agent="$1" cfg="$2" topkey="$3" shape="$4" jsonc="$5"
    local state
    if [ ! -f "$cfg" ] || [ ! -s "$cfg" ]; then
        if [ "$DRY_RUN" = 1 ]; then
            dry "$agent: $cfg olusturulacak ($topkey.$MCP_NAME + kimlik env'leri)"
            return 0
        fi
        mkdir -p "$(dirname "$cfg")"
        if pycfg set "$cfg" "$topkey" "$MCP_NAME" "$shape" "${ENV_LINES[@]+"${ENV_LINES[@]}"}" >/dev/null; then
            chmod 600 "$cfg" 2>/dev/null || :
            ok "$agent: $cfg olusturuldu ($topkey.$MCP_NAME eklendi)"
            WRITTEN_FILES+=("$cfg")
        else
            warn "$agent: $cfg olusturulamadi"
        fi
        return 0
    fi
    if ! state=$(pycfg check "$cfg" "$topkey" "$MCP_NAME" "$shape" "$jsonc" "${ENV_LINES[@]+"${ENV_LINES[@]}"}" 2>&1); then
        warn "$agent: $cfg okunamadi — $(printf '%s' "$state" | tail -n 1)"
        return 0
    fi
    case "$state" in
        same)
            ok "$agent: $MCP_NAME zaten kurulu ve guncel ($cfg)"
            ;;
        absent)
            if [ "$DRY_RUN" = 1 ]; then
                dry "$agent: $cfg -> $topkey.$MCP_NAME eklenecek"
                return 0
            fi
            if pycfg set "$cfg" "$topkey" "$MCP_NAME" "$shape" "${ENV_LINES[@]+"${ENV_LINES[@]}"}" >/dev/null; then
                ok "$agent: $topkey.$MCP_NAME eklendi ($cfg)"
                WRITTEN_FILES+=("$cfg")
            else
                warn "$agent: $cfg guncellenemedi"
            fi
            ;;
        diff)
            if ask_update "$agent"; then
                if [ "$DRY_RUN" = 1 ]; then
                    dry "$agent: $cfg -> $topkey.$MCP_NAME guncellenecek (mevcut kayit farkli)"
                    return 0
                fi
                if pycfg set "$cfg" "$topkey" "$MCP_NAME" "$shape" "${ENV_LINES[@]+"${ENV_LINES[@]}"}" >/dev/null; then
                    ok "$agent: $topkey.$MCP_NAME guncellendi ($cfg)"
                    WRITTEN_FILES+=("$cfg")
                else
                    warn "$agent: $cfg guncellenemedi"
                fi
            else
                info "$agent: mevcut kayit korundu"
            fi
            ;;
    esac
}

# $1=ajan adi  $2=cfg  $3=topkey  $4=jsonc(0|1)
json_remove() {
    local agent="$1" cfg="$2" topkey="$3" jsonc="$4"
    local has
    if [ ! -f "$cfg" ] || [ ! -s "$cfg" ]; then
        info "$agent: $cfg yok — atlandi"
        return 0
    fi
    if ! has=$(pycfg has "$cfg" "$topkey" "$MCP_NAME" "$jsonc" 2>&1); then
        warn "$agent: $cfg okunamadi — atlandi"
        return 0
    fi
    if [ "$has" = present ]; then
        if [ "$DRY_RUN" = 1 ]; then
            dry "$agent: $cfg -> $topkey.$MCP_NAME kaldirilacak"
            return 0
        fi
        if pycfg remove "$cfg" "$topkey" "$MCP_NAME" >/dev/null 2>&1; then
            ok "$agent: $topkey.$MCP_NAME kaldirildi ($cfg)"
        else
            warn "$agent: $cfg'dan kaldirma basarisiz"
        fi
    else
        info "$agent: $MCP_NAME kaydi yok — atlandi"
    fi
}

# --- TOML (Codex) --------------------------------------------------------------
toml_guard() {
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
}

# $1=ajan adi (codex)
toml_apply() {
    local agent="$1" cfg="$HOME/.codex/config.toml"
    local state
    if ! toml_guard; then
        warn "$agent: python3 >= 3.11 gerekli (tomllib) — atlandi"
        return 0
    fi
    if [ ! -f "$cfg" ] || [ ! -s "$cfg" ]; then
        if [ "$DRY_RUN" = 1 ]; then
            dry "$agent: $cfg olusturulacak ([mcp_servers.$MCP_NAME] + kimlik env'leri)"
            return 0
        fi
        mkdir -p "$HOME/.codex"
        if pycfg toml_set "$cfg" "$MCP_NAME" "${ENV_LINES[@]+"${ENV_LINES[@]}"}" >/dev/null; then
            chmod 600 "$cfg" 2>/dev/null || :
            ok "$agent: $cfg olusturuldu ([mcp_servers.$MCP_NAME])"
            WRITTEN_FILES+=("$cfg")
        else
            warn "$agent: $cfg olusturulamadi"
        fi
        return 0
    fi
    if ! state=$(pycfg toml_check "$cfg" "$MCP_NAME" "${ENV_LINES[@]+"${ENV_LINES[@]}"}" 2>&1); then
        warn "$agent: $cfg okunamadi — $(printf '%s' "$state" | tail -n 1)"
        return 0
    fi
    case "$state" in
        same)
            ok "$agent: $MCP_NAME zaten kurulu ve guncel ($cfg)"
            ;;
        absent)
            if [ "$DRY_RUN" = 1 ]; then
                dry "$agent: $cfg -> [mcp_servers.$MCP_NAME] eklenecek"
                return 0
            fi
            if pycfg toml_set "$cfg" "$MCP_NAME" "${ENV_LINES[@]+"${ENV_LINES[@]}"}" >/dev/null; then
                ok "$agent: [mcp_servers.$MCP_NAME] eklendi ($cfg)"
                WRITTEN_FILES+=("$cfg")
            else
                warn "$agent: $cfg guncellenemedi"
            fi
            ;;
        diff)
            if ask_update "$agent"; then
                if [ "$DRY_RUN" = 1 ]; then
                    dry "$agent: $cfg -> [mcp_servers.$MCP_NAME] guncellenecek"
                    return 0
                fi
                if pycfg toml_set "$cfg" "$MCP_NAME" "${ENV_LINES[@]+"${ENV_LINES[@]}"}" >/dev/null; then
                    ok "$agent: [mcp_servers.$MCP_NAME] guncellendi ($cfg)"
                    WRITTEN_FILES+=("$cfg")
                else
                    warn "$agent: $cfg guncellenemedi"
                fi
            else
                info "$agent: mevcut kayit korundu"
            fi
            ;;
    esac
}

toml_remove() {
    local agent="$1" cfg="$HOME/.codex/config.toml"
    local has
    if ! toml_guard; then
        warn "$agent: python3 >= 3.11 gerekli (tomllib) — atlandi"
        return 0
    fi
    if [ ! -f "$cfg" ] || [ ! -s "$cfg" ]; then
        info "$agent: $cfg yok — atlandi"
        return 0
    fi
    if ! has=$(pycfg toml_has "$cfg" "$MCP_NAME" 2>&1); then
        warn "$agent: $cfg okunamadi — atlandi"
        return 0
    fi
    if [ "$has" = present ]; then
        if [ "$DRY_RUN" = 1 ]; then
            dry "$agent: $cfg -> [mcp_servers.$MCP_NAME] kaldirilacak"
            return 0
        fi
        if pycfg toml_remove "$cfg" "$MCP_NAME" >/dev/null 2>&1; then
            ok "$agent: [mcp_servers.$MCP_NAME] kaldirildi ($cfg)"
        else
            warn "$agent: $cfg'dan kaldirma basarisiz"
        fi
    else
        info "$agent: $MCP_NAME kaydi yok — atlandi"
    fi
}

# --- Claude Code (CLI yolu) ----------------------------------------------------
claude_add_cmd() {
    local cmd=(claude mcp add "$MCP_NAME" --scope user)
    local line
    for line in "${ENV_LINES[@]+"${ENV_LINES[@]}"}"; do
        cmd+=(--env "$line")
    done
    cmd+=(-- "$MCP_CMD")
    if [ "$DRY_RUN" = 1 ]; then
        plan_cmd "${cmd[@]}"
        return 0
    fi
    if exec_cmd "${cmd[@]}" >/dev/null 2>&1; then
        ok "claude: $MCP_NAME kaydi eklendi (kullanici kapsami)"
    else
        warn "claude mcp add basarisiz — ~/.claude.json'a dogrudan yaziliyor"
        json_apply "claude" "$HOME/.claude.json" mcpServers claude 0
    fi
}

claude_cli_apply() {
    if [ "$DRY_RUN" = 1 ]; then
        if claude mcp list 2>/dev/null | grep -qw "$MCP_NAME"; then
            dry "claude: mevcut kayit farkli olabilir — claude mcp add ile guncellenecek"
        else
            dry "claude: kayit yok — claude mcp add calistirilacak"
        fi
        claude_add_cmd
        return 0
    fi
    if claude mcp list 2>/dev/null | grep -qw "$MCP_NAME"; then
        if ask_update "claude"; then
            claude_add_cmd
        else
            info "claude: mevcut kayit korundu"
        fi
    else
        claude_add_cmd
    fi
}

claude_cli_remove() {
    if [ "$DRY_RUN" = 1 ]; then
        dry "calistirilacak: claude mcp remove $MCP_NAME (kayit varsa)"
        return 0
    fi
    if claude mcp list 2>/dev/null | grep -qw "$MCP_NAME"; then
        if claude mcp remove "$MCP_NAME" >/dev/null 2>&1; then
            ok "claude: $MCP_NAME kaldirildi"
        else
            warn "claude: kaldirma basarisiz (el ile: claude mcp remove $MCP_NAME)"
        fi
    else
        info "claude: $MCP_NAME kaydi yok — atlandi"
    fi
}

# --- Hermes (CLI yolu, best-effort) ---------------------------------------------
hermes_add_cmd() {
    local cmd=(hermes mcp add "$MCP_NAME" --command "$MCP_CMD" --connect-timeout 20)
    local line
    for line in "${ENV_LINES[@]+"${ENV_LINES[@]}"}"; do
        cmd+=(--env "$line")
    done
    if [ "$DRY_RUN" = 1 ]; then
        plan_cmd "${cmd[@]}"
        dry "not: hermes mcp add, sunucuya baglanip tool'larini kesfeder (florence-mcp calisabilir olmali)"
        return 0
    fi
    if exec_cmd "${cmd[@]}" >/dev/null 2>&1; then
        ok "hermes: $MCP_NAME kaydi eklendi"
    else
        local hint=""
        for line in "${ENV_LINES[@]+"${ENV_LINES[@]}"}"; do
            hint+="--env $line "
        done
        warn "hermes mcp add basarisiz — el ile ekleyin:"
        warn "  hermes mcp add $MCP_NAME --command $MCP_CMD $hint"
        warn "  (diger ajanlarin kayitlari etkilenmedi)"
    fi
}

hermes_apply() {
    if [ "$DRY_RUN" = 1 ]; then
        if hermes mcp list 2>/dev/null | grep -qw "$MCP_NAME"; then
            dry "hermes: mevcut kayit farkli olabilir — hermes mcp add ile guncellenecek"
        else
            dry "hermes: kayit yok — hermes mcp add calistirilacak"
        fi
        hermes_add_cmd
        return 0
    fi
    if hermes mcp list 2>/dev/null | grep -qw "$MCP_NAME"; then
        if ask_update "hermes"; then
            hermes_add_cmd
        else
            info "hermes: mevcut kayit korundu"
        fi
    else
        hermes_add_cmd
    fi
}

hermes_cli_remove() {
    if [ "$DRY_RUN" = 1 ]; then
        dry "calistirilacak: hermes mcp remove $MCP_NAME (kayit varsa)"
        return 0
    fi
    if hermes mcp list 2>/dev/null | grep -qw "$MCP_NAME"; then
        if hermes mcp remove "$MCP_NAME" >/dev/null 2>&1; then
            ok "hermes: $MCP_NAME kaldirildi"
        else
            warn "hermes: kaldirma basarisiz (el ile: hermes mcp remove $MCP_NAME)"
        fi
    else
        info "hermes: $MCP_NAME kaydi yok — atlandi"
    fi
}

# --- Dogrulama ----------------------------------------------------------------
verify_configs() {
    info "Dogrulama (yazilan konfigurasyonlar):"
    local cfg type v
    for cfg in "${WRITTEN_FILES[@]+"${WRITTEN_FILES[@]}"}"; do
        [ -f "$cfg" ] || continue
        case "$cfg" in
            *.toml) type=toml ;;
            *.jsonc) type=jsonc ;;
            *) type=json ;;
        esac
        case "$type" in
            json)  v=$(pycfg json_valid "$cfg" 0 2>&1) || v="gecersiz" ;;
            jsonc) v=$(pycfg json_valid "$cfg" 1 2>&1) || v="gecersiz" ;;
            toml)  v=$(pycfg toml_valid "$cfg" 2>&1) || v="gecersiz" ;;
        esac
        if [ "$v" = valid ]; then
            ok "$cfg — gecerli"
            if [ "$type" = json ] && command -v jq >/dev/null 2>&1; then
                if jq empty "$cfg" >/dev/null 2>&1; then
                    ok "$cfg — jq ile de dogrulandi"
                else
                    warn "$cfg — jq gecersiz buldu!"
                fi
            fi
        else
            warn "$cfg — gecersiz/okunamadi: $v"
        fi
    done
}

# --- Ana akis ------------------------------------------------------------------
main() {
    parse_args "$@"

    case "$(uname -s)" in
        Linux|Darwin) ;;
        MINGW*|MSYS*|CYGWIN*)
            die "Windows desteklenmez — WSL2 veya Docker onerilir."
            ;;
        *)
            warn "Bilinmeyen isletim sistemi: $(uname -s) — script Linux/macOS icin tasarlandi"
            ;;
    esac

    if [ "$DO_REMOVE" = 1 ]; then
        if [ -n "$BOT_USER" ] || [ -n "$TOKEN" ] || [ -n "$DOWNLOAD_DIR" ]; then
            warn "--remove ile kimlik/indirme secenekleri yok sayilir"
        fi
        info "Kurulum kaldirma modu"
    else
        if ! command -v "$MCP_CMD" >/dev/null 2>&1; then
            err "'$MCP_CMD' PATH'te bulunamadi."
            err "Once florence-sdk'yi kurun: repo icinde ./install.sh (veya: pipx install 'florence-sdk')."
            exit 1
        fi
        info "florence-mcp bulundu: $(command -v "$MCP_CMD")"
        build_identity_env
        if [ "$DRY_RUN" = 1 ] && [ -n "$BOT_USER" ]; then
            dry "bot sifresi calisma aninda sorulacak (MCP_FLORENCE_BOT_PASSWORD)"
        fi
    fi

    detect_all

    info "Ajan tespiti:"
    if [ "$CLAUDE_MODE" != none ]; then
        ok "Claude Code — tespit edildi ($CLAUDE_MODE yolu)"
    else
        info "Claude Code — tespit edilmedi"
    fi
    if [ "$CODEX_MODE" != none ]; then
        ok "Codex — tespit edildi"
    else
        info "Codex — tespit edilmedi"
    fi
    if [ "$OPENCODE_MODE" != none ]; then
        ok "OpenCode — tespit edildi"
    else
        info "OpenCode — tespit edilmedi"
    fi
    if [ "$CURSOR_MODE" != none ]; then
        ok "Cursor — tespit edildi"
    else
        info "Cursor — tespit edilmedi"
    fi
    if [ "$HERMES_MODE" != none ]; then
        ok "Hermes — tespit edildi"
    else
        info "Hermes — tespit edilmedi"
    fi

    local any=0
    if [ "$DO_REMOVE" = 1 ]; then
        if [ "$CLAUDE_MODE" = cli ]; then claude_cli_remove; any=1; fi
        if [ "$CLAUDE_MODE" = json ]; then json_remove "claude" "$CLAUDE_CFG" mcpServers 0; any=1; fi
        if [ "$CODEX_MODE" = toml ]; then toml_remove "codex"; any=1; fi
        if [ "$OPENCODE_MODE" = jsonc ]; then json_remove "opencode" "$OPENCODE_CFG" mcp 1; any=1; fi
        if [ "$CURSOR_MODE" = json ]; then json_remove "cursor" "$CURSOR_CFG" mcpServers 0; any=1; fi
        if [ "$HERMES_MODE" = cli ]; then hermes_cli_remove; any=1; fi
    else
        if [ "$CLAUDE_MODE" = cli ]; then claude_cli_apply; any=1; fi
        if [ "$CLAUDE_MODE" = json ]; then json_apply "claude" "$CLAUDE_CFG" mcpServers claude 0; any=1; fi
        if [ "$CODEX_MODE" = toml ]; then toml_apply "codex"; any=1; fi
        if [ "$OPENCODE_MODE" = jsonc ]; then json_apply "opencode" "$OPENCODE_CFG" mcp opencode 1; any=1; fi
        if [ "$CURSOR_MODE" = json ]; then json_apply "cursor" "$CURSOR_CFG" mcpServers cursor 0; any=1; fi
        if [ "$HERMES_MODE" = cli ]; then hermes_apply; any=1; fi
    fi

    if [ "$any" = 0 ]; then
        info "Tespit edilen ajan yok — el ile kurulum icin docs/mcp-install.md inceleyin."
    fi

    if [ "$DO_REMOVE" = 0 ] && [ "$DRY_RUN" = 0 ] && [ "$any" = 1 ]; then
        verify_configs
    fi

    echo
    info "Ozet:"
    if [ "$DO_REMOVE" = 1 ]; then
        info "florence MCP kaydi, tespit edilen ajanlardan kaldirildi/atlandi."
    else
        info "Kimlik: $IDENTITY_SUMMARY"
        info "Sonraki adim: ajani yeniden baslatin; 'auth_status' tool'u ile kimligi dogrulayin"
        info "(docs/mcp-setup.md Bolum 4)."
    fi
}

main "$@"
