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

import pytest
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


def test_un_vrai_depot_de_labs_passe_le_garde_fou(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Avec `meta.yml`, la commande travaille normalement.

    On lui présente une clé déjà en place : le chemin nominal est donc couvert
    sans dépendre de `ssh-keygen`, et surtout sans écrire de clé privée depuis
    une suite de tests.

    L'outillage est stubé présent : depuis que le code de retour reflète les
    outils manquants, ce test mesurerait sinon la machine qui l'exécute, et il
    tomberait sur un runner CI dépourvu de terraform.
    """
    from dsoxlab.infra import ansible as ansible_infra
    from dsoxlab.infra import terraform as tf

    monkeypatch.setattr(tf, "is_available", lambda: True)
    monkeypatch.setattr(ansible_infra, "is_available", lambda: True)
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


def test_le_code_de_retour_dit_la_meme_chose_que_l_ecran(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sortir en 0 après avoir affiché une erreur bloquante trompe deux fois.

    Mesuré sur une machine neuve : la commande affichait « ✘ terraform absent
    du PATH » puis rendait 0. Un apprenant qui vérifie son code de retour, ou
    un script d'installation, en concluait que tout allait bien, alors que la
    clé venait d'être créée pour une infrastructure que rien ne pourra
    provisionner.
    """
    from dsoxlab.infra import ansible as ansible_infra
    from dsoxlab.infra import terraform as tf

    (tmp_path / "meta.yml").write_text(META_MINIMAL, encoding="utf-8")
    monkeypatch.setattr(tf, "is_available", lambda: False)
    monkeypatch.setattr(ansible_infra, "is_available", lambda: True)

    resultat = runner.invoke(
        app, ["instructor", "bootstrap", "--lab-home", str(tmp_path)]
    )

    assert resultat.exit_code == 1, (
        "un outil requis manquant doit se voir dans le code de retour"
    )
    # La clé, elle, a bien été générée : l'échec porte sur l'outillage, et le
    # dire sans avoir rien fait serait tout aussi faux.
    assert (tmp_path / "ssh" / "id_ed25519").is_file()


def test_tout_en_place_sort_en_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dsoxlab.infra import ansible as ansible_infra
    from dsoxlab.infra import terraform as tf

    (tmp_path / "meta.yml").write_text(META_MINIMAL, encoding="utf-8")
    monkeypatch.setattr(tf, "is_available", lambda: True)
    monkeypatch.setattr(ansible_infra, "is_available", lambda: True)

    resultat = runner.invoke(
        app, ["instructor", "bootstrap", "--lab-home", str(tmp_path)]
    )

    assert resultat.exit_code == 0
