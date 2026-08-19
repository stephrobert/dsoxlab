"""Le rapport de diagnostic, et surtout ce qu'il ne doit jamais contenir.

Ce rapport est fait pour être collé publiquement dans une issue. L'anonymisation
n'est donc pas un confort : un chemin absolu suffit à publier le nom de famille
de quelqu'un, un nom d'hôte à identifier une machine d'entreprise.

Les tests qui comptent ici sont ceux qui vérifient une ABSENCE.
"""

from __future__ import annotations

import getpass
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.services import support

runner = CliRunner()

META = "repo:\n  id: demo\n  category: demo\n"


@pytest.fixture
def catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "meta.yml").write_text(META, encoding="utf-8")
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    return tmp_path


# ── anonymisation : ce que le rapport ne doit jamais porter ───────────────────

def test_le_repertoire_personnel_devient_un_tilde() -> None:
    texte = f"le lab est dans {Path.home()}/Projets/mon-catalogue"

    assert str(Path.home()) not in support.anonymiser(texte)
    assert "~/Projets/mon-catalogue" in support.anonymiser(texte)


def test_le_nom_d_utilisateur_disparait() -> None:
    """Un chemin ne portant pas le HOME peut tout de même porter le nom.

    Le cas courant : /srv/formations/<user>/labs, ou une trace de commande.
    """
    utilisateur = getpass.getuser()
    if len(utilisateur) <= 2:
        pytest.skip("nom trop court pour être substitué sans casser le texte")

    texte = f"/srv/formations/{utilisateur}/labs et sudo -u {utilisateur} virsh"
    anonyme = support.anonymiser(texte)

    assert utilisateur not in anonyme
    assert anonyme.count("<user>") == 2


def test_les_adresses_publiques_sont_masquees() -> None:
    texte = "connexion vers 93.184.216.34 puis vers 8.8.8.8"
    anonyme = support.anonymiser(texte)

    assert "93.184.216.34" not in anonyme
    assert "8.8.8.8" not in anonyme
    assert anonyme.count("<ip>") == 2


def test_les_adresses_privees_restent_lisibles() -> None:
    """Masquer les IP de lab rendrait inexploitable tout rapport d'infra.

    10.10.30.11 ne désigne personne hors du réseau local, et c'est précisément
    l'information dont on a besoin pour diagnostiquer un provisionnement.
    """
    texte = "alma-rhcsa-1 a pris 10.10.30.11, bridge en 192.168.122.1, boucle 127.0.0.1"
    anonyme = support.anonymiser(texte)

    assert "10.10.30.11" in anonyme
    assert "192.168.122.1" in anonyme
    assert "127.0.0.1" in anonyme
    assert "<ip>" not in anonyme


def test_une_chaine_vide_ne_leve_pas() -> None:
    assert support.anonymiser("") == ""


# ── le rapport complet ────────────────────────────────────────────────────────

def test_le_rapport_ne_porte_aucun_chemin_personnel(catalogue: Path) -> None:
    """Le contrôle qui vaut pour tout le reste : on relit le rapport entier."""
    rapport = support.collecter()
    rendu = support.en_markdown(rapport) + json.dumps(rapport, ensure_ascii=False)

    assert str(Path.home()) not in rendu, (
        "un chemin absolu dans un rapport destiné à une issue publie le HOME"
    )

    utilisateur = getpass.getuser()
    if len(utilisateur) > 2:
        assert utilisateur not in rendu


def test_le_rapport_nomme_les_outils_manquants_sans_en_faire_une_erreur(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une absence normale reste une absence, pas un échec.

    Un catalogue entièrement `shell` n'a besoin ni de terraform ni d'incus :
    les afficher comme des erreurs reproduirait le défaut que `doctor` a mis
    des versions à corriger.
    """
    monkeypatch.setattr(support.shutil, "which", lambda nom: None)

    rapport = support.collecter()

    assert set(rapport["outils"].values()) == {"absent"}
    assert "erreur" not in rapport["outils"]


def test_le_rapport_survit_a_un_catalogue_illisible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un diagnostic qui lève en diagnostiquant est le pire des cas.

    Il survient justement quand l'environnement est cassé, c'est-à-dire quand
    on en a le plus besoin.
    """
    (tmp_path / "meta.yml").write_text("repo: [ceci nest pas: un mapping\n", encoding="utf-8")
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))

    rapport = support.collecter()

    assert rapport["dsoxlab"]
    assert "catalogue" in rapport


def test_le_journal_est_joint_et_bornable(catalogue: Path) -> None:
    runner.invoke(app, ["list-labs"])

    avec = support.collecter(lignes_journal=5)
    sans = support.collecter(lignes_journal=0)

    assert len(avec["journal"]) <= 5
    assert sans["journal"] == []


# ── les deux sorties de la commande ───────────────────────────────────────────

def test_la_commande_rend_du_markdown_collable(catalogue: Path) -> None:
    resultat = runner.invoke(app, ["support"])

    assert resultat.exit_code == 0
    assert "## dsoxlab support" in resultat.stdout
    assert "| dsoxlab |" in resultat.stdout


def test_la_sortie_json_ne_contient_que_du_json(catalogue: Path) -> None:
    """Un « ℹ » en tête de flux rendrait le document illisible pour l'appelant."""
    resultat = runner.invoke(app, ["support", "--json"])

    charge = json.loads(resultat.stdout)
    assert charge["schema"] == 1
    assert charge["dsoxlab"]
    assert "outils" in charge and "catalogue" in charge


def test_les_deux_sorties_portent_le_meme_contenu(catalogue: Path) -> None:
    """Sinon l'une des deux finirait par mentir, et ce serait la moins lue."""
    markdown = runner.invoke(app, ["support"]).stdout
    charge = json.loads(runner.invoke(app, ["support", "--json"]).stdout)

    assert charge["dsoxlab"] in markdown
    assert charge["architecture"] in markdown
