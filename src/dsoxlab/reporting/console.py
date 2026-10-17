"""Rendu terminal avec Rich : tableaux, panneaux, statuts."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.errors import MarkupError
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from ..i18n import _
from ..models.course import CourseManifest, CourseSection
from ..models.lab import LabDefinition
from ..models.runtime import RuntimeType
from ..security.terminal import neutraliser, texte_affichable
from ..security.urls import URLRefusee, url_sure
from ..services.audit_pedagogique import RapportPedagogique
from ..services.catalog import CatalogueConnu, CatalogueInstalle
from ..services.doctor import (
    STATE_CHOICE_REQUIRED,
    STATE_UNKNOWN,
    Check,
    DoctorReport,
)
from ..services.infra_state_service import EtatHote, EtatInfra
from ..services.lab_service import EchecDeTest
from ..services.lab_state import LabState
from ..services.progress_service import build_progress, exam_verdict
from ..services.validation_service import Anomalie, Famille, RapportValidation
from ..validators.structure import StructureReport


class ConsoleSure(Console):
    """Une console où un balisage illisible ne fait pas échouer la commande.

    Le filet, pas la protection : les valeurs du contrat s'échappent au point où
    on les rend (``security/terminal.py``). Mais l'échappement est un geste qu'on
    oublie, et l'oubli coûtait cher — mesuré avant correction, un titre de lab
    valant ``Titre [red]x[/red] et [/] non apparié`` faisait sortir ``list-labs``
    et ``show`` en ``MarkupError``, c'est-à-dire en trace Python. Un catalogue
    tiers rendait le catalogue entier inaffichable avec un caractère.

    Alors on rejoue le rendu sans analyser le balisage : le panneau s'affiche
    littéralement, les balises voulues comprises. C'est moins joli, et c'est
    lisible — un affichage dégradé vaut mieux qu'une commande de lecture qui
    échoue sur la donnée qu'elle devait montrer.
    """

    def print(self, *objects: Any, **kwargs: Any) -> None:
        try:
            super().print(*objects, **kwargs)
        except MarkupError:
            # `markup=False` ne suffit pas : il ne gouverne que les chaînes
            # passées ici, pas le contenu d'un Panel ou d'une Table, qui
            # interroge la console au moment de son propre rendu. D'où la
            # bascule de l'attribut, restaurée dans tous les cas.
            precedent = self._markup
            self._markup = False
            try:
                super().print(*objects, **{**kwargs, "markup": False})
            finally:
                self._markup = precedent


console = ConsoleSure()
err_console = ConsoleSure(stderr=True, style="bold red")
#: Avis de mise a jour : sur stderr comme les erreurs, pour ne jamais
#: polluer un document JSON, mais sans le rouge qui ferait croire a un echec.
update_console = ConsoleSure(stderr=True, style="dim", highlight=False)


# ── Pager ────────────────────────────────────────────────────────────────────

def _pager_command() -> list[str]:
    """La commande de pagination, dans l'ordre des préférences déclarées.

    ``DSOXLAB_PAGER`` prime sur ``PAGER`` pour qu'un apprenant puisse régler
    la lecture des cours sans toucher au pager de tout son système. Faute
    des deux, ``less -R`` : sans ``-R``, les couleurs de Rich s'affichent en
    séquences d'échappement brutes et le cours devient illisible.
    """
    raw = os.environ.get("DSOXLAB_PAGER") or os.environ.get("PAGER") or ""
    parts = shlex.split(raw) if raw.strip() else ["less"]
    if Path(parts[0]).name == "less" and not any(
        arg in ("-R", "-r", "--RAW-CONTROL-CHARS", "--raw-control-chars")
        for arg in parts[1:]
    ):
        parts.append("-R")
    return parts


def _write_through(text: str) -> None:
    """Écrit un rendu déjà produit par Rich, sans le repasser dans Rich."""
    console.file.write(text)
    console.file.flush()


def _page(text: str) -> None:
    """Affiche ``text`` directement s'il tient à l'écran, sinon le pagine."""
    if not text:
        return
    # -1 : la ligne que le shell reprendra pour son prompt.
    if text.count("\n") <= console.size.height - 1:
        _write_through(text)
        return

    cmd = _pager_command()
    if shutil.which(cmd[0]) is None:
        _write_through(text)
        return
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, text=True)
    except OSError:
        # Pas de pager utilisable : mieux vaut une sortie trop longue
        # qu'une commande qui échoue sur son affichage.
        _write_through(text)
        return
    try:
        proc.communicate(text)
    except KeyboardInterrupt:
        proc.wait()


@contextmanager
def paged(*, enabled: bool = True) -> Iterator[None]:
    """Envoie au pager ce que le bloc affiche, s'il dépasse la hauteur du terminal.

    ``course`` déverse un README entier, jusqu'à un millier de lignes dans
    les catalogues existants. Sans client SSH ni tmux, le scrollback d'un
    terminal local ne suffit pas et le début du cours est perdu.

    Deux garde-fous : on ne pagine jamais hors d'un terminal, pour qu'un
    pipe ou une redirection reçoive toujours du texte exploitable, et on ne
    pagine pas ce qui tient déjà à l'écran, pour ne pas ouvrir un pager sur
    trois lignes. Le rendu capturé est réémis même si le bloc lève, sans
    quoi une erreur en fin d'affichage avalerait tout ce qui la précède.
    """
    if not enabled or not console.is_terminal:
        yield
        return

    capture = None
    try:
        with console.capture() as capture:
            yield
    finally:
        if capture is not None:
            _page(capture.get())


# ── Helpers ──────────────────────────────────────────────────────────────────

#: Palette employée pour teinter les valeurs LIBRES du contrat (`section`,
#: `level`). Elle ne connaît aucune valeur : la couleur est tirée du nom, pas
#: d'une table qui nommerait des domaines.
_FREE_FIELD_PALETTE = (
    "green", "yellow", "cyan", "magenta", "blue", "orange3", "purple4", "red",
)


def _stable_color(value: str, *, bold: bool = False) -> str:
    """Une couleur stable pour une valeur libre du contrat.

    ``section`` et ``level`` appartiennent au catalogue, pas au moteur : le
    contrat les déclare libres et « dsoxlab ne connaît aucune liste de
    domaines ». Ces deux fonctions portaient pourtant une table de noms —
    ``linux``, ``ansible``, ``terraform``, ``kubernetes``, ``rhcsa`` — donc de
    la connaissance de domaine dans le moteur, et une seule conséquence
    visible : les catalogues de cette table étaient colorés, les autres
    uniformément blancs.

    La couleur vient donc du nom lui-même, par ``crc32`` : déterministe d'une
    exécution à l'autre (là où ``hash()`` d'une ``str`` est randomisé par
    ``PYTHONHASHSEED``), stable pour un catalogue donné, et disponible pour
    tout nom, y compris celui d'un domaine que personne n'a prévu.
    """
    if not value:
        return "white"
    teinte = _FREE_FIELD_PALETTE[zlib.crc32(value.encode("utf-8")) % len(_FREE_FIELD_PALETTE)]
    return f"bold {teinte}" if bold else teinte


def _level_color(level: str) -> str:
    return _stable_color(level)


def _difficulty_label(difficulty: str) -> str:
    """Traduit les difficultés courantes, laisse passer le reste.

    Le champ est libre par contrat : un dépôt de labs peut y mettre ce qu'il
    veut. On ne traduit donc que les trois valeurs employées partout, et toute
    autre valeur s'affiche telle quelle plutôt que de disparaître.
    """
    cle = f"difficulty_{difficulty.strip().lower()}"
    traduit = _(cle)
    return difficulty if traduit == cle else traduit


def _section_color(section: str | None) -> str:
    return _stable_color(section or "", bold=True)


def _type_badge(lab_type: str) -> str:
    """Short coloured badge for the lab type.

    Le repli échappe la valeur : le parseur du contrat est tolérant par
    garantie de v1, donc ``lab_type`` arrive ici tel que le catalogue l'a écrit,
    y compris avec des crochets. ``validate-structure`` le refuserait, mais il
    n'est pas joué avant d'afficher un catalogue.
    """
    return {
        "lab":       "[bold green]lab[/bold green]",
        "challenge": "[bold yellow]challenge[/bold yellow]",
        "capstone":  "[bold red]capstone[/bold red]",
    }.get(lab_type, f"[dim]{texte_affichable(lab_type)}[/dim]")


# ── list-labs ─────────────────────────────────────────────────────────────────

#: Les colonnes du catalogue, de la plus indispensable à la plus accessoire.
#:
#: L'ordre est celui du besoin de quelqu'un qui CHOISIT un lab : l'identifiant
#: parce qu'il le tapera, le titre parce qu'il dit le sujet, le niveau parce
#: qu'il situe le lab dans la progression (`l1` à `l4` sur les catalogues qui
#: en déclarent), le score parce qu'il dit où l'on en est.
#:
#: `runtime` est dernier à dessein : c'est la seule colonne dont le contenu
#: (`shell`, `vm`) est du vocabulaire d'infrastructure, et un apprenant n'a pas
#: à le connaître pour choisir un exercice.
_COLONNES_CATALOGUE = ("id", "title", "level", "score", "section", "duration", "type", "runtime")

#: L'ordre d'AFFICHAGE, qui n'est pas celui de la priorité ci-dessus : c'est
#: celui des huit colonnes d'origine, et le changer pour rien ferait chercher
#: le score là où il n'est plus à quiconque connaît déjà ce tableau.
_ORDRE_AFFICHAGE = ("section", "id", "title", "type", "level", "runtime", "duration", "score")

#: Les trois colonnes qu'on garde même dans un terminal très étroit : sans
#: l'identifiant il n'y a rien à taper, sans le titre rien à comprendre, sans
#: le score rien à reprendre.
_COLONNES_MINIMALES = ("id", "title", "score")

#: Largeur laissée au titre. C'est la SEULE colonne élastique : elle se replie
#: sur plusieurs lignes de toute façon, donc lui réserver la largeur de son plus
#: long libellé coûterait une colonne entière pour rien. 18 est le réglage qui
#: fait tenir « identifiant + titre + niveau + score » à 80 colonnes sur
#: `ansible-training`, dont les identifiants montent à 36 caractères.
#:
#: L'identifiant, lui, n'est jamais plafonné, et c'est une règle et non un
#: réglage : plafonné à 28, il s'affichait « decouvrir-declaratif-vs… » sur ce
#: même catalogue. Un identifiant tronqué ne se tape pas et ne se copie pas ;
#: c'est la seule valeur du tableau dont l'intégrité est non négociable. Quand
#: la place manque, c'est une autre colonne qui tombe, jamais lui.
_LARGEUR_MIN_TITRE = 18

#: Ce qu'une colonne coûte en plus de son contenu : deux espaces de marge et
#: une bordure verticale, tels que Rich les dessine.
_MARGE_COLONNE = 3


def _largeur_utile(valeurs: list[str], entete: str) -> int:
    """La place qu'il faut à une colonne, entête comprise, marges incluses."""
    contenu = max((len(v) for v in valeurs), default=0)
    return max(contenu, len(entete)) + _MARGE_COLONNE


