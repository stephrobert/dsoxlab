"""Tests for fixture copying in ShellRuntime.

The runtime used to copy every fixture on its **base name**
(``workdir / Path(rel).name``), while the module docstring promised
``<lab>/fixtures/<file>`` → ``<lab>/<workdir>/<file>``. Any lab shipping a
local module was therefore impossible: ``modules/stockage/main.tf`` landed on
``main.tf`` and silently overwrote the root ``main.tf``. A Terraform lab needs
modules, so the declared path is now preserved.

These tests pin both directions: the tree is kept, and a path escaping the
workdir is refused rather than followed.
"""

from __future__ import annotations

from pathlib import Path

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.runtimes.shell import ShellRuntime


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
    """`../` in a declared path must not write outside the workdir."""
    _ecrire(tmp_path, "dehors.txt", "vole\n")
    lab = _lab(tmp_path, ["../dehors.txt"])

    ShellRuntime().start(lab)

    work = tmp_path / "challenge" / "work"
    assert work.is_dir(), "the workdir is still created"
    assert list(work.iterdir()) == [], "nothing may be copied from outside fixtures/"


def test_an_absolute_fixture_path_is_always_refused(tmp_path: Path) -> None:
    lab = _lab(tmp_path, ["/etc/hostname"])

    ShellRuntime().start(lab)

    assert list((tmp_path / "challenge" / "work").iterdir()) == []


def test_a_missing_fixture_does_not_stop_the_others(tmp_path: Path) -> None:
    """A typo in one entry must not deprive the learner of the whole workdir."""
    _ecrire(tmp_path / "fixtures", "present.tf", "ok\n")
    lab = _lab(tmp_path, ["absent.tf", "present.tf"])

    ShellRuntime().start(lab)

    assert (tmp_path / "challenge" / "work" / "present.tf").is_file()
