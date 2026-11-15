"""La chaîne de sécurité des catalogues frères, posée par `new catalog`.

Reprise de applications-ia-dsoxlab-training (e7db2da) : les jobs Zizmor,
Actionlint, Poutine, Pre-commit parity et CodeQL dans `ci.yml`, Dependabot, la
configuration CodeQL, CODEOWNERS, les gabarits d'issue, `.poutine.yml`, et une
politique de sécurité avec délais de divulgation.

Ce que ces tests tiennent : chaque fichier est écrit et se charge ; les sept
contrôles portent les noms exacts que le ruleset exige ; le propriétaire est
celui de `--github`, ou l'emplacement `<owner>`, jamais un compte réel.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from dsoxlab.services.scaffold import creer_catalogue
from tests.test_socle_du_catalogue import _noms_des_controles

#: Les contrôles exigés par le ruleset des catalogues frères, au caractère près.
SEPT_CONTROLES = {
    "Zizmor (workflow static analysis)",
    "Actionlint (workflow syntax)",
    "Poutine (CI/CD exploit chains)",
    "Pre-commit parity (all hooks)",
    "Contract, guardrails and lint",
    "CodeQL (python)",
    "CodeQL (actions)",
}

_YAML = (
    ".github/dependabot.yml",
    ".github/codeql/config.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/lab_report.yml",
    ".poutine.yml",
)


@pytest.fixture
def avec(tmp_path: Path) -> Path:
    return creer_catalogue("demo", tmp_path / "avec", proprietaire="exemple").racine


@pytest.fixture
def sans(tmp_path: Path) -> Path:
    return creer_catalogue("demo", tmp_path / "sans").racine


def test_chaque_fichier_de_la_chaine_est_ecrit_et_se_charge(avec: Path) -> None:
    for relatif in _YAML:
        chemin = avec / relatif
        assert chemin.is_file(), f"{relatif} manque au socle"
        assert yaml.safe_load(chemin.read_text(encoding="utf-8")), f"{relatif} est vide"
    for relatif in (".github/CODEOWNERS", "SECURITY.md", "SECURITY.fr.md"):
        assert (avec / relatif).is_file(), f"{relatif} manque au socle"


def test_les_sept_controles_portent_leur_nom_exact(avec: Path) -> None:
    """Le ruleset exige des NOMS : un job renommé est un contrôle jamais rendu."""
    ci = yaml.safe_load(
        (avec / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    assert _noms_des_controles(ci) == SEPT_CONTROLES


def test_dependabot_suit_le_verrou_et_les_actions(avec: Path) -> None:
    config = yaml.safe_load((avec / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    ecosystemes = {u["package-ecosystem"] for u in config["updates"]}
    assert ecosystemes == {"uv", "github-actions"}
    # Les paliers semver ne sont pas acceptés pour github-actions : les
    # déclarer fait rejeter le fichier par GitHub, qui cesse d'ouvrir des PR.
    actions = next(u for u in config["updates"] if u["package-ecosystem"] == "github-actions")
    assert set(actions["cooldown"]) == {"default-days"}


def test_codeql_laisse_les_fixtures_et_les_solutions(avec: Path) -> None:
    config = yaml.safe_load((avec / ".github" / "codeql" / "config.yml").read_text(encoding="utf-8"))
    assert config["paths-ignore"] == ["labs/**/fixtures/**", "labs/**/solution/**"]


def _proprietaires_codeowners(racine: Path) -> set[str]:
    texte = (racine / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    return {
        mot
        for ligne in texte.splitlines()
        if ligne.strip() and not ligne.lstrip().startswith("#")
        for mot in ligne.split()[1:]
    }


def test_codeowners_nomme_le_proprietaire_de_github(avec: Path, sans: Path) -> None:
    assert _proprietaires_codeowners(avec) == {"@exemple"}
    assert _proprietaires_codeowners(sans) == {"@<owner>"}


def test_security_suit_la_structure_de_reference(avec: Path) -> None:
    for nom, titres in (
        ("SECURITY.md", ["Supported versions", "Reporting a vulnerability",
                         "Disclosure policy", "Scope",
                         "What this repository will never ask you"]),
        ("SECURITY.fr.md", ["Versions supportées", "Signaler une vulnérabilité",
                            "Politique de divulgation", "Périmètre",
                            "Ce que ce dépôt ne vous demandera jamais"]),
    ):
        texte = (avec / nom).read_text(encoding="utf-8")
        assert re.findall(r"^## (.+)$", texte, re.MULTILINE) == titres, nom
        assert "https://github.com/exemple/demo/security/advisories/new" in texte
        assert "90" in texte and "48" in texte, f"{nom} : délais de divulgation absents"
    # Le périmètre est celui d'un catalogue de labs, pas d'un domaine.
    for nom in ("SECURITY.md", "SECURITY.fr.md"):
        texte = (avec / nom).read_text(encoding="utf-8").lower()
        for mot in (" ia ", " ai ", "intelligence", "agent"):
            assert mot not in texte, f"{nom} parle encore de {mot.strip()!r}"


def test_le_gabarit_d_issue_vise_le_depot_du_catalogue(avec: Path) -> None:
    config = yaml.safe_load(
        (avec / ".github" / "ISSUE_TEMPLATE" / "config.yml").read_text(encoding="utf-8")
    )
    urls = [lien["url"] for lien in config["contact_links"]]
    assert "https://github.com/exemple/demo/security/advisories/new" in urls
    rapport = (avec / ".github" / "ISSUE_TEMPLATE" / "lab_report.yml").read_text(encoding="utf-8")
    assert "exemple/demo" in rapport


#: Les seuls dépôts tiers qu'un catalogue neuf peut nommer : le moteur, et les
#: deux binaires que la CI télécharge avec vérification d'empreinte.
_DEPOTS_TIERS = {"dsoxlab", "actionlint", "trufflehog"}


def test_aucun_proprietaire_reel_sans_option_github(sans: Path) -> None:
    """Sans `--github`, le catalogue n'est attribué à personne de réel.

    Toute URL GitHub d'un fichier `.github/` ou de SECURITY vise soit le dépôt
    `<owner>/demo`, soit un dépôt tiers attendu (le moteur, un binaire vérifié).
    """
    fichiers = [p for p in (sans / ".github").rglob("*") if p.is_file()]
    fichiers += [sans / "SECURITY.md", sans / "SECURITY.fr.md", sans / ".poutine.yml"]
    for chemin in fichiers:
        texte = chemin.read_text(encoding="utf-8")
        for proprietaire, depot in re.findall(r"github\.com/([\w.<>-]+)/([\w.<>-]+)", texte):
            if proprietaire == "<owner>":
                assert depot.startswith("demo"), f"{chemin.name} : <owner>/{depot}"
                continue
            assert depot in _DEPOTS_TIERS, (
                f"{chemin.relative_to(sans)} nomme {proprietaire}/{depot}"
            )
