"""Arrêter, geler et relancer les machines d'un catalogue, sans les détruire.

``provision`` crée les machines et ``destroy`` les supprime avec leurs disques.
Entre les deux, il manquait le geste le plus courant : rendre la mémoire de
l'hôte le temps d'autre chose, puis reprendre là où on en était (issue #405).

Trois actions :

* ``stop`` arrête proprement le système invité. Les disques restent, la mémoire
  est rendue. ``force`` coupe l'alimentation d'une machine qui n'a pas fini de
  s'arrêter dans le délai : c'est une coupure, jamais une suppression ;
* ``pause`` gèle la machine. Le CPU est rendu, **pas** la mémoire ;
* ``start`` relance une machine arrêtée, ou reprend une machine gelée.

Le périmètre est celui de :func:`machines` : les hôtes que le ``meta.yml``
courant déclare (communs et optionnels) et qui existent sur l'hyperviseur. Une
machine que ce catalogue ne déclare pas n'est jamais touchée, même si elle
porte un nom voisin.

Seuls ``kvm`` et ``incus`` ont un hyperviseur local à piloter. ``outscale`` est
refusé par :class:`ProviderSansAlimentation`, plutôt que de laisser croire
qu'une commande sans effet a réussi.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from ..models.repo import RepoMetadata
from ..utils.shell import CommandError, CommandResult, run_command
from . import libvirt

logger = logging.getLogger(__name__)

Action = Literal["stop", "pause", "start"]

#: Les providers dont les machines se pilotent ici.
PROVIDERS = frozenset({"kvm", "incus"})

#: Délai par défaut d'un arrêt propre, en secondes. Un système invité ordinaire
#: s'arrête en moins de 30 s ; un nœud qui vide ses conteneurs peut en prendre
#: davantage, et le dépasser n'est pas encore un échec si ``force`` est demandé.
DELAI_ARRET = 120

#: Intervalle entre deux lectures d'état pendant l'attente d'un arrêt.
_PAS = 2.0

#: Délai d'une commande d'hyperviseur unitaire (suspend, start, resume…).
_DELAI_COMMANDE = 60


class Etat(StrEnum):
    """L'état d'une machine, ramené à ce qui décide du geste."""

    MARCHE = "marche"
    GELEE = "gelee"
    ARRETEE = "arretee"
    AUTRE = "autre"


class Issue(StrEnum):
    """Ce qui est arrivé à une machine."""

    FAIT = "fait"
    COUPEE = "coupee"
    DEJA = "deja"
    IGNOREE = "ignoree"
    ECHEC = "echec"


@dataclass(frozen=True)
class Resultat:
    """Le sort d'une machine. ``cause`` porte la sortie brute de l'hyperviseur."""

    host: str
    issue: Issue
    etat_avant: Etat
    cause: str = ""
    delai_depasse: bool = False


class ProviderSansAlimentation(RuntimeError):
    """Le provider actif n'a pas d'hyperviseur local à piloter."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(provider)


class _Pilote(Protocol):
    """Ce qu'un provider doit savoir faire pour être piloté ici."""

    def lister(self) -> list[str]: ...
    def nom(self, fqdn: str, connus: list[str]) -> str | None: ...
    def etat(self, nom: str) -> Etat: ...
    def arreter(self, nom: str) -> CommandResult: ...
    def couper(self, nom: str) -> CommandResult: ...
    def geler(self, nom: str) -> CommandResult: ...
    def demarrer(self, nom: str) -> CommandResult: ...
    def reprendre(self, nom: str) -> CommandResult: ...


class _Kvm:
    """Les domaines libvirt, par le chemin d'accès que :mod:`libvirt` a détecté."""

    def __init__(self, delai_arret: int) -> None:
        self._delai_arret = delai_arret

    def lister(self) -> list[str]:
        return libvirt.list_domains()

    def nom(self, fqdn: str, connus: list[str]) -> str | None:
        return libvirt.existing_domains([fqdn], known=connus).get(fqdn)

    def etat(self, nom: str) -> Etat:
        brut = libvirt.domain_state(nom)
        if brut in libvirt.RUNNING_STATES:
            return Etat.MARCHE
        if brut == "paused":
            return Etat.GELEE
        if brut == "shut off":
            return Etat.ARRETEE
        return Etat.AUTRE

    def _virsh(self, *args: str) -> CommandResult:
        return libvirt.run_virsh(list(args), check=False, timeout=_DELAI_COMMANDE)

    def arreter(self, nom: str) -> CommandResult:
        # `shutdown` rend la main tout de suite : l'attente se fait ensuite, sur
        # toutes les machines à la fois, au lieu de les arrêter l'une après l'autre.
        return self._virsh("shutdown", nom)

    def couper(self, nom: str) -> CommandResult:
        # `virsh destroy` coupe l'alimentation. Il ne supprime rien : le domaine
        # et ses disques restent définis, malgré le nom de la sous-commande.
        return self._virsh("destroy", nom)

    def geler(self, nom: str) -> CommandResult:
        return self._virsh("suspend", nom)

    def demarrer(self, nom: str) -> CommandResult:
        return self._virsh("start", nom)

    def reprendre(self, nom: str) -> CommandResult:
        return self._virsh("resume", nom)


