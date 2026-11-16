"""Du diagnostic aux étapes : ce qui manque, dans l'ordre où le faire.

Le tableau d'avant listait des composants ; l'apprenant devait deviner l'ordre,
et relancer ``doctor`` après chaque geste pour découvrir le suivant (parcours
mesurés le 2026-11-16 sur Ubuntu 24.04 et AlmaLinux 10). Ce module range les
contrôles en **étapes numérotées** :

- une étape par remède : deux lignes rouges qui se réparent par la même
  commande (``/dev/kvm`` fermé et groupe libvirt absent) sont une seule étape ;
- dans l'ordre des dépendances de la table des remèdes (libvirt avant son
  pool, Ansible avant ses collections) ;
- un contrôle qui attend une autre étape le dit : « faire l'étape N d'abord ».

L'affichage et ``--fix`` lisent tous deux ces étapes : ce qui est montré est
ce qui est joué, dans le même ordre.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .doctor_controles.modele import STATE_OK, STATE_UNKNOWN, Check, DoctorReport
from .doctor_controles.remedes import Remede, rang


@dataclass
class Etape:
    """Une chose à faire : ses contrôles, sa commande, et ce qu'elle attend."""

    cle: str
    """La clé du remède (``kvm``, ``groupes``…), ou celle du contrôle sans remède."""

    controles: list[Check]
    remede: Remede | None
    numero: int = 0
    apres: int | None = None
    """Le numéro de l'étape à faire d'abord, quand un contrôle l'attend."""

    facultative: bool = False
    """Un composant que ce catalogue n'exige pas (Docker, Incus) : seulement
    avec ``--fix --clients``."""

    @property
    def detail(self) -> str:
        return self.controles[0].detail

    @property
    def manuelle(self) -> bool:
        """Rien à lancer : un geste que seul l'humain peut faire (BIOS, reconnexion)."""
        return self.remede is None or not self.remede.lignes


@dataclass
class Plan:
    """Les étapes du diagnostic, et ce qui n'en est pas une."""

    etapes: list[Etape] = field(default_factory=list)
    facultatives: list[Etape] = field(default_factory=list)
    non_mesures: list[Check] = field(default_factory=list)
    """Une sonde muette sans étape à attendre : ni vert, ni étape. Le dire,
    plutôt que de conclure « tout est prêt » sur une mesure qui n'a pas eu lieu."""

    prets: list[Check] = field(default_factory=list)

    def etape_de(self, cle_controle: str) -> Etape | None:
        for etape in self.etapes:
            if any(c.key == cle_controle for c in etape.controles):
                return etape
        return None


def _a_faire(check: Check) -> bool:
    """Le contrôle demande-t-il un geste ?

    ``unknown`` n'en demande que s'il attend une étape (``apres``) : une sonde
    muette sans cause connue n'a pas de remède, elle se remesure.
    """
    if check.state == STATE_OK:
        return False
    if check.state == STATE_UNKNOWN:
        return check.apres is not None
    return True


def _regrouper(checks: list[Check], *, facultative: bool) -> list[Etape]:
    """Une étape par clé de remède, dans l'ordre des dépendances."""
    par_cle: dict[str, Etape] = {}
    for check in checks:
        cle = check.remede.cle if check.remede is not None else check.key
        etape = par_cle.get(cle)
        if etape is None:
            par_cle[cle] = Etape(cle, [check], check.remede, facultative=facultative)
            continue
        etape.controles.append(check)
        # Le remède retenu est celui du contrôle qui porte la clé : le contrôle
        # des groupes ajoute libvirt à kvm, celui de /dev/kvm ne connaît que kvm.
        if check.key == cle and check.remede is not None:
            etape.remede = check.remede
    position = {id(c): i for i, c in enumerate(checks)}
    return sorted(
        par_cle.values(),
        key=lambda e: (rang(e.cle), position[id(e.controles[0])]),
    )


def construire(report: DoctorReport) -> Plan:
    """Range le diagnostic en étapes numérotées."""
    plan = Plan()
    a_faire = [c for c in report.required if _a_faire(c)]
    plan.etapes = _regrouper(a_faire, facultative=False)
    for numero, etape in enumerate(plan.etapes, start=1):
        etape.numero = numero
    for etape in plan.etapes:
        attendues = [
            prealable.numero
            for c in etape.controles if c.apres
            if (prealable := plan.etape_de(c.apres)) is not None
            and prealable.numero < etape.numero
        ]
        etape.apres = max(attendues) if attendues else None

    plan.non_mesures = [
        c for c in report.required if c.state == STATE_UNKNOWN and c.apres is None
    ]
    plan.prets = [c for c in report.required if c.state == STATE_OK]
    facultatifs = [c for c in report.optional if not c.ok and c.remede is not None]
    plan.facultatives = _regrouper(facultatifs, facultative=True)
    return plan
