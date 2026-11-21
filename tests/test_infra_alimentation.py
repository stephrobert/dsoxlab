"""``infra stop``, ``infra pause`` et ``infra start`` : arrêter sans détruire (issue #405).

Les assertions portent sur ce qui est **demandé à l'hyperviseur** et sur le code
de sortie, jamais sur le texte affiché. Un pilote simulé joue l'hyperviseur et
fait évoluer l'état des machines comme le ferait libvirt ou Incus.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab import i18n
from dsoxlab.cli import app
from dsoxlab.infra import alimentation, libvirt
from dsoxlab.infra.alimentation import Etat, Issue
from dsoxlab.models.repo import HostDefinition, InfraDefinition, RepoMetadata
from dsoxlab.utils.shell import CommandError, CommandResult

runner = CliRunner()

OK = CommandResult(returncode=0, stdout="", stderr="")


class PiloteSimule:
    """Un hyperviseur en mémoire. ``inertes`` ne réagissent pas à l'arrêt propre."""

    def __init__(
        self,
        etats: dict[str, Etat],
        *,
        inertes: frozenset[str] = frozenset(),
        refus: frozenset[str] = frozenset(),
    ) -> None:
        self.etats = dict(etats)
        self.inertes = inertes
        self.refus = refus
        self.appels: list[tuple[str, str]] = []

    def _faire(self, geste: str, nom: str, apres: Etat | None) -> CommandResult:
        self.appels.append((geste, nom))
        if geste in self.refus:
            return CommandResult(returncode=1, stdout="", stderr=f"{geste} refusé")
        if apres is not None:
            self.etats[nom] = apres
        return OK

    def lister(self) -> list[str]:
        return list(self.etats)

    def nom(self, fqdn: str, connus: list[str]) -> str | None:
        return fqdn if fqdn in connus else None

    def etat(self, nom: str) -> Etat:
        return self.etats[nom]

    def arreter(self, nom: str) -> CommandResult:
        return self._faire("arreter", nom, None if nom in self.inertes else Etat.ARRETEE)

    def couper(self, nom: str) -> CommandResult:
        return self._faire("couper", nom, Etat.ARRETEE)

    def geler(self, nom: str) -> CommandResult:
        return self._faire("geler", nom, Etat.GELEE)

    def demarrer(self, nom: str) -> CommandResult:
        return self._faire("demarrer", nom, Etat.MARCHE)

    def reprendre(self, nom: str) -> CommandResult:
        return self._faire("reprendre", nom, Etat.MARCHE)


