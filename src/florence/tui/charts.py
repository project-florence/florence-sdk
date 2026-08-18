"""ccharts adapter katmani (tasarim v2, Faz A — T-A2).

Ekranlar/DataHub bu module dokunur; ccharts import'u YALNIZCA burada
(Y2 karari: render stratejisi degisirse ekranlar etkilenmez). Veri akisi:
``[{ts, open, high, low, close}, ...]`` -> ``ohlc_rows()`` -> JSON string ->
``ccharts.Chart`` -> ``line()``/``candle()`` -> ANSI string.

Sorumluluklar:
- ``ohlc_rows``: price_history satirlarindan ccharts JSON uretir. Eksik
  ``close`` (None) kayitlari atilir (backend ara tatil gunu bos birakir);
  ``high``/``low`` yoksa ve ``fill_hl`` ise sentez (P2):
  ``high=max(open, close)``, ``low=min(open, close)`` (gunluk mum; guncel
  high/low yoksa bilinen yaklasim — 'yaklasik mum'). ``ts`` yoksa epoch'a
  cevrilmez, ISO dize korunur -> ``show_times`` dogru basar. ccharts null
  deger kabul etmedigi icin hicbir alan ``null`` uretilmez (sayi yoksa
  sentezlenir ya da alan yazilmaz).
- ``render_line``/``render_candle``: ``Chart(payload).line()/.candle()``
  cagrisi; bos/hata durumunda ``''`` doner (ekran 'veri yok' gosterir).
- ``single_row``: DataTable hucresi icin ciktiyi tek satira indirir.
- ``theme_ansi``: ``'$success'`` gibi Textual tema degiskenini 24-bit ANSI
  escape'e cevirir (P4) — dark/light temada otomatik uyum.
- ``period_colors``: TR BIST tek renk kurali — donem getirisine gore
  (rise, fall) ANSI cifti (``single_color=True`` ile birlikte kullanilir;
  mevcut ``sparkline_color`` davranisi).

P3: ccharts render'i saf C (~µs–ms) — bu moduldeki fonksiyonlar senkron
cagrilir; ``asyncio.to_thread`` GEREKMEZ (olcum testi: 500 kayit + 60x14
grafik 50ms altinda).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ccharts import Chart

__all__ = [
    "ohlc_rows",
    "period_colors",
    "period_return",
    "render_candle",
    "render_line",
    "single_row",
    "theme_ansi",
]


def _to_float(value: Any) -> float | None:
    """Sayi degerini float'a cevirir; bool/None/gecersiz -> ``None``."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ohlc_rows(rows: Any, *, fill_hl: bool = True) -> str:
    """price_history satirlarindan ccharts JSON stringi uretir.

    - Eksik ``close`` (None) kayitlar atilir (backend ara tatil gunu bos
      birakir); ``close`` olmayan satirlar gecersizdir.
    - ``high``/``low`` yoksa ve ``fill_hl`` ise sentez (P2):
      ``high=max(open, close)``, ``low=min(open, close)`` — docstring'de
      'yaklasik mum' notu (guncel high/low verisi yoksa bilinen yaklasim).
    - Gercek ``high``/``low`` varsa birebir korunur (P2 tercihi).
    - ``ts`` sayisal degilse ISO dize korunur -> ``show_times`` dogru basar.
    - ccharts null deger iceren JSON'i reddeder: sayi yoksa ya sentezlenir
      (``fill_hl``) ya da alan yazilmaz — ``null`` asla uretilmez.
    - Bos girdi -> ``"[]"`` (ekran 'veri yok' gosterir; render bos doner).
    """
    out: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping):
            continue
        close = _to_float(row.get("close"))
        if close is None:
            continue
        open_ = _to_float(row.get("open"))
        high = _to_float(row.get("high"))
        low = _to_float(row.get("low"))
        entry: dict[str, Any] = {}
        ts = row.get("ts")
        if ts is not None:
            entry["ts"] = ts
        if fill_hl:
            high = high if high is not None else (max(open_, close) if open_ is not None else close)
            low = low if low is not None else (min(open_, close) if open_ is not None else close)
            entry["high"] = high
            entry["low"] = low
        else:
            if high is not None:
                entry["high"] = high
            if low is not None:
                entry["low"] = low
        entry["open"] = open_ if open_ is not None else close
        entry["close"] = close
        out.append(entry)
    return json.dumps(out, ensure_ascii=False)


def period_return(values: Any) -> float | None:
    """Donem getirisi: (son - ilk) close; yetersiz veride ``None``.

    ``sparkline.py``'deki ayni adli yardimcinin adapter karsiligi (Y3):
    widget'lar/ekranlar buradan kullanir; eski kopya Faz B'de tasinir.
    """
    cleaned = [float(v) for v in values if v is not None]
    if len(cleaned) < 2:
        return None
    return cleaned[-1] - cleaned[0]


