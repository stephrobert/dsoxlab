"""`start` ne monte et ne compte que les hôtes du lab joué (issue #358).

Le défaut, lu dans le code de 0.8.1 et mesuré sur `kubernetes-dsoxlab-training` :
`doctor` et `start` raisonnaient sur **tout le catalogue**, jamais sur le lab
joué.

- `doctor` additionnait les `ram_mb` de tous les hôtes du `meta.yml`, et ce
  contrôle est **requis** dès qu'un hôte est déclaré ;
- `start` lisait `rapport.failing()` et sortait en **code 2** ;
- `_infra_prete` rendait faux dès qu'un hôte du catalogue n'avait pas d'adresse,
  **sans même sonder**, et `start` remontait alors tout le plan.

Conséquence chiffrée : le catalogue Kubernetes déclare trois hôtes, 10752 Mo au
total, mais **61 de ses 66 labs ne visent qu'un seul hôte** et aucun ne demande
plus de 6656 Mo. Ajouter deux labs sur un troisième hôte rendait donc les 66
labs injouables sur une machine à 8 Go.

Un second défaut se cumulait, et il tient à l'offre et non à la demande : le
contrôle compare le `MemAvailable` **du moment** à la demande, sans retirer les
hôtes **déjà démarrés**, dont la mémoire est pourtant déjà prise. Un second
`start` la comptait donc deux fois et refusait une infrastructure déjà debout.

Chaque test d'ici porte un critère d'acceptation de l'issue, et chacun a été
éprouvé contre le code d'avant la correction : tous échouaient.

    pytest tests/test_start_hotes_du_lab.py -v
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app

runner = CliRunner()

#: Trois hôtes, comme le catalogue Kubernetes : deux pour le cluster, un pour
#: kind. Les tailles sont celles du vrai catalogue, parce que les chiffres de
#: l'issue s'y réfèrent et qu'un test qui les change ne la défend plus.
_META = """\
repo:
  id: trois-hotes
  category: domaine

infra:
  provider: kvm
  network: reseau
  cidr: 10.10.50.0/24
  hosts:
    - name: cp.lab
      distro: ubuntu24
      ram_mb: 4096
    - name: w1.lab
      distro: ubuntu24
      ram_mb: 2560
    - name: kind.lab
      distro: debian13
      ram_mb: 4096
"""

#: Le lab qui ne vise qu'un hôte : 61 des 66 labs du catalogue réel sont ainsi.
_LAB_UN_HOTE = """\
id: lab-un-hote
title: Un seul hote
level: l1
skills: [demo]
distros: [debian13]
doc_url: https://example.test/docs/un/
runtime:
  type: vm
  targets:
    - name: kind
      host: kind.lab
  default: kind
"""

#: Le lab qui vise deux hôtes, le second par un RÔLE. Les cinq labs du
#: catalogue réel qui ont besoin d'un worker le déclarent tous ainsi : les
#: ignorer sous-estimerait leur besoin.
_LAB_DEUX_HOTES = """\
id: lab-deux-hotes
title: Deux hotes par un role
level: l1
skills: [demo]
distros: [ubuntu24]
doc_url: https://example.test/docs/deux/
runtime:
  type: vm
  targets:
    - name: cluster
      host: cp.lab
      roles:
        worker: w1.lab
  default: cluster
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


@pytest.fixture
def catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "meta.yml").write_text(_META, encoding="utf-8")
    for nom, contenu in (
        ("lab-un-hote", _LAB_UN_HOTE),
        ("lab-deux-hotes", _LAB_DEUX_HOTES),
        ("lab-shell", _LAB_SHELL),
    ):
        dossier = tmp_path / "labs" / "domaine" / nom
        (dossier / "challenge" / "tests").mkdir(parents=True)
        (dossier / "lab.yaml").write_text(contenu, encoding="utf-8")
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "etat"))
    monkeypatch.setenv("HOME", str(tmp_path / "maison"))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    # Un `DSOXLAB_TARGET` hérité de l'environnement choisirait la target à la
    # place du lab, et ces tests mesurent justement quels hôtes en découlent.
    monkeypatch.delenv("DSOXLAB_TARGET", raising=False)
    return tmp_path


