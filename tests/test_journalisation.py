"""Le moteur savait, mais ne le disait à personne.

Onze modules écrivent dans un logger. Aucun de ces messages n'atteignait
l'utilisateur ni un fichier. Le cas le plus coûteux : un `lab.yaml` qui lève au
parsing est avalé par un `logger.warning` puis un `continue`, donc le lab
disparaît du catalogue sans un mot. C'est le premier symptôme que rencontre un
auteur, et le plus difficile à diagnostiquer.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab import logging_setup
from dsoxlab.cli import app

runner = CliRunner()

META = "repo:\n  id: demo\n  category: demo\n"

#: Un lab.yaml qui lève au parsing : `runtime.type` doit être une chaîne.
LAB_CASSE = "id: casse\ntitle: Casse\nlevel: l1\nruntime:\n  type: [pas, une, chaine]\n"


@pytest.fixture
def catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Un catalogue dont un seul lab est invalide, et un état XDG isolé."""
    (tmp_path / "meta.yml").write_text(META, encoding="utf-8")
    casse = tmp_path / "labs" / "demo" / "l1" / "lab-casse"
    casse.mkdir(parents=True)
    (casse / "lab.yaml").write_text(LAB_CASSE, encoding="utf-8")

    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.delenv("DSOXLAB_LOG", raising=False)
    return tmp_path


def test_un_lab_yaml_invalide_ne_disparait_plus_en_silence(catalogue: Path) -> None:
    """Le défaut d'origine : le lab s'évapore, et rien ne le signale.

    Un avertissement n'est pas du bruit ici : il annonce une perte réelle de
    contenu, que l'auteur comme l'apprenant ont besoin de voir.
    """
    resultat = runner.invoke(app, ["list-labs"])

    assert "lab.yaml" in resultat.stderr
    assert "lab-casse" in resultat.stderr


def test_le_journal_est_ecrit_meme_sans_option(catalogue: Path) -> None:
    """C'est ce qui permet de joindre une trace APRÈS coup.

    Sans fichier, diagnostiquer un incident suppose de demander à l'utilisateur
    de reproduire, avec la bonne option, ce qui coûte un aller-retour complet.
    """
    runner.invoke(app, ["list-labs"])

    journal = catalogue / "etat" / "dsoxlab" / "dsoxlab.log"
    assert journal.is_file()
    assert "lab.yaml" in journal.read_text(encoding="utf-8")


def test_le_mode_verbeux_ajoute_le_detail(catalogue: Path) -> None:
    """`-vv` fait remonter le DEBUG, que le niveau par défaut retient."""
    normal = runner.invoke(app, ["list-labs"])
    bavard = runner.invoke(app, ["-vv", "list-labs"])

    assert len(bavard.stderr) >= len(normal.stderr)


def test_la_sortie_json_reste_lisible_par_un_programme(catalogue: Path) -> None:
    """Le contrat qui interdit d'écrire les logs sur stdout.

    Un seul octet de diagnostic sur la sortie standard casserait tout
    consommateur machine, et c'est précisément en mode verbeux qu'on serait
    tenté d'en ajouter.
    """
    resultat = runner.invoke(app, ["-vv", "list-labs", "--json"])

    charge = json.loads(resultat.stdout)
    assert "labs" in charge
    # Le diagnostic doit bien exister quelque part : sinon ce test passerait
    # aussi sur une version qui n'écrit rien du tout.
    assert "lab.yaml" in resultat.stderr


def test_la_variable_d_environnement_regle_le_niveau(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pour les cas où l'on ne contrôle pas la ligne de commande."""
    monkeypatch.setenv("DSOXLAB_LOG", "debug")
    logging_setup.configurer(0)

    assert logging.getLogger("dsoxlab").isEnabledFor(logging.DEBUG)

    # On identifie NOS handlers par leur marqueur, pas par leur type : pytest
    # attache ses propres LogCaptureHandler à ce logger, et ils héritent eux
    # aussi de StreamHandler. C'est précisément à quoi sert ce marqueur, et
    # c'est ce qui permet à `configurer()` de ne retirer que les siens.
    notres = [
        h for h in logging.getLogger("dsoxlab").handlers
        if getattr(h, logging_setup._MARQUEUR, False)
    ]
    console = [h for h in notres if not isinstance(h, logging.FileHandler)]
    assert console and console[0].level == logging.DEBUG


def test_une_valeur_d_environnement_absurde_est_ignoree(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une faute de frappe dans un .bashrc ne doit pas casser la CLI."""
    monkeypatch.setenv("DSOXLAB_LOG", "trace-moi-tout")
    logging_setup.configurer(0)

    resultat = runner.invoke(app, ["list-labs"])
    assert resultat.exit_code == 0


def test_configurer_deux_fois_n_empile_pas_les_handlers(catalogue: Path) -> None:
    """Sinon chaque message apparaîtrait autant de fois qu'il y a eu d'appels."""
    logging_setup.configurer(1)
    apres_un = len(logging.getLogger("dsoxlab").handlers)
    logging_setup.configurer(1)
    apres_deux = len(logging.getLogger("dsoxlab").handlers)

    assert apres_un == apres_deux


def test_un_journal_impossible_a_ecrire_ne_casse_rien(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un HOME en lecture seule ne doit pas empêcher de jouer un lab.

    Le journal est un confort, jamais une dépendance.
    """
    def _refuse(*args: object, **kwargs: object) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr(Path, "mkdir", _refuse)
    logging_setup.configurer(0)

    resultat = runner.invoke(app, ["list-labs"])
    assert resultat.exit_code == 0


def test_les_dernieres_lignes_sont_lisibles(catalogue: Path) -> None:
    """Matière du futur `dsoxlab support` (#75)."""
    runner.invoke(app, ["list-labs"])

    lignes = logging_setup.dernieres_lignes(5)
    assert lignes
    assert any("lab.yaml" in ligne for ligne in lignes)


def test_les_dernieres_lignes_sans_journal_rendent_une_liste_vide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un rapport sans traces reste utile ; une exception en produisant un, non."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "vide"))

    assert logging_setup.dernieres_lignes() == []
