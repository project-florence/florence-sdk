#!/usr/bin/env bash
# =============================================================================
# florence-sdk kurulum scripti — Linux / macOS
#
# Yaptiklari:
#   - Paket yoneticisi algilama: apt / dnf / pacman / zypper / apk / brew
#   - Python >= 3.12 yoksa sistem genelinde kurar (apt: python3.12 + deadsnakes
#     PPA opsiyonu; brew: python@3.12; pacman/zypper/apk: python paketi)
#   - uv yoksa kurar (astral.sh standalone kurucu; curl/wget yoksa pip fallback)
#   - Paketi su oncelikle kurar: uv tool install > pipx > pip --user
#   - fl/florence binary yolunu ~/.bashrc / ~/.zshrc / fish config.fish'e
#     idempotent ekler (tekrar calistirmak cift satir olusturmaz)
#   - Basarida `fl --version` ile dogrular ve FLORENCE banner'i basar
#   - --dry-run / --check, --uninstall, --source, -y destegi
#
# Kullanim:
#   curl -fsSL https://raw.githubusercontent.com/project-florence/florence-sdk/main/install.sh | bash
#   bash install.sh --dry-run
#   bash install.sh --source /path/to/florence-sdk
#   bash install.sh --uninstall
#
# Windows desteklenmez (WSL2 veya Docker onerilir).
# =============================================================================
set -euo pipefail

# --- Sabitler ----------------------------------------------------------------
MIN_PY="3.12"
DEFAULT_SOURCE="https://github.com/project-florence/florence-sdk"
MARKER_TOP="# >>> florence-sdk (fl/florence) >>>"
MARKER_BOT="# <<< florence-sdk <<<"

# --- Durum degiskenleri ------------------------------------------------------
DRY_RUN=0
DO_UNINSTALL=0
ASSUME_YES=0
SOURCE_ARG=""
OS=""
PM=""
SUDO=""
PY_BIN=""
PY_VER=""
UV_BIN=""
SOURCE=""
NEED_GIT=0
BIN_DIR=""
RC_FILES=()

# --- Renkler (bagimlilik yok; NO_COLOR / TTY olmayan ortamda kapanir) --------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-}" != "dumb" ]; then
    USE_COLOR=1
    C_RESET=$'\033[0m'
    C_DIM=$'\033[2m'
    C_RED=$'\033[31m'
    C_GREEN=$'\033[32m'
    C_YELLOW=$'\033[33m'
    C_BLUE=$'\033[34m'
    C_MAGENTA=$'\033[35m'
    C_CYAN=$'\033[36m'
else
    USE_COLOR=0
    C_RESET=""
    C_DIM=""
    C_RED=""
    C_GREEN=""
    C_YELLOW=""
    C_BLUE=""
    C_MAGENTA=""
    C_CYAN=""
fi

