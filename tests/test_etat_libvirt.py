"""L'outil demande son état à l'hyperviseur, au lieu de s'en passer.

Deux défauts, un seul angle mort : ``dsoxlab`` ne se fiait qu'à Terraform et à
SSH, et aucun des deux ne sait ce qu'une machine fait.

* Un ``provision`` interrompu après la définition d'un domaine le laisse sur
  l'hyperviseur sans jamais l'inscrire au state. ``terraform destroy`` n'a donc
  rien à supprimer : la commande annonçait « infrastructure détruite » et sortait
  en 0 en laissant les machines debout, et tout ``provision`` suivant mourait sur
  « domain already exists ».
* ``status`` capturait la vraie raison de chaque échec SSH puis la jetait, pour
  afficher une phrase qui proposait deux causes à la fois. Or « No route to
  host » et « Connection refused » disent des choses **opposées** sur l'état
  d'une machine.

Aucun test ici n'exige un libvirt réel : ``virsh`` est simulé au niveau du
wrapper ``run_command``, ce qui laisse chaque test dicter ce que l'hyperviseur
répond — y compris qu'il ne répond pas.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab import i18n
from dsoxlab.cli import app
from dsoxlab.infra import inventory, libvirt, terraform
from dsoxlab.models.repo import HostDefinition, InfraDefinition, RepoMetadata
from dsoxlab.services import host_diagnosis as diag
from dsoxlab.utils.shell import CommandError, CommandResult

runner = CliRunner()

#: Ce que porte l'hyperviseur d'un poste de développement ordinaire : les
#: machines du lab, et d'autres qui ne le concernent pas.
DOMAINES = "web1.lab\ndb1.lab\nmachine-perso\n"


class VirshSimule:
    """Un ``run_command`` de substitution, qui joue le rôle de ``virsh``.

    Chaque sous-commande a sa réponse, réglable par le test. Les commandes
    reçues sont enregistrées : c'est sur elles que portent les assertions de
    « qui a été visé », plutôt que sur un effet de bord invérifiable.
    """

    def __init__(
        self,
        domaines: str = DOMAINES,
        *,
        etats: dict[str, str] | None = None,
        baux: dict[str, str] | None = None,
        echecs: frozenset[str] = frozenset(),
    ) -> None:
        self.domaines = domaines
        self.etats = etats or {}
        self.baux = baux or {}
        self.echecs = echecs
        self.commandes: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs: Any) -> CommandResult:
        self.commandes.append(cmd)
        sous = cmd[3] if len(cmd) > 3 else ""
        if sous in self.echecs:
            return self._echec(cmd, kwargs, "virsh: erreur simulée")
        if sous == "list":
            return CommandResult(returncode=0, stdout=self.domaines, stderr="")
        if sous == "domstate":
            etat = self.etats.get(cmd[4])
            if etat is None:
                return self._echec(cmd, kwargs, "error: failed to get domain")
            return CommandResult(returncode=0, stdout=f"{etat}\n\n", stderr="")
        if sous == "domifaddr":
            bail = self.baux.get(cmd[4], "")
            entete = " Name  MAC address  Protocol  Address\n---\n"
            corps = f" vnet0  52:54:00:aa:bb:cc  ipv4  {bail}/24\n" if bail else ""
            return CommandResult(returncode=0, stdout=entete + corps, stderr="")
        return CommandResult(returncode=0, stdout="", stderr="")

    @staticmethod
    def _echec(cmd: list[str], kwargs: dict[str, Any], stderr: str) -> CommandResult:
        resultat = CommandResult(returncode=1, stdout="", stderr=stderr)
        if kwargs.get("check", True):
            raise CommandError(cmd, resultat)
        return resultat

    def sous_commandes(self) -> list[str]:
        return [c[3] for c in self.commandes if len(c) > 3]


def virsh_injoignable(cmd: list[str], **kwargs: Any) -> CommandResult:
    """``virsh`` absent, ``sudo`` refusé ou démon éteint : tous lèvent ici."""
    raise CommandError(
        cmd,
        CommandResult(returncode=1, stdout="", stderr="sudo: a password is required"),
    )


@pytest.fixture(autouse=True)
def langue_en(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les assertions portent sur le texte anglais, pas sur la LANG du poste."""
    monkeypatch.setattr(i18n, "_strings", i18n._load("en"))


@pytest.fixture
def virsh(monkeypatch: pytest.MonkeyPatch) -> VirshSimule:
    faux = VirshSimule()
    monkeypatch.setattr(libvirt, "run_command", faux)
    return faux


