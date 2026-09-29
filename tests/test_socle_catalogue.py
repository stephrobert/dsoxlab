"""Le socle d'un catalogue : joué une fois, après le provisionnement.

Un catalogue Kubernetes doit poser un cluster kubeadm avant que le moindre lab ait
un sens. Ce socle n'appartient à aucun lab — il appartient au catalogue — et faute
d'un point d'accroche après `provision`, chaque `setup.yaml` devait inclure
`../../shared/kubeadm-cluster.yml` (issue #213). Trois défauts : un auteur peut
l'oublier, le chemin relatif couple le lab à sa profondeur dans `labs/`, et `reset`
rejoue le socle.

Ce que ces tests tiennent, par ordre d'importance :

- **joué une fois**, et rejoué quand son contenu change — pas à chaque `provision` ;
- **le marqueur ne s'écrit qu'après un succès**, l'invariant que l'appliance a
  appris à ses frais : un marqueur posé sur un échec condamne en silence ;
- **un socle déclaré et absent se dit**, comme une fixture déclarée et absente ;
- **rien ne sort du catalogue** : le contrat décrit un dépôt, il ne désigne pas
  des fichiers de la machine.

Aucun de ces tests ne provisionne : ils portent sur la décision — quoi jouer, et
quand — qui est la partie où un défaut passe inaperçu. Que le playbook s'exécute
est le travail d'`infra/ansible.py`, éprouvé ailleurs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.models import RepoMetadata
from dsoxlab.services.bootstrap import (
    BootstrapAbsent,
    a_jouer,
    chemin_du_playbook,
    empreinte_enregistree,
    enregistrer,
)

runner = CliRunner()

_META = """\
repo:
  id: socle-essai
  category: domaine
infra:
  provider: kvm
  network: essai-net
  cidr: 10.10.90.0/24
{bootstrap}  hosts:
    - name: n1.lab
      distro: debian13
"""


def _repo(tmp_path: Path, *, bootstrap: str | None = "bootstrap.yaml") -> RepoMetadata:
    ligne = "" if bootstrap is None else f"  bootstrap: {bootstrap}\n"
    meta = tmp_path / "meta.yml"
    meta.write_text(_META.format(bootstrap=ligne), encoding="utf-8")
    return RepoMetadata.from_yaml(meta)


def _playbook(tmp_path: Path, nom: str = "bootstrap.yaml", corps: str = "") -> Path:
    chemin = tmp_path / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        corps or "- hosts: all\n  tasks:\n    - ansible.builtin.ping:\n",
        encoding="utf-8",
    )
    return chemin


@pytest.fixture(autouse=True)
def _etat_isole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """L'état du socle vit sous `XDG_STATE_HOME` : le déplacer, sinon ces tests
    écrivent dans le répertoire personnel de qui les joue."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


# ── le contrat ───────────────────────────────────────────────────────────────

def test_un_catalogue_sans_socle_n_en_declare_pas(tmp_path: Path) -> None:
    """Le cas courant : la plupart des catalogues n'ont aucune base à poser."""
    repo = _repo(tmp_path, bootstrap=None)

    assert repo.infra.bootstrap == ""
    assert chemin_du_playbook(repo) is None
    assert a_jouer(repo) is None


def test_le_chemin_est_relatif_au_depot(tmp_path: Path) -> None:
    repo = _repo(tmp_path, bootstrap="infra/socle.yaml")

    chemin = chemin_du_playbook(repo)

    assert chemin == tmp_path / "infra" / "socle.yaml"


@pytest.mark.parametrize("hors", ["/etc/ansible/socle.yaml", "../ailleurs.yaml"])
def test_un_chemin_hors_du_depot_est_refuse(tmp_path: Path, hors: str) -> None:
    """Le contrat décrit un catalogue, il ne désigne pas la machine."""
    repo = _repo(tmp_path, bootstrap=hors)

    with pytest.raises(BootstrapAbsent) as refus:
        chemin_du_playbook(repo)

    assert refus.value.cle == "bootstrap_hors_depot"


def test_un_socle_declare_et_absent_se_dit(tmp_path: Path) -> None:
    """Même règle qu'une fixture déclarée et absente : le silence coûte un lab."""
    repo = _repo(tmp_path)

    with pytest.raises(BootstrapAbsent) as refus:
        a_jouer(repo)

    assert refus.value.cle == "bootstrap_absent"


def test_l_exception_porte_une_cle_pas_une_phrase(tmp_path: Path) -> None:
    """La commande parle la langue de l'apprenant, pas ce module."""
    repo = _repo(tmp_path)

    with pytest.raises(BootstrapAbsent) as refus:
        a_jouer(repo)

    assert refus.value.cle.startswith("bootstrap_")
    assert refus.value.chemin.endswith("bootstrap.yaml")


# ── une fois, et pas une de plus ─────────────────────────────────────────────

