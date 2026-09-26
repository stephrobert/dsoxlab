#!/usr/bin/env bash
# Ce qui se passe au PREMIER démarrage chez l'utilisateur, et pas à la
# construction. Trois choses ne peuvent pas être figées dans une image :
#
#   1. la version de dsoxlab, qui serait périmée dès le correctif suivant ;
#   2. les hyperviseurs, qui n'ont de sens que si l'hôte expose la virtualisation
#      imbriquée. On ne le sait qu'à l'exécution, jamais à la construction : c'est
#      la leçon de l'issue #91, et `doctor` sait désormais le dire ;
#   3. le bureau, qui pèse près d'un gigaoctet et que tout le monde ne veut pas.
#      L'installer ici ne coûte RIEN dans l'artefact distribué.
#
# À la fin de ce premier démarrage, la machine est prête à jouer un lab `vm` :
# daemons actifs, groupes en place, pool de stockage défini, clé d'instructeur
# générée si un catalogue est déjà là. Le redémarrage final n'est pas une
# précaution de style — il est nécessaire pour que l'appartenance aux groupes
# prenne effet et pour arriver sur le bureau.
set -euo pipefail

install -m 0755 /dev/stdin /usr/local/sbin/dsoxlab-premier-demarrage <<'SCRIPT'
#!/usr/bin/env bash
# Rien ici ne doit pouvoir empêcher la machine de démarrer : chaque étape qui
# dépend du réseau ou du matériel échoue en le disant, et le boot continue. Une
# appliance qui refuse de démarrer parce qu'un miroir est muet serait pire
# qu'une appliance incomplète.
#
# Mais une appliance incomplète qui se CROIT complète est pire que les deux.
# Mesuré dans VirtualBox : sans réseau, les trois étapes échouaient, le marqueur
# était posé quand même, et la machine n'avait plus aucun moyen de se rattraper
# — ni dsoxlab, ni hyperviseur, ni bureau, définitivement. D'où la règle tenue
# plus bas : LE MARQUEUR NE SE POSE QUE SI TOUT CE QUI ÉTAIT APPLICABLE A RÉUSSI.
# Sinon le service sort en échec, le dit, et recommence au prochain démarrage.
set -uo pipefail
marque=/var/lib/dsoxlab-premier-demarrage.fait
[ -e "$marque" ] && exit 0

export DEBIAN_FRONTEND=noninteractive
echec=""
echo "=== Première configuration de l'appliance dsoxlab ==="

# ── 0. Attendre que le réseau réponde VRAIMENT ───────────────────────────────
#
# `After=network-online.target` ne suffisait pas : sur cette image la cible est
# atteinte sans qu'aucun bail DHCP soit pris. Le symptôme était un `uv tool
# install` qui échouait en huit secondes sur « Temporary failure in name
# resolution », suivi de deux autres échecs en cascade.
#
# On ne teste pas l'interface ni la route, qui peuvent être là sans servir : on
# teste ce dont les étapes suivantes ont besoin, c'est-à-dire résoudre un nom.
attendre_la_resolution() {
  local restants=60          # 60 × 2 s = deux minutes, large pour un DHCP
  while [ "$restants" -gt 0 ]; do
    if getent hosts deb.debian.org >/dev/null 2>&1; then
      return 0
    fi
    restants=$((restants - 1))
    sleep 2
  done
  return 1
}

echo "Attente du réseau…"
if ! attendre_la_resolution; then
  echo "ÉCHEC : aucun nom ne se résout après deux minutes d'attente." >&2
  echo "Rien n'a été installé, et RIEN N'EST PERDU : cette configuration" >&2
  echo "recommencera au prochain démarrage. Vérifiez la carte réseau de la" >&2
  echo "machine virtuelle, puis redémarrez-la." >&2
  exit 1
fi

# ── 1. dsoxlab, dans sa dernière version publiée ─────────────────────────────
echo "Installation de dsoxlab (dernière version publiée)…"
if ! sudo -u student -H bash -lc 'uv tool install --force dsoxlab'; then
  echo "ÉCHEC : « uv tool install dsoxlab » n'a pas abouti." >&2
  echec="$echec dsoxlab"
fi

