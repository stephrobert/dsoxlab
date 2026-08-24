"""Point d'entrée CLI — dsoxlab.

Usage:
    dsoxlab use linux/l1
    dsoxlab list-labs
    dsoxlab show <id>
    dsoxlab run <id>
    dsoxlab check <id>
    dsoxlab reset <id>
    dsoxlab clean <id>
    dsoxlab validate-structure
    dsoxlab doctor
    dsoxlab quit

Convention de ce module : un ``except`` qui a déjà rendu la cause en une phrase
traduite (``error(...)``) sort par ``raise typer.Exit(n) from None``. Le ``from
None`` n'est pas un raccourci, c'est l'affirmation que la cause a été dite à
l'utilisateur, et qu'un chaînage d'exceptions n'ajouterait qu'une trace Python
au-dessus d'un message déjà écrit pour lui. Partout ailleurs, on chaîne.
"""

from __future__ import annotations

import logging
from typing import Any

import typer
from typer.core import TyperGroup, TyperOption

from ..i18n import _
from ..interrupt import (
    Interrupted,
    Stage,
)
from ..reporting import (
    error,
)

logger = logging.getLogger(__name__)


class _I18nGroup(TyperGroup):
    """TyperGroup avec l'option --help traduite."""

    # ``ctx`` est annoté ``Any`` volontairement : typer a fait évoluer le
    # type du Context de get_help_option (click public en 0.25, copie
    # vendorée typer._click en 0.26+). Annoter ``Any`` garde la surcharge
    # valide (LSP) sans coupler le code à un module privé qui n'existe pas
    # dans toutes les versions. Le retour ``TyperOption`` est public et
    # stable.
    def get_help_option(self, ctx: Any) -> TyperOption | None:
        opt = super().get_help_option(ctx)
        if opt is not None:
            opt.help = _("opt_help")
        return opt

    def invoke(self, ctx: Any) -> Any:
        """Traduit un Ctrl-C resté sans propriétaire en interruption nommée.

        C'est le **seul** endroit qui puisse le faire. Typer attrape lui-même
        ``KeyboardInterrupt`` tout en bas de son ``_main()`` et le change en
        ``Exit(130)`` : le code de retour était déjà juste, mais l'interruption
        y perdait toute identité, et un filet posé autour de ``app()`` ne voit
        jamais rien passer. ``invoke`` s'exécute à l'intérieur de ce ``_main()``,
        donc en amont : c'est le dernier moment où l'on peut encore dire à
        l'apprenant ce qui vient d'être interrompu, au lieu de lui rendre son
        invite sans un mot.

        On convertit ici, et **jamais** à la source par un handler de signal :
        ``KeyboardInterrupt`` descend de ``BaseException``, ce qui est
        exactement ce qui lui permet de traverser les ``except Exception`` que
        ce code pose autour des callbacks d'affichage. Une exception ordinaire
        levée depuis un handler s'y ferait avaler en silence, et le flux
        Terraform continuerait comme si de rien n'était.
        """
        try:
            return super().invoke(ctx)
        except KeyboardInterrupt:
            raise Interrupted(Stage.UNKNOWN) from None
        except FileNotFoundError as exc:
            # Un binaire absent remontait jusqu'à l'interpréteur, et une trace
            # Python dit « l'outil est cassé » alors qu'il manque le plus
            # souvent un paquet que l'apprenant peut poser lui-même. Toutes les
            # autres erreurs attendues sont déjà converties en message + code ;
            # celle-ci ne l'était pas, faute d'un endroit qui la voie passer.
            manquant = exc.filename or str(exc)
            # Un nom sans séparateur a été cherché dans le PATH : c'est la
            # définition d'un exécutable introuvable, et 127 est le code que le
            # shell rend dans ce cas. Un chemin, lui, désigne un fichier.
            est_executable = "/" not in str(manquant)
            error(_(
                "err_executable_introuvable" if est_executable
                else "err_fichier_introuvable",
                nom=manquant,
            ))
            raise typer.Exit(127 if est_executable else 2) from None


app = typer.Typer(
    name="dsoxlab",
    help=_("app_help"),
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=True,
    cls=_I18nGroup,
)

# ── Sous-application 'instructor' (commandes formateur) ───────────────────────

instructor_app = typer.Typer(
    name="instructor",
    help=_("cmd_instructor_help"),
    no_args_is_help=True,
    rich_markup_mode="rich",
    cls=_I18nGroup,
)
app.add_typer(instructor_app, name="instructor")

# ── Sous-application 'completion' ─────────────────────────────────────────────

completion_app = typer.Typer(
    name="completion",
    help=_("cmd_completion_help"),
    no_args_is_help=True,
    rich_markup_mode="rich",
    cls=_I18nGroup,
)
app.add_typer(completion_app, name="completion")

# ── Sous-application 'catalog' ────────────────────────────────────────────────

catalog_app = typer.Typer(
    name="catalog",
    help=_("cmd_catalog_help"),
    no_args_is_help=True,
    rich_markup_mode="rich",
    cls=_I18nGroup,
)
app.add_typer(catalog_app, name="catalog")

# ── Sous-application 'infra' ──────────────────────────────────────────────────

infra_app = typer.Typer(
    name="infra",
    help=_("cmd_infra_help"),
    no_args_is_help=True,
    rich_markup_mode="rich",
    cls=_I18nGroup,
)
app.add_typer(infra_app, name="infra")