# --- Log yardimcilari --------------------------------------------------------
info() { printf '%s==>%s %s\n' "$C_CYAN" "$C_RESET" "$*"; }
ok()   { printf '%s[OK]%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%s[!]%s %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
err()  { printf '%s[HATA]%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; }
dry()  { printf '%s[dry-run]%s %s\n' "$C_DIM" "$C_RESET" "$*"; }
die()  { err "$*"; exit 1; }

# --- Calistir: dry-run'da sadece goster, gercekte calistir -------------------
run() {
    if [ "$DRY_RUN" = 1 ]; then
        dry "$*"
        return 0
    fi
    printf '  %s%s%s\n' "$C_DIM" "\$ $*" "$C_RESET"
    "$@"
}

# --- Paket yoneticisi komutu (gerekirse sudo on eki) -------------------------
pm() {
    local cmd
    cmd=("$@")
    if [ "${cmd[0]}" = "brew" ]; then
        # brew asla sudo ile calistirilmaz (Linux'ta da)
        run "${cmd[@]}"
        return 0
    fi
    if [ -z "$SUDO" ] && [ "$(id -u)" != 0 ]; then
        die "Paket kurulumu icin root veya sudo gerekli: $*"
    fi
    if [ -n "$SUDO" ]; then
        cmd=("$SUDO" "${cmd[@]}")
    fi
    run "${cmd[@]}"
}

# --- Kullanim ----------------------------------------------------------------
usage() {
    cat <<'EOF'
florence-sdk kurulum scripti (Linux/macOS) — Python SDK + CLI (fl / florence)

Kullanim:
  install.sh [SECENEKLER]

Secenekler:
  --dry-run, --check   Hicbir degisiklik yapmaz; yapilacaklari gosterir
  --uninstall          PATH satirlarini ve kurulu paketi kaldirir
  --source <YOL|URL>   Kaynak: yerel dizin veya git URL (varsayilan: GitHub repo)
  -y, --yes            Onay sorusu sormadan devam eder
  -h, --help           Bu yardimi gosterir

Ornekler:
  bash install.sh                              # git URL'den kur
  bash install.sh --source /path/to/florence-sdk
  bash install.sh --dry-run
  bash install.sh --uninstall

curl ile:
  curl -fsSL https://raw.githubusercontent.com/project-florence/florence-sdk/main/install.sh | bash
EOF
}

# --- Arguman ayrisma ---------------------------------------------------------
parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --dry-run|--check)
                DRY_RUN=1
                ;;
            --uninstall)
                DO_UNINSTALL=1
                ;;
            --source)
                SOURCE_ARG="${2:-}"
                if [ -z "$SOURCE_ARG" ]; then
                    die "--source bir deger ister: --source <YOL|URL>"
                fi
                shift
                ;;
            -y|--yes)
                ASSUME_YES=1
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                die "Bilinmeyen arguman: $1 (--help ile kullanimi gosterin)"
                ;;
        esac
        shift
    done
}

# --- Isletim sistemi ---------------------------------------------------------
detect_os() {
    local uname_s
    uname_s="$(uname -s)"
    case "$uname_s" in
        Linux)
            OS="linux"
            ;;
        Darwin)
            OS="macos"
            ;;
        MINGW*|MSYS*|CYGWIN*|*_NT-*)
            die "Windows desteklenmiyor. WSL2 (Linux) veya Docker onerilir."
            ;;
        *)
            die "Desteklenmeyen isletim sistemi: ${uname_s}"
            ;;
    esac
    info "Isletim sistemi: ${OS}"
    if [ "$(id -u)" = 0 ]; then
        SUDO=""
    elif command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        SUDO=""
    fi
}

# --- Paket yoneticisi --------------------------------------------------------
detect_pm() {
    PM=""
    if command -v apt-get >/dev/null 2>&1; then
        PM="apt"
    elif command -v dnf >/dev/null 2>&1; then
        PM="dnf"
    elif command -v pacman >/dev/null 2>&1; then
        PM="pacman"
    elif command -v zypper >/dev/null 2>&1; then
        PM="zypper"
    elif command -v apk >/dev/null 2>&1; then
        PM="apk"
    elif command -v brew >/dev/null 2>&1; then
        PM="brew"
    fi
    if [ -n "$PM" ]; then
        info "Paket yoneticisi: ${PM}"
    else
        warn "Bilinen paket yoneticisi bulunamadi; sistem paketi kurulumu atlanir."
    fi
}

# --- Python >= 3.12 bul ------------------------------------------------------
find_python() {
    local candidates
    local c
    local bin
    candidates=(python3 python3.14 python3.13 python3.12)
    if [ -x /opt/homebrew/bin/python3.12 ]; then
        candidates+=("/opt/homebrew/bin/python3.12")
    fi
    if [ -x /opt/homebrew/bin/python3 ]; then
        candidates+=("/opt/homebrew/bin/python3")
    fi
    if [ -x /usr/local/bin/python3.12 ]; then
        candidates+=("/usr/local/bin/python3.12")
    fi
    for c in "${candidates[@]}"; do
        if [ -x "$c" ]; then
            bin="$c"
        elif command -v "$c" >/dev/null 2>&1; then
            bin="$(command -v "$c")"
        else
            continue
        fi
        if "$bin" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1; then
            PY_BIN="$bin"
            PY_VER="$("$bin" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
            return 0
        fi
    done
    return 1
}

