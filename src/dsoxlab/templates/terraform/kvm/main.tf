# Provider KVM/libvirt — homelab Linux desktop.
#
# Topologie :
# - 1 réseau libvirt dédié, NAT, DHCP avec baux statiques par MAC.
# - Pour chaque host : 1 image cloud (téléchargée si absente), 1 disque
#   QCOW2 backing-file, 1 ISO seed cloud-init, 1 domain libvirt.
# - Pas de bastion (réseau homelab direct depuis le poste de l'apprenant).

locals {
  # MAC déterministe, unique par DÉPÔT et par index. Les deux octets du milieu
  # sont dérivés d'un hash du repo.id : sans ça, deux catalogues KVM tournant en
  # parallèle sur le même hôte donnaient la même MAC (52:54:00:cd:00:<idx>) à
  # leurs VM de même index. Leurs baux se disputaient alors la table FDB du
  # bridge et une des deux VM restait injoignable (« No route to host », sans
  # erreur). C'est le pendant, en couche 2, de l'isolation par CIDR déjà en
  # place. L'index reste dans le dernier octet pour garder les baux lisibles.
  mac_prefix = format("52:54:%s:%s:00",
    substr(sha256(var.repo_id), 0, 2),
    substr(sha256(var.repo_id), 2, 2),
  )
  hosts_with_idx = [
    for idx, h in var.hosts : merge(h, {
      idx = idx
      mac = format("%s:%02x", local.mac_prefix, idx + 16)
      ip  = cidrhost(var.network_cidr, idx + 11)
    })
  ]

  ssh_pubkey = lookup(var.provider_config, "ssh_pubkey", "")

  # Mapping distro pédagogique → nom du template cloud-init packagé
  # dans dsoxlab/templates/cloud-init/<name>.yaml.tmpl. Aligné avec
  # le provider outscale (cf. terraform/outscale/main.tf).
  distro_to_template = {
    alma10   = "almalinux"
    alma9    = "almalinux"
    ubuntu26 = "ubuntu"
    ubuntu24 = "ubuntu"
    ubuntu22 = "ubuntu"
    debian13 = "debian"
    debian12 = "debian"
  }

  # URL de téléchargement des images cloud par distro. L'utilisateur
  # peut surcharger via providers.kvm.image_url_<distro> dans meta.yml.
  default_image_urls = {
    alma10   = "https://repo.almalinux.org/almalinux/10/cloud/x86_64/images/AlmaLinux-10-GenericCloud-latest.x86_64.qcow2"
    alma9    = "https://repo.almalinux.org/almalinux/9/cloud/x86_64/images/AlmaLinux-9-GenericCloud-latest.x86_64.qcow2"
    ubuntu26 = "https://cloud-images.ubuntu.com/resolute/current/resolute-server-cloudimg-amd64.img"
    ubuntu24 = "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
    ubuntu22 = "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
    # Variante « generic », PAS « genericcloud ». « genericcloud » utilise le
    # kernel CLOUD de Debian, aux drivers réduits (ciblé EC2/Azure). Combiné au
    # firmware OVMF/EFI que dsoxlab force ET au resize du disque au premier boot,
    # il kernel-panique (« Attempted to kill init » ; bug connu documenté côté
    # Proxmox et XCP-ng). « generic » embarque le kernel standard Debian et boot
    # partout, EFI compris, pour ~90 Mo de plus. alma et ubuntu ne sont pas
    # concernés (leur kernel n'est pas ce build cloud réduit).
    debian13 = "https://cloud.debian.org/images/cloud/trixie/latest/debian-13-generic-amd64.qcow2"
    debian12 = "https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2"
  }

  image_urls = {
    for h in var.hosts : h.distro => coalesce(
      lookup(var.provider_config, "image_url_${h.distro}", null),
      lookup(local.default_image_urls, h.distro, null),
    )...
  }

  # Distro unique → URL (déduplication)
  unique_distros = toset([for h in var.hosts : h.distro])
}

# ── Réseau libvirt dédié ───────────────────────────────────────────────────
#
# Syntaxe dmacvicar/libvirt 0.9.x : depuis la 0.8 le provider a remplacé
# les blocks "dns"/"dhcp"/"hosts" et les attributs string "mode"/"bridge"/
# "domain" par des attributs typés (objets/listes). Voir :
# https://registry.terraform.io/providers/dmacvicar/libvirt/latest/docs/resources/network

