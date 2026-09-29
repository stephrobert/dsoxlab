"""Le disque d'une OVA doit finir là où son lecteur s'arrête.

Remontée d'un utilisateur sur l'appliance 0.2.5 : VMware refuse l'import, «SHA256
digest of file does not match manifest». Le disque, lui, est intact.

La cause est mesurée dans `packer/vmdk_flux.py` : le sous-format
``streamOptimized`` est un **flux**, son lecteur s'arrête au premier secteur
entièrement nul qu'il rencontre, et ``qemu-img`` laisse après ce secteur une zone
de zéros d'alignement. Sur le disque publié, **64 512 octets** qu'``ovftool`` n'a
jamais lus et que notre ``sha256sum`` comptait.

Ces tests travaillent sur des disques **synthétiques** : quelques kilo-octets
écrits à la main, avec la seule propriété qui compte — des données, puis une zone
de zéros. Rien n'exige ``qemu-img`` ici, donc rien ne dépend de la machine qui
exécute la suite ; l'accord avec un vrai disque a été établi une fois, à la main,
sur le fichier de la 0.2.5 (20 GiB relus identiques après la coupe).

Le dernier test est le plus utile : il éprouve le **contrôle**, pas la coupe.
C'est lui qui aurait empêché ce défaut de partir chez un utilisateur.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

RACINE = Path(__file__).resolve().parent.parent
SECTEUR = 512


def _module() -> Any:
    """Charge `packer/vmdk_flux.py`, qui n'est pas dans le paquet installé.

    Ce fichier accompagne la recette Packer, pas le moteur : il n'a rien à faire
    dans la roue. On le charge donc par son chemin, comme le script shell le fait
    par `dirname $0`.
    """
    chemin = RACINE / "packer" / "vmdk_flux.py"
    spec = importlib.util.spec_from_file_location("vmdk_flux", chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["vmdk_flux"] = module
    spec.loader.exec_module(module)
    return module


vmdk_flux = _module()


def _disque(
    chemin: Path, *, utiles: int = 4, zeros_en_tete: bool = True, queue: int = 0
) -> Path:
    """Un disque synthétique : en-tête, tables nulles, données, zone de zéros.

    ``zeros_en_tete`` reproduit la propriété qui piège une recherche naïve : les
    tables de grains préallouées sont **nulles**, et elles sont en tête. Un code
    qui chercherait « le premier secteur nul du fichier » couperait là, c'est-à-
    dire au tout début.
    """
    morceaux = [b"KDMV" + b"\x01" * (SECTEUR - 4)]
    if zeros_en_tete:
        morceaux += [b"\x00" * SECTEUR] * 3
    morceaux += [bytes([(i % 251) + 1]) * SECTEUR for i in range(utiles)]
    morceaux += [b"\x00" * SECTEUR] * queue
    chemin.write_bytes(b"".join(morceaux))
    return chemin


# ── trouver la fin du flux ───────────────────────────────────────────────────

def test_la_fin_se_cherche_depuis_la_queue(tmp_path: Path) -> None:
    """Les tables de grains nulles sont en tête : les prendre couperait tout."""
    disque = _disque(tmp_path / "d.vmdk", utiles=4, queue=10)

    fin = vmdk_flux.fin_du_flux(disque)

    # 1 en-tête + 3 tables nulles + 4 secteurs utiles, puis un secteur nul gardé.
    assert fin == (1 + 3 + 4 + 1) * SECTEUR


def test_un_disque_sans_queue_ne_se_coupe_pas(tmp_path: Path) -> None:
    """Rien à couper, et surtout rien à inventer : on rend le fichier tel quel."""
    disque = _disque(tmp_path / "d.vmdk", utiles=4, queue=0)
    taille = disque.stat().st_size

    avant, apres = vmdk_flux.couper(disque)

    assert (avant, apres) == (taille, taille)
    assert disque.stat().st_size == taille


def test_un_disque_entierement_nul_est_refuse(tmp_path: Path) -> None:
    """Couper à l'aveugle produirait une appliance au système incomplet."""
    disque = tmp_path / "vide.vmdk"
    disque.write_bytes(b"\x00" * (SECTEUR * 40))

    with pytest.raises(vmdk_flux.DisqueInattendu):
        vmdk_flux.fin_du_flux(disque)


def test_un_fichier_trop_court_est_refuse(tmp_path: Path) -> None:
    disque = tmp_path / "court.vmdk"
    disque.write_bytes(b"KDMV")

    with pytest.raises(vmdk_flux.DisqueInattendu):
        vmdk_flux.fin_du_flux(disque)


# ── couper ───────────────────────────────────────────────────────────────────

def test_la_coupe_garde_un_secteur_nul(tmp_path: Path) -> None:
    """Il tient le rôle du marqueur de fin, et borne un lecteur aligné."""
    disque = _disque(tmp_path / "d.vmdk", utiles=4, queue=10)

    vmdk_flux.couper(disque)
    donnees = disque.read_bytes()

    assert donnees[-SECTEUR:] == b"\x00" * SECTEUR
    assert donnees[-2 * SECTEUR:-SECTEUR] != b"\x00" * SECTEUR


