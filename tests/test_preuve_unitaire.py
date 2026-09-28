"""Une preuve pour un seul lab : le même document, transportable autrement.

Le lien de remise est l'UX la plus directe, et il ne suffit pas : un terminal qui
ne rend pas les URL cliquables, un navigateur sur une autre machine, un
environnement isolé, un formateur qui collecte autrement, un apprenant qui
archive. Trois transports, donc — lien, fichier, copier-coller — et **un seul
format**, sans quoi chaque consommateur devrait en gérer deux pour dire la même
chose.

Ce fichier tient trois promesses. Que la preuve unitaire soit le **même
document** que l'export complet, avec un résultat et `count: 1`. Que le fichier
s'écrive **sans surprise** : rien d'écrasé en silence, aucun lien symbolique
suivi, une sortie standard vide. Et qu'elle ne porte **rien de la machine** — la
liste blanche de l'export global, éprouvée à nouveau ici, parce que ce document-ci
est fait pour être envoyé à quelqu'un.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.sessions.store import record_result

runner = CliRunner()

#: Ce que le portail accepte dans un fragment d'URL, encodé. Mesuré côté site,
#: pas deviné : au-delà, la charge est refusée avant tout décodage.
LIMITE_FRAGMENT = 32 * 1024


def _tentative(
    catalogue: Path, *, lab_id: str = "premier", score: int = 80, passed: int = 8
) -> None:
    record_result(
        catalogue,
        lab_id=lab_id,
        section="domaine",
        score=score,
        max_score=100,
        passed_tests=passed,
        total_tests=8,
        hints_used=0,
    )


def _document(sortie: str) -> dict[str, Any]:
    return json.loads(sortie)


# ── le même document, réduit à un lab ────────────────────────────────────────

def test_une_preuve_unitaire_ne_porte_qu_un_resultat(catalogue: Path) -> None:
    _tentative(catalogue, lab_id="premier")
    _tentative(catalogue, lab_id="second")

    resultat = runner.invoke(app, ["export", "--lab", "premier"])

    assert resultat.exit_code == 0, resultat.stdout
    document = _document(resultat.stdout)
    assert document["count"] == 1
    assert [ligne["lab_id"] for ligne in document["results"]] == ["premier"]


def test_l_enveloppe_est_celle_de_l_export_complet(catalogue: Path) -> None:
    """Pas de second schéma : qui sait lire l'un sait lire l'autre."""
    _tentative(catalogue)

    complet = _document(runner.invoke(app, ["export"]).stdout)
    unitaire = _document(runner.invoke(app, ["export", "--lab", "premier"]).stdout)

    assert set(complet) == set(unitaire)
    assert unitaire["schema"] == "dsoxlab-evidence-v1"
    assert set(complet["results"][0]) == set(unitaire["results"][0])


def test_c_est_la_derniere_tentative_qui_compte(catalogue: Path) -> None:
    """Une preuve atteste ce qui s'est passé, pas ce qu'on préfère montrer."""
    _tentative(catalogue, score=95, passed=8)
    _tentative(catalogue, score=40, passed=4)

    document = _document(runner.invoke(app, ["export", "--lab", "premier"]).stdout)

    assert document["results"][0]["score"] == 40
    assert document["results"][0]["validated"] is False


def test_le_document_se_relit_sans_perte(catalogue: Path) -> None:
    """Le round-trip que tout consommateur va faire, fait ici une fois."""
    _tentative(catalogue)

    brut = runner.invoke(app, ["export", "--lab", "premier"]).stdout
    document = json.loads(brut)

    assert json.loads(json.dumps(document)) == document


def test_la_preuve_tient_dans_un_fragment_d_url(catalogue: Path) -> None:
    """La limite du portail est mesurée, pas supposée : 32 Ko encodés.

    Ce test la vérifie sur une preuve réelle plutôt que de faire confiance à
    l'intuition « ça tient » — c'est ce qui dira, le jour où un champ s'ajoute,
    que le lien de remise vient de cesser d'être une option.
    """
    _tentative(catalogue)

    document = _document(runner.invoke(app, ["export", "--lab", "premier"]).stdout)
    compact = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    charge = base64.urlsafe_b64encode(compact.encode("utf-8")).decode("ascii")

    assert len(charge) < LIMITE_FRAGMENT


# ── ce que la preuve ne porte pas ────────────────────────────────────────────

@pytest.mark.parametrize("interdit", [
    "/home/", "path", "hostname", "provider", "target", "stdout", "stderr",
])
def test_la_preuve_unitaire_ne_porte_rien_de_local(
    catalogue: Path, interdit: str
) -> None:
    """La même liste blanche que l'export complet, éprouvée sur ce chemin-ci.

    Un second producteur du même document est un second endroit où un champ
    peut fuir. D'où ce contrôle ici, et pas seulement sur l'export global.
    """
    _tentative(catalogue)

    brut = runner.invoke(app, ["export", "--lab", "premier"]).stdout

    assert interdit not in brut


# ── les cas où il n'y a pas de preuve ────────────────────────────────────────

def test_un_lab_inconnu_se_distingue(catalogue: Path) -> None:
    """Un lab inconnu se cherche, une preuve absente se gagne : deux messages."""
    resultat = runner.invoke(app, ["export", "--lab", "rien-du-tout"])

    assert resultat.exit_code == 1
    assert resultat.stdout == "" or "rien-du-tout" in resultat.output


def test_un_lab_jamais_tente_le_dit(catalogue: Path) -> None:
    resultat = runner.invoke(app, ["export", "--lab", "premier"])

    assert resultat.exit_code == 1
    assert "submit" in resultat.output


def test_un_lab_de_validation_ne_produit_pas_de_preuve(catalogue: Path) -> None:
    """Il défend un guide et ne note personne : rien à attester."""
    lab = catalogue / "labs" / "domaine" / "premier" / "lab.yaml"
    lab.write_text(
        lab.read_text(encoding="utf-8") + "lab_type: validation\n", encoding="utf-8"
    )
    _tentative(catalogue)

    resultat = runner.invoke(app, ["export", "--lab", "premier"])

    assert resultat.exit_code == 1
    assert "guide" in resultat.output


# ── le fichier ───────────────────────────────────────────────────────────────

def test_out_laisse_la_sortie_standard_vide(catalogue: Path, tmp_path: Path) -> None:
    """Un appelant qui redirige `--out` ne veut rien voir passer dans le tube."""
    _tentative(catalogue)
    cible = tmp_path / "preuve.json"

    resultat = runner.invoke(app, ["export", "--lab", "premier", "--out", str(cible)])

    assert resultat.exit_code == 0, resultat.output
    assert resultat.stdout == ""
    assert json.loads(cible.read_text(encoding="utf-8"))["count"] == 1


def test_un_fichier_existant_n_est_pas_ecrase(catalogue: Path, tmp_path: Path) -> None:
    """Une preuve remplacée en silence est une preuve perdue."""
    _tentative(catalogue)
    cible = tmp_path / "preuve.json"
    cible.write_text("le contenu précédent\n", encoding="utf-8")

    resultat = runner.invoke(app, ["export", "--lab", "premier", "--out", str(cible)])

    assert resultat.exit_code == 1
    assert cible.read_text(encoding="utf-8") == "le contenu précédent\n"
    assert "--force" in resultat.output


def test_force_ecrase_ce_qui_a_ete_demande(catalogue: Path, tmp_path: Path) -> None:
    _tentative(catalogue)
    cible = tmp_path / "preuve.json"
    cible.write_text("le contenu précédent\n", encoding="utf-8")

    resultat = runner.invoke(
        app, ["export", "--lab", "premier", "--out", str(cible), "--force"]
    )

    assert resultat.exit_code == 0, resultat.output
    assert json.loads(cible.read_text(encoding="utf-8"))["count"] == 1


def test_un_lien_symbolique_n_est_jamais_suivi(
    catalogue: Path, tmp_path: Path
) -> None:
    """Écrire « dans » un lien écrit ailleurs, à un endroit qu'on n'a pas nommé."""
    _tentative(catalogue)
    ailleurs = tmp_path / "ailleurs.json"
    lien = tmp_path / "lien.json"
    lien.symlink_to(ailleurs)

    resultat = runner.invoke(app, ["export", "--lab", "premier", "--out", str(lien)])

    assert resultat.exit_code == 1
    assert not ailleurs.exists()


def test_le_fichier_n_est_pas_un_secret(catalogue: Path, tmp_path: Path) -> None:
    """Un formateur doit pouvoir le lire sans commencer par un chmod.

    `ecrire_atomiquement` crée en `0600` — juste pour un `ssh_config`, trop pour
    une preuve, dont le contrat garantit qu'elle ne porte aucun secret.
    """
    _tentative(catalogue)
    cible = tmp_path / "preuve.json"

    runner.invoke(app, ["export", "--lab", "premier", "--out", str(cible)])

    assert cible.stat().st_mode & 0o044, oct(cible.stat().st_mode)


def test_out_vaut_aussi_pour_l_export_complet(catalogue: Path, tmp_path: Path) -> None:
    """`--out` n'est pas réservé à `--lab` : archiver tout son historique compte."""
    _tentative(catalogue, lab_id="premier")
    _tentative(catalogue, lab_id="second")
    cible = tmp_path / "tout.json"

    resultat = runner.invoke(app, ["export", "--out", str(cible)])

    assert resultat.exit_code == 0, resultat.output
    assert json.loads(cible.read_text(encoding="utf-8"))["count"] == 2
