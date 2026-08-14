"""Kullanici endpoint'leri: profil, avatar, tercihler, kredi, veri disa aktarim."""

from __future__ import annotations

from typing import Any

from .base import BaseResource

__all__ = ["UserResource"]


class UserResource(BaseResource):
    """GET /profile — profil + kredi bilgisi (JWT).

    Yanit: ``{username, email, user_type, created_at, email_verified, avatar_id, credits}``.
    """

    def profile(self) -> Any:
        return self._request("GET", "/profile")

    """PUT /profile/avatar — avatar guncelle (JWT). Body: ``{avatar_id}``."""

    def update_avatar(self, avatar_id: str) -> Any:
        return self._request("PUT", "/profile/avatar", json={"avatar_id": avatar_id})

    """GET /user/preferences — kullanici tercihleri (JWT, JSONB)."""

    def get_preferences(self) -> Any:
        return self._request("GET", "/user/preferences")

    """PUT /user/preferences — tercihleri guncelle (JWT; PUT mevcut prefs ile birlestirir)."""

    def update_preferences(self, prefs: dict[str, Any]) -> Any:
        return self._request("PUT", "/user/preferences", json={"prefs": prefs})

    """GET /credits — kredi bakiyesi (JWT). Yanit: ``{credits: float}``."""

    def credits(self) -> Any:
        return self._request("GET", "/credits")

    """GET /user/export — kullanicinin tum verisinin JSON dump'i (JWT).

    Yanit: ``{profile, favorites, reports, token_usage, simulations}``.
    """

    def export_data(self) -> Any:
        return self._request("GET", "/user/export")
