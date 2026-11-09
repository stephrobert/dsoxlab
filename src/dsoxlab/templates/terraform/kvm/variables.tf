variable "repo_id" {
  description = "Identifiant du dépôt de labs (meta.yml: repo.id). Préfixe les ressources partagées entre dépôts au sein d'un même hyperviseur, pour que deux catalogues utilisant la même distro ne se disputent pas le volume de base."
  type        = string
}

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
  description = "Overrides spécifiques au provider KVM (libvirt_uri, bridge_name, images_dir, ssh_pubkey, storage_pool, image_url_<distro>)."
  type        = map(string)
  default     = {}
}

variable "target_hosts" {
  description = "Restreint la création des ressources dédiées à ces hôtes (ciblage `dsoxlab provision/destroy --host`). Vide = tous les hôtes. Utilisé pour scoper le for_each des disques additionnels afin qu'un ciblage --host ne crée pas le disque d'un autre hôte (dsoxlab issue #1)."
  type        = list(string)
  default     = []
}

variable "efi_loader" {
  description = <<-EOT
    Chemin du firmware EFI, DÉCOUVERT par dsoxlab dans `virsh domcapabilities`
    plutôt qu'écrit ici.

    L'autoselect `os.firmware = "efi"` a longtemps servi, mais il ne survit pas à
    la relecture du XML par le provider sur libvirt 8 : l'apply échoue alors sur
    « Provider produced inconsistent result after apply », avec `.os.firmware`
    revenu à null (dsoxlab issue #234, reproduit dans une VM Ubuntu 22.04).

    Le chemin ne peut pas être écrit en dur : il diffère selon la distribution
    (`/usr/share/OVMF/` sur Debian et Ubuntu, `/usr/share/edk2/` sur Fedora et
    Arch) et les variantes 2M/4M cohabitent. libvirt sait où sont ses firmwares,
    y compris en version 8, donc c'est lui qu'on interroge.

    Le loader retenu est celui SANS Secure Boot : les variantes `.ms.fd` et
    `.secboot.fd` enrôlent les clés Microsoft, qui rejettent les kernels non
    signés par elles, et les images cloud AlmaLinux, Debian et Ubuntu bloquent
    alors dans /init faute de charger leurs modules virtio.
  EOT
  type        = string
  # Un défaut vide pour que `terraform validate` tourne sans variables, comme le
  # fait la CI. Ce n'est pas une valeur utilisable : `apply` refuse de partir sur
  # une chaîne vide, en nommant le paquet OVMF à installer.
  default     = ""
}

variable "provenance_xml" {
  description = <<-EOT
    Bloc `<metadata>` de provenance, construit par dsoxlab et posé tel quel sur
    chaque domaine : d'où vient cette machine, c'est-à-dire quel catalogue l'a
    provisionnée et depuis quel répertoire (dsoxlab issue #345).

    Le XML est fabriqué en Python, et non ici : HCL n'a aucune fonction
    d'échappement XML, et un chemin de clone peut porter un `&`. Le document
    serait alors invalide et libvirt refuserait le domaine entier.

    Mesuré avec dmacvicar/libvirt 0.9.7 le 2026-11-09 : le XML se relit par
    `virsh metadata <domaine> <namespace>` sans Terraform, un second plan ne
    rend aucun changement, et le modifier donne un update IN-PLACE — l'UUID du
    domaine ne bouge pas, donc une reprovision ne détruit pas la machine.

    Une entrée PAR HÔTE, et non un bloc unique : une machine ajoutée à un
    catalogue déjà provisionné n'a pas été provisionnée en même temps que les
    autres, et lui attribuer la date des premières serait écrire un fait faux.
    Un hôte absent de la map ne reçoit aucun bloc.
  EOT
  type        = map(string)
  default     = {}
}
