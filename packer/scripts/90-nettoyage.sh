#!/usr/bin/env bash
# Réduire l'image et retirer ce qui ne doit pas être distribué. Ce script décide
# du poids final, donc de ce que l'utilisateur téléchargera.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get -y autoremove --purge
apt-get -y clean
rm -rf /var/lib/apt/lists/*

# Les clés d'hôte SSH sont régénérées au premier boot : distribuer les mêmes
# clés privées à tous les utilisateurs serait une faute de sécurité, pas un
# détail de taille.
rm -f /etc/ssh/ssh_host_*
cat > /etc/systemd/system/regen-ssh-host-keys.service <<'UNIT'
[Unit]
Description=Régénère les clés d'hôte SSH propres à cette machine
Before=ssh.service
ConditionPathExists=!/etc/ssh/ssh_host_ed25519_key

[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT
systemctl enable regen-ssh-host-keys.service

# Identité machine : la laisser identique sur toutes les copies ferait que deux
# appliances obtiendraient le même bail DHCP.
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id

# Historiques et journaux : rien de personnel ne doit partir dans l'image.
rm -f /root/.bash_history /home/student/.bash_history
journalctl --rotate --vacuum-time=1s || true
rm -rf /tmp/* /var/tmp/*

# Les journaux de l'installateur et les vieux gabarits debconf : ils ne servent
# qu'à diagnostiquer une installation qui vient de réussir.
rm -rf /var/log/installer /var/cache/debconf/*-old
find /var/log -type f -exec truncate -s 0 {} +

# Garde-fou : un seul noyau doit rester. Deux noyaux pèsent 170 Mio bruts, et le
# cas arrive dès qu'un `full-upgrade` en installe un plus récent.
test "$(ls /boot/vmlinuz-* | wc -l)" -eq 1 \
  || { echo "plus d'un noyau installé : l'image serait inutilement lourde" >&2; exit 1; }

# La swap n'est ni un système de fichiers ni de l'espace libre : ni `fstrim` ni un
# remplissage par zéros ne la touchent, et elle peut contenir jusqu'à 100 Mio de
# pages écrites pendant l'installation. On la libère, on la jette, on la refait
# avec le MÊME UUID, sans quoi /etc/fstab ne la retrouverait plus au boot.
for dev in $(awk 'NR>1 {print $1}' /proc/swaps); do
  uuid=$(blkid -s UUID -o value "$dev") || continue
  swapoff "$dev" && blkdiscard -f "$dev" && mkswap -q -U "$uuid" "$dev"
done

# Le vide est rendu à l'hôte. Le disque étant attaché en `discard=unmap` et
# `detect-zeroes=unmap` (voir le .pkr.hcl), ce `fstrim` libère RÉELLEMENT les
# clusters du qcow2 : c'est mesuré, 1110 Mio d'artefact sous le défaut `ignore`
# contre 597 avec `unmap`.
#
# Il n'y a plus de repli par remplissage de zéros, et c'est délibéré : sous
# `ignore` il était le seul à fonctionner, mais il écrivait toute la place libre
# (environ 17 Gio sur ce disque) avant que le convert final ne la reprenne. Un
# repli qui ne se déclenche jamais n'est pas un repli ; celui-là coûtait des
# minutes quand il se déclenchait.
fstrim -av

# La mesure, affichée : elle se compare au « disk size » que `qemu-img info`
# donne côté hôte, et c'est ce qui permet de voir une régression du trim.
df -m /
sync
