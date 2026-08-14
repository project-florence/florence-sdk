"""Dosya yazma sozlesmesi: base64 + ``dest_path`` + traversal korumasi.

``dest_path`` verilen tool'lar (``analysis_download_report``,
``export_download``) dosyayi sunucunun calistigi makineye yazar ve
``{path, size_bytes, md5, format}`` meta JSON'u doner. ``dest_path``
verilmezse binary icerik base64 olarak doner (LLM kucuk dosyalarda icerigi
gorebilir; buyukler icin ``dest_path`` onerilir — mcp-design.md Bölüm 4/5).

Guvenlik: ``dest_path`` yalnizca ``MCP_DOWNLOAD_DIR`` (yoksa calisma dizini)
icinde normalize edilmis bir yola cozulebilir; disari cikan path (path
traversal) ``ToolError`` ile reddedilir.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

from .config import get_download_dir
from .errors import ToolError

__all__ = [
    "base64_payload",
    "resolve_dest_path",
    "write_bytes",
]


def resolve_dest_path(dest_path: str) -> Path:
    """``dest_path``'i guvenli sekilde cozer; ``MCP_DOWNLOAD_DIR`` disina cikamaz.

    - Relative path: ``MCP_DOWNLOAD_DIR`` altina eklenir.
    - Absolute path: ``MCP_DOWNLOAD_DIR`` icinde olmalidir (``..`` / symlink
      normalize edildikten sonra kontrol edilir).
    - Kisit ihlali: ``ToolError`` (path traversal korumasi).
    """
    if not dest_path or dest_path.strip() in ("", "."):
        raise ToolError("dest_path bos olamaz.")
    download_dir = Path(get_download_dir()).expanduser().resolve()
    candidate = Path(dest_path).expanduser()
    if not candidate.is_absolute():
        candidate = download_dir / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(download_dir):
        raise ToolError(
            f"dest_path MCP_DOWNLOAD_DIR disina cikamaz: {dest_path} "
            f"(izin verilen dizin: {download_dir})"
        )
    return resolved


def write_bytes(content: bytes, dest_path: str, fmt: str | None = None) -> dict[str, Any]:
    """Icerigi guvenli yola yazar; meta JSON doner.

    Return: ``{path, size_bytes, md5, format}``.
    """
    path = resolve_dest_path(dest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    meta: dict[str, Any] = {
        "path": str(path),
        "size_bytes": len(content),
        "md5": hashlib.md5(content).hexdigest(),
    }
    if fmt is not None:
        meta["format"] = fmt
    return meta


def base64_payload(content: bytes, fmt: str) -> dict[str, Any]:
    """Binary icerigi base64'e cevirir; meta JSON doner.

    Return: ``{format, encoding: "base64", size_bytes, data}`` — LLM
    ``data`` alanini decode edemiyorsa ``dest_path`` kullanmali (aciklama).
    """
    return {
        "format": fmt,
        "encoding": "base64",
        "size_bytes": len(content),
        "data": base64.b64encode(content).decode("ascii"),
    }
