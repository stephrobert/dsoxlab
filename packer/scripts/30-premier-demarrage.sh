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

# ── Dire où l'on en est, sur l'invite de connexion elle-même ─────────────────
#
# Le journal part sur /dev/console, désormais la fenêtre de la VM. Cela ne suffit
# pas : `getty` affiche son invite par-dessus, et un utilisateur qui se connecte
# ne voit plus rien défiler. Il croit alors que rien ne tourne — mesuré, remonté
# en ces termes : « je ne vois pas que la phase d'installation tourne, on voit un
# login ».
#
# `/etc/issue` est relu par getty à CHAQUE invite : une touche Entrée suffit donc
# à voir l'étape en cours, sans rien savoir de systemd ni de journalctl.
annoncer() {
  # 1. Le journal et la console série, par la sortie standard du service.
  echo "$1"

  # 2. L'invite de connexion, relue par getty à CHAQUE invite.
  {
    printf '\n  dsoxlab : première configuration EN COURS\n'
    printf '  %s\n\n' "$1"
    printf '  La suivre en direct :  journalctl -u dsoxlab-premier-demarrage -f\n'
    printf "  La machine redémarrera d'elle-même quand ce sera terminé.\n\n"
  } > /etc/issue

  # 3. La FENÊTRE de la machine virtuelle, explicitement. Elle ne reçoit plus
  #    /dev/console, rendu à la série pour que la CI et le diagnostic à distance
  #    gardent tout le journal. Écrire ici est donc le seul moyen de parler à qui
  #    regarde l'écran — et `|| true`, parce qu'un tty1 absent (machine sans
  #    console graphique) ne doit pas faire échouer la configuration.
  { printf '  dsoxlab : %s\n' "$1" > /dev/tty1; } 2>/dev/null || true
}

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
# Les deux destinations dont CETTE configuration dépend, et rien d'autre :
# Debian pour les paquets, PyPI pour dsoxlab. Les nommer ici évite le piège
# d'attendre un nom que les étapes n'utilisent pas.
DESTINATIONS="deb.debian.org pypi.org"

joignable() {
  # Une RÉSOLUTION, puis une CONNEXION. La première ne prouve pas la seconde :
  # un résolveur local peut répondre avant que la route par défaut existe, et
  # c'est exactement ce qui faisait passer l'ancien contrôle pour vert alors
  # que l'installation suivante échouait.
  getent hosts "$1" >/dev/null 2>&1 || return 1
  # `bash` sait ouvrir une socket sans aucun outil réseau installé ; le délai
  # borne l'attente d'un hôte qui ne répond pas du tout.
  timeout 5 bash -c "exec 3<>/dev/tcp/$1/443" 2>/dev/null
}

attendre_la_resolution() {
  local restants=60          # 60 × 2 s = deux minutes, large pour un DHCP
  local manquantes
  while [ "$restants" -gt 0 ]; do
    manquantes=""
    for hote in $DESTINATIONS; do
      joignable "$hote" || manquantes="$manquantes $hote"
    done
    if [ -z "$manquantes" ]; then
      echo "Réseau prêt :$(printf ' %s' $DESTINATIONS) répondent en HTTPS."
      return 0
    fi
    restants=$((restants - 1))
    sleep 2
  done
  # Nommer CE QUI manque : « PyPI injoignable » et « miroir Debian
  # injoignable » n'appellent pas le même geste.
  echo "Injoignable après deux minutes :$manquantes" >&2
  return 1
}

# ── Dire pourquoi, là où l'utilisateur regarde ───────────────────────────────
#
# Chaque étape écrit sa sortie dans un fichier à elle. Le journal la reçoit
# toujours ; la FENÊTRE ne reçoit que ce qui compte, et seulement en cas
# d'échec. C'est la différence entre « configuration INCOMPLÈTE — bureau » et
# « apt n'a pas trouvé xfce4 parce que l'index est vide ».
TRACES=/var/log/dsoxlab
install -d -m 0755 "$TRACES"

# Nomme la cause quand le motif est reconnaissable, et se tait sinon. Même
# principe que `explique_echec_provision` dans `services/doctor.py` : la sortie
# brute d'un outil n'est pas un diagnostic, et une cause inventée serait pire
# que pas de cause du tout.
cause_probable() {
  local trace=$1
  if grep -qiE 'unable to locate package|has no installation candidate' "$trace"; then
    printf "l'index des paquets est vide ou périmé"
  elif grep -qiE 'temporary failure resolving|could not resolve' "$trace"; then
    printf "cette machine n'a pas de résolution DNS"
  elif grep -qiE 'failed to fetch|unable to connect|connection (failed|timed out)' "$trace"; then
    printf "le miroir Debian est injoignable depuis cette machine"
  elif grep -qiE 'no space left on device' "$trace"; then
    printf "le disque est plein"
  elif grep -qiE 'could not get lock|frontend lock' "$trace"; then
    printf "une autre installation tient le verrou d'apt"
  elif grep -qiE 'unmet dependencies|broken packages|dpkg: error' "$trace"; then
    printf "un conflit entre paquets"
  fi
}