locals {
  network_prefix  = tonumber(split("/", var.network_cidr)[1])
  network_gateway = cidrhost(var.network_cidr, 1)
  bridge_name     = lookup(var.provider_config, "bridge_name", "virbr-${replace(var.network_name, "lab-", "")}")
}

resource "libvirt_network" "lab" {
  name      = var.network_name
  autostart = true

  forward = {
    mode = "nat"
  }

  bridge = {
    name = local.bridge_name
  }

  domain = {
    name       = "lab"
    local_only = "yes"
  }

  dns = {
    enable = "yes"
  }

  ips = [
    {
      address = local.network_gateway
      prefix  = local.network_prefix
      family  = "ipv4"
      dhcp = {
        ranges = [
          {
            start = cidrhost(var.network_cidr, 2)
            end   = cidrhost(var.network_cidr, -2)
          }
        ]
        hosts = [
          for h in local.hosts_with_idx : {
            name = h.name
            ip   = h.ip
            mac  = h.mac
          }
        ]
      }
    }
  ]

  # Le provider dmacvicar/libvirt ne sait PAS mettre à jour un réseau existant :
  # modifier `ips[].dhcp.hosts` (ajout/retrait d'un host) le pousse à RECRÉER le
  # réseau (issue #468), ce qui échoue en « element N has vanished /
  # inconsistent result after apply » et couperait la connectivité de toutes les
  # VMs attachées. On fige donc le réseau après création : Terraform le crée une
  # fois avec les baux de la liste initiale, puis n'y touche plus. Les baux des
  # hosts ajoutés ENSUITE sont posés à chaud par dsoxlab via `virsh net-update`
  # (infra/terraform.py:_ensure_kvm_dhcp_leases), avant l'apply des domaines.
  lifecycle {
    ignore_changes = [ips]
  }
}

# ── Images cloud (téléchargées une fois par distro) ────────────────────────
#
# 0.9.x : libvirt_volume sépare maintenant la création (create.content.url)
# du format cible (target.format.type) — l'attribut top-level "source"
# et "format" ont disparu.

resource "libvirt_volume" "base_image" {
  for_each = local.unique_distros

  # Le nom porte le repo_id : le pool libvirt est PARTAGÉ entre tous les dépôts
  # de labs, alors que chacun a son propre state Terraform et ignore les autres.
  # Sans ce préfixe, deux catalogues utilisant la même distro (linux et ansible
  # sur alma10, par exemple) se disputent « dsoxlab-base-alma10.qcow2 » : le
  # second à provisionner échoue sur « storage volume exists already », puisque
  # son state ne contient pas le volume créé par le premier.
  # Coût assumé : l'image cloud est dupliquée par dépôt (sparse, ~600 Mo à 2 Go).
  name = "dsoxlab-base-${var.repo_id}-${each.key}.qcow2"
  pool = "default"

  # 10 GiB : capacity requise quand le serveur HTTP ne renvoie pas de
  # Content-Length (cas du miroir AlmaLinux derrière redirection).
  # Le provider qcow2 stocke en sparse, donc l'occupation réelle reste
  # de l'ordre de la taille de l'image cloud (~600 MB - 2 GB).
  capacity = 10 * 1024 * 1024 * 1024

  target = {
    format = {
      type = "qcow2"
    }
  }

  create = {
    content = {
      url = local.image_urls[each.key][0] # première URL trouvée pour cette distro
    }
  }
}

# ── Disques par VM (backing file vers l'image de base) ─────────────────────
#
# 0.9.x : "base_volume_id" remplacé par "backing_store.path". On prend
# le path résolu de l'image de base. capacity en bytes (GiB → bytes).

resource "libvirt_volume" "host" {
  for_each = { for h in local.hosts_with_idx : h.name => h }

  name     = "${each.value.name}.qcow2"
  pool     = "default"
  capacity = each.value.disk_gb * 1024 * 1024 * 1024 # GiB → bytes

  target = {
    format = {
      type = "qcow2"
    }
  }

  backing_store = {
    path = libvirt_volume.base_image[each.value.distro].path
    format = {
      type = "qcow2"
    }
  }
}

# ── ISO seed cloud-init par VM ─────────────────────────────────────────────
#
# 0.9.x : libvirt_cloudinit_disk n'a plus d'attribut "pool" (il génère
# le ISO sur le filesystem libvirt et expose son path via .path). On
# l'attache ensuite à la VM via devices.disks[] en mode "cdrom".

