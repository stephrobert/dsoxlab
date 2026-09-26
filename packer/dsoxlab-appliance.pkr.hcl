# L'appliance dsoxlab : une VM prête à jouer les labs, sans rien installer.
#
# Pour qui : les postes Windows et macOS. Sur Linux, `uv tool install dsoxlab`
# suffit, et `dsoxlab demo` donne un premier lab : télécharger un gigaoctet pour
# éviter une commande n'aurait aucun sens, et le README le dit.
#
# Construite par le builder `qemu` de Packer, et non par `virtualbox-iso`. La
# raison est la CI : depuis avril 2024, les runners GitHub-hosted Linux exposent
# /dev/kvm, donc QEMU y est accéléré, là où VirtualBox exigerait un runner
# self-hosted. Cela retire du même coup `ovftool`, propriétaire, de la chaîne :
# l'OVA se fabrique avec `qemu-img` et `tar`, et c'est le workflow qui s'en charge.
#
# Ce qui a été éprouvé avant d'écrire ce fichier, localement :
#
#   * `packer init` installe le plugin qemu, `packer validate` passe ;
#   * un build accéléré KVM produit un qcow2 que `qemu-img check` déclare sain ;
#   * ce qcow2, converti en VMDK streamOptimized puis empaqueté en OVA, est
#     importé par VirtualBox : « Successfully imported the appliance », disque
#     attaché, 2 vCPU, 4 Go, NAT.
#
# L'image n'épingle PAS une version de dsoxlab : le premier démarrage installe la
# dernière publiée. Sans cela, il faudrait republier un gigaoctet à chaque
# correctif, et l'image serait périmée le lendemain.

packer {
  required_plugins {
    qemu = {
      version = "~> 1.1"
      source  = "github.com/hashicorp/qemu"
    }
  }
}

source "qemu" "appliance" {
  # L'extension n'est pas cosmétique : Packer n'en ajoute aucune, et sans elle
  # les globs `*.qcow2` du workflow (budget, empreintes, envoi) ne verraient
  # jamais le fichier. Le build local l'a produit sous « dsoxlab-appliance-dev ».
  vm_name = "dsoxlab-appliance-${var.image_version}.qcow2"

  iso_url      = var.iso_url
  iso_checksum = var.iso_checksum

  # `kvm` n'est pas une optimisation : sans accélération, l'installation de
  # Debian dépasse la limite de six heures d'un job GitHub.
  accelerator  = "kvm"
  machine_type = "q35"
  cpus         = var.build_cpus
  memory       = var.build_memory_mb
  disk_size    = "${var.disk_size_mb}M"

  format           = "qcow2"
  disk_compression = true
  disk_interface   = "virtio"
  net_device       = "virtio-net"

  # Ces deux lignes valent 513 Mio sur le fichier que l'utilisateur téléchargera,
  # et c'est mesuré, pas supposé. Cinq builds comparés :
  #
  #   discard=ignore + fstrim   → 1110 Mio   (les déchets restent dans l'image)
  #   discard=unmap  + fstrim   →  597 Mio   (ils sont rendus)
  #
  # Sous le défaut `ignore`, le guest annonce « 520 MiB trimmed » et le qcow2 ne
  # perd pas un octet : `fstrim` réussit sans rien libérer. C'est pourquoi le
  # script de nettoyage ne s'y fie plus, et pourquoi le disque est attaché ici en
  # `unmap`.
  #
  # `detect_zeroes` complète le tableau : il rend gratuit le remplissage par
  # zéros du nettoyage, qui sinon gonfle le disque de build à toute la place
  # libre, soit environ 17 Gio sur un disque de 20.
  disk_discard       = "unmap"
  disk_detect_zeroes = "unmap"

  # Aucun affichage sur un runner : sans `headless`, QEMU échoue à ouvrir SDL.
  headless = true

  # Sur un runner GitHub, `/` n'a qu'une quinzaine de gigaoctets libres contre
  # une septantaine sur `/mnt` : le workflow pointe donc ici vers /mnt.
  output_directory = var.output_directory

  # Le preseed est servi par Packer pendant le boot de l'ISO netinst.
  http_directory = "http"

  boot_command = [
    "<esc><wait>",
    "install ",
    "auto=true priority=critical ",
    "preseed/url=http://{{ .HTTPIP }}:{{ .HTTPPort }}/preseed.cfg ",
    # Locale et clavier sont des variables, non des valeurs figées : cette image
    # sert aussi les catalogues Terraform et Ansible, dont les apprenants ne sont
    # pas tous francophones.
    "debian-installer=${var.locale} locale=${var.locale} ",
    "keyboard-configuration/xkb-keymap=${var.keymap} ",
    "hostname=dsoxlab domain=lab ",
    "<enter>"
  ]
  boot_wait = "5s"

  ssh_username = var.ssh_username
  ssh_password = var.ssh_password
  ssh_timeout  = "45m"

  shutdown_command = "echo '${var.ssh_password}' | sudo -S shutdown -P now"
}

