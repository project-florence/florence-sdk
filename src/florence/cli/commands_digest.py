"""``fl digest`` — Günlük piyasa bülteni komutları.

Backend ``GET /api/v1/digest``:
- Parametresiz: en güncel bülten
- ``--date YYYY-MM-DD`` + ``--slot morning|noon|evening``: belirli slot bülteni
- ``--date YYYY-MM-DD``: o günün tüm bültenleri
- ``--json``: makine-okunur çıktı
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .context import CliState
from .options import json_opt, verbose_opt
from .output import emit_json, render_data

__all__ = ["digest_app", "digest_impl"]

digest_app = typer.Typer(
    help="Piyasa bülteni (fl digest / fl digest --slot morning).",
    invoke_without_command=True,
    no_args_is_help=False,
)

console = Console()

SLOT_LABELS = {
    "morning": "Sabah Bülteni (09:30)",
    "noon": "Öğle Bülteni (13:00)",
    "evening": "Kapanış Bülteni (18:30)",
}


def _state(ctx: typer.Context) -> CliState:
    return ctx.obj


def render_single_digest(digest: dict[str, Any]) -> None:
    """Tek bülteni Rich paneli olarak çizer."""
    date_str = str(digest.get("date", ""))
    slot = str(digest.get("slot", ""))
    slot_label = SLOT_LABELS.get(slot, slot.capitalize() if slot else "Güncel")
    content = digest.get("content", "")
    sections = digest.get("sections", [])

    body_elements = []
    if content:
        body_elements.append(content.strip())

    if isinstance(sections, list) and sections:
        for sec in sections:
            if isinstance(sec, dict):
                heading = sec.get("heading", "")
                body = sec.get("body", "")
                if heading and body:
                    body_elements.append(f"\n### {heading}\n{body}")

    full_md = "\n\n".join(body_elements)
    panel_title = (
        f"[bold cyan]✦ Florence Bülten[/bold cyan] · "
        f"[yellow]{date_str}[/yellow] · [magenta]{slot_label}[/magenta]"
    )
    console.print(Panel(Markdown(full_md), title=panel_title, border_style="blue"))


@digest_app.callback(invoke_without_command=True)
def digest_impl(
    ctx: typer.Context,
    date: str | None = typer.Option(
        None, "--date", "-d", help="Bülten tarihi (YYYY-MM-DD)."
    ),
    slot: str | None = typer.Option(
        None,
        "--slot",
        "-s",
        help="Bülten slotu (morning | noon | evening).",
    ),
    at: str | None = typer.Option(
        None, "--at", help="ISO8601 tarih-saat filtresi."
    ),
    json_output: bool = json_opt(),
    verbose: bool = verbose_opt(),
) -> None:
    """Piyasa bültenini görüntüler (varsayılan: en güncel bülten)."""
    state = _state(ctx)
    state.apply_flags(json_output, verbose)
    client = state.client()

    data = client.digest.get(date=date, slot=slot, at=at)

    if state.effective_json():
        emit_json(data)
        return

    if isinstance(data, list):
        if not data:
            console.print("[dim]Belirtilen tarihe ait bülten bulunamadı.[/dim]")
            return
        for d in data:
            if isinstance(d, dict):
                render_single_digest(d)
    elif isinstance(data, dict):
        render_single_digest(data)
    else:
        render_data(data)
