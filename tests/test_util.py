"""CLI util birim testleri: period normalizasyonu + fiyat geçmişi limit doğrulaması.

TAMAMEN OFFLINE: saf fonksiyonlar (HTTP isteği yok).
Kapsam: ``parse_period``, ``_period_days``, ``INTERVAL_MAX_DAYS`` sabiti ve
``validate_history_request`` sınır değerleri — backend'deki
``src/services/price.py: _MAX_PERIOD_FOR_INTERVAL`` değerleriyle birebir.
"""

from __future__ import annotations

import pytest
import typer

from florence.cli.util import (
    INTERVAL_MAX_DAYS,
    _period_days,
    parse_period,
    validate_history_request,
)


# ----------------------------------------------------------------------
# INTERVAL_MAX_DAYS — backend src/services/price.py ile senkron kalmalı
# ----------------------------------------------------------------------
def test_interval_max_days_matches_backend() -> None:
    """Backend ``_MAX_PERIOD_FOR_INTERVAL`` ile birebir (kaynak: price.py:149)."""
    assert INTERVAL_MAX_DAYS == {
        "1m": 7,
        "5m": 60,
        "15m": 60,
        "30m": 60,
        "1h": 730,
        "1d": 3650,
        "5d": 3650,
        "1wk": 3650,
        "1mo": 3650,
        "3mo": 3650,
    }


# ----------------------------------------------------------------------
# _period_days — period -> gün hesabı
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("period", "expected"),
    [
        ("1d", 1),
        ("60d", 60),
        ("61d", 61),
        ("1w", 7),
        ("1mo", 30),
        ("3mo", 90),
        ("1y", 365),
        ("2y", 730),
        ("10y", 3650),
        ("ytd", 366),  # üst sınır yaklaşımı (backend dinamik hesaplar, ondan küçük)
        ("max", 3650),
    ],
)
def test_period_days(period: str, expected: int) -> None:
    assert _period_days(period) == expected


@pytest.mark.parametrize("period", ["", "1", "abc", "3q", "1.5y", "mo"])
def test_period_days_unknown_returns_none(period: str) -> None:
    """Tanınmayan format limit kontrolüne tabi tutulmaz (backend karar verir)."""
    assert _period_days(period) is None


# ----------------------------------------------------------------------
# validate_history_request — sınır değerler (tam sınır geçerli, +1 gün hatalı)
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("period", "interval"),
    [
        ("7d", "1m"),  # 1m: 7 gün
        ("60d", "5m"),  # 5m: 60 gün (tam sınır)
        ("60d", "15m"),  # 15m: 60 gün
        ("60d", "30m"),  # 30m: 60 gün
        ("730d", "1h"),  # 1h: 730 gün
        ("3650d", "1d"),  # 1d: 3650 gün
        ("3650d", "5d"),
        ("3650d", "1wk"),
        ("3650d", "1mo"),
        ("3650d", "3mo"),
        ("10y", "1d"),  # 10y = 3650 gün (tam sınır)
        ("3mo", "1d"),  # 90 <= 3650
        ("ytd", "1h"),  # ytd <= 730
        ("max", "1d"),  # max = 3650 (tam sınır)
    ],
)
def test_validate_history_request_accepts_exact_boundary(period: str, interval: str) -> None:
    """Tam sınır (ve altı) geçerlidir; normalize edilmiş period döner."""
    assert validate_history_request(period, interval) == parse_period(period)


@pytest.mark.parametrize(
    ("period", "interval"),
    [
        ("8d", "1m"),  # 1m: 8 > 7
        ("61d", "5m"),  # 5m: 61 > 60
        ("61d", "15m"),
        ("61d", "30m"),
        ("3mo", "5m"),  # 3mo = 90 > 60 (eski default artık geçersiz)
        ("731d", "1h"),  # 1h: 731 > 730
        ("3651d", "1d"),  # 1d: 3651 > 3650
        ("ytd", "5m"),  # ytd ~ 366 > 60
        ("max", "5m"),  # max = 3650 > 60
    ],
)
def test_validate_history_request_rejects_over_limit(period: str, interval: str) -> None:
    with pytest.raises(typer.BadParameter):
        validate_history_request(period, interval)


def test_validate_history_request_rejects_just_over_boundary() -> None:
    """Sınır eşitliği geçerli, +1 gün hatalı (60 vs 61 gün, 5m)."""
    assert validate_history_request("60d", "5m") == "60d"
    with pytest.raises(typer.BadParameter):
        validate_history_request("61d", "5m")
    assert validate_history_request("730d", "1h") == "730d"
    with pytest.raises(typer.BadParameter):
        validate_history_request("731d", "1h")
    assert validate_history_request("3650d", "1d") == "3650d"
    with pytest.raises(typer.BadParameter):
        validate_history_request("3651d", "1d")


# ----------------------------------------------------------------------
# validate_history_request — normalizasyon ve hata biçimi
# ----------------------------------------------------------------------
def test_validate_history_request_normalizes_short_units() -> None:
    """3m -> 3mo, 1m -> 1mo, 1y/1d olduğu gibi döner."""
    assert validate_history_request("3m", "1d") == "3mo"  # 90 <= 3650
    assert validate_history_request("1m", "5m") == "1mo"  # 30 <= 60
    assert validate_history_request("1y", "1d") == "1y"
    assert validate_history_request("1d", "5m") == "1d"


def test_validate_history_request_interval_case_insensitive() -> None:
    """'5M' / '1H' büyük harf kabul edilir (lowercase normalize)."""
    assert validate_history_request("60d", "5M") == "60d"
    assert validate_history_request("730d", "1H") == "730d"


def test_validate_history_request_invalid_interval_raises() -> None:
    """Bilinmeyen aralık net Türkçe hata verir (backend 400'ü beklenmez)."""
    with pytest.raises(typer.BadParameter) as exc:
        validate_history_request("1mo", "7m")
    msg = str(exc.value)
    assert "Geçersiz aralık" in msg
    assert "1m, 5m, 15m, 30m, 1h, 1d, 5d, 1wk, 1mo, 3mo" in msg


def test_validate_history_request_over_limit_message() -> None:
    """Limit aşımı hatası hangi aralığın kaç gün desteklediğini söyler."""
    with pytest.raises(typer.BadParameter) as exc:
        validate_history_request("3mo", "5m")
    msg = str(exc.value)
    assert "60 gün" in msg
    assert "3mo = 90 gün" in msg


def test_validate_history_request_unknown_period_passes_through() -> None:
    """Tanınmayan period formatı limit kontrolüne takılmadan geçer (backend karar verir)."""
    assert validate_history_request("xyz", "5m") == "xyz"
    assert validate_history_request("3x", "1d") == "3x"