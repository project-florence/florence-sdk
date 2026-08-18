"""ccharts adapter birim testleri (tasarim v2, Faz A — T-A2).

Strateji (plan §Test Stratejisi 2): ccharts ZORUNLU dep oldugundan adapter
testleri GERCEK ccharts ile kosar (mock yok). ImportError olursa test HATA
verir (= fail loud; sessiz fallback yok).

Kapsam (plan T-A2):
- ``ohlc_rows``: her turlu girisle JSON uretir; ``high``/``low`` yokken
  sentez (P2); ``close=None`` kayitlar atilir; bos liste -> ``"[]"``.
- ``render_line``/``render_candle``: gercek ccharts ile — cikti ``\\n``
  icerir ve bos degildir; ``show_prices`` -> min/max fiyat metni;
  ``show_times`` -> ilk tarih metni. Bos/hata durumunda ``''`` doner.
- ``single_row``: cok satirli ciktiyi tek satira indirir; ANSI korunur.
- ``theme_ansi``: tema hex'i -> 24-bit ANSI escape (P4); bilinmeyen
  degisken/bos tema -> ``None`` (fallback ccharts default).
- ``period_colors``: donem getirisine gore (rise, fall) ANSI cifti.
- P3: senkron render olcumu — 500 kayit + 60x14 grafik 50ms altinda.
"""

from __future__ import annotations

import json
import time

import pytest

from florence.tui import charts

#: MOCK_HISTORY benzeri 3 kayit (high/low YOK -> sentez yolu, P2).
MOCK_ROWS = [
    {"ts": "2026-07-01T00:00:00+00:00", "open": 300.0, "close": 310.0, "volume": 1000},
    {"ts": "2026-07-02T00:00:00+00:00", "open": 310.0, "close": 313.4, "volume": 1200},
    {"ts": "2026-07-03T00:00:00+00:00", "open": 313.4, "close": 312.0, "volume": 900},
]

#: Tam OHLC'li kayitlar (mum grafigi wick testi icin — high/low gercek).
MOCK_OHLC_ROWS = [
    {"ts": "2026-07-01T00:00:00+00:00", "open": 100.0, "high": 200.0, "low": 50.0, "close": 150.0},
    {"ts": "2026-07-02T00:00:00+00:00", "open": 150.0, "high": 160.0, "low": 40.0, "close": 60.0},
]


# ----------------------------------------------------------------------
# ohlc_rows
# ----------------------------------------------------------------------
def test_ohlc_rows_produces_parseable_json():
    payload = charts.ohlc_rows(MOCK_ROWS)
    data = json.loads(payload)  # gercek ccharts da ayni sekilde parse eder
    assert len(data) == 3
    # ts ISO dize olarak KORUNUR (epoch'a cevrilmez — show_times dogru basar).
    assert data[0]["ts"] == "2026-07-01T00:00:00+00:00"
    # Sentez (P2): high=max(open, close), low=min(open, close)
    assert data[0]["high"] == pytest.approx(310.0)
    assert data[0]["low"] == pytest.approx(300.0)
    assert data[1]["high"] == pytest.approx(313.4)
    assert data[1]["low"] == pytest.approx(310.0)
    # open/close korunur
    assert data[2]["open"] == pytest.approx(313.4)
    assert data[2]["close"] == pytest.approx(312.0)


def test_ohlc_rows_keeps_real_high_low_when_present():
    payload = charts.ohlc_rows(MOCK_OHLC_ROWS)
    data = json.loads(payload)
    assert data[0]["high"] == pytest.approx(200.0)
    assert data[0]["low"] == pytest.approx(50.0)
    # Sentez devreye girmez (gercek deger var).
    assert data[0]["high"] != pytest.approx(150.0)


def test_ohlc_rows_drops_none_close_records():
    rows = [dict(MOCK_ROWS[0]), {"ts": "2026-07-02T00:00:00+00:00", "open": 310.0, "close": None}, dict(MOCK_ROWS[2])]
    data = json.loads(charts.ohlc_rows(rows))
    assert len(data) == 2
    assert data[0]["close"] == pytest.approx(310.0)
    assert data[1]["close"] == pytest.approx(312.0)


