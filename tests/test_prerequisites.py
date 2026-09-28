"""`prerequisites` — ce qu'un capstone suppose, et que `doc_url` ne dit pas.

Un lab porte un seul `doc_url` : la leçon qu'il éprouve. C'est juste pour un
micro-lab, et faux pour un capstone, qui croise plusieurs sujets et ne peut en
nommer qu'un. Le champ est alors honnêtement rempli et sous-annonce quand même
ce que le lab couvre.

Les prérequis disent l'ordre, qui est la vraie information — encore faut-il
qu'ils nomment des labs qui existent, sans quoi le catalogue affiche un
parcours qui ne mène nulle part.
"""
from __future__ import annotations

from pathlib import Path

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.validators import content


def _lab(
    chemin: Path, lab_type: str = "capstone", id_: str = "capstone-portail"
) -> LabDefinition:
    return LabDefinition(
        id=id_,
        title="Le parcours entier, en une fois",
        level="l3",
        path=chemin,
        doc_url="https://example.test/guide",
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="work"),
        skills=["synthese"],
        distros=["almalinux10"],
        validation=ValidationConfig(),
        lab_type=lab_type,
    )


class TestPrerequisites:
    """`prerequisites` : ce qu'un capstone suppose, et que `doc_url` tait.

    Un capstone croise plusieurs sujets et ne peut en nommer qu'un dans
    `doc_url`. Le champ est alors honnêtement rempli et sous-annonce quand même
    ce que le lab couvre. Les prérequis disent l'ordre, qui est la vraie
    information — encore faut-il qu'ils nomment des labs qui existent.
    """

    def test_un_prerequis_connu_passe(self, tmp_path: Path) -> None:
        capstone = _lab(tmp_path, lab_type="capstone", id_="capstone-portail")
        capstone.prerequisites = ["socle-reseau", "socle-stockage"]

        rapport = content.validate_prerequisites(
            capstone, {"capstone-portail", "socle-reseau", "socle-stockage"}
        )

        assert rapport.ok

    def test_un_prerequis_inconnu_est_signale(self, tmp_path: Path) -> None:
        """Le défaut invisible : aucun test ne casse, aucun run n'échoue.

        Le catalogue affiche simplement un ordre qui ne mène nulle part, et
        l'auteur ne s'en aperçoit pas.
        """
        capstone = _lab(tmp_path, lab_type="capstone", id_="capstone-portail")
        capstone.prerequisites = ["socle-reseau", "lab-renomme-hier"]

        rapport = content.validate_prerequisites(
            capstone, {"capstone-portail", "socle-reseau"}
        )

        assert not rapport.ok
        (souci,) = rapport.issues
        assert souci.key == "content_prerequisite_unknown"
        assert souci.params == {"prerequisite": "lab-renomme-hier"}

    def test_un_lab_ne_peut_pas_etre_son_propre_prerequis(self, tmp_path: Path) -> None:
        """La boucle se lit ici ; dans un parcours, elle se débusque."""
        capstone = _lab(tmp_path, lab_type="capstone", id_="capstone-portail")
        capstone.prerequisites = ["capstone-portail"]

        rapport = content.validate_prerequisites(capstone, {"capstone-portail"})

        assert not rapport.ok
        assert rapport.issues[0].key == "content_prerequisite_self"

    def test_sans_prerequis_le_controle_se_tait(self, tmp_path: Path) -> None:
        assert content.validate_prerequisites(_lab(tmp_path), set()).ok

    def test_le_champ_est_expose_a_un_consommateur(self, tmp_path: Path) -> None:
        """Déclaré mais non exposé, le champ ne servirait à personne.

        C'est un site qui en a besoin : proposer le capstone à la fin d'un
        chapitre plutôt que de le noyer dans une liste.
        """
        from dsoxlab.reporting import machine

        capstone = _lab(tmp_path, lab_type="capstone", id_="capstone-portail")
        capstone.prerequisites = ["socle-reseau"]

        assert machine.lab_dict(capstone)["prerequisites"] == ["socle-reseau"]