def largeurs_du_catalogue(labs: list[LabDefinition]) -> dict[str, int]:
    """Ce que chaque colonne coûterait pour CES labs.

    Mesurer plutôt qu'estimer, et la différence n'est pas théorique : une
    première version portait des largeurs constantes, dont 12 pour le niveau.
    Or le niveau vaut « l1 » à « l4 » sur les catalogues linux et ansible, soit
    **deux caractères**, et il y est un repère de progression que l'apprenant
    cherche. Estimé large, il tombait de l'affichage à 80 colonnes ; mesuré, il
    coûte 9 colonnes et y tient sans peine.
    """
    textes = {
        "id": [lab.id for lab in labs],
        "title": [lab.title for lab in labs],
        "level": [lab.level for lab in labs],
        "section": [lab.section or "" for lab in labs],
        "duration": [lab.estimated_time for lab in labs],
        "type": [lab.lab_type for lab in labs],
        "runtime": [lab.runtime.type.value for lab in labs],
        # Le score n'est pas une donnée du lab : sa cellule la plus large est
        # « 100/100 », et son entête peut être plus longue selon la langue.
        "score": ["100/100"],
    }
    largeurs = {
        nom: _largeur_utile(valeurs, _(f"col_{nom}")) for nom, valeurs in textes.items()
    }
    # Le titre est la seule colonne élastique : au-delà de son minimum, il se
    # replie plutôt que de réclamer la place de son plus long libellé.
    largeurs["title"] = min(largeurs["title"], _LARGEUR_MIN_TITRE + _MARGE_COLONNE)
    return largeurs


def _colonnes_reservees(labs: list[LabDefinition] | None) -> tuple[str, ...]:
    """Les colonnes servies avant toutes les autres.

    Le niveau en fait partie dès qu'il est **court**, et non pas dès qu'il
    varie. C'est un repère de progression : sur les catalogues qui le déclarent
    en `l1`…`l4`, savoir qu'on est en `l1` oriente, même quand tous les labs
    affichés sont en `l1` parce qu'une section est active. Son absence
    désoriente plus sûrement que celle de trois autres colonnes réunies, et
    c'est un retour d'usage qui l'a établi, pas une mesure.

    Écrit en mots (« automatisation »), il répète la section et coûte dix-sept
    colonnes : il redevient alors une colonne ordinaire.
    """
    if not labs:
        return _COLONNES_MINIMALES
    plus_long = max((len(lab.level) for lab in labs), default=0)
    if plus_long <= _LONGUEUR_MAX_NIVEAU_REPERE:
        return (*_COLONNES_MINIMALES, "level")
    return _COLONNES_MINIMALES


#: Longueur au-delà de laquelle un niveau n'est plus un repère de progression.
#: `l1` à `l4` sur les catalogues linux, ansible et kubernetes ; mais
#: « automatisation » sur `python-dsoxlab-training`, où il répète la section.
#: Un code court situe dans un parcours, un mot long est une étiquette.
_LONGUEUR_MAX_NIVEAU_REPERE = 6


def _colonne_constante(labs: list[LabDefinition], nom: str) -> bool:
    """La colonne porte-t-elle la même valeur partout ?

    Une colonne constante ne distingue aucun lab de ses voisins : elle occupe
    de la largeur sans aider à choisir, et cette largeur est prise au titre,
    qui se replie alors sur une ligne de plus. Mesuré sur
    `python-dsoxlab-training` : afficher `type`, qui vaut « lab » pour les sept
    labs, faisait passer le rendu de 33 à 49 lignes. Elle est donc écartée,
    sauf sous ``--long``.
    """
    if nom in _COLONNES_MINIMALES or len(labs) < 2:
        return False
    lecteurs: dict[str, Callable[[LabDefinition], str]] = {
        "level": lambda lab: lab.level,
        "section": lambda lab: lab.section or "",
        "duration": lambda lab: lab.estimated_time,
        "type": lambda lab: lab.lab_type,
        "runtime": lambda lab: lab.runtime.type.value,
    }
    lire = lecteurs.get(nom)
    if lire is None:
        return False
    return len({lire(lab) for lab in labs}) == 1


def colonnes_du_catalogue(
    largeur: int, labs: list[LabDefinition] | None = None, *, tout: bool = False
) -> tuple[str, ...]:
    """Quelles colonnes afficher dans un terminal de cette largeur.

    Le défaut corrigé, mesuré avant de l'être : les huit colonnes exigeaient
    **160 colonnes** de terminal pour ne rien tronquer. À 80, la largeur d'un
    terminal ouvert sans redimensionnement et celle d'un tmux coupé en deux,
    six colonnes sur huit tombaient à une lettre (``│ L… │ l… │ a… │``) et le
    rendu comptait **104 troncatures**. Le tableau le plus consulté du parcours
    était illisible par défaut.

    Les colonnes sont donc ajoutées par ordre d'utilité tant qu'elles tiennent,
    avec deux règles qui comptent plus que l'ordre lui-même :

    - les largeurs sont **mesurées sur les labs affichés** quand on les a, pas
      estimées : le niveau vaut deux caractères sur les catalogues qui le
      déclarent en `l1`…`l4`, et dix-sept sur celui qui l'écrit en mots ;
    - une colonne **constante** passe en dernier, puisqu'elle ne distingue rien.

    ``tout=True`` (option ``--long``) force les huit : un écran large ou une
    capture pour un document n'a pas à subir une heuristique.
    """
    if tout:
        return _ORDRE_AFFICHAGE
    largeurs = largeurs_du_catalogue(labs) if labs else dict(_LARGEURS_PAR_DEFAUT)
    reservees = _colonnes_reservees(labs)
    candidates = [nom for nom in _COLONNES_CATALOGUE if nom not in reservees]
    if labs:
        # Une colonne constante est écartée, pas reléguée : la largeur qu'elle
        # prendrait revient au titre, qui se replie sur moins de lignes.
        candidates = [nom for nom in candidates if not _colonne_constante(labs, nom)]
    retenues = list(reservees)
    pris = sum(largeurs[nom] for nom in retenues)
    for nom in candidates:
        if pris + largeurs[nom] > largeur:
            continue
        retenues.append(nom)
        pris += largeurs[nom]
    return tuple(nom for nom in _ORDRE_AFFICHAGE if nom in retenues)


#: Largeurs de repli, quand l'appelant ne passe pas les labs. Elles ne servent
#: qu'à cela : dès qu'on a les labs, on mesure.
_LARGEURS_PAR_DEFAUT = {
    "id": 33,
    "title": 24,
    "level": 12,
    "score": 10,
    "section": 18,
    "duration": 9,
    "type": 8,
    "runtime": 11,
}


#: Mise en forme de chaque colonne, séparée du remplissage : une colonne
#: s'ajoute ou se retire sans toucher à la boucle qui remplit les lignes.
_REGLAGES_COLONNES: dict[str, dict[str, Any]] = {
    "section": {"style": "bold", "no_wrap": True},
    # `no_wrap` sur l'identifiant : sa colonne lui réserve sa largeur entière,
    # donc il ne peut ni être tronqué ni être coupé en deux. Rich ne replie que
    # sur les espaces, et un identifiant n'en a pas.
    "id": {"style": "bold cyan", "no_wrap": True},
    "title": {},
    "type": {"justify": "center"},
    "level": {"justify": "center"},
    "runtime": {"justify": "center"},
    "duration": {"justify": "center"},
    "score": {"justify": "center"},
}


