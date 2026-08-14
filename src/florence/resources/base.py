"""Resource katmani — her endpoint grubu bir modul, her metod bir endpoint.

STANDART CIKTI KURALI (tum resource'lar icin gecerli):
- Her metod parse edilmis JSON (dict/list) dondurur. Normalizasyon client
  icindeki TEK yardimci fonksiyondan gecer (``client.parse_json_body``):
  bos gövde -> ``None``, JSON -> dict/list, JSON degil -> ham metin.
- Ham dosya/CSV donduren endpoint'ler (``export.download``, ``export_csv``,
  ``download_report``) icin ``raw=True`` kullanilir; bu durumlar docstring'de
  acikca isaretlenir.
- Kucuk pydantic modeller (TokenPair, UserProfile, ...) long-tail icin
  ``florence.models`` altinda mevcuttur; zorunlu degildir.

SENKRON / ASENKRON: Resource metotlari client'in ``request()`` metodunu cagirir.
- Senkron client'ta dogrudan sonuc dondurur.
- Asenkron client'ta bir coroutine dondurur; ``await`` edilir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..config import API_PREFIX

if TYPE_CHECKING:
    from ..client import _BaseClient

__all__ = ["BaseResource"]


class BaseResource:
    """Client ustune kurulan resource tabani.

    ``path`` parametreleri ``/api/v1`` prefix'i OLMADAN verilir; prefix
    burada eklenir (openapi.json path'leri birebir korunur).
    """

    def __init__(self, client: _BaseClient) -> None:
        self._client = client

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
        timeout: Any = None,
        retry: bool = True,
        raw: bool = False,
        absolute: bool = False,
    ) -> Any:
        return self._client.request(
            method,
            path if absolute else f"{API_PREFIX}{path}",
            params=params,
            json=json,
            data=data,
            headers=headers,
            auth=auth,
            timeout=timeout,
            retry=retry,
            raw=raw,
        )