def test_la_coupe_ne_touche_pas_aux_donnees(tmp_path: Path) -> None:
    """Le contrôle qui compte : ce qui précède la queue est intact."""
    disque = _disque(tmp_path / "d.vmdk", utiles=6, queue=12)
    utile = disque.read_bytes()[: (1 + 3 + 6) * SECTEUR]

    vmdk_flux.couper(disque)

    assert disque.read_bytes().startswith(utile)


def test_la_coupe_est_idempotente(tmp_path: Path) -> None:
    """Un script se rejoue : couper deux fois ne doit pas couper deux fois."""
    disque = _disque(tmp_path / "d.vmdk", utiles=4, queue=10)

    vmdk_flux.couper(disque)
    taille = disque.stat().st_size
    avant, apres = vmdk_flux.couper(disque)

    assert (avant, apres) == (taille, taille)


# ── contrôler, ce qui est le vrai garde-fou ──────────────────────────────────

def test_le_controle_refuse_une_queue_restante(tmp_path: Path) -> None:
    """C'est lui qui aurait arrêté le défaut avant l'utilisateur.

    64 512 octets après le marqueur de fin, exactement ce que portait le disque
    de la 0.2.5 : le manifeste et VMware ne parlent alors pas du même fichier.
    """
    disque = _disque(tmp_path / "d.vmdk", utiles=4, queue=1 + 126)

    with pytest.raises(vmdk_flux.DisqueInattendu) as refus:
        vmdk_flux.empreinte_accordee(disque)

    assert "64512" in str(refus.value)


def test_le_controle_accepte_un_disque_taille(tmp_path: Path) -> None:
    disque = _disque(tmp_path / "d.vmdk", utiles=4, queue=10)
    vmdk_flux.couper(disque)

    empreinte = vmdk_flux.empreinte_accordee(disque)

    assert empreinte == hashlib.sha256(disque.read_bytes()).hexdigest()


def test_les_deux_lectures_donnent_la_meme_empreinte(tmp_path: Path) -> None:
    """La propriété qu'on cherchait, énoncée telle que VMware la vérifie.

    « Ce que `sha256sum` lit » et « ce qu'un lecteur de flux lit » doivent être le
    même octet près. Avant la coupe, non ; après, oui.
    """
    disque = _disque(tmp_path / "d.vmdk", utiles=5, queue=20)

    def empreintes(chemin: Path) -> tuple[str, str]:
        donnees = chemin.read_bytes()
        fin = vmdk_flux.fin_du_flux(chemin)
        return (
            hashlib.sha256(donnees).hexdigest(),
            hashlib.sha256(donnees[:fin]).hexdigest(),
        )

    entier, flux = empreintes(disque)
    assert entier != flux, "sans la coupe, les deux lectures divergent"

    vmdk_flux.couper(disque)
    entier, flux = empreintes(disque)
    assert entier == flux


# ── l'interface en ligne de commande, celle que le script appelle ────────────

def test_la_commande_coupe_et_controle(tmp_path: Path) -> None:
    disque = _disque(tmp_path / "d.vmdk", utiles=4, queue=10)

    assert vmdk_flux.main(["vmdk_flux.py", "couper", str(disque)]) == 0
    assert vmdk_flux.main(["vmdk_flux.py", "controler", str(disque)]) == 0


def test_la_commande_signale_un_disque_non_coupe(tmp_path: Path) -> None:
    """Un code de retour non nul : le script du dépôt s'arrête dessus (`set -e`)."""
    disque = _disque(tmp_path / "d.vmdk", utiles=4, queue=10)

    assert vmdk_flux.main(["vmdk_flux.py", "controler", str(disque)]) == 1


def test_un_usage_errone_ne_passe_pas_pour_un_succes(tmp_path: Path) -> None:
    assert vmdk_flux.main(["vmdk_flux.py"]) == 2
    assert vmdk_flux.main(["vmdk_flux.py", "autre", "x"]) == 2


# ── l'OVF, l'autre moitié de la remontée ────────────────────────────────────

def test_l_ovf_declare_l_os_pour_vmware() -> None:
    """VMware rendait « identifier '' (id: 96) … mapped to Other (32-bit) ».

    `ovf:id="96"` est la bonne valeur CIM (« Debian 64-Bit »), mais sans
    `vmw:osType` ni description, VMware ne trouve aucun nom d'OS et retombe sur
    un profil **32 bits** — pour une appliance qui n'existe qu'en 64 bits.
    """
    script = (RACINE / "packer" / "faire-ova.sh").read_text(encoding="utf-8")

    assert 'xmlns:vmw="http://www.vmware.com/schema/ovf"' in script
    assert 'vmw:osType=' in script
    assert "<Description>Debian GNU/Linux 13 (64-bit)</Description>" in script


def test_le_script_coupe_avant_d_empreindre() -> None:
    """L'ordre décide : empreindre un fichier qu'on coupe ensuite ne sert à rien."""
    script = (RACINE / "packer" / "faire-ova.sh").read_text(encoding="utf-8")

    coupe = script.index('vmdk_flux.py" couper')
    controle = script.index('vmdk_flux.py" controler')
    # L'écriture du manifeste, pas sa première mention : le commentaire de tête
    # du script parle du `.mf` bien avant de l'écrire.
    manifeste = script.index('> "${NOM}.mf"')

    assert coupe < controle < manifeste
