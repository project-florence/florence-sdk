"""Cikti katmani: --json (tek JSON belgesi, stdout) ve insan tablolari (rich).

Kurallar (tasarim bolum 3):
- stdout = veri, stderr = hata/progress.
- ``--json``'da stdout'a yalnizca TEK JSON belgesi (nesne veya dizi).
- Hatalar ``--json``'da stderr'e tek JSON satiri: ``{"error": {...}}``.
- Sayilar insan modunda TR bicimi (``1.234,50``), JSON'da ham deger.
- Ekonomi degerleri ``"40,25"`` -> ``40.25`` (float) normalize edilir
  (sunum katmaninda; SDK'ya dokunulmaz).
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from rich.console import Console
from rich.table import Table

from ..errors import AuthError, FlorenceAPIError, NetworkError, RateLimitError

__all__ = [
    "TRUNCATE_LIMIT",
    "emit_json",
    "fmt_value",
    "format_error_json",
    "human_detail",
    "normalize_economy",
    "render_data",
    "render_kv",
    "render_table",
    "tr_number",
]

#: Tablo hucrelerinde uzun metin kirpma siniri (3.4).
TRUNCATE_LIMIT = 40

console = Console()
err_console = Console(stderr=True)  # hata ciktisi stderr'e (tasarim 3.1)

#: Turk virgullu ondalik kaliplari: "40,25", "1.234,56", "%0,42", "-0,5"
_TR_THOUSANDS = re.compile(r"^[%+\-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?%?$")
_TR_PLAIN = re.compile(r"^[%+\-]?\d+(?:,\d+)?%?$")


def emit_json(data: Any) -> None:
    """stdout'a tek JSON belgesi yazar (makine-okunur cikti)."""
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def tr_number(value: float) -> str:
    """Sayiyi TR biciminde bicimler: 1234.5 -> ``1.234,50``."""
    negative = value < 0
    text = f"{abs(value):,.2f}"
    text = text.replace(",", "\u00a7").replace(".", ",").replace("\u00a7", ".")
    return f"-{text}" if negative else text


def truncate(text: str, limit: int = TRUNCATE_LIMIT) -> str:
    """Uzun metni ``limit`` karakterde kirpar (sona ``…`` ekler)."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def fmt_value(value: Any) -> str:
    """Bir degeri insan-okur metne cevirir (tablo hucreleri icin)."""
    if isinstance(value, float):
        return tr_number(value)
    if isinstance(value, bool):
        return "evet" if value else "hayır"
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        return truncate(json.dumps(value, ensure_ascii=False))
    return str(value)


def _columns_of(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def render_table(rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    """Dict satirlarini rich tabloya basar. Bos liste -> 'Kayıt yok'."""
    if not rows:
        print("Kayıt yok")
        return
    cols = columns or _columns_of(rows)
    table = Table(show_header=True, header_style="bold cyan", title_justify="left")
    for col in cols:
        table.add_column(str(col))
    for row in rows:
        table.add_row(*[truncate(fmt_value(row.get(col))) for col in cols])
    console.print(table)


def render_kv(data: dict[str, Any]) -> None:
    """Anahtar-deger blogu (kenarliksiz tablo)."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Alan", style="bold", no_wrap=True)
    table.add_column("Değer")
    for key, value in data.items():
        table.add_row(str(key), fmt_value(value))
    console.print(table)


#: Dict icinde tabloya cevrilebilecek liste anahtarlari.
_LIST_KEYS = (
    "history",
    "data",
    "items",
    "results",
    "prices",
    "candles",
    "records",
    "bots",
    "reports",
    "simulations",
    "ipos",
    "announcements",
    "transactions",
    "favorites",
    "news",
)


def render_data(data: Any) -> None:
    """API yanitini insan-okur bicimde basar (genel dagitici).

    - ``None`` -> basari mesaji
    - str -> ham metin (stdout)
    - dict -> anahtar-deger; icinde liste varsa once skalerler, sonra tablolar
    - liste -> tablo (dict satirlari) veya satir satir degerler
    """
    if data is None:
        print("İşlem başarılı")
        return
    if isinstance(data, str):
        print(data)
        return
    if isinstance(data, list):
        if not data:
            print("Kayıt yok")
            return
        if all(isinstance(item, dict) for item in data):
            render_table(data)
            return
        for item in data:
            print(fmt_value(item))
        return
    if isinstance(data, dict):
        if len(data) == 1 and "message" in data:
            print(str(data["message"]))
            return
        list_keys = [
            key
            for key, value in data.items()
            if isinstance(value, list) and value and isinstance(value[0], dict)
        ]
        scalar = {key: value for key, value in data.items() if key not in list_keys}
        if list_keys:
            if scalar:
                render_kv(scalar)
            for key in list_keys:
                render_table(data[key])
            return
        render_kv(data)
        return
    print(fmt_value(data))


