"""Yardimci tool (helper) katmani ortak yardimcilari: ticker, sayi, zaman, satir.

Bu modul ic kullanim icindir (isim on ekli dosyalar gibi); public yuzey
``florence/helpers/__init__.py``'dir.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

__all__ = ["_as_rows", "_num", "_norm_number", "now_iso", "upper_ticker"]

#: Turk virgullu ondalik kaliplari: "40,25", "1.234,56", "%0,42", "-0,5"
_TR_THOUSANDS = re.compile(r"^[%+\-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?%?$")
_TR_PLAIN = re.compile(r"^[%+\-]?\d+(?:,\d+)?%?$")


def upper_ticker(ticker: str) -> str:
    """Ticker'i buyuk harfe cevirir ve bosluklari temizler (helper duzeyi)."""
    return (ticker or "").strip().upper()


def now_iso() -> str:
    """UTC zaman damgasi (ISO 8601, saniye hassasiyeti)."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _num(value: Any) -> float | None:
    """Sayisal degeri float'a cevirir; cevrilemezse ``None`` (toleransli)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text.replace(",", "."))
        except ValueError:
            return None
    return None


def _norm_number(value: Any) -> Any:
    """Turk virgullu ondalik string'i float'a cevirir; uymuyorsa aynen doner.

    Ornek: ``"1.234,56"`` -> ``1234.56``, ``"%0,42"`` -> ``0.42``.
    Yalnizca virgullu ondalik normalize edilir (duz ondalik icin ``_num``).
    """
    if isinstance(value, str):
        text = value.strip()
        if _TR_THOUSANDS.match(text) or _TR_PLAIN.match(text):
            if "," in text:
                negative = text.startswith("-")
                cleaned = text.lstrip("+-").rstrip("%").replace(".", "").replace(",", ".")
                try:
                    number = float(cleaned)
                except ValueError:
                    return value
                return -number if negative else number
    return value


def _as_rows(data: Any) -> list[dict[str, Any]]:
    """API yanitindan dict satirlari cikarir (liste veya bilinen liste anahtarlari)."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("items", "data", "results", "history", "rows", "series"):
            value = data.get(key)
            if isinstance(value, list):
                rows = [x for x in value if isinstance(x, dict)]
                if rows:
                    return rows
    return []