def _meta(hosts: list[str], *, provider: str = "kvm") -> RepoMetadata:
    return RepoMetadata(
        id="demo",
        category="demo",
        infra=InfraDefinition(
            provider=provider,
            network="lab-demo",
            hosts=[HostDefinition(name=h) for h in hosts],
        ),
    )


# ── infra/libvirt : interroger sans jamais bloquer ni inventer ───────────────

def test_virsh_est_appele_en_sudo_non_interactif(virsh: VirshSimule) -> None:
    """Un prompt de mot de passe n'aurait aucun terminal où s'afficher.

    La sortie de ces commandes est capturée : sans ``-n``, ``sudo`` attendrait
    une saisie que personne ne peut faire, et ``status`` resterait pendu
    jusqu'au timeout au lieu de diagnostiquer quoi que ce soit.
    """
    libvirt.list_domains()
    assert virsh.commandes[0][:3] == ["sudo", "-n", "virsh"]


def test_seuls_les_hotes_declares_sont_reconnus(virsh: VirshSimule) -> None:
    """Le garde-fou qui empêche de nommer, puis de retirer, la machine d'autrui."""
    trouves = libvirt.existing_domains(["web1.lab", "absent.lab"])
    assert trouves == {"web1.lab": "web1.lab"}
    assert "machine-perso" not in trouves.values()


def test_l_etat_est_rendu_tel_que_libvirt_le_dit(monkeypatch: pytest.MonkeyPatch) -> None:
    """C'est ce mot que l'apprenant retrouvera dans son ``virsh list --all``."""
    monkeypatch.setattr(
        libvirt, "run_command", VirshSimule(etats={"web1.lab": "shut off"})
    )
    assert libvirt.domain_state("web1.lab") == "shut off"


def test_un_domaine_eteint_n_est_pas_interroge_sur_ses_baux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sinon l'absence de bail d'une machine éteinte passerait pour une panne réseau."""
    faux = VirshSimule(etats={"web1.lab": "shut off"})
    monkeypatch.setattr(libvirt, "run_command", faux)

    etat = libvirt.inspect_host("web1.lab")

    assert etat.exists and not etat.running
    assert "domifaddr" not in faux.sous_commandes()


def test_un_domaine_en_marche_rend_son_bail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        libvirt,
        "run_command",
        VirshSimule(etats={"web1.lab": "running"}, baux={"web1.lab": "10.10.30.11"}),
    )
    etat = libvirt.inspect_host("web1.lab")
    assert etat.running and etat.addresses == ["10.10.30.11"]


def test_un_domaine_absent_est_un_fait_pas_une_ignorance(virsh: VirshSimule) -> None:
    etat = libvirt.inspect_host("absent.lab")
    assert not etat.exists and etat.state is None


def test_un_hyperviseur_muet_leve_au_lieu_de_rendre_une_liste_vide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """« Je n'ai pas pu savoir » ne doit jamais devenir « rien n'existe »."""
    monkeypatch.setattr(libvirt, "run_command", virsh_injoignable)
    with pytest.raises(CommandError):
        libvirt.existing_domains(["web1.lab"])


def test_un_domaine_en_marche_est_arrete_avant_d_etre_defini_hors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``undefine`` seul le laisserait tourner en transitoire, nom compris."""
    faux = VirshSimule(etats={"web1.lab": "running"})
    monkeypatch.setattr(libvirt, "run_command", faux)

    libvirt.remove_domain("web1.lab")

    assert faux.sous_commandes() == ["domstate", "destroy", "undefine"]