# ----------------------------------------------------------------------
# Ekonomi normalizasyonu (sunum katmani)
# ----------------------------------------------------------------------
def _tr_decimal_to_float(value: str) -> float | None:
    """Turk virgullu ondalik string'i float'a cevirir; uymazsa ``None``."""
    text = value.strip()
    if not (_TR_THOUSANDS.match(text) or _TR_PLAIN.match(text)):
        return None
    if "," not in text:
        return None  # yalnizca virgullu ondalik normalize edilir
    negative = text.startswith("-")
    cleaned = text.lstrip("+-").rstrip("%").replace(".", "").replace(",", ".")
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return -number if negative else number


def normalize_economy(obj: Any) -> Any:
    """Ekonomi yanitlarindaki ``"40,25"`` degerlerini float'a cevirir (derin).

    Ornek: ``{"gram-altin": "40,25"}`` -> ``{"gram-altin": 40.25}``.
    Makine tuketicisi string istemez; SDK ham veriyi korur, CLI sunar.
    """
    if isinstance(obj, dict):
        return {key: normalize_economy(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [normalize_economy(value) for value in obj]
    if isinstance(obj, str):
        number = _tr_decimal_to_float(obj)
        return number if number is not None else obj
    return obj


# ----------------------------------------------------------------------
# Hata bicimlendirme (--json ve insan)
# ----------------------------------------------------------------------
_KNOWN_CODE_MESSAGES: dict[str, str] = {
    "error_login_failed": "Kullanıcı adı veya şifre hatalı",
    "error_email_not_verified": "E-posta adresi doğrulanmamış; doğrulama mailini kontrol edin",
    "error_username_taken": "Kullanıcı adı zaten alınmış",
    "error_email_taken": "E-posta adresi zaten kayıtlı",
    "error_bots_not_allowed": "Bot hesabı oluşturmaya izniniz yok",
    "error_bot_limit_reached": "Maksimum bot hesabı sayısına ulaşıldı (5)",
    "error_not_found": "Kayıt bulunamadı",
    "error_insufficient_credits": "Kredi yetersiz",
    "error_report_generation_in_progress": "Rapor üretimi zaten devam ediyor",
    "error_export_limit_reached": "Saatlik export limiti aşıldı (3)",
    "error_market_closed": "Piyasa kapalı; işlem yapılamıyor",
    "error_invalid_credentials": "Geçersiz kimlik bilgileri",
    "error_verification_required": "E-posta doğrulaması gerekli",
}


def human_detail(exc: BaseException) -> str:
    """Hata nesnesinden insan-okur, Turkce aciklama uretir."""
    if isinstance(exc, RateLimitError):
        retry = exc.retry_after
        suffix = f"; {retry:.0f}s sonra tekrar deneyin" if retry else ""
        return f"Rate limit aşıldı (429){suffix}"
    if isinstance(exc, AuthError):
        code = exc.code or "not_authenticated"
        message = _KNOWN_CODE_MESSAGES.get(code)
        if message:
            return message
        detail = exc.detail
        return f"Kimlik doğrulama hatası: {detail if detail is not None else code}"
    if isinstance(exc, FlorenceAPIError):
        code = exc.code
        if code and code in _KNOWN_CODE_MESSAGES:
            return _KNOWN_CODE_MESSAGES[code]
        if isinstance(exc.detail, str) and exc.detail:
            return exc.detail
        status = exc.status_code
        return f"API hatası {status}: {code if code else 'bilinmeyen hata'}"
    if isinstance(exc, NetworkError):
        return f"Bağlantı hatası: {exc}"
    return str(exc) or exc.__class__.__name__


def error_code(exc: BaseException) -> str:
    """--json hata bicimi icin makine kodu (tasarim 3.1)."""
    if isinstance(exc, FlorenceAPIError):
        if exc.code:
            return exc.code
        if exc.status_code == 401:
            return "not_authenticated"
        if exc.status_code == 404:
            return "not_found"
        if exc.status_code == 429:
            return "rate_limited"
        return "api_error"
    if isinstance(exc, NetworkError):
        return "network"
    return "error"


def error_status(exc: BaseException) -> int | None:
    """--json hata bicimi icin HTTP durum kodu (yerel hatalarda ``None``)."""
    if isinstance(exc, FlorenceAPIError):
        return exc.status_code
    return None


def format_error_json(exc: BaseException) -> dict[str, Any]:
    """``{"error": {"code", "status", "detail"}}`` semasi (tasarim 3.1)."""
    return {
        "error": {
            "code": error_code(exc),
            "status": error_status(exc),
            "detail": human_detail(exc),
        }
    }


def emit_error(exc: BaseException, *, json_mode: bool) -> None:
    """Hatayi stderr'e basar (insan veya --json biciminde)."""
    if json_mode:
        print(json.dumps(format_error_json(exc), ensure_ascii=False), file=sys.stderr)
    else:
        err_console.print(f"[bold red]Hata:[/] {human_detail(exc)}")
