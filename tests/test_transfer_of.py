"""`transfer_of` : la variante de transfert déclarée par un lab.

Une variante éprouve la même capacité dans un autre contexte. Le moteur ne
décide rien de ce que cela vaut : il vérifie que la relation est bien formée,
l'expose, et laisse à la variante son identifiant et ses résultats.

Les contrôles qui comptent : une cible qui n'existe pas ne casse aucun test et
ne fait échouer aucun run, une chaîne de variantes rend la famille illisible, et
surtout un catalogue sans `transfer_of` doit se comporter exactement comme avant.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.discovery.scanner import discover_labs
from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.reporting import machine
from dsoxlab.services.validation_service import valider
from dsoxlab.validators import content

runner = CliRunner()


def _lab(
    chemin: Path, id_: str, transfer_of: str | None = None, lab_type: str = "lab"
) -> LabDefinition:
    return LabDefinition(
        id=id_,
        title=f"Lab {id_}",
        level="l1",
        path=chemin / id_,
        doc_url="https://example.test/guide",
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="work"),
        skills=["capacite"],
        distros=["alma10"],
        validation=ValidationConfig(),
        lab_type=lab_type,
        transfer_of=transfer_of,
    )


def _catalogue(chemin: Path, *labs: LabDefinition) -> dict[str, LabDefinition]:
    return {lab.id: lab for lab in labs}


def _cles(rapport: content.ContentReport) -> list[str]:
    return [souci.key for souci in rapport.issues]


class TestContrat:
    def test_une_variante_bien_formee_passe(self, tmp_path: Path) -> None:
        origine = _lab(tmp_path, "origine")
        variante = _lab(tmp_path, "variante", transfer_of="origine")

        rapport = content.validate_transfer(variante, _catalogue(tmp_path, origine, variante))

        assert rapport.ok

    def test_une_variante_peut_etre_un_challenge_ou_un_capstone(self, tmp_path: Path) -> None:
        origine = _lab(tmp_path, "origine")
        for forme in ("lab", "challenge", "capstone"):
            variante = _lab(tmp_path, f"v-{forme}", transfer_of="origine", lab_type=forme)
            assert content.validate_transfer(
                variante, _catalogue(tmp_path, origine, variante)
            ).ok, forme

    def test_plusieurs_variantes_partagent_une_origine(self, tmp_path: Path) -> None:
        origine = _lab(tmp_path, "origine")
        un = _lab(tmp_path, "un", transfer_of="origine")
        deux = _lab(tmp_path, "deux", transfer_of="origine")
        labs = _catalogue(tmp_path, origine, un, deux)

        assert content.validate_transfer(un, labs).ok
        assert content.validate_transfer(deux, labs).ok

    def test_sans_transfer_of_le_controle_se_tait(self, tmp_path: Path) -> None:
        assert content.validate_transfer(_lab(tmp_path, "seul"), {}).ok

    def test_une_cible_absente_du_catalogue_est_signalee(self, tmp_path: Path) -> None:
        variante = _lab(tmp_path, "variante", transfer_of="renomme-hier")

        rapport = content.validate_transfer(variante, _catalogue(tmp_path, variante))

        (souci,) = rapport.issues
        assert souci.key == "content_transfer_unknown"
        assert souci.params == {"target": "renomme-hier"}

    def test_un_lab_ne_peut_pas_etre_sa_propre_origine(self, tmp_path: Path) -> None:
        lab = _lab(tmp_path, "boucle", transfer_of="boucle")

        rapport = content.validate_transfer(lab, _catalogue(tmp_path, lab))

        assert _cles(rapport) == ["content_transfer_self"]

    def test_une_chaine_de_variantes_est_refuse(self, tmp_path: Path) -> None:
        """Une famille est un lab d'origine et ses variantes, jamais une chaîne."""
        origine = _lab(tmp_path, "origine")
        premiere = _lab(tmp_path, "premiere", transfer_of="origine")
        seconde = _lab(tmp_path, "seconde", transfer_of="premiere")
        labs = _catalogue(tmp_path, origine, premiere, seconde)

        assert content.validate_transfer(premiere, labs).ok
        rapport = content.validate_transfer(seconde, labs)
        (souci,) = rapport.issues
        assert souci.key == "content_transfer_chain"
        assert souci.params == {"target": "premiere", "origin": "origine"}

    def test_un_cycle_est_refuse_des_deux_cotes(self, tmp_path: Path) -> None:
        a = _lab(tmp_path, "a", transfer_of="b")
        b = _lab(tmp_path, "b", transfer_of="a")
        labs = _catalogue(tmp_path, a, b)

        assert _cles(content.validate_transfer(a, labs)) == ["content_transfer_chain"]
        assert _cles(content.validate_transfer(b, labs)) == ["content_transfer_chain"]

    @pytest.mark.parametrize("valeur", ["", " ", "a b", "../autre", "a/b", "-debut", "é", "x" * 129])
    def test_une_forme_invalide_est_signalee(self, tmp_path: Path, valeur: str) -> None:
        variante = _lab(tmp_path, "variante", transfer_of=valeur)

        rapport = content.validate_transfer(variante, _catalogue(tmp_path, variante))

        (souci,) = rapport.issues
        assert souci.key == "content_transfer_invalid_id"
        assert souci.params == {"value": valeur}

    def test_un_lab_de_validation_n_entre_dans_aucune_famille(self, tmp_path: Path) -> None:
        origine = _lab(tmp_path, "origine")
        garde = _lab(tmp_path, "garde", lab_type="validation")
        variante_validation = _lab(tmp_path, "v", transfer_of="origine", lab_type="validation")
        variante_de_garde = _lab(tmp_path, "w", transfer_of="garde")
        labs = _catalogue(tmp_path, origine, garde, variante_validation, variante_de_garde)

        assert _cles(content.validate_transfer(variante_validation, labs)) == [
            "content_transfer_validation"]
        assert _cles(content.validate_transfer(variante_de_garde, labs)) == [
            "content_transfer_validation"]