def _cellule_de_score(lab_id: str, scores: dict[str, tuple[int, int]] | None) -> Text:
    """Le meilleur score du lab, coloré par ce qu'il vaut, ou un tiret."""
    if not scores or lab_id not in scores:
        return Text("·", style="dim")
    best, max_s = scores[lab_id]
    pct = int(best * 100 / max_s) if max_s else 0
    couleur = "green" if pct == 100 else "yellow" if pct >= 50 else "red"
    return Text(f"{best}/{max_s}", style=couleur)


def _cellules_du_lab(
    lab: LabDefinition,
    scores: dict[str, tuple[int, int]] | None,
    section_precedente: str,
) -> dict[str, Any]:
    """Toutes les cellules possibles d'une ligne, que les colonnes piochent.

    Les huit sont construites même quand trois seront affichées : chacune coûte
    une mise en forme de chaîne, et faire dépendre la construction des colonnes
    retenues rendrait la fonction conditionnelle à son propre rendu.

    ``Text`` rend les crochets littéralement mais pas une séquence
    d'échappement : d'où ``neutraliser`` ici, et ``texte_affichable`` sur ce qui
    part dans une chaîne de balisage.
    """
    section = lab.section or ""
    # Une seule section affichée par groupe : les lignes suivantes du même
    # groupe laissent la cellule vide.
    if section == section_precedente:
        cellule_section = Text("", style="")
    else:
        cellule_section = Text(neutraliser(section), style=_section_color(section))

    return {
        "section": cellule_section,
        "id": texte_affichable(lab.id),
        "title": texte_affichable(lab.title),
        "type": _type_badge(lab.lab_type),
        "level": Text(neutraliser(lab.level), style=_level_color(lab.level)),
        "runtime": lab.runtime.type.value,
        "duration": texte_affichable(lab.estimated_time),
        "score": _cellule_de_score(lab.id, scores),
    }


def print_labs_table(
    labs: list[LabDefinition],
    scores: dict[str, tuple[int, int]] | None = None,
    *,
    tout: bool = False,
) -> None:
    if not labs:
        console.print(f"[yellow]{_('no_labs_found')}[/yellow]")
        return

    colonnes = colonnes_du_catalogue(console.width, labs, tout=tout)
    table = Table(title=_('table_labs_title'), show_lines=True)
    for nom in colonnes:
        table.add_column(_(f"col_{nom}"), **_REGLAGES_COLONNES[nom])

    section_precedente = ""
    for lab in labs:
        cellules = _cellules_du_lab(lab, scores, section_precedente)
        section_precedente = lab.section or ""
        table.add_row(*(cellules[nom] for nom in colonnes))

    console.print(table)
    # Le dire, plutôt que de laisser des colonnes disparaître en silence : une
    # information retirée sans un mot se cherche dans la documentation, ou,
    # pire, ne se cherche pas du tout.
    masquees = len(_COLONNES_CATALOGUE) - len(colonnes)
    if masquees:
        note(_("labs_table_colonnes_masquees", masquees=masquees,
               total=len(_COLONNES_CATALOGUE)))


# ── show ──────────────────────────────────────────────────────────────────────

def _doc_affichable(lab: LabDefinition) -> str:
    """Le ``doc_url`` tel qu'on peut le montrer, ou la raison de son refus.

    Pas d'hyperlien cliquable : la cible d'un ``[link=…]`` n'est pas ce que
    l'œil lit, et cette cible vient du catalogue. L'adresse s'affiche en clair,
    et ``dsoxlab guide --open`` reste le geste qui l'ouvre — demandé, jamais
    déclenché par une valeur déclarée.
    """
    if not lab.doc_url:
        return "·"
    try:
        return texte_affichable(url_sure(lab.doc_url, champ="doc_url"))
    except URLRefusee as refus:
        # La chaîne fautive n'est pas affichée : on dit pourquoi, pas quoi.
        return f"[red]{_('url_refusee_inline', reason=_(refus.cle, **refus.params))}[/red]"


def print_lab_detail(lab: LabDefinition, status: str | None = None) -> None:
    couleur_section = _section_color(lab.section)
    couleur_niveau = _level_color(lab.level)
    lines = [
        f"{_('field_section')}    [{couleur_section}]{texte_affichable(lab.section or '')}[/{couleur_section}]",
        f"{_('field_title')}      {texte_affichable(lab.title)}",
        f"{_('field_type')}       {_type_badge(lab.lab_type)}"
        + (f"  —  bloc {lab.bloc}" if lab.bloc else ""),
        f"{_('field_level')}     [{couleur_niveau}]{texte_affichable(lab.level)}[/{couleur_niveau}]",
        f"{_('field_runtime')}    {lab.runtime.type.value} / {lab.runtime.topology}",
        f"{_('field_duration')}      {texte_affichable(lab.estimated_time)}",
        f"{_('field_difficulty')} {texte_affichable(_difficulty_label(lab.difficulty))}",
        f"{_('field_distros')}    {texte_affichable(', '.join(lab.distros))}",
        f"{_('field_skills')}     {texte_affichable(', '.join(lab.skills))}",
        f"{_('field_doc')}        {_doc_affichable(lab)}",
    ]
    # Le seuil d'un examen blanc se lit AVANT de le passer, pas après : c'est
    # la barre que l'apprenant vise. Un lab ordinaire n'en déclare pas.
    if lab.exam_passing_score:
        lines.append(f"{_('field_exam_score')} {lab.exam_passing_score} %")
    if lab.track:
        lines.append(f"{_('field_track')}   {texte_affichable(', '.join(lab.track))}")
    if lab.certification_tags:
        lines.append(
            f"{_('field_certifs')}    {texte_affichable(', '.join(lab.certification_tags))}"
        )
    if status:
        lines.append(f"{_('field_status')}     {status}")

    val = lab.validation
    val_parts = []
    if val.functional:
        val_parts.append(f"[green]{_('val_functional')}[/green]")
    if val.security:
        val_parts.append(f"[yellow]{_('val_security')}[/yellow]")
    if val.persistence_after_reboot:
        val_parts.append(f"[cyan]{_('val_persistence')}[/cyan]")
    lines.append(f"{_('field_validation')} {', '.join(val_parts)}")

    console.print(Panel("\n".join(lines), title=f"[bold]{texte_affichable(lab.id)}[/bold]",
                        expand=False))


# ── validate-structure ────────────────────────────────────────────────────────

def print_structure_reports(reports: list[StructureReport]) -> None:
    tree = Tree(_('tree_structure_title'))
    for report in reports:
        if report.ok:
            branch = tree.add(f"[green]✔[/green] {texte_affichable(report.lab_id)}")
        else:
            branch = tree.add(f"[red]✘[/red] {texte_affichable(report.lab_id)}")
            for issue in report.issues:
                branch.add(f"[red]{_(issue.key, **issue.params)}[/red]")
    console.print(tree)


# ── doctor ────────────────────────────────────────────────────────────────────

def _libelle_statut(check: Check, *, blocking: bool) -> str:
    """Le mot qui rend l'état d'un contrôle, dans la langue du lecteur.

    L'état, lui, est un jeton stable porté par le contrôle. Un composant
    informatif absent n'est pas un échec, et le vocabulaire change donc de
    tableau ; ce qu'une intégration lit, elle, ne change jamais.
    """
    if check.state == STATE_CHOICE_REQUIRED:
        return _("status_choose")
    if check.state == STATE_UNKNOWN:
        # Rien mesuré : ni le vert qui rassure à tort, ni le rouge qui accuse
        # sans preuve. Le mot le dit dans les deux tableaux.
        return _("status_unknown")
    if blocking:
        return _("status_ok") if check.ok else _("status_ko")
    return _("status_present") if check.ok else _("status_absent")


def _doctor_table(title: str, checks: list[Check], *, blocking: bool) -> Table:
    """Un tableau de checks.

    ``blocking=False`` change le vocabulaire du statut : un composant
    informatif absent n'est pas un échec, et l'afficher en rouge est
    précisément ce qui décourageait au premier lancement.
    """
    # La colonne de remédiation n'existe que s'il y a quelque chose à remédier.
    # Sur un poste sain, elle était vide de haut en bas et prenait pourtant sa
    # part de largeur : à 80 colonnes, le détail était alors tronqué, et c'est
    # lui qui porte la version trouvée et le chemin du composant. Une colonne
    # entièrement vide ne dit rien, et elle coûtait la seule information utile.
    avec_remediation = any(not check.ok and check.remediation for check in checks)

    # `SIMPLE_HEAD` plutôt que le cadre plein : vingt lignes de filets verticaux
    # pour un diagnostic qui est vert de haut en bas, c'est du bruit qui occupe
    # six colonnes et attire l'œil là où il n'y a rien à voir. Un trait sous
    # l'en-tête suffit à dire « tableau ».
    table = Table(title=title, show_header=True, box=box.SIMPLE_HEAD, pad_edge=False)
    table.add_column(_('col_component'))
    # Le statut tient en un signe. « ✔ OK » disait deux fois la même chose, et
    # prenait cinq colonnes au détail, qui porte la version et le chemin.
    table.add_column(_('col_status'), justify="center", no_wrap=True)
    table.add_column(_('col_detail'), overflow="fold")
    if avec_remediation:
        # `fold` plutôt que le repli par mots : une remédiation est une
        # commande, et une commande porte des chemins. Rich ne coupe pas un
        # mot plus long que la colonne, il le tronque par un « … » — et une
        # commande tronquée ne se copie pas, donc ne répare rien. Mesuré sur
        # `ansible-galaxy collection install -r <chemin absolu>`.
        table.add_column(_('col_remediation'), overflow="fold")

    for check in checks:
        status = _libelle_statut(check, blocking=blocking)
        cellules = [check.label, status, check.detail]
        if avec_remediation:
            cellules.append("" if check.ok else f"[dim]{check.remediation}[/dim]")
        table.add_row(*cellules)
    return table