def test_ohlc_rows_empty_list_returns_empty_json():
    assert charts.ohlc_rows([]) == "[]"
    assert charts.ohlc_rows([{"ts": "x", "close": None}]) == "[]"
    # Non-dict satirlar atilir.
    assert charts.ohlc_rows([None, "x", 42]) == "[]"
    # close'suz kayit atilir.
    assert charts.ohlc_rows([{"ts": "x", "open": 1.0}]) == "[]"


def test_ohlc_rows_fill_hl_false_keeps_only_present_hl():
    rows = [{"ts": 1, "open": 10.0, "high": 15.0, "close": 12.0}]
    data = json.loads(charts.ohlc_rows(rows, fill_hl=False))
    # Yalnizca gercek high gider; low yoksa alan yazilmaz (ccharts toleransli).
    assert "high" in data[0]
    assert data[0]["high"] == pytest.approx(15.0)
    assert "low" not in data[0]


def test_ohlc_rows_close_only_row_synthesizes_from_close():
    # open yok -> sentez high=low=close (ccharts en az close ister).
    rows = [{"ts": 1, "close": 12.0}]
    data = json.loads(charts.ohlc_rows(rows))
    assert data[0]["open"] == pytest.approx(12.0)
    assert data[0]["high"] == pytest.approx(12.0)
    assert data[0]["low"] == pytest.approx(12.0)


def test_ohlc_rows_never_emits_null_values():
    """ccharts null deger iceren JSON'i reddeder — adapter null uretmemeli."""
    rows = [{"ts": 1, "open": None, "high": None, "low": None, "close": 12.0}]
    payload = charts.ohlc_rows(rows)
    assert "null" not in payload
    # Gercek ccharts bu payload'i parse edebilmeli.
    from ccharts import Chart

    Chart(payload)  # ValueError firlatmamali


# ----------------------------------------------------------------------
# render_line / render_candle (gercek ccharts — zorunlu dep)
# ----------------------------------------------------------------------
def test_render_line_produces_ansi_multiline_output():
    payload = charts.ohlc_rows(MOCK_ROWS)
    out = charts.render_line(payload, width=30, height=6)
    assert out
    assert "\n" in out
    # Renklendirilmis blok karakterler cikar (ccharts line cikisi).
    assert any(ch in out for ch in "▁▂▃▄▅▆▇█")
    assert "\x1b[" in out


def test_render_line_show_prices_and_times():
    payload = charts.ohlc_rows(MOCK_ROWS)
    out = charts.render_line(
        payload, width=30, height=6, show_prices=True, show_times=True
    )
    # show_prices: ccharts C tarafi noktali ondalik basar (TR format yok — not).
    assert "313.40" in out
    assert "310.00" in out
    # show_times: ilk/son ISO tarihi (UTC) basar.
    assert "2026-07-01" in out
    assert "2026-07-03" in out


def test_render_line_single_color_with_rise_falls():
    # Rise/fall ANSI'leri 24-bit; single_color'da ccharts SON MUMUN yonune
    # gore tek renk secer: yukselis serisinde rise, dusus serisinde fall.
    payload = charts.ohlc_rows(MOCK_ROWS)  # 310 -> 313.4 -> 312: son mum inis
    green = "\x1b[38;2;26;138;92m"
    red = "\x1b[38;2;220;50;47m"
    # Son mum inis -> fall kullanilir (period_colors asagi yolu).
    out = charts.render_line(payload, width=20, height=4, single_color=True, rise=None, fall=red)
    assert red in out
    assert green not in out
    # Monoton yukselis serisi (watchlist deseni: open = onceki close):
    # son mum yukselis -> rise kullanilir (period_colors yukari yolu).
    up_rows = [
        {"ts": 1, "open": 310.0, "close": 310.0},
        {"ts": 2, "open": 310.0, "close": 313.4},
        {"ts": 3, "open": 313.4, "close": 314.0},
    ]
    up = charts.render_line(
        charts.ohlc_rows(up_rows), width=20, height=4, single_color=True, rise=green, fall=None
    )
    assert green in up
    # Cikti bos degil ve yeni satirlar iceriyor.
    assert up.strip()
    assert "\n" in up


