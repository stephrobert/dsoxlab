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
from typing import Annotated

import typer

from ..i18n import _, get_lang
from ..reporting import (
    error,
    info,
    machine,
    success,
)
from ._socle import catalog_app

logger = logging.getLogger(__name__)



# ── catalog ───────────────────────────────────────────────────────────────────

@catalog_app.command("list", help=_("cmd_catalog_list_help"))
def catalog_list(
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    """Les catalogues connus, et ceux qui sont installés."""
    from ..reporting.console import print_catalogues
    from ..services.catalog import installes, lire_manifeste

    connus = lire_manifeste()
    poses = installes()

    if as_json:
        machine.emit({
            "schema": 1,
            "known": [
                {"id": c.id, "repository": c.depot,
                 "description": c.description(get_lang())}
                for c in connus
            ],
            "installed": [
                {"id": p.id, "path": str(p.racine),
                 "active": p.actif, "repository": p.depot}
                for p in poses
            ],
        })
        return

    print_catalogues(connus, poses, get_lang())


@catalog_app.command("add", help=_("cmd_catalog_add_help"))
def catalog_add(
    reference: Annotated[str, typer.Argument(help=_("arg_catalog_reference"))],
    force: Annotated[
        bool, typer.Option("--force", help=_("opt_catalog_force"))
    ] = False,
) -> None:
    """Installe un catalogue et le rend actif."""
    from ..services.catalog import CatalogueError, ajouter, resoudre

    try:
        identifiant, url = resoudre(reference)
        info(_("catalog_installation", name=identifiant, url=url))
        pose = ajouter(reference, force=force)
    except CatalogueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    success(_("catalog_installe", name=pose.id, path=str(pose.racine)))
    _dire_les_collections_a_installer(pose.racine)
    info(_("catalog_installe_suite"))


def _dire_les_collections_a_installer(racine: Path) -> None:
    """Les collections que ce catalogue exige, si elles manquent.

    C'est ici que le trou se refermait mal (kubernetes-dsoxlab-training#94) :
    le catalogue déclarait ses collections ET documentait leur installation
    dans son README, mais `catalog add` clone sous `~/.local/share/`, où
    personne ne lit ce README. Deux utilisateurs ont donc perdu six jours sur
    un lab qui échouait faute d'une commande qu'un fichier qu'ils ne verraient
    jamais leur demandait de taper.

    L'avis est posé juste après le clone, parce que c'est le moment où l'on
    acquiert le besoin. Il ne lève pas : un catalogue s'installe aussi pour
    lire ses labs, et `doctor` redira la même chose avant de les jouer.
    """
    from ..services.collections_ansible import geste_d_installation, mesurer

    besoins = mesurer(racine)
    if not besoins.manquantes:
        return
    info(_("catalog_collections_manquantes", names=", ".join(besoins.manquantes)))
    info(_(
        "catalog_collections_geste",
        command=" ".join(geste_d_installation(besoins)),
    ))


@catalog_app.command("update", help=_("cmd_catalog_update_help"))
def catalog_update(
    identifiant: Annotated[
        str | None, typer.Argument(help=_("arg_catalog_id"))
    ] = None,
) -> None:
    """Met à jour un catalogue, ou tous ceux qui sont installés."""
    from ..services.catalog import CatalogueError, installes, mettre_a_jour

    cibles = [identifiant] if identifiant else [p.id for p in installes()]
    if not cibles:
        info(_("catalog_aucun_installe"))
        return

    echecs = 0
    for cible in cibles:
        try:
            detail = mettre_a_jour(cible)
        except CatalogueError as exc:
            error(str(exc))
            echecs += 1
            continue
        # git dit « Already up to date. » quand il n'a rien fait : le répéter
        # tel quel obligerait à lire de l'anglais dans une session française.
        if "up to date" in detail.lower() or not detail:
            info(_("catalog_a_jour", name=cible))
        else:
            success(_("catalog_mis_a_jour", name=cible, detail=detail))

    # Une mise à jour ratée parmi plusieurs doit se voir dans le code de
    # retour : un script qui enchaîne ne lit pas l'écran.
    if echecs:
        raise typer.Exit(1)


@catalog_app.command("remove", help=_("cmd_catalog_remove_help"))
def catalog_remove(
    identifiant: Annotated[str, typer.Argument(help=_("arg_catalog_id"))],
) -> None:
    """Retire un catalogue installé."""
    from ..services.catalog import CatalogueError, retirer

    try:
        racine = retirer(identifiant)
    except CatalogueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    success(_("catalog_retire", name=identifiant, path=str(racine)))


@catalog_app.command("use", help=_("cmd_catalog_use_help"))
def catalog_use(
    identifiant: Annotated[str, typer.Argument(help=_("arg_catalog_id"))],
) -> None:
    """Choisit le catalogue actif."""
    from ..services.catalog import CatalogueError, definir_actif

    try:
        racine = definir_actif(identifiant)
    except CatalogueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    success(_("catalog_actif_defini", name=identifiant, path=str(racine)))


# ── support ───────────────────────────────────────────────────────────────────