class Horloge:
    """Le temps avance de ce que le code dort, sans jamais dormir pour de vrai."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def dormir(self, s: float) -> None:
        self.t += s


def _appliquer(action: alimentation.Action, p: PiloteSimule, **kw: Any) -> dict[str, Issue]:
    h = Horloge()
    cibles = {n: n for n in p.etats}
    res = alimentation.appliquer(
        action, "kvm", cibles, pilote=p, horloge=h, dormir=h.dormir, **kw
    )
    return {r.host: r.issue for r in res}


# ── la logique, provider par provider indifférent ────────────────────────────


def test_stop_arrete_ce_qui_tourne_et_ne_touche_pas_a_ce_qui_est_arrete() -> None:
    p = PiloteSimule({"a.lab": Etat.MARCHE, "b.lab": Etat.ARRETEE})
    assert _appliquer("stop", p) == {"a.lab": Issue.FAIT, "b.lab": Issue.DEJA}
    assert p.appels == [("arreter", "a.lab")]


def test_stop_sans_force_ne_coupe_jamais_une_machine_lente() -> None:
    p = PiloteSimule({"a.lab": Etat.MARCHE}, inertes=frozenset({"a.lab"}))
    assert _appliquer("stop", p, delai=10) == {"a.lab": Issue.ECHEC}
    assert ("couper", "a.lab") not in p.appels


def test_stop_force_coupe_seulement_apres_le_delai() -> None:
    p = PiloteSimule(
        {"lent.lab": Etat.MARCHE, "vif.lab": Etat.MARCHE}, inertes=frozenset({"lent.lab"})
    )
    assert _appliquer("stop", p, force=True, delai=10) == {
        "lent.lab": Issue.COUPEE,
        "vif.lab": Issue.FAIT,
    }
    assert ("couper", "vif.lab") not in p.appels


def test_stop_reprend_d_abord_une_machine_gelee() -> None:
    p = PiloteSimule({"a.lab": Etat.GELEE})
    assert _appliquer("stop", p) == {"a.lab": Issue.FAIT}
    assert p.appels == [("reprendre", "a.lab"), ("arreter", "a.lab")]


def test_stop_refuse_par_l_hyperviseur_est_un_echec() -> None:
    p = PiloteSimule({"a.lab": Etat.MARCHE}, refus=frozenset({"arreter"}))
    assert _appliquer("stop", p) == {"a.lab": Issue.ECHEC}


def test_pause_ignore_une_machine_arretee() -> None:
    p = PiloteSimule({"a.lab": Etat.MARCHE, "b.lab": Etat.ARRETEE, "c.lab": Etat.GELEE})
    assert _appliquer("pause", p) == {
        "a.lab": Issue.FAIT,
        "b.lab": Issue.IGNOREE,
        "c.lab": Issue.DEJA,
    }
    assert p.appels == [("geler", "a.lab")]


def test_start_relance_les_arretees_et_reprend_les_gelees() -> None:
    p = PiloteSimule({"a.lab": Etat.ARRETEE, "b.lab": Etat.GELEE, "c.lab": Etat.MARCHE})
    assert _appliquer("start", p) == {
        "a.lab": Issue.FAIT,
        "b.lab": Issue.FAIT,
        "c.lab": Issue.DEJA,
    }
    assert p.appels == [("demarrer", "a.lab"), ("reprendre", "b.lab")]


# ── le périmètre : ce catalogue, et lui seul ─────────────────────────────────


def _repo(tmp_path: Path, *noms: str, provider: str = "kvm") -> RepoMetadata:
    return RepoMetadata(
        id="demo",
        category="demo",
        path=tmp_path,
        infra=InfraDefinition(
            provider=provider,
            hosts=[HostDefinition(name=n) for n in noms],
        ),
    )


def test_machines_ne_rend_que_les_hotes_declares_qui_existent(tmp_path: Path) -> None:
    p = PiloteSimule({"web.lab": Etat.MARCHE, "voisin.lab": Etat.MARCHE})
    repo = _repo(tmp_path, "web.lab", "db.lab")
    assert alimentation.machines(repo, "kvm", pilote=p) == {"web.lab": "web.lab"}


def test_machines_restreint_aux_hotes_demandes(tmp_path: Path) -> None:
    p = PiloteSimule({"web.lab": Etat.MARCHE, "db.lab": Etat.MARCHE})
    repo = _repo(tmp_path, "web.lab", "db.lab")
    assert alimentation.machines(repo, "kvm", ["db.lab"], pilote=p) == {"db.lab": "db.lab"}


def test_outscale_n_a_rien_a_piloter(tmp_path: Path) -> None:
    with pytest.raises(alimentation.ProviderSansAlimentation):
        alimentation.machines(_repo(tmp_path, "web.lab"), "outscale")


def test_une_instance_incus_porte_le_fqdn_avec_des_tirets() -> None:
    pilote = alimentation._Incus(120)
    assert pilote.nom("web.lab", ["web-lab", "autre"]) == "web-lab"
    assert pilote.nom("db.lab", ["web-lab"]) is None


# ── kvm : ce qui part vraiment vers virsh ────────────────────────────────────


class VirshEtats:
    """``run_command`` de substitution : virsh qui répond et change d'état."""

    def __init__(self, etats: dict[str, str]) -> None:
        self.etats = etats
        self.sous_commandes: list[str] = []

    def __call__(self, cmd: list[str], **kwargs: Any) -> CommandResult:
        reste = cmd[cmd.index("virsh") + 1 :]
        if reste[:1] == ["--connect"]:
            reste = reste[2:]
        sous = reste[0]
        if sous == "list":
            return CommandResult(returncode=0, stdout="\n".join(self.etats), stderr="")
        if sous == "domstate":
            return CommandResult(returncode=0, stdout=self.etats[reste[1]] + "\n", stderr="")
        self.sous_commandes.append(sous)
        if sous == "destroy":
            self.etats[reste[1]] = "shut off"
        return OK


@pytest.fixture(autouse=True)
def sans_cache_de_prefixe() -> None:
    libvirt._oublier_prefixe()


