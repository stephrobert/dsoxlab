"""Le contrat de la sortie machine.

Une intégration — extension d'éditeur, tableau de bord — lit ces documents. Ce
qui les casse ne se voit pas en utilisant la CLI à la main : d'où ces tests.

Deux exigences, et une seule compte vraiment : que la sortie standard ne
contienne QUE du JSON. Un message d'ambiance en tête de flux suffit à rendre le
document illisible pour l'appelant, et c'est arrivé trois fois en l'écrivant :
« ℹ Validation de… », la barre de progression pytest, puis le contexte actif.
"""

from __future__ import annotations

import json
from pathlib import Path

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType, Target
from dsoxlab.reporting import machine


def _lab() -> LabDefinition:
    return LabDefinition(
        id="demo-lab",
        title="Demo",
        level="l1",
        skills=["swap"],
        runtime=RuntimeConfig(
            type=RuntimeType.VM,
            targets=[Target(name="t", host="node1.lab")],
            session="local",
        ),
        distros=["alma9"],
        doc_url="https://example.test/doc",
        validation=ValidationConfig(),
        path=Path("/repo/labs/demo"),
    )


def test_the_document_is_versioned() -> None:
    """Un consommateur doit savoir s'il parle la même langue avant de lire."""
    assert machine.SCHEMA >= 1


def test_a_lab_carries_what_an_editor_needs(capsys) -> None:
    machine.emit({"labs": [machine.lab_dict(_lab(), (60, 100))]})
    doc = json.loads(capsys.readouterr().out)

    lab = doc["labs"][0]
    assert doc["schema"] == machine.SCHEMA
    assert lab["id"] == "demo-lab"
    assert lab["path"] == "/repo/labs/demo", "chemin absolu : l'éditeur ouvre les fichiers"
    assert lab["doc_url"].startswith("http")
    assert lab["runtime"] == {
        "type": "vm", "session": "local", "target": "node1.lab",
        "workdir": "challenge/work",
    }
    assert lab["best_score"] == {"points": 60, "max": 100}


def test_a_lab_never_attempted_is_not_a_zero(capsys) -> None:
    """Distinguer « jamais tenté » de « tenté et raté » : ce n'est pas pareil."""
    machine.emit({"labs": [machine.lab_dict(_lab(), None)]})

    assert json.loads(capsys.readouterr().out)["labs"][0]["best_score"] is None


def test_stdout_holds_nothing_but_json(capsys) -> None:
    machine.emit({"labs": []})
    sortie = capsys.readouterr().out

    json.loads(sortie)  # lève si un message s'est glissé avant ou après
    assert sortie.lstrip().startswith("{")


def test_accents_are_not_escaped(capsys) -> None:
    """`\\u00e9` partout rendrait les titres français illisibles au débogage."""
    machine.emit({"titre": "Préparer les nœuds gérés"})
    sortie = capsys.readouterr().out

    assert "Préparer les nœuds gérés" in sortie
