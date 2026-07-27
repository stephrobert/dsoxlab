"""Garde-fou : une clé SSH ne se génère que dans un dépôt de labs.

Incident à l'origine de ce module. `dsoxlab instructor bootstrap` a été lancé
depuis le dépôt de l'outil (pas un dépôt de labs). `get_lab_home()` retombe sur
le répertoire courant en dernier recours, faute de `meta.yml` : la commande y a
donc créé `ssh/id_ed25519`, une clé privée sans passphrase, dans un dépôt
**public** où aucun `.gitignore` ne la couvrait.

Le hook `detect-private-key` l'aurait refusée au commit (vérifié : il sort en 1
avec « Private key found »), donc la fuite n'était pas imminente. Mais un hook
se contourne avec `--no-verify`, et surtout une clé de lab n'a rien à faire
dans le dépôt du moteur : le défaut est de l'avoir écrite là.

Trois protections se superposent désormais, et ce module tient la première :
refuser de générer hors d'un dépôt de labs, puis `ssh/` dans le `.gitignore`,
puis les hooks de détection de secrets.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from dsoxlab.cli import app

runner = CliRunner()

META_MINIMAL = "repo:\n  id: demo\n  category: demo\n"


def test_refuse_de_generer_hors_dun_depot_de_labs(tmp_path: Path) -> None:
    """Sans `meta.yml`, aucune clé, et un message qui dit quoi faire."""
    resultat = runner.invoke(
        app, ["instructor", "bootstrap", "--lab-home", str(tmp_path)]
    )

    assert resultat.exit_code == 1
    assert not (tmp_path / "ssh").exists(), (
        "le répertoire ssh/ ne doit même pas être créé"
    )


def test_un_vrai_depot_de_labs_passe_le_garde_fou(tmp_path: Path) -> None:
    """Avec `meta.yml`, la commande travaille normalement.

    On lui présente une clé déjà en place : le chemin nominal est donc couvert
    sans dépendre de `ssh-keygen`, et surtout sans écrire de clé privée depuis
    une suite de tests.
    """
    (tmp_path / "meta.yml").write_text(META_MINIMAL, encoding="utf-8")
    ssh_dir = tmp_path / "ssh"
    ssh_dir.mkdir()
    (ssh_dir / "id_ed25519").write_text("clé factice", encoding="utf-8")
    (ssh_dir / "id_ed25519.pub").write_text("clé publique factice", encoding="utf-8")

    resultat = runner.invoke(
        app, ["instructor", "bootstrap", "--lab-home", str(tmp_path)]
    )

    assert resultat.exit_code == 0
    # La clé en place n'est pas écrasée : c'est celle des VM déjà provisionnées.
    assert (ssh_dir / "id_ed25519").read_text(encoding="utf-8") == "clé factice"
