"""``doc_url`` et ``criteria[].lessons`` se traduisent par ``lab.<lang>.yaml`` (0.9.3).

Une leçon du site existe dans chaque langue, à une URL qui ne se déduit pas de
l'autre (``/docs/admin-serveurs/linux/`` devient ``/en/docs/linux/``). Avant
0.9.3, un lab n'avait qu'un ``doc_url`` : ``guide`` envoyait un apprenant
anglophone sur la page française, et ``lab.fr.yaml`` ne pouvait rien y faire.
``lab.yaml`` porte désormais l'URL anglaise, ``lab.fr.yaml`` la française,
comme pour ``title``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.models.lab import LabDefinition, langues_traduites
from dsoxlab.services.scaffold import creer_catalogue, creer_lab
from dsoxlab.validators import content
from dsoxlab.validators.contract import validate_unknown_keys
from dsoxlab.validators.metadata import validate_metadata

runner = CliRunner()

EN = "https://site.test/en/docs/linux/"
FR = "https://site.test/docs/admin-serveurs/linux/"
LECON_EN = "https://site.test/en/docs/linux/ssh/"
LECON_FR = "https://site.test/docs/admin-serveurs/linux/ssh/"


def _lab(dossier: Path, traduction: str | None) -> Path:
    dossier.mkdir(parents=True)
    (dossier / "lab.yaml").write_text(
        "id: lab-a\ntitle: Title\nlevel: l1\nskills: [s]\ndistros: [d]\n"
        f"doc_url: {EN}\n"
        "criteria:\n"
        "  - id: ssh\n    tests: [test_ssh]\n    label: SSH is hardened\n"
        f"    lessons: [{LECON_EN}]\n"
        "  - id: autre\n    tests: [test_autre]\n    label: Other\n",
        encoding="utf-8",
    )
    if traduction is not None:
        (dossier / "lab.fr.yaml").write_text(traduction, encoding="utf-8")
    return dossier / "lab.yaml"


class TestLeModele:
    def test_la_langue_de_la_session_choisit_le_doc_url(self, tmp_path: Path) -> None:
        lab_yaml = _lab(tmp_path / "lab-a", f"title: Titre\ndoc_url: {FR}\n")
        assert LabDefinition.from_yaml(lab_yaml, "en").doc_url == EN
        assert LabDefinition.from_yaml(lab_yaml, "fr").doc_url == FR

    def test_sans_doc_url_traduit_la_langue_herite_de_l_anglais(self, tmp_path: Path) -> None:
        lab_yaml = _lab(tmp_path / "lab-a", "title: Titre\n")
        assert LabDefinition.from_yaml(lab_yaml, "fr").doc_url == EN

    def test_les_lecons_se_traduisent_par_critere(self, tmp_path: Path) -> None:
        """Le libellé reste anglais quand la traduction ne donne que les leçons."""
        lab_yaml = _lab(
            tmp_path / "lab-a",
            f"criteria:\n  - id: ssh\n    lessons: [{LECON_FR}]\n",
        )
        ssh, autre = LabDefinition.from_yaml(lab_yaml, "fr").criteria
        assert ssh.lessons == (LECON_FR,)
        assert ssh.label == "SSH is hardened"
        assert autre.lessons is None
        assert LabDefinition.from_yaml(lab_yaml, "en").criteria[0].lessons == (LECON_EN,)

    def test_un_libelle_traduit_garde_les_lecons_anglaises(self, tmp_path: Path) -> None:
        lab_yaml = _lab(
            tmp_path / "lab-a",
            "criteria:\n  - id: ssh\n    label: SSH est durci\n",
        )
        ssh = LabDefinition.from_yaml(lab_yaml, "fr").criteria[0]
        assert ssh.label == "SSH est durci"
        assert ssh.lessons == (LECON_EN,)

    def test_les_langues_traduites_excluent_l_anglais(self, tmp_path: Path) -> None:
        lab_yaml = _lab(tmp_path / "lab-a", "title: Titre\n")
        (lab_yaml.parent / "lab.en.yaml").write_text("title: x\n", encoding="utf-8")
        (lab_yaml.parent / "lab.de.yaml").write_text("title: x\n", encoding="utf-8")
        assert langues_traduites(lab_yaml) == ("de", "fr")


def _cles(lab_yaml: Path, champ: str) -> list[str]:
    rapport = validate_metadata(LabDefinition.from_yaml(lab_yaml, "en"))
    return [i.key for i in rapport.issues if i.field == champ]


class TestLeControleHorsLigne:
    def test_un_doc_url_traduit_sans_schema_web_est_signale(self, tmp_path: Path) -> None:
        lab_yaml = _lab(tmp_path / "lab-a", "doc_url: ftp://site.test/docs/\n")
        assert _cles(lab_yaml, "doc_url (fr)") == ["metadata_doc_url_scheme"]

    def test_un_doc_url_traduit_mais_vide_est_signale(self, tmp_path: Path) -> None:
        lab_yaml = _lab(tmp_path / "lab-a", 'doc_url: ""\n')
        assert _cles(lab_yaml, "doc_url (fr)") == ["metadata_field_empty"]

    def test_un_doc_url_traduit_correct_ne_dit_rien(self, tmp_path: Path) -> None:
        lab_yaml = _lab(tmp_path / "lab-a", f"doc_url: {FR}\n")
        assert _cles(lab_yaml, "doc_url (fr)") == []

    def test_une_lecon_traduite_invalide_est_signalee(self, tmp_path: Path) -> None:
        lab_yaml = _lab(
            tmp_path / "lab-a",
            "criteria:\n  - id: ssh\n    lessons: [pas-une-url]\n",
        )
        assert "metadata_lecon_url_invalide" in _cles(lab_yaml, "criteria")

    def test_une_lecon_heritee_n_est_pas_signalee_deux_fois(self, tmp_path: Path) -> None:
        """Une URL anglaise fautive se dit une fois, pas une fois par langue."""
        dossier = tmp_path / "lab-a"
        lab_yaml = _lab(dossier, "title: Titre\n")
        texte = lab_yaml.read_text(encoding="utf-8").replace(LECON_EN, "pas-une-url")
        lab_yaml.write_text(texte, encoding="utf-8")
        assert _cles(lab_yaml, "criteria").count("metadata_lecon_url_invalide") == 1


@pytest.fixture
def catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "maison"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.setenv("DSOXLAB_NO_UPDATE_CHECK", "1")
    racine = creer_catalogue("traduit", tmp_path).racine
    creer_lab("lab-a", racine, runtime="shell")
    dossier = racine / "labs" / "lab-a"
    data = yaml.safe_load((dossier / "lab.yaml").read_text(encoding="utf-8"))
    data["doc_url"] = EN
    (dossier / "lab.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    fr = dossier / "lab.fr.yaml"
    traduction = yaml.safe_load(fr.read_text(encoding="utf-8")) if fr.exists() else {}
    traduction["doc_url"] = FR
    fr.write_text(yaml.safe_dump(traduction, allow_unicode=True), encoding="utf-8")
    return racine


class TestLaCommande:
    def test_doc_url_traduit_n_est_pas_une_cle_hors_contrat(self, catalogue: Path) -> None:
        assert validate_unknown_keys(catalogue).issues == []

    def test_la_lecon_traduite_n_est_pas_une_cle_hors_contrat(self, catalogue: Path) -> None:
        fr = catalogue / "labs" / "lab-a" / "lab.fr.yaml"
        fr.write_text(
            fr.read_text(encoding="utf-8")
            + f"criteria:\n  - id: ssh\n    label: SSH\n    lessons: [{LECON_FR}]\n",
            encoding="utf-8",
        )
        assert validate_unknown_keys(catalogue).issues == []

    def test_le_catalogue_traduit_est_conforme(self, catalogue: Path) -> None:
        resultat = runner.invoke(app, ["validate-structure", "--lab-home", str(catalogue)])
        assert resultat.exit_code == 0, resultat.output

    @pytest.mark.parametrize(("langue", "attendue"), [("en", EN), ("fr", FR)])
    def test_guide_rend_l_url_de_la_langue(
        self, catalogue: Path, monkeypatch: pytest.MonkeyPatch, langue: str, attendue: str
    ) -> None:
        monkeypatch.setenv("DSOXLAB_LANG", langue)
        resultat = runner.invoke(
            app, ["guide", "lab-a", "--print", "--lab-home", str(catalogue)]
        )
        assert resultat.exit_code == 0, resultat.output
        assert resultat.output.strip().startswith(attendue), resultat.output

    def test_check_urls_interroge_aussi_l_url_traduite(
        self, catalogue: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        interrogees: list[str] = []

        def _faux(lab: LabDefinition, **_k: object) -> None:
            interrogees.append(lab.doc_url)

        monkeypatch.setattr(content, "check_doc_url", _faux)
        resultat = runner.invoke(
            app, ["validate-structure", "--check-urls", "--lab-home", str(catalogue)]
        )
        assert resultat.exit_code == 0, resultat.output
        assert sorted(interrogees) == sorted([EN, FR])
