"""Les contrôles de contenu doivent trouver ce qu'aucun test fonctionnel ne voit.

Un lien mort, un guide disparu, une solution en clair : rien de tout cela
n'empêche un lab de s'exécuter. C'est précisément pourquoi ces défauts
survivaient. Ces tests vérifient donc surtout que le contrôle *échoue* quand il
le doit, et qu'il reste muet là où il n'a rien à dire.
"""

from __future__ import annotations

import urllib.error
from pathlib import Path

import pytest

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.validators import content


def _lab(chemin: Path, doc_url: str = "https://example.test/guide") -> LabDefinition:
    return LabDefinition(
        id="lab-test",
        title="Lab de test",
        level="l1",
        path=chemin,
        doc_url=doc_url,
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="work"),
        skills=["test"],
        distros=["almalinux10"],
        validation=ValidationConfig(),
    )


class TestLiensInternes:
    def test_un_lien_mort_est_signale(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "Voir [le lab](../autre/lab.md) pour la suite.", encoding="utf-8"
        )
        rapport = content.validate_internal_links(_lab(tmp_path))
        assert not rapport.ok
        assert "../autre/lab.md" in rapport.issues[0].message

    def test_un_lien_valide_ne_dit_rien(self, tmp_path: Path) -> None:
        (tmp_path / "cible.md").write_text("cible", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "Voir [la cible](./cible.md).", encoding="utf-8"
        )
        assert content.validate_internal_links(_lab(tmp_path)).ok

    def test_l_ancre_est_ignoree(self, tmp_path: Path) -> None:
        """`#section` est résolu par le lecteur Markdown, pas par le disque."""
        (tmp_path / "cible.md").write_text("cible", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "Voir [la section](./cible.md#une-section).", encoding="utf-8"
        )
        assert content.validate_internal_links(_lab(tmp_path)).ok

    def test_une_url_absolue_n_est_pas_de_son_ressort(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "Voir [le guide](https://example.test/absent).", encoding="utf-8"
        )
        assert content.validate_internal_links(_lab(tmp_path)).ok

    def test_lab_sans_markdown(self, tmp_path: Path) -> None:
        assert content.validate_internal_links(_lab(tmp_path)).ok


class TestSolutionsChiffrees:
    def test_une_solution_en_clair_est_signalee(self, tmp_path: Path) -> None:
        sol = tmp_path / "solution"
        sol.mkdir()
        (sol / "solution.yaml").write_text("- name: en clair\n", encoding="utf-8")
        rapport = content.validate_solutions_encrypted(_lab(tmp_path), sol)
        assert not rapport.ok
        assert "en clair" in rapport.issues[0].message

    def test_une_solution_chiffree_passe(self, tmp_path: Path) -> None:
        sol = tmp_path / "solution"
        sol.mkdir()
        (sol / "solution.yaml").write_text(
            "$ANSIBLE_VAULT;1.1;AES256\n3462383...\n", encoding="utf-8"
        )
        assert content.validate_solutions_encrypted(_lab(tmp_path), sol).ok

    def test_repertoire_absent_n_est_pas_une_faute(self, tmp_path: Path) -> None:
        """Un dépôt sans corrigés a fait un autre choix, pas une erreur."""
        assert content.validate_solutions_encrypted(
            _lab(tmp_path), tmp_path / "nexiste-pas"
        ).ok

    def test_un_readme_dans_solution_n_a_pas_a_etre_chiffre(
        self, tmp_path: Path
    ) -> None:
        sol = tmp_path / "solution"
        sol.mkdir()
        (sol / "README.md").write_text("Comment lire ces corrigés.", encoding="utf-8")
        assert content.validate_solutions_encrypted(_lab(tmp_path), sol).ok


