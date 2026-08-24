"""Tests for the environment diagnostic behind `dsoxlab doctor`.

Both rules asserted here come from a learner's very first run of the tool,
which greeted them with three red lines: `kvm ko`, `pytest ko`, `incus ko`.
Two of the three were noise, and nothing said which one actually blocked
them.

A check must mirror the command it claims to cover, and it must only be
blocking when it blocks *this* repo. The tests below pin those two rules so
a future refactor cannot quietly reintroduce a discouraging first run.

Labels are compared through `_()` rather than spelled out: the catalog is
bilingual, and hardcoding either language would make these tests depend on
the machine's locale.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from dsoxlab.i18n import _
from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.repo import InfraDefinition, RepoMetadata
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType, Target
from dsoxlab.services import doctor


def _lab(lab_id: str, runtime_type: RuntimeType) -> LabDefinition:
    """A LabDefinition carrying only what the diagnostic reads."""
    targets = (
        []
        if runtime_type is RuntimeType.SHELL
        else [Target(name="rhel", host="node1.lab")]
    )
    return LabDefinition(
        id=lab_id,
        title=lab_id,
        level="l1",
        skills=["s"],
        runtime=RuntimeConfig(type=runtime_type, targets=targets),
        distros=["alma10"],
        doc_url="https://example.test/doc",
        validation=ValidationConfig(),
    )


def _repo(provider: str = "", candidates: list[str] | None = None) -> RepoMetadata:
    return RepoMetadata(
        id="demo",
        category="demo",
        infra=InfraDefinition(
            provider=provider,
            providers_available=candidates or [],
        ),
    )


@pytest.fixture
def stub_hypervisors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the virsh/incus probes: they shell out and take seconds.

    What this module asserts is the *classification* of the checks, not the
    probes themselves.
    """
    monkeypatch.setattr(
        doctor, "_hypervisor_checks",
        lambda: {
            "kvm": doctor._check("kvm", False, "not found", fix="apt install"),
            "incus": doctor._check("incus", True, "daemon ok"),
        },
    )


@pytest.fixture(autouse=True)
def _outillage_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Terraform et ansible-playbook considérés installés, dans tout ce module.

    Sans cela, ces tests mesurent la machine qui les exécute : ils passaient en
    local, où les deux outils sont là, et échouaient sur un runner CI qui ne les
    a pas. Ce que ce module vérifie est le CLASSEMENT des checks, pas la
    présence réelle des outils, laquelle est couverte par
    `test_doctor_installation.py`.
    """
    monkeypatch.setattr(
        doctor, "_check_terraform",
        lambda: doctor._check("terraform", True, "Terraform v1.0.0"),
    )
    monkeypatch.setattr(
        doctor, "_check_ansible",
        lambda: doctor._check("ansible", True, "ok"),
    )


def _labs(monkeypatch: pytest.MonkeyPatch, labs: list[LabDefinition]) -> None:
    monkeypatch.setattr(doctor, "get_all_labs", lambda root: labs)


def _labels(checks: list[doctor.Check]) -> set[str]:
    return {c.label for c in checks}


# ── pytest is diagnosed the way `check` runs it ───────────────────────────────

def test_pytest_check_mirrors_how_check_runs_it(tmp_path: Path) -> None:
    """The interpreter bundled with the tool counts as available.

    `doctor` used to look for a `pytest` binary in PATH while `check` runs
    `sys.executable -m pytest`, where pytest is a declared dependency of
    dsoxlab. The diagnostic said red, the command worked, and the offered
    remediation installed something the learner already had.
    """
    cmd = doctor.resolve_pytest_cmd(tmp_path)
    assert cmd is not None and cmd[0] == sys.executable

    check = doctor._check_pytest(tmp_path)
    assert check.ok
    assert check.fix is None


def test_missing_pytest_is_not_offered_a_project_dependency_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unresolvable pytest is a broken install *of the tool*.

    Adding pytest to the labs repo would not help: `check` does not look
    there first. So the guidance points at dsoxlab, and stays a hint rather
    than a fix, because `--fix` must not reinstall the tool it runs from.
    """
    monkeypatch.setattr(doctor, "resolve_pytest_cmd", lambda root: None)
    check = doctor._check_pytest(tmp_path)

    assert not check.ok
    assert check.fix is None
    assert "dsoxlab" in (check.hint or "")


# ── hypervisors are blocking only where they block ────────────────────────────

def test_shell_only_repo_never_shows_a_red_hypervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_hypervisors: None
) -> None:
    """A catalog of `shell` labs needs no hypervisor at all.

    This is `terraform-training`, which declares no `infra:` block: every
    one of its labs runs on the learner's own machine.
    """
    _labs(monkeypatch, [_lab("a", RuntimeType.SHELL)])
    report = doctor.collect_checks(tmp_path, _repo())

    assert _labels(report.optional) == {_("check_kvm"), _("check_incus")}
    assert not report.failing()
    assert report.notes


def test_active_provider_is_required_and_the_others_are_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_hypervisors: None
) -> None:
    _labs(monkeypatch, [_lab("a", RuntimeType.VM)])
    report = doctor.collect_checks(tmp_path, _repo(provider="kvm"))

    assert _("check_kvm") in _labels(report.required)
    assert _labels(report.optional) == {_("check_incus")}
    assert [c.label for c in report.failing()] == [_("check_kvm")]


def test_remote_provider_requires_no_local_hypervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_hypervisors: None
) -> None:
    """`outscale` provisions in the cloud: nothing to check on this machine."""
    _labs(monkeypatch, [_lab("a", RuntimeType.VM)])
    report = doctor.collect_checks(tmp_path, _repo(provider="outscale"))

    assert _labels(report.optional) == {_("check_kvm"), _("check_incus")}
    assert not report.failing()


def test_unresolved_provider_is_a_decision_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_hypervisors: None
) -> None:
    """Several candidates and no choice: name the choice, do not make it.

    The check is blocking, since `provision` cannot run without it, but it
    carries its own status so a pending decision is not painted red. It
    stays a hint too: choosing a provider for the learner would silently
    decide how their labs run.
    """
    _labs(monkeypatch, [_lab("a", RuntimeType.VM)])
    report = doctor.collect_checks(tmp_path, _repo(candidates=["kvm", "incus"]))

    provider = next(c for c in report.required if c.key == "provider")
    assert not provider.ok
    assert provider.state == doctor.STATE_CHOICE_REQUIRED
    assert provider.fix is None
    assert "use --provider kvm" in (provider.hint or "")
    assert not report.fixable()


def test_legacy_runtime_aliases_still_count_as_vm() -> None:
    """`kvm` and `incus` are retro-compatible aliases of `vm`.

    A repo still using them needs a hypervisor just as much, so they must
    not fall through to the shell-only branch.
    """
    assert doctor.uses_vm([_lab("a", RuntimeType.KVM)])
    assert doctor.uses_vm([_lab("a", RuntimeType.INCUS)])
    assert not doctor.uses_vm([_lab("a", RuntimeType.SHELL)])


def test_missing_meta_yml_still_produces_a_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_hypervisors: None
) -> None:
    """No `meta.yml` is no reason to report nothing: the socle still holds."""
    _labs(monkeypatch, [])
    report = doctor.collect_checks(tmp_path, None)

    assert _labels(report.required) >= {
        _("check_python"), _("check_pytest"), _("check_lab_home"),
    }
    # No lab found is the one thing genuinely wrong here.
    assert [c.label for c in report.failing()] == [_("check_labs")]
