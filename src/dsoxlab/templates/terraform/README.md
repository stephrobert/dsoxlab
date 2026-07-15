# Contrat des templates Terraform — providers dsoxlab

Chaque provider supporté par dsoxlab est implémenté comme un dossier
`<provider>/` dans `dsoxlab/templates/terraform/`. Pour ajouter un
nouveau provider, le contrat invariant suivant doit être respecté.

## Variables d'entrée (variables.tf)

Chaque template **doit** déclarer au minimum :

```hcl
variable "network_name" {
  description = "Nom du réseau lab (libvirt network, AWS VPC, etc.)."
  type        = string
}

variable "network_cidr" {
  description = "CIDR du réseau (ex. 10.20.0.0/22)."
  type        = string
}

variable "hosts" {
  description = "Liste des VMs lab à créer (FQDN, distro, role, ressources)."
  type = list(object({
    name    = string
    distro  = string   # alma10 | ubuntu24 | opensuse15 | debian12 | ...
    role    = string
    ram_mb  = number
    vcpu    = number
    disk_gb = number
  }))
}

variable "provider_config" {
  description = "Overrides spécifiques au provider (lus depuis meta.yml: providers.<name>)."
  type        = map(string)
  default     = {}
}
```

dsoxlab génère ces variables au runtime via
`<work-dir>/.dsoxlab.auto.tfvars.json` depuis `meta.yml`.

## Outputs obligatoires (outputs.tf)

Chaque template **doit** exposer exactement :

```hcl
output "hosts" {
  description = "Map FQDN → IP des VMs lab (IP privée pour les clouds)."
  value       = { for h in var.hosts : h.name => <ressource>.private_ip }
}

output "bastion" {
  description = "Bastion SSH si réseau privé (null pour KVM/Vagrant)."
  value = {
    fqdn      = <ressource>.public_dns
    public_ip = <ressource>.public_ip
    user      = "ec2-user"   # ou "ubuntu" / "admin" selon image
  }
}
```

Le bastion est **null** pour les providers à accès direct
(KVM homelab, Vagrant). Pour les providers cloud (AWS, GCP, Azure,
Outscale…), un bastion est **non négociable** :

- VMs lab dans subnet **privé** (pas d'IP publique)
- Bastion dans subnet **public** avec IP publique
- Security Groups : SSH bastion ouvert depuis Internet ; SSH lab
  ouvert uniquement depuis le SG bastion

dsoxlab détecte `bastion != null` et configure automatiquement
`ProxyJump` sur tous les hosts privés.

## Conventions de nommage

- Fichiers obligatoires : `versions.tf`, `variables.tf`, `main.tf`, `outputs.tf`
- Pas de `terraform.tfvars` ni `*.auto.tfvars` versionné — dsoxlab
  génère `.dsoxlab.auto.tfvars.json` à chaque provision
- Pas de backend distant ; le state vit dans le work-dir XDG géré par
  dsoxlab (`~/.local/state/dsoxlab/<repo-id>/terraform/<provider>/`)

## Convention cloud-init

Les VMs reçoivent leur user-data depuis les templates packagés
`dsoxlab/templates/cloud-init/<distro>.yaml.tmpl`. Variables
substituées via `templatefile()` :

- `__HOSTNAME__` → nom court de la VM
- `__SSH_PUBKEY__` → clé publique SSH du dépôt fournisseur

Compte utilisateur créé : `student` avec sudo NOPASSWD.

## Ajouter un provider

1. Créer `dsoxlab/templates/terraform/<provider>/` avec les 4 fichiers
   `.tf` et le contrat ci-dessus respecté.
2. Pour les providers cloud : implémenter le bastion + SG (règle non
   contournable, voir REFACTORING-PLAN §11.8).
3. Documenter dans `dsoxlab/templates/terraform/<provider>/README.md`
   les variables d'env de credentials attendues.
4. Ajouter un backend snapshot si pertinent dans
   `src/dsoxlab/infra/snapshot/<provider>.py` (sinon
   `NotImplementedError` est levée par défaut — acceptable).
5. PR sur dsoxlab uniquement. Les dépôts fournisseurs basculent au
   nouveau provider via `meta.yml: infra.provider` ou
   `DSOXLAB_PROVIDER=<provider>`.

## Providers actuels

| Provider | Fichier | État | Bastion | Snapshot |
| --- | --- | --- | --- | --- |
| `kvm`      | `kvm/`      | ✅ MVP | non (réseau direct libvirt) | ✅ via `virsh` |
| `outscale` | `outscale/` | 🟡 en cours | ✅ obligatoire | ⏳ à implémenter |
| `aws`      | `aws/`      | ⏳ planifié | ✅ obligatoire | ⏳ |
| `gcp`      | `gcp/`      | ⏳ planifié | ✅ obligatoire | ⏳ |
| `azure`    | `azure/`    | ⏳ planifié | ✅ obligatoire | ⏳ |
| `proxmox`  | `proxmox/`  | ⏳ planifié | optionnel | ⏳ |
| `vagrant`  | `vagrant/`  | ⏳ planifié | non | ⏳ |
| `incus`    | `incus/`    | ⏳ planifié | non | ⏳ |
