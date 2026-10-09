#!/usr/bin/env bash
# Les outils que dsoxlab exige, et que `doctor` contrôle : uv, terraform,
# ansible. dsoxlab lui-même n'est PAS installé ici, et c'est délibéré : l'image
# ne doit pas épingler une version qui serait périmée le lendemain. Le premier
# démarrage installe la dernière publiée.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# uv, par un BINAIRE DE RELEASE VÉRIFIÉ, et non par `curl | sh`.
#
# L'installateur officiel exécute un script téléchargé sans en contrôler
# l'empreinte : OpenSSF Scorecard le signale en « Pinned-Dependencies », et il a
# raison. Un dépôt qui épingle toutes ses actions par SHA de 40 caractères et
# qui tube un script dans un shell se contredit.
#
# C'est le même patron que `actionlint` et `trufflehog` en CI : version
# déclarée, artefact téléchargé, empreinte vérifiée depuis le fichier que le
# projet publie à côté. L'outil vit toujours dans le répertoire personnel de
# `student`, comme sur le poste d'un apprenant.
UV_VERSION=0.12.24
uv_tmp="$(mktemp -d)"
uv_base="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}"
uv_asset="uv-x86_64-unknown-linux-gnu.tar.gz"
curl -fsSL -o "${uv_tmp}/${uv_asset}" "${uv_base}/${uv_asset}"
curl -fsSL -o "${uv_tmp}/${uv_asset}.sha256" "${uv_base}/${uv_asset}.sha256"
( cd "${uv_tmp}" && sha256sum -c "${uv_asset}.sha256" )
tar -xzf "${uv_tmp}/${uv_asset}" -C "${uv_tmp}"
install -d -m 0755 -o student -g student /home/student/.local/bin
for outil in uv uvx; do
  install -m 0755 -o student -g student \
    "${uv_tmp}/uv-x86_64-unknown-linux-gnu/${outil}" "/home/student/.local/bin/${outil}"
done
rm -rf "${uv_tmp}"
sudo -u student -H bash -lc 'uv --version'

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
