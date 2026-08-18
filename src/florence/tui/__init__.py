"""florence-tui: ``fl tui`` terminal arayuzu (Textual).

Kapsam: pano (dashboard), izleme listesi (watchlist — favoriler + canli
fiyat + ccharts mini cizgi), portfoy (portfolio — Faz E, P7: secim + ozet +
grafik + performers) ve ticker detay/grafik (detail — 1/3/6/y period +
haberler) ekranlari + polling altyapisi (``data.py``: TTL cache / 429
interval uzatmasi / K4 next_open_at planlama). ``fl tui`` CLI komutu
``cli/commands_tui.py`` icindedir.
"""

from .app import FlorenceTUI, main

__all__ = ["FlorenceTUI", "main"]