def test_le_retrait_ne_supprime_aucun_volume_de_disque(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les disques appartiennent à Terraform : les effacer ici serait hors mandat."""
    faux = VirshSimule(etats={"web1.lab": "shut off"})
    monkeypatch.setattr(libvirt, "run_command", faux)

    libvirt.remove_domain("web1.lab")

    for cmd in faux.commandes:
        assert "--remove-all-storage" not in cmd


def test_le_retrait_retente_sans_nvram_si_l_option_est_refusee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un libvirt ancien rejette l'option : abandonner sur ce détail serait absurde."""
    faux = VirshSimule(etats={"web1.lab": "shut off"})
    appels: list[list[str]] = []

    def refuse_nvram(cmd: list[str], **kwargs: Any) -> CommandResult:
        appels.append(cmd)
        if "undefine" in cmd and "--nvram" in cmd:
            raise CommandError(
                cmd,
                CommandResult(returncode=1, stdout="", stderr="unsupported flag"),
            )
        return faux(cmd, **kwargs)

    monkeypatch.setattr(libvirt, "run_command", refuse_nvram)
    libvirt.remove_domain("web1.lab")

    nus = [c for c in appels if "undefine" in c and "--nvram" not in c]
    assert nus, "le repli sans --nvram n'a pas été tenté"


def test_seul_kvm_est_declare_interrogeable() -> None:
    """incus crée des ``incus_instance``, que ``virsh`` ne voit pas ; outscale
    est un cloud distant. Prétendre les interroger produirait « rien n'existe »."""
    assert libvirt.supports_domain_state("kvm")
    assert not libvirt.supports_domain_state("incus")
    assert not libvirt.supports_domain_state("outscale")


# ── services/host_diagnosis : une cause, pas deux hypothèses ─────────────────

def test_pas_de_route_et_connexion_refusee_ne_disent_pas_la_meme_chose() -> None:
    """Le critère central de l'issue : l'ancien message les traitait pareil."""
    injoignable = diag.diagnose(
        reachable=False,
        reason="ssh: connect to host 10.10.30.11 port 22: No route to host",
        status=None,
    )
    refuse = diag.diagnose(
        reachable=False,
        reason="ssh: connect to host 10.10.30.11 port 22: Connection refused",
        status=None,
    )
    assert injoignable == diag.CAUSE_UNREACHABLE
    assert refuse == diag.CAUSE_SSH_REFUSED
    assert injoignable != refuse


def test_l_etat_du_domaine_l_emporte_sur_ce_que_dit_ssh() -> None:
    """Cas réel : « No route to host » sur un domaine simplement éteint.

    SSH ne pouvait rien dire de plus ; l'hyperviseur, lui, connaît la réponse.
    """
    cause = diag.diagnose(
        reachable=False,
        reason="ssh: connect to host 10.10.30.11 port 22: No route to host",
        status=libvirt.DomainStatus(host="web1.lab", domain="web1.lab", state="shut off"),
    )
    assert cause == diag.CAUSE_DOMAIN_NOT_RUNNING


def test_un_domaine_absent_renvoie_vers_provision() -> None:
    cause = diag.diagnose(
        reachable=False, reason="No route to host",
        status=libvirt.DomainStatus(host="web1.lab"),
    )
    assert cause == diag.CAUSE_DOMAIN_ABSENT


def test_un_domaine_en_marche_sans_bail_est_un_probleme_reseau() -> None:
    cause = diag.diagnose(
        reachable=False, reason="No route to host",
        status=libvirt.DomainStatus(
            host="web1.lab", domain="web1.lab", state="running", addresses=[]
        ),
    )
    assert cause == diag.CAUSE_DOMAIN_NO_LEASE


def test_un_domaine_en_marche_avec_bail_attend_cloud_init() -> None:
    cause = diag.diagnose(
        reachable=False, reason="Connection refused",
        status=libvirt.DomainStatus(
            host="web1.lab", domain="web1.lab", state="running",
            addresses=["10.10.30.11"],
        ),
    )
    assert cause == diag.CAUSE_BOOTING


def test_une_cle_refusee_n_est_pas_un_cloud_init_en_cours() -> None:
    """sshd écoute déjà : attendre ne réglera rien, la clé ne correspond pas."""
    cause = diag.diagnose(
        reachable=False, reason="Permission denied (publickey).",
        status=libvirt.DomainStatus(
            host="web1.lab", domain="web1.lab", state="running",
            addresses=["10.10.30.11"],
        ),
    )
    assert cause == diag.CAUSE_SSH_DENIED


def test_un_etat_illisible_ne_conclut_pas_a_l_absence() -> None:
    """Le domaine a été résolu : il existe. Ne pas connaître son état n'autorise
    pas à dire qu'il n'y en a pas."""
    cause = diag.diagnose(
        reachable=False, reason="No route to host",
        status=libvirt.DomainStatus(host="web1.lab", domain="web1.lab", state=None),
    )
    assert cause == diag.CAUSE_UNREACHABLE


def test_une_raison_inconnue_reste_inconnue() -> None:
    """Une cause plausible inventée coûte plus cher qu'un « je ne sais pas »."""
    assert diag.classify_ssh("kex_exchange_identification: banner") == diag.CAUSE_UNKNOWN


def test_un_hote_joignable_n_a_pas_de_cause() -> None:
    assert diag.diagnose(reachable=True, reason="", status=None) == diag.CAUSE_NONE


# ── infra/terraform : ce que le state connaît, et ce qui lui échappe ─────────

def _ecrire_state(chemin: Path, domaines: list[str]) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps({
            "resources": [
                {"type": "libvirt_volume", "instances": [{"attributes": {"name": "img"}}]},
                {
                    "type": "libvirt_domain",
                    "instances": [{"attributes": {"name": d}} for d in domaines],
                },
            ]
        }),
        encoding="utf-8",
    )


