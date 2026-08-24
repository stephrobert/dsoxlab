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

Le module sert aussi à **diagnostiquer** : ``inspect_host`` rend l'état d'un
domaine et ses baux DHCP, de quoi distinguer « cette machine n'existe pas » de
« elle existe et ne tourne pas » et de « elle tourne mais son réseau n'a pas
abouti ». Ces trois faits appellent trois gestes opposés, et aucun ne se déduit
d'un échec SSH.

Une règle traverse tout le module : **une interrogation impossible n'est jamais
une absence**. ``virsh`` absent, ``sudo`` refusé ou démon éteint lèvent
``CommandError`` ; rendre une liste vide dans ces cas ferait dire à l'outil
« aucune machine n'existe », ce qui est un faux diagnostic, pas une prudence.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..i18n import _
from ..utils.shell import CommandError, CommandResult, run_command

logger = logging.getLogger(__name__)

#: Timeout de l'interrogation. Lister les domaines est une opération locale et
#: immédiate ; au-delà, c'est que le démon ne répond pas, et attendre plus
#: longtemps n'y changera rien.
_TIMEOUT = 30

#: Les providers du contrat qui exposent leurs machines comme des domaines
#: libvirt, donc les seuls que ce module sait interroger.
#:
#: ``incus`` est délibérément absent : son template Terraform crée des
#: ``incus_instance``, que le démon incus gère et que ``virsh`` ne voit pas.
#: Les interroger demanderait un second backend (``incus list``), qu'aucune
#: machine de test ne permet aujourd'hui de vérifier. ``outscale`` est un cloud
#: distant, sans hyperviseur local à interroger. Pour ces deux-là, l'outil dit
#: qu'il ne sait pas plutôt que d'affirmer que rien n'existe.
INSPECTABLE_PROVIDERS = frozenset({"kvm"})

#: Les états libvirt qui signifient « le domaine exécute du code ». ``idle`` est
#: un état de marche, pas un arrêt : le domaine tourne sans consommer de CPU.
RUNNING_STATES = frozenset({"running", "idle"})

#: Une adresse IPv4, éventuellement suivie de son préfixe, telle que
#: ``virsh domifaddr`` la présente (``10.10.30.12/24``).
_IPV4 = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})(?:/\d{1,2})?\b")


def supports_domain_state(provider: str) -> bool:
    """Ce provider expose-t-il un état de machine interrogeable ici ?

    Répondre ``False`` n'est pas une panne : c'est la seule réponse honnête
    pour un provider dont les machines ne sont pas des domaines libvirt. Les
    appelants doivent alors garder leur comportement d'avant et le dire, pas
    conclure à une absence.
    """
    return provider in INSPECTABLE_PROVIDERS


#: L'URI que le template vise. Les domaines créés par ``provision`` vivent sur
#: l'URI **système** ; l'URI session d'un utilisateur n'en contient aucun, et
#: ``virsh`` sans ``--connect`` peut viser l'une ou l'autre selon la
#: distribution. La déclarer supprime toute ambiguïté. ``LIBVIRT_DEFAULT_URI``
#: reste prioritaire : qui l'a posée sait ce qu'elle fait.
_URI_DEFAUT = "qemu:///system"

#: Le préfixe retenu après détection, mémorisé pour ne pas resonder à chaque
#: appel. ``None`` signifie « pas encore cherché », la liste vide « direct ».
_prefixe_retenu: list[str] | None = None


def _uri() -> str:
    return os.environ.get("LIBVIRT_DEFAULT_URI") or _URI_DEFAUT


def _sonder(prefixe: list[str], *, timeout: int = _TIMEOUT) -> bool:
    """Ce préfixe permet-il de joindre l'hyperviseur ?"""
    try:
        run_command(
            [*prefixe, "virsh", "--connect", _uri(), "list", "--name"],
            check=True,
            timeout=timeout,
        )
    except CommandError:
        return False
    return True


