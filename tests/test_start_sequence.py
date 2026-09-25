"""`dsoxlab start` annonce sa séquence, et nomme l'étape qui casse (issue #79).

Cette commande a été **révisée avant d'être écrite**, et la révision gouverne ce
que ces tests vérifient. L'argument de l'issue : un raccourci qui enchaîne six
étapes implicitement rend les échecs opaques, là où toute la milestone a consisté
à *nommer* ce qui manque. Et pour un outil pédagogique, la séquence est du
contenu : l'apprenant devra la refaire sans dsoxlab.

D'où le critère non négociable, et le premier test de ce fichier : **chaque étape
est annoncée avec la commande qui la rejoue seule, et un échec nomme celle qui a
cassé.** Un `start` qui se contenterait de marcher, sans dire par où il passe,
échouerait à cette issue même en atteignant la session.

Les deux autres propriétés testées ici viennent des critères d'acceptation : la
séquence couvre les deux runtimes, dont un cas « infrastructure absente », et
elle est idempotente.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app

runner = CliRunner()

_META = """\
repo:
  id: sequence
  category: domaine

infra:
  provider: kvm
  network: reseau
  cidr: 10.10.10.0/24
  hosts:
    - name: un.lab
      distro: alma10
"""

_LAB_SHELL = """\
id: lab-shell
title: Lab shell
level: l1
skills: [demo]
distros: [any]
doc_url: https://example.test/docs/shell/
runtime:
  type: shell
  workdir: challenge/work
"""

_LAB_VM = """\
id: lab-vm
title: Lab vm
level: l1
skills: [demo]
distros: [alma10]
doc_url: https://example.test/docs/vm/
runtime:
  type: vm
  targets:
    - name: alma
      host: un.lab
  default: alma
"""


@pytest.fixture
def catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "meta.yml").write_text(_META, encoding="utf-8")
    for nom, contenu in (("lab-shell", _LAB_SHELL), ("lab-vm", _LAB_VM)):
        dossier = tmp_path / "labs" / "domaine" / nom
        (dossier / "challenge" / "tests").mkdir(parents=True)
        (dossier / "lab.yaml").write_text(contenu, encoding="utf-8")
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.setenv("HOME", str(tmp_path / "maison"))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    return tmp_path


@pytest.fixture
def etapes_simulees(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Neutralise ce que les étapes FONT, pour n'observer que ce qu'elles DISENT.

    Aucune de ces simulations ne porte sur `start` lui-même : provisionner et run
    sont les commandes qu'il orchestre, et c'est l'orchestration qu'on mesure.
    """
    from dsoxlab.cli import demarrage
    from dsoxlab.services import doctor

    joue: dict[str, Any] = {"provision": 0, "run": []}

    def _faux_provision(root: Path, **kw: Any) -> None:
        joue["provision"] += 1

    def _faux_run(**kw: Any) -> None:
        joue["run"].append(kw)

    monkeypatch.setattr(demarrage, "provisionner", _faux_provision, raising=False)
    # `start` importe localement : on remplace donc à la SOURCE, sinon l'import
    # irait rechercher l'original et le test passerait en croyant mesurer.
    import dsoxlab.cli.infrastructure as infra_cli
    import dsoxlab.cli.parcours as parcours_cli
    monkeypatch.setattr(infra_cli, "provisionner", _faux_provision)
    monkeypatch.setattr(parcours_cli, "run", _faux_run)
    monkeypatch.setattr(
        doctor, "collect_checks",
        lambda _root, _meta: doctor.DoctorReport(
            required=[doctor._check("python", True, "3.13")],
        ),
    )
    return joue


# ── le critère non négociable ────────────────────────────────────────────────

def test_chaque_etape_est_annoncee_avec_sa_commande(
    catalogue: Path, etapes_simulees: dict[str, Any]
) -> None:
    """Sans cela, `start` échouerait à l'issue même en atteignant la session."""
    resultat = runner.invoke(app, ["start", "lab-shell"])

    assert resultat.exit_code == 0, resultat.output
    for attendu in ("1/3", "2/3", "3/3",
                    "dsoxlab use domaine", "dsoxlab doctor",
                    "dsoxlab run lab-shell"):
        assert attendu in resultat.output, f"absent de la sortie : {attendu}"


def test_un_echec_nomme_l_etape_et_sa_commande(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch,
    etapes_simulees: dict[str, Any],
) -> None:
    """Le cœur de la révision de l'issue : ne pas rendre un échec global.

    On fait échouer les prérequis, l'étape la plus fréquente chez un débutant.
    """
    from dsoxlab.services import doctor

    monkeypatch.setattr(
        doctor, "collect_checks",
        lambda _root, _meta: doctor.DoctorReport(
            required=[doctor._check("terraform", False, "introuvable")],
        ),
    )

    resultat = runner.invoke(app, ["start", "lab-shell"])

    assert resultat.exit_code == 2, resultat.output
    # L'étape est nommée, avec son rang…
    assert "2/3" in resultat.output
    # …et la commande qui la rejoue seule.
    assert "dsoxlab doctor" in resultat.output
    # Et rien au-delà n'a été tenté.
    assert etapes_simulees["run"] == []


def test_rien_au_dela_de_l_etape_en_echec_n_est_tente(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch,
    etapes_simulees: dict[str, Any],
) -> None:
    """Un `start` qui continuerait après un échec masquerait sa cause."""
    import typer

    import dsoxlab.cli.infrastructure as infra_cli

    def _provision_qui_echoue(root: Path, **kw: Any) -> None:
        raise typer.Exit(8)

    monkeypatch.setattr(infra_cli, "provisionner", _provision_qui_echoue)

    resultat = runner.invoke(app, ["start", "lab-vm"])

    # Le code de l'étape, pas un code inventé pour `start` : 8 est celui de
    # `provision` quand des hôtes ne répondent pas.
    assert resultat.exit_code == 8, resultat.output
    assert "3/4" in resultat.output
    assert "dsoxlab provision" in resultat.output
    assert etapes_simulees["run"] == []