class TestLecture:
    def test_le_champ_est_lu_dans_le_lab_yaml(self, tmp_path: Path) -> None:
        fichier = tmp_path / "lab.yaml"
        fichier.write_text(
            "id: v\ntitle: V\nlevel: l1\ntransfer_of: origine\n", encoding="utf-8"
        )
        assert LabDefinition.from_yaml(fichier).transfer_of == "origine"

    def test_absent_vaut_none(self, tmp_path: Path) -> None:
        fichier = tmp_path / "lab.yaml"
        fichier.write_text("id: v\ntitle: V\nlevel: l1\n", encoding="utf-8")
        assert LabDefinition.from_yaml(fichier).transfer_of is None

    def test_une_valeur_non_chaine_reste_signalable(self, tmp_path: Path) -> None:
        """Le lab ne disparaît pas : `validate-structure` dit pourquoi c'est faux."""
        fichier = tmp_path / "lab.yaml"
        fichier.write_text(
            "id: v\ntitle: V\nlevel: l1\ntransfer_of: [a, b]\n", encoding="utf-8"
        )
        lab = LabDefinition.from_yaml(fichier)
        assert lab.transfer_of is not None
        assert _cles(content.validate_transfer(lab, {lab.id: lab})) == [
            "content_transfer_invalid_id"]


# ── dans un vrai catalogue, par la CLI ────────────────────────────────────────

def _declarer(catalogue: Path, ident: str, ligne: str) -> None:
    lab = catalogue / "labs" / "domaine" / ident / "lab.yaml"
    lab.write_text(lab.read_text(encoding="utf-8") + ligne + "\n", encoding="utf-8")


def _document(*args: str) -> Any:
    resultat = runner.invoke(app, [*args, "--json"])
    assert resultat.exit_code == 0, resultat.stderr
    return json.loads(resultat.stdout)


