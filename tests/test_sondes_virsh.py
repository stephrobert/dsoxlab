"""Issues #172 et #173 : toute sonde ``virsh`` emprunte le chemin détecté.

Deux défauts, une même cause : des appels ``virsh`` qui recomposaient leur
propre ligne de commande au lieu de passer par ``run_virsh``.

* ``doctor`` sondait le pool par un ``virsh -c qemu:///system`` direct, sans la
  détection du préfixe ``sudo -n``. Sur une machine où l'URI système exige des
  droits, la sonde échouait **toujours** — et l'échec rendait ``ok=True`` :
  le contrôle était vert en permanence, précisément là où ``provision``
  allait mourir sur « Pool Not Found ». Et ``virsh version`` nu, sans
  ``--connect``, pouvait viser l'URI session : deux lignes vertes au-dessus
  d'un provisionnement mort.
* Trois ``subprocess.run(["sudo", "virsh", …], capture_output=True)`` sans
  ``-n`` : un prompt sudo sans terminal où s'afficher pend, et sur une machine
  configurée par groupe ``libvirt`` sans droits sudo, le bail DHCP n'était
  jamais posé — l'échec partait dans un ``logger.warning`` que personne ne lit.

Comme dans ``test_etat_libvirt.py``, ``virsh`` est simulé au niveau du wrapper
``run_command`` du module ``libvirt`` : c'est le seul niveau qui prouve que
l'appel passe bien par la détection de préfixe et par l'URI système.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab import i18n
from dsoxlab.cli import app
from dsoxlab.i18n import _
from dsoxlab.infra import inventory, libvirt, terraform
from dsoxlab.models.repo import HostDefinition, InfraDefinition, RepoMetadata
from dsoxlab.services import doctor
from dsoxlab.utils.shell import CommandError, CommandResult

runner = CliRunner()


@pytest.fixture(autouse=True)
def langue_en(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les assertions portent sur le texte anglais, pas sur la LANG du poste."""
    monkeypatch.setattr(i18n, "_strings", i18n._load("en"))


@pytest.fixture(autouse=True)
def sans_cache_de_prefixe() -> None:
    """Le chemin retenu est mémorisé par processus : un test ne doit pas
    hériter de la détection d'un autre."""
    libvirt._oublier_prefixe()


class VirshScripte:
    """Un ``run_command`` de substitution, réglé sous-commande par sous-commande.

    Chaque commande reçue est enregistrée **entière**, préfixe compris : c'est
    sur elle que portent les assertions « par quel chemin » et « vers quelle
    URI », qui sont tout le sujet de ces deux issues.

    ``reponses`` associe une sous-commande virsh à son :class:`CommandResult`.
    Une sous-commande absente répond ``rc=0`` sans sortie. ``sudo_requis``
    simule la machine où l'URI système n'est joignable que par ``sudo -n``.
    """

    def __init__(
        self,
        reponses: dict[str, CommandResult] | None = None,
        *,
        sudo_requis: bool = False,
    ) -> None:
        self.reponses = reponses or {}
        self.sudo_requis = sudo_requis
        self.commandes: list[list[str]] = []

    @staticmethod
    def _sous_commande(cmd: list[str]) -> str:
        if "virsh" not in cmd:
            return ""
        reste = cmd[cmd.index("virsh") + 1 :]
        if reste[:1] == ["--connect"]:
            reste = reste[2:]
        return reste[0] if reste else ""

    def __call__(self, cmd: list[str], **kwargs: Any) -> CommandResult:
        self.commandes.append(cmd)
        if self.sudo_requis and cmd[:2] != ["sudo", "-n"]:
            return self._rendre(
                cmd, kwargs,
                CommandResult(returncode=1, stdout="", stderr="permission denied"),
            )
        reponse = self.reponses.get(
            self._sous_commande(cmd), CommandResult(returncode=0, stdout="", stderr="")
        )
        return self._rendre(cmd, kwargs, reponse)

    @staticmethod
    def _rendre(
        cmd: list[str], kwargs: dict[str, Any], reponse: CommandResult
    ) -> CommandResult:
        if not reponse.ok and kwargs.get("check", True):
            raise CommandError(cmd, reponse)
        return reponse

    def celles_de(self, sous_commande: str) -> list[list[str]]:
        return [c for c in self.commandes if self._sous_commande(c) == sous_commande]