def _prefixe(*, timeout: int = _TIMEOUT) -> list[str]:
    """Rend le préfixe qui joint l'hyperviseur, ``[]`` ou ``["sudo", "-n"]``.

    L'ordre n'est pas indifférent. La configuration que recommande libvirt est
    d'ajouter l'utilisateur au groupe ``libvirt``, ce qui donne accès à l'URI
    système **sans** sudo et n'implique aucun ``NOPASSWD``. Exiger ``sudo``
    d'emblée éteindrait tout le diagnostic sur ces machines, en annonçant un
    hyperviseur injoignable là où ``virsh list --all`` répond parfaitement.

    Le repli ``sudo -n`` sert la machine où libvirt n'est joignable que par
    root. Le ``-n`` est indispensable : la sortie de ces commandes est capturée,
    donc un prompt de mot de passe n'aurait aucun terminal où s'afficher et
    l'appel resterait pendu jusqu'au timeout.

    Si aucun des deux ne répond, on rend le préfixe direct : l'appel réel
    échouera et lèvera ``CommandError``, que l'appelant traduit en « hyperviseur
    non interrogeable ». Une interrogation impossible n'est jamais une absence.
    """
    global _prefixe_retenu  # noqa: PLW0603 — un cache de processus, pas un état métier
    if _prefixe_retenu is not None:
        return _prefixe_retenu

    for candidat in ([], ["sudo", "-n"]):
        if _sonder(candidat, timeout=timeout):
            logger.debug(
                "virsh reachable with prefix %r on %s", candidat, _uri()
            )
            _prefixe_retenu = candidat
            return candidat

    logger.debug("virsh unreachable, neither directly nor through sudo -n")
    _prefixe_retenu = []
    return _prefixe_retenu


def _oublier_prefixe() -> None:
    """Vide le cache de détection. Réservé aux tests."""
    global _prefixe_retenu  # noqa: PLW0603
    _prefixe_retenu = None


def _virsh(
    args: list[str], *, check: bool = True, timeout: int = _TIMEOUT
) -> CommandResult:
    """Invoque ``virsh`` sur l'URI système, sans jamais bloquer sur un mot de passe.

    Le ``timeout`` borne aussi la détection du préfixe : un appelant pressé
    (``doctor``, qui sonde en quelques secondes) ne doit pas attendre deux
    fois trente secondes qu'un démon muet refuse de répondre aux sondes.
    """
    return run_command(
        [*_prefixe(timeout=min(timeout, _TIMEOUT)), "virsh", "--connect", _uri(), *args],
        check=check,
        timeout=timeout,
    )


def run_virsh(
    args: list[str], *, check: bool = True, timeout: int = _TIMEOUT
) -> CommandResult:
    """Invoque ``virsh`` par le chemin détecté, pour les modules du paquet.

    Une seule porte d'entrée : le backend de snapshot passe par ici plutôt que
    de recomposer sa propre ligne de commande, sans quoi la détection du chemin
    et le ``-n`` qui empêche de pendre ne vaudraient que pour la moitié des
    appels.
    """
    return _virsh(args, check=check, timeout=timeout)


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
    result = _virsh(["list", "--all", "--name"])
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
            logger.debug("libvirt domain resolved: %s -> %s", host_fqdn, candidate)
            return candidate
    raise DomainNotFound(host_fqdn, candidates, domains)


def existing_domains(
    host_fqdns: Iterable[str], *, known: list[str] | None = None
) -> dict[str, str]:
    """Parmi ``host_fqdns``, ceux qui correspondent à un domaine défini.

    Args:
        host_fqdns: les ``infra.hosts[].name`` du ``meta.yml`` courant, et
            **eux seuls**. Un domaine que ce dépôt ne déclare pas n'a rien à
            faire dans le résultat : c'est ce qui empêche l'outil de désigner,
            puis de retirer, une machine qui ne lui appartient pas.
        known: les domaines déjà listés, pour n'interroger libvirt qu'une fois.

    Returns:
        ``{fqdn déclaré: nom du domaine tel que libvirt le connaît}``, restreint
        à ceux qui existent réellement.

    Raises:
        CommandError: si l'hyperviseur ne peut pas être interrogé. L'appelant
            doit traiter ce cas comme « je ne sais pas », jamais comme « rien
            n'existe ».
    """
    domains = list_domains() if known is None else known
    trouves: dict[str, str] = {}
    for fqdn in host_fqdns:
        try:
            trouves[fqdn] = resolve_domain(fqdn, known=domains)
        except DomainNotFound:
            continue
    return trouves


