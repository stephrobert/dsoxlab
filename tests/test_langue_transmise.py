"""La langue retenue par dsoxlab parvient aux processus enfants (0.11.1).

Le défaut : avec ``dsoxlab use --lang fr`` ou une locale française, l'interface
était en français et les messages d'échec des tests restaient en anglais. Les
tests d'un catalogue lisent ``DSOXLAB_LANG``, que dsoxlab ne posait pas.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dsoxlab import i18n
from dsoxlab.infra import ansible
from dsoxlab.services import lab_service

_TEST = '''import os


def test_langue():
    assert False, "langue=" + os.environ.get("DSOXLAB_LANG", "absente")
'''


@pytest.fixture
def depot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Un catalogue d'un lab ``shell``, dont le test dit la langue qu'il reçoit."""
    (tmp_path / "meta.yml").write_text("repo:\n  id: langues\n  category: domaine\n", encoding="utf-8")
    lab = tmp_path / "labs" / "un-lab"
    (lab / "challenge" / "tests").mkdir(parents=True)
    (lab / "lab.yaml").write_text(
        "id: un-lab\ntitle: Un lab\nlevel: l1\nskills: [a]\ndistros: [b]\n"
        "doc_url: https://example.org/\nruntime:\n  type: shell\n  workdir: challenge/work\n",
        encoding="utf-8",
    )
    (lab / "challenge" / "tests" / "test_functional.py").write_text(_TEST, encoding="utf-8")
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.delenv("DSOXLAB_LANG", raising=False)
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setattr(i18n, "_langue", None, raising=False)
    return tmp_path


def _langue_vue_par_les_tests(depot: Path) -> str:
    from dsoxlab.discovery.scanner import discover_labs

    lab = next(iter(discover_labs(depot)))
    sortie = lab_service.check_lab(lab).output
    for langue in ("fr", "en", "absente"):
        if f"langue={langue}" in sortie:
            return langue
    raise AssertionError(sortie)


def test_la_langue_du_contexte_parvient_aux_tests(depot: Path) -> None:
    (depot / ".dsoxlab-context.json").write_text(json.dumps({"lang": "fr"}), encoding="utf-8")

    assert _langue_vue_par_les_tests(depot) == "fr"


def test_la_locale_parvient_aux_tests(depot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")

    assert _langue_vue_par_les_tests(depot) == "fr"


def test_la_variable_l_emporte_sur_le_contexte(
    depot: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (depot / ".dsoxlab-context.json").write_text(json.dumps({"lang": "fr"}), encoding="utf-8")
    monkeypatch.setenv("DSOXLAB_LANG", "en")

    assert _langue_vue_par_les_tests(depot) == "en"


def test_une_langue_non_traduite_retombe_sur_l_anglais(
    depot: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANG", "de_DE.UTF-8")

    assert _langue_vue_par_les_tests(depot) == "en"


def test_les_playbooks_recoivent_la_langue_de_la_cli(
    depot: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``i18n.set_lang`` est ce que l'amorçage de la CLI appelle."""
    monkeypatch.setattr(i18n, "_strings", None)
    i18n.set_lang("fr")

    assert ansible._env_overrides()["DSOXLAB_LANG"] == "fr"
