"""florence-tui: ``fl tui`` terminal arayuzu (Textual).

PART 1 kapsami: pano (dashboard) ekrani + polling altyapisi
(``data.py``: TTL cache / 429 interval uzatmasi / K4 next_open_at planlama).

PART 2 (ayri subagent): watchlist + detay ekranlari ve ``fl tui`` CLI
komutu — bu paketin disinda (``cli/``) eklenir.
"""

from .app import FlorenceTUI, main

__all__ = ["FlorenceTUI", "main"]
