"""Trois défauts que la relecture a vus et qu'aucun test ne voyait.

Le plus grave des trois viole la **première règle** de la sortie machine, que la
0.3.0 publie : « rien d'autre que du JSON sur la sortie standard ». Un `ℹ` en
tête de flux suffit à rendre un document illisible pour l'appelant, et c'est
arrivé trois fois pendant l'écriture de cette sortie — d'où la règle. Deux
chemins y échappaient encore.

Les deux autres relèvent du même souci de dire vrai : `submit` annonçait
« Submission recorded » quand rien n'était enregistré, et l'ordre d'un groupe
dans `--help` dépendait de l'ordre d'import de ses modules.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.sessions.store import get_results

runner = CliRunner()


# ── la sortie machine ne porte que son document ──────────────────────────────

def test_un_export_refuse_ne_dit_rien_sur_stdout(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une erreur dure d'`export` ne doit rien écrire sur la sortie standard.

    Le conseil qui suit le refus partait par `info()`, donc sur stdout : le
    `json.loads` de l'appelant échouait sur un texte d'aide. La cause et le
    conseil vont sur stderr, le code de retour ne change pas.
    """
    # Un identifiant de catalogue que la politique refuse : un retour chariot.
    meta = catalogue / "meta.yml"
    meta.write_text(
        meta.read_text(encoding="utf-8").replace(
            "id: catalogue-essai", 'id: "catalogue\\ressai"'
        ),
        encoding="utf-8",
    )

    resultat = runner.invoke(app, ["export"])

    assert resultat.exit_code == 1
    assert resultat.stdout == "", resultat.stdout


def test_infra_status_json_ne_porte_que_son_document(catalogue: Path) -> None:
    """`infra status --json` sur un dépôt sans hôte : un document, et rien d'autre.

    Le message « via bastion » échappait à la garde `--json` — il ne se déclenche
    qu'avec un bastion configuré, mais la règle ne souffre pas d'exception, et
    c'est précisément ce genre de branche oubliée qu'elle existe pour attraper.
    """
    resultat = runner.invoke(app, ["infra", "status", "--json"])

    assert resultat.stdout.startswith("{"), resultat.stdout
    json.loads(resultat.stdout)


# ── `submit` ne dit pas « enregistré » quand rien ne l'est ───────────────────

def test_submit_sur_un_lab_de_validation_ne_dit_pas_enregistre(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Il défend un guide et ne note personne : rien n'est inscrit, rien ne le dit.

    `check` disait déjà la vérité sur ce cas ; `submit` affirmait le contraire.
    """
    lab = catalogue / "labs" / "domaine" / "premier" / "lab.yaml"
    lab.write_text(
        lab.read_text(encoding="utf-8") + "lab_type: validation\n", encoding="utf-8"
    )

    resultat = runner.invoke(app, ["submit", "premier"], env={"COLUMNS": "200"})

    assert resultat.exit_code == 0, resultat.output
    assert "Submission recorded" not in resultat.output
    assert "grades nobody" in resultat.output or "guide" in resultat.output
    assert get_results(catalogue, lab_id="premier") == []


def test_submit_sans_mesure_ne_dit_pas_enregistre(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zéro test exécuté n'est pas une note de zéro, et ne s'enregistre pas.

    L'invariant est ancien (issue #168) et tenu côté base ; le message, lui,
    annonçait encore un enregistrement. Un `conftest.py` qui lève à l'import ou
    une machine injoignable donnent ce cas.
    """
    from dsoxlab.cli import progression
    from dsoxlab.services.lab_service import CheckResult

    # Sur `progression` et non sur `_validation` : `submit` a importé
    # `_run_check` par son nom au chargement du module, donc c'est ce binding-là
    # qu'il appelle. Poser l'attribut ailleurs laisse le vrai pytest tourner —
    # mesuré, le test passait alors sur un vrai 100/100.
    monkeypatch.setattr(
        progression, "_run_check",
        lambda *a, **k: (CheckResult(False, "", 0, 0), 0, 0),
    )

    resultat = runner.invoke(app, ["submit", "premier"], env={"COLUMNS": "200"})

    assert resultat.exit_code == 0, resultat.output
    assert "Submission recorded" not in resultat.output
    assert "nothing was recorded" in resultat.output


def test_submit_dit_enregistre_quand_ca_l_est(catalogue: Path) -> None:
    """Le contre-exemple : sans lui, les deux tests ci-dessus passeraient à vide."""
    resultat = runner.invoke(app, ["submit", "premier"], env={"COLUMNS": "200"})

    assert resultat.exit_code == 0, resultat.output
    assert "Submission recorded" in resultat.output
    assert len(get_results(catalogue, lab_id="premier")) == 1


# ── l'ordre de `--help` est décidé, pas hérité des imports ───────────────────

def test_chaque_groupe_a_son_rang_declare() -> None:
    """Un groupe absent de `_ORDRE_GROUPES` prend le rang de son import.

    C'était le cas de `new` : son rang dans `--help` dépendait de l'ordre
    d'import des modules, donc d'un détail qui n'a rien à voir avec la
    pédagogie. Le fichier déclare l'ordre justement pour que ce ne soit pas le
    cas.
    """
    from dsoxlab.cli import _ORDRE_GROUPES

    declares = set(_ORDRE_GROUPES)
    reels = {groupe.name for groupe in app.registered_groups if groupe.name}

    assert reels <= declares, f"groupes sans rang déclaré : {sorted(reels - declares)}"
