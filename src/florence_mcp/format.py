"""Cikti normalizasyonu: JSON/metin formatlama, sifre maskeleme.

MCP sozlesmesi (mcp-design.md Bölüm 5.2):
- JSON tool'lari: ``text`` blogu = pretty JSON (``ensure_ascii=False``,
  ``indent=2``) + ``structuredContent`` = ayni veri. Turkce karakterler
  korunur.
- Metin tool'lari (md/csv/legal): duz metin ``text`` blogu.
- Maskeleme: ``bots_create`` cikisindaki tek seferlik ``password`` alani
  ``"***"`` olarak maskelenir (deger yalnizca token store'a yazilir).
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp.tools import ToolResult
from mcp.types import TextContent

__all__ = [
    "format_json",
    "json_result",
    "mask_bot_password",
    "text_result",
]

#: Maskelenmis bot sifresi gosterimi (gercek deger asla ciktiya girmez).
MASKED_PASSWORD = "***"


def format_json(data: Any) -> str:
    """``ensure_ascii=False, indent=2`` ile pretty JSON metni."""
    return json.dumps(data, ensure_ascii=False, indent=2)


def text_result(text: str) -> ToolResult:
    """Duz metin tool sonucu (md/csv/legal vb.)."""
    return ToolResult(content=[TextContent(type="text", text=text)])


def json_result(data: Any) -> ToolResult:
    """JSON tool sonucu: pretty metin + ayni veri ``structuredContent`` olarak."""
    return ToolResult(
        content=[TextContent(type="text", text=format_json(data))],
        structured_content=data,
    )


def mask_bot_password(data: Any) -> Any:
    """``bots_create`` cikisindaki tek seferlik sifreyi maskeler.

    ``password`` alani (dict veya dict listesi icinde) ``"***"`` yapilir;
    gercek deger yalnizca token store'a yazildigi icin LLM baglamina dusmez.
    """
    if isinstance(data, dict):
        if "password" in data:
            data["password"] = MASKED_PASSWORD
        return {k: mask_bot_password(v) for k, v in data.items()}
    if isinstance(data, list):
        return [mask_bot_password(item) for item in data]
    return data
