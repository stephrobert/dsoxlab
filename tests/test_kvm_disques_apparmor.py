"""Les disques d'une VM KVM se déclarent par chemin, jamais par référence de pool.

Ce n'est pas une préférence de style, c'est la condition pour qu'un lab `vm`
démarre sur Ubuntu et sur Debian, où AppArmor est actif par défaut.

`virt-aa-helper` fabrique le profil AppArmor d'un domaine à partir de son XML.
Il sait résoudre `<disk type='file'><source file='/chemin/absolu'/>`, et pas
`<disk type='volume'><source pool=… volume=…/>`. Avec la seconde forme, **aucun**
disque n'entre dans le profil, et qemu se voit tout refuser par un « Permission
denied » qui ressemble à un problème de propriétaire sans en être un : mettre
tous les volumes en `libvirt-qemu:kvm` ne change rien.

Mesuré sur Ubuntu 24.04.2, avec le `virt-aa-helper` du paquet et le provider
`dmacvicar/libvirt` 0.9.8, sur deux domaines créés côte à côte à partir du même
volume, puis détruits :

    source.volume → <disk type='volume'> → profil généré : aucune règle de disque
    source.file   → <disk type='file'>   → « /var/lib/…/x.qcow2 » rwk,

Le `rwk` compte jusque dans sa dernière lettre : sans le droit de verrouillage
`k`, l'échec devient « Failed to lock byte 100 ».

Ce que ce module tient, c'est la forme du template packagé. Il ne peut pas
prouver le démarrage d'une VM, ce qui demande une machine où les profils libvirt
sont en `enforce` ; il empêche en revanche la régression silencieuse qui
ramènerait la forme non résoluble, dont rien d'autre ne rendrait compte avant le
premier `provision` d'un apprenant.
"""

from __future__ import annotations

import re

from dsoxlab.templates import template_root

#: Bornes du bloc qui déclare les disques du domaine. Le pool reste la bonne
#: façon de **créer** un volume : c'est la façon de le **désigner au domaine**
#: qui décide du profil AppArmor. Les deux ne doivent donc pas être confondues,
#: d'où la lecture d'une tranche précise du fichier plutôt que du tout.
_DEBUT = "disks = concat("
_FIN = "interfaces = ["

_POOL = re.compile(r"^\s*pool\s*=", re.MULTILINE)
_VOLUME = re.compile(r"^\s*volume\s*=\s*\{?", re.MULTILINE)
_CHEMIN = re.compile(r"file\s*=\s*libvirt_volume\.(\w+)\[")


def _main_tf() -> str:
    return (template_root() / "terraform" / "kvm" / "main.tf").read_text(
        encoding="utf-8"
    )


def _bloc_disques(texte: str) -> str:
    """La tranche du main.tf qui déclare les disques du domaine.

    L'assertion n'est pas décorative : si la structure du fichier change, la
    tranche devient vide et tous les contrôles de ce module passeraient au vert
    sans rien lire. Un test qui ne mesure plus rien doit tomber, pas se taire.
    """
    debut = texte.find(_DEBUT)
    assert debut != -1, (
        f"« {_DEBUT} » introuvable : la structure du main.tf a changé, "
        "ce module ne lit plus les disques du domaine"
    )
    fin = texte.find(_FIN, debut)
    assert fin > debut, (
        f"« {_FIN} » introuvable après les disques : la tranche lue serait "
        "vide, et les contrôles passeraient au vert à vide"
    )
    return texte[debut:fin]


def test_aucun_disque_declare_par_reference_de_pool() -> None:
    """La forme que virt-aa-helper ne sait pas résoudre ne doit plus exister."""
    bloc = _bloc_disques(_main_tf())

    assert not _POOL.search(bloc), (
        "un disque du domaine désigne encore un pool : virt-aa-helper ne "
        "résoudra aucun disque, et aucune VM ne démarrera sous AppArmor"
    )
    assert not _VOLUME.search(bloc), (
        "un disque du domaine désigne encore un volume par son nom : c'est "
        "l'autre moitié de la forme <disk type='volume'>"
    )


def test_les_trois_disques_pointent_un_chemin() -> None:
    """Système, seed cloud-init et disque additionnel, tous les trois.

    En compter le nombre exact plutôt que se contenter d'une présence : le
    défaut d'origine tenait justement à ce qu'un seul des trois avait été
    corrigé n'aurait rien changé, un domaine dont un disque manque au profil
    échouant exactement comme un domaine dont aucun n'y figure.
    """
    ressources = _CHEMIN.findall(_bloc_disques(_main_tf()))

    assert sorted(ressources) == ["cloudinit", "extra", "host"], (
        f"les trois disques doivent pointer un chemin de volume, vus : {ressources}"
    )


def test_les_volumes_restent_crees_dans_le_pool() -> None:
    """Le contrepoids : on ne règle pas AppArmor en abandonnant le pool.

    Sans ce contrôle, supprimer purement et simplement le pool des ressources
    `libvirt_volume` ferait passer les deux tests précédents, tout en cassant le
    réglage `infra.providers.kvm.storage_pool` que l'issue #94 a introduit.
    """
    texte = _main_tf()
    bloc = _bloc_disques(texte)
    hors_disques = texte.replace(bloc, "")

    assert len(_POOL.findall(hors_disques)) == 4, (
        "les quatre ressources libvirt_volume doivent toujours déclarer leur "
        "pool : le chemin du disque en dérive"
    )
    assert 'lookup(var.provider_config, "storage_pool", "default")' in hors_disques
