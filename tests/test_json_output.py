"""Le contrat de la sortie machine.

Une intégration — extension d'éditeur, tableau de bord — lit ces documents. Ce
qui les casse ne se voit pas en utilisant la CLI à la main : d'où ces tests.

Deux exigences, et une seule compte vraiment : que la sortie standard ne
contienne QUE du JSON. Un message d'ambiance en tête de flux suffit à rendre le
document illisible pour l'appelant, et c'est arrivé trois fois en l'écrivant :
« ℹ Validation de… », la barre de progression pytest, puis le contexte actif.

D'où la forme des contrôles de commande, plus bas : ``json.loads(stdout)``
**sans strip**, ce qui refuse tout résidu, et jamais une recherche de sous-chaîne
qui laisserait passer un flux déjà cassé. Chaque commande y est jouée par
``CliRunner``, qui sépare la sortie standard de la sortie d'erreur : c'est la
seule façon de prouver que les avis partent bien du bon côté.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType, Target
from dsoxlab.reporting import machine
from dsoxlab.services import doctor as service_doctor

runner = CliRunner()


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


def test_a_lab_never_attempted_is_not_a_zero_score(capsys) -> None:
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


def test_a_failing_check_still_prints_only_json(monkeypatch, capsys, tmp_path) -> None:
    """Un lab en échec ne doit pas préfixer le JSON de sa sortie pytest.

    C'est le cas le plus fréquent en usage réel, et le plus facile à manquer :
    un lab qui passe n'emprunte jamais la branche fautive. Le contrôle initial
    avait été fait sur un lab à 14/14, donc sur le seul cas favorable.
    """
    from dsoxlab import cli
    from dsoxlab.services.lab_service import CheckResult

    # `_run_check` prend le verrou d'écriture du dépôt, dont le fichier vit
    # sous XDG_STATE_HOME. Sans cette redirection, ce test déposerait un
    # répertoire dans le `~/.local/state` de qui lance la suite, pour une
    # racine (`/repo`) qui n'existe même pas.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    echec = CheckResult(ok=False, output="=== test session starts ===\nFAILED", passed=1, total=3)
    monkeypatch.setattr(cli._validation, "_run_check_with_progress", lambda *a, **k: echec)
    monkeypatch.setattr(cli._validation, "evaluate_lab", lambda *a, **k: type("E", (), {"score": 30, "max_score": 100})())

    cli._run_check(Path("/repo"), _lab(), None, quiet=True)

    assert capsys.readouterr().out == "", "le mode machine doit rester muet"


# ── les documents rendus par les commandes ───────────────────────────────────

_META = """\
repo:
  id: catalogue-essai
  category: domaine
sections:
  - id: domaine
    title: Domaine
    labs:
      - domaine/premier
      - domaine/second
"""

_LAB = """\
id: {ident}
title: {titre}
level: l1
skills: [une-competence]
distros: [alma10]
doc_url: https://exemple.test/guide
runtime:
  type: shell
  workdir: challenge/work
"""


def _poser_lab(racine: Path, ident: str, titre: str) -> Path:
    """Un lab conforme au contrat, réduit à ce que les validators exigent."""
    lab = racine / "labs" / "domaine" / ident
    (lab / "challenge" / "tests").mkdir(parents=True)
    (lab / "lab.yaml").write_text(
        _LAB.format(ident=ident, titre=titre), encoding="utf-8"
    )
    (lab / "README.md").write_text(f"# {titre}\n", encoding="utf-8")
    (lab / "scenario.md").write_text("Faites la chose.\n", encoding="utf-8")
    (lab / "challenge" / "tests" / "test_functional.py").write_text(
        "def test_la_chose_est_faite() -> None:\n    assert True\n", encoding="utf-8"
    )
    return lab


@pytest.fixture
def catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Un catalogue minimal, conforme, et sans le moindre chemin personnel.

    ``LAB_HOME`` le désigne : c'est aussi ce que lit ``--lab-home``, donc les
    commandes le trouvent sans qu'aucun test ne dépende du répertoire courant.
    Les répertoires XDG partent dans le ``tmp_path``, faute de quoi cette suite
    écrirait un journal dans le répertoire personnel de qui la lance.
    """
    racine = tmp_path / "catalogue"
    racine.mkdir()
    (racine / "meta.yml").write_text(_META, encoding="utf-8")
    _poser_lab(racine, "premier", "Le premier")
    _poser_lab(racine, "second", "Le second")

    monkeypatch.setenv("LAB_HOME", str(racine))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    for variable in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
        monkeypatch.setenv(variable, str(tmp_path / variable.lower()))
    return racine


def _noter(racine: Path, ident: str, score: int) -> None:
    """Une note dans la base du catalogue, sans passer par un lab joué."""
    from dsoxlab.sessions.store import record_result

    record_result(
        racine, lab_id=ident, section="domaine", score=score, max_score=100,
        passed_tests=score // 20, total_tests=5, hints_used=0,
    )


