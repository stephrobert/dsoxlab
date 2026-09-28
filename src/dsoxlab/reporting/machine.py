"""Sorties JSON, destinées aux programmes et non aux yeux.

Toute intégration — extension d'éditeur, tableau de bord web, script de suivi —
a besoin de lire l'état du catalogue et de la progression. Sans ce module, elle
devrait analyser la sortie Rich : des tableaux dont la largeur dépend du
terminal, des couleurs, des retours à la ligne. Le moindre ajustement
d'affichage casserait l'intégration, et l'affichage est fait pour bouger.

Trois règles tiennent ce contrat :

1. **Rien d'autre que du JSON sur la sortie standard.** En mode machine, les
   messages d'ambiance (contexte actif, astuces) sont tus : un « ℹ » en tête de
   flux rendrait le document illisible pour l'appelant.
2. **Le format est versionné.** Chaque document porte un ``schema``, pour qu'un
   consommateur sache s'il parle la même langue avant de lire le reste.
3. **Un verdict se lit sans traduire.** Un contrôle porte une **clé** stable et
   un **état** en jeton (``ok``, ``failed``…), et seulement *ensuite* un libellé
   traduit. Recopier le texte affiché dans un champ rendrait l'interface
   inutilisable tout en paraissant complète : personne ne peut savoir si c'est
   vert ou rouge sans analyser du français ou de l'anglais.

Le mode machine ne change **jamais** le verdict ni le code de retour d'une
commande : il en change la forme. Un ``check`` en échec sort en 1 avec ou sans
``--json``, et une erreur dure (lab inconnu, ``meta.yml`` illisible) laisse la
sortie standard vide, dit pourquoi sur la sortie d'erreur, et garde son code.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..i18n import _
from ..models.lab import LabDefinition

if TYPE_CHECKING:  # pragma: no cover - imports de typage seulement
    from ..services.doctor import Check, DoctorReport

#: Version du format. À incrémenter dès qu'un champ change de sens ou disparaît
#: — un ajout de champ, lui, reste compatible.
SCHEMA = 1


def emit(payload: dict[str, Any]) -> None:
    """Écrit un document JSON sur la sortie standard, et rien d'autre."""
    json.dump({"schema": SCHEMA, **payload}, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def lab_dict(
    lab: LabDefinition, score: tuple[int, int] | None = None
) -> dict[str, Any]:
    """Représentation d'un lab : ce qu'une interface a besoin de savoir.

    Le chemin est absolu et le ``doc_url`` conservé : une extension d'éditeur
    doit pouvoir ouvrir les fichiers du lab et le guide en ligne sans avoir à
    reconstruire quoi que ce soit.
    """
    target = lab.runtime.target()
    return {
        "id": lab.id,
        "title": lab.title,
        "section": lab.section,
        # Les blocs pédagogiques : la CLI trie dessus, une interface qui ne les
        # voit pas ne peut que regrouper par « section », laquelle vaut
        # repo.category par défaut. Mesuré : 84 labs sous une section unique
        # côté linux-dsoxlab-training, donc un seul nœud illisible.
        "bloc": lab.bloc or None,
        "bloc_order": lab.bloc_order or None,
        "level": lab.level,
        "type": lab.lab_type,
        # Le seuil de réussite d'un examen blanc, en pourcentage du barème.
        # `or None` comme les autres champs facultatifs : un lab ordinaire n'en
        # déclare pas, et 0 se lirait comme « réussi d'office ».
        "exam_passing_score": lab.exam_passing_score or None,
        "difficulty": lab.difficulty or None,
        "estimated_time": lab.estimated_time or None,
        "skills": list(lab.skills),
        "distros": list(lab.distros),
        "doc_url": lab.doc_url,
        "path": str(lab.path),
        "runtime": {
            "type": lab.runtime.type.value,
            "session": lab.runtime.session,
            "target": target.host if target else None,
            "workdir": lab.runtime.workdir,
        },
        # (obtenu, maximum) plutôt qu'un pourcentage : l'appelant décide de sa
        # présentation, et un lab jamais tenté se distingue d'un lab à zéro.
        "best_score": None if score is None else {"points": score[0], "max": score[1]},
    }


def check_dict(check: Check) -> dict[str, Any]:
    """Un contrôle de ``doctor``, tel qu'un tableau de bord doit le lire.

    ``key`` et ``state`` sont les deux champs qui décident : ils ne bougent ni
    avec la langue, ni avec le tableau où le contrôle est rangé. ``label`` et
    ``detail`` sont là pour être affichés à un humain, jamais comparés.
    """
    return {
        "key": check.key,
        "state": check.state,
        "ok": check.ok,
        "label": check.label,
        "detail": check.detail,
        # Deux remédiations, deux natures : ``fix`` est un correctif que
        # ``--fix`` sait jouer (token par token, sans shell), ``hint`` une
        # consigne que seul un humain pose. Les fondre en un champ ferait
        # exécuter une URL. Le correctif est rendu sous sa forme lisible,
        # accompagnée de sa catégorie : c'est elle qui dit à un appelant si
        # le geste est automatisable, manuel, ou à effet différé.
        "fix": None if check.fix is None else check.fix.display,
        "fix_kind": None if check.fix is None else check.fix.kind.value,
        "hint": check.hint,
    }


def doctor_dict(report: DoctorReport) -> dict[str, Any]:
    """Le diagnostic entier, verdict d'abord.

    ``ok`` porte sur le **requis** seul, comme le classement de ``doctor``
    l'affirme déjà : un hyperviseur que ce dépôt n'utilise pas n'a pas à peindre
    en rouge un poste qui va très bien.
    """
    return {
        "ok": not report.failing(),
        "required": [check_dict(c) for c in report.required],
        "informational": [check_dict(c) for c in report.optional],
        # Traduites, et c'est assumé : une note explique *pourquoi* un composant
        # est informatif ici. Rien ne s'y décide, donc rien n'a à s'y comparer.
        "notes": list(report.notes),
    }


def _valeur(brute: Any) -> Any:
    """Une valeur de paramètre, ramenée à ce que JSON sait porter.

    Les validators mettent dans ``params`` ce qu'ils ont sous la main, y compris
    un ``Path`` ou l'exception qui a fait échouer une requête HTTP. Les rendre
    tels quels lèverait au ``json.dump``, c'est-à-dire après que la commande a
    fait tout son travail.
    """
    if brute is None or isinstance(brute, bool | int | float | str):
        return brute
    return str(brute)


def issue_dict(
    kind: str,
    key: str,
    params: dict[str, Any],
    *,
    lab: str | None = None,
    path: Path | None = None,
    field: str | None = None,
) -> dict[str, Any]:
    """Une anomalie de ``validate-structure``, identifiée par sa règle.

    ``kind`` dit quelle famille de contrôle a parlé, ``key`` **quelle règle** :
    c'est l'identité stable de l'anomalie, celle sur laquelle une intégration
    filtre, compte et compare. ``message`` est la même chose dite à un humain,
    dans sa langue, et n'a pas à être analysé pour cela.
    """
    return {
        "kind": kind,
        "key": key,
        "params": {nom: _valeur(valeur) for nom, valeur in params.items()},
        "message": _(key, **params),
        "lab": lab,
        "path": None if path is None else str(path),
        "field": field,
    }


def export_result_dict(
    row: dict[str, Any],
    lab: LabDefinition | None,
    catalog_id: str,
) -> dict[str, Any]:
    """Une ligne de l'export : un résultat qui dit lui-même ce qu'il vaut.

    Trois différences avec :func:`score_dict`, et chacune répond à une chose
    qu'un consommateur devait deviner.

    ``validated`` est **explicite**. Une tentative mesurée mais ratée est
    inscrite elle aussi — c'est voulu, un échec fait partie de l'historique —
    et le champ de la base s'appelle pourtant ``validated_at``. Le lecteur
    devait donc déduire la validation de ``passed_tests == total_tests``, règle
    qui n'était écrite nulle part. Elle l'est ici, une fois, et le document
    porte le verdict.

    ``catalog`` et ``lab_type`` sont **joints**. Les identifiants de labs sont
    distincts d'un catalogue à l'autre aujourd'hui, mais aucun contrat ne le
    garantit, et un consommateur qui fusionne plusieurs catalogues ne peut pas
    s'appuyer là-dessus. Quant au type, il décide si la ligne se range en
    pratique (``lab``) ou en preuve (``challenge``, ``capstone``) : le joindre
    depuis son propre catalogue ne marche que tant que les versions coïncident.

    ``attempted_at`` plutôt que ``validated_at`` : l'horodatage dit quand
    l'apprenant a tenté, pas que sa tentative vaut validation. Le nom ne
    préjuge plus du verdict, et le verdict a son champ.

    ``lab_type`` vaut ``null`` quand le lab n'existe plus dans le catalogue —
    renommé, déplacé, supprimé. Le résultat reste exporté : il a eu lieu.
    """
    from ..services.progress_service import exam_percentage, exam_verdict

    passing_score = lab.exam_passing_score if lab and lab.exam_passing_score else None
    verdict = exam_verdict(row["score"], row["max_score"], passing_score or 0)
    return {
        "catalog": catalog_id,
        "lab_id": row["lab_id"],
        "lab_type": lab.lab_type if lab else None,
        "section": row["section"],
        # La règle, écrite une fois : tous les tests passés, et au moins un
        # test joué. Sans la seconde moitié, un lab dont rien n'a pu tourner
        # serait « validé » à 0 sur 0.
        "validated": row["total_tests"] > 0
        and row["passed_tests"] == row["total_tests"],
        "score": row["score"],
        "max_score": row["max_score"],
        "passed_tests": row["passed_tests"],
        "total_tests": row["total_tests"],
        "hints_used": row["hints_used"],
        "attempted_at": row["validated_at"],
        "exam": None if verdict is None else {
            "passing_score": passing_score,
            "percentage": exam_percentage(row["score"], row["max_score"]),
            "passed": verdict,
        },
    }


def score_dict(row: dict[str, Any], passing_score: int | None) -> dict[str, Any]:
    """Une note de l'historique, et le verdict quand le lab est un examen.

    ``exam`` vaut ``null`` sur un lab ordinaire : il n'y a pas de seuil, donc
    pas de verdict à rendre. Un ``false`` s'y lirait comme un échec.
    """
    from ..services.progress_service import exam_percentage, exam_verdict

    verdict = exam_verdict(row["score"], row["max_score"], passing_score or 0)
    return {
        "lab_id": row["lab_id"],
        "section": row["section"],
        "score": row["score"],
        "max_score": row["max_score"],
        "passed_tests": row["passed_tests"],
        "total_tests": row["total_tests"],
        "hints_used": row["hints_used"],
        "validated_at": row["validated_at"],
        "exam": None if verdict is None else {
            "passing_score": passing_score,
            "percentage": exam_percentage(row["score"], row["max_score"]),
            "passed": verdict,
        },
    }
