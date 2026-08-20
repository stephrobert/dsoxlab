"""Le catalogue de démonstration, et le parcours qu'il doit rendre possible.

Entre `uv tool install dsoxlab` et le premier lab joué, il y avait une
connaissance implicite : savoir que les labs vivent dans d'autres dépôts, savoir
lesquels, savoir qu'il faut se placer dedans. Qui lançait l'outil là où il se
trouvait n'obtenait rien, avec un code de retour 0 pour dire que tout allait
bien.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.services import demo
from dsoxlab.templates import demo_catalog

runner = CliRunner()

#: Les réponses attendues, et où l'apprenant lit chaque mot.
REPONSES = {
    "cours.txt": "catalogue",
    "mission.txt": "challenge",
    "indice.txt": "progression",
}


@pytest.fixture
def maison(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.delenv("LAB_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ── le catalogue packagé respecte le contrat qu'il enseigne ───────────────────

def test_le_catalogue_est_bien_empaquete() -> None:
    """Livré avec l'outil : il doit exister dans l'arbre du paquet."""
    racine = demo_catalog()

    assert (racine / "meta.yml").is_file()
    labs = list((racine / "labs").rglob("lab.yaml"))
    assert labs, "le catalogue de démonstration doit contenir au moins un lab"


def test_le_lab_porte_les_fichiers_exiges_par_le_contrat() -> None:
    """Un lab de démonstration qui violerait le contrat serait le pire exemple.

    C'est le tout premier lab que voit un utilisateur : il doit être conforme,
    et il doit rester jouable sans infrastructure.
    """
    lab = next((demo_catalog() / "labs").rglob("lab.yaml")).parent

    for exige in (
        "lab.yaml", "README.md", "scenario.md",
        "challenge/tests/test_functional.py",
    ):
        assert (lab / exige).is_file(), f"{exige} manquant"

    # Le conftest est ce qui place pytest dans le répertoire de travail :
    # sans lui, les tests cherchent les réponses à la racine du catalogue et
    # trois cas rouges sanctionnent un travail pourtant juste.
    assert (lab / "challenge" / "tests" / "conftest.py").is_file()

    contenu = (lab / "lab.yaml").read_text(encoding="utf-8")
    assert "type: shell" in contenu, "le lab de démonstration ne doit exiger aucune VM"


def test_la_parite_de_langue_est_tenue() -> None:
    """Un document traduit d'un seul côté est signalé par le validator."""
    lab = next((demo_catalog() / "labs").rglob("lab.yaml")).parent

    for base in ("README", "scenario", "challenge/README"):
        assert (lab / f"{base}.md").is_file()
        assert (lab / f"{base}.fr.md").is_file(), f"{base}.fr.md manquant"


# ── l'installation ────────────────────────────────────────────────────────────

def test_l_installation_pose_un_catalogue_jouable(maison: Path) -> None:
    resultat = runner.invoke(app, ["demo"])

    assert resultat.exit_code == 0, resultat.output
    cible = demo.destination()
    assert (cible / "meta.yml").is_file()
    assert list((cible / "labs").rglob("lab.yaml"))


def test_une_installation_existante_n_est_jamais_ecrasee(maison: Path) -> None:
    """Ce répertoire porte la progression et les réponses de l'apprenant.

    Une réinstallation silencieuse effacerait un lab en cours de résolution,
    ce qu'on ne pardonne pas à un outil.
    """
    runner.invoke(app, ["demo"])
    temoin = demo.destination() / "labs" / "temoin.txt"
    temoin.write_text("le travail de l'apprenant", encoding="utf-8")

    resultat = runner.invoke(app, ["demo"])

    assert resultat.exit_code == 1
    assert temoin.is_file(), "le travail en place a été détruit"
    assert temoin.read_text(encoding="utf-8") == "le travail de l'apprenant"


def test_force_reinstalle_vraiment(maison: Path) -> None:
    runner.invoke(app, ["demo"])
    temoin = demo.destination() / "labs" / "temoin.txt"
    temoin.write_text("ancien", encoding="utf-8")

    resultat = runner.invoke(app, ["demo", "--force"])

    assert resultat.exit_code == 0
    assert not temoin.exists(), "--force doit repartir d'un catalogue propre"


def test_la_marche_a_suivre_nomme_le_lab_reellement_installe(maison: Path) -> None:
    """Elle est construite depuis le catalogue posé, pas recopiée à la main.

    Le jour où le catalogue de démonstration change de lab, ce qui s'affiche
    suit tout seul.
    """
    resultat = runner.invoke(app, ["demo"])

    # Rich replie les longues lignes : on compare sur une sortie recollée,
    # sinon le test échoue sur un retour à la ligne et non sur le fond.
    sortie = resultat.output.replace("\n", "")
    lab = next((demo.destination() / "labs").rglob("lab.yaml")).parent.name

    assert lab in sortie
    assert str(demo.destination()).replace("\n", "") in sortie


# ── le parcours complet, joué pour de vrai ────────────────────────────────────

def test_de_l_installation_au_100_sur_100(maison: Path) -> None:
    """Le test qui justifie tout le reste : l'outil se démontre lui-même.

    On joue le parcours d'un débutant en entier, dans un sous-processus, avec
    la CLI réelle : installer, échouer à froid, répondre, réussir.
    """
    assert runner.invoke(app, ["demo"]).exit_code == 0
    catalogue = demo.destination()

    binaire = Path(sys.executable).parent / "dsoxlab"
    if not binaire.exists():
        pytest.skip("script console dsoxlab absent de cet environnement")

    def dsoxlab(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 : c'est notre propre CLI
            [str(binaire), *args],
            cwd=catalogue, capture_output=True, text=True, timeout=120,
        )

    avant = dsoxlab("check", "premiers-pas")
    assert "0 / 100" in avant.stdout or "0/100" in avant.stdout, (
        f"un lab non résolu doit valoir 0 : {avant.stdout[-300:]}"
    )

    work = next((catalogue / "labs").rglob("lab.yaml")).parent / "challenge" / "work"
    (work / "reponses").mkdir(parents=True, exist_ok=True)
    for fichier, mot in REPONSES.items():
        (work / "reponses" / fichier).write_text(mot + "\n", encoding="utf-8")

    apres = dsoxlab("check", "premiers-pas")
    assert "100 / 100" in apres.stdout or "100/100" in apres.stdout, (
        f"le parcours complet doit valoir 100 : {apres.stdout[-300:]}"
    )
