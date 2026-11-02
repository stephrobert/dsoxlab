"""Lab metadata validation.

Comme les autres validators, ce module ne compose **aucune phrase** : chaque
anomalie porte une clé i18n et ses paramètres, que ``validate-structure`` rend
dans la langue de l'auteur. Les messages écrits ici en dur sortaient en
français quel que soit ``DSOXLAB_LANG``.
"""

from __future__ import annotations

import ast
import dataclasses
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ..models.lab import LabDefinition

#: Les trois premières formes supposent un apprenant qui fait ; ``validation``
#: non — c'est une suite d'assertions qui défend un guide publié. Étendre
#: l'énuméré plutôt qu'ajouter un champ : le lab est le bon grain, puisque le
#: même dépôt peut porter les deux (une stack d'infra et ses assertions).
_VALID_LAB_TYPES = {"lab", "challenge", "capstone", "validation"}

#: Les deux formes qui ÉVALUENT, et les seules où un seuil de réussite
#: veut dire quelque chose. Mesuré sur les 424 labs des 22 catalogues du
#: 2026-10-19 : les 21 labs qui déclarent `exam_passing_score` sont tous
#: l'un de ces deux types, aucun n'est un `lab`. L'invariant est donc
#: déjà tenu, et ce contrôle le rend opposable au lieu de reposer sur
#: l'attention de l'auteur.
_TYPES_QUI_EVALUENT = {"challenge", "capstone"}


@dataclass
class MetadataIssue:
    field: str
    key: str
    """Clé i18n du message, présente dans ``strings/en.py`` ET ``strings/fr.py``."""

    # `dataclasses.field`, en toutes lettres : la dataclass porte un attribut
    # nommé `field`, et le nom court désignerait alors le champ, pas la fonction.
    params: dict[str, Any] = dataclasses.field(default_factory=dict)
    """Paramètres de substitution du message."""


@dataclass
class MetadataReport:
    lab_id: str
    issues: list[MetadataIssue] = dataclasses.field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.issues) == 0


