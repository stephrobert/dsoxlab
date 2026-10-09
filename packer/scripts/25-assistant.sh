#!/usr/bin/env bash
# L'assistant du premier démarrage : il demande, il n'impose pas.
#
# POURQUOI CE FICHIER EXISTE
#
# L'appliance est livrée en AZERTY, parce que la formation est francophone. Mais
# « par défaut » n'est pas « pour tout le monde », et un apprenant belge, suisse,
# canadien ou anglophone n'a aucune raison de découvrir la commande
# `dpkg-reconfigure` avant son premier lab.
#
# L'idée vient de l'usage : « le top serait, au moment de démarrer, de choisir
# son clavier ». Un menu GRUB aurait pu le faire, mais il parle avant que le
# système existe et ne sait rien appliquer. Un assistant au premier démarrage,
# comme à l'installation d'un système, le fait au bon moment.
#
# TROIS CONTRAINTES, ET CHACUNE A SA RÉPONSE DANS CE FICHIER
#
# 1. Il doit parler AVANT l'invite de connexion, sinon personne ne le voit. D'où
#    `Before=` et `Conflicts=getty@tty1.service` : l'unité réclame la console, et
#    getty attend son tour.
#
# 2. Il ne doit JAMAIS bloquer un démarrage sans personne devant l'écran — la CI
#    de cette image, un serveur distant, une machine relancée la nuit. D'où un
#    `read -t`, un repli silencieux sur le défaut, et une sortie immédiate si la
#    ligne de commande du noyau porte `dsoxlab.oobe=0`.
#
# 3. Le menu doit être NUMÉROTÉ. Les chiffres sont au même endroit sur toutes
#    les dispositions : taper « 2 » fonctionne quel que soit le clavier que la
#    machine croit avoir. Demander de taper « belge » exigerait le clavier qu'on
#    est précisément en train de choisir.
set -euo pipefail

install -m 0755 /dev/stdin /usr/local/sbin/dsoxlab-assistant <<'SCRIPT'
#!/usr/bin/env bash
# Demande la disposition du clavier, le fuseau et la langue de l'interface.
# Tout défaut est celui de l'appliance : répondre n'est jamais obligatoire.
set -uo pipefail

marque=/var/lib/dsoxlab-assistant.fait
DELAI=${DSOXLAB_ASSISTANT_DELAI:-30}

# ── Les choix, et leur ordre ────────────────────────────────────────────────
#
# Le premier de chaque liste est le défaut : c'est lui que le silence choisit.
CLAVIERS=(
  "fr|Français (AZERTY)"
  "be|Belge"
  "ch|Suisse romand"
  "ca|Canadien français"
  "us|US (QWERTY)"
  "de|Allemand (QWERTZ)"
)
FUSEAUX=(
  "Europe/Paris|Paris, Bruxelles, Genève"
  "Europe/London|Londres"
  "America/Montreal|Montréal"
  "UTC|UTC"
)
LANGUES=(
  "fr|Français"
  "en|English"
)

demander() {
  # $1 = titre, $2... = entrées « valeur|libellé ». Écrit le choix sur stdout.
  local titre=$1; shift
  local entrees=("$@") i=1
  printf '\n  %s\n\n' "$titre" >&2
  for e in "${entrees[@]}"; do
    local marqueur="  "
    [ "$i" = 1 ] && marqueur=" *"
    printf '   %s %d) %s\n' "$marqueur" "$i" "${e#*|}" >&2
    i=$((i + 1))
  done
  printf '\n  Votre choix [1] (%d s) : ' "$DELAI" >&2

  local reponse=""
  read -r -t "$DELAI" reponse || true
  printf '\n' >&2
  # Tout ce qui n'est pas un numéro valide vaut le défaut : une faute de frappe
  # ne doit pas arrêter un premier démarrage.
  case "$reponse" in
    ''|*[!0-9]*) reponse=1 ;;
  esac
  [ "$reponse" -ge 1 ] 2>/dev/null && [ "$reponse" -le "${#entrees[@]}" ] || reponse=1
  local choisi=${entrees[$((reponse - 1))]}
  printf '%s' "${choisi%%|*}"
}

# ── Sortir sans rien faire quand il n'y a personne, ou qu'on l'a déjà fait ──
if [ -e "$marque" ]; then
  exit 0
fi
if grep -qw 'dsoxlab.oobe=0' /proc/cmdline 2>/dev/null; then
  echo "assistant désactivé par la ligne de commande du noyau"
  exit 0
fi

printf '\n'
printf '  ═══════════════════════════════════════════════════════════\n'
printf '    Bienvenue dans l%sappliance dsoxlab\n' "'"
printf '  ═══════════════════════════════════════════════════════════\n'
printf '\n  Trois questions, et vous pouvez les ignorer : sans réponse,\n'
printf '  les valeurs marquées d%sune étoile sont retenues.\n' "'"

