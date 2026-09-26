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

# Le journal ne doit pas grossir sans fin dans une image qu'on ne surveille pas.
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/appliance.conf <<'CONF'
[Journal]
SystemMaxUse=200M
CONF
