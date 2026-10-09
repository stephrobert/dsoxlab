#!/usr/bin/env bash
# Base du système. Rien de spécifique à dsoxlab ici : ce que tout poste de lab
# demande, et rien de plus, pour que l'image reste petite.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# Ce qui ne sera JAMAIS installé, avant toute installation. Mesuré : la
# documentation pèse 38 Mio bruts (21 compressés) et les locales 92 Mio dont 6
# utiles (26 compressés). La politique Debian interdit toute dépendance sur
# /usr/share/doc, donc rien ne casse à l'exécution.
#
# `man` est délibérément CONSERVÉ : le retirer rapporterait 9 Mio et priverait un
# apprenant Linux de `man ls`, ce qui serait absurde pour une formation Linux.
cat > /etc/dpkg/dpkg.cfg.d/01-appliance <<'EOF'
path-exclude=/usr/share/doc/*
path-include=/usr/share/doc/*/copyright
path-exclude=/usr/share/info/*
path-exclude=/usr/share/lintian/*
path-exclude=/usr/share/locale/*
path-include=/usr/share/locale/locale.alias
path-include=/usr/share/locale/en*
path-include=/usr/share/locale/fr*
EOF

# La règle ci-dessus ne vaut que pour les installations à venir : ce que
# l'installateur a déjà posé se retire une fois, ici.
find /usr/share/doc -mindepth 2 -type f ! -name copyright -delete
find /usr/share/doc -mindepth 1 -type d -empty -delete
rm -rf /usr/share/info/* /usr/share/lintian/*
find /usr/share/locale -mindepth 1 -maxdepth 1 -type d \
  ! -name 'en*' ! -name 'fr*' -exec rm -rf {} +

apt-get update -qq
apt-get install -y --no-install-recommends \
  ca-certificates curl git gnupg jq less openssh-client python3 python3-venv \
  qemu-guest-agent sudo unzip vim

# Ce que la tâche `standard` apportait et qu'un apprenant attend vraiment :
# nommé un par un plutôt que par une tâche de 248 Mio. 19 Mio bruts mesurés.
apt-get install -y --no-install-recommends \
  bash-completion bind9-dnsutils bzip2 file lsof man-db manpages traceroute \
  wget xz-utils

# L'agent qemu permet à l'hyperviseur hôte de remonter l'adresse de la VM. Il ne
# coûte rien quand personne ne l'interroge, et il évite à l'utilisateur de
# chercher son IP dans la console.
systemctl enable qemu-guest-agent

# Une console série, sans quoi l'appliance n'est diagnosticable qu'avec un écran.
# Mesuré en la démarrant : la console était vide, 0 octet, alors que la VM
# tournait. Ni la CI, ni un formateur à distance, ni l'utilisateur au téléphone ne
# pouvait voir le premier démarrage — donc ni savoir si dsoxlab s'installait, ni
# pourquoi lorsqu'il échouait.
#
# L'ORDRE COMPTE, ET IL ÉTAIT À L'ENVERS. Le noyau écrit ses messages sur TOUTES
# les consoles déclarées, mais `/dev/console` — celle où écrit l'espace
# utilisateur — est la DERNIÈRE de la liste. Avec `console=tty0` puis
# `console=ttyS0`, la première configuration envoyait donc tout son journal sur
# le port série, et la fenêtre de la VM n'affichait qu'une invite de connexion.
#
# Mesuré sur l'appliance 0.3.1, par un utilisateur : « je ne vois pas que la
# phase d'installation tourne, on voit un login ». Elle tournait, et son service
# porte bien `StandardOutput=journal+console` : c'est `/dev/console` qui n'était
# pas là où il regardait.
#
# La série vient donc en premier, `tty0` en dernier : la fenêtre reçoit
# `/dev/console`, et la série garde les messages du noyau pour la CI, pour un
# formateur à distance et pour qui diagnostique sans écran.
sed -i 's/^GRUB_CMDLINE_LINUX=.*/GRUB_CMDLINE_LINUX="console=ttyS0,115200n8 console=tty0"/' \
  /etc/default/grub
grep -q '^GRUB_TERMINAL' /etc/default/grub \
  || echo 'GRUB_TERMINAL="console serial"' >> /etc/default/grub
grep -q '^GRUB_SERIAL_COMMAND' /etc/default/grub \
  || echo 'GRUB_SERIAL_COMMAND="serial --speed=115200"' >> /etc/default/grub
update-grub

# Un shell sur la série : le noyau qui parle ne suffit pas, il faut pouvoir
# répondre. C'est ce qui permettra au workflow de vérifier le premier démarrage.
systemctl enable serial-getty@ttyS0.service

# Le générateur ssh de systemd cherche un canal AF_VSOCK que ni VirtualBox ni
# VMware n'exposent, et il échoue bruyamment : « Failed to query local AF_VSOCK
# CID: Cannot assign requested address », une ligne par rechargement de systemd.
# Mesuré au premier démarrage dans VirtualBox : une dizaine de lignes rouges en
# cinq secondes, parce que chaque paquet installé provoque un daemon-reload.
# Sur une appliance destinée à des débutants, un écran d'erreurs donne à croire
# que tout est cassé alors que rien ne l'est. Le lien vers /dev/null est la
# façon documentée de neutraliser un générateur.
mkdir -p /etc/systemd/system-generators
ln -sf /dev/null /etc/systemd/system-generators/systemd-ssh-generator

# Le journal ne doit pas grossir sans fin dans une image qu'on ne surveille pas.
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/appliance.conf <<'CONF'
[Journal]
SystemMaxUse=200M
CONF
