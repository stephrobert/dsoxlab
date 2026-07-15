variable "network_name" {
  description = "Nom du réseau Incus à créer (ex. lab-linux). Sera prefixé par 'incusbr-' au niveau du bridge si non géré par Incus."
  type        = string
}

variable "network_cidr" {
  description = "CIDR du réseau (ex. 10.10.30.0/24). L'adresse de gateway est cidrhost(cidr, 1)."
  type        = string
}

variable "hosts" {
  description = "Liste des VMs lab à créer (héritage du contrat dsoxlab). ``extra_disk_gb`` (0 = pas de disque additionnel) attache un volume block qui apparaît dans la VM comme /dev/sdb (virtio-scsi sur Incus)."
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
  description = "Overrides spécifiques au provider Incus : ssh_pubkey (injectée), image_<distro> pour surcharger l'alias par défaut."
  type        = map(string)
  default     = {}
}

variable "target_hosts" {
  description = "Restreint la création des ressources dédiées à ces hôtes (ciblage `dsoxlab provision/destroy --host`). Vide = tous les hôtes. Utilisé pour scoper le for_each des disques additionnels afin qu'un ciblage --host ne crée pas le disque d'un autre hôte (dsoxlab issue #1)."
  type        = list(string)
  default     = []
}
