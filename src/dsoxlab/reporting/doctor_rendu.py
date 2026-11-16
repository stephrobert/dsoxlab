"""Le rendu de ``dsoxlab doctor`` : des étapes numérotées, pas un tableau.

Maquettes validées le 2026-11-16. Trois règles :

- **chaque commande seule sur sa ligne**, jamais dans une cellule : le tableau
  d'avant coupait les commandes longues (Terraform, le pool), qui ne se
  collaient plus ;
- **tous les manques en une passe**, dans l'ordre où les faire ;
- **un résumé à la fin** : combien d'étapes, ou « tout est prêt », puis la
  commande unique.

Les commandes et les détails s'affichent en ``Text`` littéral : une commande
porte des crochets (``[arch=...]``) que Rich lirait comme du balisage.
"""

from __future__ import annotations

import re

from rich.text import Text

from ..i18n import _
from ..services.doctor_controles.modele import STATE_OK, STATE_UNKNOWN, Check, DoctorReport
from ..services.doctor_controles.remedes import TABLE
from ..services.doctor_etapes import Etape, Plan, construire
from .console import console

#: Un détail plus long ne tient pas dans la ligne « Déjà prêt » : on n'y garde
#: que le libellé.
_DETAIL_COURT = 28

#: Une version dans un détail (« git version 2.43.0 », « Terraform v1.16.1 ») :
#: c'est elle qu'on garde dans le résumé, pas la phrase de l'outil.
_VERSION = re.compile(r"(?<![\d.])\d+\.\d+(?:\.\d+)?(?![\d.])")

#: Toujours verts, et sans rien à apprendre : ils encombraient le résumé.
_TAIRE_SI_PRET = frozenset({"shell", "lab_home", "pytest"})


def _compte(cle: str, count: int) -> str:
    """Une phrase au singulier ou au pluriel : la clé ``_1`` porte le singulier."""
    return _(f"{cle}_1") if count == 1 else _(cle, count=count)


def _ligne(texte: str, style: str = "", retrait: int = 0) -> None:
    console.print(Text(" " * retrait + texte, style=style), soft_wrap=True)


def _resume_long(texte: str) -> None:
    """Une ligne de prose : Rich la replie entre les mots, ce n'est pas une commande."""
    console.print(Text(texte, style="dim"))


def _commande(ligne: str) -> None:
    # `soft_wrap` : le terminal replie la ligne s'il le faut, Rich ne la coupe
    # pas. Une commande coupée par un retour à la ligne ne se colle plus.
    console.print(Text("      " + ligne, style="bold"), soft_wrap=True)


def titre_etape(etape: Etape) -> str:
    """Le titre d'une étape : un verbe pour les étapes connues, le composant sinon."""
    if etape.cle in TABLE or etape.cle == "labs":
        return _(f"etape_{etape.cle}")
    return _("etape_reparer", label=etape.controles[0].label)


def _detail(etape: Etape) -> str:
    porteur = next((c for c in etape.controles if c.key == etape.cle), etape.controles[0])
    return porteur.detail


def _entete(report: DoctorReport, plan: Plan) -> None:
    morceaux = ["dsoxlab doctor"]
    if report.catalogue:
        morceaux.append(_("doctor_entete_catalogue", id=report.catalogue))
        morceaux.append(_compte("doctor_entete_labs", report.nb_labs))
    else:
        morceaux.append(_("doctor_entete_sans_catalogue"))
    if report.systeme:
        morceaux.append(report.systeme)
    if report.provider:
        etape = plan.etape_de("provider")
        if report.provider_a_confirmer and etape is not None:
            morceaux.append(_("doctor_entete_provider_a_confirmer",
                              provider=report.provider, step=etape.numero))
        else:
            morceaux.append(_("doctor_entete_provider", provider=report.provider))
    _ligne(" · ".join(morceaux), style="bold")


