"""Auth endpoint'leri (kayit, dogrulama, hesap yonetimi).

Not: Login/refresh/logout token DURUMU ``AuthManager`` tarafindan yonetilir
(``client.auth.*``). Bu modul ayni endpoint'leri durumsuz (stateless) olarak
sunar — ornek: ``client.auth_res.refresh(refresh_token)`` sadece endpoint'i
cagirir, token store'a yazmaz.

Tum endpoint path'leri openapi.json'dan birebir alinmistir.
"""

from __future__ import annotations

from typing import Any

from .base import BaseResource

__all__ = ["AuthResource"]


class AuthResource(BaseResource):
    """POST /auth/register — yeni kullanici kaydi (public).

    Body: ``{username, email, password}`` (password min 10 karakter).
    Yanit: ``{message, user_id, verification_sent}``.
    """

    def register(self, username: str, email: str, password: str) -> Any:
        return self._request(
            "POST",
            "/auth/register",
            json={"username": username, "email": email, "password": password},
            auth=False,
        )

    """POST /auth/resend-verification — dogrulama mailini yeniden gonder (public)."""

    def resend_verification(self, username_or_email: str) -> Any:
        return self._request(
            "POST",
            "/auth/resend-verification",
            json={"username_or_email": username_or_email},
            auth=False,
        )

    """POST /auth/refresh — refresh token rotasyonu (public; token body'de).

    Body: ``{"refresh_token": "..."}`` (opsiyonel; cookie fallback backend'de).
    Yanit: ``{access_token, refresh_token, token_type}``. Durumsuz cagridir;
    token durumu guncellenmez.
    """

    def refresh(self, refresh_token: str | None = None) -> Any:
        return self._request(
            "POST",
            "/auth/refresh",
            json={"refresh_token": refresh_token},
            auth=False,
        )

    """POST /auth/logout — refresh token'i iptal et (public)."""

    def logout(self, refresh_token: str | None = None) -> Any:
        return self._request(
            "POST",
            "/auth/logout",
            json={"refresh_token": refresh_token},
            auth=False,
        )

    """GET /auth/verify-email — e-posta dogrulama (public, ``?token=``)."""

    def verify_email(self, token: str) -> Any:
        return self._request(
            "GET",
            "/auth/verify-email",
            params={"token": token},
            auth=False,
        )

    """DELETE /auth/delete — hesabi kalici sil (JWT)."""

    def delete(self) -> Any:
        return self._request("DELETE", "/auth/delete")

    """PUT /auth/change-password — sifre degistir (JWT; tum refresh token'lar iptal)."""

    def change_password(self, current_password: str, new_password: str) -> Any:
        return self._request(
            "PUT",
            "/auth/change-password",
            json={"current_password": current_password, "new_password": new_password},
        )

    """PUT /auth/change-email — e-posta degistir (JWT)."""

    def change_email(self, new_email: str, current_password: str) -> Any:
        return self._request(
            "PUT",
            "/auth/change-email",
            json={"new_email": new_email, "current_password": current_password},
        )

    """PUT /auth/change-username — kullanici adi degistir (JWT)."""

    def change_username(self, new_username: str, current_password: str) -> Any:
        return self._request(
            "PUT",
            "/auth/change-username",
            json={"new_username": new_username, "current_password": current_password},
        )
