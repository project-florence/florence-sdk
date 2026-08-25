"""BÜLTEN ekranı (DigestScreen) — Günlük AI piyasa bülteni okuyucusu.

Sabah (09:30), Öğle (13:00) ve Akşam (18:30) slotlarındaki piyasa özetlerini gösterir.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from rich.markdown import Markdown
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import ContentSwitcher, Static

from ..data import DigestSnapshot, status_bar_text
from ..widgets.nav import AppHeader

__all__ = ["DigestDataFailed", "DigestDataUpdated", "DigestScreen"]


class DigestDataUpdated(Message):
    def __init__(self, snapshot: DigestSnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot


class DigestDataFailed(Message):
    def __init__(self, error: str, retry_after: float | None = None) -> None:
        super().__init__()
        self.error = error
        self.retry_after = retry_after


class DigestScreen(Screen[None]):
    """Piyasa Bülteni (Market Digest) tam ekran görüntüleyici."""

    DEFAULT_CSS = """
    DigestScreen {
        background: $surface;
    }
    #digest-status {
        padding: 0 1;
        text-style: bold;
        background: $panel;
    }
    #digest-container {
        height: 1fr;
        padding: 1 2;
    }
    #digest-content {
        padding: 1 2;
        background: $surface;
        border: round $primary 40%;
    }
    #banner {
        display: none;
        padding: 0 1;
        background: $error 25%;
        color: $text;
    }
    #banner.visible {
        display: block;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._last_snapshot: DigestSnapshot | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="digest-root"):
            yield AppHeader(active="digest")
            yield Static("Piyasa durumu yükleniyor…", id="digest-status")
            yield Static("", id="banner")
            with ContentSwitcher(id="digest-switcher", initial="digest-loading"):
                yield Static("Bülten yükleniyor…", id="digest-loading")
                yield Static("Giriş yapın: fl auth login", id="digest-auth")
                yield Static("Henüz bülten bulunmuyor", id="digest-empty")
                with ScrollableContainer(id="digest-container"):
                    yield Static("", id="digest-content")

    def on_mount(self) -> None:
        poll_now = getattr(self.app, "poll_now", None)
        if callable(poll_now):
            poll_now()

    def on_digest_data_updated(self, message: DigestDataUpdated) -> None:
        self._last_snapshot = message.snapshot
        snap = message.snapshot
        self._render_status(snap.market_status, snap.fetched_at)
        self._render_digest(snap)

    def on_digest_data_failed(self, message: DigestDataFailed) -> None:
        banner = self.query_one("#banner", Static)
        if message.retry_after is not None:
            text = f"Rate limit — {message.retry_after:.0f}s sonra tekrar deneniyor"
        else:
            text = message.error
        banner.update(text)
        banner.add_class("visible")

    def _render_status(self, status: dict[str, Any] | None, fetched_at: datetime) -> None:
        bar = self.query_one("#digest-status", Static)
        bar.update(status_bar_text(status, fetched_at))

    def _render_digest(self, snap: DigestSnapshot) -> None:
        switcher = self.query_one("#digest-switcher", ContentSwitcher)
        if "digest" in snap.auth_sections:
            switcher.current = "digest-auth"
            return
        if snap.current_digest is None:
            switcher.current = "digest-loading"
            return
        if not snap.current_digest:
            switcher.current = "digest-empty"
            return

        d = snap.current_digest
        title = d.get("title", "Piyasa Bülteni")
        date_str = str(d.get("date", ""))
        slot = str(d.get("slot", ""))
        slot_map = {"morning": "Sabah (09:30)", "noon": "Öğle (13:00)", "evening": "Akşam Kapanış (18:30)"}
        slot_text = slot_map.get(slot, slot.capitalize() if slot else "")

        elements = [f"# {title}", f"**Tarih:** {date_str}  │  **Slot:** {slot_text}\n"]
        content = d.get("content", "")
        if content:
            elements.append(content.strip())

        sections = d.get("sections", [])
        if isinstance(sections, list):
            for s in sections:
                if isinstance(s, dict):
                    h = s.get("heading", "")
                    b = s.get("body", "")
                    if h and b:
                        elements.append(f"\n## {h}\n{b}")

        full_md = "\n\n".join(elements)
        content_widget = self.query_one("#digest-content", Static)
        content_widget.update(Markdown(full_md))
        switcher.current = "digest-container"