def test_un_state_absent_ne_connait_rien(tmp_path: Path) -> None:
    assert terraform._domains_in_state(tmp_path / "terraform.tfstate") == set()


def test_un_state_illisible_rend_une_ignorance_pas_un_vide(tmp_path: Path) -> None:
    """Sinon un fichier tronqué ferait passer une infra saine pour un champ de ruines."""
    corrompu = tmp_path / "terraform.tfstate"
    corrompu.write_text("{ pas du json", encoding="utf-8")
    assert terraform._domains_in_state(corrompu) is None


def test_le_state_rend_les_noms_des_domaines_connus(tmp_path: Path) -> None:
    state = tmp_path / "terraform.tfstate"
    _ecrire_state(state, ["web1.lab", "db1.lab"])
    assert terraform._domains_in_state(state) == {"web1.lab", "db1.lab"}


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Le work-dir XDG du dépôt de démonstration, isolé du poste."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path / "state" / "dsoxlab" / "demo" / "terraform" / "kvm"


def test_un_domaine_defini_hors_du_state_est_signale(
    virsh: VirshSimule, state_dir: Path
) -> None:
    """Le cas vécu : ``libvirt_domain`` échoue au démarrage, le domaine reste."""
    _ecrire_state(state_dir / "terraform.tfstate", [])

    scan = terraform.find_orphan_domains(_meta(["web1.lab", "db1.lab"]))

    assert scan.inspected
    assert scan.orphans == {"web1.lab": "web1.lab", "db1.lab": "db1.lab"}


def test_un_provision_reussi_ne_signale_aucun_reste(
    virsh: VirshSimule, state_dir: Path
) -> None:
    """Le comportement d'avant doit survivre : pas un avertissement de plus."""
    _ecrire_state(state_dir / "terraform.tfstate", ["web1.lab", "db1.lab"])

    scan = terraform.find_orphan_domains(_meta(["web1.lab", "db1.lab"]))

    assert scan.inspected and scan.orphans == {}


def test_une_machine_absente_du_meta_n_est_jamais_signalee(
    virsh: VirshSimule, state_dir: Path
) -> None:
    """``machine-perso`` tourne sur le même hyperviseur et ne regarde pas ce dépôt."""
    _ecrire_state(state_dir / "terraform.tfstate", [])

    scan = terraform.find_orphan_domains(_meta(["web1.lab"]))

    assert scan.orphans == {"web1.lab": "web1.lab"}
    assert "machine-perso" not in scan.orphans.values()


def test_un_provider_sans_etat_interrogeable_reste_inerte(
    virsh: VirshSimule, state_dir: Path
) -> None:
    """incus n'a pas de domaine libvirt : ni détection, ni avertissement inutile."""
    scan = terraform.find_orphan_domains(_meta(["web1.lab"], provider="incus"))

    assert not scan.inspected and scan.orphans == {} and scan.reason == ""
    assert virsh.commandes == [], "aucune interrogation ne devait partir"


def test_un_hyperviseur_muet_se_dit_au_lieu_de_conclure_a_rien(
    monkeypatch: pytest.MonkeyPatch, state_dir: Path
) -> None:
    """Rendre « aucun orphelin » sans avoir pu regarder serait un faux diagnostic."""
    monkeypatch.setattr(libvirt, "run_command", virsh_injoignable)
    _ecrire_state(state_dir / "terraform.tfstate", [])

    scan = terraform.find_orphan_domains(_meta(["web1.lab"]))

    assert not scan.inspected and scan.orphans == {}
    assert "password" in scan.reason


# ── La CLI : ce que l'apprenant lit et le code qu'il récupère ────────────────