# Le contenu cloud-init est calculé ici plutôt que dans la ressource, pour
# pouvoir en dériver un instance-id stable (voir plus bas).
locals {
  cloudinit_user_data = {
    for h in local.hosts_with_idx : h.name => templatefile(
      "${path.module}/../../cloud-init/${local.distro_to_template[h.distro]}.yaml.tmpl",
      {
        hostname   = h.name
        ssh_pubkey = local.ssh_pubkey
      }
    )
  }
}

resource "libvirt_cloudinit_disk" "host" {
  for_each = { for h in local.hosts_with_idx : h.name => h }

  # Le nom porte lui aussi le hachage. Sans cela, un remplacement réutilise le
  # même nom de volume, le provider y voit une mise à jour et refuse : c'est
  # l'autre moitié du blocage. Avec un nom distinct, le nouveau volume est créé
  # puis l'ancien supprimé, ce que le provider sait faire.
  name      = "${each.value.name}-seed-${substr(md5(local.cloudinit_user_data[each.value.name]), 0, 8)}.iso"
  user_data = local.cloudinit_user_data[each.value.name]

  # L'instance-id dérive du HACHAGE du cloud-init, et non de l'heure courante.
  #
  # Avec « timestamp() », il changeait à chaque plan : Terraform voulait donc
  # remplacer le disque à chaque exécution, et le provider libvirt refuse de
  # remplacer un volume (« Update Not Supported : storage volumes cannot be
  # updated »). Conséquence, tout provision rejoué sur une infrastructure
  # existante échouait, quel que soit le dépôt de labs.
  #
  # Avec un hachage, le plan est stable tant que le cloud-init ne bouge pas, et
  # l'identifiant change quand il bouge réellement : c'est précisément ce qui
  # doit conduire cloud-init à rejouer sa configuration au prochain démarrage.
  meta_data = yamlencode({
    instance-id    = "${each.value.name}-${substr(md5(local.cloudinit_user_data[each.value.name]), 0, 12)}"
    local-hostname = each.value.name
  })
  # Pas de network_config explicite : cloud-init applique sa logique
  # par défaut (DHCP sur la première NIC physique trouvée) qui marche
  # uniformément sur Ubuntu (netplan), AlmaLinux/RHEL (NetworkManager)
  # et Debian (ifupdown). Le format netplan v2 (match: { driver:
  # virtio* }) testé précédemment ne s'applique pas sur les distros
  # RHEL-like → la NIC reste sans config → pas de requête DHCP.
}

# Disque additionnel (extra_disk_gb > 0) pour les labs RHCSA/LFCS qui
# exigent un vrai bloc device pour partitionner + LVM. Apparaît dans
# la VM comme /dev/vdb (2e device virtio après vda du système).
# Création conditionnelle : seuls les hosts avec extra_disk_gb > 0
# obtiennent ce volume.
resource "libvirt_volume" "extra" {
  for_each = {
    for h in local.hosts_with_idx : h.name => h if h.extra_disk_gb > 0
  }

  name     = "${each.value.name}-extra.qcow2"
  pool     = "default"
  capacity = each.value.extra_disk_gb * 1024 * 1024 * 1024

  target = {
    format = { type = "qcow2" }
  }
}

# Upload du seed cloud-init dans le pool libvirt sous forme de volume
# nommé. Évite le path /tmp/terraform-provider-libvirt-cloudinit/ qui
# peut être bloqué par AppArmor sur Ubuntu (libvirt-qemu n'a pas accès
# à /tmp par défaut).
resource "libvirt_volume" "cloudinit" {
  for_each = { for h in local.hosts_with_idx : h.name => h }

  name = "${each.value.name}-cloudinit.iso"
  pool = "default"

  create = {
    content = {
      url = libvirt_cloudinit_disk.host[each.key].path
    }
  }
}

# ── Domains libvirt (les VMs) ──────────────────────────────────────────────
#
# 0.9.x : libvirt_domain a perdu tous ses blocks (network_interface,
# disk, graphics, console) — tout passe par devices = { ... }. L'API
# suit fidèlement le XML libvirt. Cf. examples/two_vms_with_cloudinit.tf
# du repo dmacvicar/terraform-provider-libvirt.

