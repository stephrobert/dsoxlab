# Provider Outscale — labs cloud avec bastion + réseau privé.
#
# Architecture (règle non contournable §11.8 du REFACTORING-PLAN) :
#
#   Internet
#      │
#      ▼
#   ┌─────────────── IGW ────────────────┐
#   │                                     │
#   │  Subnet public (10.x.0.0/24)        │
#   │  ┌──────────────┐                   │
#   │  │   bastion    │ ← IP publique     │
#   │  │ (Ubuntu 24)  │   SSH 22 depuis   │
#   │  └──────┬───────┘   Internet        │
#   │         │                            │
#   │         ▼ (SG-bastion → SG-lab)     │
#   │  Subnet privé (10.x.1.0/24)         │
#   │  ┌──────────────┐ ┌──────────────┐  │
#   │  │ alma-rhcsa-1 │ │ alma-rhcsa-2 │  │  ← pas d'IP publique
#   │  │ (AlmaLinux10)│ │              │  │     route NAT pour
#   │  └──────────────┘ └──────────────┘  │     accès Internet
#   │                                      │
#   └──────────────────────────────────────┘
#                  │
#                  ▼
#              NAT Service (egress only)

locals {
  region          = lookup(var.provider_config, "region", "eu-west-2")
  vm_type_default = lookup(var.provider_config, "vm_type_default", "tinav5.c2r4p1")
  vm_type_bastion = lookup(var.provider_config, "vm_type_bastion", "tinav5.c1r1p1")
  bastion_user    = lookup(var.provider_config, "bastion_user", "student")
  ssh_pubkey      = lookup(var.provider_config, "ssh_pubkey", "")

  # OMI par distro : l'utilisateur PIN les références dans meta.yml. Une entrée
  # par distro de distro_to_template : une distro déclarée dans un lab mais
  # absente ici donnerait une OMI vide et un échec Terraform opaque. Le défaut
  # "" reste : chaque catalogue ne pin QUE les distros qu'il utilise.
  image_ids = {
    alma10   = lookup(var.provider_config, "image_id_alma10", "")
    alma9    = lookup(var.provider_config, "image_id_alma9", "")
    ubuntu26 = lookup(var.provider_config, "image_id_ubuntu26", "")
    ubuntu24 = lookup(var.provider_config, "image_id_ubuntu24", "")
    ubuntu22 = lookup(var.provider_config, "image_id_ubuntu22", "")
    debian13 = lookup(var.provider_config, "image_id_debian13", "")
    debian12 = lookup(var.provider_config, "image_id_debian12", "")
  }
  image_id_bastion = coalesce(
    lookup(var.provider_config, "image_id_bastion", ""),
    local.image_ids["ubuntu24"],
  )

  # Mapping convention lab.yaml.distros[] → nom du template cloud-init
  # packagé dans dsoxlab/templates/cloud-init/<name>.yaml.tmpl.
  distro_to_template = {
    alma10   = "almalinux"
    alma9    = "almalinux"
    ubuntu26 = "ubuntu"
    ubuntu24 = "ubuntu"
    ubuntu22 = "ubuntu"
    debian13 = "debian"
    debian12 = "debian"
  }

  # Découpage du Net en 2 subnets /24 :
  # Net /22 = 1024 IPs → on prend les 2 premiers /24 :
  #   public  = cidrsubnet(net, 24-22, 0) = subnet[0]
  #   private = cidrsubnet(net, 24-22, 1) = subnet[1]
  # Le Net doit donc etre au moins /22 (le validator dsoxlab le verifie).
  network_prefix      = tonumber(split("/", var.network_cidr)[1])
  subnet_newbits      = 24 - local.network_prefix
  public_subnet_cidr  = cidrsubnet(var.network_cidr, local.subnet_newbits, 0)
  private_subnet_cidr = cidrsubnet(var.network_cidr, local.subnet_newbits, 1)

  # IPs privées allouées aux VMs lab (offset +10 dans le subnet privé)
  hosts_with_ip = [
    for idx, h in var.hosts : merge(h, {
      private_ip = cidrhost(local.private_subnet_cidr, 10 + idx)
    })
  ]

  bastion_private_ip = cidrhost(local.public_subnet_cidr, 10)
}

# ── Net (équivalent VPC) ───────────────────────────────────────────────────

