"""Tests for fixture copying in ShellRuntime.

The runtime used to copy every fixture on its **base name**
(``workdir / Path(rel).name``), while the module docstring promised
``<lab>/fixtures/<file>`` → ``<lab>/<workdir>/<file>``. Any lab shipping a
local module was therefore impossible: ``modules/stockage/main.tf`` landed on
``main.tf`` and silently overwrote the root ``main.tf``. A Terraform lab needs
modules, so the declared path is now preserved.

These tests pin both directions: the tree is kept, and a path escaping the
workdir is refused rather than followed.

Since #177 a fixture that cannot be copied **fails the run** instead of being
skipped with a log line nobody reads. The reversal is deliberate: a partially
filled workdir looks like it works, so the learner hunts for a mistake that is
not theirs, while `run` exits 0. A refusal naming the missing file tells them
in one line that the lab itself is broken.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.runtimes.shell import FixtureError, ShellRuntime


def _lab(tmp_path: Path, fixtures: list[str]) -> LabDefinition:
    return LabDefinition(
        id="demo-lab",
        title="Demo",
        level="l1",
        skills=["s"],
        runtime=RuntimeConfig(
            type=RuntimeType.SHELL, workdir="challenge/work", fixtures=fixtures
        ),
        distros=["alma10"],
        doc_url="https://example.test/doc",
        validation=ValidationConfig(),
        path=tmp_path,
    )


def _ecrire(racine: Path, rel: str, contenu: str) -> None:
    cible = racine / rel
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(contenu, encoding="utf-8")


def test_a_nested_fixture_keeps_its_path(tmp_path: Path) -> None:
    """`modules/stockage/main.tf` must not land on `main.tf`."""
    _ecrire(tmp_path / "fixtures", "main.tf", "racine\n")
    _ecrire(tmp_path / "fixtures", "modules/stockage/main.tf", "module\n")
    lab = _lab(tmp_path, ["main.tf", "modules/stockage/main.tf"])

    ShellRuntime().start(lab)

    work = tmp_path / "challenge" / "work"
    assert (work / "main.tf").read_text(encoding="utf-8") == "racine\n"
    assert (work / "modules" / "stockage" / "main.tf").read_text(
        encoding="utf-8"
    ) == "module\n", "the nested fixture must keep its directory"


def test_intermediate_directories_are_created(tmp_path: Path) -> None:
    """The learner never runs mkdir: the runtime creates the tree."""
    _ecrire(tmp_path / "fixtures", "a/b/c/note.txt", "profond\n")
    lab = _lab(tmp_path, ["a/b/c/note.txt"])

    ShellRuntime().start(lab)

    assert (tmp_path / "challenge" / "work" / "a" / "b" / "c" / "note.txt").is_file()


def test_a_flat_fixture_still_lands_at_the_root(tmp_path: Path) -> None:
    """Regression guard: the 136 fixtures declared across the lab repos are flat."""
    _ecrire(tmp_path / "fixtures", "versions.tf", "tf\n")
    lab = _lab(tmp_path, ["versions.tf"])

    ShellRuntime().start(lab)

    assert (tmp_path / "challenge" / "work" / "versions.tf").is_file()


def test_a_fixture_escaping_the_workdir_is_refused(tmp_path: Path) -> None:
    """`../` in a declared path must not write outside the workdir.

    The safety invariant is unchanged and now enforced more strongly: nothing
    is copied, *and* the lab refuses to start.
    """
    _ecrire(tmp_path, "dehors.txt", "vole\n")
    lab = _lab(tmp_path, ["../dehors.txt"])

    with pytest.raises(FixtureError):
        ShellRuntime().start(lab)

    work = tmp_path / "challenge" / "work"
    assert work.is_dir(), "the workdir is still created"
    assert list(work.iterdir()) == [], "nothing may be copied from outside fixtures/"


def test_an_absolute_fixture_path_is_always_refused(tmp_path: Path) -> None:
    lab = _lab(tmp_path, ["/etc/hostname"])

    with pytest.raises(FixtureError):
        ShellRuntime().start(lab)

    assert list((tmp_path / "challenge" / "work").iterdir()) == []


def test_a_typo_in_one_entry_now_fails_the_whole_run(tmp_path: Path) -> None:
    """The reversal of #177, kept explicit rather than quietly dropped.

    This test used to assert the opposite — that the other fixtures were still
    copied — on the grounds that a typo should not deprive the learner of the
    whole workdir. It is the missing file that deprives them: they cannot fix
    an authoring mistake, and an amputated exercise fails `check` for reasons
    they will look for in their own work. What the old intent asked for is kept
    where it belongs: the message names every file that is missing.
    """
    _ecrire(tmp_path / "fixtures", "present.tf", "ok\n")
    lab = _lab(tmp_path, ["absent.tf", "present.tf"])

    with pytest.raises(FixtureError) as exc:
        ShellRuntime().start(lab)

    assert "absent.tf" in str(exc.value)
    assert not (tmp_path / "challenge" / "work" / "present.tf").exists(), (
        "all or nothing: a half-filled workdir looks like it works"
    )
