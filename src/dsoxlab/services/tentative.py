"""Ce qu'une tentative consigne, et comment cela se relit.

Lot B de l'issue #336 (0.8.0). Chaque `check` enregistré porte, en plus de son
score : un identifiant propre, l'empreinte du lab tel qu'il était, la révision
du catalogue, un résultat par critère et les indices vus. Tout est calculé ICI,
une fois, au moment de l'enregistrement, pour que l'export (lot C) n'ait qu'à
relire.

Deux règles tiennent l'ensemble :

- **Rien de technique ne se consigne.** Les critères ne portent que ce que
  `ResultatDeCritere` autorise : le message de l'AUTEUR du lab, jamais le texte
  d'une exception.
- **NULL veut dire inconnu.** Une ligne écrite avant 0.8.0, ou un check sans
  rapport lisible, laisse la colonne à NULL : on ne devine pas.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..models.hint import HintFile
from ..models.lab import LabDefinition
from .rapport_de_criteres import IDENTIFIANT_MAX, ResultatDeCritere, nom_de_controle

#: Longueur de l'empreinte du lab, en caractères hexadécimaux.
LONGUEUR_EMPREINTE = 16

_EXCLUS = frozenset({"__pycache__", ".pytest_cache"})


def nouvel_identifiant() -> str:
    """L'identifiant d'une tentative : un uuid4, jamais déduit de rien."""
    return str(uuid.uuid4())


def _fichiers_des_tests(tests: Path) -> list[Path]:
    if not tests.is_dir():
        return []
    return sorted(
        (
            p for p in tests.rglob("*")
            if p.is_file()
            and not (_EXCLUS & set(p.relative_to(tests).parts))
            and p.suffix != ".pyc"
        ),
        key=lambda p: p.relative_to(tests).as_posix(),
    )


def empreinte_du_lab(lab: LabDefinition) -> str:
    """L'empreinte du lab : `lab.yaml`, `challenge/tests/**` et `hints.yaml`.

    SHA-256 tronqué à 16 hexadécimaux, indépendante de git : elle se calcule sur
    le contenu des fichiers, donc sur un catalogue copié ou modifié à la main
    comme sur un dépôt propre. Les fichiers sont lus dans l'ordre trié de leur
    chemin relatif, et le chemin entre dans le calcul : renommer un test change
    l'empreinte, déplacer un lab entier non. Les caches (`__pycache__`,
    `.pytest_cache`) n'y entrent pas : pytest les écrit à chaque exécution.

    Un fichier illisible compte comme absent plutôt que de faire lever le check.
    """
    h = hashlib.sha256()
    fichiers: list[tuple[str, Path]] = [("lab.yaml", lab.path / "lab.yaml")]
    tests = lab.path / "challenge" / "tests"
    fichiers += [
        ("tests/" + p.relative_to(tests).as_posix(), p) for p in _fichiers_des_tests(tests)
    ]
    fichiers.append(("hints.yaml", lab.path / "challenge" / "hints.yaml"))
    for nom, chemin in fichiers:
        try:
            contenu = chemin.read_bytes()
        except OSError:
            continue
        h.update(nom.encode("utf-8") + b"\0" + contenu + b"\0")
    return h.hexdigest()[:LONGUEUR_EMPREINTE]


def criteres_en_json(criteres: tuple[ResultatDeCritere, ...] | None) -> str | None:
    """Les critères sous forme compacte pour la base ; ``None`` reste inconnu."""
    if criteres is None:
        return None
    return json.dumps(
        [
            {
                "id": c.identifiant,
                "state": c.etat,
                "phase": c.phase,
                "mention": c.mention,
                "origin": c.origine_message,
                "author_message": c.message_auteur,
            }
            for c in criteres
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def indices_vus_en_json(demandes: list[dict[str, Any]], hints: HintFile) -> str:
    """Les indices demandés pour ce lab, tels qu'ils étaient au check.

    `reset_hints` efface `hint_requests` : cette copie sur la ligne est ce qui
    permet de dire plus tard qu'une réussite a été assistée. `id` est lu dans
    `hints.yaml` quand il existe, `criterion` vaut `null` tant qu'aucun indice
    ne se rattache à un critère.
    """
    vus: list[dict[str, Any]] = []
    for demande in demandes:
        index = int(demande["hint_index"])
        identifiant = hints.hints[index].id if 0 <= index < len(hints.hints) else None
        vus.append({"index": index, "id": identifiant, "criterion": None})
    return json.dumps(vus, ensure_ascii=False, separators=(",", ":"))


# ── relecture, pour l'export ─────────────────────────────────────────────────

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_EMPREINTE = re.compile(rf"[0-9a-f]{{{LONGUEUR_EMPREINTE}}}")
_REVISION = re.compile(r"[0-9a-f]{7,64}")
_JETON = re.compile(r"[\w.:\[\]-]{1,%d}" % IDENTIFIANT_MAX)  # noqa: UP031
_ETATS = frozenset({"satisfied", "unsatisfied", "not_evaluated", "skipped"})
_PHASES = frozenset({"setup", "call", "teardown", "collect"})


def _texte_valide(valeur: object, motif: re.Pattern[str]) -> str | None:
    return valeur if isinstance(valeur, str) and motif.fullmatch(valeur) else None


def identifiant_de_ligne(row: Mapping[str, Any]) -> str | None:
    return _texte_valide(row.get("attempt_id"), _UUID)


def empreinte_de_ligne(row: Mapping[str, Any]) -> str | None:
    return _texte_valide(row.get("lab_digest"), _EMPREINTE)


def revision_de_ligne(row: Mapping[str, Any]) -> str | None:
    return _texte_valide(row.get("catalog_revision"), _REVISION)


def _json_de_colonne(row: Mapping[str, Any], colonne: str) -> list[Any] | None:
    brut = row.get(colonne)
    if not isinstance(brut, str):
        return None
    try:
        valeur = json.loads(brut)
    except ValueError:
        return None
    return valeur if isinstance(valeur, list) else None


def criteres_de_ligne(row: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    """Les critères d'une ligne, validés un par un ; ``None`` si inconnus.

    Une base qu'un humain a retouchée traverse la frontière de confiance à
    l'export : un critère dont l'identifiant, l'état ou la phase sort du jeu
    attendu est écarté, jamais recopié tel quel.
    """
    brutes = _json_de_colonne(row, "criteria")
    if brutes is None:
        return None
    propres: list[dict[str, Any]] = []
    for brut in brutes:
        if not isinstance(brut, dict):
            continue
        identifiant = _texte_valide(brut.get("id"), _JETON)
        if identifiant is None or brut.get("state") not in _ETATS:
            continue
        phase = brut.get("phase")
        mention = brut.get("mention")
        message = brut.get("author_message")
        propres.append({
            "id": identifiant,
            "state": brut["state"],
            "phase": phase if phase in _PHASES else None,
            "mention": _texte_valide(mention, _JETON),
            "author_message": message if isinstance(message, str) and message else None,
        })
    return propres


def indices_de_ligne(row: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    brutes = _json_de_colonne(row, "hints_seen")
    if brutes is None:
        return None
    propres: list[dict[str, Any]] = []
    for brut in brutes:
        if not isinstance(brut, dict) or isinstance(brut.get("index"), bool):
            continue
        index = brut.get("index")
        if not isinstance(index, int) or index < 0:
            continue
        identifiant = brut.get("id")
        critere = brut.get("criterion")
        propres.append({
            "index": index,
            "id": _texte_valide(identifiant, _JETON),
            "criterion": _texte_valide(critere, _JETON),
        })
    return propres


__all__ = [
    "criteres_de_ligne",
    "criteres_en_json",
    "empreinte_de_ligne",
    "empreinte_du_lab",
    "identifiant_de_ligne",
    "indices_de_ligne",
    "indices_vus_en_json",
    "nom_de_controle",
    "nouvel_identifiant",
    "revision_de_ligne",
]
