# Provider Incus — homelab Linux desktop avec VMs Incus.
#
# Topologie :
# - 1 réseau Incus dédié (bridge type) : NAT + DHCP par Incus.
# - Pour chaque host : 1 VM Incus (type virtual-machine, pas container)
#   avec image cloud-* (cloud-init préinstallé).
# - Pas de bastion (accès direct au bridge depuis le poste apprenant).
#
# Pourquoi VMs et pas containers ? Les labs RHCSA/LFCS testent systemd,
# SELinux, partitionnement et services système — tout ça marche dans
# un container Incus mais avec des limitations (SELinux désactivé,
# certains modules kernel inaccessibles). Les VMs Incus utilisent
# QEMU+virtio derrière, comme libvirt KVM, et exposent un OS complet.

locals {
  # Mapping distro pédagogique → alias d'image cloud Incus du registry
  # public images:. Override possible via providers.incus.image_<distro>
  # dans meta.yml. Toutes les images doivent être ``-cloud`` (cloud-init
  # préinstallé) — sinon SSH/users ne sont pas configurés au boot.
  default_images = {
    alma10   = "images:almalinux/10/cloud"
    alma9    = "images:almalinux/9/cloud"
    ubuntu24 = "images:ubuntu/noble/cloud"
    ubuntu22 = "images:ubuntu/jammy/cloud"
    debian12 = "images:debian/12/cloud"
  }

  # Mapping distro → nom du template cloud-init partagé dans
  # dsoxlab/templates/cloud-init/<name>.yaml.tmpl. Aligné avec
  # outscale et kvm.
  distro_to_template = {
    alma10   = "almalinux"
    alma9    = "almalinux"
    ubuntu24 = "ubuntu"
    ubuntu22 = "ubuntu"
    debian12 = "debian"
  }

  ssh_pubkey = lookup(var.provider_config, "ssh_pubkey", "")

  # Hosts enrichis avec idx et IP statique calculée depuis le CIDR.
  # MAC déterministe pour réservation DHCP côté Incus (cf. device nic).
  hosts_with_idx = [
    for idx, h in var.hosts : merge(h, {
      idx = idx
      mac = format("00:16:3e:cd:00:%02x", idx + 16) # OUI Xen/LXC
      ip  = cidrhost(var.network_cidr, idx + 11)
    })
  ]

  # Hôtes dont on crée réellement le disque additionnel : ceux qui en
  # déclarent un (extra_disk_gb > 0) ET, si un ciblage --host est actif
  # (var.target_hosts non vide), qui sont dans la cible. Sinon TOUS les
  # hôtes à disque. Ce filtrage évite que `provision --host X` ne crée le
  # volume extra d'un AUTRE hôte : terraform -target de l'instance tire le
  # for_each extra en entier, mais ce for_each ne contient alors que les
  # volumes des hôtes ciblés (issue #1). La référence de ressource est
  # conservée dans le device → l'ordre create/destroy reste correct.
  in_scope_extra = {
    for h in local.hosts_with_idx : h.name => h
    if h.extra_disk_gb > 0 && (
      length(var.target_hosts) == 0 || contains(var.target_hosts, h.name)
    )
  }
}

# ── Réseau Incus dédié (bridge NAT) ───────────────────────────────────────────
#
# Incus crée un bridge Linux <name> + dnsmasq + iptables NAT
# automatiquement quand type = "bridge". L'adressage est passé via
# ipv4.address (gateway/CIDR) et le DHCP est activé par défaut.

resource "incus_network" "lab" {
  name = var.network_name
  type = "bridge"

  config = {
    "ipv4.address" = "${cidrhost(var.network_cidr, 1)}/${tonumber(split("/", var.network_cidr)[1])}"
    "ipv4.nat"     = "true"
    "ipv4.dhcp"    = "true"
    "ipv6.address" = "none"
  }
}

# ── Instances VMs Incus ───────────────────────────────────────────────────────
#
# image = alias du catalogue images: (résolu et téléchargé par Incus
# au premier lancement, puis caché localement). type = "virtual-machine"
# pour avoir un vrai kernel + systemd complet (SELinux/AppArmor,
# partitionnement, services). cloud-init.user-data dans config injecte
# le seed cloud-init au premier boot.

# ── Volumes block additionnels (extra_disk_gb > 0) ──────────────────────────
#
# Pour les labs RHCSA/LFCS storage qui exigent un vrai bloc device
# (partitionnement, LVM). content_type=block expose un volume raw
# (pas formaté) que la VM voit comme /dev/sdb (virtio-scsi sur Incus).

