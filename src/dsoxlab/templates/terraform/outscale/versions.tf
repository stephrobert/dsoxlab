terraform {
  required_version = ">= 1.5"

  required_providers {
    outscale = {
      source  = "outscale/outscale"
      version = "~> 1.0"
    }
  }
}

# Le provider Outscale lit ses credentials depuis :
#   - variables d'env OSC_ACCESS_KEY / OSC_SECRET_KEY / OSC_REGION
#   - ou ~/.osc/config.json (profile "default")
# Aucune credential n'est jamais hardcodée dans le template.
provider "outscale" {
  region = lookup(var.provider_config, "region", "eu-west-2")
}
