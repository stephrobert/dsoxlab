"""Le plan de `doctor --fix` et le playbook du poste, sans toucher la machine.

Ce que ce module prouve :

- le plan range chaque étape là où elle doit aller : lancée par dsoxlab (sans
  sudo), confiée au playbook (root), ou seulement nommée (manuelle) ; Docker
  et Incus facultatifs n'y entrent qu'avec ``--clients`` ;
- le playbook joue exactement les lignes affichées, à trois transformations
  près : ``sudo`` retiré, ``-y`` ajouté aux installations, ``$USER`` remplacé
  par le compte de l'apprenant (sous ``become``, il vaudrait root) ;
- une étape n'est réussie que si le contrôle, refait, est vert, ou n'attend
  plus qu'une reconnexion.
"""

from __future__ import annotations

import pytest
import yaml

from dsoxlab.services.doctor import DoctorReport, Fix, FixKind, _check
from dsoxlab.services.doctor_controles.modele import STATE_UNKNOWN
from dsoxlab.services.doctor_controles.remedes import Remede
from dsoxlab.services.doctor_etapes import construire
from dsoxlab.services.remediation import (
    Application,
    etape_verifiee,
    lignes_root,
    planifier,
    playbook_du_poste,
)


def _rapport(*checks: object, optional: tuple[object, ...] = ()) -> DoctorReport:
    report = DoctorReport()
    report.required.extend(checks)  # type: ignore[arg-type]
    report.optional.extend(optional)  # type: ignore[arg-type]
    return report


_ROOT = Remede("kvm", ("sudo apt install libvirt-clients",), root=True, tag="libvirt")
_DOCKER = Remede("docker", ("sudo apt install docker-ce",), root=True, tag="docker")


class TestPlanifier:
    def test_chaque_etape_va_ou_elle_doit(self) -> None:
        report = _rapport(
            _check("kvm", False, "absent", remede=_ROOT),
            _check("ansible", False, "absent", fix=Fix((("uv", "tool", "install", "ansible-core"),))),
            _check("hw_virt", False, "active la virtualisation dans le BIOS"),
            _check("provider", False, "à choisir", hint="dsoxlab use --provider kvm"),
        )
        plan = planifier(report, actions={"provider": lambda: None})

        assert [e.cle for e in plan.root] == ["kvm"]
        assert [e.cle for e in plan.sans_sudo] == ["provider", "ansible"]
        assert [e.cle for e in plan.manuelles] == ["hw_virt"]
        assert plan.executables == 3

    def test_un_correctif_manuel_n_est_jamais_lance(self) -> None:
        report = _rapport(_check(
            "x", False, "cassé", fix=Fix((("rm", "-rf", "/x"),), kind=FixKind.MANUAL),
        ))
        plan = planifier(report)

        assert plan.executables == 0
        assert [e.cle for e in plan.manuelles] == ["x"]

    def test_une_consigne_sans_action_reste_manuelle(self) -> None:
        """Une commande affichée que dsoxlab ne sait pas jouer n'est pas lancée."""
        report = _rapport(_check("labs", False, "aucun", hint="dsoxlab catalog add linux"))
        assert [e.cle for e in planifier(report).manuelles] == ["labs"]

    def test_les_facultatifs_n_entrent_qu_avec_clients(self) -> None:
        report = _rapport(optional=(_check("docker", False, "absent", remede=_DOCKER),))

        assert planifier(report).vide
        assert [e.cle for e in planifier(report, clients=True).root] == ["docker"]

    def test_un_controle_en_attente_entre_dans_le_plan(self) -> None:
        """Le pool attend libvirt : une seule passe de `--fix` fait les deux."""
        pool = Remede("libvirt_pool", ("sudo virsh pool-define-as default dir",), root=True)
        report = _rapport(
            _check("kvm", False, "absent", remede=_ROOT),
            _check("libvirt_pool", False, "en attente", forced_state=STATE_UNKNOWN,
                   apres="kvm", remede=pool),
        )
        assert [e.cle for e in planifier(report).root] == ["kvm", "libvirt_pool"]


class TestLignesRoot:
    def test_sudo_est_retire_partout_y_compris_apres_un_tube(self) -> None:
        jouees = lignes_root((
            "wget -O - https://x/gpg | sudo gpg --dearmor -o /k.gpg",
            "sudo apt update && sudo apt install terraform",
        ), "bob")

        assert "sudo" not in jouees
        assert "| gpg --dearmor" in jouees
        assert "apt update && apt install -y terraform" in jouees

    def test_une_installation_ne_pose_jamais_de_question(self) -> None:
        jouees = lignes_root((
            "sudo apt install git", "sudo dnf install -y yum-utils", "sudo dnf -y install terraform",
        ), "bob")

        assert "apt install -y git" in jouees
        assert "dnf install -y yum-utils" in jouees
        assert "-y -y" not in jouees
        assert "dnf -y install terraform" in jouees

    def test_user_vise_l_apprenant_et_pas_root(self) -> None:
        """Sous `become`, `$USER` vaut root : le groupe irait au mauvais compte."""
        jouees = lignes_root(("sudo usermod -aG kvm,libvirt $USER",), "student")
        assert "usermod -aG kvm,libvirt student" in jouees
        assert "$USER" not in jouees

    def test_le_script_s_arrete_a_la_premiere_ligne_en_echec(self) -> None:
        assert lignes_root(("sudo true",), "bob").startswith("set -e\n")

    @pytest.mark.parametrize("compte", ["bob; rm -rf /", "$(id)", "Bob Smith", ""])
    def test_un_nom_de_compte_inhabituel_est_refuse(self, compte: str) -> None:
        with pytest.raises(ValueError, match="unusual account name"):
            lignes_root(("sudo usermod -aG kvm $USER",), compte)


