"""L'état d'une infrastructure de labs, mesuré sans rien afficher.

Ce que ce module corrige
========================

``infra status`` portait 205 lignes pour une complexité cognitive de 61,
mesurées le 2026-10-16 : lecture du contrat, construction de l'inventaire,
rafraîchissement du fragment SSH, un ``ssh`` par hôte, interrogation paresseuse
de l'hyperviseur, diagnostic, puis deux sorties. L'état vivait dans des
variables ``nonlocal`` qu'une fonction interne modifiait.

Rien de tout cela ne concerne l'affichage, et c'était pourtant inséparable de
lui : un écran d'état d'une autre interface aurait dû le réécrire.

L'interrogation paresseuse, et pourquoi elle reste
==================================================

L'hyperviseur n'est interrogé **qu'au premier hôte muet**, et une seule fois
pour toute la commande. Ce n'est pas une optimisation gratuite : ``virsh`` peut
demander un mot de passe ou mettre plusieurs secondes à répondre, et tant que
tout répond il n'y a rien à diagnostiquer. La paresse est donc un comportement,
et :class:`EtatInfra` en garde la trace (``hyperviseur_interrogeable``,
``hyperviseur_erreur``) pour qu'un appelant distingue « aucun domaine » de
« rien n'a répondu ».
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..infra import libvirt
from ..models.repo import RepoMetadata
from ..utils.shell import CommandError
from . import host_diagnosis

logger = logging.getLogger(__name__)

#: Délai au-delà duquel un hôte est tenu pour muet. Quatre secondes pour la
#: connexion, quinze pour le tout : un hôte qui met plus que cela à répondre
#: n'est pas utilisable pour un lab de toute façon.
DELAI_CONNEXION = 4
DELAI_TOTAL = 15


@dataclass(frozen=True)
class EtatHote:
    """Ce qu'on sait d'un hôte, et ce qu'on n'a pas pu savoir."""

    fqdn: str
    ip: str
    joignable: bool
    raison: str | None = None
    domaine: str | None = None
    etat_domaine: str | None = None
    cause: str = ""


@dataclass
class EtatInfra:
    """L'état complet, tel que les deux sorties le liront."""

    provider: str | None = None
    hotes: list[EtatHote] = field(default_factory=list)
    hyperviseur_interrogeable: bool = False
    hyperviseur_erreur: str | None = None
    bastion: dict[str, Any] | None = None
    #: Le fragment SSH n'a pas pu être écrit, et la cause. Ce n'est pas un échec
    #: de la commande : l'état reste mesurable sans lui.
    fragment_ssh_erreur: str | None = None

    @property
    def joignables(self) -> int:
        return sum(1 for h in self.hotes if h.joignable)

    @property
    def total(self) -> int:
        return len(self.hotes)

    @property
    def tout_repond(self) -> bool:
        return self.total > 0 and self.joignables == self.total


class _Hyperviseur:
    """L'hyperviseur, interrogé au plus une fois, et seulement si besoin.

    Objet plutôt que trois ``nonlocal`` : l'état de l'interrogation (tentée ?
    réussie ? quelle erreur ?) est précisément ce qu'un appelant doit pouvoir
    lire, et une fermeture ne le lui rend pas.
    """

    def __init__(self, provider: str | None) -> None:
        # Un provider non résolu n'est pas interrogeable : il n'y a pas
        # d'hyperviseur à nommer, donc rien à demander.
        self.interrogeable = bool(
            provider and libvirt.supports_domain_state(provider)
        )
        self.erreur: str | None = None
        self._domaines: list[str] | None = None
        self._tente = False

    @property
    def a_repondu(self) -> bool:
        return self.interrogeable and self.erreur is None

    def etat_de(self, fqdn: str) -> libvirt.DomainStatus | None:
        """Ce que l'hyperviseur dit de cet hôte, ou ``None`` s'il ne dit rien.

        ``None`` signifie « je n'ai pas pu regarder », jamais « rien n'existe » :
        le diagnostic retombe alors sur ce que SSH sait, sans jamais conclure à
        une machine absente.
        """
        if not self.interrogeable:
            return None
        if not self._tente:
            self._tente = True
            try:
                self._domaines = libvirt.list_domains()
            except CommandError as exc:
                self.erreur = exc.result.stderr.strip() or str(exc)
        if self._domaines is None:
            return None
        try:
            return libvirt.inspect_host(fqdn, known=self._domaines)
        except CommandError as exc:
            logger.debug("libvirt state unavailable for %s: %s", fqdn, exc)
            return None


