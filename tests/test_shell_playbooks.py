"""Tests for setup.yaml / cleanup.yaml on a shell lab (issue #298).

A shell lab may now prepare a terrain before the learner starts: the same
Ansible playbooks a vm lab ships, played on localhost over a local connection.
The Terraform level exams need it to bring up machines, a shared store and a
randomly drawn incident without handing the draw to the learner.

What these tests pin:

- a shell lab WITHOUT playbooks behaves exactly as before (no Ansible call);
- `run` plays setup.yaml after the fixtures, `clean` plays cleanup.yaml before
  removing the workdir, `reset` chains both, in that order;
- a failing playbook fails the command instead of opening a session on a
  half-prepared terrain;
- the playbooks receive lab_id, lab_workdir and lab_state_dir, the state dir
  lives OUTSIDE the workdir and is the one `check` exports as LAB_STATE_DIR.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.infra import ansible as ansible_infra
from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.runtimes import shell as shell_module
from dsoxlab.runtimes.shell import ShellRuntime
from dsoxlab.services.lab_service import check_lab
from dsoxlab.services.lab_state import repertoire_etat


def _lab(lab_dir: Path) -> LabDefinition:
    return LabDefinition(
        id="exam-lab",
        title="Exam",
        level="l2",
        skills=["s"],
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="challenge/work"),
        distros=["debian13"],
        doc_url="https://example.test/doc",
        validation=ValidationConfig(),
        path=lab_dir,
    )


def _catalogue(tmp_path: Path) -> Path:
    """A minimal catalogue root holding one lab directory."""
    (tmp_path / "meta.yml").write_text("repo:\n  id: test-catalogue\n", encoding="utf-8")
    lab_dir = tmp_path / "labs" / "exam-lab"
    lab_dir.mkdir(parents=True)
    return lab_dir


class _Result:
    def __init__(self, ok: bool) -> None:
        self.ok = ok
        self.rc = 0 if ok else 2
        self.status = "successful" if ok else "failed"
        self.stdout = ""


def _espion(monkeypatch: pytest.MonkeyPatch, ok: bool = True) -> list[dict]:
    """Replace run_playbook, recording each call."""
    appels: list[dict] = []

    def faux(**kwargs):
        appels.append(kwargs)
        return _Result(ok)

    monkeypatch.setattr(shell_module.ansible_infra, "run_playbook", faux)
    return appels


def test_a_shell_lab_without_playbooks_never_calls_ansible(tmp_path, monkeypatch) -> None:
    appels = _espion(monkeypatch)
    lab = _lab(_catalogue(tmp_path))
    ShellRuntime().start(lab)
    ShellRuntime().reset(lab)
    ShellRuntime().clean(lab)
    assert appels == []


def test_run_plays_setup_on_localhost_with_the_lab_variables(tmp_path, monkeypatch) -> None:
    appels = _espion(monkeypatch)
    lab_dir = _catalogue(tmp_path)
    (lab_dir / "setup.yaml").write_text("- hosts: all\n  tasks: []\n", encoding="utf-8")
    lab = _lab(lab_dir)

    ShellRuntime().start(lab)

    assert len(appels) == 1
    appel = appels[0]
    assert appel["playbook_path"] == lab_dir / "setup.yaml"
    hote = appel["inventory"]["all"]["hosts"]["localhost"]
    assert hote["ansible_connection"] == "local"
    variables = appel["extra_vars"]
    assert variables["lab_id"] == "exam-lab"
    assert Path(variables["lab_workdir"]) == (lab_dir / "challenge" / "work").resolve()
    etat = Path(variables["lab_state_dir"])
    assert etat.is_dir(), "the state dir must exist before the playbook writes to it"
    assert etat == repertoire_etat(tmp_path, "exam-lab")
    assert not str(etat).startswith(str(lab_dir)), "the state dir must live outside the lab"


def test_clean_plays_cleanup_before_removing_the_workdir(tmp_path, monkeypatch) -> None:
    lab_dir = _catalogue(tmp_path)
    (lab_dir / "cleanup.yaml").write_text("- hosts: all\n  tasks: []\n", encoding="utf-8")
    lab = _lab(lab_dir)
    ShellRuntime().start(lab)
    workdir = lab_dir / "challenge" / "work"
    (workdir / "terraform.tfstate").write_text("{}", encoding="utf-8")

    vu: list[bool] = []

    def faux(**kwargs):
        # The cleanup may need the workdir (a Terraform state, for instance).
        vu.append((workdir / "terraform.tfstate").is_file())
        return _Result(True)

    monkeypatch.setattr(shell_module.ansible_infra, "run_playbook", faux)
    ShellRuntime().clean(lab)
    assert vu == [True]
    assert not workdir.exists()


def test_reset_plays_cleanup_then_setup(tmp_path, monkeypatch) -> None:
    appels = _espion(monkeypatch)
    lab_dir = _catalogue(tmp_path)
    for nom in ("setup.yaml", "cleanup.yaml"):
        (lab_dir / nom).write_text("- hosts: all\n  tasks: []\n", encoding="utf-8")
    ShellRuntime().reset(_lab(lab_dir))
    assert [a["playbook_path"].name for a in appels] == ["cleanup.yaml", "setup.yaml"]


def test_a_failing_setup_fails_the_run(tmp_path, monkeypatch) -> None:
    _espion(monkeypatch, ok=False)
    lab_dir = _catalogue(tmp_path)
    (lab_dir / "setup.yaml").write_text("- hosts: all\n  tasks: []\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"setup\.yaml"):
        ShellRuntime().start(_lab(lab_dir))


@pytest.mark.skipif(not ansible_infra.is_available(), reason="ansible-runner or ansible-playbook absent")
def test_a_real_setup_writes_into_the_workdir_and_the_state_dir(tmp_path) -> None:
    lab_dir = _catalogue(tmp_path)
    (lab_dir / "setup.yaml").write_text(
        "- hosts: all\n"
        "  gather_facts: false\n"
        "  tasks:\n"
        "    - ansible.builtin.copy:\n"
        "        dest: \"{{ lab_workdir }}/main.tf\"\n"
        "        content: \"# prepared for {{ lab_id }}\\n\"\n"
        "        mode: \"0644\"\n"
        "    - ansible.builtin.copy:\n"
        "        dest: \"{{ lab_state_dir }}/incident\"\n"
        "        content: \"drift\\n\"\n"
        "        mode: \"0600\"\n",
        encoding="utf-8",
    )
    lab = _lab(lab_dir)
    ShellRuntime().start(lab)
    assert (lab_dir / "challenge" / "work" / "main.tf").read_text() == "# prepared for exam-lab\n"
    assert (repertoire_etat(tmp_path, "exam-lab") / "incident").read_text() == "drift\n"


def test_the_failure_names_the_failing_task_and_its_message() -> None:
    sortie = (
        "TASK [Prepare the store] ****\n"
        "ok: [localhost]\n"
        "TASK [Wait for its address] ****\n"
        'fatal: [localhost]: FAILED! => {"changed": false, "msg": "Conditionals must have a boolean result."}\n'
        "PLAY RECAP ****\n"
    )
    cause = shell_module.cause_d_echec(sortie)
    assert "Wait for its address" in cause
    assert "Conditionals must have a boolean result." in cause
    assert shell_module.cause_d_echec("PLAY RECAP\nok=3") == ""


@pytest.mark.skipif(not ansible_infra.is_available(), reason="ansible-runner or ansible-playbook absent")
def test_a_real_failing_setup_reports_its_task(tmp_path) -> None:
    lab_dir = _catalogue(tmp_path)
    (lab_dir / "setup.yaml").write_text(
        "- hosts: all\n"
        "  gather_facts: false\n"
        "  tasks:\n"
        "    - name: Refuse on purpose\n"
        "      ansible.builtin.fail:\n"
        "        msg: the store is unreachable\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError) as exc:
        ShellRuntime().start(_lab(lab_dir))
    assert "Refuse on purpose" in str(exc.value)
    assert "the store is unreachable" in str(exc.value)


def test_check_exports_the_state_dir_to_the_tests(tmp_path) -> None:
    lab_dir = _catalogue(tmp_path)
    tests = lab_dir / "challenge" / "tests"
    tests.mkdir(parents=True)
    temoin = tmp_path / "vu.txt"
    (tests / "test_env.py").write_text(
        "import os, pathlib\n"
        f"def test_state_dir():\n    pathlib.Path({str(temoin)!r}).write_text(os.environ['LAB_STATE_DIR'])\n",
        encoding="utf-8",
    )
    resultat = check_lab(_lab(lab_dir))
    assert resultat.ok, resultat.output
    assert Path(temoin.read_text()) == repertoire_etat(tmp_path, "exam-lab")
