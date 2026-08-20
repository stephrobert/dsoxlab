"""Interrogation de libvirt : savoir ce qui existe, plutôt que le deviner.

Le nom d'un domaine libvirt n'est **pas** dérivable d'une convention. Il est
posé par le template Terraform packagé ici, qui reprend tel quel le
``infra.hosts[].name`` du ``meta.yml`` — un FQDN par contrat. Un module qui
reconstruit ce nom de tête finit par viser un domaine inexistant dès que la
convention supposée diverge de celle que le template applique, et c'est
exactement ce qui est arrivé au backend de snapshot.

La règle de ce module est donc l'inverse : on **demande** à libvirt la liste
des domaines, puis on résout le nom dans cette liste. La résolution accepte
deux formes, dans cet ordre :

1. le FQDN complet (``control-node.lab``), ce que produit le template actuel ;
2. le nom court (``control-node``), pour les infrastructures créées par une
   version antérieure du template.

Aucune troisième forme n'est tentée : au-delà, on ne résout plus, on devine.
"""

from __future__ import annotations

import logging

from ..i18n import _
from ..utils.shell import run_command

logger = logging.getLogger(__name__)

#: Timeout de l'interrogation. Lister les domaines est une opération locale et
#: immédiate ; au-delà, c'est que le démon ne répond pas, et attendre plus
#: longtemps n'y changera rien.
_TIMEOUT = 30


class DomainNotFound(RuntimeError):
    """Levée quand aucun domaine libvirt ne correspond à un hôte du ``meta.yml``.

    Le message porte les trois informations qui permettent de trancher sans
    relancer ``virsh`` à la main : l'hôte demandé, les noms réellement essayés,
    et les domaines qui existent.
    """

    def __init__(self, host_fqdn: str, tried: list[str], known: list[str]) -> None:
        self.host_fqdn = host_fqdn
        self.tried = tried
        self.known = known
        super().__init__(
            _(
                "libvirt_domain_not_found",
                host=host_fqdn,
                tried=", ".join(tried),
                domains=", ".join(known) if known else _("libvirt_no_domain"),
            )
        )


def list_domains() -> list[str]:
    """Les domaines libvirt définis sur l'hyperviseur, démarrés ou non.

    Raises:
        CommandError: si ``virsh`` est absent ou si le démon ne répond pas.
            Cet échec-là n'est pas une absence de domaine, et le confondre
            avec elle produirait un diagnostic faux.
    """
    result = run_command(
        ["sudo", "virsh", "list", "--all", "--name"],
        timeout=_TIMEOUT,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def resolve_domain(host_fqdn: str, *, known: list[str] | None = None) -> str:
    """Résout un hôte du ``meta.yml`` vers le domaine libvirt qui existe.

    Args:
        host_fqdn: le ``infra.hosts[].name``, un FQDN par contrat.
        known: les domaines déjà connus, pour éviter une interrogation par
            hôte quand on en résout plusieurs d'affilée.

    Returns:
        Le nom du domaine tel que libvirt le connaît.

    Raises:
        DomainNotFound: si ni le FQDN ni le nom court n'existent.
    """
    domains = list_domains() if known is None else known
    short = host_fqdn.split(".", 1)[0]
    # Le FQDN d'abord : c'est ce que le template produit aujourd'hui, donc le
    # cas courant. Le nom court n'est qu'un repli historique.
    candidates = [host_fqdn] if short == host_fqdn else [host_fqdn, short]
    for candidate in candidates:
        if candidate in domains:
            logger.debug("domaine libvirt résolu : %s → %s", host_fqdn, candidate)
            return candidate
    raise DomainNotFound(host_fqdn, candidates, domains)