def test_un_socle_jamais_pose_est_a_jouer(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _playbook(tmp_path)

    travail = a_jouer(repo)

    assert travail is not None
    chemin, empreinte = travail
    assert chemin.name == "bootstrap.yaml"
    assert len(empreinte) == 64


def test_un_socle_pose_n_est_pas_rejoue(tmp_path: Path) -> None:
    """C'est la propriété que l'issue demande : pas à chaque provision."""
    repo = _repo(tmp_path)
    _playbook(tmp_path)
    travail = a_jouer(repo)
    assert travail is not None
    enregistrer(repo, travail[1], ["n1.lab"])

    assert a_jouer(repo) is None


def test_un_socle_modifie_est_rejoue(tmp_path: Path) -> None:
    """La seule chose utile à faire d'un socle qui a changé."""
    repo = _repo(tmp_path)
    _playbook(tmp_path)
    travail = a_jouer(repo)
    assert travail is not None
    enregistrer(repo, travail[1], ["n1.lab"])

    _playbook(tmp_path, corps="- hosts: all\n  tasks:\n    - ansible.builtin.debug:\n")

    assert a_jouer(repo) is not None


def test_force_rejoue_un_socle_a_jour(tmp_path: Path) -> None:
    """`provision --bootstrap` : rejouable sans dégât, comme l'issue l'exige."""
    repo = _repo(tmp_path)
    _playbook(tmp_path)
    travail = a_jouer(repo)
    assert travail is not None
    enregistrer(repo, travail[1], ["n1.lab"])

    assert a_jouer(repo, force=True) is not None


def test_le_contenu_decide_pas_la_date(tmp_path: Path) -> None:
    """Un `git clone` réécrit toutes les dates : un socle inchangé le resterait."""
    repo = _repo(tmp_path)
    chemin = _playbook(tmp_path)
    travail = a_jouer(repo)
    assert travail is not None
    enregistrer(repo, travail[1], ["n1.lab"])

    chemin.touch()

    assert a_jouer(repo) is None


def test_un_etat_illisible_fait_rejouer(tmp_path: Path) -> None:
    """Rejouer un socle idempotent coûte du temps ; s'en passer coûte un lab."""
    repo = _repo(tmp_path)
    _playbook(tmp_path)
    travail = a_jouer(repo)
    assert travail is not None
    enregistrer(repo, travail[1], ["n1.lab"])

    etat = tmp_path / "state" / "dsoxlab" / "socle-essai" / "bootstrap.json"
    etat.write_text("ceci n'est pas du JSON", encoding="utf-8")

    assert empreinte_enregistree(repo) == ""
    assert a_jouer(repo) is not None


def test_deux_catalogues_ne_partagent_pas_leur_socle(tmp_path: Path) -> None:
    """Namespacé par `repo.id` : l'un ne répond pas pour l'autre."""
    premier = tmp_path / "a"
    second = tmp_path / "b"
    for racine, ident in ((premier, "socle-a"), (second, "socle-b")):
        racine.mkdir()
        (racine / "meta.yml").write_text(
            _META.format(bootstrap="  bootstrap: bootstrap.yaml\n").replace(
                "socle-essai", ident
            ),
            encoding="utf-8",
        )
        _playbook(racine)

    repo_a = RepoMetadata.from_yaml(premier / "meta.yml")
    repo_b = RepoMetadata.from_yaml(second / "meta.yml")
    travail = a_jouer(repo_a)
    assert travail is not None
    enregistrer(repo_a, travail[1], ["n1.lab"])

    assert a_jouer(repo_a) is None
    assert a_jouer(repo_b) is not None


# ── ce que l'auteur du catalogue voit ────────────────────────────────────────

def _catalogue_avec_socle(catalogue: Path, declare: str) -> None:
    meta = catalogue / "meta.yml"
    meta.write_text(
        meta.read_text(encoding="utf-8")
        + f"infra:\n  network: essai\n  bootstrap: {declare}\n",
        encoding="utf-8",
    )


def test_validate_structure_refuse_un_socle_absent(catalogue: Path) -> None:
    _catalogue_avec_socle(catalogue, "socle.yaml")

    resultat = runner.invoke(app, ["validate-structure"])

    assert resultat.exit_code == 1
    assert "socle.yaml" in resultat.output


def test_validate_structure_refuse_un_socle_dehors(catalogue: Path) -> None:
    _catalogue_avec_socle(catalogue, "/etc/ansible/socle.yaml")

    resultat = runner.invoke(app, ["validate-structure"])

    assert resultat.exit_code == 1
    assert "/etc/ansible/socle.yaml" in resultat.output


def test_validate_structure_accepte_un_socle_present(catalogue: Path) -> None:
    _catalogue_avec_socle(catalogue, "socle.yaml")
    (catalogue / "socle.yaml").write_text(
        "- hosts: all\n  tasks: []\n", encoding="utf-8"
    )

    resultat = runner.invoke(app, ["validate-structure"])

    assert resultat.exit_code == 0, resultat.output


def test_un_catalogue_sans_socle_ne_voit_rien(catalogue: Path) -> None:
    """Un champ facultatif absent n'est pas une anomalie à signaler."""
    resultat = runner.invoke(app, ["validate-structure"])

    assert resultat.exit_code == 0, resultat.output
    assert "bootstrap" not in resultat.output


# ── l'option, et le code de sortie ───────────────────────────────────────────

def test_l_option_de_rejeu_existe() -> None:
    """`provision` porte bien `--bootstrap`, et on le demande à la commande.

    Deux versions de ce test ont échoué en CI en passant en local, toutes deux
    parce qu'elles lisaient le **rendu** de `--help` : Rich coupe, aligne et
    tronque selon une largeur qui ne se reproduit pas d'une machine à l'autre.
    Un test qui lit un rendu mesure le moteur de rendu autant que son sujet.

    Ce qu'on veut savoir est ailleurs et ne dépend de rien : l'option existe-t-elle
    sur la commande ?
    """
    import typer.main

    commande = typer.main.get_command(app)
    provision = commande.commands["provision"]  # type: ignore[attr-defined]
    noms = {nom for param in provision.params for nom in param.opts}

    assert "--bootstrap" in noms, sorted(noms)


def test_le_code_de_sortie_du_socle_est_stable() -> None:
    """Un code n'a ni schéma ni version : celui-ci vaut 11, et le reste."""
    from dsoxlab.exit_codes import ExitCode

    assert ExitCode.BOOTSTRAP_ECHOUE == 11