resource "libvirt_domain" "host" {
  for_each = { for h in local.hosts_with_idx : h.name => h }

  name = each.value.name
  # 0.9.x : memory est en KiB (pas MiB). 2048 MB → 2 097 152 KiB.
  memory    = each.value.ram_mb * 1024
  vcpu      = each.value.vcpu
  autostart = true
  running   = true
  type      = "kvm"

  os = {
    type         = "hvm"
    type_machine = "q35"
    # firmware = "efi" : UEFI obligatoire pour les images cloud
    # AlmaLinux 10+ (l'image générique n'embarque plus de bootloader
    # BIOS legacy depuis AlmaLinux 10). Sans ça → kernel panic au
    # démarrage. Ubuntu cloud reste compatible BIOS, mais UEFI marche
    # aussi sur Ubuntu donc on uniformise.
    firmware = "efi"
    # Désactive Secure Boot : libvirt 10+ enrôle par défaut les clés
    # Microsoft (OVMF_CODE_4M.ms.fd) qui rejettent les kernels non
    # signés MS. AlmaLinux/Debian/Ubuntu cloud images démarrent puis
    # bloquent à /init faute de modules virtio chargés.
    firmware_info = {
      # Ordre IMPORTANT : libvirt retourne les features dans l'ordre
      # alphabétique de leur name, donc on les déclare aussi dans cet
      # ordre pour éviter "Provider produced inconsistent result".
      features = [
        { enabled = "no", name = "enrolled-keys" },
        { enabled = "no", name = "secure-boot" },
      ]
    }
  }

  features = {
    acpi = true
  }

  # CPU host-passthrough : expose tous les flags CPU de l'hôte à la VM
  # (AES-NI, SSE4.x, AVX, etc.). Sans ça, libvirt utilise par défaut
  # ``mode='custom' model='qemu64'`` qui n'expose que des instructions
  # x86_64 minimales. Or les kernels RHEL/AlmaLinux 10 et certaines
  # modules crypto exigent des instructions modernes → stuck dans
  # /init au premier chargement de module.
  cpu = {
    mode = "host-passthrough"
  }

  devices = {
    disks = concat(
      [
        # Disque système principal (qcow2 backing file vers l'image de base).
        # 0.9.x : driver { name = "qemu", type = "qcow2" } EXPLICITE — sans
        # `name`, le disque est traité comme raw et la VM ne boote pas.
        {
          device = "disk"
          driver = {
            name = "qemu"
            type = "qcow2"
          }
          source = {
            volume = {
              pool   = libvirt_volume.host[each.key].pool
              volume = libvirt_volume.host[each.key].name
            }
          }
          target = {
            bus = "virtio"
            dev = "vda"
          }
        },
        # ISO cloud-init : on charge le seed via le volume libvirt
        # (libvirt_volume.cloudinit) pour éviter les problèmes d'AppArmor
        # avec le path /tmp/terraform-provider-libvirt-cloudinit/.
        {
          device = "cdrom"
          driver = {
            name = "qemu"
            type = "raw"
          }
          source = {
            volume = {
              pool   = libvirt_volume.cloudinit[each.key].pool
              volume = libvirt_volume.cloudinit[each.key].name
            }
          }
          target = {
            bus = "sata"
            dev = "sda"
          }
        },
      ],
      # Disque additionnel optionnel (extra_disk_gb > 0). Apparaît
      # comme /dev/vdb dans la VM, ce qui correspond au comportement
      # attendu par les labs RHCSA/LFCS storage.
      each.value.extra_disk_gb > 0 ? [
        {
          device = "disk"
          driver = {
            name = "qemu"
            type = "qcow2"
          }
          source = {
            volume = {
              pool   = libvirt_volume.extra[each.key].pool
              volume = libvirt_volume.extra[each.key].name
            }
          }
          target = {
            bus = "virtio"
            dev = "vdb"
          }
        }
      ] : []
    )

    interfaces = [
      {
        type  = "network"
        mac   = { address = each.value.mac }
        model = { type = "virtio" }
        source = {
          network = {
            network = libvirt_network.lab.name
          }
        }
      }
    ]

    graphics = [
      {
        vnc = {
          auto_port = true
          listen    = "127.0.0.1"
        }
      }
    ]

    # NOTE : serials/consoles/channels (qemu-guest-agent) déclarés
    # explicitement ne passent pas la validation 0.9.7 telle quelle —
    # le schéma exige source.pty.path obligatoire (alors qu'on veut
    # un path auto-alloué par libvirt). Pour l'instant on n'en
    # déclare aucun et on s'appuie sur :
    # - le DHCP libvirt + reservation par MAC pour récupérer les IPs
    # - les logs dnsmasq + journalctl pour le debug si cloud-init plante
    # À reprendre dans une PR future quand un exemple fonctionnel
    # sera disponible côté upstream.
  }
}
