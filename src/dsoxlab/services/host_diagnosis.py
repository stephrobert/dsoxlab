"""Pourquoi un hôte de lab ne répond pas — un fait, pas deux hypothèses.

``dsoxlab status`` ne faisait que du SSH. Il capturait la vraie raison de
l'échec, hôte par hôte, puis la jetait pour afficher une phrase qui proposait
deux causes à la fois (« cloud-init tourne peut-être encore, ou alors
reprovisionne »). L'apprenant lisait deux devinettes et devait deviner à son
tour, alors que la réponse était à un appel ``virsh`` de distance, sur la
machine même où la commande s'exécutait.

Ce module transforme des **observations** en une **cause unique**. Il ne compose
aucun texte : il rend un code, que la CLI traduit. C'est ce qui permet de le
tester sans terminal, sans libvirt et sans langue.

Deux couches, dans cet ordre :

1. **Ce que dit l'hyperviseur**, quand il peut être interrogé. C'est un fait sur
   la machine, il l'emporte sur tout ce que SSH peut suggérer.
2. **Ce que dit SSH**, sinon. Cette couche seule distingue déjà des situations
   opposées que l'ancien message confondait : ``EHOSTUNREACH`` (« No route to
   host ») dit que *personne* ne répond à cette adresse, ``ECONNREFUSED``
   (« Connection refused ») dit qu'une machine répond et refuse le port. La
   première appelle à regarder la machine, la seconde à attendre.

Aucune couche ne conclut à partir de rien : quand ni l'hyperviseur ni SSH ne
donnent de signe reconnaissable, la cause est ``unknown``, et la raison brute
est rapportée telle quelle.
"""

from __future__ import annotations

from typing import Final

from ..infra.libvirt import DomainStatus

#: L'hôte répond : il n'y a rien à diagnostiquer.
CAUSE_NONE: Final = "reachable"

#: Aucun domaine ne porte ce nom sur l'hyperviseur — le provisionnement n'a
#: jamais créé cette machine.
CAUSE_DOMAIN_ABSENT: Final = "domain_absent"

#: Le domaine existe et n'exécute rien (``shut off``, ``crashed``, ``paused``).
CAUSE_DOMAIN_NOT_RUNNING: Final = "domain_not_running"

#: Le domaine tourne mais libvirt ne lui connaît aucun bail : il boote encore,
#: ou son interface réseau n'a pas abouti.
CAUSE_DOMAIN_NO_LEASE: Final = "domain_no_lease"

#: Le domaine tourne, il a son adresse, et SSH n'ouvre pas encore : cloud-init
#: n'a pas fini.
CAUSE_BOOTING: Final = "booting"

#: Quelque chose répond à cette adresse et refuse la connexion (ECONNREFUSED) :
#: la machine est debout, ``sshd`` n'écoute pas.
CAUSE_SSH_REFUSED: Final = "ssh_refused"

#: Personne ne répond à cette adresse (EHOSTUNREACH) : la machine n'est pas sur
#: le réseau.
CAUSE_UNREACHABLE: Final = "unreachable"

#: L'adresse ne répond pas dans le délai : un filtrage jette les paquets, ou la
#: machine est figée.
CAUSE_SSH_TIMEOUT: Final = "ssh_timeout"

#: SSH aboutit et la clé est refusée : ce n'est ni le réseau ni la machine.
CAUSE_SSH_DENIED: Final = "ssh_denied"

#: Rien de reconnaissable. La raison brute reste affichée, elle.
CAUSE_UNKNOWN: Final = "unknown"

#: Fragments de ``strerror`` observés dans la sortie de ``ssh``, associés à la
#: cause qu'ils désignent. Le rapprochement se fait en minuscules, sur une
#: sortie forcée en ``LC_ALL=C`` par l'appelant — sans ce verrou, la même panne
#: produirait un texte différent selon la langue du poste, et cette table ne
#: reconnaîtrait plus rien.
_SSH_SIGNATURES: Final[tuple[tuple[str, str], ...]] = (
    ("no route to host", CAUSE_UNREACHABLE),
    ("network is unreachable", CAUSE_UNREACHABLE),
    ("host is down", CAUSE_UNREACHABLE),
    ("connection refused", CAUSE_SSH_REFUSED),
    ("permission denied", CAUSE_SSH_DENIED),
    ("too many authentication failures", CAUSE_SSH_DENIED),
    ("timed out", CAUSE_SSH_TIMEOUT),
    ("timeout", CAUSE_SSH_TIMEOUT),
)


def classify_ssh(reason: str) -> str:
    """La cause que la seule sortie de ``ssh`` permet d'affirmer.

    Args:
        reason: la dernière ligne de ``stderr`` de la tentative SSH.

    Returns:
        Un des ``CAUSE_*``. ``CAUSE_UNKNOWN`` quand rien n'est reconnu — ce qui
        vaut mieux qu'une cause plausible : un diagnostic faux coûte plus cher
        qu'un « je ne sais pas ».
    """
    minuscule = reason.lower()
    for fragment, cause in _SSH_SIGNATURES:
        if fragment in minuscule:
            return cause
    return CAUSE_UNKNOWN


def diagnose(*, reachable: bool, reason: str, status: DomainStatus | None) -> str:
    """La cause unique d'un hôte, des faits les plus solides aux plus faibles.

    Args:
        reachable: la tentative SSH a-t-elle abouti.
        reason: la dernière ligne de ``stderr`` de cette tentative.
        status: ce que l'hyperviseur dit de cet hôte, ou ``None`` quand il n'a
            pas pu être interrogé (provider sans état interrogeable, ``virsh``
            absent, ``sudo`` refusé, démon éteint). ``None`` veut dire « je
            n'ai pas pu regarder », **jamais** « rien n'existe » : la fonction
            retombe alors sur ce que SSH sait, elle ne conclut pas à l'absence.

    Returns:
        Un des ``CAUSE_*``.
    """
    if reachable:
        return CAUSE_NONE
    if status is not None:
        if not status.exists:
            return CAUSE_DOMAIN_ABSENT
        if status.state is not None:
            if not status.running:
                return CAUSE_DOMAIN_NOT_RUNNING
            if not status.addresses:
                return CAUSE_DOMAIN_NO_LEASE
            # Le domaine tourne et porte son adresse : la machine est là. Reste
            # à savoir si SSH n'est pas encore ouvert (cloud-init) ou s'il est
            # ouvert et refuse la clé — deux gestes différents.
            cause_ssh = classify_ssh(reason)
            return CAUSE_SSH_DENIED if cause_ssh == CAUSE_SSH_DENIED else CAUSE_BOOTING
        # Domaine résolu mais état illisible : on sait qu'il existe, pas plus.
        # Affirmer davantage serait inventer.
    return classify_ssh(reason)