class _Incus:
    """Les instances Incus, nommées d'après le FQDN dont les points deviennent des tirets."""

    def __init__(self, delai_arret: int) -> None:
        self._delai_arret = delai_arret

    def _incus(self, *args: str, timeout: int = _DELAI_COMMANDE) -> CommandResult:
        return run_command(["incus", *args], check=False, timeout=timeout)

    def lister(self) -> list[str]:
        resultat = self._incus("list", "--format", "csv", "--columns", "n")
        if not resultat.ok:
            raise CommandError(["incus", "list"], resultat)
        return [ligne.strip() for ligne in resultat.stdout.splitlines() if ligne.strip()]

    def nom(self, fqdn: str, connus: list[str]) -> str | None:
        # Le template incus remplace les points par des tirets (main.tf).
        candidat = fqdn.replace(".", "-")
        return candidat if candidat in connus else None

    def etat(self, nom: str) -> Etat:
        resultat = self._incus("list", f"^{nom}$", "--format", "csv", "--columns", "s")
        brut = resultat.stdout.strip().upper() if resultat.ok else ""
        return {
            "RUNNING": Etat.MARCHE,
            "FROZEN": Etat.GELEE,
            "STOPPED": Etat.ARRETEE,
        }.get(brut, Etat.AUTRE)

    def arreter(self, nom: str) -> CommandResult:
        # `incus stop` attend lui-même l'arrêt, borné par son propre délai.
        return self._incus(
            "stop", nom, "--timeout", str(self._delai_arret),
            timeout=self._delai_arret + 30,
        )

    def couper(self, nom: str) -> CommandResult:
        return self._incus("stop", nom, "--force")

    def geler(self, nom: str) -> CommandResult:
        return self._incus("pause", nom)

    def demarrer(self, nom: str) -> CommandResult:
        return self._incus("start", nom)

    def reprendre(self, nom: str) -> CommandResult:
        return self._incus("resume", nom)


def _pilote(provider: str, delai_arret: int) -> _Pilote:
    if provider == "kvm":
        return _Kvm(delai_arret)
    if provider == "incus":
        return _Incus(delai_arret)
    raise ProviderSansAlimentation(provider)


def machines(
    repo_meta: RepoMetadata,
    provider: str,
    hotes: Iterable[str] | None = None,
    *,
    pilote: _Pilote | None = None,
) -> dict[str, str]:
    """Les machines de ce catalogue qui existent : ``{fqdn: nom côté hyperviseur}``.

    Args:
        hotes: restreint aux FQDN donnés, qui doivent être déclarés. ``None``
            prend tous les hôtes déclarés, communs et optionnels.

    Raises:
        ProviderSansAlimentation: si le provider n'a rien à piloter ici.
        CommandError: si l'hyperviseur ne répond pas. Ce n'est pas une
            absence de machine, et l'appelant ne doit pas le dire ainsi.
    """
    p = pilote or _pilote(provider, DELAI_ARRET)
    declares = [h.name for h in repo_meta.infra.hosts]
    vises = declares if hotes is None else [h for h in declares if h in set(hotes)]
    connus = p.lister()
    trouves: dict[str, str] = {}
    for fqdn in vises:
        nom = p.nom(fqdn, connus)
        if nom is not None:
            trouves[fqdn] = nom
    return trouves


def resoudre_hotes(demandes: Iterable[str], declares: list[str]) -> tuple[list[str], list[str]]:
    """Ramène chaque nom demandé à un hôte déclaré : ``(trouvés, inconnus)``.

    Le FQDN exact, ou le nom court quand un seul hôte déclaré le porte
    (``k8s-cp`` pour ``k8s-cp.lab``). Un nom court partagé par deux hôtes
    reste inconnu : deviner lequel viser serait arrêter la mauvaise machine.
    """
    trouves: list[str] = []
    inconnus: list[str] = []
    for nom in demandes:
        choix = [nom] if nom in declares else [h for h in declares if h.split(".", 1)[0] == nom]
        if len(choix) == 1:
            if choix[0] not in trouves:
                trouves.append(choix[0])
        else:
            inconnus.append(nom)
    return trouves, inconnus


def _sortie(resultat: CommandResult) -> str:
    return (resultat.stderr or resultat.stdout).strip()


def _reprendre_si_gelee(p: _Pilote, fqdn: str, nom: str, avant: Etat) -> Resultat | None:
    """Une machine gelée n'exécute rien : elle ne verrait pas la demande d'arrêt."""
    if avant is not Etat.GELEE:
        return None
    r = p.reprendre(nom)
    if r.ok:
        return None
    return Resultat(fqdn, Issue.ECHEC, avant, _sortie(r))