# --- Python kur (sistem paket yoneticisi ile) --------------------------------
ensure_python() {
    if find_python; then
        ok "Python ${PY_VER} bulundu: ${PY_BIN}"
        return 0
    fi
    if [ -z "$PM" ]; then
        die "Python >= ${MIN_PY} bulunamadi ve paket yoneticisi tespit edilemedi. Lutfen Python ${MIN_PY}+ kurun: https://python.org/downloads/"
    fi
    warn "Python >= ${MIN_PY} bulunamadi; '${PM}' ile sistem genelinde kuruluyor..."
    case "$PM" in
        apt)
            pm apt-get update
            if pm apt-get install -y python3.12; then
                :
            else
                if grep -q '^ID=ubuntu' /etc/os-release 2>/dev/null; then
                    info "python3.12 paketi bulunamadi; deadsnakes PPA deneniyor..."
                    pm apt-get install -y software-properties-common
                    pm add-apt-repository -y ppa:deadsnakes/ppa
                    pm apt-get update
                    pm apt-get install -y python3.12
                else
                    pm apt-get install -y python3
                fi
            fi
            ;;
        dnf)
            if pm dnf install -y python3.12; then
                :
            else
                pm dnf install -y python3
            fi
            ;;
        pacman)
            pm pacman -S --noconfirm python
            ;;
        zypper)
            if pm zypper --non-interactive install python312; then
                :
            else
                pm zypper --non-interactive install python3
            fi
            ;;
        apk)
            pm apk add --no-cache python3
            ;;
        brew)
            if pm brew install python@3.12; then
                :
            else
                pm brew install python
            fi
            ;;
    esac
    if find_python; then
        ok "Python ${PY_VER} kuruldu: ${PY_BIN}"
    else
        die "Python >= ${MIN_PY} kurulamadi. Lutfen manuel kurun: https://python.org/downloads/"
    fi
}

# --- uv kur ----------------------------------------------------------------
ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        UV_BIN="$(command -v uv)"
        ok "uv bulundu: ${UV_BIN}"
        return 0
    fi
    if [ -x "$HOME/.local/bin/uv" ]; then
        UV_BIN="$HOME/.local/bin/uv"
        export PATH="$HOME/.local/bin:$PATH"
        ok "uv bulundu: ${UV_BIN}"
        return 0
    fi
    warn "uv bulunamadi; kuruluyor (onerilen arac)."
    local installer=""
    if command -v curl >/dev/null 2>&1; then
        installer="curl -LsSf https://astral.sh/uv/install.sh | sh"
    elif command -v wget >/dev/null 2>&1; then
        installer="wget -qO- https://astral.sh/uv/install.sh | sh"
    else
        if [ -n "$PM" ]; then
            warn "curl/wget yok; '${PM}' ile curl kuruluyor..."
            case "$PM" in
                apt)  pm apt-get update; pm apt-get install -y curl ;;
                dnf)  pm dnf install -y curl ;;
                pacman) pm pacman -S --noconfirm curl ;;
                zypper) pm zypper --non-interactive install curl ;;
                apk)  pm apk add --no-cache curl ;;
                brew) pm brew install curl ;;
            esac
            installer="curl -LsSf https://astral.sh/uv/install.sh | sh"
        else
            warn "curl/wget yok; uv, pip ile kurulacak."
            if [ "$DRY_RUN" = 1 ]; then
                dry "\"${PY_BIN}\" -m pip install --user uv"
            elif "$PY_BIN" -m pip install --user uv; then
                :
            else
                "$PY_BIN" -m pip install --user --break-system-packages uv
            fi
        fi
    fi
    if [ -n "$installer" ]; then
        if [ "$DRY_RUN" = 1 ]; then
            dry "${installer}   # uv -> ~/.local/bin"
        else
            info "uv standalone kurucu calistiriliyor (astral.sh)..."
            if [[ "$installer" == curl* ]]; then
                curl -LsSf https://astral.sh/uv/install.sh | sh
            else
                wget -qO- https://astral.sh/uv/install.sh | sh
            fi
        fi
    fi
    if [ "$DRY_RUN" = 1 ]; then
        UV_BIN="$HOME/.local/bin/uv"
        return 0
    fi
    if [ -x "$HOME/.local/bin/uv" ]; then
        UV_BIN="$HOME/.local/bin/uv"
        export PATH="$HOME/.local/bin:$PATH"
    elif command -v uv >/dev/null 2>&1; then
        UV_BIN="$(command -v uv)"
    else
        die "uv kurulamadi. Manuel: curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
    ok "uv kuruldu: ${UV_BIN}"
}