def commande_ssh(
    ip: str,
    utilisateur: str,
    cle: Path,
    bastion: dict[str, Any] | None = None,
) -> list[str]:
    """La commande qui teste un hôte, avec ses options et leurs raisons.

    ``-F /dev/null`` ignore la configuration SSH personnelle de l'apprenant :
    un ``ProxyJump`` appliqué par motif d'adresse (``Host 10.*``) y routait les
    hôtes de lab vers un bastion tiers, et l'erreur parlait alors d'un port
    65535 que personne n'avait demandé.

    Un ``ProxyCommand`` explicite plutôt que ``ProxyJump`` : le second ne
    propage pas le ``-i`` et utilise la clé par défaut de l'utilisateur, qui ne
    correspond pas à celle du lab, d'où un « Permission denied (publickey) ».
    """
    commande = [
        "ssh",
        "-F", "/dev/null",
        "-o", f"ConnectTimeout={DELAI_CONNEXION}",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-i", str(cle),
    ]
    if bastion:
        cible = bastion["fqdn"] or bastion["public_ip"]
        commande += [
            "-o",
            (
                f"ProxyCommand=ssh -F /dev/null -W %h:%p "
                f"-i {cle} "
                f"-o StrictHostKeyChecking=no "
                f"-o UserKnownHostsFile=/dev/null "
                f"{bastion['user']}@{cible}"
            ),
        ]
    return [*commande, f"{utilisateur}@{ip}", "true"]


def _sonder(commande: list[str]) -> tuple[bool, str | None]:
    """Joue la commande et rend (joignable, raison de l'échec).

    ``LC_ALL=C`` verrouille la langue : la raison vient de ``strerror``, que la
    libc traduit, et sans ce verrou « No route to host » devient une phrase
    différente sur chaque poste. Le diagnostic ne reconnaîtrait plus rien.

    ``check=False`` parce que l'échec **est** la mesure : un hôte injoignable
    est un résultat à rapporter, pas un incident qui arrête le tour des autres.
    """
    try:
        resultat = subprocess.run(
            commande,
            capture_output=True,
            timeout=DELAI_TOTAL,
            env={**os.environ, "LC_ALL": "C"},
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    if resultat.returncode == 0:
        return True, None
    dernieres = resultat.stderr.decode(errors="replace").strip().splitlines()[-1:]
    return False, dernieres[0] if dernieres else "timeout"


def mesurer(
    repo_meta: RepoMetadata,
    hotes: dict[str, dict[str, Any]],
    cle_ssh: Path,
    *,
    provider: str | None = None,
    bastion: dict[str, Any] | None = None,
    sonde: Callable[[list[str]], tuple[bool, str | None]] | None = None,
) -> EtatInfra:
    """Interroge chaque hôte, et diagnostique ceux qui ne répondent pas.

    ``sonde`` est injectable pour les tests : la sonder est la seule partie qui
    touche le réseau, et un test ne doit pas en dépendre.

    L'ordre des hôtes est **trié**, et il le reste : un ordre qui change d'un
    appel à l'autre rend illisible tout diff de deux documents.
    """
    sonder = sonde or _sonder
    hyperviseur = _Hyperviseur(provider)
    etat = EtatInfra(
        provider=provider,
        bastion=bastion,
        hyperviseur_interrogeable=hyperviseur.interrogeable,
    )

    for fqdn, variables in sorted(hotes.items()):
        ip = variables["ansible_host"]
        joignable, raison = sonder(
            commande_ssh(
                ip, variables.get("ansible_user", "ansible"), cle_ssh, bastion
            )
        )
        domaine = None if joignable else hyperviseur.etat_de(fqdn)
        etat.hotes.append(
            EtatHote(
                fqdn=fqdn,
                ip=ip,
                joignable=joignable,
                raison=raison,
                domaine=domaine.domain if domaine else None,
                etat_domaine=domaine.state if domaine else None,
                cause=host_diagnosis.diagnose(
                    reachable=joignable, reason=raison or "", status=domaine
                ),
            )
        )

    etat.hyperviseur_erreur = hyperviseur.erreur
    return etat


def document(etat: EtatInfra) -> dict[str, Any]:
    """Le document machine, dont la forme est un contrat lu par des scripts.

    ``hypervisor`` existe pour qu'un appelant distingue « aucun domaine » d'un
    hyperviseur qui n'a rien répondu : sans ce bloc, les deux se ressembleraient
    à des ``domain_state: null``.
    """
    return {
        "provider": etat.provider,
        "hypervisor": {
            "queryable": etat.hyperviseur_interrogeable and etat.hyperviseur_erreur is None,
            "error": etat.hyperviseur_erreur,
        },
        "hosts": [
            {
                "fqdn": h.fqdn,
                "ip": h.ip,
                "reachable": h.joignable,
                "reason": h.raison,
                "domain": h.domaine,
                "domain_state": h.etat_domaine,
                "cause": h.cause,
            }
            for h in etat.hotes
        ],
        "summary": {"reachable": etat.joignables, "total": etat.total},
    }


def document_sans_infrastructure() -> dict[str, Any]:
    """Le document d'un catalogue qui ne déclare aucune machine.

    Un catalogue 100 % shell est un cas normal, pas une erreur. En mode machine
    il faut tout de même un document : une phrase et un code 0 laissaient
    l'appelant sans rien à lire.
    """
    return {"provider": None, "hosts": [], "summary": {"reachable": 0, "total": 0}}