def _document(*args: str) -> Any:
    """Joue une commande et rend son document, refusé s'il traîne quoi que ce soit.

    Pas de ``strip`` : c'est tout l'intérêt. Un « ℹ contexte actif » en tête ou
    une barre de progression en queue font lever ``json.loads``, ce qu'aucune
    recherche de sous-chaîne n'attraperait.
    """
    resultat = runner.invoke(app, [*args, "--json"])
    assert resultat.exit_code == 0, resultat.stderr
    return json.loads(resultat.stdout)


@pytest.fixture
def sans_hyperviseur(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise les sondes système : un diagnostic n'a pas à sortir du test.

    Sans cela, ``doctor`` lancerait ``virsh`` et ``incus`` sur la machine qui
    joue la suite, et le document dépendrait de ce qui y est installé.
    """
    monkeypatch.setattr(
        service_doctor,
        "_hypervisor_checks",
        lambda: {
            "kvm": service_doctor._check(
                "kvm", False, "absent",
                fix=service_doctor.Fix((("apt", "install"),)),
            ),
            "incus": service_doctor._check("incus", True, "ok"),
        },
    )


def test_show_rend_le_lab_et_son_statut(catalogue: Path) -> None:
    document = _document("show", "premier")

    assert document["schema"] == machine.SCHEMA
    assert document["lab"]["id"] == "premier"
    assert document["lab"]["path"] == str(catalogue / "labs" / "domaine" / "premier")
    # Un lab jamais joué : le répertoire de travail n'existe pas encore.
    assert document["status"] == "stopped"
    assert document["lab"]["best_score"] is None


def test_scores_rend_un_historique_vide(catalogue: Path) -> None:
    """Aucune note enregistrée reste un document, pas une phrase.

    C'est le cas du premier lancement, celui qu'une intégration rencontre en
    premier : sans document, elle n'aurait rien à lire pour le dire.
    """
    document = _document("scores")

    assert document == {"schema": machine.SCHEMA, "results": [], "count": 0}


def test_scores_rend_le_verdict_dun_examen(catalogue: Path) -> None:
    """Le seuil vit dans le catalogue, la note dans la base : `exam` joint les deux."""
    lab = catalogue / "labs" / "domaine" / "premier" / "lab.yaml"
    lab.write_text(
        lab.read_text(encoding="utf-8") + "exam_passing_score: 70\n", encoding="utf-8"
    )
    _noter(catalogue, "premier", 60)

    (note,) = _document("scores")["results"]

    assert note["lab_id"] == "premier"
    assert note["exam"] == {"passing_score": 70, "percentage": 60, "passed": False}


def test_scores_sans_seuil_ne_rend_aucun_verdict(catalogue: Path) -> None:
    """`null` et non `false` : un lab ordinaire n'est pas un examen recalé."""
    _noter(catalogue, "premier", 60)

    assert _document("scores")["results"][0]["exam"] is None


def test_next_designe_le_prochain_lab(catalogue: Path) -> None:
    runner.invoke(app, ["use", "domaine"])
    document = _document("next")

    assert document["next"]["id"] == "premier"
    assert document["all_done"] is False
    assert document["remaining"] == 2
    assert document["context"]["section"] == "domaine"


def test_next_dit_quand_tout_est_fait(catalogue: Path) -> None:
    """`all_done` et `next: null` ne disent pas la même chose.

    Une section vide rendrait aussi `next: null`, et l'appelant fêterait un
    parcours terminé qui n'a jamais commencé.
    """
    runner.invoke(app, ["use", "domaine"])
    for ident in ("premier", "second"):
        _noter(catalogue, ident, 100)

    document = _document("next")

    assert document["next"] is None
    assert document["all_done"] is True
    assert document["remaining"] == 0


def test_next_sans_contexte_ne_rend_rien(catalogue: Path) -> None:
    """Erreur dure : rien sur la sortie standard, la cause sur l'autre, code 1.

    C'est la règle du mode machine, et elle vaut mieux qu'un document inventé
    pour l'occasion : l'appelant lit le code de retour d'abord.
    """
    resultat = runner.invoke(app, ["next", "--json"])

    assert resultat.exit_code == 1
    assert resultat.stdout == ""
    assert resultat.stderr.strip()


def test_doctor_rend_des_cles_stables(catalogue: Path, sans_hyperviseur: None) -> None:
    document = _document("doctor")

    requis = {c["key"]: c for c in document["required"]}
    assert {"python", "pytest", "shell", "labs", "lab_home"} <= set(requis)
    assert requis["labs"]["state"] == "ok"
    assert document["ok"] is True
    # Un catalogue 100 % shell : les hyperviseurs sont informatifs, et le kvm
    # en échec ne doit donc pas peindre le verdict en rouge.
    assert [c["key"] for c in document["informational"]] == ["kvm", "incus"]


def test_un_correctif_expose_sa_categorie(
    catalogue: Path, sans_hyperviseur: None
) -> None:
    """`fix` est la forme lisible, `fix_kind` ce qu'une automatisation lit.

    Une remédiation `manual` ne doit jamais être lancée par un appelant, et une
    `needs_relogin` réussie laisse le contrôle rouge : sans la catégorie, le
    document ne permet de décider ni l'un ni l'autre.
    """
    document = _document("doctor")

    kvm = next(c for c in document["informational"] if c["key"] == "kvm")
    assert kvm["fix"] == "apt install"
    assert kvm["fix_kind"] == "automatic"
    # Un contrôle sans correctif n'invente pas de catégorie.
    python_check = next(c for c in document["required"] if c["key"] == "python")
    assert python_check["fix"] is None
    assert python_check["fix_kind"] is None


def test_un_verdict_se_lit_sans_traduire(
    catalogue: Path, sans_hyperviseur: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le libellé change de langue, l'identité et l'état ne bougent pas.

    C'est tout l'objet de l'interface : une intégration qui devrait comparer
    « Labs detected » puis « Labs détectés » pour savoir si c'est vert ne
    saurait jamais si c'est vert.
    """
    anglais = _document("doctor")
    monkeypatch.setenv("DSOXLAB_LANG", "fr")
    francais = _document("doctor")

    def _extraire(document: Any, champ: str) -> list[Any]:
        return [c[champ] for c in document["required"]]

    assert _extraire(anglais, "key") == _extraire(francais, "key")
    assert _extraire(anglais, "state") == _extraire(francais, "state")
    assert _extraire(anglais, "label") != _extraire(francais, "label")


def test_doctor_ne_repare_pas_en_mode_machine(
    catalogue: Path, sans_hyperviseur: None
) -> None:
    """`--fix` lance apt, dont la sortie irait sur le flux du document.

    Le refus est net et dit quoi faire ; rendre un JSON précédé de la sortie
    d'apt serait le pire des deux.
    """
    resultat = runner.invoke(app, ["doctor", "--json", "--fix"])

    assert resultat.exit_code == 1
    assert resultat.stdout == ""
    assert "--fix" in resultat.stderr


def test_validate_structure_rend_ok(catalogue: Path) -> None:
    document = _document("validate-structure")

    assert document["ok"] is True
    assert document["labs_checked"] == 2
    assert document["issues"] == []
    # Toutes les familles présentes, à zéro : sans quoi l'appelant ne peut pas
    # distinguer une famille saine d'une famille que cette version ignore.
    assert set(document["counts"]) == {
        "contract", "unknown_key", "structure", "content", "doc_url", "metadata",
    }
    assert document["doc_urls_checked"] is False


def test_une_anomalie_porte_sa_regle(catalogue: Path) -> None:
    """`key` identifie la règle, `message` ne fait que la dire à un humain."""
    (catalogue / "labs" / "domaine" / "premier" / "challenge" / "tests"
     / "test_functional.py").unlink()

    resultat = runner.invoke(app, ["validate-structure", "--json"])
    document = json.loads(resultat.stdout)

    assert resultat.exit_code == 1, "le verdict ne change pas avec la forme"
    (anomalie,) = [i for i in document["issues"] if i["kind"] == "structure"]
    assert anomalie["key"] == "struct_missing_file"
    assert anomalie["params"] == {"name": "test_functional.py"}
    assert anomalie["lab"] == "premier"
    assert anomalie["path"].endswith("test_functional.py")
    assert document["counts"]["structure"] == 1
    assert document["ok"] is False


def test_le_code_de_retour_ne_bouge_pas(catalogue: Path) -> None:
    """`--json` change la forme de la sortie, jamais le verdict ni le code.

    Les deux modes sont joués sur le même catalogue cassé, et comparés.
    """
    (catalogue / "labs" / "domaine" / "second" / "README.md").unlink()

    terminal = runner.invoke(app, ["validate-structure"])
    machine_ = runner.invoke(app, ["validate-structure", "--json"])

    assert terminal.exit_code == machine_.exit_code == 1
    assert json.loads(machine_.stdout)["ok"] is False


def test_un_parametre_illisible_ne_casse_rien(catalogue: Path) -> None:
    """Un `params` porte ce que le validator avait sous la main, pas du JSON.

    Un `Path` ou l'exception d'une requête HTTP y atterrissent, et les rendre
    tels quels ferait lever le `json.dump` après tout le travail de la commande.
    """
    rendu = machine.issue_dict(
        "content", "content_doc_url_unreachable", {"error": OSError("réseau coupé")},
    )

    json.dumps(rendu)  # lève si un objet Python a survécu
    assert rendu["params"]["error"] == "réseau coupé"
