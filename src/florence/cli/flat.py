"""Duzlestirilmis gruplar icin ozel click grubu (``FlatTyperGroup``).

Sorun: click, alt komutu olan gruplarda ilk pozisyonel token'i HER ZAMAN
alt komut adi olarak yorumlar. ``fl report ASELS`` (generate) ile
``fl report search foo`` (alt komut) ayni grupta birlikte calismaz.

Cozum: parse_args'i ez — ilk non-option token bir alt komutsa normal
alt komut yolu; degilse tum argumanlar grubun callback'ine (pozisyonel
generate/run/price) gider. Tasarim karari 2026-08-14 (analysis duzlestirme
+ ``fl price`` alias'i).
"""

from __future__ import annotations

try:  # typer >= 0.16: click vendored (typer._click)
    import typer._click as click  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover — typer < 0.16: gercek click
    import click  # type: ignore[no-redef]

from typer.main import TyperGroup

__all__ = ["FlatTyperGroup", "make_flat_group"]


class FlatTyperGroup(TyperGroup):
    """Alt komut + pozisyonel callback argumanini birlikte destekleyen grup."""

    allow_interspersed_args = True

    def _find_option_param(self, name: str) -> click.Parameter | None:
        for param in self.params:
            if name in param.opts:
                return param
        return None

    def _split_subcommand(self, args: list[str]) -> int | None:
        """Ilk non-option token'in alt komut olup olmadigina bakar.

        Opsiyon degerlerini (``--purpose x``) atlayarak tarar; ilk gercek
        token bir alt komutsa konumunu, degilse ``None`` dondurur.
        """
        index = 0
        while index < len(args):
            token = args[index]
            if token.startswith("-"):
                if "=" in token:
                    index += 1
                    continue
                param = self._find_option_param(token)
                if param is not None and not param.is_flag and param.nargs != 0:
                    index += 2  # deger alan opsiyon + degeri
                else:
                    index += 1
                continue
            if token in self.commands:
                return index
            return None
        return None

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if not args and self.no_args_is_help and not ctx.resilient_parsing:
            raise click.exceptions.NoArgsIsHelpError(ctx)

        sub_index = self._split_subcommand(args)
        if sub_index is not None:
            # Normal alt komut yolu: grup opsiyonlari + alt komut adi.
            group_options = args[:sub_index]
            sub_args = args[sub_index:]
            click.Command.parse_args(self, ctx, group_options)
            ctx._protected_args, ctx.args = sub_args[:1], sub_args[1:]
            return ctx.args

        # Alt komut yok: tum argumanlar callback'e (pozisyonel + opsiyonlar).
        rest = click.Command.parse_args(self, ctx, args)
        ctx._protected_args = []
        ctx.args = list(rest or [])
        return ctx.args


def make_flat_group(typer_app: click.Command) -> FlatTyperGroup:
    """Typer'in urettigi click komutunu ``FlatTyperGroup``'a cevirir."""
    typer_app.__class__ = FlatTyperGroup
    return typer_app