def _etape(etape: Etape) -> None:
    titre = f"{etape.numero:>2}. {titre_etape(etape)}"
    texte = Text(titre, style="bold")
    if etape.apres is not None:
        texte.append("   " + _("doctor_etape_apres", step=etape.apres), style="dim")
    console.print(texte, soft_wrap=True)
    _ligne(_detail(etape), retrait=4)
    if etape.remede is not None:
        for ligne in etape.remede.lignes:
            _commande(ligne)
        if etape.remede.reconnexion:
            _ligne(_("doctor_etape_reconnexion"), retrait=4)
    else:
        indice = next((c.hint for c in etape.controles if c.hint), None)
        if indice:
            _ligne(indice, retrait=6)


def _resume(check: Check) -> str:
    """Un contrôle vert en quelques mots : son nom, et sa version s'il en a une."""
    version = _VERSION.search(check.detail or "")
    if version is not None:
        return f"{check.label} {version.group(0)}"
    if check.detail and len(check.detail) <= _DETAIL_COURT and check.detail not in check.label:
        return f"{check.label} {check.detail}"
    return check.label


def _resume_court(checks: list[Check]) -> str:
    return " · ".join(_resume(c) for c in checks if c.key not in _TAIRE_SI_PRET)


def _a_savoir(report: DoctorReport) -> None:
    if not report.a_savoir:
        return
    console.print()
    _ligne(_("doctor_a_savoir_titre"), style="bold")
    for check in report.a_savoir:
        _ligne("⚠ " + check.detail, style="yellow", retrait=1)
        if check.hint:
            _ligne(_("doctor_a_savoir_une_machine"), retrait=3)
            _commande(check.hint)


def _facultatifs(report: DoctorReport, plan: Plan) -> None:
    installes = [c for c in report.optional if c.ok]
    if installes:
        _resume_long(_("doctor_facultatif_installe", items=_resume_court(installes)))
    if plan.facultatives:
        noms = ", ".join(e.controles[0].label for e in plan.facultatives)
        _ligne(_("doctor_facultatif_absent", items=noms), style="dim")


def _verbeux(report: DoctorReport) -> None:
    """Chaque contrôle, sa mise en garde éventuelle, et les notes de classement."""
    console.print()
    for check in [*report.required, *report.a_savoir, *report.optional]:
        signe = {STATE_OK: "✔", STATE_UNKNOWN: "?"}.get(check.state, "✘")
        _ligne(f"{signe} {check.label} : {check.detail}")
        if check.mise_en_garde:
            _ligne("⚠ " + check.mise_en_garde, style="yellow", retrait=3)
    for note in report.notes:
        _ligne("ℹ " + note, style="cyan")


def print_doctor(report: DoctorReport, *, verbose: bool = False) -> None:
    """Affiche le diagnostic en étapes, puis ce qui est prêt, puis le résumé."""
    plan = construire(report)
    _entete(report, plan)

    console.print()
    if plan.etapes:
        _ligne(_compte("doctor_n_etapes", len(plan.etapes)), style="bold yellow")
        for etape in plan.etapes:
            console.print()
            _etape(etape)
    _a_savoir(report)

    if plan.etapes or report.a_savoir:
        console.print()
    for check in plan.non_mesures:
        _ligne(_("doctor_non_mesure", label=check.label, detail=check.detail), style="yellow")
    if plan.etapes or plan.non_mesures:
        if plan.prets:
            _resume_long(_("doctor_deja_pret", items=_resume_court(plan.prets)))
    else:
        _ligne(_compte("doctor_tout_pret", len(plan.prets)), style="bold green")
        _resume_long("  " + _resume_court(plan.prets))
    _facultatifs(report, plan)

    if verbose:
        _verbeux(report)
    else:
        mises_en_garde = sum(1 for c in report.required if c.mise_en_garde)
        if mises_en_garde:
            _ligne(_compte("doctor_mises_en_garde", mises_en_garde), style="dim")

    if any(e.lancable for e in plan.etapes):
        console.print()
        _ligne(_("doctor_tout_corriger"), style="bold")
        _commande("dsoxlab doctor --fix")