resource "outscale_net" "lab" {
  ip_range = var.network_cidr

  tags {
    key   = "Name"
    value = var.network_name
  }
  tags {
    key   = "ManagedBy"
    value = "dsoxlab"
  }
}

# ── Internet Gateway ───────────────────────────────────────────────────────

resource "outscale_internet_service" "igw" {
  tags {
    key   = "Name"
    value = "${var.network_name}-igw"
  }
}

resource "outscale_internet_service_link" "igw_link" {
  internet_service_id = outscale_internet_service.igw.id
  net_id              = outscale_net.lab.id
}

# ── Subnets public + privé ─────────────────────────────────────────────────

resource "outscale_subnet" "public" {
  net_id                  = outscale_net.lab.id
  ip_range                = local.public_subnet_cidr
  subregion_name          = "${local.region}a"
  map_public_ip_on_launch = false # on attache une PublicIp explicitement au bastion

  tags {
    key   = "Name"
    value = "${var.network_name}-public"
  }
}

resource "outscale_subnet" "private" {
  net_id         = outscale_net.lab.id
  ip_range       = local.private_subnet_cidr
  subregion_name = "${local.region}a"

  tags {
    key   = "Name"
    value = "${var.network_name}-private"
  }
}

# ── NAT Service (egress du subnet privé) ───────────────────────────────────

resource "outscale_public_ip" "nat" {
  tags {
    key   = "Name"
    value = "${var.network_name}-nat-eip"
  }
}

resource "outscale_nat_service" "nat" {
  subnet_id    = outscale_subnet.public.id
  public_ip_id = outscale_public_ip.nat.id

  tags {
    key   = "Name"
    value = "${var.network_name}-nat"
  }

  depends_on = [outscale_internet_service_link.igw_link]
}

# ── Route Tables ──────────────────────────────────────────────────────────

resource "outscale_route_table" "public" {
  net_id = outscale_net.lab.id
  tags {
    key   = "Name"
    value = "${var.network_name}-rt-public"
  }
}

resource "outscale_route" "public_default" {
  route_table_id       = outscale_route_table.public.id
  destination_ip_range = "0.0.0.0/0"
  gateway_id           = outscale_internet_service.igw.id
}

resource "outscale_route_table_link" "public" {
  route_table_id = outscale_route_table.public.id
  subnet_id      = outscale_subnet.public.id
}

resource "outscale_route_table" "private" {
  net_id = outscale_net.lab.id
  tags {
    key   = "Name"
    value = "${var.network_name}-rt-private"
  }
}

resource "outscale_route" "private_default" {
  route_table_id       = outscale_route_table.private.id
  destination_ip_range = "0.0.0.0/0"
  nat_service_id       = outscale_nat_service.nat.id
}

resource "outscale_route_table_link" "private" {
  route_table_id = outscale_route_table.private.id
  subnet_id      = outscale_subnet.private.id
}

# ── Security Groups ────────────────────────────────────────────────────────
# Règle non contournable §11.8 : SSH bastion ouvert depuis Internet,
# SSH lab ouvert UNIQUEMENT depuis le SG bastion (pas depuis Internet).

resource "outscale_security_group" "bastion" {
  net_id              = outscale_net.lab.id
  description         = "dsoxlab bastion SSH ingress from Internet"
  security_group_name = "${var.network_name}-bastion-sg"

  tags {
    key   = "Name"
    value = "${var.network_name}-bastion-sg"
  }
}

resource "outscale_security_group_rule" "bastion_ssh_in" {
  flow              = "Inbound"
  security_group_id = outscale_security_group.bastion.id
  rules {
    from_port_range = 22
    to_port_range   = 22
    ip_protocol     = "tcp"
    ip_ranges       = ["0.0.0.0/0"]
  }
}

# Note : pas de regle bastion_egress explicite — Outscale cree
# automatiquement une regle outbound 0.0.0.0/0 -1 sur tout SG dans
# un Net. La declarer explicitement provoque un conflit a l'apply.

resource "outscale_security_group" "lab" {
  net_id              = outscale_net.lab.id
  description         = "dsoxlab lab VMs (SSH from bastion only)"
  security_group_name = "${var.network_name}-lab-sg"

  tags {
    key   = "Name"
    value = "${var.network_name}-lab-sg"
  }
}

