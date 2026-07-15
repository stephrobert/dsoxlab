"""Package infra — couche d'infrastructure pluggable.

- ``ansible``  : pilote Ansible via ansible-runner (config management).
- ``inventory``: génère l'inventory Ansible depuis meta.yml + outputs Terraform.
- ``terraform``: routeur multi-provider qui invoque ``terraform``.
- ``snapshot`` : abstraction snapshots avec dispatch par provider (à venir).
"""

from . import ansible as ansible_runner_mod
from . import terraform as terraform_mod
from .ansible import AnsibleNotInstalled, PlaybookResult, run_playbook
from .inventory import (
    bastion_info,
    build_inventory,
    inventory_path,
    read_terraform_outputs,
    write_inventory_file,
)
from .terraform import (
    ProviderNotImplemented,
    ProvisionResult,
    TerraformNotInstalled,
)

# Aliases courts pour que `from dsoxlab.infra import terraform` et
# `from dsoxlab.infra import ansible` fonctionnent (cohérent avec
# `import yaml` côté pyyaml).
ansible = ansible_runner_mod
terraform = terraform_mod

__all__ = [
    "AnsibleNotInstalled",
    "PlaybookResult",
    "ProviderNotImplemented",
    "ProvisionResult",
    "TerraformNotInstalled",
    "ansible",
    "bastion_info",
    "build_inventory",
    "inventory_path",
    "read_terraform_outputs",
    "run_playbook",
    "terraform",
    "write_inventory_file",
]