def print_infra_status(etat: EtatInfra) -> None:
    """Qui répond, qui ne répond pas, et pourquoi.

    Les hôtes d'abord, un par ligne, puis le verdict ; et quand il manque
    quelqu'un, la cause de chacun. Dire pourquoi le diagnostic est limité plutôt
    que de laisser croire que l'outil a regardé la machine alors qu'il n'a pu
    regarder que le réseau.
    """
    for hote in etat.hotes:
        # `success` et `error` posent déjà leur marqueur : en ajouter un dans la
        # chaîne donnait « ✘   ✘ hote.lab », que l'utilisateur lit comme un
        # défaut de rendu.
        if hote.joignable:
            success(f"  {hote.fqdn} ({hote.ip})")
        else:
            error(f"  {hote.fqdn} ({hote.ip}) : {hote.raison}")

    if etat.tout_repond:
        success(_("status_all_ok", count=etat.joignables))
        return

    error(_(
        "status_partial",
        ok=etat.joignables,
        total=etat.total,
        provider=etat.provider,
    ))
    if not etat.hyperviseur_interrogeable:
        warn(_("status_provider_not_inspectable", provider=etat.provider))
    elif etat.hyperviseur_erreur is not None:
        warn(_("status_hypervisor_unavailable", error=etat.hyperviseur_erreur))
    for hote in etat.hotes:
        if not hote.joignable:
            console.print(f"[cyan]ℹ[/cyan]   {hote.fqdn} — {_cause_de(hote)}")


def _cause_de(hote: EtatHote) -> str:
    """La phrase qui nomme la cause d'un hôte muet, et le geste qui la corrige.

    Une cause, un message, une action. L'ancien texte en proposait deux à la
    fois (« cloud-init tourne peut-être encore, ou alors reprovisionne ») pour
    tous les hôtes et toutes les pannes : l'apprenant devait trancher lui-même
    entre deux conseils dont l'un coûtait une infrastructure entière.
    """
    from ..services import host_diagnosis

    domaine = hote.domaine or hote.fqdn
    phrases = {
        host_diagnosis.CAUSE_DOMAIN_ABSENT: lambda: _(
            "status_cause_domain_absent", host=hote.fqdn
        ),
        host_diagnosis.CAUSE_DOMAIN_NOT_RUNNING: lambda: _(
            "status_cause_domain_not_running",
            domain=domaine,
            state=hote.etat_domaine or "?",
        ),
        host_diagnosis.CAUSE_DOMAIN_NO_LEASE: lambda: _(
            "status_cause_domain_no_lease", domain=domaine
        ),
        host_diagnosis.CAUSE_BOOTING: lambda: _("status_cause_booting", domain=domaine),
        host_diagnosis.CAUSE_SSH_REFUSED: lambda: _(
            "status_cause_ssh_refused", ip=hote.ip
        ),
        host_diagnosis.CAUSE_UNREACHABLE: lambda: _(
            "status_cause_unreachable", ip=hote.ip
        ),
        host_diagnosis.CAUSE_SSH_TIMEOUT: lambda: _(
            "status_cause_ssh_timeout", ip=hote.ip
        ),
        host_diagnosis.CAUSE_SSH_DENIED: lambda: _(
            "status_cause_ssh_denied", ip=hote.ip
        ),
    }
    phrase = phrases.get(hote.cause)
    if phrase is not None:
        return phrase()
    # Une raison inconnue reste inconnue : on la rend telle quelle plutôt que
    # d'en inventer une interprétation.
    return _("status_cause_unknown", reason=hote.raison or "?")


def print_validation(
    rapport: RapportValidation,
    table: tuple[Famille, ...],
    root: Path,
) -> None:
    """Les anomalies d'une validation, groupées par famille, dans l'ordre de la table.

    Ce rendu remplace sept blocs d'affichage quasi identiques, chacun construit
    à côté de son contrôle. Les séparer de la collecte supprime le risque que
    le document machine et le terminal divergent : ils lisent désormais le même
    rapport.

    La structure garde son rendu propre (``print_structure_reports``) : il
    groupe par lab avec le détail des fichiers requis, ce qu'une liste à plat
    ne saurait pas dire.
    """
    for famille in table:
        anomalies = [a for a in rapport.anomalies if a.rubrique == famille.entete]
        _rendre_famille(famille.entete, anomalies, root)

    # Les guides injoignables, après les anomalies et sous leur propre titre :
    # ce n'est pas un défaut du lab, c'est un contrôle qui n'a pas regardé.
    if rapport.urls_injoignables:
        console.print(_("doc_url_unreachable_header"))
        for anomalie in rapport.urls_injoignables:
            url = anomalie.params.get("url", "")
            console.print(
                f"  [yellow]―[/yellow] {texte_affichable(anomalie.lab or '')} — "
                f"{texte_affichable(str(url))} — {_(anomalie.cle, **anomalie.params)}"
            )
        info(_("doc_url_unreachable_note"))


def _rendre_famille(entete: str, anomalies: list[Anomalie], root: Path) -> None:
    """Un groupe d'anomalies sous son titre, ou rien du tout s'il est vide."""
    if not anomalies:
        return
    console.print(_(entete))
    for anomalie in anomalies:
        console.print(f"  [red]✘[/red] {_etiquette(anomalie, root)}")


def _etiquette(anomalie: Anomalie, root: Path) -> str:
    """Ce qui situe l'anomalie : son lab, son fichier, son champ, puis la phrase.

    Les trois ne sont jamais tous présents : une anomalie de `meta.yml` n'a pas
    de lab, une anomalie de métadonnée n'a pas de fichier mais un champ.
    """
    situation: list[str] = []
    if anomalie.lab:
        situation.append(texte_affichable(anomalie.lab))
    if anomalie.chemin is not None:
        situation.append(str(_relatif(anomalie.chemin, root)))
    if anomalie.champ:
        situation.append(texte_affichable(anomalie.champ))
    prefixe = " — ".join(situation)
    phrase = _(anomalie.cle, **anomalie.params)
    return f"{prefixe}: {phrase}" if prefixe else phrase


def _relatif(chemin: Path, root: Path) -> Path:
    """Le chemin depuis la racine du catalogue, ou absolu s'il est ailleurs."""
    try:
        return chemin.relative_to(root)
    except ValueError:
        return chemin


def print_audit_pedagogique(rapport: RapportPedagogique) -> None:
    """Les constats de l'audit, groupés par lab, les manques d'abord.

    Pas de score global, et c'est délibéré : agréger « aucun test » et « aucun
    indice » en un chiffre ferait viser le chiffre. Chaque ligne nomme un lab et
    une chose à faire.
    """
    from ..services.audit_pedagogique import ATTENTION, MANQUE

    if not rapport.constats:
        success(_("audit_rien_a_signaler", count=rapport.labs_examines))
        _note_assertions(rapport)
        return

    table = Table(title=_("audit_titre"), show_header=True, show_lines=True)
    table.add_column(_("audit_colonne_lab"), style="bold cyan", no_wrap=True)
    table.add_column(_("audit_colonne_constat"), overflow="fold")

    # Les manques avant les points d'attention : un lab sans test n'est pas du
    # même ordre qu'un lab sans indice, et l'ordre de lecture doit le dire.
    for niveau, marque in ((MANQUE, "[red]✘[/red]"), (ATTENTION, "[yellow]⚠[/yellow]")):
        for constat in rapport.par_niveau(niveau):
            table.add_row(
                texte_affichable(constat.lab_id),
                f"{marque} {neutraliser(constat.phrase())}",
            )
    console.print(table)
    note(_(
        "audit_resume",
        labs=rapport.labs_examines,
        manques=len(rapport.par_niveau(MANQUE)),
        attentions=len(rapport.par_niveau(ATTENTION)),
    ))
    _note_assertions(rapport)
    note(_("audit_suite_export"))


def _note_assertions(rapport: RapportPedagogique) -> None:
    """Le cumul des assertions du catalogue, y compris quand rien n'est signalé.

    Ce chiffre est le seul endroit où la parité des langues se lit sur tout un
    catalogue : il n'y a pas de constat par lab pour elle, pour ne pas peindre
    en rouge cent labs d'un coup. Il s'affiche donc même sur un catalogue sans
    constat, sinon la mesure disparaîtrait au moment où elle devient utile.
    """
    mesure = rapport.assertions
    if not mesure.total:
        return
    note(_(
        "audit_resume_assertions",
        total=mesure.total,
        sans=mesure.sans_message,
        monolingues=mesure.monolingues,
        bilingues=mesure.bilingues,
    ))
    # Celui-ci n'est pas un chiffre de progression : c'est un défaut. Il se
    # dit donc en avertissement, et non dans la même phrase que le cumul,
    # parce qu'un message bilingue qui lève n'est pas un message traduit.
    if mesure.helper_injoignable:
        warn(_("audit_helper_injoignable", count=mesure.helper_injoignable))