resource "incus_storage_volume" "extra" {
  for_each = local.in_scope_extra

  name         = "${replace(each.value.name, ".", "-")}-extra"
  pool         = "default"
  type         = "custom"
  content_type = "block"

  config = {
    "size" = "${each.value.extra_disk_gb}GiB"
  }
}

resource "incus_instance" "host" {
  for_each = { for h in local.hosts_with_idx : h.name => h }

  # Incus refuse les '.' dans les noms d'instance. On sanitize en
  # remplaçant '.' par '-' (alma-rhcsa-1.lab → alma-rhcsa-1-lab).
  # La clé du for_each garde le fqdn original pour rester cohérent
  # avec les autres providers (kvm, outscale) côté outputs et inventory.
  name    = replace(each.value.name, ".", "-")
  type    = "virtual-machine"
  image   = lookup(var.provider_config, "image_${each.value.distro}", local.default_images[each.value.distro])
  running = true

  config = {
    "limits.cpu"     = tostring(each.value.vcpu)
    "limits.memory"  = "${each.value.ram_mb}MiB"
    "boot.autostart" = "true"
    # Cloud-init NoCloud-style : Incus pose le seed via virtio-fs ou
    # config drive selon la version. user-data = full YAML cloud-config.
    "cloud-init.user-data" = templatefile(
      "${path.module}/../../cloud-init/${local.distro_to_template[each.value.distro]}.yaml.tmpl",
      {
        hostname   = each.value.name
        ssh_pubkey = local.ssh_pubkey
      }
    )
    # Réservation DHCP statique côté Incus : la NIC reçoit toujours la
    # même IP au sein du bridge.
    "user.lab.ip"   = each.value.ip
    "user.lab.role" = each.value.role
  }

  # NIC reliée au bridge lab + IP statique. Le ``hwaddr`` fixe la MAC,
  # ce qui permet à Incus de réserver l'IP via dnsmasq.
  device {
    name = "eth0"
    type = "nic"
    properties = {
      "name"         = "eth0"
      "network"      = incus_network.lab.name
      "ipv4.address" = each.value.ip
      "hwaddr"       = each.value.mac
    }
  }

  # Disque root personnalisé pour overrider la taille (l'image cloud
  # par défaut fait ~10 GiB, on étend selon disk_gb du contrat dsoxlab).
  device {
    name = "root"
    type = "disk"
    properties = {
      "path" = "/"
      "pool" = "default"
      "size" = "${each.value.disk_gb}GiB"
    }
  }

  # Disque agent:config requis par les VMs Incus. Ce disque virtuel
  # injecte le incus-agent + son token + les seed cloud-init dans la
  # VM via un device 9p/virtio-fs. Sans lui, certaines images (cas
  # observé : AlmaLinux 10 cloud) refusent de démarrer avec :
  #   "This virtual machine image requires an agent:config disk".
  # Les images Ubuntu/Debian cloud bootent quand même mais l'agent
  # incus exec ne fonctionne pas sans ce device.
  device {
    name = "agent"
    type = "disk"
    properties = {
      "source" = "agent:config"
    }
  }

  # Disque additionnel optionnel. Apparaît dans la VM comme /dev/sdb
  # (virtio-scsi). On n'attache le device QUE quand le volume extra de
  # cet hôte est réellement créé (cf. local.in_scope_extra) : ainsi le
  # ciblage --host reste cohérent (pas de référence à un volume filtré)
  # et la référence de ressource garde l'ordre create/destroy.
  dynamic "device" {
    for_each = contains(keys(local.in_scope_extra), each.value.name) ? [each.value] : []
    content {
      name = "extra"
      type = "disk"
      properties = {
        "source" = incus_storage_volume.extra[each.key].name
        "pool"   = "default"
      }
    }
  }

  # Attendre que la VM ait pris une IPv4 quelle qu'en soit l'interface.
  # On NE filtre pas sur ``nic = "eth0"`` : si la VM a un souci pour
  # configurer cette interface précise (cas observé : agent:config
  # manquant qui empêche le boot complet), terraform reste bloqué
  # indéfiniment sur le wait_for. Sans nic, dès qu'une NIC obtient
  # une IP, l'apply rend la main.
  wait_for {
    type = "ipv4"
  }
}
