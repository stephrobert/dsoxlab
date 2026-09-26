#!/usr/bin/env bash
# Les outils que dsoxlab exige, et que `doctor` contrôle : uv, terraform,
# ansible. dsoxlab lui-même n'est PAS installé ici, et c'est délibéré : l'image
# ne doit pas épingler une version qui serait périmée le lendemain. Le premier
# démarrage installe la dernière publiée.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# uv, par son installateur officiel, en tant que `student` : l'outil vit dans son
# répertoire personnel, comme sur le poste d'un apprenant.
sudo -u student -H bash -lc 'curl -fsSL https://astral.sh/uv/install.sh | sh'

# Terraform, depuis le dépôt HashiCorp, avec la clé vérifiée. Requis par
# `provision` dès qu'un catalogue déclare des hôtes.
install -d -m 0755 /usr/share/keyrings
curl -fsSL https://apt.releases.hashicorp.com/gpg \
  | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
# `lsb_release` venait de la tâche `standard`, qui n'est plus installée : le nom
# de code se lit dans /etc/os-release, présent partout et sans dépendance.
. /etc/os-release
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
https://apt.releases.hashicorp.com ${VERSION_CODENAME} main" \
  > /etc/apt/sources.list.d/hashicorp.list
apt-get update -qq
apt-get install -y --no-install-recommends terraform

# ansible-core par le paquet de la distribution : `ansible-runner` ne le tire pas
# en transitif, et un `run` sur un lab vm sort en 127 sans lui.
apt-get install -y --no-install-recommends ansible-core

terraform version
ansible-playbook --version | head -1
