"""`catalog add` dit les collections manquantes, là où le README ne le dit plus.

Le catalogue kubernetes déclarait ses collections dans son `requirements.yml`
**et** documentait leur installation dans son README. Les deux étaient justes,
et pourtant deux utilisateurs ont perdu six jours (issue #94) : `catalog add`
clone sous `~/.local/share/dsoxlab/catalogs/`, où personne ne lit ce README.

Une documentation que le parcours ne fait jamais croiser ne documente rien.
L'avis se pose donc au moment où l'on acquiert le besoin, juste après le clone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.cli import catalogues
from dsoxlab.services import collections_ansible
from dsoxlab.utils.shell import CommandResult


def _catalogue(racine: Path, *, declare: str | None) -> None:
    playbook = racine / "labs/cka/l1/setup.yaml"
    playbook.parent.mkdir(parents=True, exist_ok=True)
    playbook.write_text(
        "- hosts: lab_target\n"
        "  tasks:\n"
        "    - name: Load the br_netfilter module\n"
        "      community.general.modprobe:\n"
        "        name: br_netfilter\n",
        encoding="utf-8",
    )
    if declare is not None:
        (racine / "requirements.yml").write_text(declare, encoding="utf-8")


@pytest.fixture
def galaxy_vide(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        collections_ansible,
        "run_command",
        lambda *a, **k: CommandResult(returncode=0, stdout="{}", stderr=""),
    )


def test_le_geste_joue_la_declaration_du_catalogue(
    tmp_path: Path, galaxy_vide: None
) -> None:
    """La commande proposée respecte les bornes de version déclarées.

    On interroge le geste, pas la sortie : lire un rendu Rich mesurerait le
    repli des colonnes, qui dépend de la largeur du terminal.
    """
    _catalogue(tmp_path, declare="collections:\n  - name: community.general\n")

    besoins = collections_ansible.mesurer(tmp_path)

    assert collections_ansible.geste_d_installation(besoins) == [
        "ansible-galaxy", "collection", "install",
        "-r", str(tmp_path / "requirements.yml"),
    ]


def test_sans_declaration_le_geste_nomme_les_collections(
    tmp_path: Path, galaxy_vide: None
) -> None:
    _catalogue(tmp_path, declare=None)

    besoins = collections_ansible.mesurer(tmp_path)

    assert collections_ansible.geste_d_installation(besoins) == [
        "ansible-galaxy", "collection", "install", "community.general",
    ]


def test_l_avis_est_pose_quand_une_collection_manque(
    tmp_path: Path, galaxy_vide: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """Qu'il parle, et qu'il nomme la collection : le reste est du rendu."""
    _catalogue(tmp_path, declare="collections:\n  - name: community.general\n")

    catalogues._dire_les_collections_a_installer(tmp_path)

    assert "community.general" in capsys.readouterr().out


def test_l_avis_se_tait_quand_tout_est_installe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le cas du mainteneur : l'avis doit se taire, pas rassurer bruyamment."""
    _catalogue(tmp_path, declare="collections:\n  - name: community.general\n")
    monkeypatch.setattr(
        collections_ansible,
        "run_command",
        lambda *a, **k: CommandResult(
            returncode=0,
            stdout='{"/x": {"community.general": {"version": "11.4.7"}}}',
            stderr="",
        ),
    )

    catalogues._dire_les_collections_a_installer(tmp_path)

    assert capsys.readouterr().out == ""


def test_un_catalogue_sans_playbook_ne_dit_rien(
    tmp_path: Path, galaxy_vide: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """`terraform` et `python` : tous leurs labs sont `shell`."""
    (tmp_path / "labs").mkdir()

    catalogues._dire_les_collections_a_installer(tmp_path)

    assert capsys.readouterr().out == ""


def test_galaxy_muet_ne_fait_pas_accuser_a_tort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un avis posé sans avoir mesuré enverrait installer ce qui est déjà là."""
    _catalogue(tmp_path, declare="collections:\n  - name: community.general\n")
    monkeypatch.setattr(
        collections_ansible,
        "run_command",
        lambda *a, **k: CommandResult(
            returncode=127, stdout="", stderr="", failure="not_found"
        ),
    )

    catalogues._dire_les_collections_a_installer(tmp_path)

    assert capsys.readouterr().out == ""
