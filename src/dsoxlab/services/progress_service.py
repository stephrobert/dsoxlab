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


def exam_percentage(score: int, max_score: int) -> int:
    """Le score, ramené au pourcentage du barème. ``0`` si le barème est nul.

    Un barème à zéro n'est pas une réussite parfaite : c'est un contrat
    incomplet, et il vaut 0 % comme il vaut 0 point dans :func:`compute_score`.
    """
    if max_score <= 0:
        return 0
    return score * 100 // max_score


def exam_verdict(score: int, max_score: int, passing_score: int) -> bool | None:
    """Le lab est-il réussi au sens de son ``exam_passing_score`` ?

    Rend ``None`` quand le lab ne déclare pas de seuil : la très grande
    majorité des labs, qui ne sont pas des examens. ``None`` n'est pas un
    échec, et distinguer les deux est tout l'intérêt de cette fonction — un
    lab ordinaire ne doit jamais s'afficher « recalé ».

    La comparaison est faite en entiers, sans passer par un pourcentage
    arrondi : à 69,5 % d'un barème, l'arrondi rendrait 70 et déclarerait reçu
    un apprenant qui ne l'est pas. Un seuil d'examen ne s'arrondit pas en
    faveur du candidat.
    """
    if passing_score <= 0:
        return None
    if max_score <= 0:
        return False
    return score * 100 >= passing_score * max_score


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
    return [_resumer_un_bloc(numero, blocs[numero], scores) for numero in sorted(blocs)]


def _moyenne_des_valides(
    valides: list[LabDefinition], scores: dict[str, tuple[int, int]]
) -> int | None:
    """La moyenne des pourcentages des seuls labs validés.

    Un lab dont le `max_score` vaut 0, cas d'un contrat incomplet, compte pour
    0 % au lieu de lever une `ZeroDivisionError` au milieu de la commande de
    progression. Aucun lab validé ne donne `None`, qui se distingue de 0 % :
    « rien tenté » n'est pas « tout raté ».
    """
    if not valides:
        return None
    total = sum(
        int(scores[lab.id][0] * 100 / scores[lab.id][1]) if scores[lab.id][1] else 0
        for lab in valides
    )
    return total // len(valides)


def _resumer_un_bloc(
    numero: int,
    labs_du_bloc: list[LabDefinition],
    scores: dict[str, tuple[int, int]],
) -> BlocProgress:
    """Ce qu'un bloc vaut : ses labs notés, son challenge, son capstone."""
    ordonnes = sorted(labs_du_bloc, key=lambda lab: lab.bloc_order)
    par_type: dict[str, list[LabDefinition]] = {"lab": [], "challenge": [], "capstone": []}
    for lab in ordonnes:
        par_type.setdefault(lab.lab_type, []).append(lab)

    notes = par_type["lab"]
    valides = [lab for lab in notes if lab.id in scores]
    challenges = par_type["challenge"]
    capstones = par_type["capstone"]

    # Nom lisible du bloc (titre de section du meta.yml). Un lab rattaché à
    # aucune section ne porte pas de nom : on retombe sur le numéro.
    nom = next((lab.bloc_name for lab in ordonnes if lab.bloc_name), "")

    return BlocProgress(
        bloc=numero,
        label=nom or (str(numero) if numero else ""),
        validated=len(valides),
        total=len(notes),
        average_pct=_moyenne_des_valides(valides, scores),
        challenge_validated=(challenges[0].id in scores) if challenges else None,
        capstone_validated=(capstones[0].id in scores) if capstones else None,
    )


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
        # Un lab `validation` n'est l'étape suivante de personne : il défend un
        # guide, il n'apprend rien. Il n'entre jamais dans `scores` non plus,
        # donc sans ce filtre il serait proposé indéfiniment — et proposé en
        # premier, puisqu'il ne peut jamais être « validé ».
        if not lab.is_exercise:
            continue
        if lab.id not in scores:
            return lab
    return None
