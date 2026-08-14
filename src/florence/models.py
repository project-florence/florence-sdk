"""Kucuk pydantic model seti.

STANDART CIKTI KURALI: Resource metodlari normalde ham parse edilmis JSON
(dict/list) dondurur — modeller long-tail kullanim icin KOLAYLIK olarak
sunulur, zorunlu degildir. ``extra="allow"`` ile backend'in ekledigi yeni
alanlar modele zarar vermez.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = [
    "BotRecord",
    "CreditBalance",
    "ExportRecord",
    "TokenPair",
    "UserProfile",
]


class _Lenient(BaseModel):
    """Bilinmeyen alanlara toleransli temel model."""

    model_config = ConfigDict(extra="allow")


class TokenPair(_Lenient):
    """POST /auth/login ve POST /auth/refresh yaniti."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserProfile(_Lenient):
    """GET /profile yaniti (backend: username, email, user_type, credits, ...)."""

    username: str
    email: str
    user_type: str = "user"
    created_at: str | None = None
    email_verified: bool = False
    avatar_id: str | None = None
    credits: float | None = None


class CreditBalance(_Lenient):
    """GET /credits yaniti."""

    credits: float


class ExportRecord(_Lenient):
    """GET /data/export/{id} ve /data/export (liste) yanit kaydi."""

    id: int
    year: int
    format: str
    status: str  # queued | processing | ready | sent | error
    created_at: str | None = None
    updated_at: str | None = None
    row_count: int | None = None
    size_bytes: int | None = None
    downloaded_count: int | None = None
    expires_at: str | None = None
    error: str | None = None
    downloadable: bool = False
    download_url: str | None = None


class BotRecord(_Lenient):
    """GET /bots yanitindaki tek bot kaydi."""

    id: int
    username: str
    created_at: str | None = None
    last_login: str | None = None
