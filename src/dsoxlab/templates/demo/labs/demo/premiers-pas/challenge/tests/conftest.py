"""conftest.py — premiers-pas

`dsoxlab check` lance pytest depuis la RACINE du catalogue, pas depuis le
répertoire de travail du lab. Sans cette fixture, un test qui écrit
`pathlib.Path(".")` regarderait la racine du catalogue et ne trouverait jamais
les réponses de l'apprenant : trois tests rouges sur un travail pourtant juste.

C'est la convention de tous les labs `shell` du contrat, reprise telle quelle.
"""
import os
import pathlib
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def set_workdir() -> Iterator[None]:
    work_dir = pathlib.Path(__file__).parent.parent / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    original = os.getcwd()
    os.chdir(work_dir)
    yield
    os.chdir(original)