@pytest.fixture
def depot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Un dépôt de labs minimal, avec son infrastructure déclarée.

    ``HOME`` et ``XDG_STATE_HOME`` sont déviés vers le tmp : ces commandes
    écrivent un fragment SSH et lisent un state, et aucun test n'a le droit de
    toucher au poste qui le joue.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("DSOXLAB_NO_UPDATE_CHECK", "1")
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    monkeypatch.delenv("DSOXLAB_PROVIDER", raising=False)
    (tmp_path / "home" / ".ssh" / "config.d").mkdir(parents=True)

    repo = tmp_path / "repo"
    (repo / "ssh").mkdir(parents=True)
    (repo / "ssh" / "id_ed25519").write_text("clé factice", encoding="utf-8")
    (repo / "meta.yml").write_text(
        "repo:\n"
        "  id: demo\n"
        "  category: demo\n"
        "infra:\n"
        "  provider: kvm\n"
        "  network: lab-demo\n"
        "  cidr: 10.10.30.0/24\n"
        "  hosts:\n"
        "    - name: web1.lab\n"
        "    - name: db1.lab\n",
        encoding="utf-8",
    )
    state = tmp_path / "state" / "dsoxlab" / "demo" / "terraform" / "kvm"
    _ecrire_state(state / "terraform.tfstate", [])
    return repo


@pytest.fixture
def terraform_muet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Terraform réduit au silence : ces tests portent sur ce qui l'entoure."""
    monkeypatch.setattr(terraform, "is_available", lambda: True)
    monkeypatch.setattr(terraform, "init", lambda *a, **k: None)
    monkeypatch.setattr(terraform, "destroy", lambda *a, **k: None)


def _texte(resultat: Any) -> str:
    return resultat.stdout.replace("\n", " ")


def _ssh_echoue(raison: str) -> Any:
    """Le ``CompletedProcess`` que rendrait un ``ssh`` en échec."""
    return subprocess.CompletedProcess(
        args=["ssh"], returncode=255, stdout=b"",
        stderr=f"ssh: connect to host 10.10.30.11 port 22: {raison}\n".encode(),
    )