def _meta(*hosts: str, provider: str = "kvm") -> RepoMetadata:
    return RepoMetadata(
        id="demo",
        category="demo",
        infra=InfraDefinition(
            provider=provider,
            network="lab-demo",
            cidr="10.10.30.0/24",
            hosts=[HostDefinition(name=h) for h in hosts],
        ),
    )


# ── #172 : la sonde du pool passe par run_virsh ──────────────────────────────

def test_le_pool_present_est_vu_meme_derriere_sudo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le cœur du défaut : la sonde directe échouait toujours sur une machine
    où l'URI système exige des droits, et l'échec valait « vert ». Par
    ``run_virsh``, la sonde emprunte ``sudo -n`` et **mesure** enfin."""
    virsh = VirshScripte(
        {
            "list": CommandResult(returncode=0, stdout="", stderr=""),
            "pool-list": CommandResult(returncode=0, stdout="default\n", stderr=""),
        },
        sudo_requis=True,
    )
    monkeypatch.setattr(libvirt, "run_command", virsh)

    check = doctor._check_libvirt_pool("default")

    assert check.ok
    assert check.detail == "default"
    sondes = virsh.celles_de("pool-list")
    assert sondes, "aucune sonde pool-list jouée"
    for cmd in sondes:
        assert cmd[:2] == ["sudo", "-n"], "la sonde doit emprunter le chemin détecté"
        assert "--connect" in cmd and "qemu:///system" in cmd


def test_le_pool_absent_reste_un_constat_rouge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mesurer et ne rien trouver n'est pas « ne pas pouvoir mesurer » : le
    pool manquant garde son rouge et sa remédiation de création."""
    virsh = VirshScripte(
        {"pool-list": CommandResult(returncode=0, stdout="", stderr="")}
    )
    monkeypatch.setattr(libvirt, "run_command", virsh)

    check = doctor._check_libvirt_pool("default")

    assert not check.ok
    assert check.state == doctor.STATE_FAILED
    assert check.fix is not None
    assert "pool-define-as" in check.fix.display


