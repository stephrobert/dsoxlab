"""Le bloc qui installe l'agent Incus dans le cloud-init AlmaLinux.

Pourquoi ce bloc existe : les images cloud montent leur config drive en 9p pour
récupérer l'agent, or la famille RHEL n'a pas ce driver. Sans agent, Incus ne
remonte aucune IP et ``dsoxlab provision`` expire sur son attente réseau alors
que la VM a parfaitement booté. Incus prévoit ce cas avec le device
``agent:config``, qui expose les mêmes fichiers sur un CD-ROM ISO 9660.

Pourquoi ce test existe : le bloc doit être un no-op **silencieux et sans échec**
partout ailleurs. Deux pièges, tous deux déjà payés dans ce projet :

- le provider KVM attache lui aussi un CD-ROM (le seed cloud-init NoCloud), donc
  tester la seule existence de ``/dev/sr0`` ne discrimine rien ;
- un ``runcmd`` qui sort non nul fait finir cloud-init en ``status: error``, ce
  qui bloque l'attente de provision sur une VM pourtant prête : exactement ce
  qui s'est produit avec ``systemctl enable --now qemu-guest-agent``.
"""

from __future__ import annotations

import re
import subprocess

import pytest
import yaml

from dsoxlab.templates import cloud_init_template, template_root


def _runcmd(stem: str) -> list[object]:
    """Rend le ``runcmd`` d'un template cloud-init, variables substituées."""
    brut = cloud_init_template(stem).read_text(encoding="utf-8")
    rendu = brut.replace("${hostname}", "alma-rhcsa-1.lab").replace(
        "${ssh_pubkey}", "ssh-ed25519 AAAAC3Nz factice"
    )
    # Une interpolation Terraform oubliée lèverait à l'apply, jamais en test.
    restes = re.findall(r"\$\{[^}]*\}|%\{[^}]*\}", rendu)
    assert not restes, f"interpolations non résolues dans {stem} : {restes}"
    doc = yaml.safe_load(rendu)
    return list(doc["runcmd"])


def _bloc_agent() -> str:
    blocs = [
        c for c in _runcmd("almalinux") if isinstance(c, str) and "install.sh" in c
    ]
    assert len(blocs) == 1, f"attendu 1 bloc agent Incus, trouvé {len(blocs)}"
    return blocs[0]


def test_le_cloud_init_almalinux_installe_l_agent_incus() -> None:
    assert "iso9660" in _bloc_agent(), (
        "l'agent doit être récupéré depuis le CD-ROM agent:config"
    )


def test_le_discriminant_est_install_sh_pas_le_device() -> None:
    """Le seul test qui distingue Incus de KVM est la présence de install.sh.

    Le provider KVM attache son seed NoCloud en CD-ROM (cf.
    ``templates/terraform/kvm/main.tf``, devices.disks[].device = "cdrom") :
    /dev/sr0 y existe donc aussi.
    """
    bloc = _bloc_agent()
    assert "-f /run/incus_config/install.sh" in bloc, (
        "le bloc doit vérifier la présence de install.sh avant de l'exécuter"
    )
    main_tf = (template_root() / "terraform" / "kvm" / "main.tf").read_text(
        encoding="utf-8"
    )
    assert 'device = "cdrom"' in main_tf, (
        "prémisse de ce test : KVM attache bien un CD-ROM. Si ce n'est plus le "
        "cas, le discriminant peut être simplifié."
    )


def test_le_bloc_ne_peut_pas_faire_echouer_cloud_init() -> None:
    assert _bloc_agent().rstrip().endswith("exit 0"), (
        "un runcmd non nul fait finir cloud-init en status: error, ce qui bloque "
        "l'attente de provision sur une VM pourtant prête"
    )


@pytest.mark.parametrize("shell", ["sh", "bash"])
def test_le_bloc_est_du_shell_valide(shell: str) -> None:
    """cloud-init passe une entrée runcmd de type chaîne au shell système."""
    # check=False : le code retour est ce que le test mesure. Lever donnerait
    # une CalledProcessError nue là où l'assertion nomme le shell fautif.
    proc = subprocess.run(
        [shell, "-n"], input=_bloc_agent(), text=True, capture_output=True, check=False
    )
    assert proc.returncode == 0, f"{shell} rejette le bloc :\n{proc.stderr}"


def test_les_autres_distros_n_ont_pas_ce_bloc() -> None:
    """Ubuntu et Debian ont le driver 9p : leur agent est récupéré tout seul.

    Y ajouter le bloc serait du bruit, et surtout une divergence à maintenir.
    """
    for stem in ("ubuntu", "debian"):
        blocs = [
            c for c in _runcmd(stem) if isinstance(c, str) and "install.sh" in c
        ]
        assert not blocs, f"{stem} n'a pas besoin du contournement 9p"
