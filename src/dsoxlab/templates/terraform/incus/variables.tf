variable "repo_id" {
  description = "Identifiant du dépôt de labs (meta.yml: repo.id). Préfixe les ressources partagées entre dépôts au sein d'un même hyperviseur, pour que deux catalogues utilisant la même distro ne se disputent pas le volume de base."
  type        = string
}

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

variable "provenance_config" {
  description = <<-EOT
    Clés `user.dsoxlab.*` de provenance, fusionnées dans la config de chaque
    instance : d'où vient cette machine, c'est-à-dire quel catalogue l'a
    provisionnée et depuis quel répertoire (dsoxlab issue #345).

    `user.` est l'espace que le serveur Incus réserve aux applications ; ce
    template y écrivait déjà `user.lab.ip` et `user.lab.role`.

    Mesuré avec lxc/incus 0.5.1 et un serveur Incus 7.2 le 2026-11-09 : la clé
    se relit par `incus config get` sans Terraform, le plan reste stable bien
    que `config` soit à la fois optional et computed, et une modification est
    appliquée IN-PLACE.

    Une entrée PAR HÔTE, pour la même raison que côté kvm : la date de
    provisionnement d'une machine ajoutée plus tard n'est pas celle des
    premières. Un hôte absent de la map ne reçoit aucune clé.
  EOT
  type        = map(map(string))
  default     = {}
}