# ── les deux runtimes, et le cas « infrastructure absente » ──────────────────

def test_un_lab_shell_n_a_pas_d_etape_d_infrastructure(
    catalogue: Path, etapes_simulees: dict[str, Any]
) -> None:
    """Annoncer « infrastructure — sautée » serait du bruit sur un lab shell."""
    resultat = runner.invoke(app, ["start", "lab-shell"])

    assert "3 steps" in resultat.output
    assert "infrastructure" not in resultat.output
    assert etapes_simulees["provision"] == 0


def test_un_lab_vm_sans_infrastructure_la_monte(
    catalogue: Path, etapes_simulees: dict[str, Any]
) -> None:
    """Le cas exact que l'issue décrit : `run` seul échouerait ici."""
    resultat = runner.invoke(app, ["start", "lab-vm"])

    assert resultat.exit_code == 0, resultat.output
    assert "4 steps" in resultat.output
    assert etapes_simulees["provision"] == 1
    assert etapes_simulees["run"] and etapes_simulees["run"][0]["lab_id"] == "lab-vm"


def test_une_infra_deja_montee_n_est_pas_remontee(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch,
    etapes_simulees: dict[str, Any],
) -> None:
    """L'idempotence exigée : relancé sur un lab prêt, il reprend la session.

    On lit le state plutôt que de sonder en SSH : une machine éteinte reste
    provisionnée, et « est-ce qu'elle répond » est la question de `status`.
    """
    from dsoxlab.cli import demarrage

    monkeypatch.setattr(demarrage, "_infra_prete", lambda _root: True)

    resultat = runner.invoke(app, ["start", "lab-vm"])

    assert resultat.exit_code == 0, resultat.output
    assert "already provisioned" in resultat.output
    assert etapes_simulees["provision"] == 0
    # La session s'ouvre quand même : c'est tout l'intérêt de l'idempotence.
    assert etapes_simulees["run"]


# ── la séquence ne bouge pas d'une exécution à l'autre ───────────────────────

def test_la_sequence_est_stable_entre_deux_appels(
    catalogue: Path, etapes_simulees: dict[str, Any]
) -> None:
    """Un total qui change d'un run à l'autre est déroutant.

    Le premier essai de cette commande passait de 3 à 2 étapes au second appel,
    parce que le contexte était déjà posé — ce qui cachait `dsoxlab use`, une
    commande que l'apprenant doit connaître. Une étape déjà faite reste annoncée.
    """
    premier = runner.invoke(app, ["start", "lab-shell"])
    second = runner.invoke(app, ["start", "lab-shell"])

    assert "3 steps" in premier.output
    assert "3 steps" in second.output
    assert "already on" in second.output
    assert "1/3" in second.output


def test_sans_argument_il_prend_le_lab_suggere(
    catalogue: Path, etapes_simulees: dict[str, Any]
) -> None:
    """Le seul raccourci que la commande s'autorise, et il est sans ambiguïté."""
    runner.invoke(app, ["use", "domaine"])

    resultat = runner.invoke(app, ["start"])

    assert resultat.exit_code == 0, resultat.output
    assert etapes_simulees["run"]
    assert etapes_simulees["run"][0]["lab_id"] in {"lab-shell", "lab-vm"}


def test_un_identifiant_inconnu_sort_en_un(
    catalogue: Path, etapes_simulees: dict[str, Any]
) -> None:
    resultat = runner.invoke(app, ["start", "jamais-vu"])

    assert resultat.exit_code == 1
    assert etapes_simulees["run"] == []


# ── la lecture de l'infrastructure, sans la simuler ─────────────────────────

def test_infra_prete_lit_vraiment_l_inventaire(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le test qui manquait, et sans lequel un vrai défaut est passé.

    Les tests d'idempotence ci-dessus **simulent** `_infra_prete`, donc aucun
    n'aurait vu que la fonction lisait `labenv` à la racine de l'inventaire au
    lieu de `all.children.labenv`. Elle rendait donc toujours « à provisionner »,
    et la relance remontait une infrastructure déjà debout — constaté en montant
    trois VM pour de vrai.

    Ici on ne simule que Terraform, jamais la fonction mesurée.
    """
    from dsoxlab.cli import demarrage
    from dsoxlab.infra import inventory

    monkeypatch.setattr(
        inventory, "read_terraform_outputs",
        lambda _meta: {"hosts": {"value": {"un.lab": "10.10.10.11"}}},
    )
    assert demarrage._infra_prete(catalogue) is True


def test_infra_absente_se_voit_dans_l_inventaire(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aucune adresse : il y a bien quelque chose à monter."""
    from dsoxlab.cli import demarrage
    from dsoxlab.infra import inventory

    monkeypatch.setattr(inventory, "read_terraform_outputs", lambda _meta: None)

    assert demarrage._infra_prete(catalogue) is False


def test_un_depot_sans_hote_declare_n_a_rien_a_monter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le contre-exemple du dépôt sans bloc `infra:` : rien à provisionner."""
    from dsoxlab.cli import demarrage

    (tmp_path / "meta.yml").write_text(
        "repo:\n  id: sans-infra\n  category: domaine\n", encoding="utf-8")
    monkeypatch.setenv("LAB_HOME", str(tmp_path))

    assert demarrage._infra_prete(tmp_path) is True