def test_render_line_empty_payload_returns_empty_string():
    assert charts.render_line("[]", width=30, height=6) == ""
    # Gecersiz JSON da ayni sekilde yutulur (ekran 'veri yok' gosterir).
    assert charts.render_line("{{{", width=30, height=6) == ""


def test_render_candle_produces_wick_characters():
    payload = charts.ohlc_rows(MOCK_OHLC_ROWS)
    out = charts.render_candle(payload, width=30, height=8)
    assert out
    assert "\n" in out
    # Mum govdesi/fitil karakterleri cikar (wick: │).
    assert "│" in out


def test_render_candle_empty_payload_returns_empty_string():
    assert charts.render_candle("[]", width=30, height=8) == ""


# ----------------------------------------------------------------------
# single_row
# ----------------------------------------------------------------------
def test_single_row_collapses_to_one_line_and_keeps_ansi():
    payload = charts.ohlc_rows(MOCK_ROWS)
    out = charts.render_line(payload, width=30, height=6)
    row = charts.single_row(out)
    assert "\n" not in row
    assert row  # bos degil
    # ANSI dizileri korunur (renkli tek satir — DataTable hucresi).
    assert "\x1b[" in row


def test_single_row_empty_input():
    assert charts.single_row("") == ""


# ----------------------------------------------------------------------
# theme_ansi (P4 kofrusu)
# ----------------------------------------------------------------------
def test_theme_ansi_hex_to_24bit_escape():
    theme = {"success": "#1a8a5c"}
    assert charts.theme_ansi("$success", theme) == "\x1b[38;2;26;138;92m"


def test_theme_ansi_unknown_variable_returns_none():
    assert charts.theme_ansi("$nope", {"success": "#1a8a5c"}) is None
    assert charts.theme_ansi("$success", {}) is None
    assert charts.theme_ansi("$success", None) is None


def test_theme_ansi_rejects_malformed_hex():
    assert charts.theme_ansi("$success", {"success": "not-a-color"}) is None
    assert charts.theme_ansi("$success", {"success": "#12345"}) is None  # 5 hane


# ----------------------------------------------------------------------
# period_colors (TR BIST tek renk kurali)
# ----------------------------------------------------------------------
def test_period_colors_positive_return_uses_success():
    theme = {"success": "#1a8a5c", "error": "#dc322f"}
    rise, fall = charts.period_colors(2.0, theme)
    assert rise == "\x1b[38;2;26;138;92m"
    assert fall is None
    rise, fall = charts.period_colors(0.5, {})
    assert rise is None  # tema yoksa fallback ccharts default
    assert fall is None


def test_period_colors_negative_return_uses_error():
    theme = {"success": "#1a8a5c", "error": "#dc322f"}
    rise, fall = charts.period_colors(-1.0, theme)
    assert rise is None
    assert fall == "\x1b[38;2;220;50;47m"


def test_period_colors_flat_or_missing_is_neutral():
    theme = {"success": "#1a8a5c", "error": "#dc322f"}
    assert charts.period_colors(0.0, theme) == (None, None)
    assert charts.period_colors(None, theme) == (None, None)


# ----------------------------------------------------------------------
# P3: senkron render olcumu (to_thread GEREKMEZ)
# ----------------------------------------------------------------------
def test_sync_render_under_50ms_for_large_dataset():
    """500 kayit + 60x14 grafik: render dogrudan (mesaj handler'inda) cagrilabilir."""
    rows = [
        {"ts": f"2026-07-{i % 28 + 1:02d}T00:00:00+00:00", "open": 100.0 + i, "close": 101.0 + i}
        for i in range(500)
    ]
    payload = charts.ohlc_rows(rows)
    started = time.perf_counter()
    out = charts.render_line(
        payload, width=60, height=14, show_prices=True, show_times=True
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    assert out
    assert elapsed_ms < 50.0, f"renders {elapsed_ms:.2f}ms > 50ms"