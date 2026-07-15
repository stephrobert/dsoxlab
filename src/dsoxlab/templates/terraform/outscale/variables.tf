variable "network_name" {
  description = "Nom du Net Outscale (équivalent VPC) — ex. lab-linux."
  type        = string
}

variable "network_cidr" {
  description = "CIDR du Net (ex. 10.20.0.0/22 — assez large pour 2 subnets /24)."
  type        = string
}

variable "hosts" {
  description = "Liste des VMs lab (sans le bastion qui est créé en plus). ``extra_disk_gb`` (0 = pas de disque additionnel) crée un outscale_volume + outscale_volumes_link qui apparaît comme /dev/xvdb dans la VM."
  type = list(object({
    name          = string
    distro        = string
    role          = string
    ram_mb        = number
    vcpu          = number
    disk_gb       = number
    extra_disk_gb = number
  }))
}

variable "provider_config" {
  description = <<-EOT
    Overrides Outscale lus depuis meta.yml: providers.outscale.

    Clés attendues (toutes optionnelles sauf image_id_*) :
    - region                 : région Outscale (défaut eu-west-2)
    - vm_type_default        : type VM des labs (défaut tinav5.c2r4p1)
    - vm_type_bastion        : type VM du bastion (défaut tinav5.c1r1p1)
    - image_id_alma10        : OMI AlmaLinux 10 PINÉE (omi-xxxxxxxx)
    - image_id_ubuntu24      : OMI Ubuntu 24.04 PINÉE
    - image_id_bastion       : OMI du bastion (par défaut = image_id_ubuntu24)
    - bastion_user           : utilisateur SSH du bastion (défaut "outscale")
    - ssh_pubkey             : clé SSH publique (injectée par dsoxlab depuis
                               <repo>/ssh/id_ed25519.pub)
  EOT
  type        = map(string)
  default     = {}
}

variable "target_hosts" {
  description = "Restreint la création des ressources dédiées à ces hôtes (ciblage `dsoxlab provision/destroy --host`). Vide = tous les hôtes. Utilisé pour scoper le for_each des disques additionnels afin qu'un ciblage --host ne crée pas le disque d'un autre hôte (dsoxlab issue #1)."
  type        = list(string)
  default     = []
}