# --- git kur (git URL kaynak icin gerekli) -----------------------------------
ensure_git() {
    if command -v git >/dev/null 2>&1; then
        return 0
    fi
    if [ -z "$PM" ]; then
        die "git bulunamadi ve paket yoneticisi yok; lutfen manuel kurun."
    fi
    warn "git bulunamadi; kuruluyor..."
    case "$PM" in
        apt)    pm apt-get update; pm apt-get install -y git ;;
        dnf)    pm dnf install -y git ;;
        pacman) pm pacman -S --noconfirm git ;;
        zypper) pm zypper --non-interactive install git ;;
        apk)    pm apk add --no-cache git ;;
        brew)   pm brew install git ;;
    esac
    command -v git >/dev/null 2>&1 || die "git kurulumu basarisiz."
}

# --- Kaynak cozumleme (yerel dizin veya git URL) -----------------------------
resolve_source() {
    if [ -n "$SOURCE_ARG" ]; then
        if [ -d "$SOURCE_ARG" ]; then
            SOURCE="$(cd "$SOURCE_ARG" && pwd -P)"
            info "Kaynak: yerel dizin ${SOURCE}"
        elif [[ "$SOURCE_ARG" == http://* || "$SOURCE_ARG" == https://* || "$SOURCE_ARG" == git@* || "$SOURCE_ARG" == git+* ]]; then
            SOURCE="$SOURCE_ARG"
            info "Kaynak: git URL ${SOURCE}"
        else
            die "--source degeri yerel dizin veya git URL olmali: ${SOURCE_ARG}"
        fi
    else
        # Repo icinden calisiliyorsa yerel dizini kullan
        if [ -f pyproject.toml ] && grep -q 'name = "florence-sdk"' pyproject.toml 2>/dev/null; then
            SOURCE="$PWD"
            info "Kaynak: mevcut dizin (repo icindeyiz): ${SOURCE}"
        else
            SOURCE="$DEFAULT_SOURCE"
            info "Kaynak: ${SOURCE}"
        fi
    fi
    if [[ "$SOURCE" == http://* || "$SOURCE" == https://* ]]; then
        if [[ "$SOURCE" != git+* ]]; then
            SOURCE="git+${SOURCE}"
        fi
        NEED_GIT=1
    else
        NEED_GIT=0
    fi
}

# --- Paket kurulumu: uv tool > pipx > pip --user -----------------------------
install_package() {
    info "Paket kurulumu basliyor (kaynak: ${SOURCE})..."
    local method=""
    if command -v uv >/dev/null 2>&1 || [ -x "$HOME/.local/bin/uv" ]; then
        method="uv"
    elif command -v pipx >/dev/null 2>&1; then
        method="pipx"
    else
        method="pip"
    fi
    case "$method" in
        uv)
            info "Yontem: uv tool install"
            if [ "$DRY_RUN" = 1 ]; then
                dry "uv tool install --python ${PY_BIN} ${SOURCE}"
            else
                uv tool install --python "$PY_BIN" "$SOURCE"
            fi
            BIN_DIR="${UV_TOOL_BIN_DIR:-$HOME/.local/bin}"
            ;;
        pipx)
            info "Yontem: pipx"
            if [ "$DRY_RUN" = 1 ]; then
                dry "pipx install --python ${PY_BIN} ${SOURCE}"
            else
                pipx install --python "$PY_BIN" "$SOURCE"
            fi
            BIN_DIR="${PIPX_BIN_DIR:-$HOME/.local/bin}"
            ;;
        pip)
            info "Yontem: pip --user"
            if [ "$DRY_RUN" = 1 ]; then
                dry "\"${PY_BIN}\" -m pip install --user ${SOURCE}"
            elif "$PY_BIN" -m pip install --user "$SOURCE"; then
                :
            else
                warn "PEP 668 (externally-managed) hatasi olabilir; --break-system-packages ile tekrar deneniyor..."
                "$PY_BIN" -m pip install --user --break-system-packages "$SOURCE"
            fi
            if [ "$OS" = "macos" ]; then
                BIN_DIR="$HOME/Library/Python/${PY_VER}/bin"
            else
                BIN_DIR="$HOME/.local/bin"
            fi
            ;;
    esac
    ok "Binary dizini: ${BIN_DIR}"
}

# --- Shell rc dosyalarini algila ---------------------------------------------
detect_rc_files() {
    local shell_name=""
    if [ -n "${SHELL:-}" ]; then
        shell_name="$(basename "$SHELL")"
    fi
    if [ -z "$shell_name" ]; then
        local pw=""
        if command -v getent >/dev/null 2>&1; then
            pw="$(getent passwd "$(id -u)" 2>/dev/null | cut -d: -f7 || true)"
        fi
        shell_name="$(basename "${pw:-}")"
    fi
    RC_FILES=()
    case "$shell_name" in
        zsh)
            RC_FILES+=("$HOME/.zshrc")
            if [ "$OS" = "macos" ]; then
                RC_FILES+=("$HOME/.zprofile")
            fi
            ;;
        fish)
            RC_FILES+=("$HOME/.config/fish/config.fish")
            ;;
        bash)
            RC_FILES+=("$HOME/.bashrc")
            ;;
        *)
            warn "Shell algilanamadi; .bashrc ve .zshrc'ye eklenecek."
            RC_FILES+=("$HOME/.bashrc" "$HOME/.zshrc")
            ;;
    esac
    info "PATH eklenecek dosyalar: ${RC_FILES[*]}"
}