@pytest.fixture
def ssh_muet(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Fait échouer toute tentative SSH avec la raison que le test dicte.

    Le remplacement vise **la seule** commande ``ssh`` : remplacer
    ``subprocess.run`` en bloc détournerait aussi les appels de
    ``utils.shell``, et le test mesurerait alors son propre harnais.
    """
    vrai = subprocess.run

    def installer(raison: str) -> None:
        def aiguillage(cmd: Any, *args: Any, **kwargs: Any) -> Any:
            if isinstance(cmd, list) and cmd and cmd[0] == "ssh":
                return _ssh_echoue(raison)
            return vrai(cmd, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", aiguillage)

    return installer


@pytest.fixture
def outputs_terraform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les adresses que Terraform aurait publiées, sans lancer Terraform."""
    monkeypatch.setattr(
        inventory,
        "read_terraform_outputs",
        lambda repo_meta: {
            "hosts": {"value": {"web1.lab": "10.10.30.11", "db1.lab": "10.10.30.12"}}
        },
    )


def test_provision_nomme_les_machines_restees_et_la_commande_qui_les_retire(
    depot: Path, virsh: VirshSimule
) -> None:
    """Au lieu de laisser remonter « domain already exists », sans quoi faire."""
    resultat = runner.invoke(app, ["provision", "--lab-home", str(depot)])

    sortie = _texte(resultat)
    assert resultat.exit_code == 5
    assert "web1.lab" in sortie and "db1.lab" in sortie
    assert "virsh undefine" in sortie


def test_destroy_retire_les_machines_que_terraform_ignore(
    depot: Path, virsh: VirshSimule, terraform_muet: None
) -> None:
    """Le défaut d'origine : ``✔ Infrastructure destroyed`` et un code 0."""
    resultat = runner.invoke(app, ["destroy", "--yes", "--lab-home", str(depot)])

    assert resultat.exit_code == 0, _texte(resultat)
    dedefinis = [c[4] for c in virsh.commandes if c[3] == "undefine"]
    assert sorted(dedefinis) == ["db1.lab", "web1.lab"]


def test_destroy_refuse_de_sortir_en_succes_si_les_machines_restent(
    depot: Path, monkeypatch: pytest.MonkeyPatch, terraform_muet: None
) -> None:
    """Sans confirmation, on ne retire rien — mais on ne ment pas non plus."""
    monkeypatch.setattr(libvirt, "run_command", VirshSimule())
    monkeypatch.setattr("typer.confirm", lambda *a, **k: False)

    resultat = runner.invoke(app, ["destroy", "--lab-home", str(depot)])

    sortie = _texte(resultat)
    assert resultat.exit_code == 6
    assert "virsh undefine" in sortie
    assert "Infrastructure destroyed" not in sortie


def test_destroy_sans_machine_restee_est_inchange(
    depot: Path, monkeypatch: pytest.MonkeyPatch, terraform_muet: None
) -> None:
    """Un provision réussi suivi d'un destroy ne doit rien voir de nouveau."""
    monkeypatch.setattr(libvirt, "run_command", VirshSimule("machine-perso\n"))

    resultat = runner.invoke(app, ["destroy", "--yes", "--lab-home", str(depot)])

    sortie = _texte(resultat)
    assert resultat.exit_code == 0
    assert "Infrastructure destroyed" in sortie
    assert "still defined" not in sortie


def test_status_json_porte_l_etat_de_chaque_domaine(
    depot: Path,
    monkeypatch: pytest.MonkeyPatch,
    ssh_muet: Callable[[str], None],
    outputs_terraform: None,
) -> None:
    """Critère de l'issue : le diagnostic doit être exploitable par un script."""
    monkeypatch.setattr(
        libvirt, "run_command",
        VirshSimule(etats={"web1.lab": "shut off", "db1.lab": "running"},
                    baux={"db1.lab": "10.10.30.12"}),
    )
    ssh_muet("No route to host")

    resultat = runner.invoke(app, ["status", "--json", "--lab-home", str(depot)])

    doc = json.loads(resultat.stdout)
    par_hote = {h["fqdn"]: h for h in doc["hosts"]}
    assert doc["hypervisor"] == {"queryable": True, "error": None}
    assert par_hote["web1.lab"]["domain_state"] == "shut off"
    assert par_hote["web1.lab"]["cause"] == diag.CAUSE_DOMAIN_NOT_RUNNING
    assert par_hote["db1.lab"]["domain_state"] == "running"
    assert par_hote["db1.lab"]["cause"] == diag.CAUSE_BOOTING


def test_status_nomme_la_cause_et_le_geste(
    depot: Path,
    monkeypatch: pytest.MonkeyPatch,
    ssh_muet: Callable[[str], None],
    outputs_terraform: None,
) -> None:
    """La formulation à deux hypothèses disparaît, une cause par hôte la remplace.

    Les deux hôtes échouent avec **la même** raison SSH — « No route to host » —
    et reçoivent pourtant deux diagnostics différents : l'un est éteint, l'autre
    n'a jamais été créé. C'est exactement ce que l'ancien message ne pouvait pas
    dire.
    """
    monkeypatch.setattr(
        libvirt, "run_command",
        VirshSimule("web1.lab\n", etats={"web1.lab": "shut off"}),
    )
    ssh_muet("No route to host")

    resultat = runner.invoke(app, ["status", "--lab-home", str(depot)])

    sortie = _texte(resultat)
    assert resultat.exit_code == 1
    assert "virsh start web1.lab" in sortie
    assert "no domain named 'db1.lab'" in sortie
    assert "dsoxlab provision" in sortie
    assert "Cloud-init may still be running" not in sortie


def test_status_dit_qu_il_n_a_pas_pu_regarder(
    depot: Path,
    monkeypatch: pytest.MonkeyPatch,
    ssh_muet: Callable[[str], None],
    outputs_terraform: None,
) -> None:
    """``sudo`` refusé : on retombe sur SSH, on le dit, et on ne part pas en erreur."""
    monkeypatch.setattr(libvirt, "run_command", virsh_injoignable)
    ssh_muet("Connection refused")

    resultat = runner.invoke(app, ["status", "--lab-home", str(depot)])

    sortie = _texte(resultat)
    assert resultat.exit_code == 1, "un diagnostic impossible n'est pas un plantage"
    assert "hypervisor did not answer" in sortie
    # La couche SSH tient toute seule : refus de connexion ≠ pas de route.
    assert "refuses the connection" in sortie


def test_status_le_dit_aussi_quand_le_provider_n_a_pas_d_etat(
    depot: Path,
    monkeypatch: pytest.MonkeyPatch,
    ssh_muet: Callable[[str], None],
    outputs_terraform: None,
    virsh: VirshSimule,
) -> None:
    """Sur incus, rien ne change et personne n'est interrogé pour rien."""
    monkeypatch.setenv("DSOXLAB_PROVIDER", "incus")
    ssh_muet("No route to host")

    resultat = runner.invoke(app, ["status", "--lab-home", str(depot)])

    sortie = _texte(resultat)
    assert resultat.exit_code == 1
    assert "no machine state that can be queried" in sortie
    assert "nothing answers at 10.10.30.11" in sortie
    assert virsh.commandes == [], "aucune interrogation ne devait partir"
