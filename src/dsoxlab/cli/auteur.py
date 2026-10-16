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
from pathlib import Path
from typing import Annotated, Any

import typer

from ..exit_codes import ExitCode
from ..i18n import _
from ..reporting import (
    error,
    info,
    machine,
    print_validation,
    success,
)
from ..services.validation_service import RapportValidation
from ._commun import (
    LabHomeOption,
    _root,
)
from ._socle import app, new_app

logger = logging.getLogger(__name__)



@app.command("validate-structure", help=_("cmd_validate_help"))
def validate_structure_cmd(
    lab_home: LabHomeOption = None,
    check_urls: Annotated[bool, typer.Option(
        "--check-urls", help=_("opt_check_urls"),
    )] = False,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    """Confronte le catalogue au contrat, et rend le même verdict aux deux sorties.

    Cette fonction portait 280 lignes, une complexité cyclomatique de 53 et une
    cognitive de 65 : elle enchaînait onze familles de contrôles, tenait le
    document machine au fil de l'eau, et répétait sept fois le même patron de
    trois instructions. Les contrôles vivent désormais dans
    ``services.validation_service``, derrière une table ; il ne reste ici que
    le choix de la sortie.

    Les deux sorties lisent le **même** rapport, ce qui supprime le risque
    qu'elles divergent : l'ancienne version les construisait en parallèle, et
    rien n'empêchait l'une de signaler une anomalie que l'autre taisait.
    """
    from ..discovery.scanner import discover_labs
    from ..services.validation_service import TABLE, valider

    root = _root(lab_home)
    labs = discover_labs(root)
    rapport = valider(root, labs, verifier_urls=check_urls)

    if as_json:
        machine.emit(_document(rapport))
        if not rapport.ok:
            raise typer.Exit(ExitCode.ECHEC)
        return

    print_validation(rapport, TABLE, root)
    if rapport.ok:
        success(_("all_labs_valid"))
    else:
        error(_("labs_have_issues"))
        raise typer.Exit(ExitCode.ECHEC)


def _document(rapport: RapportValidation) -> dict[str, Any]:
    """Le document machine, dont la forme est un contrat joué en CI.

    Aucun champ ne bouge : ``doc_urls_checked`` dit si les guides ont été
    regardés, sans quoi un appelant ne pourrait pas distinguer « aucune URL
    morte » de « les URL n'ont pas été vérifiées » ; et
    ``doc_urls_unreachable`` reste séparé de ``issues``, parce qu'un guide
    injoignable n'est pas un défaut du lab.
    """
    return {
        "ok": rapport.ok,
        "labs_checked": rapport.labs_examines,
        "doc_urls_checked": rapport.urls_examinees,
        "doc_urls_unreachable": [
            {"lab": a.lab, "url": a.params.get("url"), "key": a.cle}
            for a in rapport.urls_injoignables
        ],
        "issues": [
            machine.issue_dict(
                a.famille, a.cle, a.params, lab=a.lab, path=a.chemin, field=a.champ
            )
            for a in rapport.anomalies
        ],
        "counts": rapport.comptes(),
    }


# ── doctor ────────────────────────────────────────────────────────────────────


# ── new : créer un squelette conforme au contrat ──────────────────────────────

@new_app.command("catalog", help=_("cmd_new_catalog_help"))
def new_catalog(
    identifiant: Annotated[str, typer.Argument(help=_("arg_new_id"))],
    dans: Annotated[
        Path | None, typer.Option("--in", help=_("opt_new_dans"))
    ] = None,
) -> None:
    """Crée un catalogue vide mais conforme."""
    from ..services.scaffold import ScaffoldError, creer_catalogue

    try:
        creation = creer_catalogue(identifiant, dans or Path.cwd())
    except ScaffoldError as exc:
        error(str(exc))
        raise typer.Exit(1) from None
    except OSError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    success(_("scaffold_catalogue_cree", name=identifiant, path=str(creation.racine)))
    info(_("scaffold_catalogue_suite", path=str(creation.racine)))


@new_app.command("lab", help=_("cmd_new_lab_help"))
def new_lab(
    identifiant: Annotated[str, typer.Argument(help=_("arg_new_id"))],
    runtime: Annotated[
        str, typer.Option("--runtime", help=_("opt_new_runtime"))
    ] = "shell",
    lab_home: LabHomeOption = None,
) -> None:
    """Crée un lab conforme, découvert dès le prochain `list-labs`."""
    from ..services.scaffold import ScaffoldError, creer_lab

    root = _root(lab_home)
    try:
        creation = creer_lab(identifiant, root, runtime=runtime)
    except ScaffoldError as exc:
        error(str(exc))
        raise typer.Exit(1) from None
    except OSError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    success(_("scaffold_lab_cree", name=identifiant,
              path=str(creation.racine), runtime=runtime))
    info(_("scaffold_lab_suite"))
