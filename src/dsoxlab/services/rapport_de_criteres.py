"""Le rapport structuré d'une exécution de pytest : un résultat par critère.

Jusqu'ici, ``check`` ne savait de pytest que sa sortie TEXTE, et
``echecs_de_tests`` en retrouvait les noms par expressions régulières. Ce module
lit à la place le rapport JSONL qu'écrit le plugin embarqué
(``dsoxlab.rapport_pytest.dsoxlab_rapport``), qui porte pour chaque test le
nodeid complet, la phase et l'origine du message.

Ce lot est INTERNE : le score, ``failed_checks``, ``blocking_failed``,
l'affichage et les codes de sortie restent calculés depuis le texte, comme avant.

``None`` veut dire « inconnu » : rapport absent, tronqué (pas de ligne de fin),
ou illisible. L'appelant garde alors le chemin texte. Un rapport douteux n'est
jamais complété ni réparé : « je n'ai pas pu lire » n'est pas « zéro critère ».
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

#: Nom du module du plugin, tel que ``-p`` le reçoit.
PLUGIN = "dsoxlab_rapport"
#: Variable d'environnement qui donne au plugin le chemin du rapport.
VARIABLE_RAPPORT = "DSOXLAB_RAPPORT"

EtatDeCritere = Literal["satisfied", "unsatisfied", "not_evaluated", "skipped"]
OrigineDeMessage = Literal["author", "technical"]

IDENTIFIANT_MAX = 128
MESSAGE_MAX = 500
MENTION_TEARDOWN = "teardown_error"


@dataclass(frozen=True)
class ResultatDeCritere:
    """Ce qu'un test a dit d'un critère, sous une forme qui se montre.

    ``etat`` : ``satisfied`` (le test a réussi), ``unsatisfied`` (l'assertion a
    échoué dans la phase ``call``), ``not_evaluated`` (le critère n'a pas pu
    être évalué : fixture en erreur ou erreur de collecte, donc une vérification
    BLOQUÉE) ou ``skipped`` (le test a été sauté, par ``skip`` ou ``xfail`` :
    rien n'a été bloqué, le test ne s'applique simplement pas). Aucun des deux
    derniers n'est un échec de l'apprenant, et ils ne se confondent pas.

    ``message_auteur`` n'est renseigné que si ``origine_message`` vaut
    ``author`` : c'est la phrase que l'auteur du lab a écrite. Le texte d'une
    exception technique n'est jamais conservé.

    ``mention`` vaut ``teardown_error`` quand le nettoyage du test a échoué
    alors que le test lui-même était réussi : le critère reste ``satisfied``.
    """

    identifiant: str
    nodeid: str
    phase: str
    etat: EtatDeCritere
    origine_message: OrigineDeMessage | None = None
    message_auteur: str | None = None
    mention: str | None = None


def repertoire_du_plugin() -> Path:
    """Le répertoire à placer en tête de ``PYTHONPATH`` pour charger le plugin."""
    return Path(__file__).resolve().parent.parent / "rapport_pytest"


def environnement_du_plugin(env: dict[str, str], rapport: Path) -> None:
    """Prépare ``env`` pour que pytest charge le plugin et écrive ``rapport``."""
    existant = env.get("PYTHONPATH", "")
    prefixe = str(repertoire_du_plugin())
    env["PYTHONPATH"] = prefixe + (os.pathsep + existant if existant else "")
    env[VARIABLE_RAPPORT] = str(rapport)


def arguments_du_plugin() -> list[str]:
    return ["-p", PLUGIN]


_INTERDIT = re.compile(r"[^\w.:\[\]-]", re.UNICODE)


def assainir(texte: str) -> str:
    normalise = unicodedata.normalize("NFC", texte)
    # `\w` accepte aussi `_` et les lettres/chiffres Unicode : c'est le jeu
    # `[\p{L}\p{N}_.:\[\]-]` attendu côté site.
    return _INTERDIT.sub("_", normalise)


def identifiants_de_criteres(nodeids: list[str]) -> dict[str, str]:
    """Un identifiant stable par nodeid, sans le chemin de fichier.

    Par défaut : le nodeid privé de son chemin de fichier
    (``labs/x/test_a.py::TestC::test_x[p]`` donne ``TestC::test_x[p]``), assaini
    (tout caractère hors lettres, chiffres, ``_ . : [ ] -`` devient ``_``) et
    borné à 128. Deux cas paramétrés distincts restent distincts par leurs
    crochets.

    Collision après retrait du chemin (deux fonctions homonymes dans deux
    fichiers) : on regagne le chemin, en entier, pour TOUS les nodeids du groupe
    en collision, de façon que l'identifiant ne dépende pas de l'ordre
    d'exécution. Si l'assainissement ou la coupe à 128 caractères fait encore
    collisionner, un suffixe ``~<n>`` (rang dans l'ordre des nodeids) départage.
    """
    sans_chemin = {n: assainir(_sans_chemin(n)) for n in nodeids}
    groupes: dict[str, list[str]] = {}
    for nodeid, court in sans_chemin.items():
        groupes.setdefault(court[:IDENTIFIANT_MAX], []).append(nodeid)
    resultat: dict[str, str] = {}
    for court, membres in groupes.items():
        if len(membres) == 1:
            resultat[membres[0]] = court
            continue
        for nodeid in membres:
            resultat[nodeid] = assainir(nodeid)[:IDENTIFIANT_MAX]
    vus: dict[str, int] = {}
    for nodeid in sorted(resultat):
        ident = resultat[nodeid]
        rang = vus.get(ident, 0)
        vus[ident] = rang + 1
        if rang:
            suffixe = f"~{rang}"
            resultat[nodeid] = ident[: IDENTIFIANT_MAX - len(suffixe)] + suffixe
    return resultat


def _sans_chemin(nodeid: str) -> str:
    tete, separateur, reste = nodeid.partition("::")
    return reste if separateur else tete


def lire_rapport(chemin: Path) -> tuple[ResultatDeCritere, ...] | None:
    """Les critères du rapport, ou ``None`` s'il est absent ou douteux."""
    try:
        texte = chemin.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    entrees = _entrees_completes(texte)
    if entrees is None:
        return None
    try:
        return _agreger(entrees)
    except (KeyError, TypeError, ValueError):
        return None


def _entrees_completes(texte: str) -> list[dict[str, Any]] | None:
    """Les lignes ``phase``, si le rapport a son début ET sa fin, sinon ``None``.

    Une ligne illisible, un genre inconnu ou l'absence de la ligne de fin (pytest
    interrompu) rendent tout le rapport douteux : on ne le répare pas.
    """
    entrees: list[dict[str, Any]] = []
    genres: set[str] = set()
    for ligne in texte.splitlines():
        if not ligne.strip():
            continue
        entree = _ligne_json(ligne)
        genre = None if entree is None else entree.get("t")
        if genre not in ("debut", "fin", "phase"):
            return None
        genres.add(genre)
        if genre == "phase" and entree is not None:
            entrees.append(entree)
    return entrees if {"debut", "fin"} <= genres else None


def _ligne_json(ligne: str) -> dict[str, Any] | None:
    try:
        entree = json.loads(ligne)
    except ValueError:
        return None
    return entree if isinstance(entree, dict) else None


def _agreger(entrees: list[dict[str, Any]]) -> tuple[ResultatDeCritere, ...]:
    ordre: list[str] = []
    phases: dict[str, dict[str, dict[str, Any]]] = {}
    for entree in entrees:
        nodeid = str(entree["nodeid"])
        phase = str(entree["phase"])
        if nodeid not in phases:
            phases[nodeid] = {}
            ordre.append(nodeid)
        phases[nodeid][phase] = entree
    identifiants = identifiants_de_criteres(ordre)
    return tuple(_un_critere(n, identifiants[n], phases[n]) for n in ordre)


def _un_critere(
    nodeid: str, identifiant: str, phases: dict[str, dict[str, Any]]
) -> ResultatDeCritere:
    if "collect" in phases:
        return ResultatDeCritere(identifiant, nodeid, "collect", "not_evaluated")
    setup = phases.get("setup")
    if setup is not None and setup["issue"] == "skipped":
        # `mark.skip` / `skipif` jouent en phase setup : le test ne s'applique pas.
        return ResultatDeCritere(identifiant, nodeid, "setup", "skipped")
    if setup is not None and setup["issue"] != "passed":
        # Une fixture en erreur : la vérification n'a pas pu avoir lieu.
        return ResultatDeCritere(identifiant, nodeid, "setup", "not_evaluated")
    appel = phases.get("call")
    teardown = phases.get("teardown")
    teardown_rate = teardown is not None and teardown["issue"] == "failed"
    mention = MENTION_TEARDOWN if teardown_rate else None
    if appel is None:
        return ResultatDeCritere(
            identifiant, nodeid, "teardown", "not_evaluated", mention=mention
        )
    if appel["issue"] == "failed":
        origine, message = _origine_et_message(appel)
        return ResultatDeCritere(
            identifiant, nodeid, "call", "unsatisfied", origine, message, mention
        )
    if appel["issue"] == "skipped":
        return ResultatDeCritere(
            identifiant, nodeid, "call", "skipped", mention=mention
        )
    return ResultatDeCritere(identifiant, nodeid, "call", "satisfied", mention=mention)


def _origine_et_message(
    entree: dict[str, Any],
) -> tuple[OrigineDeMessage | None, str | None]:
    if entree.get("origine") == "author":
        message = entree.get("message")
        if isinstance(message, str) and message.strip():
            return "author", message.strip()[:MESSAGE_MAX]
        return "author", None
    return "technical", None


def nom_de_controle(identifiant: str) -> str:
    """Le nom d'un critère au format de ``failed_checks`` : la fonction, sans cas.

    ``TestC::test_x[p-1]`` donne ``test_x``. Un critère de collecte, qui n'a pas
    de ``::``, garde son identifiant entier. Sert aussi sur un nodeid complet :
    ``labs/x/test_a.py::TestC::test_x[p-1]`` donne ``test_x``.
    """
    dernier = identifiant.rsplit("::", 1)[-1]
    return dernier.split("[", 1)[0] or identifiant


def _etat_du_groupe(etats: list[str]) -> EtatDeCritere:
    """L'état d'un critère déclaré qui regroupe plusieurs tests.

    Satisfait seulement si TOUS le sont ; non satisfait dès qu'un seul ne l'est
    pas ; non évalué si l'un est bloqué et qu'aucun n'est non satisfait ; sauté
    si tous sont sautés. Un mélange de satisfaits et de sautés n'est pas
    « satisfait » (une partie de la preuve n'a pas eu lieu) : il vaut ``skipped``.
    """
    if "unsatisfied" in etats:
        return "unsatisfied"
    if "not_evaluated" in etats:
        return "not_evaluated"
    if all(etat == "satisfied" for etat in etats):
        return "satisfied"
    return "skipped"


def _critere_declare(
    identifiant: str, membres: list[ResultatDeCritere]
) -> ResultatDeCritere:
    etat = _etat_du_groupe([m.etat for m in membres])
    determinant = next((m for m in membres if m.etat == etat), membres[0])
    mention = next((m.mention for m in membres if m.mention), None)
    origine: OrigineDeMessage | None = None
    message: str | None = None
    if etat == "unsatisfied":
        origine, message = determinant.origine_message, determinant.message_auteur
    return ResultatDeCritere(
        identifiant, determinant.nodeid, determinant.phase, etat, origine, message, mention
    )


def regrouper_par_declaration(
    criteres: tuple[ResultatDeCritere, ...] | None,
    declarations: list[tuple[str, tuple[str, ...]]],
) -> tuple[ResultatDeCritere, ...] | None:
    """Regroupe les tests d'un critère DÉCLARÉ sous son ``id`` ; le reste, intact.

    ``declarations`` : ``(id, noms de fonction de test)``. Un test qui appartient
    à un critère déclaré perd son identifiant par défaut au profit de l'``id``
    déclaré, à la place du premier de ses membres. Un critère déclaré dont aucun
    test n'a tourné (rien de collecté) n'apparaît pas : on ne conclut rien sur ce
    qu'on n'a pas vu. ``None`` (rapport inconnu) reste ``None``.

    Si un identifiant déclaré rejoint celui d'un test non déclaré, ce dernier
    prend un suffixe ``~n`` : deux critères ne partagent jamais un identifiant.
    """
    if criteres is None or not declarations:
        return criteres
    appartenance = {nom: ident for ident, noms in declarations for nom in noms}
    groupes: dict[str, list[ResultatDeCritere]] = {}
    ordre: list[str | ResultatDeCritere] = []
    for critere in criteres:
        declare = appartenance.get(nom_de_controle(critere.nodeid))
        if declare is None or critere.phase == "collect":
            ordre.append(critere)
        else:
            if declare not in groupes:
                groupes[declare] = []
                ordre.append(declare)
            groupes[declare].append(critere)
    resultat: list[ResultatDeCritere] = []
    pris = set(groupes)
    for element in ordre:
        if isinstance(element, str):
            resultat.append(_critere_declare(element, groupes[element]))
            continue
        ident = element.identifiant
        rang = 0
        while ident in pris:
            rang += 1
            suffixe = f"~{rang}"
            ident = element.identifiant[: IDENTIFIANT_MAX - len(suffixe)] + suffixe
        pris.add(ident)
        resultat.append(
            element if ident == element.identifiant else _renomme(element, ident)
        )
    return tuple(resultat)


def _renomme(critere: ResultatDeCritere, identifiant: str) -> ResultatDeCritere:
    return ResultatDeCritere(
        identifiant, critere.nodeid, critere.phase, critere.etat,
        critere.origine_message, critere.message_auteur, critere.mention,
    )