# Joue une étape. En cas d'échec, dit CE QUI a échoué et POURQUOI, sur la
# fenêtre de la machine autant que dans le journal.
etape() {
  local cle=$1; shift
  local trace="$TRACES/${cle}.log"
  local code=0
  "$@" > "$trace" 2>&1 || code=$?

  # Le journal reçoit tout, succès ou échec : c'est lui qu'on relit à froid.
  cat "$trace"
  [ "$code" = 0 ] && return 0

  local cause lignes rapport
  cause=$(cause_probable "$trace")
  # Les trois lignes qui disent quelque chose, pas les quatre cents d'apt.
  lignes=$(grep -E '^(E:|Err:|W: Failed|dpkg: error)' "$trace" | tail -3)
  if [ -z "$lignes" ]; then
    lignes=$(grep -vE '^(Get:|Hit:|Ign:|Reading|Building|Preparing|Unpacking|Setting up|Selecting|\(Reading)' \
             "$trace" | grep -v '^$' | tail -3)
  fi

  rapport=$(
    printf '\n  ╭─ l%sétape « %s » a échoué (code %s)\n' "'" "$cle" "$code"
    [ -n "$cause" ] && printf '  │\n  │  Cause probable : %s.\n' "$cause"
    printf '  │\n  │  Ce que dit la commande :\n'
    printf '%s\n' "$lignes" | sed 's/^/  │      /'
    printf '  │\n  ╰─ trace complète : %s\n\n' "$trace"
  )
  # Le journal et la console série…
  printf '%s\n' "$rapport"
  # …et la FENÊTRE, qui ne reçoit rien d'autre. C'est tout l'objet du correctif.
  { printf '%s\n' "$rapport" > /dev/tty1; } 2>/dev/null || true
  return "$code"
}

annoncer "Étape 1 sur 5 : attente du réseau…"
if ! attendre_la_resolution; then
  echo "ÉCHEC : le réseau n'est pas utilisable après deux minutes." >&2
  echo "Rien n'a été installé, et RIEN N'EST PERDU : cette configuration" >&2
  echo "recommencera au prochain démarrage. Vérifiez la carte réseau de la" >&2
  echo "machine virtuelle, puis redémarrez-la." >&2
  exit 1
fi

# ── 1. dsoxlab, dans sa dernière version publiée ─────────────────────────────
# ── L'index des paquets, AVANT toute installation ────────────────────────────
#
# `90-nettoyage.sh` retire `/var/lib/apt/lists/*` de l'image : c'est ce qui la
# rend légère, et c'est délibéré. Mais une image sans index n'installe plus
# rien tant qu'il n'est pas reconstruit.
#
# Cet `apt-get update` vivait DANS la branche `if [ -e /dev/kvm ]`, ce qui l'a
# rendu invisible pendant tout le développement : sur une machine qui a la
# virtualisation imbriquée, il était joué et le bureau s'installait. Sur une
# machine sans — VirtualBox par défaut, donc le cas le plus courant chez un
# apprenant — il ne l'était pas, et l'étape du bureau cherchait `xfce4` dans un
# index vide. Elle échouait à chaque démarrage, en répétant le même message.
# Remonté depuis une VM VirtualBox réelle, pas trouvé en relisant du code.
annoncer "Étape 2 sur 5 : mise à jour de l'index des paquets…"
if etape index-des-paquets apt-get update; then
  echo "Index des paquets reconstruit."
else
  echo "Sans index, ni les hyperviseurs ni le bureau ne peuvent s'installer." >&2
  echec="$echec index-des-paquets"
fi

annoncer "Étape 3 sur 5 : installation de dsoxlab…"
if ! etape dsoxlab sudo -u student -H bash -lc 'uv tool install --force dsoxlab'; then
  echec="$echec dsoxlab"
fi

annoncer "Étape 4 sur 5 : installation des hyperviseurs…"

# ── 2. Les hyperviseurs, seulement s'ils peuvent servir ──────────────────────
#
# Sans /dev/kvm, les installer ne servirait à rien : les labs `vm` ne peuvent pas
# tourner, et `dsoxlab doctor` dit que l'imbrication s'active sur l'hyperviseur
# HÔTE, cette machine éteinte. Ce n'est donc PAS un échec : c'est un cas prévu,
# et le marqueur se pose quand même.
if [ -e /dev/kvm ]; then
  echo "Virtualisation imbriquée disponible : installation de KVM et d'Incus…"
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
  if etape hyperviseurs apt-get install -y --no-install-recommends \
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
# Le choix de l'assistant, s'il a été fait. `DSOXLAB_APPLIANCE_DESKTOP` dans
# l'environnement reste prioritaire : c'est ce qui permet de construire une
# image sans bureau sans toucher à l'assistant.
if [ -z "${DSOXLAB_APPLIANCE_DESKTOP:-}" ] && [ -r /etc/dsoxlab/appliance.conf ]; then
  # shellcheck source=/dev/null
  . /etc/dsoxlab/appliance.conf
