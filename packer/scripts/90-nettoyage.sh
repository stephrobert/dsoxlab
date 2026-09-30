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

# Le home appartient à son propriétaire, quoi qu'il se soit passé avant. C'est une
# ceinture, pas un remplacement du `sudo -H` du .pkr.hcl : un seul fichier créé
# par root dans ~student suffit à casser Ansible pour toujours, et le symptôme
# (« rc=5, Stats: {} ») ne désigne pas sa cause.
chown -R student:student /home/student

# Les journaux de l'installateur et les vieux gabarits debconf : ils ne servent
# qu'à diagnostiquer une installation qui vient de réussir.
rm -rf /var/log/installer /var/cache/debconf/*-old
find /var/log -type f -exec truncate -s 0 {} +

# Les anciens noyaux. Le cas arrive dès que Debian publie un noyau entre la
# gravure de l'ISO et le build : l'installateur pose le sien, le `full-upgrade`
# en ajoute un plus récent, et les deux restent. `apt-get autoremove` ci-dessus
# n'y change rien — il ne retire que les paquets marqués « automatiques », et
# l'installateur installe le noyau EXPLICITEMENT.
#
# Le build de la 0.3.0 est mort là-dessus, sur le garde-fou qui suit : il
# refusait au lieu de corriger, alors que le geste est mécanique. On garde le
# noyau le plus récent — celui qui bootera — et on purge les autres, y compris
# celui en cours d'exécution le cas échéant : il est en mémoire, et cette
# machine va s'éteindre.
garder="$(ls -1 /boot/vmlinuz-* | sed 's#.*/vmlinuz-##' | sort -V | tail -1)"
a_purger=()
while read -r paquet; do
  [ -n "$paquet" ] || continue
  [ "$paquet" = "linux-image-${garder}" ] && continue
  a_purger+=("$paquet")
done < <(dpkg-query -W -f='${Package}\n' 'linux-image-[0-9]*' 2>/dev/null || true)

if [ "${#a_purger[@]}" -gt 0 ]; then
  echo "noyau gardé : ${garder} — retirés : ${a_purger[*]}"
  apt-get -y purge "${a_purger[@]}"
  apt-get -y autoremove --purge
fi

# Le garde-fou, maintenant qu'il porte sur le RÉSULTAT et non sur l'intention :
# deux noyaux pèsent 170 Mio bruts, et une image lourde est ce que
# l'utilisateur télécharge.
test "$(ls /boot/vmlinuz-* | wc -l)" -eq 1 \
  || { echo "plus d'un noyau après nettoyage : $(ls /boot/vmlinuz-*)" >&2; exit 1; }

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
