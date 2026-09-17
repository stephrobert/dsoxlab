"""Ouvrir une issue depuis la CLI : le routage, la forme, et la limite d'URL.

Trois choses se cassent ici sans bruit, et chacune a son test.

Le **routage** : un défaut de lab déposé sur le dépôt du moteur oblige à un
transfert manuel, et c'était l'état par défaut avant cette commande.

La **forme** : un formulaire d'issue ignore ``body=`` et se remplit par
identifiant de champ. Une implémentation écrite contre ``body`` a donc l'air de
marcher, et n'ouvre qu'un formulaire vide. Rien dans la sortie ne le dit.

La **longueur** : le percent-encoding triple chaque octet, et une URL trop
longue ne s'ouvre pas, elle rend un 414. Le rapport est perdu au moment précis
où il servait.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from typer.testing import CliRunner

import dsoxlab
from dsoxlab.cli import app
from dsoxlab.i18n.strings.en import STRINGS as EN
from dsoxlab.i18n.strings.fr import STRINGS as FR
from dsoxlab.logging_setup import dernieres_lignes
from dsoxlab.models import RepoMetadata
from dsoxlab.services.issue_service import (
    CHAMPS_CONNUS,
    CHAMPS_MOTEUR,
    LIMITE_URL,
    TEMPLATE_MOTEUR,
    Cible,
    Destination,
    Origine,
    Repli,
    _ids_formulaire,
    _normaliser_remote,
    construire_lien,
    resoudre_destination,
)

runner = CliRunner()

RACINE_DEPOT = Path(dsoxlab.__file__).parent.parent.parent

FORMULAIRE = """\
name: Bug
description: Rapporter un défaut
body:
  - type: markdown
    attributes:
      value: Merci.
  - type: input
    id: lab
    attributes:
      label: Lab
  - type: textarea
    id: support
    attributes:
      label: Diagnostic
  - type: input
    id: os
    attributes:
      label: OS
  - type: textarea
    id: inconnu-du-moteur
    attributes:
      label: Autre
"""


def _depot_git(racine: Path, remote: str) -> Path:
    """Un vrai dépôt git avec un remote, plutôt qu'un ``run_command`` simulé.

    C'est ce chemin-là qui casse en vrai (remote absent, nommé autrement,
    écriture SSH), et une simulation le dirait toujours d'accord avec elle-même.
    """
    subprocess.run(["git", "init", "-q", str(racine)], check=True)
    subprocess.run(
        ["git", "-C", str(racine), "remote", "add", "origin", remote], check=True
    )
    return racine


def _params(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


# ── normaliser un remote : les trois écritures, et le jeton ───────────────────

@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        ("https://github.com/proprio/depot.git", "https://github.com/proprio/depot"),
        ("https://github.com/proprio/depot", "https://github.com/proprio/depot"),
        ("git@github.com:proprio/depot.git", "https://github.com/proprio/depot"),
        ("ssh://git@github.com/proprio/depot.git", "https://github.com/proprio/depot"),
        ("  https://github.com/proprio/depot.git\n", "https://github.com/proprio/depot"),
    ],
)
def test_les_ecritures_de_remote_donnent_la_meme_adresse(brut: str, attendu: str) -> None:
    resultat = _normaliser_remote(brut)

    assert resultat is not None
    assert resultat[0] == attendu
    assert resultat[1] == "proprio/depot"


def test_un_jeton_porte_par_le_remote_ne_ressort_jamais() -> None:
    """Un clone par jeton le garde en clair dans son remote.

    Cette adresse est affichée puis ouverte dans un navigateur : la recopier
    telle quelle publierait le jeton à l'écran, dans l'historique du shell et
    dans celui du navigateur.
    """
    resultat = _normaliser_remote("https://utilisateur:ghp_secret@github.com/proprio/depot.git")

    assert resultat is not None
    assert "ghp_secret" not in resultat[0]
    assert "utilisateur" not in resultat[0]
    assert resultat[0] == "https://github.com/proprio/depot"


@pytest.mark.parametrize("brut", ["", "   ", "pas une adresse"])
def test_un_remote_illisible_ne_leve_pas(brut: str) -> None:
    assert _normaliser_remote(brut) is None


# ── routage : quel dépôt reçoit l'issue ───────────────────────────────────────

def test_le_contrat_l_emporte_sur_le_remote(tmp_path: Path) -> None:
    """``repo.issues_url`` est le contrat ; le remote n'en est que le repli."""
    _depot_git(tmp_path, "https://github.com/proprio/depuis-le-remote.git")
    meta = RepoMetadata(
        id="demo",
        category="demo",
        issues_url="https://gitlab.example/equipe/catalogue/issues",
    )

    destination = resoudre_destination(tmp_path, meta, cible=Cible.CATALOGUE)

    assert destination is not None
    assert destination.origine is Origine.CONTRAT
    assert destination.url_issues == "https://gitlab.example/equipe/catalogue/issues"


