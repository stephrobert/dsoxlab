variable "network_name" {
  description = "Nom du réseau libvirt à créer (ex. lab-linux)."
  type        = string
}

variable "network_cidr" {
  description = "CIDR du réseau (ex. 10.10.30.0/24)."
  type        = string
}

variable "hosts" {
  description = "Liste des VMs lab à créer. ``extra_disk_gb`` (0 = pas de disque additionnel) attache un 2e disque qui apparaît comme /dev/vdb dans la VM — utile pour les labs RHCSA/LFCS storage (LVM, partitionnement)."
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
  description = "Overrides spécifiques au provider KVM (libvirt_uri, bridge_name, images_dir, ssh_pubkey, image_url_<distro>)."
  type        = map(string)
  default     = {}
}
