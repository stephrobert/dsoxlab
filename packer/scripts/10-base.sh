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

# ── Le clavier, écrit ici et non espéré du preseed ───────────────────────────
#
# La 0.3.2 confiait la disposition au preseed seul. Mesuré dans l'image publiée :
# `XKBLAYOUT="us"`. Le preseed garde sa ligne — c'est la bonne façon de le
# demander à l'installateur — mais ce qui FAIT la disposition est ici, après
# l'installation, où le résultat se lit dans l'image à froid.
#
# Les trois endroits doivent dire la même chose, sinon la première
# reconfiguration contredit les deux autres :
#   - /etc/default/keyboard, lu par console-setup ET par X11 (donc XFCE) ;
#   - debconf, pour qu'un `dpkg-reconfigure` ne revienne pas en arrière ;
#   - la console courante, par setupcon.
cat > /etc/default/keyboard <<'CLAVIER'
# AZERTY français : la formation est francophone. Changer de disposition :
#   sudo dpkg-reconfigure keyboard-configuration && sudo setupcon
XKBMODEL="pc105"
XKBLAYOUT="fr"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
CLAVIER

debconf-set-selections <<'DEBCONF'
keyboard-configuration keyboard-configuration/xkb-keymap select fr
keyboard-configuration keyboard-configuration/layoutcode string fr
keyboard-configuration keyboard-configuration/modelcode string pc105
DEBCONF

# `--save` écrit la configuration de la console sans exiger un terminal, ce qui
# est le cas ici : ce script tourne par SSH, sans console attachée.
setupcon --save-only 2>/dev/null || setupcon --save 2>/dev/null || true

# On ne suppose pas que ça a marché : on relit ce qu'on vient d'écrire. Un build
# qui livrerait un clavier anglais doit échouer ICI, pas chez l'utilisateur.
grep -q '^XKBLAYOUT="fr"' /etc/default/keyboard || {
  echo "ÉCHEC : /etc/default/keyboard ne porte pas XKBLAYOUT=fr" >&2
  exit 1
}
echo "clavier : $(grep '^XKBLAYOUT' /etc/default/keyboard)"

# Une console série, sans quoi l'appliance n'est diagnosticable qu'avec un écran.
# Mesuré en la démarrant : la console était vide, 0 octet, alors que la VM
# tournait. Ni la CI, ni un formateur à distance, ni l'utilisateur au téléphone ne
# pouvait voir le premier démarrage — donc ni savoir si dsoxlab s'installait, ni
# pourquoi lorsqu'il échouait.
#
# L'ORDRE COMPTE, ET LES DEUX ORDRES ONT UN DÉFAUT. Le noyau écrit ses messages
# sur TOUTES les consoles déclarées, mais `/dev/console` — celle où écrit
# l'espace utilisateur — est la DERNIÈRE de la liste.
#
# La série reste donc en dernier, et garde `/dev/console` : c'est elle qui porte
# TOUT le journal de la première configuration, pour la CI, pour un formateur à
# distance et pour qui diagnostique sans écran. La 0.3.2 avait inversé l'ordre
# pour rendre ce journal visible dans la fenêtre, et l'a rendu invisible sur la
# série — mesuré en démarrant l'image sous QEMU : la série ne portait plus que
# GRUB et l'invite de connexion. Un aveuglement échangé contre un autre.
#
# Ce que la fenêtre reçoit ne dépend donc plus de `/dev/console` : la première
# configuration écrit ses annonces d'étape directement sur `/dev/tty1`, et son
# étape courante dans `/etc/issue`. Les deux publics sont servis, chacun par un
# chemin qui lui est propre.
sed -i 's/^GRUB_CMDLINE_LINUX=.*/GRUB_CMDLINE_LINUX="console=tty0 console=ttyS0,115200n8"/' \
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