# --- PATH blogu ekle (idempotent; markera gore degistir/ekle) ----------------
add_path_block() {
    local file="$1"
    local dir="$2"
    local line=""
    local tmp=""
    local perms=""
    if [ "$(basename "$file")" = "config.fish" ]; then
        line="fish_add_path ${dir}"
    else
        line="export PATH=\"${dir}:\$PATH\""
    fi
    if [ "$DRY_RUN" = 1 ]; then
        dry "PATH satiri -> ${file}: ${line}"
        return 0
    fi
    mkdir -p "$(dirname "$file")"
    [ -f "$file" ] || touch "$file"
    if grep -qF "$MARKER_TOP" "$file"; then
        tmp="$(mktemp)"
        awk -v top="$MARKER_TOP" -v bot="$MARKER_BOT" -v line="$line" '
            index($0, top) { in_block = 1; print; print line; next }
            in_block && index($0, bot) { in_block = 0; print; next }
            !in_block { print }
        ' "$file" > "$tmp"
        perms="$(stat -c '%a' "$file" 2>/dev/null || stat -f '%Lp' "$file" 2>/dev/null || printf '644')"
        chmod "$perms" "$tmp"
        mv "$tmp" "$file"
        ok "PATH blogu guncellendi: ${file}"
    else
        {
            printf '\n%s\n' "$MARKER_TOP"
            printf '%s\n' "$line"
            printf '%s\n' "$MARKER_BOT"
        } >> "$file"
        ok "PATH eklendi: ${file}"
    fi
}