def _cles_du_catalogue(catalogue: Path) -> list[str]:
    rapport = valider(catalogue, discover_labs(catalogue))
    return [a.cle for a in rapport.anomalies]


class TestCatalogue:
    def test_un_catalogue_sans_transfer_of_valide_comme_avant(self, catalogue: Path) -> None:
        assert not [c for c in _cles_du_catalogue(catalogue) if c.startswith("content_transfer")]

    def test_validate_structure_accepte_une_variante(self, catalogue: Path) -> None:
        _declarer(catalogue, "second", "transfer_of: premier")

        assert _cles_du_catalogue(catalogue) == []

    def test_validate_structure_refuse_une_cible_absente(self, catalogue: Path) -> None:
        _declarer(catalogue, "second", "transfer_of: introuvable")

        assert "content_transfer_unknown" in _cles_du_catalogue(catalogue)

    def test_la_cle_n_est_pas_signalee_comme_hors_contrat(self, catalogue: Path) -> None:
        _declarer(catalogue, "second", "transfer_of: premier")

        assert not [c for c in _cles_du_catalogue(catalogue) if "unknown_key" in c
                    or "cle_inconnue" in c]

    def test_show_json_expose_la_relation(self, catalogue: Path) -> None:
        _declarer(catalogue, "second", "transfer_of: premier")

        assert _document("show", "second")["lab"]["transfer_of"] == "premier"
        assert _document("show", "premier")["lab"]["transfer_of"] is None

    def test_list_labs_json_expose_la_relation(self, catalogue: Path) -> None:
        _declarer(catalogue, "second", "transfer_of: premier")

        par_id = {lab["id"]: lab for lab in _document("list-labs")["labs"]}

        assert par_id["second"]["transfer_of"] == "premier"
        assert par_id["premier"]["transfer_of"] is None

    @pytest.mark.parametrize(
        ("langue", "attendu"),
        [("en", "Transfer variant of:"), ("fr", "Variante de transfert de :")],
    )
    def test_show_dit_la_relation_dans_la_langue_du_lecteur(
        self, catalogue: Path, monkeypatch: pytest.MonkeyPatch, langue: str, attendu: str
    ) -> None:
        _declarer(catalogue, "second", "transfer_of: premier")
        monkeypatch.setenv("DSOXLAB_LANG", langue)

        resultat = runner.invoke(app, ["show", "second"])

        assert resultat.exit_code == 0, resultat.stderr
        assert attendu in resultat.stdout
        assert "premier" in resultat.stdout

    def test_show_ne_dit_rien_sans_variante(self, catalogue: Path) -> None:
        resultat = runner.invoke(app, ["show", "premier"])

        assert "Transfer variant" not in resultat.stdout

    def test_la_variante_garde_son_identifiant_et_ses_resultats(self, catalogue: Path) -> None:
        """Rien ne change dans la base, l'export ni le score : la note est celle du lab."""
        from dsoxlab.sessions.store import record_result

        _declarer(catalogue, "second", "transfer_of: premier")
        record_result(
            catalogue, lab_id="second", section="domaine", score=80, max_score=100,
            passed_tests=4, total_tests=5, hints_used=0,
        )

        par_id = {lab["id"]: lab for lab in _document("list-labs")["labs"]}

        assert par_id["second"]["best_score"] == {"points": 80, "max": 100}
        assert par_id["premier"]["best_score"] is None


class TestSansRegression:
    def test_seul_le_champ_nouveau_distingue_la_sortie(self, tmp_path: Path) -> None:
        """Hors `transfer_of`, le document d'un lab sans variante est celui d'avant."""
        document = machine.lab_dict(_lab(tmp_path, "seul"))

        assert document.pop("transfer_of") is None
        assert set(document) == {
            "id", "title", "section", "bloc", "bloc_order", "level", "type",
            "exam_passing_score", "difficulty", "estimated_time", "skills",
            "distros", "prerequisites", "doc_url", "path", "runtime", "best_score",
        }
