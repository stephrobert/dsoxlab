terraform {
  required_version = ">= 1.5"

  required_providers {
    incus = {
      source  = "lxc/incus"
      version = "~> 0.3"
    }
  }
}

# Provider Incus officiel maintenu par le projet LXC. Communique avec
# le daemon local via /var/lib/incus/unix.socket. L'apprenant doit
# appartenir au groupe ``incus`` (cf. ``dsoxlab doctor``).
provider "incus" {}