# --- PATH blogu kaldir -------------------------------------------------------
remove_path_block() {
    local file="$1"
    local tmp=""
    local perms=""
    if [ "$DRY_RUN" = 1 ]; then
        dry "PATH blogu kaldirilacak: ${file}"
        return 0
    fi
    [ -f "$file" ] || return 0
    grep -qF "$MARKER_TOP" "$file" || return 0
    tmp="$(mktemp)"
    awk -v top="$MARKER_TOP" -v bot="$MARKER_BOT" '
        index($0, top) { in_block = 1; next }
        in_block && index($0, bot) { in_block = 0; next }
        !in_block { print }
    ' "$file" > "$tmp"
    perms="$(stat -c '%a' "$file" 2>/dev/null || stat -f '%Lp' "$file" 2>/dev/null || printf '644')"
    chmod "$perms" "$tmp"
    mv "$tmp" "$file"
    ok "PATH blogu kaldirildi: ${file}"
}

# --- Dogrulama ---------------------------------------------------------------
verify_install() {
    info "Kurulum dogrulaniyor..."
    if [ "$DRY_RUN" = 1 ]; then
        dry "PATH=\"${BIN_DIR}:\$PATH\" fl --version"
        dry "PATH=\"${BIN_DIR}:\$PATH\" florence --version"
        return 0
    fi
    local fl_bin=""
    if command -v fl >/dev/null 2>&1; then
        fl_bin="$(command -v fl)"
    elif [ -x "$BIN_DIR/fl" ]; then
        fl_bin="$BIN_DIR/fl"
    fi
    if [ -z "$fl_bin" ]; then
        die "Dogrulama basarisiz: 'fl' binary'si bulunamadi (${BIN_DIR})."
    fi
    local ver=""
    local rc=0
    ver="$("$fl_bin" --version 2>&1)" || rc=$?
    if [ "$rc" -eq 0 ]; then
        ok "Dogrulama basarili: ${ver}"
    else
        warn "'fl --version' basarisiz (rc=${rc}); 'fl --help' ile deneniyor..."
        "$fl_bin" --help >/dev/null 2>&1 || die "Dogrulama basarisiz: fl calismiyor (${BIN_DIR})."
        ok "Dogrulama basarili: fl --help OK"
    fi
    if [ ! -x "$BIN_DIR/florence" ] && ! command -v florence >/dev/null 2>&1; then
        warn "'florence' binary'si ${BIN_DIR} altinda bulunamadi (fl yeterli)."
    fi
}

# --- FLORENCE banner'i (statik ASCII + ANSI; bagimlilik yok) -----------------
print_banner() {
    local lines
    local colors
    lines=(
        "███████╗██╗      ██████╗ ██████╗ ███████╗███╗   ██╗ ██████╗███████╗"
        "██╔════╝██║     ██╔═══██╗██╔══██╗██╔════╝████╗  ██║██╔════╝██╔════╝"
        "█████╗  ██║     ██║   ██║██████╔╝█████╗  ██╔██╗ ██║██║     █████╗  "
        "██╔══╝  ██║     ██║   ██║██╔══██╗██╔══╝  ██║╚██╗██║██║     ██╔══╝  "
        "██║     ███████╗╚██████╔╝██║  ██║███████╗██║ ╚████║╚██████╗███████╗"
        "╚═╝     ╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝ ╚═════╝╚══════╝"
    )
    colors=(228 226 220 214 208 202)   # sari -> turuncu gradient
    printf '\n'
    if [ "$USE_COLOR" = 1 ]; then
        local i
        for i in "${!lines[@]}"; do
            printf '\033[38;5;%sm%s\033[0m\n' "${colors[$i]}" "${lines[$i]}"
        done
        printf '%s%s%s\n' "$C_BLUE" "============================================================" "$C_RESET"
        printf '%s%s%s\n' "$C_MAGENTA" "  ✨ florence-sdk kuruldu — Python SDK + CLI (fl / florence)" "$C_RESET"
        printf '%s%s%s\n' "$C_CYAN" "  Baslamak icin:  fl --help   |   fl price THYAO" "$C_RESET"
    else
        local line
        for line in "${lines[@]}"; do
            printf '%s\n' "$line"
        done
        printf '%s\n' "============================================================"
        printf '%s\n' "  florence-sdk kuruldu — Python SDK + CLI (fl / florence)"
        printf '%s\n' "  Baslamak icin:  fl --help   |   fl price THYAO"
    fi
    printf '\n'
}