@pytest.fixture
def espion(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Observe ce que `start` DEMANDE, sans rien monter.

    On n'intercepte pas `_hotes_du_lab` ni `_hotes_a_monter` : ce sont elles
    qu'on mesure. On intercepte ce qu'elles alimentent, `provisionner` et
    `collect_checks`, plus la sonde réseau, qui est la seule chose qu'un test
    ne peut pas jouer pour de vrai.
    """
    from dsoxlab.cli import demarrage
    from dsoxlab.services import doctor

    vu: dict[str, Any] = {"provision_host": None, "doctor_hosts": None, "run": []}

    def _faux_provision(root: Path, **kw: Any) -> None:
        vu["provision_host"] = kw.get("host")

    def _faux_run(**kw: Any) -> None:
        vu["run"].append(kw)

    def _faux_collect(root: Path, meta: Any, hosts: list[str] | None = None) -> Any:
        vu["doctor_hosts"] = hosts
        return doctor.DoctorReport(required=[doctor._check("python", True, "3.13")])

    import dsoxlab.cli.infrastructure as infra_cli
    import dsoxlab.cli.parcours as parcours_cli
    monkeypatch.setattr(demarrage, "provisionner", _faux_provision, raising=False)
    monkeypatch.setattr(infra_cli, "provisionner", _faux_provision)
    monkeypatch.setattr(parcours_cli, "run", _faux_run)
    monkeypatch.setattr(doctor, "collect_checks", _faux_collect)
    return vu


# ----------------------------------------------------------------------
# Le garde-fou de ce module. Sans lui, un `catalogue` mal bâti ferait
# passer les tests pour de mauvaises raisons.
# ----------------------------------------------------------------------
def test_le_catalogue_du_banc_declare_bien_trois_hotes(catalogue: Path) -> None:
    from dsoxlab.discovery.repo import read_repo_metadata

    meta = read_repo_metadata(catalogue)
    assert [h.name for h in meta.infra.hosts] == ["cp.lab", "w1.lab", "kind.lab"]
    assert sum(h.ram_mb for h in meta.infra.hosts) == 10752


# ----------------------------------------------------------------------
# Critère : un lab qui cible un hôte ne monte et ne compte que lui.
# ----------------------------------------------------------------------
def test_un_lab_mono_hote_ne_monte_que_le_sien(
    catalogue: Path, espion: dict[str, Any]
) -> None:
    resultat = runner.invoke(app, ["start", "lab-un-hote"])

    assert resultat.exit_code == 0, resultat.output
    assert espion["provision_host"] == ["kind.lab"], (
        "`start` doit provisionner le seul hôte du lab. Avant la correction il "
        "passait `host=None`, donc montait les trois."
    )


def test_le_controle_memoire_ne_compte_que_l_hote_du_lab(
    catalogue: Path, espion: dict[str, Any]
) -> None:
    """Le cœur de l'issue : la demande, c'est le lab, pas le catalogue."""
    resultat = runner.invoke(app, ["start", "lab-un-hote"])

    assert resultat.exit_code == 0, resultat.output
    assert espion["doctor_hosts"] == ["kind.lab"], (
        "le contrôle de ressources doit porter sur le seul hôte du lab. Avant "
        "la correction, `collect_checks` ne recevait aucun hôte et additionnait "
        "les 10752 Mo du catalogue, ce qui refusait le lab en code 2 sur une "
        "machine à 8 Go."
    )


# ----------------------------------------------------------------------
# Critère : un lab qui cible plusieurs hôtes les monte tous, rôles compris.
# ----------------------------------------------------------------------
def test_un_lab_multi_hotes_monte_aussi_ses_roles(
    catalogue: Path, espion: dict[str, Any]
) -> None:
    """Le contre-témoin du précédent : la restriction ne doit pas trop retirer.

    Sans ce test, la correction pourrait ne monter que l'hôte primaire et
    passerait tous les autres contrôles de ce fichier. Les cinq labs du
    catalogue Kubernetes qui ont besoin d'un worker le déclarent par un rôle.
    """
    resultat = runner.invoke(app, ["start", "lab-deux-hotes"])

    assert resultat.exit_code == 0, resultat.output
    assert espion["provision_host"] == ["cp.lab", "w1.lab"], (
        "un rôle désigne un hôte dont le lab a besoin : l'oublier monterait "
        "une infrastructure incomplète, et le lab échouerait en UNREACHABLE."
    )
    assert espion["doctor_hosts"] == ["cp.lab", "w1.lab"], (
        "la demande de mémoire doit inclure les hôtes des rôles, sinon elle "
        "sous-estime le besoin et laisse passer un provisionnement qui échouera."
    )


# ----------------------------------------------------------------------
# Critère : le cas nominal reste inchangé.
# ----------------------------------------------------------------------
def test_un_lab_shell_ne_restreint_rien(
    catalogue: Path, espion: dict[str, Any]
) -> None:
    """Un lab `shell` ne demande AUCUN hôte, donc aucune mémoire de VM.

    `_sequence` ne lui donne même pas d'étape d'infrastructure. Ce test a
    trouvé un défaut de la première correction : en confondant « pas de
    restriction » et « restriction vide », elle faisait réclamer à un lab
    `shell` les 10752 Mo du catalogue, et le refusait donc sur une petite
    machine pour des VM qu'il ne monte jamais. `None` et `[]` sont depuis deux
    cas distincts.
    """
    resultat = runner.invoke(app, ["start", "lab-shell"])

    assert resultat.exit_code == 0, resultat.output
    assert espion["provision_host"] is None
    assert espion["doctor_hosts"] == [], (
        "un lab sans hôte demande une liste VIDE, pas `None` : la demande de "
        "mémoire est alors nulle, au lieu d'être celle du catalogue entier."
    )


# ----------------------------------------------------------------------
# `_hotes_a_compter` : les replis vont vers le pire cas, jamais vers 0.
# ----------------------------------------------------------------------
def test_la_demande_sans_restriction_est_celle_du_catalogue(catalogue: Path) -> None:
    from dsoxlab.discovery.repo import read_repo_metadata
    from dsoxlab.services.doctor import _hotes_a_compter

    infra = read_repo_metadata(catalogue).infra
    assert sum(h.ram_mb for h in _hotes_a_compter(infra, None)) == 10752


def test_la_demande_restreinte_ne_compte_que_les_hotes_demandes(catalogue: Path) -> None:
    from dsoxlab.discovery.repo import read_repo_metadata
    from dsoxlab.services.doctor import _hotes_a_compter

    infra = read_repo_metadata(catalogue).infra
    assert sum(h.ram_mb for h in _hotes_a_compter(infra, ["kind.lab"])) == 4096
    assert sum(h.ram_mb for h in _hotes_a_compter(infra, ["cp.lab", "w1.lab"])) == 6656


def test_des_hotes_inconnus_ne_font_pas_une_demande_nulle(catalogue: Path) -> None:
    """Le repli qui compte : un FQDN étranger ne doit pas donner « 0 Mo requis ».

    Zéro serait vert sur n'importe quelle machine, et le contrôle cesserait de
    contrôler. On retombe donc sur le catalogue entier, qui est le pire cas.
    """
    from dsoxlab.discovery.repo import read_repo_metadata
    from dsoxlab.services.doctor import _hotes_a_compter

    infra = read_repo_metadata(catalogue).infra
    assert sum(h.ram_mb for h in _hotes_a_compter(infra, ["etranger.lab"])) == 10752


def test_un_hote_inconnu_melange_a_un_connu_ne_compte_que_le_connu(
    catalogue: Path,
) -> None:
    from dsoxlab.discovery.repo import read_repo_metadata
    from dsoxlab.services.doctor import _hotes_a_compter

    infra = read_repo_metadata(catalogue).infra
    retenus = _hotes_a_compter(infra, ["kind.lab", "etranger.lab"])
    assert [h.name for h in retenus] == ["kind.lab"]


# ----------------------------------------------------------------------
# Le chemin complet `collect_checks`, que les appels directs ne couvrent pas.
# ----------------------------------------------------------------------
def test_doctor_seul_annonce_le_total_du_catalogue(catalogue: Path) -> None:
    """Le défaut que les tests directs de `_hotes_a_compter` n'ont PAS vu.

    Ils appelaient la fonction avec `None`, mais `collect_checks` posait
    `hotes_demandes=list(hosts or [])` : sans restriction, l'appelant
    transmettait donc une liste VIDE, qui veut dire « aucun hôte » depuis que
    les deux cas sont distingués. `doctor` annonçait « 0 Mo déclarés », vert
    sur n'importe quelle machine.

    Trouvé en lançant la commande sur un vrai catalogue, pas par un test : d'où
    celui-ci, qui emprunte le chemin entier.
    """
    from dsoxlab.discovery.repo import read_repo_metadata
    from dsoxlab.services.doctor import collect_checks

    rapport = collect_checks(catalogue, read_repo_metadata(catalogue))
    ressources = [c for c in rapport.required if "resources" in c.key]
    assert ressources, "le contrôle de ressources doit être requis, des hôtes sont déclarés"
    assert "10752" in ressources[0].detail, (
        "`doctor` lancé seul doit annoncer le total du catalogue, et non 0 Mo. "
        f"Détail obtenu : {ressources[0].detail!r}"
    )


def test_doctor_restreint_annonce_la_demande_du_lab(catalogue: Path) -> None:
    """Le contre-témoin : sans lui, le test précédent passerait sur un total figé."""
    from dsoxlab.discovery.repo import read_repo_metadata
    from dsoxlab.services.doctor import collect_checks

    rapport = collect_checks(catalogue, read_repo_metadata(catalogue), ["kind.lab"])
    ressources = [c for c in rapport.required if "resources" in c.key]
    assert ressources
    assert "4096" in ressources[0].detail, (
        "restreint à l'hôte kind, le contrôle doit annoncer 4096 Mo. "
        f"Détail obtenu : {ressources[0].detail!r}"
    )


# ----------------------------------------------------------------------
# `Target.hosts()` : la source unique de « quels hôtes ce lab vise ».
# ----------------------------------------------------------------------
def test_les_hotes_d_une_cible_incluent_ses_roles() -> None:
    from dsoxlab.models.runtime import Target

    cible = Target(name="c", host="cp.lab", roles={"worker": "w1.lab"})
    assert cible.hosts() == ["cp.lab", "w1.lab"]


def test_un_role_qui_designe_l_hote_primaire_ne_le_compte_pas_deux_fois() -> None:
    """Sinon la demande de mémoire doublerait cet hôte, et refuserait à tort."""
    from dsoxlab.models.runtime import Target

    cible = Target(name="c", host="cp.lab", roles={"meme": "cp.lab"})
    assert cible.hosts() == ["cp.lab"]


def test_l_ordre_des_hotes_est_stable_et_l_hote_primaire_vient_en_tete() -> None:
    """Ces listes s'affichent : un ordre qui varie se lit comme un changement."""
    from dsoxlab.models.runtime import Target

    cible = Target(name="c", host="cp.lab", roles={"z": "z.lab", "a": "a.lab"})
    assert cible.hosts()[0] == "cp.lab"
    assert cible.hosts() == cible.hosts()


# ----------------------------------------------------------------------
# La mémoire déjà prise ne se redemande pas.
# ----------------------------------------------------------------------
def test_un_hote_qui_repond_n_est_plus_a_monter(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le second défaut de l'issue, côté offre et non côté demande.

    `_check_resources` lit le `MemAvailable` du moment, qui a déjà baissé de ce
    que consomme un hôte en marche. Le redemander le compte deux fois, et un
    second `start` refusait alors une infrastructure déjà debout.
    """
    from dsoxlab.cli import demarrage
    from dsoxlab.infra import inventory

    monkeypatch.setattr(
        inventory, "read_terraform_outputs",
        lambda _meta: {"hosts": {"value": {"kind.lab": "10.10.50.13"}}},
    )
    monkeypatch.setattr(demarrage, "_hote_repond", lambda _adresse, **_kw: True)

    assert demarrage._hotes_a_monter(catalogue, ["kind.lab"]) == []
    assert demarrage._infra_prete(catalogue, ["kind.lab"]) is True


def test_un_hote_qui_ne_repond_pas_reste_a_monter(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le contre-témoin : sans lui, le test précédent passerait sur un « toujours vide ».

    Une adresse dans le state ne prouve pas qu'une machine répond : c'est la
    leçon d'un `provision` sorti en 8 pendant que `start` annonçait « rien à
    reconstruire ».
    """
    from dsoxlab.cli import demarrage
    from dsoxlab.infra import inventory

    monkeypatch.setattr(
        inventory, "read_terraform_outputs",
        lambda _meta: {"hosts": {"value": {"kind.lab": "10.10.50.13"}}},
    )
    monkeypatch.setattr(demarrage, "_hote_repond", lambda _adresse, **_kw: False)

    assert demarrage._hotes_a_monter(catalogue, ["kind.lab"]) == ["kind.lab"]
    assert demarrage._infra_prete(catalogue, ["kind.lab"]) is False


def test_seuls_les_hotes_du_lab_sont_sondes(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le cœur du troisième point de l'issue.

    Avant la correction, `_infra_prete` rendait faux dès qu'un hôte du
    catalogue n'avait pas d'adresse, SANS MÊME SONDER. Ici, seul `kind.lab` est
    dans l'inventaire ; les deux autres n'y sont pas, et cela ne doit plus
    empêcher un lab qui ne vise que `kind.lab` de se jouer.
    """
    from dsoxlab.cli import demarrage
    from dsoxlab.infra import inventory

    sondes: list[str] = []
    monkeypatch.setattr(
        inventory, "read_terraform_outputs",
        lambda _meta: {"hosts": {"value": {"kind.lab": "10.10.50.13"}}},
    )

    def _sonde(adresse: str, **_kw: Any) -> bool:
        sondes.append(adresse)
        return True

    monkeypatch.setattr(demarrage, "_hote_repond", _sonde)

    assert demarrage._hotes_a_monter(catalogue, ["kind.lab"]) == []
    assert sondes == ["10.10.50.13"], (
        "seul l'hôte du lab doit être sondé ; sonder les autres coûte deux "
        "secondes chacun pour une réponse dont on n'a que faire."
    )


def test_sans_restriction_les_hotes_absents_restent_a_monter(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le comportement d'avant est conservé quand aucun lab n'est en main.

    `doctor` et les appelants sans lab doivent continuer à voir le catalogue
    entier : la correction restreint sur demande, elle ne change pas le défaut.
    """
    from dsoxlab.cli import demarrage
    from dsoxlab.infra import inventory

    monkeypatch.setattr(
        inventory, "read_terraform_outputs",
        lambda _meta: {"hosts": {"value": {"kind.lab": "10.10.50.13"}}},
    )
    monkeypatch.setattr(demarrage, "_hote_repond", lambda _adresse, **_kw: True)

    assert demarrage._hotes_a_monter(catalogue) == ["cp.lab", "w1.lab"]
    assert demarrage._infra_prete(catalogue) is False
