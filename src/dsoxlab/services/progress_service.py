"""Agrégation de la progression pédagogique : où en est l'apprenant.

Ce module ne contient que du calcul. Il ne sait ni afficher, ni traduire : il
rend des structures typées que n'importe quelle couche de présentation (table
Rich, TUI, export JSON) peut consommer.

Cette logique vivait auparavant dans ``reporting/console.py`` et dans la
commande ``next`` de ``cli.py``. Elle y était mêlée à du markup Rich et à des
``typer.Exit``, donc impossible à réutiliser ailleurs et impossible à tester
sans capturer une sortie terminal.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models.lab import LabDefinition

# Ordre pédagogique des types de lab : on apprend (lab), puis on se confronte
# (challenge), puis on synthétise (capstone). Un type inconnu passe en dernier
# plutôt que de faire échouer le tri.
_TYPE_ORDER = {"lab": 0, "challenge": 1, "capstone": 2}
_TYPE_ORDER_UNKNOWN = 3


@dataclass(frozen=True)
class BlocProgress:
    """Avancement d'un bloc pédagogique.

    ``average_pct`` vaut None tant qu'aucun lab du bloc n'est validé : c'est
    « pas encore commencé », ce qui ne veut pas dire zéro. De même,
    ``challenge_validated`` et ``capstone_validated`` valent None quand le bloc
    n'en déclare pas : distinguer « absent » de « non validé » évite d'afficher
    un échec là où il n'y a simplement rien à faire.
    """

    bloc: int
    label: str
    validated: int
    total: int
    average_pct: int | None
    challenge_validated: bool | None
    capstone_validated: bool | None

    @property
    def complete(self) -> bool:
        """Tous les labs simples du bloc sont validés (et il y en a au moins un)."""
        return self.total > 0 and self.validated == self.total

    @property
    def started(self) -> bool:
        return self.validated > 0


def pedagogical_sort_key(lab: LabDefinition) -> tuple[int, int, int, str]:
    """Ordre dans lequel un apprenant doit rencontrer les labs.

    Bloc, puis type (lab → challenge → capstone), puis ordre déclaré dans le
    ``meta.yml``, puis l'id pour rendre le tri déterministe à rang égal.
    """
    type_order = _TYPE_ORDER.get(lab.lab_type, _TYPE_ORDER_UNKNOWN)
    return (lab.bloc, type_order, lab.bloc_order, lab.id)


def build_progress(
    labs: list[LabDefinition],
    scores: dict[str, tuple[int, int]],
) -> list[BlocProgress]:
    """Agrège la progression bloc par bloc.

    ``scores`` est le retour de ``get_best_scores`` : ``{lab_id: (score,
    max_score)}``. Un lab absent de ce dict n'a jamais été validé.
    """
    blocs: dict[int, list[LabDefinition]] = {}
    for lab in labs:
        blocs.setdefault(lab.bloc, []).append(lab)

    progress: list[BlocProgress] = []
    for bloc_num in sorted(blocs):
        bloc_labs = sorted(blocs[bloc_num], key=lambda lab: lab.bloc_order)
        plain = [lab for lab in bloc_labs if lab.lab_type == "lab"]
        challenges = [lab for lab in bloc_labs if lab.lab_type == "challenge"]
        capstones = [lab for lab in bloc_labs if lab.lab_type == "capstone"]

        validated = [lab for lab in plain if lab.id in scores]

        # Moyenne des pourcentages des seuls labs validés. Un lab dont le
        # max_score serait 0 (contrat incomplet) compte pour 0 % au lieu de
        # lever une ZeroDivisionError sur la commande de progression.
        average_pct: int | None = None
        if validated:
            total_pct = sum(
                int(scores[lab.id][0] * 100 / scores[lab.id][1]) if scores[lab.id][1] else 0
                for lab in validated
            )
            average_pct = total_pct // len(validated)

        # Nom lisible du bloc (titre de section du meta.yml). Un lab rattaché à
        # aucune section ne porte pas de nom : on retombe sur le numéro.
        bloc_name = next((lab.bloc_name for lab in bloc_labs if lab.bloc_name), "")

        progress.append(
            BlocProgress(
                bloc=bloc_num,
                label=bloc_name or (str(bloc_num) if bloc_num else ""),
                validated=len(validated),
                total=len(plain),
                average_pct=average_pct,
                challenge_validated=(challenges[0].id in scores) if challenges else None,
                capstone_validated=(capstones[0].id in scores) if capstones else None,
            )
        )
    return progress


def next_pending_lab(
    labs: list[LabDefinition],
    scores: dict[str, tuple[int, int]],
) -> LabDefinition | None:
    """Le premier lab non validé dans l'ordre pédagogique, ou None si tout est fait.

    « Non validé » signifie absent de ``scores`` : un lab noté, même
    partiellement, est considéré comme passé. Refaire un lab pour améliorer son
    score reste possible, mais ce n'est plus l'étape *suivante*.
    """
    for lab in sorted(labs, key=pedagogical_sort_key):
        if lab.id not in scores:
            return lab
    return None
