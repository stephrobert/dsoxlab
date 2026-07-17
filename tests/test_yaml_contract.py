"""Regression tests for the untrusted-YAML contract.

`lab.yaml` and `meta.yml` come from lab-provider repositories, so they are the
engine's untrusted input. `discovery/scanner.py` rattrape exactement
``(KeyError, ValueError, yaml.YAMLError)`` et ignore le lab fautif avec un
warning. Toute autre exception échappe à ce filet et remonte en traceback à
l'utilisateur, sur une commande sans rapport.

Ces cas ont été trouvés par les harnais de fuzzing (``fuzz/``) : un document
vide et un ``runtime:`` scalaire faisaient lever AttributeError, hors contrat.
Chaque test vérifie donc le *type* d'exception, pas seulement qu'il y a échec.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dsoxlab.models.lab import LabDefinition
from dsoxlab.models.repo import RepoMetadata

# Le filet exact de discovery/scanner.py.
CONTRACT_EXCEPTIONS = (KeyError, ValueError, yaml.YAMLError)

VALID_LAB = """\
id: l1-demo
title: Demo lab
level: beginner
skills: [demo]
distros: [any]
doc_url: https://example.org/docs/demo/
runtime:
  type: shell
  workdir: challenge/work
"""

# Socle minimal valide : `repo.id` et `repo.category` sont les seuls champs
# requis par le contrat. Les cas ci-dessous lui ajoutent le bloc à éprouver.
VALID_META = """\
repo:
  id: demo-training
  category: demo
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_valid_lab_still_parses(tmp_path: Path) -> None:
    lab = LabDefinition.from_yaml(_write(tmp_path, "lab.yaml", VALID_LAB))
    assert lab.id == "l1-demo"
    assert lab.runtime.workdir == "challenge/work"


def test_empty_validation_block_falls_back_to_defaults(tmp_path: Path) -> None:
    """`validation:` sans valeur n'est pas une erreur : le bloc est optionnel."""
    lab = LabDefinition.from_yaml(_write(tmp_path, "lab.yaml", VALID_LAB + "validation:\n"))
    assert lab.validation.functional is True
    assert lab.validation.security is False


@pytest.mark.parametrize(
    ("label", "document"),
    [
        ("empty file", ""),
        ("comments only", "# rien qu'un commentaire\n"),
        ("root is a list", "- id: l1\n- id: l2\n"),
        ("root is a scalar", "42\n"),
        # `runtime: vm` au lieu du bloc `runtime:\n  type: vm` : la faute la
        # plus naturelle du contrat.
        ("runtime is a scalar", VALID_LAB.replace("runtime:\n  type: shell\n  workdir: challenge/work\n", "runtime: vm\n")),
        ("validation is a scalar", VALID_LAB + "validation: true\n"),
        ("fixtures is a scalar", VALID_LAB + "  fixtures: 42\n"),
        ("targets is a bool", VALID_LAB + "  targets: true\n"),
        ("targets is a scalar", VALID_LAB + "  targets: 3\n"),
        ("targets holds a scalar", VALID_LAB + "  targets:\n    - 42\n"),
        ("roles is a scalar", VALID_LAB + "  targets:\n    - name: a\n      host: h.lab\n      roles: nope\n"),
        ("bloc is not a number", VALID_LAB + "bloc: abc\n"),
        ("skills is a scalar", VALID_LAB.replace("skills: [demo]", "skills: 42")),
    ],
)
def test_malformed_lab_stays_within_contract(tmp_path: Path, label: str, document: str) -> None:
    """Un lab.yaml hostile est rejeté DANS le contrat, jamais en AttributeError."""
    lab_yaml = _write(tmp_path, "lab.yaml", document)
    with pytest.raises(CONTRACT_EXCEPTIONS):
        LabDefinition.from_yaml(lab_yaml)


@pytest.mark.parametrize(
    ("label", "document"),
    [
        ("root is a list", "- repo\n- other\n"),
        ("root is a scalar", "42\n"),
        ("repo is a scalar", "repo: linux\n"),
        ("repo is empty", "repo:\n"),
        ("missing category", "repo:\n  id: demo\n"),
        ("infra is a scalar", VALID_META + "infra: kvm\n"),
        # `hosts:` en mapping au lieu d'une liste : l'itération porterait sur
        # les clés (des str) et `h["name"]` lèverait TypeError.
        ("hosts is a mapping", VALID_META + "infra:\n  hosts:\n    web: 10.0.0.1\n"),
        ("hosts holds a scalar", VALID_META + "infra:\n  hosts:\n    - 42\n"),
        ("providers is a scalar", VALID_META + "infra:\n  providers: nope\n"),
        ("sections is a mapping", VALID_META + "sections:\n  l1: yes\n"),
        ("labs is a scalar", VALID_META + "sections:\n  - id: l1\n    labs: 42\n"),
        ("vcpu is not a number", VALID_META + "infra:\n  hosts:\n    - name: a.lab\n      vcpu: abc\n"),
    ],
)
def test_malformed_meta_stays_within_contract(tmp_path: Path, label: str, document: str) -> None:
    meta_yml = _write(tmp_path, "meta.yml", document)
    with pytest.raises(CONTRACT_EXCEPTIONS):
        RepoMetadata.from_yaml(meta_yml)


def test_empty_host_fields_fall_back_to_defaults(tmp_path: Path) -> None:
    """Une clé présente mais vide (`vcpu:`) doit retomber sur le défaut.

    `.get("vcpu", 1)` rend None dans ce cas, pas 1 : c'est ce qui faisait
    lever `int(None)`.
    """
    meta_yml = _write(
        tmp_path,
        "meta.yml",
        VALID_META + "infra:\n  hosts:\n    - name: a.lab\n      vcpu:\n      ram_mb:\n      ip:\n",
    )
    meta = RepoMetadata.from_yaml(meta_yml)
    host = meta.infra.hosts[0]
    assert host.vcpu == 1
    assert host.ram_mb == 1024
    assert host.ip == ""  # et surtout pas la chaîne "None"


def test_invalid_translation_file_is_ignored(tmp_path: Path) -> None:
    """Un lab.<lang>.yaml non-mapping ne doit pas casser le lab de base."""
    _write(tmp_path, "lab.yaml", VALID_LAB)
    _write(tmp_path, "lab.fr.yaml", "- pas un mapping\n")

    lab = LabDefinition.from_yaml(tmp_path / "lab.yaml", lang="fr")
    assert lab.title == "Demo lab"  # on retombe sur la valeur de base