build {
  name    = "dsoxlab-appliance"
  sources = ["source.qemu.appliance"]

  provisioner "shell" {
    # `-H` et non `-E`, et ce n'est pas un détail de style. `-E` préserve
    # l'environnement, donc `HOME` restait `/home/student` pendant que le script
    # tournait en root : `terraform version` et `ansible-playbook --version` y ont
    # créé `~/.terraform.d` et `~/.ansible/tmp` APPARTENANT À ROOT.
    #
    # Conséquence mesurée dans l'appliance : Ansible ne démarre plus du tout pour
    # l'apprenant (« Permission denied: /home/student/.ansible/tmp », erreur sur
    # DEFAULT_LOCAL_TMP), donc AUCUN lab `vm` ne fonctionne — et le symptôme rendu
    # par dsoxlab est un « rc=5, Stats: {} » que rien ne relie à cette cause.
    execute_command = "echo '${var.ssh_password}' | sudo -S -H bash '{{ .Path }}'"
    scripts = [
      "scripts/10-base.sh",
      "scripts/20-outils.sh",
      "scripts/30-premier-demarrage.sh",
      # Avant-dernier à dessein : il bascule le résolveur, et 20-outils.sh
      # télécharge encore. Après lui, plus rien n'a besoin du réseau.
      "scripts/40-reseau-portable.sh",
      "scripts/90-nettoyage.sh",
    ]
  }

  post-processor "checksum" {
    checksum_types = ["sha256"]
    output         = "${var.output_directory}/SHA256SUMS-qcow2"
  }
}

variable "image_version" {
  type        = string
  description = "Version de l'image, pas celle de dsoxlab : l'image ne l'épingle pas."
}

variable "iso_url" { type = string }
variable "iso_checksum" { type = string }

#: Ressources du BUILD, sans rapport avec celles que l'utilisateur donnera.
variable "build_cpus" {
  type    = number
  default = 2
}
variable "build_memory_mb" {
  type    = number
  default = 2048
}

#: Le disque est fin : un qcow2 n'occupe que ce qu'il contient, et l'OVA dérivée
#: est compressée. 20 Gio laissent la place aux images de base des labs.
variable "disk_size_mb" {
  type    = number
  default = 20480
}

variable "ssh_username" {
  type    = string
  default = "student"
}

#: Mot de passe du BUILD, remplacé au premier démarrage. Il ne survit pas à
#: l'image : `30-premier-demarrage.sh` force son changement à la connexion.
variable "ssh_password" {
  type      = string
  default   = "dsoxlab"
  sensitive = true
}

variable "output_directory" {
  type    = string
  default = "output"
}

variable "locale" {
  type    = string
  default = "en_US.UTF-8"
}

variable "keymap" {
  type    = string
  default = "us"
}
