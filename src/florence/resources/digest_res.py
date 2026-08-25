"""Piyasa bulteni (market digest) endpoint'leri: /digest.

Backend /api/v1/digest ucu:
- date + slot -> o gune ve slota ait bulten (morning, noon, evening)
- date -> o gunun tum bultenleri listesi
- at -> verilen tarihteki slot araligini kapsayan bulten (ISO8601)
- parametresiz -> en guncel (current) bulten
"""

from __future__ import annotations

from typing import Any

from .base import BaseResource

__all__ = ["DigestResource"]


class DigestResource(BaseResource):
    """GET /digest — piyasa bulteni (morning, noon, evening)."""

    def get(
        self,
        date: str | None = None,
        slot: str | None = None,
        at: str | None = None,
    ) -> Any:
        """Piyasa bultenini ceker.

        Parametre yoksa en guncel bulten doner.
        ``date``: 'YYYY-MM-DD'
        ``slot``: 'morning' | 'noon' | 'evening' (date gerektirir)
        ``at``: ISO8601 tarih-saat
        """
        params: dict[str, Any] = {}
        if date is not None:
            params["date"] = date
        if slot is not None:
            params["slot"] = slot
        if at is not None:
            params["at"] = at
        return self._request("GET", "/digest", params=params or None)

    def current(self) -> Any:
        """En guncel piyasa bultenini ceker."""
        return self.get()

    def by_date_slot(self, date: str, slot: str) -> Any:
        """Belirli bir gun ve slota ait bulteni ceker."""
        return self.get(date=date, slot=slot)

    def by_date(self, date: str) -> Any:
        """Belirli bir gunun tum bultenlerini ceker."""
        return self.get(date=date)
