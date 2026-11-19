"""Le plan de `doctor --fix` et le playbook du poste, sans toucher la machine.

Ce que ce module prouve :

- le plan range chaque étape là où elle doit aller : lancée par dsoxlab (sans
  sudo), confiée au playbook (root), ou seulement nommée (manuelle) ; Docker
  et Incus facultatifs n'y entrent qu'avec ``--clients`` ;
- les profils s'emboîtent (socle, ``--clients``, ``--all``), et chaque étape
  root devient un composant du playbook du poste, statique et embarqué ;
- le playbook ne joue aucun shell, rafraîchit l'index APT avant toute
  installation, et couvre chaque remède root de la table ;
- une étape n'est réussie que si le contrôle, refait, est vert, ou n'attend
  plus qu'une reconnexion.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest
import yaml

from dsoxlab.services.doctor import DoctorReport, Fix, FixKind, _check
from dsoxlab.services.doctor_controles import remedes
from dsoxlab.services.doctor_controles.modele import STATE_UNKNOWN
from dsoxlab.services.doctor_controles.remedes import Remede
from dsoxlab.services.doctor_etapes import construire
from dsoxlab.services.remediation import (
    _COMPOSANTS,
    PROFILS,
    Application,
    composants,
    composants_du_profil,
    etape_verifiee,
    planifier,
    playbook_du_poste,
    profil_de,
    variables_du_poste,
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


class TestProfils:
    def test_le_socle_entre_sans_option_mais_pas_docker(self) -> None:
        """Le profil par défaut installe le socle KVM, même facultatif ici."""
        report = _rapport(optional=(
            _check("kvm", False, "absent", remede=_ROOT),
            _check("docker", False, "absent", remede=_DOCKER),
        ))
        assert [e.cle for e in planifier(report).root] == ["kvm"]

    def test_all_contient_clients_qui_contient_le_socle(self) -> None:
        assert PROFILS["socle"] < PROFILS["clients"] < PROFILS["tout"]
        assert {"docker", "incus"} <= PROFILS["clients"]
        assert {"terraform", "ansible", "collections"} <= PROFILS["tout"]

    def test_all_fait_entrer_terraform(self) -> None:
        tf = Remede("terraform", ("sudo apt install terraform",), root=True, tag="terraform")
        report = _rapport(optional=(_check("terraform", False, "absent", remede=tf),))
        assert planifier(report, profil="clients").vide
        assert [e.cle for e in planifier(report, profil="tout").root] == ["terraform"]

    def test_les_options_donnent_le_profil(self) -> None:
        assert profil_de(clients=False, tout=False) == "socle"
        assert profil_de(clients=True, tout=False) == "clients"
        assert profil_de(clients=False, tout=True) == "tout"
        assert profil_de(clients=True, tout=True) == "tout"


class TestComposants:
    def test_les_etapes_root_deviennent_des_composants_dans_l_ordre_du_playbook(self) -> None:
        etapes = construire(_rapport(
            _check("docker", False, "absent", remede=_DOCKER),
            _check("kvm", False, "absent", remede=_ROOT),
            _check("libvirtd", False, "arrêté",
                   remede=Remede("libvirtd", ("sudo systemctl enable --now libvirtd",), root=True)),
        ), facultatives=frozenset()).etapes
        # libvirtd est réalisé par le composant kvm : pas de doublon.
        assert composants(etapes) == ["kvm", "docker"]

    def test_une_etape_root_sans_composant_est_une_erreur(self) -> None:
        inconnu = Remede("nouveau", ("sudo x",), root=True)
        etapes = construire(_rapport(_check("nouveau", False, "absent", remede=inconnu))).etapes
        with pytest.raises(ValueError, match="without a playbook component"):
            composants(etapes)

    def test_chaque_remede_root_de_la_table_a_son_composant(self) -> None:
        """Une entrée root ajoutée à la table sans composant casserait --fix."""
        for famille in ("ubuntu", "almalinux"):
            sys_ = remedes.Systeme(remedes.Famille.RHEL if famille == "almalinux" else remedes.Famille.DEBIAN,
                                   famille, famille)
            for cle in remedes.TABLE:
                remede = remedes.remede(cle, sys_)
                if remede is not None and remede.root:
                    assert remede.cle in _COMPOSANTS, (famille, cle)


class TestVariables:
    def test_le_pool_et_les_groupes_viennent_du_diagnostic(self) -> None:
        pool = Remede("libvirt_pool", ("sudo virsh pool-define-as labs dir --target /x",), root=True)
        groupes = Remede("groupes", ("sudo usermod -aG libvirt $USER",), root=True, reconnexion=True)
        docker = Remede("docker", ("sudo usermod -aG docker $USER",), root=True)
        etapes = construire(_rapport(
            _check("docker", False, "absent", remede=docker),
            _check("groupes", False, "absent", remede=groupes),
            _check("libvirt_pool", False, "absent", remede=pool),
        )).etapes
        variables = variables_du_poste(etapes, "bob")

        assert variables["utilisateur"] == "bob"
        assert variables["pool"] == "labs"
        # Le groupe docker n'est pas un groupe de virtualisation : il ne fuit pas.
        assert variables["groupes"] == ["libvirt"]
        # Les étapes à faire, plus tout le socle (profil par défaut).
        assert variables["composants"] == ["git", "kvm", "efi", "groupes", "pool", "docker"]

    def test_le_profil_entier_part_au_playbook_en_une_passe(self) -> None:
        """Un pool qui « attend libvirt » n'est pas encore à faire : sans le
        profil, il fallait relancer --fix (banc Ubuntu 24.04 du 2026-11-19)."""
        etapes = construire(_rapport(_check("kvm", False, "absent", remede=_ROOT)),
                            facultatives=frozenset()).etapes
        assert variables_du_poste(etapes, "bob")["composants"] == ["git", "kvm", "efi", "groupes", "pool"]
        assert variables_du_poste(etapes, "bob", "clients")["composants"][-2:] == ["docker", "incus"]
        assert composants_du_profil("tout")[-1] == "terraform"

    @pytest.mark.parametrize("compte", ["bob; rm -rf /", "$(id)", "Bob Smith", ""])
    def test_un_nom_de_compte_inhabituel_est_refuse(self, compte: str) -> None:
        with pytest.raises(ValueError, match="unusual account name"):
            variables_du_poste([], compte)


class TestPlaybookEmbarque:
    def test_le_playbook_est_embarque_et_vise_le_poste(self) -> None:
        chemin = playbook_du_poste()
        jeu = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        assert jeu[0]["hosts"] == "localhost"
        assert jeu[0]["become"] is True
        assert jeu[0]["connection"] == "local"

    def test_aucune_commande_shell_n_est_jouee(self) -> None:
        """Le principe du brief : des modules natifs, pas de shell généré."""
        texte = playbook_du_poste().read_text(encoding="utf-8")
        assert "ansible.builtin.shell" not in texte
        assert "ansible.builtin.raw" not in texte

    def test_chaque_composant_a_ses_taches(self) -> None:
        texte = playbook_du_poste().read_text(encoding="utf-8")
        for composant in set(_COMPOSANTS.values()):
            assert f"'{composant}' in composants" in texte, composant

    def test_l_index_apt_est_rafraichi_avant_la_premiere_installation(self) -> None:
        taches = yaml.safe_load(playbook_du_poste().read_text(encoding="utf-8"))[0]["tasks"]
        premiere_install = next(i for i, t in enumerate(taches)
                                if any(m in t for m in ("ansible.builtin.package", "ansible.builtin.apt"))
                                and "name" in (t.get("ansible.builtin.package") or t.get("ansible.builtin.apt") or {}))
        rafraichi = next(i for i, t in enumerate(taches)
                         if (t.get("ansible.builtin.apt") or {}).get("update_cache"))
        assert rafraichi < premiere_install

    @pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible-playbook absent")
    def test_le_playbook_se_charge(self) -> None:
        res = subprocess.run(
            ["ansible-playbook", "--syntax-check", "-i", "localhost,", str(playbook_du_poste()),
             "-e", '{"composants": ["git"], "utilisateur": "bob"}'],
            capture_output=True, text=True, check=False,
        )
        assert res.returncode == 0, res.stderr


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
