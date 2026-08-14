"""Florence CLI paketi (``florence`` / ``fl`` entry point'leri).

Komut agaci: ``fl <grup> <komut> [arg] [opsiyonlar]`` — gruplar: auth,
account, market, economy, portfolio, analysis, bots, export, misc, config.
Tam tasarim: ``docs/cli-design.md``.

typer >= 0.16 uyumlulugu: typer 0.16+ click'i kendi icinde tasir
(``typer._click``) ve ``typer.UsageError``'u kamu API'sinden kaldirir.
CLI modulleri ``typer.UsageError`` desenini kullanir; geri uyumlu alias
paket ici TEK YERDE tanimlanir (typer < 0.16'da no-op).
"""

from __future__ import annotations

import typer

if not hasattr(typer, "UsageError"):  # typer >= 0.16
    try:
        from typer._click.exceptions import UsageError  # type: ignore[attr-defined]
    except ImportError:  # pragma: no cover — typer < 0.16 (gercek click)
        from click.exceptions import UsageError  # type: ignore[no-redef]

    typer.UsageError = UsageError  # type: ignore[attr-defined]
