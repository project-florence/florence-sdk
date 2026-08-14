"""Client ve store kurulumu: config/env onceligi, token store secimi (T3.2c).

Oncelik sirasi (yuksekten dusuge):
1. ``FLORENCE_API_URL`` env > config ``api_url`` > SDK default.
2. ``FLORENCE_TOKEN`` env (salt-okunur override; AuthManager halleder).
3. ``FLORENCE_KEYRING=0`` -> ``FileTokenStore``; aksi halde
   ``KeyringTokenStore`` (fallback'i de ``FileTokenStore`` — T3.2b).
4. ``--json`` bayragi > config ``default_output`` > varsayilan ``table``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ..auth import KeyringTokenStore, TokenStore
from ..client import FlorenceClient
from ..config import KEYRING_SERVICE
from ..store import FileTokenStore
from .config_cli import CliConfig

__all__ = ["CliState", "build_store"]


def build_store() -> TokenStore:
    """Ortama uygun token store'u kurar (keyring / FileTokenStore)."""
    if os.environ.get("FLORENCE_KEYRING") == "0":
        return FileTokenStore()
    return KeyringTokenStore(KEYRING_SERVICE)


@dataclass
class CliState:
    """Komut basina tasinan durum: bayraklar, config, client ve store."""

    json_output: bool = False
    verbose: bool = False
    config: CliConfig | None = None
    _store: TokenStore | None = field(default=None, init=False, repr=False)
    _client: FlorenceClient | None = field(default=None, init=False, repr=False)

    def apply_flags(self, json_output: bool = False, verbose: bool = False) -> None:
        """Grup callback'i ve komut bayraklarini birlestirir (OR)."""
        self.json_output = self.json_output or json_output
        self.verbose = self.verbose or verbose

    def effective_json(self) -> bool:
        """Etkin JSON modu: ``--json`` bayragi > config ``default_output``."""
        if self.json_output:
            return True
        return bool(self.config is not None and self.config.default_output == "json")

    def store(self) -> TokenStore:
        if self._store is None:
            self._store = build_store()
        return self._store

    def client(self) -> FlorenceClient:
        """Istek basina bir client kurar (store ile paylasilir)."""
        if self._client is None:
            base_url: str | None = None
            if self.config is not None and self.config.api_url:
                # Env her zaman config'ten once gelir; SDK env'i zaten okur.
                base_url = os.environ.get("FLORENCE_API_URL") or self.config.api_url
            self._client = FlorenceClient(base_url=base_url, token_store=self.store())
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


def state_value(state: CliState | None, key: str, default: Any = None) -> Any:
    """Config degerini guvenle okur (state/config yoksa default)."""
    if state is None or state.config is None:
        return default
    return state.config.get(key) if state.config.get(key) is not None else default
