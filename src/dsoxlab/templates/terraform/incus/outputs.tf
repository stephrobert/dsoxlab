output "hosts" {
  description = "Map FQDN → IP des VMs lab (résolu après wait_for ipv4)."
  value       = { for k, v in incus_instance.host : k => v.ipv4_address }
}

output "bastion" {
  description = "Pas de bastion pour le provider Incus — accès direct depuis le poste apprenant via le bridge incusbr*."
  value       = null
}

output "network_cidr" {
  description = "CIDR du réseau lab."
  value       = var.network_cidr
}
