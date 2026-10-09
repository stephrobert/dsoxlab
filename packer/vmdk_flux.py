#!/usr/bin/env python3
"""Un VMDK `streamOptimized` doit finir là où son lecteur s'arrête.

Remontée d'un utilisateur, reproduite sur l'OVA 0.2.5 publiée : VMware refuse
l'import sur une empreinte qui ne correspond pas au manifeste.

La cause, mesurée octet par octet. Le sous-format ``streamOptimized`` est un
**flux** : son lecteur suit une chaîne de marqueurs de 512 octets et s'arrête au
marqueur de fin — ``val=0, size=0, type=0``, soit un secteur entièrement nul. Or
``qemu-img convert -O vmdk -o subformat=streamOptimized`` n'écrit pas un flux
conforme :

* ``gdOffset`` garde un offset réel au lieu de ``0xFFFFFFFFFFFFFFFF`` ;
* il n'écrit ni marqueur *footer* ni marqueur de fin ;
* il termine le fichier par une zone de zéros d'alignement.

Le lecteur prend donc le premier secteur nul de cette zone pour la fin du flux,
et ignore tout ce qui suit. Sur le disque de la 0.2.5 : dernier octet utile à
436 094 621, secteur nul suivant à 436 094 976, fichier de 436 160 000 octets —
**64 512 octets** qu'il n'a jamais lus et que notre ``sha256sum`` comptait. Deux
lectures, deux empreintes, et c'est l'utilisateur qui l'apprend.

Ce module coupe le fichier juste après ce secteur nul, puis **vérifie** que les
deux lectures s'accordent. Éprouvé sur le disque publié de la 0.2.5, qui
déclarait alors 20 GiB : ``qemu-img check`` reste propre et le disque relu est
identique, empreinte du brut comparée avant et après. Le raisonnement ne dépend
pas de cette taille — il porte sur la queue du fichier, dont la zone
d'alignement ne peut pas dépasser un grain. Le secteur nul est conservé : il tient le rôle du marqueur de
fin, et il évite qu'un lecteur aligné lise au-delà du fichier.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

#: Un secteur, l'unité de tout ce format.
SECTEUR = 512

#: Ce qu'on relit en queue pour trouver la fin utile. La zone d'alignement ne
#: peut pas dépasser la taille d'un grain (64 KiB) ; un mégaoctet laisse une
#: marge confortable sans relire un fichier de plusieurs centaines de Mo.
QUEUE = 1024 * 1024


class DisqueInattendu(ValueError):
    """Le fichier ne ressemble pas à ce que cette coupe sait traiter.

    On refuse plutôt que de couper à l'aveugle : se tromper ici produit un
    disque silencieusement tronqué, c'est-à-dire une appliance qui démarre sur
    un système de fichiers incomplet.
    """


def fin_du_flux(chemin: Path) -> int:
    """L'offset où s'arrête un lecteur de flux : après le premier secteur nul.

    Cherché depuis la **fin**, et non depuis le début : le fichier porte des
    secteurs nuls bien avant, dans les tables de grains préallouées en tête. Un
    lecteur de flux ne les rencontre pas — il navigue par marqueurs — mais une
    recherche naïve « premier secteur nul du fichier » les trouverait, et
    couperait le disque en deux.
    """
    taille = chemin.stat().st_size
    if taille < 2 * SECTEUR:
        raise DisqueInattendu(f"{chemin.name} : {taille} octets, trop court")

    with chemin.open("rb") as flux:
        flux.seek(max(0, taille - QUEUE))
        queue = flux.read()

    i = len(queue) - 1
    while i >= 0 and queue[i] == 0:
        i -= 1
    if i < 0:
        raise DisqueInattendu(
            f"{chemin.name} : le dernier mégaoctet est entièrement nul, "
            "refus de couper à l'aveugle"
        )

    dernier_utile = taille - len(queue) + i
    return ((dernier_utile // SECTEUR) + 1) * SECTEUR + SECTEUR


def couper(chemin: Path) -> tuple[int, int]:
    """Coupe le fichier à la fin de son flux. Rend (taille avant, taille après).

    Idempotent : un fichier déjà coupé ne bouge pas, ce qui compte parce qu'un
    script se rejoue.
    """
    avant = chemin.stat().st_size
    fin = fin_du_flux(chemin)
    if fin > avant:
        # Le fichier s'arrête sur des données, sans secteur nul terminal : il n'y
        # a rien à couper, et surtout rien à inventer.
        return avant, avant
    with chemin.open("r+b") as flux:
        flux.truncate(fin)
    return avant, fin


def empreinte_accordee(chemin: Path) -> str:
    """L'empreinte du fichier, si un lecteur de flux lit bien la même chose.

    Le contrôle qui manquait, et sans lequel le défaut est reparti chez
    l'utilisateur. Il porte sur le **résultat** — aucun octet après le marqueur
    de fin — et non sur l'intention de la coupe.
    """
    donnees = chemin.read_bytes()
    i = len(donnees) - 1
    while i >= 0 and donnees[i] == 0:
        i -= 1
    if i < 0:
        raise DisqueInattendu(f"{chemin.name} : disque entièrement nul")
    fin = ((i // SECTEUR) + 1) * SECTEUR + SECTEUR

    reste = len(donnees) - fin
    if reste > 0:
        raise DisqueInattendu(
            f"{chemin.name} : {reste} octets après le marqueur de fin du flux. "
            "`sha256sum` et `ovftool` ne liraient pas la même chose, et l'import "
            "VMware échouerait sur une empreinte qui ne correspond pas au "
            "manifeste."
        )

    entier = hashlib.sha256(donnees).hexdigest()
    flux = hashlib.sha256(donnees[: min(fin, len(donnees))]).hexdigest()
    if entier != flux:  # impossible par construction, gardé comme filet
        raise DisqueInattendu(f"{chemin.name} : deux empreintes divergentes")
    return entier


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in {"couper", "controler"}:
        print("usage: vmdk_flux.py couper|controler <disque.vmdk>", file=sys.stderr)
        return 2

    chemin = Path(argv[2])
    try:
        if argv[1] == "couper":
            avant, apres = couper(chemin)
            retires = avant - apres
            print(
                f"disque coupé au marqueur de fin : {avant} -> {apres} octets "
                f"({retires} retirés)" if retires else
                f"disque déjà coupé au marqueur de fin : {apres} octets"
            )
        else:
            print(f"empreinte du flux et du fichier accordées : "
                  f"{empreinte_accordee(chemin)}")
    except (DisqueInattendu, OSError) as souci:
        print(f"erreur : {souci}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