# --- Kaldirma ----------------------------------------------------------------
do_uninstall() {
    info "florence-sdk kaldiriliyor..."
    detect_os
    detect_rc_files
    local f
    for f in "${RC_FILES[@]}"; do
        remove_path_block "$f"
    done
    if command -v uv >/dev/null 2>&1 || [ -x "$HOME/.local/bin/uv" ]; then
        if [ "$DRY_RUN" = 1 ]; then
            dry "uv tool uninstall florence-sdk"
        elif uv tool uninstall florence-sdk >/dev/null 2>&1; then
            ok "uv tool kaldirildi: florence-sdk"
        fi
    fi
    if command -v pipx >/dev/null 2>&1; then
        if [ "$DRY_RUN" = 1 ]; then
            dry "pipx uninstall florence-sdk"
        elif pipx uninstall florence-sdk >/dev/null 2>&1; then
            ok "pipx kaldirildi: florence-sdk"
        fi
    fi
    if command -v python3 >/dev/null 2>&1; then
        if [ "$DRY_RUN" = 1 ]; then
            dry "python3 -m pip uninstall -y florence-sdk"
        elif python3 -m pip uninstall -y florence-sdk >/dev/null 2>&1; then
            ok "pip paketi kaldirildi: florence-sdk"
        fi
    fi
    info "Not: Python/uv/curl/git sistem paketleri kaldirilmadi (baska arac kullaniyor olabilir)."
    ok "Kaldirma tamamlandi. Yeni terminal acin; 'fl' artik bulunmamali."
}

# --- Onay --------------------------------------------------------------------
confirm() {
    if [ "$ASSUME_YES" = 1 ]; then
        return 0
    fi
    if [ ! -t 0 ]; then
        return 0    # pipe (curl|bash) ortaminda sorma
    fi
    local ans=""
    printf '%s%s%s ' "$C_YELLOW" "$1 [Evet/hayir]" "$C_RESET"
    read -r ans || true
    case "$ans" in
        ""|e|E|evet|Evet|EVET|y|Y|yes|Yes|YES) return 0 ;;
        *) return 1 ;;
    esac
}

# --- Ana akis ----------------------------------------------------------------
main() {
    parse_args "$@"
    if [ "$DO_UNINSTALL" = 1 ]; then
        do_uninstall
        exit 0
    fi
    detect_os
    detect_pm
    resolve_source
    if [ "$DRY_RUN" = 1 ]; then
        warn "DRY-RUN modu: hicbir degisiklik yapilmayacak; sadece plan gosteriliyor."
        printf '\n'
    fi
    if [ "$DRY_RUN" != 1 ]; then
        confirm "Kuruluma devam edilsin mi?" || {
            warn "Iptal edildi."
            exit 1
        }
    fi
    ensure_python
    ensure_uv
    if [ "$NEED_GIT" = 1 ]; then
        ensure_git
    fi
    install_package
    detect_rc_files
    local f
    for f in "${RC_FILES[@]}"; do
        add_path_block "$f" "$BIN_DIR"
    done
    verify_install
    print_banner
    if [ "$DRY_RUN" = 1 ]; then
        warn "DRY-RUN tamamlandi: hicbir sey degistirilmedi."
    else
        info "Kurulum tamamlandi. Yeni terminal acin veya: source ${RC_FILES[0]}"
        info "Kullanim: fl --help | fl auth login <kullanici> | fl price THYAO"
    fi
}

# Kaynak olarak yuklenirse main calismaz (test/parcali kullanim icin)
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