def _lancer_arret(p: _Pilote, fqdn: str, nom: str, avant: Etat, *, force: bool) -> Resultat | None:
    """Demande l'arrêt propre. ``None`` : la machine est en cours d'arrêt."""
    if avant is Etat.ARRETEE:
        return Resultat(fqdn, Issue.DEJA, avant)
    refus = _reprendre_si_gelee(p, fqdn, nom, avant)
    if refus is not None:
        return refus
    r = p.arreter(nom)
    if not r.ok and not force:
        return Resultat(fqdn, Issue.ECHEC, avant, _sortie(r))
    return None


def _attendre_arret(
    p: _Pilote,
    en_cours: dict[str, str],
    *,
    delai: int,
    horloge: Callable[[], float],
    dormir: Callable[[float], None],
) -> set[str]:
    """Les FQDN arrêtés avant l'échéance. ``en_cours`` garde ceux qui tournent encore."""
    arretes: set[str] = set()
    echeance = horloge() + delai
    while en_cours:
        for fqdn in [f for f, n in en_cours.items() if p.etat(n) is Etat.ARRETEE]:
            arretes.add(fqdn)
            del en_cours[fqdn]
        if not en_cours or horloge() >= echeance:
            break
        dormir(_PAS)
    return arretes


def _couper(p: _Pilote, fqdn: str, nom: str, avant: Etat, delai: int) -> Resultat:
    logger.warning("%s did not shut down within %ss, cutting power", fqdn, delai)
    r = p.couper(nom)
    if r.ok or p.etat(nom) is Etat.ARRETEE:
        return Resultat(fqdn, Issue.COUPEE, avant)
    return Resultat(fqdn, Issue.ECHEC, avant, _sortie(r))


def _arreter(
    p: _Pilote,
    cibles: dict[str, str],
    etats: dict[str, Etat],
    *,
    force: bool,
    delai: int,
    horloge: Callable[[], float],
    dormir: Callable[[float], None],
) -> list[Resultat]:
    resultats: dict[str, Resultat] = {}
    en_cours: dict[str, str] = {}
    for fqdn, nom in cibles.items():
        tranche = _lancer_arret(p, fqdn, nom, etats[fqdn], force=force)
        if tranche is None:
            en_cours[fqdn] = nom
        else:
            resultats[fqdn] = tranche

    for fqdn in _attendre_arret(p, en_cours, delai=delai, horloge=horloge, dormir=dormir):
        resultats[fqdn] = Resultat(fqdn, Issue.FAIT, etats[fqdn])

    for fqdn, nom in en_cours.items():
        resultats[fqdn] = (
            _couper(p, fqdn, nom, etats[fqdn], delai)
            if force
            else Resultat(fqdn, Issue.ECHEC, etats[fqdn], delai_depasse=True)
        )
    return [resultats[f] for f in cibles]


def _geler(p: _Pilote, fqdn: str, nom: str, avant: Etat) -> Resultat:
    if avant is Etat.GELEE:
        return Resultat(fqdn, Issue.DEJA, avant)
    if avant is not Etat.MARCHE:
        # Rien ne tourne : il n'y a rien à geler, et ce n'est pas une panne.
        return Resultat(fqdn, Issue.IGNOREE, avant)
    r = p.geler(nom)
    return Resultat(fqdn, Issue.FAIT if r.ok else Issue.ECHEC, avant, "" if r.ok else _sortie(r))


def _demarrer(p: _Pilote, fqdn: str, nom: str, avant: Etat) -> Resultat:
    if avant is Etat.MARCHE:
        return Resultat(fqdn, Issue.DEJA, avant)
    r = p.reprendre(nom) if avant is Etat.GELEE else p.demarrer(nom)
    return Resultat(fqdn, Issue.FAIT if r.ok else Issue.ECHEC, avant, "" if r.ok else _sortie(r))


def appliquer(
    action: Action,
    provider: str,
    cibles: dict[str, str],
    *,
    force: bool = False,
    delai: int = DELAI_ARRET,
    pilote: _Pilote | None = None,
    horloge: Callable[[], float] = time.monotonic,
    dormir: Callable[[float], None] = time.sleep,
) -> list[Resultat]:
    """Applique ``action`` à chaque machine de ``cibles``, dans leur ordre.

    Une machine déjà dans l'état demandé rend :attr:`Issue.DEJA`, sans appel à
    l'hyperviseur : relancer la commande ne fait rien de plus, et ne casse rien.

    Raises:
        ProviderSansAlimentation: si le provider n'a rien à piloter ici.
        CommandError: si l'état d'une machine ne peut pas être lu.
    """
    p = pilote or _pilote(provider, delai)
    etats = {fqdn: p.etat(nom) for fqdn, nom in cibles.items()}
    logger.info("infra %s on %s: %s", action, provider, ", ".join(cibles))
    if action == "stop":
        return _arreter(
            p, cibles, etats, force=force, delai=delai, horloge=horloge, dormir=dormir
        )
    if action == "pause":
        return [_geler(p, f, n, etats[f]) for f, n in cibles.items()]
    return [_demarrer(p, f, n, etats[f]) for f, n in cibles.items()]
