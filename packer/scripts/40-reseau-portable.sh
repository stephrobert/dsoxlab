#!/usr/bin/env bash
# Le réseau doit survivre au changement d'hyperviseur.
#
# L'installateur Debian fige dans /etc/network/interfaces le nom de l'interface
# qu'il a vue pendant l'installation — `enp0s2` sous le QEMU qui construit cette
# image. Ce nom est dérivé de la POSITION PCI de la carte : il devient
# `enp0s17` sous VirtualBox, autre chose encore sous VMware ou Hyper-V. La
# configuration ne s'applique alors à aucune interface, et la machine démarre
# sans réseau du tout.
#
# Mesuré, pas supposé. Importée dans VirtualBox 7.2, l'appliance affichait :
#
#   enp0s17   DOWN                       ← la carte, sans configuration
#   /etc/resolv.conf : aucun nameserver  ← donc aucune résolution
#
# et son premier démarrage échouait sur « Temporary failure in name
# resolution » : ni dsoxlab, ni les hyperviseurs, ni le bureau. Le défaut était
# invisible sous QEMU, où le nom coïncide par construction — c'est-à-dire
# invisible à tous les essais faits jusque-là, et présent chez tous les
# utilisateurs Windows et macOS, le public même de cette appliance.
#
# systemd-networkd sait dire « toute carte Ethernet, quel que soit son nom », ce
# qu'ifupdown ne sait pas : le fichier ci-dessous ne NOMME aucune interface, il
# les DÉCRIT.
#
# Pourquoi un script à part, joué ici et pas dans 10-base.sh : basculer le
# résolveur coupe la résolution le temps que systemd-resolved prenne la main, et
# 20-outils.sh télécharge encore terraform et ansible. À cet endroit, plus rien
# n'a besoin du réseau — 90-nettoyage.sh ne fait que purger et trimmer.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get install -y --no-install-recommends systemd-resolved

mkdir -p /etc/systemd/network
cat > /etc/systemd/network/10-dsoxlab-dhcp.network <<'NET'
# Aucune interface n'est nommée ici, et c'est tout l'intérêt : cette appliance
# doit obtenir une adresse sous QEMU, VirtualBox, VMware ou Hyper-V, où la même
# carte porte quatre noms différents.
[Match]
Name=en* eth*
Type=ether

[Network]
DHCP=yes

[DHCP]
UseDomains=yes
NET

# La strophe figée par l'installateur doit partir : si le nom coïncidait malgré
# tout, deux gestionnaires se disputeraient la même carte.
cat > /etc/network/interfaces <<'IFACES'
# La configuration réseau de cette appliance vit dans
# /etc/systemd/network/10-dsoxlab-dhcp.network, qui ne nomme aucune interface :
# c'est ce qui lui permet de fonctionner sous n'importe quel hyperviseur.
source /etc/network/interfaces.d/*

auto lo
iface lo inet loopback
IFACES

systemctl enable systemd-networkd systemd-resolved

# `network-online.target` n'attendait RIEN : `ifupdown-wait-online` est désactivé
# sur cette image (mesuré : « disabled »), si bien que le service de premier
# démarrage partait avant le premier bail DHCP. Celui de networkd, lui, attend
# une adresse — c'est la moitié du défaut ci-dessus, et elle se serait
# manifestée même avec le bon nom d'interface.
systemctl enable systemd-networkd-wait-online.service

# Sans ce lien, la résolution reste muette une fois l'adresse obtenue : c'est
# resolved qui écoute sur le stub, et /etc/resolv.conf doit y renvoyer.
ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf

# Les baux de dhcpcd pris pendant la construction décriraient une carte qui
# n'existera plus, sous un nom qui n'existera plus.
rm -rf /var/lib/dhcpcd/* /var/lib/dhcp/*

echo "Réseau portable : systemd-networkd sur « en* eth* », resolved actif."