# ── 2. Les hyperviseurs, seulement s'ils peuvent servir ──────────────────────
#
# Sans /dev/kvm, les installer ne servirait à rien : les labs `vm` ne peuvent pas
# tourner, et `dsoxlab doctor` dit que l'imbrication s'active sur l'hyperviseur
# HÔTE, cette machine éteinte. Ce n'est donc PAS un échec : c'est un cas prévu,
# et le marqueur se pose quand même.
if [ -e /dev/kvm ]; then
  echo "Virtualisation imbriquée disponible : installation de KVM et d'Incus…"
  apt-get update -qq || true
  # `ovmf` est nommé explicitement, et ce n'est pas du zèle : sur Debian il n'est
  # qu'une RECOMMANDATION de qemu-kvm, donc `--no-install-recommends` l'écarte.
  # Sans lui, libvirt n'expose aucun firmware EFI et tout `provision` s'arrête net
  # — mesuré dans l'appliance, où dsoxlab a nommé la cause en 2,3 secondes grâce
  # au garde-fou de l'issue #234. Le message était juste ; c'est la recette qui
  # avait tort.
  # `qemu-utils` fournit `qemu-img`, sans lequel libvirt refuse de créer un volume
  # qcow2 : « creation of non-raw file images is not supported without qemu-img ».
  # Comme `ovmf`, ce n'est qu'une recommandation sur Debian, donc écartée par
  # `--no-install-recommends`. Les deux ont été trouvés en provisionnant pour de
  # vrai depuis l'appliance, pas en relisant la liste.
  if apt-get install -y --no-install-recommends \
      qemu-kvm qemu-utils ovmf libvirt-daemon-system libvirt-clients virtinst \
      incus; then

    # Les paquets Debian activent leurs propres services, mais pas dans la session
    # qui vient de les installer : `doctor` répondait alors « virsh présent mais
    # erreur (daemon arrêté ?) ». Mesuré dans l'appliance : après le redémarrage de
    # fin de script, `libvirtd` et `incus.socket` sont actifs d'eux-mêmes. Ces
    # `enable --now` ne servent donc qu'à rendre la machine utilisable AVANT ce
    # redémarrage, et à ne pas dépendre d'un choix de paquet qui pourrait changer.
    systemctl enable --now libvirtd.socket libvirtd 2>/dev/null || \
      systemctl enable --now libvirtd 2>/dev/null || true
    systemctl enable --now virtlogd.socket 2>/dev/null || true
    systemctl enable --now incus.socket 2>/dev/null || true

    # Les groupes : sans eux, `student` ne peut ni ouvrir /dev/kvm ni parler au
    # daemon. C'est aussi la raison du redémarrage final, une appartenance de
    # groupe ne prenant effet qu'à la session suivante.
    for groupe in kvm libvirt incus-admin; do
      getent group "$groupe" >/dev/null && adduser student "$groupe" >/dev/null || true
    done

    # Le pool de stockage `default` : `dsoxlab doctor` le contrôle en REQUIS dès
    # qu'un catalogue déclare des hôtes, et une Debian fraîche n'en définit aucun.
    # Les quatre étapes comptent : `pool-define-as` seul laisse un pool défini mais
    # ni construit ni démarré.
    if virsh -c qemu:///system pool-info default >/dev/null 2>&1; then
      virsh -c qemu:///system pool-start default 2>/dev/null || true
    else
      virsh -c qemu:///system pool-define-as default dir \
        --target /var/lib/libvirt/images >/dev/null 2>&1 \
        && virsh -c qemu:///system pool-build default >/dev/null 2>&1 \
        && virsh -c qemu:///system pool-start default >/dev/null 2>&1 \
        && virsh -c qemu:///system pool-autostart default >/dev/null 2>&1 \
        && echo "Pool libvirt « default » défini, construit et démarré." || true
    fi

    # Incus a besoin d'être initialisé une fois, sinon son daemon tourne sans
    # aucun pool et `provision` échoue sur « no storage pool found ».
    if ! incus storage list >/dev/null 2>&1 || [ -z "$(incus storage list -f csv 2>/dev/null)" ]; then
      incus admin init --minimal >/dev/null 2>&1 \
        && echo "Incus initialisé (profil minimal)." || true
    fi
  else
    echo "ÉCHEC : les hyperviseurs n'ont pas pu être installés." >&2
    echec="$echec hyperviseurs"
  fi
else
  echo "Pas de /dev/kvm : les labs « shell » fonctionnent, les labs « vm » non."
  echo "La virtualisation imbriquée s'active sur l'hyperviseur HÔTE, cette"
  echo "machine éteinte. « dsoxlab doctor » le redira au besoin."
fi