resource "outscale_security_group_rule" "lab_ssh_from_bastion" {
  flow              = "Inbound"
  security_group_id = outscale_security_group.lab.id
  rules {
    from_port_range = 22
    to_port_range   = 22
    ip_protocol     = "tcp"
    security_groups_members {
      security_group_id = outscale_security_group.bastion.id
    }
  }
}

resource "outscale_security_group_rule" "lab_intra_all" {
  # Communication libre intra-lab (utile pour les exos client/serveur).
  flow              = "Inbound"
  security_group_id = outscale_security_group.lab.id
  rules {
    from_port_range = -1
    to_port_range   = -1
    ip_protocol     = "-1"
    security_groups_members {
      security_group_id = outscale_security_group.lab.id
    }
  }
}

# Note : pas de regle lab_egress explicite — Outscale cree
# automatiquement une regle outbound 0.0.0.0/0 -1 (cf. note sur
# bastion plus haut).

# ── Keypair Outscale (clé SSH publique du repo) ────────────────────────────

resource "outscale_keypair" "lab" {
  keypair_name = "${var.network_name}-keypair"
  public_key   = local.ssh_pubkey
}

# ── Bastion ────────────────────────────────────────────────────────────────

resource "outscale_vm" "bastion" {
  image_id           = local.image_id_bastion
  vm_type            = local.vm_type_bastion
  keypair_name       = outscale_keypair.lab.keypair_name
  subnet_id          = outscale_subnet.public.id
  security_group_ids = [outscale_security_group.bastion.id]
  private_ips        = [local.bastion_private_ip]

  user_data = base64encode(templatefile(
    "${path.module}/../../cloud-init/ubuntu.yaml.tmpl",
    {
      hostname   = "bastion"
      ssh_pubkey = local.ssh_pubkey
    }
  ))

  tags {
    key   = "Name"
    value = "${var.network_name}-bastion"
  }
  tags {
    key   = "ManagedBy"
    value = "dsoxlab"
  }
}

resource "outscale_public_ip" "bastion" {
  tags {
    key   = "Name"
    value = "${var.network_name}-bastion-eip"
  }
}

resource "outscale_public_ip_link" "bastion" {
  vm_id        = outscale_vm.bastion.vm_id
  public_ip_id = outscale_public_ip.bastion.id
}

# ── VMs lab (subnet privé) ─────────────────────────────────────────────────

resource "outscale_vm" "lab" {
  for_each = { for h in local.hosts_with_ip : h.name => h }

  image_id           = local.image_ids[each.value.distro]
  vm_type            = local.vm_type_default
  keypair_name       = outscale_keypair.lab.keypair_name
  subnet_id          = outscale_subnet.private.id
  security_group_ids = [outscale_security_group.lab.id]
  private_ips        = [each.value.private_ip]

  user_data = base64encode(templatefile(
    "${path.module}/../../cloud-init/${local.distro_to_template[each.value.distro]}.yaml.tmpl",
    {
      hostname   = split(".", each.value.name)[0]
      ssh_pubkey = local.ssh_pubkey
    }
  ))

  tags {
    key   = "Name"
    value = each.value.name
  }
  tags {
    key   = "Role"
    value = each.value.role
  }
  tags {
    key   = "ManagedBy"
    value = "dsoxlab"
  }

  depends_on = [
    outscale_route_table_link.private,
    outscale_nat_service.nat,
  ]
}

# ── Disque additionnel optionnel (extra_disk_gb > 0) ────────────────────────
#
# Crée un volume Outscale séparé attaché aux VMs qui en demandent un.
# Apparaît dans la VM comme /dev/xvdb (convention AWS-like). Utilisé
# par les labs RHCSA/LFCS storage qui exigent un vrai bloc device pour
# partitionnement + LVM.

resource "outscale_volume" "lab_extra" {
  for_each = {
    for h in local.hosts_with_ip : h.name => h if h.extra_disk_gb > 0
  }

  subregion_name = "${local.region}a"
  size           = each.value.extra_disk_gb
  volume_type    = "gp2"

  tags {
    key   = "Name"
    value = "${each.value.name}-extra"
  }
  tags {
    key   = "ManagedBy"
    value = "dsoxlab"
  }
}

resource "outscale_volume_link" "lab_extra" {
  for_each = outscale_volume.lab_extra

  device_name = "/dev/xvdb"
  volume_id   = each.value.volume_id
  vm_id       = outscale_vm.lab[each.key].vm_id
}