def test_sans_contrat_le_remote_sert_de_repli(tmp_path: Path) -> None:
    _depot_git(tmp_path, "git@github.com:proprio/catalogue.git")
    meta = RepoMetadata(id="demo", category="demo")

    destination = resoudre_destination(tmp_path, meta, cible=Cible.CATALOGUE)

    assert destination is not None
    assert destination.origine is Origine.REMOTE
    assert destination.url_issues == "https://github.com/proprio/catalogue/issues"
    assert destination.libelle == "proprio/catalogue"


def test_un_catalogue_sans_adresse_ne_leve_pas(tmp_path: Path) -> None:
    """Ni contrat ni remote : ce n'est pas une erreur, c'est un cas à dire.

    Lever ici ferait perdre le rapport que la commande vient de produire.
    """
    destination = resoudre_destination(
        tmp_path, RepoMetadata(id="demo", category="demo"), cible=Cible.CATALOGUE
    )

    assert destination is None


def test_un_meta_yml_illisible_n_empeche_pas_de_router(tmp_path: Path) -> None:
    """``repo_meta`` vaut ``None`` quand le contrat ne se lit pas.

    C'est précisément le moment où l'on veut ouvrir une issue, pas celui où il
    faut refuser de le faire.
    """
    _depot_git(tmp_path, "https://github.com/proprio/catalogue.git")

    destination = resoudre_destination(tmp_path, None, cible=Cible.CATALOGUE)

    assert destination is not None
    assert destination.origine is Origine.REMOTE


def test_le_moteur_tire_son_adresse_de_son_propre_paquet() -> None:
    destination = resoudre_destination(Path("/inexistant"), None, cible=Cible.MOTEUR)

    assert destination is not None
    assert destination.cible is Cible.MOTEUR
    assert destination.origine is Origine.PAQUET
    assert destination.url_issues.endswith("/issues")
    assert destination.template == TEMPLATE_MOTEUR


# ── forme : formulaire détecté sur le disque, ou issue vierge ─────────────────

def test_un_catalogue_sans_formulaire_recoit_un_corps_libre(tmp_path: Path) -> None:
    _depot_git(tmp_path, "https://github.com/proprio/catalogue.git")
    destination = resoudre_destination(tmp_path, None, cible=Cible.CATALOGUE)
    assert destination is not None and destination.template is None

    lien = construire_lien(
        destination, contexte={"lab": "demo-lab", "os": "Ubuntu"}, rapport="## rapport"
    )

    params = _params(lien.url)
    assert "template" not in params
    assert "demo-lab" in params["body"][0]
    assert "## rapport" in params["body"][0]


