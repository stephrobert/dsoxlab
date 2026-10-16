"""Un catalogue vide dit-il pourquoi ?

« Aucun lab trouvé. » en sortant en 0 était la réponse de `list-labs`,
`status`, `progress` et `scores` sur un poste sans catalogue : un écran léger,
et une impasse. Rien n'y disait qu'aucun catalogue n'était actif, ni quoi
faire, alors que `catalog use` sur un catalogue absent savait déjà le dire
parfaitement. La bonne phrase existait, elle n'était pas prononcée là où
l'apprenant arrive.

Trois causes mènent à un catalogue vide, et chacune appelle un geste
différent : aucun catalogue actif, un catalogue qui n'en déclare pas, ou des
`lab.yaml` qui lèvent au parsing. La troisième est la plus coûteuse à
diagnostiquer de tout le contrat, puisque le lab disparaît sans un mot.

Ce qui est éprouvé ici est la phrase ET le code de retour : il reste 0, parce
qu'un catalogue vide n'est pas une erreur et qu'un script qui lisait 0 doit
continuer de lire 0.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app

runner = CliRunner()

META_MINIMAL = "repo:\n  id: {id}\n  category: test\n"


@pytest.fixture(autouse=True)
def _poste_sans_catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un poste neuf : ni catalogue installé, ni pointeur d'actif.

    Sans cette isolation, le test lirait le catalogue réellement actif de la
    machine du développeur et passerait ou échouerait selon ce qu'il y a
    laissé.
    """
    for nom in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(nom, str(tmp_path / nom.lower()))
    monkeypatch.delenv("LAB_HOME", raising=False)


def test_sans_catalogue_la_cause_et_le_geste_sont_dits(tmp_path: Path) -> None:
    maison = tmp_path / "maison"
    maison.mkdir()
    resultat = runner.invoke(app, ["list-labs", "--lab-home", str(maison)])

    assert resultat.exit_code == 0, resultat.stderr
    assert "demo" in resultat.stderr, "le geste le plus sûr doit être nommé"
    assert "catalog add" in resultat.stderr


def test_un_catalogue_sans_lab_le_dit(tmp_path: Path) -> None:
    racine = tmp_path / "vidon"
    (racine / "labs").mkdir(parents=True)
    (racine / "meta.yml").write_text(META_MINIMAL.format(id="vidon"), encoding="utf-8")

    resultat = runner.invoke(app, ["list-labs", "--lab-home", str(racine)])

    assert resultat.exit_code == 0, resultat.stderr
    assert "labs/" in resultat.stderr


def test_un_lab_yaml_qui_leve_est_nomme(tmp_path: Path) -> None:
    """Le piège le plus coûteux du contrat : un lab qui disparaît en silence."""
    racine = tmp_path / "casse"
    mauvais = racine / "labs" / "test" / "mauvais"
    mauvais.mkdir(parents=True)
    (racine / "meta.yml").write_text(META_MINIMAL.format(id="casse"), encoding="utf-8")
    (mauvais / "lab.yaml").write_text("id: [ceci\n  nest: pas: du yaml\n", encoding="utf-8")

    resultat = runner.invoke(app, ["list-labs", "--lab-home", str(racine)])

    assert resultat.exit_code == 0, resultat.stderr
    assert "labs/test/mauvais/lab.yaml" in resultat.stderr, "le fichier fautif se nomme"
    assert "support" in resultat.stderr, "le geste qui donne le détail se nomme"


def test_la_cause_dun_parsing_tient_en_une_ligne(tmp_path: Path) -> None:
    """Un ParserError de PyYAML porte le chemin absolu deux fois.

    Affiché tel quel, cela donnait sept lignes repliées pour un seul fichier,
    dont six de redite avec le chemin relatif qu'on vient d'écrire.
    """
    racine = tmp_path / "casse2"
    mauvais = racine / "labs" / "test" / "mauvais"
    mauvais.mkdir(parents=True)
    (racine / "meta.yml").write_text(META_MINIMAL.format(id="casse2"), encoding="utf-8")
    (mauvais / "lab.yaml").write_text("id: [ceci\n  nest: pas: du yaml\n", encoding="utf-8")

    resultat = runner.invoke(app, ["list-labs", "--lab-home", str(racine)])

    lignes = resultat.stderr.splitlines()
    fautives = [ligne for ligne in lignes if "lab.yaml :" in ligne]
    assert len(fautives) == 1
    assert str(racine) not in fautives[0], "le chemin absolu ne doit pas revenir"


def test_le_document_json_ne_porte_aucune_de_ces_phrases(tmp_path: Path) -> None:
    """Le mode machine reste un document, et rien d'autre.

    Les phrases partent sur stderr : c'est ce qui permet de les ajouter sans
    toucher au contrat de `--json`.
    """
    import json

    maison = tmp_path / "maison"
    maison.mkdir()
    resultat = runner.invoke(app, ["list-labs", "--json", "--lab-home", str(maison)])

    assert resultat.exit_code == 0, resultat.stderr
    document = json.loads(resultat.stdout)
    assert document["labs"] == []


class TestDoctorNeLaissePasUnRougeNu:
    """« Labs détectés ✘ KO » sans un mot sur quoi faire.

    Vu en jouant le parcours d'un nouvel arrivant : juste après une
    installation réussie, `doctor` peignait « 0 lab » en rouge avec une colonne
    de remédiation vide. Un débutant en conclut que son installation est
    cassée.
    """

    def test_aucun_catalogue_propose_den_poser_un(self, tmp_path: Path) -> None:
        from dsoxlab.services.doctor import _check_labs

        check = _check_labs(tmp_path, [], 0)

        assert check.ok is False
        assert "demo" in check.remediation
        assert "catalog add" in check.remediation

    def test_des_labs_illisibles_renvoient_vers_la_liste(self, tmp_path: Path) -> None:
        """Deux causes, deux gestes : ici il y a des fichiers, mais ils lèvent."""
        from dsoxlab.services.doctor import _check_labs

        check = _check_labs(tmp_path, [], 3)

        assert check.ok is False
        assert "list-labs" in check.remediation

    def test_un_catalogue_sain_na_rien_a_remedier(self, tmp_path: Path) -> None:
        from dsoxlab.models.lab import LabDefinition, ValidationConfig
        from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
        from dsoxlab.services.doctor import _check_labs

        lab = LabDefinition(
            id="x",
            title="X",
            level="l1",
            path=tmp_path / "x",
            skills=["demo"],
            distros=["any"],
            doc_url="https://example.invalid/g",
            validation=ValidationConfig(),
            runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="challenge/work"),
        )
        check = _check_labs(tmp_path, [lab], 1)

        assert check.ok is True
        assert not check.remediation