def _controler_les_blocages(
    lab: LabDefinition, report: MetadataReport
) -> None:
    """Les deux contrôles propres à ``exam_blocking_checks``.

    Sortis de ``validate_metadata`` parce que le cliquet de complexité du
    dépôt a refusé la fonction, et il a eu raison : elle empilait sept
    contrôles indépendants, et les deux nouveaux la poussaient à 25 de
    complexité cognitive et au-delà de quatre-vingts lignes.

    Les trois tiennent ensemble : ils disent ce qu'un lab a le droit de
    déclarer quand il ÉVALUE quelqu'un, et ils ne regardent que ces
    champs-là.
    """
    # LES CONTRÔLES BLOQUANTS DOIVENT EXISTER, et c'est la faiblesse propre de
    # la forme déclarative : le `lab.yaml` nomme un test, et rien ne garantit
    # que ce test porte encore ce nom. Un renommage désarmerait l'exigence en
    # silence, et l'épreuve redeviendrait compensable sans que personne ne
    # l'ait décidé.
    #
    # On lit le FICHIER, pas les tests collectés : `validate-structure` tourne
    # hors ligne et sans machine, et doit rester jouable dans la CI d'un
    # catalogue. Chercher les `def <nom>(` suffit à attraper un renommage.
    fichier_de_tests = lab.path / "challenge/tests/test_functional.py"
    if lab.exam_blocking_checks and fichier_de_tests.is_file():
        source = fichier_de_tests.read_text(encoding="utf-8", errors="replace")
        definis = {
            noeud.name
            for noeud in ast.walk(ast.parse(source))
            if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for nom in lab.exam_blocking_checks:
            if nom not in definis:
                report.issues.append(
                    MetadataIssue(
                        "exam_blocking_checks",
                        "metadata_blocking_check_inconnu",
                        {"value": nom},
                    )
                )

    # Une exigence bloquante sur un lab qui n'évalue personne ne veut rien
    # dire, pour la même raison qu'un seuil au même endroit.
    if (
        lab.exam_blocking_checks
        and lab.lab_type in _VALID_LAB_TYPES - _TYPES_QUI_EVALUENT
    ):
        report.issues.append(
            MetadataIssue(
                "lab_type",
                "metadata_blocking_sans_epreuve",
                {
                    "value": lab.lab_type,
                    "expected": ", ".join(sorted(_TYPES_QUI_EVALUENT)),
                },
            )
        )


def _controler_le_seuil_sans_epreuve(
    lab: LabDefinition, report: MetadataReport
) -> None:
    """Un seuil de réussite sur un lab qui ne note personne.

    Séparé de son voisin parce que les deux réunis faisaient une fonction de
    quatre-vingt-quatre lignes, que le cliquet du dépôt refuse. Ce sont deux
    règles distinctes, sur deux champs distincts.
    """
    # Un seuil de réussite sur un lab qui n'évalue pas est une contradiction,
    # et elle ne se voit pas : le moteur rend le verdict que `submit` affiche,
    # pendant que tout ce qui range les labs par forme (un parcours à niveaux,
    # un sommaire) classe celui-ci parmi les exercices. Les deux lectures du
    # même fichier divergent sans qu'aucune échoue.
    #
    # Un seuil absurde est déjà signalé pour lui-même, juste au-dessus : en
    # discuter la forme par-dessus ferait deux messages pour une seule ligne,
    # dont l'un porte sur une valeur qui n'a de toute façon pas de sens. Les
    # deux contrôles sont donc exclusifs.
    if (
        lab.exam_passing_score
        and 1 <= lab.exam_passing_score <= 100
        and lab.lab_type in _VALID_LAB_TYPES - _TYPES_QUI_EVALUENT
    ):
        report.issues.append(
            MetadataIssue(
                "lab_type",
                "metadata_exam_score_sans_epreuve",
                {
                    "value": lab.lab_type,
                    "score": lab.exam_passing_score,
                    "expected": ", ".join(sorted(_TYPES_QUI_EVALUENT)),
                },
            )
        )




def validate_metadata(lab: LabDefinition) -> MetadataReport:
    """Check required fields and their consistency."""
    report = MetadataReport(lab_id=lab.id)

    for champ, valeur in (
        ("id", lab.id),
        ("title", lab.title),
        ("level", lab.level),
        ("doc_url", lab.doc_url),
    ):
        if not valeur:
            report.issues.append(
                MetadataIssue(champ, "metadata_field_empty", {"field": champ})
            )
    for champ, liste in (("skills", lab.skills), ("distros", lab.distros)):
        if not liste:
            report.issues.append(
                MetadataIssue(champ, "metadata_list_empty", {"field": champ})
            )

    if lab.doc_url:
        parsed = urlparse(lab.doc_url)
        if parsed.scheme not in ("http", "https"):
            report.issues.append(
                MetadataIssue(
                    "doc_url", "metadata_doc_url_scheme", {"url": lab.doc_url}
                )
            )
    if lab.lab_type not in _VALID_LAB_TYPES:
        report.issues.append(
            MetadataIssue(
                "lab_type",
                "metadata_lab_type_invalid",
                {
                    "value": lab.lab_type,
                    "expected": ", ".join(sorted(_VALID_LAB_TYPES)),
                },
            )
        )
    # Le seuil est un POURCENTAGE du barème. Hors de 1..100, il ne veut rien
    # dire : un examen qu'on ne peut jamais réussir, ou qu'on ne peut jamais
    # rater. Le champ absent vaut 0, ce qui est « pas un examen », pas un
    # seuil hors bornes.
    if lab.exam_passing_score and not 1 <= lab.exam_passing_score <= 100:
        report.issues.append(
            MetadataIssue(
                "exam_passing_score",
                "metadata_exam_score_invalid",
                {"value": lab.exam_passing_score},
            )
        )
    _controler_les_blocages(lab, report)
    _controler_le_seuil_sans_epreuve(lab, report)

    return report
