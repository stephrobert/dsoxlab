output "hosts" {
  description = "Map FQDN → IP des VMs lab (DHCP statique libvirt)."
  value       = { for h in local.hosts_with_idx : h.name => h.ip }
}

output "bastion" {
  description = "Pas de bastion pour le provider KVM — accès direct au réseau libvirt depuis le poste."
  value       = null
}

output "network_cidr" {
  description = "CIDR du réseau lab."
  value       = var.network_cidr
}
