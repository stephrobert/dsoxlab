"""``dsoxlab start`` : la séquence, jouée et **montrée** (issue #79).

Pour commencer un lab, il fallait savoir dans quel ordre enchaîner des commandes
dont aucune ne dit qu'elle en suppose une autre : le premier ``run`` d'un lab
``vm`` sur une infrastructure absente échoue, et l'apprenant doit deviner qu'il
lui manquait ``provision``.

Cette commande a pourtant été **révisée avant d'être écrite**, et sa révision
gouverne sa forme. L'argument, tenu dans l'issue :

    Une commande qui enchaîne implicitement contexte, dépendances,
    provisionnement, services, préparation et session rend les échecs plus
    opaques. Quand ``dsoxlab start`` échoue, l'utilisateur doit deviner laquelle
    des six étapes a cassé. C'est précisément le travail que cette milestone
    vient de faire dans l'autre sens.

Et, pour un outil pédagogique : *la séquence est du contenu*. Voir qu'une
infrastructure est provisionnée, puis qu'un lab est préparé, puis qu'une session
s'ouvre, fait partie de ce qu'un apprenant vient apprendre — il devra le faire
sans dsoxlab un jour.

D'où le critère non négociable, écrit dans l'issue :

    ``start`` doit annoncer chaque étape et, en cas d'échec, nommer celle qui a
    cassé et la commande qui la rejoue seule.

Ce module est donc construit à l'envers d'un raccourci. Il n'avale pas la
séquence : il l'**énonce**, étape par étape, avec la commande unitaire de chacune
en regard. Ce qu'il économise, c'est la frappe et l'ordre à connaître — jamais la
compréhension. Un échec nomme son étape, sa commande, et rend le code de sortie
de cette commande, pas un code inventé pour ``start``.

Le verrou, et pourquoi il est pris ici puis rendu
=================================================

``run`` prend le verrou d'écriture lui-même, et le rend **avant** d'ouvrir la
session interactive — sans quoi le ``dsoxlab check`` que l'apprenant y tape
serait refusé par sa propre session. ``start`` ne peut donc pas tenir le verrou
pendant toute sa durée : il le prend pour la seule étape d'infrastructure, le
rend, puis délègue à ``run``. Le tenir plus longtemps ferait sortir ``start`` en
**7** sur son propre verrou, ce qui serait le comble pour une commande dont le
but est de retirer des surprises.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from ..i18n import _
from ..models.lab import LabDefinition
from ..models.runtime import RuntimeType
from ..reporting import console, error, info
from ._commun import (
    LabHomeOption,
    _complete_lab_id,
    _lab,
    _lang,
    _read_repo,
    _root,
    _verrou,
)
from ._socle import app

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Etape:
    """Une étape de la séquence, et la commande qui la rejoue seule.

    ``commande`` n'est pas décorative : c'est elle que le message d'échec donne,
    et c'est elle que l'apprenant apprend en la voyant défiler.
    """

    cle: str
    """Clé i18n du nom de l'étape."""

    commande: str
    """La commande unitaire équivalente, telle qu'on la taperait."""


def _sequence(lab: LabDefinition, section: str | None) -> list[Etape]:
    """Les étapes que ce lab-ci demande, dans l'ordre, et pas une de plus.

    Deux cas à ne pas confondre, et le premier essai de cette commande l'a
    montré :

    - une étape qui **n'existe pas pour ce lab** est absente. Un lab ``shell``
      n'a aucune infrastructure à monter : annoncer « 3/4 · infrastructure —
      sautée » serait du bruit, et fausserait la numérotation de ce que
      l'apprenant a à retenir ;
    - une étape qui **existe mais est déjà faite** reste annoncée, et dit qu'elle
      n'a rien eu à faire. Retirer le contexte parce qu'il était déjà posé faisait
      passer la séquence de 3 à 2 étapes entre deux exécutions du même lab : un
      total qui bouge est déroutant, et il cachait `dsoxlab use`, que l'apprenant
      devra connaître.
    """
    etapes: list[Etape] = []
    if section is not None:
        etapes.append(Etape("start_step_context", f"dsoxlab use {section}"))
    etapes.append(Etape("start_step_deps", "dsoxlab doctor"))
    if lab.runtime.type is not RuntimeType.SHELL:
        etapes.append(Etape("start_step_infra", "dsoxlab provision"))
    etapes.append(Etape("start_step_lab", f"dsoxlab run {lab.id}"))
    return etapes


def _annonce(numero: int, total: int, etape: Etape) -> None:
    """Affiche l'en-tête d'une étape, avec sa commande unitaire en regard."""
    console.print(_(
        "start_step",
        number=numero, total=total,
        name=_(etape.cle), command=etape.commande,
    ))


def _echec(numero: int, total: int, etape: Etape) -> None:
    """Nomme l'étape qui a cassé et la commande qui la rejoue. Le critère #79."""
    error(_("start_step_failed", number=numero, total=total, name=_(etape.cle)))
    info(_("start_step_retry", command=etape.commande))