# ── 3. Le bureau ─────────────────────────────────────────────────────────────
#
# XFCE plutôt que GNOME : environ 700 Mio contre deux à trois gigaoctets, pour
# un usage qui reste un terminal et un navigateur. Le navigateur n'est pas un
# luxe : `dsoxlab guide` ouvre le guide en ligne du lab, et sans lui il faut
# passer par `--print`.
#
# Rien de tout cela ne pèse dans l'image distribuée : c'est téléchargé ici.
if [ "${DSOXLAB_APPLIANCE_DESKTOP:-1}" = "1" ]; then
  # Le serveur X est nommé explicitement, et c'est la TROISIÈME fois que ce
  # motif mord : comme `ovmf` et `qemu-utils`, `xserver-xorg` n'est qu'une
  # RECOMMANDATION de `xfce4` et de `lightdm`, jamais une dépendance. Avec
  # `--no-install-recommends`, le bureau s'installait donc sans serveur
  # graphique. Mesuré dans VirtualBox : `/usr/bin/Xorg` absent, `lightdm`
  # « failed », et la machine arrivait sur une console malgré
  # `graphical.target` — un symptôme que rien ne relie à un paquet manquant.
  #
  # Les pilotes vidéo se nomment aussi : `vmware` sert le contrôleur VMSVGA que
  # VirtualBox et VMware présentent par défaut, `vesa` et `fbdev` rattrapent
  # tout le reste. Une appliance ne sait pas sur quel hyperviseur elle tombera.
  echo "Installation du bureau XFCE et de Firefox…"
  if apt-get install -y --no-install-recommends \
      xserver-xorg-core xserver-xorg-input-libinput \
      xserver-xorg-video-vmware xserver-xorg-video-vesa \
      xserver-xorg-video-fbdev xfonts-base x11-xserver-utils \
      xfce4 xfce4-terminal lightdm lightdm-gtk-greeter \
      firefox-esr dbus-x11 xdg-utils fonts-dejavu; then
    # Sans cette cible, la machine redémarrerait sur une console : les paquets
    # installés ne suffisent pas à obtenir un bureau.
    systemctl set-default graphical.target
    systemctl enable lightdm
    echo "Bureau installé, la machine démarrera dessus."
  else
    echo "ÉCHEC : le bureau n'a pas pu être installé." >&2
    echec="$echec bureau"
  fi
fi

# ── 4. Le fragment SSH que dsoxlab écrit doit être lu ────────────────────────
#
# `provision` dépose un `~/.ssh/config.d/<catalogue>.conf` pour que `ssh <machine>`
# fonctionne, et il AVERTIT lui-même quand `~/.ssh/config` ne l'inclut pas :
# « ajoutez cette ligne en tête de fichier, sinon il ne sera jamais lu ». Mesuré
# dans l'appliance : l'avertissement tombait à chaque provisionnement.
#
# L'`Include` doit être en TÊTE du fichier : OpenSSH applique la première
# directive rencontrée pour un hôte donné, donc un Include placé après un bloc
# `Host *` serait sans effet sur ce que ce bloc a déjà décidé.
install -d -m 0700 -o student -g student /home/student/.ssh
if ! grep -qs 'Include ~/.ssh/config.d/\*.conf' /home/student/.ssh/config; then
  { echo 'Include ~/.ssh/config.d/*.conf'
    echo
    [ -f /home/student/.ssh/config ] && cat /home/student/.ssh/config
  } > /home/student/.ssh/config.nouveau
  mv /home/student/.ssh/config.nouveau /home/student/.ssh/config
  chown student:student /home/student/.ssh/config
  chmod 0600 /home/student/.ssh/config
  echo "« Include ~/.ssh/config.d/*.conf » ajouté en tête de ~/.ssh/config."
fi

# ── 5. Conclure : réussi, ou à refaire ───────────────────────────────────────
#
# Le marqueur est la SEULE chose qui empêche de recommencer. Le poser sur un
# échec condamne la machine en silence : c'est ce qui s'est produit dans
# VirtualBox, où l'utilisateur se serait retrouvé avec une console nue, sans
# dsoxlab, sans rien qui explique pourquoi ni comment rattraper.
if [ -n "$echec" ]; then
  echo "=== Configuration INCOMPLÈTE :$echec ===" >&2
  echo "Ces étapes recommenceront au prochain démarrage. Vérifiez l'accès" >&2
  echo "réseau de la machine virtuelle, puis redémarrez-la." >&2
  exit 1
fi

touch "$marque"

# ── 6. Le redémarrage, et pourquoi il est nécessaire ─────────────────────────
#
# Deux raisons, aucune cosmétique : l'appartenance aux groupes `kvm`, `libvirt`
# et `incus-admin` ne prend effet qu'à la session suivante, et la cible
# graphique ne s'applique qu'au prochain démarrage. Sans ce reboot, l'utilisateur
# aurait une machine où `dsoxlab provision` échoue sur un droit et où le bureau
# installé ne s'affiche pas — deux symptômes qu'il ne pourrait pas relier.
echo "=== Configuration terminée, redémarrage pour l'appliquer ==="
systemctl reboot
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
# La console autant que le journal : c'est ce qui permet de suivre ce premier
# démarrage depuis l'extérieur, par la console série, sans écran.
StandardOutput=journal+console
StandardError=journal+console
# Généreux à dessein : cette étape télécharge dsoxlab, les hyperviseurs et le
# bureau. Un délai trop court laisserait une machine à moitié configurée.
TimeoutStartSec=45min

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

  dsoxlab demo                un premier lab, sans rien cloner
  dsoxlab doctor              ce que cette machine peut faire, et ce qui manque
  dsoxlab catalog add <url>   installer un catalogue de labs
  dsoxlab start <lab>         jouer un lab de bout en bout

  Les labs « vm » demandent la virtualisation imbriquée, qui s'active sur
  l'hyperviseur hôte, cette machine éteinte. « dsoxlab doctor » le dit.

MOTD
