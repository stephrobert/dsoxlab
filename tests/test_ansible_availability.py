"""`ansible-runner` importable ne veut pas dire qu'un playbook peut tourner.

Mesuré sur une machine neuve : `uv tool install dsoxlab` posait un outil de
18 Mo dont le `bin/` ne contenait ni `ansible` ni `ansible-playbook`. Le
commentaire du `pyproject.toml` affirmait pourtant qu'ansible-core arrivait en
transitif.

Le coût de cet écart : `is_available()` répondait vrai, `dsoxlab doctor`
affichait « ansible-runner: OK », et tout `dsoxlab run` sur un lab `vm` sortait
en `rc=127`, code shell de « commande introuvable » que rien ne traduisait.

Ce module épingle les deux moitiés du contrôle, et le message qui les
distingue : la bibliothèque absente et l'exécutable absent ne se réparent pas
de la même façon.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.infra import ansible as ansible_infra


def test_sans_ansible_playbook_rien_n_est_disponible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le faux positif qui coûtait un rc=127 inexplicable."""
    monkeypatch.setattr(ansible_infra.shutil, "which", lambda name: None)
    assert ansible_infra.has_ansible_playbook() is False
    assert ansible_infra.is_available() is False


def test_avec_ansible_playbook_tout_est_disponible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ansible_infra.shutil, "which",
        lambda name: "/usr/bin/ansible-playbook" if name == "ansible-playbook" else None,
    )
    assert ansible_infra.has_ansible_playbook() is True
    assert ansible_infra.is_available() is True


def test_le_message_nomme_l_executable_manquant(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Un message qui parle d'ansible-runner enverrait réinstaller ce qui est
    déjà là. Il doit nommer ansible-core, qui est ce qui manque."""
    monkeypatch.setattr(ansible_infra, "has_ansible_playbook", lambda: False)
    playbook = tmp_path / "setup.yaml"
    playbook.write_text("- hosts: all\n", encoding="utf-8")

    with pytest.raises(ansible_infra.AnsibleNotInstalled) as leve:
        ansible_infra.run_playbook(playbook_path=playbook, inventory={})

    message = str(leve.value)
    assert "ansible-playbook" in message
    assert "ansible-core" in message


def test_l_exception_est_une_runtime_error() -> None:
    """La CLI attrape `RuntimeError` pour rendre une phrase plutôt qu'une
    traceback : si cette filiation disparaît, le message redevient un plantage.
    """
    assert issubclass(ansible_infra.AnsibleNotInstalled, RuntimeError)


def test_ansible_core_est_declare_en_dependance() -> None:
    """Le correctif de fond : ansible-runner ne le tire pas.

    Ce test lit `pyproject.toml` plutôt que l'environnement : ce qui compte est
    ce qui sera installé chez l'utilisateur, pas ce que porte cette machine-ci.
    """
    import tomllib

    racine = Path(__file__).resolve().parent.parent
    data = tomllib.loads((racine / "pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]

    assert any(d.startswith("ansible-core") for d in deps), (
        "ansible-core doit être déclaré explicitement : ansible-runner ne "
        "l'installe pas, et sans lui tout lab vm sort en rc=127"
    )