def _infra_prete(root: Path) -> bool:
    """L'infrastructure a-t-elle déjà des adresses, ou faut-il la monter ?

    C'est ce qui rend ``start`` idempotent : relancé sur un lab déjà prêt, il ne
    reprovisionne pas. On lit le state plutôt que de sonder en SSH — un hôte
    éteint reste provisionné, et c'est ``dsoxlab status`` qui répond à « est-ce
    qu'il répond ? ». Se tromper ici coûterait une minute d'apply inutile.
    """
    from ..infra.inventory import build_inventory, read_terraform_outputs

    repo_meta = _read_repo(root)
    if repo_meta is None or not repo_meta.infra.hosts:
        return True
    try:
        sorties = read_terraform_outputs(repo_meta)
        inventaire = build_inventory(repo_meta, terraform_outputs=sorties)
    except Exception:  # noqa: BLE001 — une infra illisible est une infra à monter
        return False
    # L'inventaire est imbriqué sous `all.children`, comme tout inventaire
    # Ansible : lire `labenv` à la racine rendait un dictionnaire vide, donc
    # « à provisionner » **toujours**. Le défaut n'est apparu qu'à l'essai réel,
    # où la relance a remonté une infrastructure déjà debout — un test qui
    # simule cette fonction ne pouvait pas le voir.
    hotes = (
        inventaire.get("all", {})
        .get("children", {})
        .get("labenv", {})
        .get("hosts", {})
    )
    return bool(hotes)


@app.command("start", help=_("cmd_start_help"))
def start(
    lab_id: Annotated[str | None, typer.Argument(
        help=_("cmd_start_arg"), autocompletion=_complete_lab_id,
    )] = None,
    target: Annotated[str | None, typer.Option(
        "--target", "-t", help=_("opt_run_target"),
    )] = None,
    lab_home: LabHomeOption = None,
) -> None:
    """Enchaîne les étapes d'un lab en les annonçant une par une."""
    from ..config import read_context, write_context
    from ..services.doctor import collect_checks
    from .infrastructure import provisionner
    from .parcours import run

    root = _root(lab_home)
    lang = _lang(root)

    lab = _resoudre_lab(root, lab_id, lang)
    contexte = read_context(root)
    # L'étape existe dès que le lab a une section ; elle n'ÉCRIT que si la section
    # change. `start` relancé sur le même lab affiche donc la même séquence, en
    # disant simplement qu'il n'a rien eu à faire.
    section = lab.section
    a_poser = bool(section) and section != contexte.section

    etapes = _sequence(lab, section)
    total = len(etapes)
    console.print(_("start_plan", lab_id=lab.id, total=total))

    numero = 0
    for etape in etapes:
        numero += 1
        _annonce(numero, total, etape)

        if etape.cle == "start_step_context":
            assert section is not None
            if not a_poser:
                console.print(_("start_context_already", section=section))
                continue
            # `write_context` préserve les autres champs (niveau, langue, lab
            # actif) : `start` pose une section, il ne réinitialise rien.
            write_context(root, section=section, level=None)
            console.print(_("start_context_set", section=section))

        elif etape.cle == "start_step_deps":
            rapport = collect_checks(root, _read_repo(root))
            manquants = rapport.failing()
            if manquants:
                console.print(_(
                    "start_deps_failing",
                    components=", ".join(_(f"check_{c.key}") for c in manquants),
                ))
                _echec(numero, total, etape)
                raise typer.Exit(2)
            console.print(_("start_deps_ok", count=len(rapport.required)))

        elif etape.cle == "start_step_infra":
            if _infra_prete(root):
                console.print(_("start_infra_already"))
                continue
            # Le verrou couvre la seule étape qui écrit le state, et il est rendu
            # avant `run`, qui prend le sien (voir l'en-tête du module).
            verrou = _verrou(root, "start")
            try:
                provisionner(root)
            except typer.Exit as sortie:
                if sortie.exit_code:
                    _echec(numero, total, etape)
                raise
            finally:
                verrou.release()

        else:
            # Dernière étape : `run` prépare, montre la mission et ouvre la
            # session. On le laisse faire son travail entier plutôt que d'en
            # réimplémenter des morceaux : il tient son verrou, ses barres de
            # progression et ses messages, et il reste la commande que
            # l'apprenant rejouera seul.
            try:
                run(lab_id=lab.id, target=target, lab_home=lab_home)
            except typer.Exit as sortie:
                if sortie.exit_code:
                    _echec(numero, total, etape)
                raise


def _resoudre_lab(root: Path, lab_id: str | None, lang: str) -> LabDefinition:
    """Le lab demandé, ou celui que ``next`` suggère, ou une phrase qui explique.

    Accepter l'absence d'argument est le seul raccourci que cette commande
    s'autorise, et il est sans ambiguïté : c'est exactement ce que ``dsoxlab
    next`` propose, calculé par le même service.
    """
    if lab_id:
        try:
            return _lab(root, lab_id, lang)
        except ValueError as exc:
            error(str(exc))
            raise typer.Exit(1) from None

    from ..config import read_context
    from ..discovery.scanner import discover_labs
    from ..services.progress_service import next_pending_lab
    from ..sessions.store import get_best_scores

    contexte = read_context(root)
    if not contexte.section:
        # Même exigence que `next`, et pour la même raison : sans contexte il n'y
        # a pas d'ordre pédagogique, donc rien à suggérer. On ne devine pas.
        error(_("next_no_context"))
        raise typer.Exit(1)

    labs = [
        lab for lab in discover_labs(root, lang=lang)
        if lab.section == contexte.section
        and (not contexte.level or lab.level == contexte.level)
    ]
    scores = get_best_scores(root, [lab.id for lab in labs])
    suggestion = next_pending_lab(labs, scores)
    if suggestion is None:
        error(_("start_no_suggestion"))
        raise typer.Exit(1)
    info(_("start_suggested", lab_id=suggestion.id))
    return suggestion