class TestDocUrl:
    def test_url_qui_repond(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(content.urllib.request, "urlopen", _reponse(200))
        assert content.check_doc_url(_lab(tmp_path)) is None

    def test_page_disparue(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def _404(*_a: object, **_k: object) -> None:
            raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)  # type: ignore[arg-type]

        monkeypatch.setattr(content.urllib.request, "urlopen", _404)
        assert content.check_doc_url(_lab(tmp_path)) == "HTTP 404"

    def test_head_refuse_mais_get_repond(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Des sites refusent HEAD et servent GET : ce n'est pas une page morte."""
        appels: list[int] = []

        def _selon_appel(*_a: object, **_k: object) -> object:
            appels.append(1)
            if len(appels) == 1:
                raise urllib.error.HTTPError("u", 405, "Not Allowed", {}, None)  # type: ignore[arg-type]
            return _Reponse(200)

        monkeypatch.setattr(content.urllib.request, "urlopen", _selon_appel)
        assert content.check_doc_url(_lab(tmp_path)) is None
        assert len(appels) == 2

    def test_hors_ligne(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boum(*_a: object, **_k: object) -> None:
            raise urllib.error.URLError("network is unreachable")

        monkeypatch.setattr(content.urllib.request, "urlopen", _boum)
        motif = content.check_doc_url(_lab(tmp_path))
        assert motif is not None and "injoignable" in motif

    def test_schema_inattendu(self, tmp_path: Path) -> None:
        motif = content.check_doc_url(_lab(tmp_path, doc_url="ftp://exemple/guide"))
        assert motif is not None and "ftp" in motif

    def test_sans_doc_url(self, tmp_path: Path) -> None:
        assert content.check_doc_url(_lab(tmp_path, doc_url="")) is None


class _Reponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _Reponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _reponse(status: int):  # noqa: ANN202 - fabrique de doublure
    def _ouvrir(*_a: object, **_k: object) -> _Reponse:
        return _Reponse(status)

    return _ouvrir


class TestBareme:
    """Le score se calcule par test : un test de plus décale tout le barème."""

    def _lab_note(self, tmp_path: Path, taches: int, tests: int) -> LabDefinition:
        ch = tmp_path / "challenge"
        (ch / "tests").mkdir(parents=True)
        points = 100 // taches
        corps = f"**Format** : {taches} tâches, {points * taches} points.\n\n"
        corps += "".join(
            f"### Tâche {i} — quelque chose ({points} pts)\n\n" for i in range(1, taches + 1)
        )
        (ch / "README.fr.md").write_text(corps, encoding="utf-8")
        (ch / "tests" / "test_functional.py").write_text(
            "".join(f"def test_{i}(host):\n    assert True\n\n" for i in range(tests)),
            encoding="utf-8",
        )
        return _lab(tmp_path)

    def test_un_test_de_plus_est_signale(self, tmp_path: Path) -> None:
        rapport = content.validate_scoring(self._lab_note(tmp_path, taches=5, tests=6))
        assert not rapport.ok
        assert "5 tâche(s) notée(s) pour 6 test(s)" in rapport.issues[0].message

    def test_un_pour_un_passe(self, tmp_path: Path) -> None:
        assert content.validate_scoring(self._lab_note(tmp_path, taches=5, tests=5)).ok

    def test_sans_bareme_par_tache_le_controle_se_tait(self, tmp_path: Path) -> None:
        """Un examen blanc peut vérifier plusieurs points par tâche."""
        ch = tmp_path / "challenge"
        (ch / "tests").mkdir(parents=True)
        (ch / "README.fr.md").write_text(
            "### Tâche 1 — sans points annoncés\n", encoding="utf-8"
        )
        (ch / "tests" / "test_functional.py").write_text(
            "def test_a(h): ...\ndef test_b(h): ...\n", encoding="utf-8"
        )
        assert content.validate_scoring(_lab(tmp_path)).ok

    def test_les_sections_ne_sont_pas_comptees_comme_taches(self, tmp_path: Path) -> None:
        """`## Section A (20 pts)` totalise ses `###` : la compter doublerait."""
        ch = tmp_path / "challenge"
        (ch / "tests").mkdir(parents=True)
        (ch / "README.fr.md").write_text(
            "**Format** : 2 tâches, 20 points.\n\n"
            "## Section A — bloc (20 pts)\n\n"
            "### Tâche 1 — a (10 pts)\n\n### Tâche 2 — b (10 pts)\n",
            encoding="utf-8",
        )
        (ch / "tests" / "test_functional.py").write_text(
            "def test_a(h): ...\ndef test_b(h): ...\n", encoding="utf-8"
        )
        assert content.validate_scoring(_lab(tmp_path)).ok


class TestPariteLangues:
    def test_traduction_manquante(self, tmp_path: Path) -> None:
        (tmp_path / "README.fr.md").write_text("cours", encoding="utf-8")
        rapport = content.validate_language_parity(_lab(tmp_path))
        assert not rapport.ok
        assert "README.md" in rapport.issues[0].message

    def test_les_deux_langues_presentes(self, tmp_path: Path) -> None:
        (tmp_path / "README.fr.md").write_text("cours", encoding="utf-8")
        (tmp_path / "README.md").write_text("course", encoding="utf-8")
        assert content.validate_language_parity(_lab(tmp_path)).ok


class TestCibles:
    def _lab_vm(self, tmp_path: Path, host: str) -> LabDefinition:
        from dsoxlab.models.runtime import Target

        lab = _lab(tmp_path)
        lab.runtime.type = RuntimeType.VM
        lab.runtime.targets = [Target(name="rhel", host=host)]
        return lab

    def test_hote_inconnu(self, tmp_path: Path) -> None:
        rapport = content.validate_targets(
            self._lab_vm(tmp_path, "absent.lab"), {"present.lab"}
        )
        assert not rapport.ok
        assert "absent.lab" in rapport.issues[0].message

    def test_hote_connu(self, tmp_path: Path) -> None:
        assert content.validate_targets(
            self._lab_vm(tmp_path, "present.lab"), {"present.lab"}
        ).ok

    def test_sans_infra_declaree_le_controle_se_tait(self, tmp_path: Path) -> None:
        """Un dépôt 100 % shell n'a pas d'`infra.hosts` : ce n'est pas une faute."""
        assert content.validate_targets(self._lab_vm(tmp_path, "x.lab"), set()).ok
