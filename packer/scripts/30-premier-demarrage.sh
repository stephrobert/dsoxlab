#!/usr/bin/env bash
# Ce qui se passe au PREMIER démarrage chez l'utilisateur, et pas à la
# construction. Deux choses ne peuvent pas être figées dans une image :
#
#   1. la version de dsoxlab, qui serait périmée dès le correctif suivant ;
#   2. les hyperviseurs, qui n'ont de sens que si l'hôte expose la virtualisation
#      imbriquée. On ne le sait qu'à l'exécution, jamais à la construction : c'est
#      la leçon de l'issue #91, et `doctor` sait désormais le dire.
set -euo pipefail

install -m 0755 /dev/stdin /usr/local/sbin/dsoxlab-premier-demarrage <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
marque=/var/lib/dsoxlab-premier-demarrage.fait
[ -e "$marque" ] && exit 0

echo "Installation de dsoxlab (dernière version publiée)…"
sudo -u student -H bash -lc 'uv tool install --force dsoxlab' || {
  echo "Échec de l'installation : relancez « uv tool install dsoxlab » une fois" \
       "le réseau disponible." >&2
  exit 0   # ne JAMAIS bloquer le boot sur un réseau absent
}

# Les hyperviseurs seulement si l'hôte expose la virtualisation imbriquée. Sans
# /dev/kvm, les installer ne servirait à rien : `dsoxlab doctor` dit alors que
# l'imbrication n'est pas disponible et que le réglage vit sur l'hôte.
if [ -e /dev/kvm ]; then
  echo "Virtualisation imbriquée disponible : installation de KVM et d'Incus…"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq || true
  apt-get install -y --no-install-recommends \
    qemu-kvm libvirt-daemon-system libvirt-clients virtinst incus || true
  adduser student libvirt || true
  adduser student incus-admin 2>/dev/null || true
else
  echo "Pas de /dev/kvm : les labs « shell » fonctionnent, les labs « vm » non."
  echo "La virtualisation imbriquée s'active sur l'hyperviseur HÔTE, cette"
  echo "machine éteinte. « dsoxlab doctor » le redira au besoin."
fi

touch "$marque"
SCRIPT

cat > /etc/systemd/system/dsoxlab-premier-demarrage.service <<'UNIT'
[Unit]
Description=Première configuration de l'appliance dsoxlab
After=network-online.target
Wants=network-online.target
ConditionPathExists=!/var/lib/dsoxlab-premier-demarrage.fait

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/dsoxlab-premier-demarrage
RemainAfterExit=yes
StandardOutput=journal+console

[Install]
WantedBy=multi-user.target
UNIT

systemctl enable dsoxlab-premier-demarrage.service

# Le mot de passe du build ne doit pas survivre : il est public, il est dans ce
# dépôt. `chage -d 0` force son changement à la première connexion.
chage -d 0 student

# Un mot d'accueil qui dit quoi taper, plutôt qu'un shell muet.
cat > /etc/motd <<'MOTD'

  dsoxlab appliance

  dsoxlab demo        un premier lab, sans rien cloner
  dsoxlab doctor      ce que cette machine peut faire, et ce qui lui manque
  dsoxlab catalog add <url>   installer un catalogue de labs

  Les labs « vm » demandent la virtualisation imbriquée, qui s'active sur
  l'hyperviseur hôte, cette machine éteinte.

MOTD