def test_kvm_force_coupe_avec_destroy_et_ne_supprime_jamais(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``virsh destroy`` coupe l'alimentation ; ``undefine`` supprimerait la machine."""
    faux = VirshEtats({"web.lab": "running"})
    monkeypatch.setattr(libvirt, "run_command", faux)
    h = Horloge()
    res = alimentation.appliquer(
        "stop", "kvm", {"web.lab": "web.lab"}, force=True, delai=4,
        horloge=h, dormir=h.dormir,
    )
    assert [r.issue for r in res] == [Issue.COUPEE]
    assert faux.sous_commandes == ["shutdown", "destroy"]
    assert "undefine" not in faux.sous_commandes


def test_kvm_pause_et_start_envoient_suspend_puis_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faux = VirshEtats({"a.lab": "running", "b.lab": "paused", "c.lab": "shut off"})
    monkeypatch.setattr(libvirt, "run_command", faux)
    alimentation.appliquer("pause", "kvm", {"a.lab": "a.lab"})
    alimentation.appliquer("start", "kvm", {"b.lab": "b.lab", "c.lab": "c.lab"})
    assert faux.sous_commandes == ["suspend", "resume", "start"]


# ── la commande : codes de sortie ────────────────────────────────────────────

META = """\
repo:
  id: demo
  category: demo
infra:
  provider: {provider}
  network: lab-demo
  cidr: 10.10.99.0/24
  hosts:
    - name: web.lab
    - name: db.lab
"""


@pytest.fixture
def catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(i18n, "_strings", i18n._load("en"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("DSOXLAB_PROVIDER", raising=False)
    depot = tmp_path / "depot"
    depot.mkdir()
    (depot / "meta.yml").write_text(META.format(provider="kvm"), encoding="utf-8")
    return depot


def _brancher(monkeypatch: pytest.MonkeyPatch, p: PiloteSimule) -> None:
    monkeypatch.setattr(alimentation, "_pilote", lambda provider, delai: p)


def test_cli_stop_rend_zero_quand_tout_est_arrete(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = PiloteSimule({"web.lab": Etat.MARCHE, "db.lab": Etat.ARRETEE, "x.lab": Etat.MARCHE})
    _brancher(monkeypatch, p)
    r = runner.invoke(app, ["infra", "stop", "--all", "--lab-home", str(catalogue)])
    assert r.exit_code == 0, r.output
    assert p.appels == [("arreter", "web.lab")]


def test_cli_stop_sort_en_echec_sur_une_machine_qui_resiste(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = PiloteSimule({"web.lab": Etat.MARCHE}, inertes=frozenset({"web.lab"}))
    _brancher(monkeypatch, p)
    r = runner.invoke(
        app, ["infra", "stop", "--all", "--timeout", "1", "--lab-home", str(catalogue)]
    )
    assert r.exit_code == 1
    assert ("couper", "web.lab") not in p.appels


def test_cli_hote_non_declare_refuse_sans_rien_toucher(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = PiloteSimule({"web.lab": Etat.MARCHE})
    _brancher(monkeypatch, p)
    r = runner.invoke(
        app, ["infra", "pause", "--host", "intrus.lab", "--lab-home", str(catalogue)]
    )
    assert r.exit_code == 1
    assert p.appels == []


def test_cli_outscale_sort_en_impossible(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (catalogue / "meta.yml").write_text(META.format(provider="outscale"), encoding="utf-8")
    r = runner.invoke(app, ["infra", "start", "--all", "--lab-home", str(catalogue)])
    assert r.exit_code == 2


def test_cli_hyperviseur_muet_n_est_pas_une_absence(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Muet(PiloteSimule):
        def lister(self) -> list[str]:
            raise CommandError(["virsh"], CommandResult(returncode=1, stdout="", stderr="down"))

    _brancher(monkeypatch, Muet({}))
    r = runner.invoke(app, ["infra", "stop", "--all", "--lab-home", str(catalogue)])
    assert r.exit_code == 1


def test_cli_commande_nue_refuse_sans_rien_toucher(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Éteindre tout le parc se demande : --host ou --all, jamais par défaut."""
    p = PiloteSimule({"web.lab": Etat.MARCHE, "db.lab": Etat.MARCHE})
    _brancher(monkeypatch, p)
    r = runner.invoke(app, ["infra", "stop", "--lab-home", str(catalogue)])
    assert r.exit_code == 1
    assert p.appels == []


def test_cli_host_et_all_ensemble_refuses(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = PiloteSimule({"web.lab": Etat.MARCHE})
    _brancher(monkeypatch, p)
    r = runner.invoke(
        app, ["infra", "stop", "--all", "--host", "web.lab", "--lab-home", str(catalogue)]
    )
    assert r.exit_code == 1
    assert p.appels == []


def test_cli_un_nom_court_et_plusieurs_machines(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = PiloteSimule({"web.lab": Etat.MARCHE, "db.lab": Etat.MARCHE})
    _brancher(monkeypatch, p)
    r = runner.invoke(
        app,
        ["infra", "pause", "--host", "web", "--host", "db.lab", "--lab-home", str(catalogue)],
    )
    assert r.exit_code == 0, r.output
    assert sorted(p.appels) == [("geler", "db.lab"), ("geler", "web.lab")]


def test_un_nom_court_partage_n_est_pas_devine() -> None:
    trouves, inconnus = alimentation.resoudre_hotes(
        ["web", "db", "db.lab"], ["web.lab", "db.lab", "db.prod"]
    )
    assert trouves == ["web.lab", "db.lab"]
    assert inconnus == ["db"]