def print_catalogues(
    connus: list[CatalogueConnu],
    installes: list[CatalogueInstalle],
    lang: str,
) -> None:
    """Les catalogues connus, puis ceux qui sont installés.

    Deux tableaux plutôt qu'une colonne « installé ? » : les deux listes ne se
    recouvrent pas nécessairement, un catalogue pouvant être installé depuis une
    URL absente du manifeste.
    """
    if connus:
        table = Table(title=_("catalog_titre_connus"), show_header=True)
        table.add_column(_("catalog_col_id"))
        table.add_column(_("catalog_col_description"))
        table.add_column(_("catalog_col_depot"), style="dim")
        for connu in connus:
            table.add_row(
                texte_affichable(connu.id),
                texte_affichable(connu.description(lang)),
                texte_affichable(connu.depot),
            )
        console.print(table)

    if not installes:
        console.print(f"[dim]{_('catalog_aucun_installe')}[/dim]")
        return

    table = Table(title=_("catalog_titre_installes"), show_header=True)
    table.add_column(_("catalog_col_id"))
    table.add_column(_("catalog_col_actif"), justify="center")
    table.add_column(_("catalog_col_chemin"), style="dim")
    for pose in installes:
        # `pose.id` est un nom de répertoire posé par `catalog add`, et la
        # racine un chemin : deux valeurs venues du dehors.
        table.add_row(
            texte_affichable(pose.id),
            "✔" if pose.actif else "",
            texte_affichable(str(pose.racine)),
        )
    console.print(table)


def print_lab_state(etat: LabState) -> None:
    """L'état d'un lab, en un panneau qui tient à l'écran.

    La couleur suit le verdict et non l'avancement : un lab dégradé appelle un
    geste immédiat, un lab validé n'en appelle aucun, et les deux intermédiaires
    disent seulement où on en est.
    """
    couleurs = {
        "not_started": "dim",
        "ready": "cyan",
        "in_progress": "yellow",
        "validated": "green",
        "degraded": "red",
    }
    teinte = couleurs.get(etat.state, "white")
    corps = f"[bold {teinte}]{etat.label}[/bold {teinte}]\n{texte_affichable(etat.detail)}"
    console.print(Panel(corps,
                        title=f"{_('status_titre')} — {texte_affichable(etat.lab_id)}",
                        border_style=teinte, expand=False))


def print_doctor(report: DoctorReport) -> None:
    """Affiche le diagnostic : ce qui bloque, puis ce qui informe."""
    console.print(_doctor_table(
        _('doctor_table_title'), report.required, blocking=True,
    ))

    if report.optional:
        # Titre et pied viennent du rapport : « non requis ici » est faux quand
        # le dépôt a des labs vm et qu'aucun provider n'est encore choisi.
        console.print(_doctor_table(
            _(report.optional_title_key), report.optional, blocking=False,
        ))
        console.print(f"[dim]{_(report.optional_hint_key)}[/dim]")

    for note in report.notes:
        console.print(f"[cyan]ℹ[/cyan] {note}")

    if report.fixable():
        console.print(f"[yellow]{_('doctor_fix_hint')}[/yellow]")
    elif report.failing():
        console.print(f"[yellow]{_('doctor_manual_hint')}[/yellow]")


# ── messages simples ──────────────────────────────────────────────────────────

def success(msg: str) -> None:
    console.print(f"[green]✔[/green] {msg}")


#: Les commandes que l'accueil propose, appariées à la clé qui les décrit.
#:
#: Ce sont des DONNÉES et non des messages : une commande s'écrit pareil dans
#: toutes les langues, et la traduire la casserait. Les sortir ici plutôt que
#: de les écrire dans des appels d'affichage dit exactement cela — et c'est ce
#: que le garde-fou i18n réclamait, à juste titre : une chaîne en dur dans un
#: `console.print` est suspecte tant qu'on n'a pas dit ce qu'elle est.
#: Le premier contact. `demo` d'abord, et l'ordre est le fond du sujet :
#: quelqu'un qui ne connaît pas l'outil n'a pas à choisir une formation parmi
#: six avant d'avoir vu à quoi ressemble un lab. `demo` ne clone rien, ne
#: provisionne rien, et tient en cinq minutes.
_ACCUEIL_SANS_CATALOGUE = (
    ("dsoxlab demo", "accueil_geste_demo"),
    ("dsoxlab catalog add linux", "accueil_geste_add"),
)
_ACCUEIL_SANS_ACTIF = (("dsoxlab catalog use", "accueil_geste_use"),)
_ACCUEIL_PRET = (
    ("dsoxlab list-labs", "accueil_geste_liste"),
    ("dsoxlab start <lab>", "accueil_geste_start"),
)
_ACCUEIL_TOUJOURS = (("dsoxlab doctor", "accueil_geste_doctor"),)

#: Le parcours entier, dans l'ordre où on le suit. Chaque message d'erreur de
#: dsoxlab nomme déjà le geste suivant ; il faut les rencontrer un par un pour
#: les découvrir, et un apprenant qui ouvre un terminal n'a aucune idée du
#: chemin. Le voici d'un bloc.
_ACCUEIL_PARCOURS = (
    ("dsoxlab catalog add linux", "accueil_parcours_1"),
    ("dsoxlab catalog use linux", "accueil_parcours_2"),
    ("dsoxlab instructor bootstrap", "accueil_parcours_3"),
    ("dsoxlab use --provider kvm", "accueil_parcours_4"),
    ("dsoxlab provision", "accueil_parcours_5"),
    ("dsoxlab run <lab>", "accueil_parcours_6"),
    ("dsoxlab check", "accueil_parcours_7"),
)

#: Celle qui joue tout le parcours à elle seule.
_ACCUEIL_RACCOURCI = "dsoxlab start <lab>"

# La boucle `for c in …; do dsoxlab catalog add $c; done` a été retirée de cet
# écran : 94 caractères de shell devant quelqu'un dont le premier lab enseigne
# le terminal, c'est une inversion de difficulté. Installer six formations
# d'un coup reste possible, et c'est le geste de quelqu'un qui sait déjà
# écrire cette boucle.


def gestes_pour(installes: list[str], actif: str | None) -> tuple[tuple[str, str], ...]:
    """Les gestes à proposer, pour un état donné de la machine.

    Hors du rendu à dessein : c'est une décision, et une décision se teste.
    Proposer « start » à qui n'a aucun catalogue ne l'avance pas ; proposer
    « catalog add » à qui en a trois le renvoie en arrière.
    """
    # Annotée : sans cela, mypy infère le type de la PREMIÈRE branche — un
    # tuple de deux éléments — et refuse la branche à un seul.
    choix: tuple[tuple[str, str], ...]
    # L'actif passe AVANT la liste des installés, et le parcours joué l'a
    # imposé : `dsoxlab demo` pose son catalogue hors de `catalogs/`, donc
    # `installes` reste vide alors qu'un catalogue est bel et bien actif.
    # L'accueil proposait alors « dsoxlab demo » à quelqu'un qui venait de le
    # faire, et annonçait « aucun catalogue » en en ayant un.
    if actif:
        choix = _ACCUEIL_PRET
    elif not installes:
        choix = _ACCUEIL_SANS_CATALOGUE
    else:
        commande, cle = _ACCUEIL_SANS_ACTIF[0]
        choix = ((f"{commande} {installes[0]}", cle),)
    return choix + _ACCUEIL_TOUJOURS


def catalogues_restants(
    connus: list[tuple[str, str, str]],
    installes: list[str],
    depots_installes: list[str],
) -> list[tuple[str, str]]:
    """Les catalogues du manifeste qui ne sont pas déjà posés.

    La comparaison porte sur l'URL du dépôt AVANT l'identifiant :
    ``catalog add <url>`` nomme le catalogue d'après l'URL, ``catalog add
    <nom>`` d'après le manifeste. Comparer les seuls identifiants faisait
    réapparaître en « installable » un catalogue déjà installé — mesuré sur une
    machine où `kubernetes` était posé sous le nom de son dépôt.
    """
    def _normalise(url: str) -> str:
        return url.rstrip("/").removesuffix(".git")

    poses = {_normalise(d) for d in depots_installes}
    return [
        (cle, description)
        for cle, description, depot in connus
        if cle not in installes and _normalise(depot) not in poses
    ]


def _gestes(entrees: tuple[tuple[str, str], ...], *, style: str = "cyan") -> None:
    """Affiche des couples (commande, libellé traduit), alignés et repliés.

    Une grille Rich plutôt qu'un gabarit `{commande:<27}` : avec le gabarit, un
    libellé plus long que la place restante était replié par la console à la
    colonne zéro, ce qui donnait « ce que cette machine peut faire, et ce qui »
    puis « manque » seul en début de ligne. La grille replie dans sa propre
    colonne, donc la seconde ligne reste alignée sous la première.
    """
    grille = Table.grid(padding=(0, 2))
    grille.add_column(style=style, no_wrap=True)
    grille.add_column(overflow="fold")
    for commande, cle in entrees:
        grille.add_row(commande, _(cle))
    console.print(Padding(grille, (0, 0, 0, 4)))


