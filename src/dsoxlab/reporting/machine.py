"""Sorties JSON, destinées aux programmes et non aux yeux.

Toute intégration — extension d'éditeur, tableau de bord web, script de suivi —
a besoin de lire l'état du catalogue et de la progression. Sans ce module, elle
devrait analyser la sortie Rich : des tableaux dont la largeur dépend du
terminal, des couleurs, des retours à la ligne. Le moindre ajustement
d'affichage casserait l'intégration, et l'affichage est fait pour bouger.

Deux règles tiennent ce contrat :

1. **Rien d'autre que du JSON sur la sortie standard.** En mode machine, les
   messages d'ambiance (contexte actif, astuces) sont tus : un « ℹ » en tête de
   flux rendrait le document illisible pour l'appelant.
2. **Le format est versionné.** Chaque document porte un ``schema``, pour qu'un
   consommateur sache s'il parle la même langue avant de lire le reste.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from ..models.lab import LabDefinition

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
        "level": lab.level,
        "type": lab.lab_type,
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
