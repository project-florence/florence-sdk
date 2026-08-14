"""CLI yardimci fonksiyonlari: ticker dogrulama, period cozumleme, CSV yazimi.

Sunum/cozumleme katmani — SDK'ya dokunmaz, yalnizca CLI giris cikti isler.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import Any

#: BIST ticker bicimi (aliases dahil): THYAO, XU100, .E sonekleri vb.
_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")

#: Period normalizasyonu: 3m -> 3mo, 6m -> 6mo, 1y, 1w, 1d (kucuk/buyuk harf).
_PERIOD_RE = re.compile(r"^(\d+)\s*(mo|m|y|w|d)$", re.IGNORECASE)


def normalize_ticker(ticker: str) -> str:
    """Ticker'i buyuk harfe cevirir; degisimde stderr'e uyari basar.

    Bicim uyumsuzlugu hard-fail DEGILDIR (backend alias destekler) —
    yalnizca uyari. 3.6 tasarim kurali.
    """
    upper = ticker.strip().upper()
    if upper != ticker:
        print(
            f"Uyari: Ticker buyuk harfe cevrildi: {ticker} -> {upper}",
            file=sys.stderr,
        )
    if not _TICKER_RE.match(upper):
        print(
            f"Uyari: Ticker bicimi taninmiyor (devam ediliyor): {upper}",
            file=sys.stderr,
        )
    return upper


def split_tickers(value: str) -> list[str]:
    """Virgullu ticker listesini ayirir ve her birini normalize eder."""
    return [normalize_ticker(t) for t in value.split(",") if t.strip()]


def parse_period(period: str) -> str:
    """Period degerini backend'in bekledigi bicime normalizes eder.

    - ``3m`` -> ``3mo``, ``6m`` -> ``6mo``
    - ``1y`` / ``1w`` / ``1d`` oldugu gibi
    - ``3mo`` zaten normalse dokunulmaz
    - Taninmayan deger oldugu gibi gecer (backend karar verir)
    """
    p = period.strip().lower()
    match = _PERIOD_RE.match(p)
    if match:
        number, unit = match.groups()
        unit = "mo" if unit == "m" else unit
        return f"{number}{unit}"
    return p


def extract_rows(data: Any) -> list[dict[str, Any]]:
    """API yanitindan tablo satirlarini (dict listesi) cikarir.

    Yanit bir liste ise dogrudan; bir dict ise bilinen liste anahtarlarini
    arar (``history``, ``data``, ``items``, ``results``, ``bots`` ...).
    Bulunamazsa bos liste doner.
    """
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in (
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
            "preferences",
        ):
            value = data.get(key)
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return [x for x in value if isinstance(x, dict)]
        # Tek kayit: dict'in kendisi tek satir.
        if data:
            return [data]
    return []


def csv_columns(rows: list[dict[str, Any]]) -> list[str]:
    """Satirlardaki anahtarlarin ilk gorulme sirasina gore birlesimi."""
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def write_csv(rows: list[dict[str, Any]], path: str | Path) -> Path:
    """Satirlari CSV dosyasina yazar; dosya yolunu dondurur."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    columns = csv_columns(rows)
    with dest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return dest


def default_download_path(ticker: str, period: str) -> str:
    """``fl download`` varsayilan dosya adi: ``<ticker>-<period>.csv``."""
    safe_period = re.sub(r"[^A-Za-z0-9]", "", period) or "max"
    return f"{ticker}-{safe_period}.csv"
