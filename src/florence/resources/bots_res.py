"""Bot hesaplari: olustur, listele, sil + bot oturumu yardimcisi.

Bot sifresi yalnizca ``POST /bots`` yanitinda TEK SEFERLIK doner; SDK onu
token store'a (keyring) kaydeder ve asla loglamaz. Botlar owner'in
kredisinden harcar.
"""

from __future__ import annotations

from typing import Any

from .base import BaseResource

__all__ = ["BotsResource"]


class BotsResource(BaseResource):
    """POST /bots — bot olustur (JWT; max 5 bot/kullanici).

    Yanit: ``{id, username, email, password}`` — ``password`` tek seferliktir;
    ``client.auth`` sifreyi otomatik keyring'e kaydeder (``create_bot`` kisa
    yolunu kullanirseniz).
    """

    def create(self, username: str, password: str | None = None) -> Any:
        return self._request(
            "POST",
            "/bots",
            json={"username": username, "password": password},
        )

    """GET /bots — kendi botlarini listele (JWT). Yanit: ``{bots: [...]}``."""

    def list(self) -> Any:
        return self._request("GET", "/bots")

    """DELETE /bots/{bot_id} — botu sil (JWT; owner-only)."""

    def delete(self, bot_id: int) -> Any:
        return self._request("DELETE", f"/bots/{bot_id}")

    def bot_session(self, username: str, password: str | None = None) -> Any:
        """Bot olarak login ol, is bitince logout et (context manager).

        Senkron: ``with client.bots.bot_session("bot-1"): ...``
        Asenkron: ``async with client.bots.bot_session("bot-1"): ...``

        ``password`` verilmezse keyring'de saklanan sifre kullanilir.
        """
        return self._client.auth.bot_session(username, password)