def test_un_formulaire_detecte_remplace_le_corps_par_ses_champs(tmp_path: Path) -> None:
    """Un formulaire ignore ``body=``. Le lui envoyer ouvrirait un formulaire vide."""
    _depot_git(tmp_path, "https://github.com/proprio/catalogue.git")
    dossier = tmp_path / ".github" / "ISSUE_TEMPLATE"
    dossier.mkdir(parents=True)
    (dossier / "bug_report.yml").write_text(FORMULAIRE, encoding="utf-8")

    destination = resoudre_destination(tmp_path, None, cible=Cible.CATALOGUE)
    assert destination is not None
    assert destination.template == "bug_report.yml"
    # Intersection : le formulaire déclare aussi `inconnu-du-moteur`, dont la
    # CLI ne sait rien, et n'a pas à deviner.
    assert destination.champs == {"lab", "support", "os"}

    lien = construire_lien(
        destination,
        contexte={"lab": "demo-lab", "os": "Ubuntu", "runtime": "vm"},
        rapport="## rapport",
    )

    params = _params(lien.url)
    assert "body" not in params
    assert params["template"] == ["bug_report.yml"]
    assert params["lab"] == ["demo-lab"]
    assert params["support"] == ["## rapport"]
    # `runtime` n'est pas déclaré par ce formulaire : l'envoyer quand même
    # créerait un paramètre que GitHub ignore en silence.
    assert "runtime" not in params


def test_le_formulaire_de_bug_est_prefere_a_celui_de_fonctionnalite(tmp_path: Path) -> None:
    _depot_git(tmp_path, "https://github.com/proprio/catalogue.git")
    dossier = tmp_path / ".github" / "ISSUE_TEMPLATE"
    dossier.mkdir(parents=True)
    (dossier / "a_feature_request.yml").write_text(FORMULAIRE, encoding="utf-8")
    (dossier / "bug_report.yml").write_text(FORMULAIRE, encoding="utf-8")

    destination = resoudre_destination(tmp_path, None, cible=Cible.CATALOGUE)

    assert destination is not None
    assert destination.template == "bug_report.yml"


def test_un_formulaire_illisible_ramene_a_l_issue_vierge(tmp_path: Path) -> None:
    _depot_git(tmp_path, "https://github.com/proprio/catalogue.git")
    dossier = tmp_path / ".github" / "ISSUE_TEMPLATE"
    dossier.mkdir(parents=True)
    (dossier / "bug_report.yml").write_text("body: [oui\n  - non", encoding="utf-8")

    destination = resoudre_destination(tmp_path, None, cible=Cible.CATALOGUE)

    assert destination is not None
    assert destination.template is None


def test_config_yml_n_est_pas_un_formulaire(tmp_path: Path) -> None:
    _depot_git(tmp_path, "https://github.com/proprio/catalogue.git")
    dossier = tmp_path / ".github" / "ISSUE_TEMPLATE"
    dossier.mkdir(parents=True)
    (dossier / "config.yml").write_text(
        "blank_issues_enabled: true\n", encoding="utf-8"
    )

    destination = resoudre_destination(tmp_path, None, cible=Cible.CATALOGUE)

    assert destination is not None
    assert destination.template is None


# ── longueur : l'URL casse bien avant le corps ────────────────────────────────

def _destination_moteur() -> Destination:
    destination = resoudre_destination(Path("/inexistant"), None, cible=Cible.MOTEUR)
    assert destination is not None
    return destination


def test_un_rapport_court_passe_entier() -> None:
    lien = construire_lien(_destination_moteur(), rapport="## court")

    assert lien.repli is Repli.COMPLET
    assert len(lien.url) <= LIMITE_URL


def test_un_rapport_trop_long_perd_son_journal_avant_l_url() -> None:
    lien = construire_lien(
        _destination_moteur(),
        rapport="x" * 12_000,
        rapport_court="## sans journal",
    )

    assert lien.repli is Repli.SANS_JOURNAL
    assert len(lien.url) <= LIMITE_URL
    assert "sans+journal" in lien.url