def domain_state(domain: str) -> str:
    """L'état libvirt brut d'un domaine (``running``, ``shut off``, ``crashed``…).

    Le mot est rendu tel que libvirt le dit, sans réinterprétation : c'est lui
    que le diagnostic doit citer, parce que c'est lui que l'apprenant retrouvera
    dans un ``virsh list --all``.

    Raises:
        CommandError: si l'hyperviseur ne peut pas être interrogé.
    """
    result = _virsh(["domstate", domain])
    for line in result.stdout.splitlines():
        if line.strip():
            return line.strip()
    return ""


def lease_addresses(domain: str) -> list[str]:
    """Les adresses IPv4 que libvirt a effectivement baillées à ce domaine.

    Répond à une question que SSH ne sait pas poser : la machine tourne-t-elle
    *sur le réseau* ? Un domaine en marche sans bail n'a pas fini de booter, ou
    son interface n'a pas abouti — deux situations où attendre un SSH est vain.

    Best-effort assumé : ``domifaddr`` échoue sur un domaine éteint et sur
    certaines configurations réseau. Une liste vide veut donc dire « aucun bail
    observé », ce que l'appelant ne doit croire que d'un domaine en marche.
    """
    result = _virsh(["domifaddr", domain, "--source", "lease"], check=False)
    if not result.ok:
        return []
    return [m.group(1) for m in _IPV4.finditer(result.stdout)]


@dataclass(frozen=True)
class DomainStatus:
    """Ce que l'hyperviseur sait d'un hôte déclaré, à un instant donné.

    ``domain`` à ``None`` signifie « aucun domaine ne porte ce nom », un fait,
    et non « je n'ai pas pu regarder » : ce second cas se signale par une
    ``CommandError`` levée avant même de construire cet objet.
    """

    host: str
    domain: str | None = None
    state: str | None = None
    addresses: list[str] = field(default_factory=list)

    @property
    def exists(self) -> bool:
        return self.domain is not None

    @property
    def running(self) -> bool:
        return self.state in RUNNING_STATES


def inspect_host(host_fqdn: str, *, known: list[str] | None = None) -> DomainStatus:
    """Interroge l'hyperviseur sur un hôte du ``meta.yml``.

    N'interroge les baux que d'un domaine en marche : sur un domaine éteint la
    réponse serait vide pour une raison sans intérêt, et la confondre avec
    « ce domaine tourne sans adresse » inventerait un problème réseau.

    Raises:
        CommandError: si l'hyperviseur ne peut pas être interrogé du tout.
    """
    domains = list_domains() if known is None else known
    try:
        domain = resolve_domain(host_fqdn, known=domains)
    except DomainNotFound:
        return DomainStatus(host=host_fqdn)
    try:
        etat = domain_state(domain)
    except CommandError as exc:
        # Le domaine existe — on vient de le résoudre. Ne pas connaître son état
        # n'autorise pas à le déclarer absent.
        logger.debug("state unavailable for %s: %s", domain, exc)
        return DomainStatus(host=host_fqdn, domain=domain)
    adresses = lease_addresses(domain) if etat in RUNNING_STATES else []
    return DomainStatus(host=host_fqdn, domain=domain, state=etat, addresses=adresses)


def remove_domain(domain: str) -> None:
    """Retire un domaine de l'hyperviseur : l'arrête s'il tourne, puis le dé-définit.

    ``undefine`` seul laisserait un domaine en marche en état **transitoire** :
    il disparaîtrait de la configuration tout en continuant de tourner, donc de
    tenir son nom, et le provisionnement suivant échouerait encore.

    Ne supprime **aucun volume** : les disques appartiennent à Terraform, qui
    les a déjà retirés dans le cas qui motive cette fonction. Détruire ici du
    stockage que l'appelant n'a pas nommé serait irréversible et hors mandat.

    Raises:
        CommandError: si le retrait échoue.
    """
    try:
        etat = domain_state(domain)
    except CommandError:
        etat = ""
    if etat in RUNNING_STATES:
        _virsh(["destroy", domain], check=False, timeout=60)
    try:
        # `--nvram` retire le fichier de variables UEFI, sans quoi libvirt
        # refuse de dé-définir une machine qui en a un.
        _virsh(["undefine", domain, "--nvram"], timeout=60)
    except CommandError:
        # Les libvirt anciens rejettent l'option sur un domaine sans nvram :
        # on retente la forme nue plutôt que d'abandonner sur un détail
        # d'options.
        _virsh(["undefine", domain], timeout=60)
