"""Trois promesses que la documentation faisait et que le code ne tenait pas.

Relevées par une relecture complète de la documentation avant la 0.3.0, et
c'est ce qui les rend intéressantes : chacune était **écrite** quelque part —
dans le contrat, dans le CHANGELOG, dans la page de sécurité — et personne
n'avait vérifié que le code suivait. Une documentation qui promet plus que le
code ne fait pas qu'induire en erreur : elle fait écrire des labs et des
scripts sur une base fausse.

1. `destroy` laissait le marqueur du socle : un `provision` suivant sautait le
   socle, et les labs tournaient sur une machine nue — la panne même que
   `infra.bootstrap` supprime.
2. `progress` comptait les labs `validation`, que rien ne peut valider : un
   dénominateur inatteignable, alors que le contrat annonce qu'ils sont ignorés.
3. `DSOXLAB_PORTAL_LOCAL=0` **activait** la dérogation de sécurité, la valeur
   étant seulement testée non vide.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.models import RepoMetadata
from dsoxlab.security.urls import VARIABLE_PORTAIL_LOCAL, URLRefusee, url_de_portail
from dsoxlab.services.bootstrap import a_jouer, empreinte_enregistree, enregistrer, oublier
from dsoxlab.sessions.store import record_result

runner = CliRunner()

_META = """\
repo:
  id: audit-essai
  category: domaine
infra:
  provider: kvm
  network: audit
  bootstrap: bootstrap.yaml
  hosts:
    - name: n1.lab
      distro: debian13
"""


@pytest.fixture
def depot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RepoMetadata:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    (tmp_path / "meta.yml").write_text(_META, encoding="utf-8")
    (tmp_path / "bootstrap.yaml").write_text(
        "- hosts: all\n  tasks: []\n", encoding="utf-8"
    )
    return RepoMetadata.from_yaml(tmp_path / "meta.yml")


# ── 1. Le socle ne survit pas à la destruction de ses machines ──────────────

def test_detruire_fait_oublier_le_socle(depot: RepoMetadata) -> None:
    """Sinon le prochain provision saute le socle sur des machines neuves."""
    travail = a_jouer(depot)
    assert travail is not None
    enregistrer(depot, travail[1], ["n1.lab"])
    assert a_jouer(depot) is None, "le socle devrait être considéré comme posé"

    assert oublier(depot) is True
    assert empreinte_enregistree(depot) == ""
    assert a_jouer(depot) is not None, "après destroy, le socle doit se rejouer"


def test_oublier_un_socle_absent_convient(depot: RepoMetadata) -> None:
    """Un catalogue sans socle passe par le même chemin, et ne doit rien voir."""
    assert oublier(depot) is False


def test_oublier_est_idempotent(depot: RepoMetadata) -> None:
    travail = a_jouer(depot)
    assert travail is not None
    enregistrer(depot, travail[1], ["n1.lab"])

    assert oublier(depot) is True
    assert oublier(depot) is False


# ── 2. Un lab qui ne note personne ne compte pas dans une progression ───────

def _catalogue_avec_validation(catalogue: Path) -> None:
    """Fait du second lab un lab `validation` : il défend un guide, il ne note pas."""
    lab = catalogue / "labs" / "domaine" / "second" / "lab.yaml"
    lab.write_text(
        lab.read_text(encoding="utf-8") + "lab_type: validation\n", encoding="utf-8"
    )


def test_progress_ignore_un_lab_de_validation(catalogue: Path) -> None:
    """Le contrat l'annonce pour toute la progression, pas seulement pour `next`."""
    _catalogue_avec_validation(catalogue)
    runner.invoke(app, ["use", "domaine"])

    resultat = runner.invoke(app, ["progress", "--json"])

    assert resultat.exit_code == 0, resultat.output
    document = json.loads(resultat.stdout)
    assert document["summary"]["total"] == 1, document["summary"]
    assert [lab["id"] for lab in document["labs"]] == ["premier"]


def test_un_denominateur_inatteignable_disparait(catalogue: Path) -> None:
    """Deux labs dont un `validation`, un résultat : la progression est complète.

    Avant, elle affichait 1/2 pour toujours — le second ne pouvant jamais
    recevoir de note.
    """
    _catalogue_avec_validation(catalogue)
    record_result(
        catalogue, lab_id="premier", section="domaine", score=100, max_score=100,
        passed_tests=1, total_tests=1, hints_used=0,
    )
    runner.invoke(app, ["use", "domaine"])

    document = json.loads(runner.invoke(app, ["progress", "--json"]).stdout)

    assert document["summary"]["attempted"] == document["summary"]["total"] == 1


def test_next_ne_compte_pas_ce_qu_il_ne_propose_pas(catalogue: Path) -> None:
    """`remaining` annonçait un travail qui ne s'achèverait jamais."""
    _catalogue_avec_validation(catalogue)
    runner.invoke(app, ["use", "domaine"])

    document = json.loads(runner.invoke(app, ["next", "--json"]).stdout)

    assert document["remaining"] == 1


# ── 3. Une variable de sécurité ne s'active pas sur « 0 » ───────────────────

@pytest.mark.parametrize("valeur", ["1", "true", "TRUE", "yes", "on"])
def test_la_derogation_s_active_sur_une_valeur_franche(
    valeur: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(VARIABLE_PORTAIL_LOCAL, valeur)

    assert url_de_portail("http://localhost:4321/p/")


@pytest.mark.parametrize("valeur", ["0", "false", "no", "off", "", " "])
def test_la_derogation_ne_s_active_pas_sur_un_refus(
    valeur: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`DSOXLAB_PORTAL_LOCAL=0` activait la dérogation : « non vide » suffisait.

    C'est la dernière chose qu'on attend d'une variable dont le nom promet le
    contraire, et le genre de défaut qu'on ne voit qu'en le cherchant.
    """
    monkeypatch.setenv(VARIABLE_PORTAIL_LOCAL, valeur)

    with pytest.raises(URLRefusee):
        url_de_portail("http://localhost:4321/p/")


def test_la_variable_porte_un_nom_anglais() -> None:
    """Les variables publiques sont en anglais ; celle-ci l'a été de justesse.

    Renommée avant la 0.3.0, donc avant qu'un utilisateur l'ait écrite quelque
    part. Après publication, le coût aurait été tout autre.
    """
    assert VARIABLE_PORTAIL_LOCAL == "DSOXLAB_PORTAL_LOCAL"