def test_quand_meme_le_rapport_court_deborde_le_formulaire_s_ouvre_nu() -> None:
    """Le dernier repli ne doit pas rendre une URL qu'on sait cassée."""
    lien = construire_lien(
        _destination_moteur(),
        rapport="x" * 12_000,
        rapport_court="y" * 12_000,
    )

    assert lien.repli is Repli.VIDE
    assert len(lien.url) <= LIMITE_URL
    assert "support=" not in lien.url


def test_sans_rapport_court_on_ne_repasse_pas_par_le_meme_corps() -> None:
    """``--log-lines 0`` rend les deux rapports identiques.

    Annoncer alors un repli serait faux : rien n'a été retiré.
    """
    lien = construire_lien(
        _destination_moteur(), rapport="## court", rapport_court="## court"
    )

    assert lien.repli is Repli.COMPLET


# ── ce que le dépôt du moteur déclare vraiment ────────────────────────────────

def test_les_champs_du_moteur_sont_ceux_de_son_formulaire() -> None:
    """``CHAMPS_MOTEUR`` est écrit à la main : le dépôt n'est pas sur le disque
    de l'apprenant, seul son paquet l'est. Ici, il l'est, donc on vérifie.
    """
    formulaire = RACINE_DEPOT / ".github" / "ISSUE_TEMPLATE" / TEMPLATE_MOTEUR
    if not formulaire.is_file():
        pytest.skip("hors du dépôt source : le formulaire n'est pas empaqueté")

    assert _ids_formulaire(formulaire) & CHAMPS_CONNUS == CHAMPS_MOTEUR


def test_le_dropdown_runtime_du_moteur_offre_les_valeurs_du_contrat() -> None:
    """La CLI remplit ``runtime`` avec ``vm`` ou ``shell``.

    Un ``dropdown`` n'accepte que ses propres options : proposer ``kvm`` et
    ``incus``, qui nomment un provider et non un runtime, rendrait ce champ
    impossible à pré-remplir.
    """
    formulaire = RACINE_DEPOT / ".github" / "ISSUE_TEMPLATE" / TEMPLATE_MOTEUR
    if not formulaire.is_file():
        pytest.skip("hors du dépôt source : le formulaire n'est pas empaqueté")

    import yaml

    donnees = yaml.safe_load(formulaire.read_text(encoding="utf-8"))
    champs = {c["id"]: c for c in donnees["body"] if "id" in c}
    options = set(champs["runtime"]["attributes"]["options"])

    assert {"vm", "shell"} <= options


# ── les phrases existent dans les deux langues ────────────────────────────────

@pytest.mark.parametrize("membre", [*list(Cible), *list(Origine)])
def test_chaque_cible_et_chaque_origine_a_sa_phrase(membre: Cible | Origine) -> None:
    """Les clés sont assemblées, donc invisibles au garde-fou statique.

    L'exhaustivité vient de l'énumération : un membre ajouté sans sa traduction
    fait échouer ce test, ce qu'une table recopiée à la main ne garantirait pas.
    """
    assert membre.cle_i18n in EN
    assert membre.cle_i18n in FR


# ── le journal : `0` ne veut pas dire « tout » ────────────────────────────────

def test_zero_ligne_de_journal_n_en_joint_aucune() -> None:
    """``lignes[-0:]`` vaut ``lignes[0:]``, c'est-à-dire le journal entier.

    L'aide promet l'inverse depuis toujours, et le défaut restait invisible
    tant que personne ne demandait zéro ligne.
    """
    assert dernieres_lignes(0) == []
    assert dernieres_lignes(-5) == []


# ── refus d'options : chacun a son code et sa phrase ──────────────────────────

@pytest.mark.parametrize(
    "arguments",
    [
        ["support", "--issue", "--json"],
        ["support", "--issue", "--engine", "--catalog"],
        ["support", "--print"],
    ],
)
def test_les_combinaisons_qui_ne_veulent_rien_dire_sortent_en_2(
    arguments: list[str],
) -> None:
    resultat = runner.invoke(app, arguments)

    assert resultat.exit_code == 2