class TestPlaybook:
    def test_une_tache_par_etape_dans_l_ordre_du_plan(self) -> None:
        pool = Remede("libvirt_pool", ("sudo virsh pool-build default",), root=True, tag="pool")
        report = _rapport(
            _check("libvirt_pool", False, "absent", remede=pool),
            _check("kvm", False, "absent", remede=_ROOT),
        )
        etapes = planifier(report).root
        jeu = yaml.safe_load(playbook_du_poste(etapes, "bob"))

        assert jeu[0]["hosts"] == "localhost"
        assert jeu[0]["become"] is True
        taches = jeu[0]["tasks"]
        # L'ordre est celui des dépendances (libvirt avant son pool), pas
        # celui du rapport.
        assert [t["tags"] for t in taches] == [["libvirt"], ["pool"]]
        assert "apt install -y libvirt-clients" in taches[0]["ansible.builtin.shell"]
        assert taches[0]["environment"] == {"DEBIAN_FRONTEND": "noninteractive"}

    def test_un_heredoc_survit_au_yaml(self) -> None:
        """Le dépôt Docker s'écrit par un heredoc : ses lignes restent entières."""
        heredoc = Remede("docker", (
            "sudo tee /etc/apt/sources.list.d/docker.sources <<EOF",
            "Types: deb",
            "Suites: $(. /etc/os-release && echo \"${UBUNTU_CODENAME:-$VERSION_CODENAME}\")",
            "EOF",
        ), root=True, tag="docker")
        etapes = planifier(_rapport(), clients=True).root + planifier(
            _rapport(optional=(_check("docker", False, "absent", remede=heredoc),)), clients=True,
        ).root
        script = yaml.safe_load(playbook_du_poste(etapes, "bob"))[0]["tasks"][0][
            "ansible.builtin.shell"]

        assert "tee /etc/apt/sources.list.d/docker.sources <<EOF\nTypes: deb\n" in script
        assert "${UBUNTU_CODENAME:-$VERSION_CODENAME}" in script


class TestVerification:
    def _etape(self, check: object) -> object:
        return construire(_rapport(check)).etapes[0]

    def test_un_controle_revenu_au_vert_valide_l_etape(self) -> None:
        etape = self._etape(_check("kvm", False, "absent", remede=_ROOT))
        assert etape_verifiee(etape, _rapport(_check("kvm", True, "libvirt 10.0.0")))  # type: ignore[arg-type]

    def test_un_controle_toujours_rouge_invalide_l_etape(self) -> None:
        """Un code de retour nul ne suffit pas : c'est le contrôle refait qui juge."""
        etape = self._etape(_check("kvm", False, "absent", remede=_ROOT))
        assert not etape_verifiee(etape, _rapport(_check("kvm", False, "absent", remede=_ROOT)))  # type: ignore[arg-type]

    def test_une_reconnexion_attendue_compte_comme_reussie(self) -> None:
        groupes = Remede("groupes", ("sudo usermod -aG libvirt $USER",), root=True, reconnexion=True)
        etape = self._etape(_check("groupes", False, "absent", remede=groupes))
        apres = _rapport(_check(
            "groupes", False, "reconnectez-vous",
            remede=Remede("groupes", (), root=False, reconnexion=True),
        ))
        assert etape_verifiee(etape, apres)  # type: ignore[arg-type]

    def test_un_controle_disparu_n_est_pas_une_reussite(self) -> None:
        etape = self._etape(_check("kvm", False, "absent", remede=_ROOT))
        assert not etape_verifiee(etape, _rapport())  # type: ignore[arg-type]


class TestEffetDiffere:
    def _application(self, *, kind: FixKind = FixKind.AUTOMATIC, code: int = 0,
                     reconnexion: bool = False) -> Application:
        remede = Remede("x", ("x",), root=False, reconnexion=reconnexion)
        etape = construire(_rapport(_check("x", False, "cassé", fix=Fix((("x",),), kind=kind),
                                           remede=remede))).etapes[0]
        return Application(etape, code, verifiee=code == 0)

    def test_un_succes_immediat_n_annonce_rien(self) -> None:
        assert self._application().avis_differe is None

    def test_une_reconnexion_requise_est_annoncee(self) -> None:
        assert self._application(reconnexion=True).avis_differe == "fix_needs_relogin"
        assert self._application(kind=FixKind.NEEDS_RELOGIN).avis_differe == "fix_needs_relogin"

    def test_un_redemarrage_requis_est_annonce(self) -> None:
        assert self._application(kind=FixKind.NEEDS_REBOOT).avis_differe == "fix_needs_reboot"

    def test_un_echec_n_annonce_aucun_effet_differe(self) -> None:
        assert self._application(reconnexion=True, code=1).avis_differe is None
