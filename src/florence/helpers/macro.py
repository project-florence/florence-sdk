"""H6 — ``macro_briefing``: makro manzara (helpers-design.md Bolum 2.6).

Veri kaynaklari: ``economy.currency`` + ``gold_prices`` + ``macroeconomy``
= 3 backend cagrisi (tamamı JWT — economy allowlist'te degil).

Backend degerleri string + Turk virgullu olabilir (``"40,25"``,
``"1.234,56"``) — helper float'a normalize eder. Seri yoksa ilgili alan
``{}`` (hata DEGIL); kimlik yoksa ``AuthError`` (exit 1).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..errors import AuthError, FlorenceError
from ._util import _norm_number, _num, now_iso
from .models import MacroBriefing

if TYPE_CHECKING:  # pragma: no cover
    from ..client import AsyncFlorenceClient, FlorenceClient

__all__ = ["macro_briefing", "macro_briefing_async"]

def _safe[T](fn: Callable[[], T]) -> T:
    """Alan ureticisini korur: AuthError yeniden firlatilir, digerleri ``{}``."""
    try:
        return fn()
    except AuthError:
        raise
    except FlorenceError:
        return {}  # type: ignore[return-value]


def _to_econ_float(value: Any) -> float | None:
    """Ekonomi degerini float'a cevirir: ``"42.5"``, ``"42,5"``, ``"1.234,56"``."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        number = _num(value)  # duz ondalik ve "42,5" -> 42.5
        if number is not None:
            return number
        normalized = _norm_number(value)  # "1.234,56" -> 1234.56
        return normalized if isinstance(normalized, (int, float)) else None
    return None


def _first_econ_float(value: Any) -> float | None:
    """Tek deger veya ``{buying: ...}`` gibi nested dict'ten sayi cikarir."""
    if isinstance(value, dict):
        for key in ("buying", "selling", "value", "price", "rate"):
            if key in value:
                number = _to_econ_float(value[key])
                if number is not None:
                    return number
        for nested in value.values():
            number = _first_econ_float(nested)
            if number is not None:
                return number
        return None
    return _to_econ_float(value)


def _currency(client: Any, symbols: str | None) -> dict[str, float]:
    data = client.economy.currency(symbols=symbols)
    out: dict[str, float] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            number = _first_econ_float(value)
            if number is not None:
                out[key] = number
    return out


def _gold(client: Any) -> dict[str, float]:
    data = client.economy.gold_prices()
    out: dict[str, float] = {}
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            key = item.get("Type") or item.get("type") or item.get("name") or item.get("symbol")
            if not key:
                continue
            value = item.get("Buying") or item.get("buying") or item.get("Selling") or item.get("selling")
            number = _to_econ_float(value)
            if number is not None:
                out[key] = number
    elif isinstance(data, dict):
        for key, value in data.items():
            number = _to_econ_float(value)
            if number is not None:
                out[key] = number
    return out


def _macro(client: Any, macro_series: str | None) -> dict[str, float]:
    data = client.economy.macroeconomy()
    out: dict[str, float] = {}
    if isinstance(data, dict):
        if isinstance(data.get("series"), list):
            for item in data["series"]:
                if not isinstance(item, dict):
                    continue
                key = item.get("id") or item.get("code") or item.get("symbol") or item.get("name")
                if not key:
                    continue
                number = _to_econ_float(item.get("value") or item.get("latest") or item.get("current"))
                if number is not None:
                    out[key] = number
        else:
            for key, value in data.items():
                number = _to_econ_float(value)
                if number is not None:
                    out[key] = number
    if macro_series:
        wanted = {symbol.strip().upper() for symbol in macro_series.split(",") if symbol.strip()}
        if wanted:
            out = {key: value for key, value in out.items() if key.upper() in wanted}
    return out


def macro_briefing(
    client: FlorenceClient,
    symbols: str = "USD,EUR,GBP",
    macro_series: str | None = None,
) -> MacroBriefing:
    """Makro manzarayi tek pakette ozetler: doviz + altin + FRED serileri."""
    currency = _safe(lambda: _currency(client, symbols))
    gold = _safe(lambda: _gold(client))
    macro = _safe(lambda: _macro(client, macro_series))
    return MacroBriefing(currency=currency, gold=gold, macro=macro, generated_at=now_iso())


async def macro_briefing_async(
    client: AsyncFlorenceClient,
    symbols: str = "USD,EUR,GBP",
    macro_series: str | None = None,
) -> MacroBriefing:
    """``macro_briefing``'in asenkron ikizi."""
    currency = _safe(lambda: _currency(client, symbols))
    gold = _safe(lambda: _gold(client))
    macro = _safe(lambda: _macro(client, macro_series))
    return MacroBriefing(currency=currency, gold=gold, macro=macro, generated_at=now_iso())