def test_la_sonde_impossible_rend_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ne pas savoir n'est ni vert ni rouge. L'ancien contrôle rendait
    ``ok=True`` ici : le vert affiché faute d'avoir mesuré, l'occurrence la
    plus littérale du motif que ce dépôt combat (issue #172)."""

    def _echec(cmd: list[str], **kwargs: Any) -> CommandResult:
        raise CommandError(
            cmd, CommandResult(returncode=1, stdout="", stderr="daemon muet")
        )

    monkeypatch.setattr(libvirt, "run_command", _echec)

    check = doctor._check_libvirt_pool("default")

    assert not check.ok
    assert check.state == doctor.STATE_UNKNOWN
    assert check.detail == _("detail_pool_unknown")
    assert check.fix is None
    assert doctor.DoctorReport(required=[check]).failing() == []


def test_check_kvm_interroge_l_uri_systeme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``virsh version`` nu peut viser l'URI session selon la distribution, et
    répondre parfaitement à un utilisateur que l'URI système refuse : deux
    lignes vertes au-dessus d'un ``provision`` mort. Le contrôle doit viser
    l'URI que ``provision`` utilise."""
    virsh = VirshScripte(
        {"version": CommandResult(returncode=0, stdout="Compiled against 10.0\n", stderr="")}
    )
    monkeypatch.setattr(libvirt, "run_command", virsh)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")

    check = doctor._check_kvm()

    assert check.ok
    versions = virsh.celles_de("version")
    assert versions, "aucun virsh version joué"
    for cmd in versions:
        assert "--connect" in cmd and "qemu:///system" in cmd


def test_kvm_rouge_quand_l_uri_systeme_refuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Machine fraîche, utilisateur hors du groupe ``libvirt``, pas de sudo :
    l'URI système ne répond ni en direct ni par ``sudo -n``. Le contrôle doit
    le dire, au lieu d'un vert lu sur l'URI session."""

    def _echec(cmd: list[str], **kwargs: Any) -> CommandResult:
        raise CommandError(
            cmd,
            CommandResult(returncode=1, stdout="", stderr="authentication failed"),
        )

    monkeypatch.setattr(libvirt, "run_command", _echec)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")

    check = doctor._check_kvm()

    assert not check.ok


# ── #173 : les trois sudo virsh passent par run_virsh ────────────────────────

def test_le_reset_kvm_emprunte_le_chemin_detecte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le ``sudo virsh reset`` brut pendait sur un prompt sans terminal, et
    échouait toujours chez qui joint libvirt par le groupe, sans sudo."""
    virsh = VirshScripte()
    monkeypatch.setattr(libvirt, "run_command", virsh)

    assert inventory._reset_kvm_domain(_meta("web1.lab"), "web1.lab")

    resets = virsh.celles_de("reset")
    assert len(resets) == 1
    assert "sudo" not in resets[0], "le chemin direct répond : pas de sudo"
    assert "--connect" in resets[0] and "qemu:///system" in resets[0]
    assert resets[0][-1] == "web1.lab"


def test_un_reset_refuse_reste_un_faux_sans_lever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C'est un dépannage opportuniste : un hyperviseur injoignable ne doit
    pas casser la boucle d'attente qui l'entoure."""

    def _echec(cmd: list[str], **kwargs: Any) -> CommandResult:
        raise CommandError(
            cmd, CommandResult(returncode=1, stdout="", stderr="unreachable")
        )

    monkeypatch.setattr(libvirt, "run_command", _echec)

    assert not inventory._reset_kvm_domain(_meta("web1.lab"), "web1.lab")


def test_un_bail_refuse_est_rendu_a_l_appelant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Best-effort ne veut pas dire muet : le refus doit remonter jusqu'à
    l'écran, pas seulement au journal (issue #173)."""
    virsh = VirshScripte(
        {
            "net-dumpxml": CommandResult(
                returncode=0, stdout="<network><name>lab-demo</name></network>",
                stderr="",
            ),
            "net-update": CommandResult(
                returncode=1, stdout="", stderr="error: permission denied"
            ),
        }
    )
    monkeypatch.setattr(libvirt, "run_command", virsh)

    avertissements = terraform._ensure_kvm_dhcp_leases(_meta("web1.lab"))

    assert len(avertissements) == 1
    assert "web1.lab" in avertissements[0]
    assert "permission denied" in avertissements[0]
    updates = virsh.celles_de("net-update")
    assert updates, "aucun net-update joué"
    assert "--connect" in updates[0] and "qemu:///system" in updates[0]


def test_un_bail_pose_ne_produit_aucun_avertissement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le contre-cas, sans lequel le précédent passerait sur un code qui
    avertit toujours."""
    virsh = VirshScripte(
        {
            "net-dumpxml": CommandResult(
                returncode=0, stdout="<network><name>lab-demo</name></network>",
                stderr="",
            ),
        }
    )
    monkeypatch.setattr(libvirt, "run_command", virsh)

    assert terraform._ensure_kvm_dhcp_leases(_meta("web1.lab")) == []


def test_apply_porte_les_avertissements_de_bail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """``apply`` est le seul relais entre le refus et l'appelant CLI : s'il
    jette la liste, l'écran ne saura jamais rien."""
    monkeypatch.setattr(terraform, "is_available", lambda: True)
    monkeypatch.setattr(terraform, "workdir", lambda meta: tmp_path)
    monkeypatch.setattr(terraform, "write_tfvars", lambda meta: None)
    monkeypatch.setattr(
        terraform, "_ensure_kvm_dhcp_leases", lambda meta, hosts=None: ["refusé"]
    )
    monkeypatch.setattr(
        terraform, "run_command",
        lambda *a, **k: CommandResult(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(
        terraform, "_read_outputs",
        lambda tf_dir, env=None: terraform.ProvisionResult(outputs={}, hosts={}),
    )

    result = terraform.apply(_meta("web1.lab"))

    assert result.warnings == ["refusé"]


def test_provision_affiche_le_refus_de_bail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Critère de l'issue #173 : l'échec se dit **à l'écran**. Un
    ``logger.warning`` que personne ne lit est un silence."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("DSOXLAB_NO_UPDATE_CHECK", "1")
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    monkeypatch.delenv("DSOXLAB_PROVIDER", raising=False)
    (tmp_path / "home" / ".ssh" / "config.d").mkdir(parents=True)

    depot = tmp_path / "repo"
    (depot / "ssh").mkdir(parents=True)
    (depot / "ssh" / "id_ed25519").write_text("clé factice", encoding="utf-8")
    (depot / "meta.yml").write_text(
        "repo:\n  id: demo\n  category: demo\n"
        "infra:\n  provider: kvm\n  network: lab-demo\n  cidr: 10.10.30.0/24\n"
        "  hosts:\n    - name: web1.lab\n",
        encoding="utf-8",
    )

    refus = _(
        "provision_lease_refused",
        host="web1.lab", mac="52:54:00:00:00:10", error="permission denied",
    )
    monkeypatch.setattr(terraform, "other_active_providers", lambda meta: [])
    monkeypatch.setattr(
        terraform, "find_orphan_domains", lambda meta: terraform.OrphanScan()
    )
    monkeypatch.setattr(terraform, "init", lambda *a, **k: None)
    monkeypatch.setattr(
        terraform, "apply",
        lambda *a, **k: terraform.ProvisionResult(
            outputs={}, hosts={}, warnings=[refus]
        ),
    )

    resultat = runner.invoke(app, ["provision", "--lab-home", str(depot)])

    assert resultat.exit_code == 0, resultat.stdout
    assert "web1.lab" in resultat.stdout
    assert "DHCP lease refused" in resultat.stdout


# ── le garde-fou : plus un seul sudo capturé sans -n ─────────────────────────

def _appels_sudo_captures_sans_n(texte: str) -> list[int]:
    """Les lignes où un ``subprocess.run(["sudo", …])`` capture sa sortie
    sans ``-n``. La capture est le critère : c'est elle qui prive le prompt
    de terminal et fait pendre l'appel. Un sudo **interactif** délibéré (le
    ``sudo -v`` de pré-authentification de ``doctor --fix``, gardé par un
    ``isatty``) laisse le prompt s'afficher, et reste légitime."""
    lignes: list[int] = []
    for depart in re.finditer(r"subprocess\.run\(", texte):
        profondeur, fin = 0, None
        for i in range(depart.end() - 1, len(texte)):
            if texte[i] == "(":
                profondeur += 1
            elif texte[i] == ")":
                profondeur -= 1
                if profondeur == 0:
                    fin = i
                    break
        if fin is None:
            continue
        appel = texte[depart.start() : fin + 1]
        capture = "capture_output" in appel or "stdout=" in appel
        if capture and re.search(r'\[\s*"sudo"\s*,\s*"(?!-n")', appel):
            lignes.append(texte.count("\n", 0, depart.start()) + 1)
    return lignes


def test_plus_aucun_sudo_capture_sans_n_en_source() -> None:
    """Le contrat de l'issue #173, sur le modèle du garde-fou
    anti-``shell=True`` : la règle que ``libvirt.py`` s'est donnée vaut pour
    tout ``src/dsoxlab/``, pas pour la moitié des appels."""
    racine = Path(__file__).resolve().parent.parent / "src" / "dsoxlab"
    coupables = [
        f"{chemin}:{ligne}"
        for chemin in sorted(racine.rglob("*.py"))
        for ligne in _appels_sudo_captures_sans_n(
            chemin.read_text(encoding="utf-8")
        )
    ]
    assert coupables == []


def test_le_garde_fou_detecte_bien_le_motif() -> None:
    """Un garde-fou qui ne détecte rien ne garde rien : on le prouve sur le
    motif exact que l'issue #173 a retiré des sources."""
    fautif = (
        'res = subprocess.run(\n'
        '    ["sudo", "virsh", "reset", fqdn],'
        ' capture_output=True, text=True, check=False\n'
        ')\n'
    )
    assert _appels_sudo_captures_sans_n(fautif) == [1]

    corrige = 'res = subprocess.run(["sudo", "-n", "virsh", "reset"], capture_output=True)'
    assert _appels_sudo_captures_sans_n(corrige) == []

    interactif = 'preauth = subprocess.run(["sudo", "-v"], check=False)'
    assert _appels_sudo_captures_sans_n(interactif) == []