fi

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
  annoncer "Étape 5 sur 5 : installation du bureau XFCE et de Firefox…"
  if etape bureau apt-get install -y --no-install-recommends \
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
    echec="$echec bureau"
  fi
else
  # Le dire, plutôt que de sauter l'étape en silence : sans cette ligne,
  # quelqu'un qui a répondu « non » sans s'en souvenir chercherait pourquoi sa
  # machine démarre en console.
  annoncer "Bureau non installé : vous l'avez refusé au premier démarrage."
  echo "Pour l'installer plus tard : sudo apt install xfce4 lightdm firefox-esr"
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

  # La cause de CHAQUE étape a déjà été affichée par `etape`, juste au-dessus et
  # dans la fenêtre. Ce bilan dit donc autre chose : ce qui a échoué, ce que la
  # machine sait encore faire, et le geste à poser. Trois choses que l'ancien
  # message ne disait pas — « configuration INCOMPLÈTE — bureau — elle
  # recommencera » laissait l'utilisateur sans savoir s'il devait agir.
  bilan=$(
    printf '\n  ╭─ dsoxlab : la configuration est INCOMPLÈTE\n'
    printf '  │\n'
    for quoi in $echec; do
      case "$quoi" in
        index-des-paquets) printf '  │  ✘ %-18s rien ne peut s%sinstaller sans lui\n' "$quoi" "'" ;;
        dsoxlab)           printf '  │  ✘ %-18s la commande « dsoxlab » est absente\n' "$quoi" ;;
        hyperviseurs)      printf '  │  ✘ %-18s les labs « vm » ne pourront pas tourner\n' "$quoi" ;;
        bureau)            printf '  │  ✘ %-18s la machine démarre en console, sans XFCE\n' "$quoi" ;;
        *)                 printf '  │  ✘ %s\n' "$quoi" ;;
      esac
    done
    printf '  │\n'
    printf '  │  La cause de chacune est affichée au-dessus, et conservée dans\n'
    printf '  │  /var/log/dsoxlab/<étape>.log\n'
    printf '  │\n'
    printf '  │  CE QU%sIL FAUT FAIRE\n' "'"
    printf '  │    1. régler la cause ci-dessus (le plus souvent : le réseau de la VM)\n'
    printf '  │    2. sudo reboot\n'
    printf '  │\n'
    printf '  │  La configuration RECOMMENCE à chaque démarrage tant qu%selle n%sa\n' "'" "'"
    printf '  │  pas abouti. Rien n%sest perdu, rien n%sest à réinstaller.\n' "'" "'"
    printf '  │\n'
    printf '  ╰─ tout le journal : journalctl -u dsoxlab-premier-demarrage --no-pager\n\n'
  )

  # Le journal et la console série.
  printf '%s\n' "$bilan" >&2
  # La FENÊTRE : c'est là que l'utilisateur regarde, et c'est là qu'il ne voyait
  # qu'une ligne.
  { printf '%s\n' "$bilan" > /dev/tty1; } 2>/dev/null || true
  # L'invite de connexion, relue par getty : sans elle, l'utilisateur qui se
  # connecte plus tard voit une invite ordinaire et croit la machine prête.
  printf '%s\n' "$bilan" > /etc/issue

  exit 1
fi

# Réussi : l'invite redevient celle de Debian, sans trace de chantier.
printf 'Debian GNU/Linux 13 \\n \\l\n\n' > /etc/issue

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
# dépôt. Son changement est demandé par l'ASSISTANT de premier démarrage
# (`25-assistant.sh`), en console, avant que LightDM existe.
#
# Il était forcé ici par `chage -d 0`, et c'était un défaut : en console PAM
# mène le dialogue correctement, mais le greeter de LightDM annonce
# « Changing password for student » puis échoue. L'appliance avec bureau était
# donc impossible à ouvrir à la première connexion — remonté d'une VirtualBox
# réelle, après que l'image a été publiée.
#
# `chage -d 0` est posé quand même ici, pour la fenêtre entre la fin de la
# fabrication et le premier démarrage : si quelqu'un démarre l'image avec
# `dsoxlab.oobe=0`, l'assistant est sauté et le mot de passe public ne doit pas
# rester silencieusement valable. L'assistant lève cette expiration dès qu'il
# s'exécute, qu'il ait obtenu une réponse ou non.
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