clavier=$(demander "Disposition du clavier" "${CLAVIERS[@]}")
fuseau=$(demander "Fuseau horaire" "${FUSEAUX[@]}")
langue=$(demander "Langue de l'interface dsoxlab" "${LANGUES[@]}")

printf '\n  Retenu : clavier %s, fuseau %s, interface %s.\n\n' "$clavier" "$fuseau" "$langue"
# Le dialogue va à l'écran ; ce qui en RESTE va au journal, pour qui diagnostique
# plus tard une machine dont il n'a pas vu le premier démarrage.
logger -t dsoxlab-assistant "clavier=${clavier} fuseau=${fuseau} langue=${langue}" 2>/dev/null || true

# ── Appliquer, et dire ce qui a échoué ─────────────────────────────────────
#
# Les trois endroits doivent dire la même chose, sinon une reconfiguration
# ultérieure contredit les deux autres.
cat > /etc/default/keyboard <<CLAVIER
# Choisi au premier démarrage par l'assistant dsoxlab. Pour en changer :
#   sudo dpkg-reconfigure keyboard-configuration && sudo setupcon
XKBMODEL="pc105"
XKBLAYOUT="${clavier}"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
CLAVIER

printf 'keyboard-configuration keyboard-configuration/xkb-keymap select %s\n' "$clavier" \
  | debconf-set-selections 2>/dev/null || true
setupcon --save-only 2>/dev/null || setupcon --save 2>/dev/null || true
loadkeys "$clavier" 2>/dev/null || true

timedatectl set-timezone "$fuseau" 2>/dev/null || true

# La langue de l'interface est une variable d'environnement : elle vit dans le
# profil de l'apprenant, pas dans une configuration système.
if [ -d /home/student ]; then
  sed -i '/^export DSOXLAB_LANG=/d' /home/student/.profile 2>/dev/null || true
  printf 'export DSOXLAB_LANG=%s\n' "$langue" >> /home/student/.profile
  chown student:student /home/student/.profile 2>/dev/null || true
fi

install -d -m 0755 /var/lib
: > "$marque"
printf '  Vous pouvez vous connecter. La configuration se poursuit en arrière-plan.\n\n'
SCRIPT

# ── L'unité, et son dialogue avec getty ─────────────────────────────────────
#
# `Conflicts=getty@tty1.service` arrête l'invite de connexion le temps de
# l'assistant, et systemd la relance ensuite. Sans cela, les deux écriraient sur
# la même console et l'utilisateur verrait un dialogue haché par un « login: ».
cat > /etc/systemd/system/dsoxlab-assistant.service <<'UNIT'
[Unit]
Description=Assistant de premier démarrage de l'appliance dsoxlab
# Avant la première configuration : elle télécharge 1,5 Go, et l'apprenant doit
# pouvoir répondre avant, puis regarder l'installation avec son clavier.
Before=dsoxlab-premier-demarrage.service getty@tty1.service
Conflicts=getty@tty1.service
After=systemd-user-sessions.service
ConditionPathExists=!/var/lib/dsoxlab-assistant.fait
ConditionKernelCommandLine=!dsoxlab.oobe=0

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/dsoxlab-assistant
# La console de la machine, et elle seule : un assistant qui pose une question
# sur le port série ne serait vu par personne devant l'écran.
StandardInput=tty-force
# LES DEUX sorties vont à l'écran, et c'est le défaut que le premier essai
# local a montré : le menu est écrit sur `stderr` — pour que `stdout` ne porte
# que la valeur de retour de la fonction — et `journal+console` l'envoyait sur
# la console série. L'utilisateur voyait « Bienvenue, trois questions » puis
# plus rien, et devait répondre à l'aveugle. Pire que pas d'assistant du tout.
#
# Le journal ne perd rien : le script y inscrit les choix retenus par `logger`,
# ce qui est la seule chose qu'on veuille y relire.
StandardOutput=tty
StandardError=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
# Trois questions à trente secondes : deux minutes couvrent le pire cas, et
# bornent un démarrage sans personne devant l'écran.
TimeoutStartSec=3min

[Install]
WantedBy=multi-user.target
UNIT

systemctl enable dsoxlab-assistant.service

# Le service de première configuration doit attendre l'assistant, sinon son
# journal se mêlerait aux questions.
mkdir -p /etc/systemd/system/dsoxlab-premier-demarrage.service.d
cat > /etc/systemd/system/dsoxlab-premier-demarrage.service.d/apres-assistant.conf <<'UNIT'
[Unit]
After=dsoxlab-assistant.service
UNIT

echo "assistant de premier démarrage installé"