def _noms_replies(noms: list[str], indentation: str = "    ") -> None:
    """Imprime une liste de noms repliée, en gardant son indentation.

    Le repli est fait ici et non laissé à Rich : Rich replie à la colonne 0,
    donc la continuation perdait les quatre espaces et la liste ne se lisait
    plus comme une liste. Mesuré à 80 colonnes, qui est la largeur que le
    cliquet d'écran simule.
    """
    largeur = max(40, console.width - len(indentation) - 2)
    ligne = ""
    for nom in noms:
        morceau = nom if not ligne else f", {nom}"
        if len(ligne) + len(morceau) > largeur:
            console.print(f"{indentation}[cyan]{ligne}[/cyan],")
            ligne = nom
        else:
            ligne += morceau
    if ligne:
        console.print(f"{indentation}[cyan]{ligne}[/cyan]")


def _bloc_catalogues(restants: list[tuple[str, str]]) -> None:
    """Les catalogues qu'il reste à installer, nommés et non déroulés.

    Les IDENTIFIANTS, pas les descriptions. La collection est passée de six à
    douze catalogues, et les dérouler avec leur description tenait 31 lignes
    sur un écran de 24, dont deux tronquées par le repli et un alignement
    cassé par l'identifiant le plus long. Un écran d'accueil oriente, il ne
    catalogue pas : `catalog list` donne les descriptions à qui les veut.

    Rien n'est affiché quand il ne reste rien à installer : lister ce qui est
    déjà là serait du bruit.
    """
    if not restants:
        return
    console.print(f"  [bold]{_('accueil_titre_catalogues')}[/bold]")
    console.print()
    _noms_replies([cle for cle, _description in restants])
    console.print()
    console.print(f"    [dim]{_('accueil_catalogues_detail')}[/dim]")
    console.print()


def afficher_accueil(
    *,
    version: str,
    installes: list[str],
    depots_installes: list[str],
    actif: str | None,
    connus: list[tuple[str, str, str]],
    machines_a_monter: bool = False,
) -> None:
    """L'écran que `dsoxlab` seul affiche : l'état, puis le geste suivant.

    Le geste dépend de l'état, et c'est tout l'intérêt. Proposer
    « dsoxlab start » à qui n'a aucun catalogue ne l'avance pas ; proposer
    « catalog add » à qui en a déjà trois le renvoie en arrière. L'aide de
    Typer, elle, alignait vingt-cinq commandes sans distinguer les deux.
    """
    console.print()
    console.print(f"  [bold]dsoxlab[/bold] [dim]{version}[/dim]")
    console.print(f"  [dim]{_('accueil_baseline')}[/dim]")
    console.print()

    # ── 1. L'état, en une ligne ──────────────────────────────────────────
    if not installes and not actif:
        console.print(f"  [yellow]•[/yellow] {_('accueil_etat_aucun')}")
    elif actif:
        console.print(
            f"  [green]•[/green] {_('accueil_etat_actif')} [bold]{actif}[/bold]"
            # Le nombre de catalogues installés n'a de sens qu'au pluriel : un
            # « (1) » nu, à côté d'un nom, se lisait comme un compte de labs.
            + (f" [dim]({len(installes)})[/dim]" if len(installes) > 1 else "")
        )
    else:
        console.print(
            f"  [yellow]•[/yellow] {_('accueil_etat_sans_actif')}"
            f" [dim]({', '.join(installes)})[/dim]"
        )
    console.print()

    # ── 2. Le geste suivant, et lui seul ─────────────────────────────────
    console.print(f"  [bold]{_('accueil_titre_suite')}[/bold]")
    console.print()
    _gestes(gestes_pour(installes, actif))
    console.print()

    # ── 3. Les catalogues, quand il en reste à installer ─────────────────
    #
    # Les lister TOUS quand tout est déjà posé serait du bruit : on ne montre
    # que ce qui manque, et rien du tout s'il ne manque rien.
    _bloc_catalogues(catalogues_restants(connus, installes, depots_installes))

    # ── 4. Le parcours des machines, pour qui en a ───────────────────────
    #
    # Ce bloc nomme `instructor bootstrap`, `use --provider kvm` et
    # `provision` : cinq des sept termes d'infrastructure que cet écran
    # affichait. Il ne s'adresse qu'à celui dont le catalogue actif déclare des
    # machines, et il était montré à tout le monde, y compris à quelqu'un qui
    # n'a encore rien installé. Le critère est celui de `doctor` depuis la
    # 0.1.88 : `infra.hosts` non vide.
    if machines_a_monter:
        console.print(f"  [bold]{_('accueil_titre_parcours')}[/bold]")
        console.print()
        console.print(
            f"    [cyan]{_ACCUEIL_RACCOURCI}[/cyan]  [dim]{_('accueil_parcours_start')}[/dim]"
        )
        console.print()
        _gestes(_ACCUEIL_PARCOURS, style="dim")
        console.print()

    console.print(f"  [dim]{_('accueil_pied')}[/dim]")
    console.print()


def info(msg: str) -> None:
    console.print(f"[cyan]ℹ[/cyan] {msg}")


def note(msg: str) -> None:
    """Une confirmation qui ne doit jamais atterrir dans la sortie standard.

    `dsoxlab export --out fichier.json` écrit un document et le dit ; mais un
    appelant qui redirige la sortie standard attend du JSON et rien d'autre.
    D'où stderr, et le même canal discret que l'avis de nouvelle version : ce
    n'est ni une erreur ni une donnée, c'est un mot à un humain.
    """
    update_console.print(f"ℹ {msg}")


def warn(msg: str) -> None:
    console.print(f"[yellow]⚠[/yellow] {msg}")


def error(msg: str) -> None:
    err_console.print(f"✘ {msg}")


# ── check result ──────────────────────────────────────────────────────────────

def print_echecs_de_tests(echecs: list[EchecDeTest]) -> None:
    """Les tests qui ont échoué, avec ce que leur auteur a écrit, sans trace.

    Deux niveaux, et l'ordre compte : le nom du test dit **quoi**, le message
    d'assertion dit **comment le réparer**. Ce second niveau est la raison
    d'être de cet affichage : une première version ne montrait que les noms, et
    jetait donc la phrase que l'auteur du lab avait écrite dans son ``assert``
    (« Crée le fichier, par exemple : mkdir -p reponses && echo … »). Le
    compteur de lignes de trace y gagnait, l'apprenant y perdait. C'est une
    capture avant/après qui l'a montré, pas une mesure.

    Le message passe par ``Text`` : il vient d'un ``assert`` écrit dans un
    catalogue, donc d'une source que ce dépôt ne contrôle pas, et un crochet y
    serait interprété comme du balisage Rich.
    """
    console.print(f"[yellow]{_('check_echecs_de_tests')}[/yellow]")
    # Les échecs qui partagent un message sont groupés, et c'est une correction
    # d'usage : sur un lab dont la fixture manque, les cinq tests rendent le
    # même « premiers-pas.txt introuvable, lance d'abord dsoxlab run », et
    # l'apprenant lisait cinq fois la même phrase sur dix lignes.
    for message, noms in _grouper_par_message(echecs):
        for nom in noms:
            console.print(f"  [red]✘[/red] {neutraliser(nom)}")
        if message:
            # `Padding` plutôt qu'une indentation dans la chaîne : Rich replie
            # alors DANS le bloc indenté, au lieu de ramener la suite à la
            # colonne zéro. Sans lui, « dsoxlab course premiers-pas » se
            # coupait en deux lignes désalignées, et la commande à taper
            # devenait illisible sur un terminal de 80 colonnes.
            console.print(Padding(Text(message, style="dim"), (0, 0, 0, 6)))


def _grouper_par_message(echecs: list[EchecDeTest]) -> list[tuple[str | None, list[str]]]:
    """Les échecs regroupés par message identique, dans l'ordre d'apparition.

    L'ordre est conservé : c'est celui dans lequel pytest a joué les tests, et
    donc celui dans lequel l'apprenant les a déclenchés.
    """
    groupes: list[tuple[str | None, list[str]]] = []
    for echec in echecs:
        if groupes and groupes[-1][0] == echec.message and echec.message:
            groupes[-1][1].append(echec.phrase)
        else:
            groupes.append((echec.message, [echec.phrase]))
    return groupes


