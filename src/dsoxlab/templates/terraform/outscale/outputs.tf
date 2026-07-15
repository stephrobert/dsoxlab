output "hosts" {
  description = "Map FQDN → IP privée des VMs lab (subnet privé Outscale)."
  value = {
    for name, vm in outscale_vm.lab : name => vm.private_ips[0]
  }
}

output "bastion" {
  description = "Bastion SSH dans le subnet public — règle non contournable §11.8."
  value = {
    fqdn      = outscale_public_ip.bastion.public_ip
    public_ip = outscale_public_ip.bastion.public_ip
    user      = local.bastion_user
  }
}

output "network_cidr" {
  description = "CIDR du Net Outscale."
  value       = var.network_cidr
}