def _render(kind: str, payload: str, width: int, height: int, **kwargs: Any) -> str:
    """``Chart(payload).line()`` veya ``.candle()`` -> ANSI string.

    Bos payload (``"[]"``), gecersiz JSON veya gecersiz boyutlarda ``''``
    doner — ekran 'veri yok' gosterir (karar: hata delege edilmez, yutulur).
    """
    try:
        chart = Chart(payload)
        method = chart.candle if kind == "candle" else chart.line
        return method(width=width, height=height, **kwargs)
    except (TypeError, ValueError):
        return ""


def render_line(
    payload: str,
    width: int,
    height: int,
    *,
    rise: str | None = None,
    fall: str | None = None,
    single_color: bool = False,
    show_prices: bool = False,
    show_times: bool = False,
) -> str:
    """``Chart(payload).line(...)`` -> ANSI string; bos/hata durumunda ``''``.

    ``rise``/``fall`` 24-bit ANSI escape stringleri alir (``theme_ansi``
    uretir); ``None`` ise ccharts kendi defaultunu (yesil/kirmizi) kullanir.
    ``single_color=True`` ile tek renk (donem getirisine gore,
    ``period_colors`` ile); ``show_prices`` sol marjda max/min fiyat,
    ``show_times`` alt satirda ilk/son tarih basar.
    """
    return _render(
        "line",
        payload,
        width,
        height,
        rise_color=rise,
        fall_color=fall,
        single_color=single_color,
        show_prices=show_prices,
        show_times=show_times,
    )


def render_candle(
    payload: str,
    width: int,
    height: int,
    *,
    rise: str | None = None,
    fall: str | None = None,
    single_color: bool = False,
    show_prices: bool = False,
    show_times: bool = False,
) -> str:
    """``Chart(payload).candle(...)`` -> ANSI string; bos/hata durumunda ``''``.

    ``width >= kayit sayisi`` iken her mum bir kac hucre genisliginde ve
    aralikli cizilir; dar alanda komsu mumlar birlestirilir (ccharts C).
    Wick karakteri ``│``, govde ``▀/▄/█`` bloklaridir.
    """
    return _render(
        "candle",
        payload,
        width,
        height,
        rise_color=rise,
        fall_color=fall,
        single_color=single_color,
        show_prices=show_prices,
        show_times=show_times,
    )


def single_row(out: str) -> str:
    """DataTable hucresi icin: ciktiyi tek satira indirir (``\\n``'ler atilir).

    ccharts ciktisi her zaman ``\\n`` ile biter; mini grafik (height=1) tek
    satir uretir. Cok satirli buyuk cikti hucreye girerse bos satirlar
    atilir ve kalan satirlar birlesir — hucre tek satir olur. ANSI dizileri
    degismez — hucrede renk korunur. Bos girdi -> ``''``.
    """
    if not out:
        return ""
    return "".join(line for line in out.splitlines() if line.strip())


def theme_ansi(color_var: str | None, theme: dict[str, str] | None) -> str | None:
    """``'$success'`` gibi tema degiskenini 24-bit ANSI escape'e cevirir (P4).

    ``theme`` = ``app.theme_variables`` (ör. ``{"success": "#1a8a5c"}``).
    Bilinmeyen degisken, gecersiz hex veya bos tema -> ``None`` (ccharts
    kendi defaultunu kullanir — fallback). ``$`` ile baslamayan girdiler de
    ``None`` doner (sadece tema degiskeni kabul edilir).
    """
    if not isinstance(theme, dict) or not isinstance(color_var, str):
        return None
    if not color_var.startswith("$"):
        return None
    hex_color = theme.get(color_var[1:])
    if not isinstance(hex_color, str):
        return None
    hex_value = hex_color.lstrip("#")
    if len(hex_value) != 6:
        return None
    try:
        r, g, b = (int(hex_value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None
    return f"\x1b[38;2;{r};{g};{b}m"


def period_colors(
    return_value: float | None, theme: dict[str, str] | None
) -> tuple[str | None, str | None]:
    """TR BIST tek renk kurali: donem getirisine gore (rise, fall) ANSI cifti.

    Yukari: ``rise=theme['success']``, ``fall=None``; asagi:
    ``rise=None``, ``fall=theme['error']``; sifir/None: ``(None, None)``
    (ccharts kendi rengini kullanir). ``single_color=True`` ile birlikte
    kullanilir — mevcut ``sparkline_color`` davranisi (tasarim §5.3).
    """
    if return_value is None or return_value == 0:
        return (None, None)
    if return_value > 0:
        return (theme_ansi("$success", theme), None)
    return (None, theme_ansi("$error", theme))