def print_check_result(
    lab_id: str,
    passed: int,
    total: int,
    max_score: int,
    score: int,
    hints_used: int,
    hints_cost: int,
) -> None:
    """Le verdict d'un `check`, en trois lignes au plus.

    Trois partis pris, après avoir regardé ce que la version d'avant affichait
    vraiment :

    - **le score passe en tête**, en gras. C'est la réponse à la question qu'on
      se pose en lançant `check` ; elle arrivait en troisième position et dans
      le même corps que le reste ;
    - **une seule couleur par état.** La barre était verte pendant que le score
      était rouge : deux couleurs pour un seul fait, qui se contredisaient à
      l'œil. Vert, jaune ou rouge, les deux ensemble ;
    - **la ligne des indices n'apparaît que s'il y en a.** « Hints : aucun »
      occupait un tiers du panneau pour ne rien dire.

    L'alignement n'est plus écrit en dur (sept espaces après un libellé) :
    il tenait par chance, et la moindre traduction plus longue le défaisait.
    """
    etat = "green" if passed == total and total > 0 else "yellow" if passed > 0 else "red"
    rempli = int((passed / total) * 20) if total else 0
    barre = f"[{etat}]{'█' * rempli}[/{etat}][dim]{'░' * (20 - rempli)}[/dim]"

    lignes = [
        f"[bold {etat}]{score} / {max_score}[/bold {etat}] [dim]pts[/dim]",
        f"{barre}  [dim]{_('check_result_tests_passes', passed=passed, total=total)}[/dim]",
    ]
    if hints_used:
        # Deux clés plutôt qu'un « indice(s) utilisé(s) » : la parenthèse de
        # pluriel est la marque d'un texte que personne n'a relu.
        cle = "check_result_hint_used" if hints_used == 1 else "check_result_hints_used"
        lignes.append(f"[dim]{_(cle, count=hints_used, cost=hints_cost)}[/dim]")

    console.print(
        Panel(
            "\n".join(lignes),
            title=f"[bold]{_('check_result_title', lab_id=texte_affichable(lab_id))}[/bold]",
            expand=False,
            # De l'air à gauche et à droite, pas en hauteur : ce panneau
            # s'affiche après chaque `check`, et le gonfler de deux lignes
            # vides coûte plus qu'il ne rend. Premier essai fait, et défait.
            padding=(0, 2),
        )
    )


# ── hint ──────────────────────────────────────────────────────────────────────

def print_hint(index: int, total_hints: int, text: str, cost: int, remaining_cost: int) -> None:
    console.print(
        Panel(
            f"[bold yellow]{_('hint_label', index=index + 1, total=total_hints)}[/bold yellow]\n\n{text}\n\n"
            f"{_('hint_costs', cost=cost, total=remaining_cost)}",
            title=_('hint_panel_title'),
            expand=False,
        )
    )


# ── progress ──────────────────────────────────────────────────────────────────

def print_progress_table(
    labs: list[LabDefinition],
    scores: dict[str, tuple[int, int]],
) -> None:
    """Print a bloc-by-bloc progression summary.

    For each bloc that has at least one lab, shows:
    - number of labs validated / total labs in the bloc
    - average score (best attempts only)
    - whether the challenge is validated
    - whether the capstone is validated
    """
    if not labs:
        console.print(f"[yellow]{_('progress_no_labs')}[/yellow]")
        return

    table = Table(title=_("progress_table_title"), show_lines=True)
    table.add_column(_("col_bloc_num"), justify="left", style="bold")
    table.add_column(_("col_bloc_done"), justify="center")
    table.add_column(_("col_bloc_avg"), justify="center")
    table.add_column(_("col_challenge"), justify="center")
    table.add_column(_("col_capstone"), justify="center")

    def _status(validated: bool | None) -> str:
        if validated is None:
            return "·"
        return _("progress_validated") if validated else _("progress_pending")

    for bloc in build_progress(labs, scores):
        done_text = f"{bloc.validated}/{bloc.total}"
        if bloc.complete:
            done_text = f"[green]{done_text}[/green]"
        elif bloc.started:
            done_text = f"[yellow]{done_text}[/yellow]"
        else:
            done_text = f"[dim]{done_text}[/dim]"

        if bloc.average_pct is None:
            avg_text = _("progress_pending")
        else:
            avg = bloc.average_pct
            avg_color = "green" if avg >= 80 else "yellow" if avg >= 50 else "red"
            avg_text = f"[{avg_color}]{avg} %[/{avg_color}]"

        table.add_row(
            texte_affichable(bloc.label) if bloc.label else "?",
            done_text,
            avg_text,
            _status(bloc.challenge_validated),
            _status(bloc.capstone_validated),
        )

    console.print(table)


# ── scores ────────────────────────────────────────────────────────────────────

def print_scores_table(
    results: list[dict[str, Any]],
    exam_thresholds: dict[str, int] | None = None,
) -> None:
    """Le tableau des scores, et le verdict des labs qui sont des examens.

    ``exam_thresholds`` associe un id de lab à son ``exam_passing_score``. La
    colonne « verdict » n'apparaît que si au moins une ligne en relève : un
    catalogue sans examen n'a pas à porter une colonne de tirets.
    """
    if not results:
        console.print(f"[yellow]{_('no_scores')}[/yellow]")
        return

    seuils = exam_thresholds or {}
    avec_verdict = any(seuils.get(r["lab_id"], 0) > 0 for r in results)

    table = Table(title=_('scores_table_title'), show_lines=True)
    table.add_column(_('col_lab'), style="bold cyan", no_wrap=True)
    table.add_column(_('col_section'), justify="center")
    table.add_column(_('col_score'), justify="center")
    if avec_verdict:
        table.add_column(_('col_verdict'), justify="center")
    table.add_column(_('col_tests'), justify="center")
    table.add_column(_('col_hints'), justify="center")
    table.add_column(_('col_validated_at'))

    for r in results:
        score = r["score"]
        max_s = r["max_score"]
        pct = score / max_s if max_s else 0
        score_color = "green" if pct >= 1.0 else "yellow" if pct >= 0.5 else "red"
        score_text = Text(f"{score}/{max_s}", style=score_color)

        tests = f"{r['passed_tests']}/{r['total_tests']}"
        validated_at = r["validated_at"][:16].replace("T", " ")

        cellules: list[str | Text] = [
            texte_affichable(r["lab_id"]),
            Text(neutraliser(r["section"]), style=_section_color(r["section"])),
            score_text,
        ]
        if avec_verdict:
            cellules.append(_verdict_cell(score, max_s, seuils.get(r["lab_id"], 0)))
        cellules += [tests, str(r["hints_used"]), validated_at]
        table.add_row(*cellules)

    console.print(table)


def _verdict_cell(score: int, max_score: int, passing_score: int) -> Text:
    """« reçu » / « recalé » et le seuil, ou un tiret si le lab n'est pas un examen."""
    verdict = exam_verdict(score, max_score, passing_score)
    if verdict is None:
        return Text("·", style="dim")
    libelle = _("verdict_pass") if verdict else _("verdict_fail")
    return Text(f"{libelle} ({passing_score}%)", style="green" if verdict else "red")


# ── fullhelp ──────────────────────────────────────────────────────────────────

def print_course_list(labs: list[LabDefinition]) -> None:
    """Display a table of all labs with course (scenario.md) availability."""
    table = Table(title=_("course_list_title"), show_lines=True)
    table.add_column(_("course_list_col_id"), style="bold cyan", no_wrap=True)
    table.add_column(_("course_list_col_title"))
    table.add_column(_("col_level"), justify="center")
    table.add_column(_("course_list_col_status"), justify="center")

    for lab in labs:
        has_course = (lab.path / "scenario.md").exists()
        status = Text("✔", style="green") if has_course else Text("✗", style="dim red")
        table.add_row(
            texte_affichable(lab.id),
            texte_affichable(lab.title),
            Text(neutraliser(lab.level), style=_level_color(lab.level)),
            status,
        )

    console.print(table)


def print_course_toc(lab: LabDefinition, manifest: CourseManifest) -> None:
    """Display the table of contents from a course.yaml."""
    table = Table(
        title=_("course_toc_title", title=texte_affichable(manifest.title)),
        show_lines=True,
    )
    table.add_column(_("course_toc_col_n"), style="bold", justify="right", width=4)
    table.add_column(_("course_toc_col_id"), style="cyan", no_wrap=True)
    table.add_column(_("course_toc_col_title"))

    for i, section in enumerate(manifest.sections, 1):
        table.add_row(
            str(i), texte_affichable(section.id), texte_affichable(section.title)
        )

    console.print(table)
    console.print(f"[dim]{_('course_toc_tip', id=texte_affichable(lab.id))}[/dim]")
    if manifest.automatique:
        # Le dire : un sommaire que personne n'a écrit peut tomber à côté du
        # propos, et l'apprenant doit savoir qu'il peut tout voir d'un bloc.
        console.print(
            f"[dim]{_('course_toc_deduit', id=texte_affichable(lab.id))}[/dim]"
        )


def print_course_section(
    lab: LabDefinition,
    section: CourseSection,
    *,
    pos: int = 0,
    total: int = 0,
) -> None:
    """Display a single course section, from its file or from its own text."""
    from rich.markdown import Markdown
    from rich.rule import Rule

    console.print(Rule(
        f"[bold cyan]{texte_affichable(section.id)} — "
        f"{texte_affichable(section.title)}[/bold cyan]"
    ))
    section_file = lab.path / section.file
    # Le contenu porté par la section l'emporte : un découpage déduit des
    # titres du cours n'a pas de fichier à lire.
    if section.contenu is not None:
        console.print(Markdown(section.contenu))
        console.print(Rule())
        _barre_de_navigation(lab, pos, total)
        return
    if section_file.exists():
        text = section_file.read_text(encoding="utf-8")
        # Strip the leading H1 (already shown in the Rule above)
        lines = text.splitlines()
        if lines and lines[0].startswith("# "):
            # Skip the H1 and any immediately following blank line
            start = 1
            while start < len(lines) and lines[start].strip() == "":
                start += 1
            text = "\n".join(lines[start:])
        console.print(Markdown(text))
    else:
        msg = _("course_section_file_missing", file=texte_affichable(section.file))
        console.print(f"[yellow]{msg}[/yellow]")
    console.print(Rule())
    _barre_de_navigation(lab, pos, total)


