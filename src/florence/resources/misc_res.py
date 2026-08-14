"""Hafif (misc) endpoint'ler: ipos, legal, about, version, contact, contributors,
maintenance, health.

KAPSAM DISI (bilincli olarak sarilmadi — TODO):
- ``/analytics/event`` (fire-and-forget izleme)
- ``/announcements`` yazma islemleri (create/update/delete/read) — okuma
  uclari (``announcements()``, ``announcement()``) dahildir
- ``/meta/avatars`` (statik varlik listesi)
- ``/data/daily/{year}`` (410 Gone — deprecated)
- Admin uygulamasi (ayri FastAPI app, X-Admin-Token)
"""

from __future__ import annotations

from typing import Any

from .base import BaseResource

__all__ = ["MiscResource"]


class MiscResource(BaseResource):
    # ------------------------------------------------------------------
    # IPOs
    # ------------------------------------------------------------------
    """GET /ipos/upcoming — yaklasan halka arzlar (public; ``?after=`` ISO)."""

    def ipos_upcoming(self, after: str | None = None) -> Any:
        return self._request("GET", "/ipos/upcoming", params=self._after(after), auth=False)

    """GET /ipos/draft — taslak halka arzlar (public)."""

    def ipos_draft(self, after: str | None = None) -> Any:
        return self._request("GET", "/ipos/draft", params=self._after(after), auth=False)

    """GET /ipos/active — aktif halka arzlar (public)."""

    def ipos_active(self, after: str | None = None) -> Any:
        return self._request("GET", "/ipos/active", params=self._after(after), auth=False)

    """GET /ipos/{slug} — halka arz detayi (public; yoksa 404)."""

    def ipo_detail(self, slug: str) -> Any:
        return self._request("GET", f"/ipos/{slug}", auth=False)

    @staticmethod
    def _after(after: str | None) -> dict[str, str]:
        return {"after": after} if after else {}

    # ------------------------------------------------------------------
    # Legal / statik
    # ------------------------------------------------------------------
    """GET /legal — tek politika metni (public).

    ``policy``: terms|privacy_policy|cookie_policy|disclaimer; ``lang``: tr|en.
    """

    def legal(self, policy: str, lang: str = "tr") -> Any:
        return self._request(
            "GET",
            "/legal",
            params={"policy": policy, "lang": lang},
            auth=False,
        )

    """GET /legal/all — tum politikalar (public)."""

    def legal_all(self, lang: str = "tr") -> Any:
        return self._request("GET", "/legal/all", params={"lang": lang}, auth=False)

    """GET /about — platform hakkindaki metin (public)."""

    def about(self, lang: str = "tr") -> Any:
        return self._request("GET", "/about", params={"lang": lang}, auth=False)

    """GET /version — surum bilgisi (public)."""

    def version(self) -> Any:
        return self._request("GET", "/version", auth=False)

    """GET /contact — iletisim bilgileri (public)."""

    def contact(self) -> Any:
        return self._request("GET", "/contact", auth=False)

    """GET /contributors — katkida bulunanlar (public)."""

    def contributors(self) -> Any:
        return self._request("GET", "/contributors", auth=False)

    """GET /maintenance — devre disi ozellik listesi (public)."""

    def maintenance(self) -> Any:
        return self._request("GET", "/maintenance", auth=False)

    """GET /health — saglik kontrolu (public; ``{"status": "ok"}``).

    Kok seviye (prefix'siz) endpoint: ``absolute=True``.
    """

    def health(self) -> Any:
        return self._request("GET", "/health", auth=False, absolute=True)

    """GET / — kok endpoint (public; ``{}``). Kok seviye (prefix'siz)."""

    def root(self) -> Any:
        return self._request("GET", "/", auth=False, absolute=True)

    # ------------------------------------------------------------------
    # Okuma tarafi announcements (yazma islemleri KAPSAM DISI)
    # ------------------------------------------------------------------
    """GET /announcements — son 7 gunun duyurulari (JWT)."""

    def announcements(self) -> Any:
        return self._request("GET", "/announcements")

    """GET /announcements/{announcement_id} — tek duyuru (JWT)."""

    def announcement(self, announcement_id: int) -> Any:
        return self._request("GET", f"/announcements/{announcement_id}")

    # TODO: Kapsam disi birakilan uclar:
    #  - POST /analytics/event (izleme)
    #  - POST/PUT/DELETE /announcements... + POST /announcements/read (yazma)
    #  - GET /meta/avatars (statik)
    #  - GET /data/daily/{year} (410 Gone)
    #  - Admin app (X-Admin-Token, ayri FastAPI uygulamasi)