def _barre_de_navigation(lab: LabDefinition, pos: int, total: int) -> None:
    """Où l'on en est, et les deux gestes pour bouger."""
    if pos <= 0 or total <= 0:
        return
    console.print(f"[dim]{_('course_nav_progress', pos=pos, total=total)}[/dim]")
    gestes: list[str] = []
    if pos > 1:
        gestes.append(_("course_nav_prev", id=texte_affichable(lab.id)))
    if pos < total:
        gestes.append(_("course_nav_next", id=texte_affichable(lab.id)))
    if gestes:
        console.print("[dim]" + "   |   ".join(gestes) + "[/dim]")


def print_course_end(lab: LabDefinition, manifest: CourseManifest) -> None:
    """Display an end-of-course congratulation panel."""
    from rich.panel import Panel

    total = len(manifest.sections)
    body = _("course_end_body", total=total, id=texte_affichable(lab.id))
    console.print(
        Panel(
            body,
            title=_("course_end_title", id=texte_affichable(lab.id)),
            border_style="green",
            padding=(1, 4),
        )
    )


def _localised(base: Path, nom: str, lang: str) -> Path | None:
    """``<nom>.<lang>.md`` s'il existe, sinon ``<nom>.md``, sinon rien."""
    if lang != "en":
        traduit = base / f"{nom}.{lang}.md"
        if traduit.is_file():
            return traduit
    defaut = base / f"{nom}.md"
    return defaut if defaut.is_file() else None


def print_lab_course(lab: LabDefinition, lang: str = "en") -> None:
    """Affiche le cours du lab : le contexte, puis la partie qui enseigne.

    Les deux fichiers sont complémentaires et étaient jusqu'ici traités comme
    des concurrents : ``scenario`` pose la situation en quelques lignes,
    ``README`` explique les commandes et déroule les exercices. Seul le premier
    était affiché, si bien que la partie la plus riche n'était atteignable par
    aucune commande (mesuré : 10 465 lignes de code dans les README d'un seul
    dépôt, exposées par rien). L'apprenant en concluait qu'il n'y avait pas de
    cours, et allait chercher la réponse dans l'énoncé du challenge.
    """
    from rich.markdown import Markdown
    from rich.rule import Rule

    console.print(Rule(f"[bold cyan]{texte_affichable(lab.id)}[/bold cyan]"))
    parties = [
        f for f in (_localised(lab.path, "scenario", lang),
                    _localised(lab.path, "README", lang))
        if f is not None
    ]
    if parties:
        for i, fichier in enumerate(parties):
            if i:
                console.print(Rule(style="dim"))
            console.print(Markdown(fichier.read_text(encoding="utf-8")))
    else:
        msg = _("course_missing")
        console.print(f"[yellow]{msg}[/yellow]")
    console.print(Rule())
    tip = _("course_tip", id=texte_affichable(lab.id))
    console.print(f"[dim]{tip}[/dim]")


#: Les commandes de session, et la clé qui décrit chacune. Le nom de la
#: commande ne se traduit pas : c'est ce que l'apprenant tape. Le sortir des
#: chaînes i18n évite qu'une traduction le déforme, et permet de l'aligner en
#: colonne, ce qu'une phrase complète interdisait : « dsoxlab challenge [<id>]
#: Affiche la mission challenge (challenge/README.md). » se repliait au milieu,
#: et la suite repartait en marge comme si c'était une autre entrée.
_COMMANDES_DE_SESSION = (
    ("dsoxlab course", "lab_welcome_course"),
    ("dsoxlab challenge", "lab_welcome_challenge"),
    ("dsoxlab check", "lab_welcome_check"),
    ("dsoxlab submit", "lab_welcome_submit"),
    ("dsoxlab hint", "lab_welcome_hint"),
)


def print_lab_welcome(lab: LabDefinition) -> None:
    """Le premier écran d'un apprenant : où il atterrit, et quoi taper.

    Il portait dix-huit lignes dont une liste de commandes écrites en phrases,
    qui se repliaient. Les commandes sont désormais une grille à deux colonnes
    que Rich aligne, et le cadre est cyan comme le reste de ce qui se tape :
    le jaune d'avant est la couleur des avertissements dans toute l'interface,
    et un accueil n'en est pas un.
    """
    from rich.console import Group
    from rich.padding import Padding
    from rich.panel import Panel
    from rich.table import Table

    title = _("lab_welcome_title")
    lines = []
    # Dire où l'on atterrit ET où travailler. Sans ces deux lignes, l'apprenant
    # arrive dans un shell à la racine du dépôt sans savoir quel répertoire le
    # concerne : le panneau listait des commandes, jamais un point de départ.
    if lab.runtime.session == "local":
        parts = lab.path.parts
        labdir = (
            "/".join(parts[parts.index("labs"):]) if "labs" in parts else lab.path.name
        )
        lines += [
            _("lab_welcome_session_local"),
            _("lab_welcome_labdir", labdir=labdir),
        ]
        # Un lab piloté depuis le poste peut malgré tout se jouer SUR une
        # machine (cas des labs système). On donne alors la commande de
        # connexion : la taper soi-même fait partie de l'apprentissage, mais
        # deviner le nom d'hôte, non.
        cible = lab.runtime.target()
        if cible is not None:
            lines.append(_("lab_welcome_local_ssh", host=cible.host))
        lines += ["", _("lab_welcome_start_here"), ""]
    elif lab.runtime.type.value in ("vm", "kvm", "incus"):
        # La session s'ouvre en SSH sur la VM, où dsoxlab n'est PAS installé.
        # Sans cet avertissement, le panneau annonce six commandes juste avant
        # de déposer l'apprenant là où aucune ne répond.
        tgt = lab.runtime.target()
        lines += [
            _("lab_welcome_session_target", host=tgt.host if tgt else "?"),
            _("lab_welcome_commands_here"),
        ]

    commandes = Table.grid(padding=(0, 3))
    commandes.add_column(style="bold cyan", no_wrap=True)
    commandes.add_column(overflow="fold")
    for nom, cle in _COMMANDES_DE_SESSION:
        commandes.add_row(nom, _(cle))

    corps = Group(
        *[ligne for ligne in lines if ligne],
        "",
        Padding(commandes, (0, 0, 0, 2)),
        "",
        _("lab_welcome_exit"),
    )
    console.print(
        Panel(corps, title=f"[bold]{title}[/bold]", border_style="cyan")
    )


def print_lab_challenge(lab: LabDefinition, lang: str = "en") -> None:
    """Display the challenge brief (challenge/README.md or README.<lang>.md)."""
    from rich.markdown import Markdown
    from rich.rule import Rule

    localised = lab.path / "challenge" / f"README.{lang}.md"
    challenge_file = (
        localised
        if lang != "en" and localised.exists()
        else lab.path / "challenge" / "README.md"
    )
    console.print(Rule(f"[bold cyan]{texte_affichable(lab.id)} — challenge[/bold cyan]"))
    if challenge_file.exists():
        console.print(Markdown(challenge_file.read_text()))
    else:
        msg = _("challenge_missing")
        console.print(f"[yellow]{msg}[/yellow]")
    console.print(Rule())
    # Le répertoire de travail est celui que le lab DÉCLARE, pas `challenge/`
    # (issue #237). L'écrire en dur annonçait `<lab>/challenge` là où le travail
    # se fait dans `<lab>/challenge/work` : un apprenant a suivi cette ligne, l'a
    # croisée avec un énoncé qui dit « reponses/cours.txt », et a perdu une
    # demi-heure à chercher pourquoi ses fichiers n'étaient pas lus. Mesuré : les
    # mêmes fichiers valent 0/100 à la racine et 100/100 sous le workdir.
    #
    # On teste le RUNTIME, pas la valeur : `workdir` vaut « challenge/work » par
    # DÉFAUT dans le modèle, y compris pour un lab `vm` où le champ est ignoré.
    # Se fier à sa présence annoncerait donc un répertoire local à des labs dont
    # le travail se fait sur la machine, et il n'y a rien à y faire.
    if lab.runtime.type is RuntimeType.SHELL and lab.runtime.workdir:
        workdir = _("challenge_workdir", path=str(lab.path / lab.runtime.workdir))
        console.print(f"[dim]{workdir}[/dim]")


# ── fullhelp ──────────────────────────────────────────────────────────────────

def print_fullhelp() -> None:
    """Affiche le guide complet de la plateforme."""
    from rich.panel import Panel
    from rich.rule import Rule

    sections = [
        ("fullhelp_concept",  None),
        ("fullhelp_workflow", None),
        ("fullhelp_commands", None),
        ("fullhelp_machine",  None),
        ("fullhelp_runtimes", None),
        ("fullhelp_language", None),
        ("fullhelp_scoring",  None),
        ("fullhelp_update",   None),
    ]

    console.print()
    console.print(Panel(
        f"[bold cyan]{_('fullhelp_title')}[/bold cyan]",
        expand=False,
        border_style="bright_blue",
    ))
    console.print()

    for key, _unused in sections:
        console.print(_( key))
        console.print()
        console.print(Rule(style="dim"))
        console.print()
