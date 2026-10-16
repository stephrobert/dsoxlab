"""Ce que ``doctor --fix`` va jouer, et ce qui l'en empêche.

La décision et l'exécution vivaient dans la commande, qui pesait 56 de
complexité cognitive pour 121 lignes : elle partageait les correctifs en deux
familles, vérifiait les préconditions de sudo, lançait la cascade, classait
chaque sortie, puis rejugeait le tout pour ``--strict``. Rien de cela n'est du
câblage, et rien n'était joignable par un test sans passer par la CLI.

Trois règles portent tout le module, et chacune vient d'un défaut constaté :

1. **Un correctif ``MANUAL`` n'est jamais exécuté.** Le geste appartient à
   l'humain ; ``--fix`` se contente de le nommer.
2. **Un échec n'arrête pas la cascade.** ``--fix`` répare plusieurs choses
   indépendantes : lever sur la première qui rate abandonnerait les autres.
3. **Un succès à effet différé le dit.** Un ``usermod -aG`` réussi laisse la
   ligne rouge jusqu'à la reconnexion. Sans ce message, l'utilisateur relance
   ``doctor``, revoit le même rouge, et conclut que le correctif a échoué.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .doctor import DoctorReport, Fix, FixKind

#: Signature d'un exécuteur de correctif : il rend le code de retour. Elle est
#: injectable pour que les tests décrivent une cascade sans toucher la machine,
#: ce que l'ancienne forme interdisait.
Executeur = Callable[[Fix], int]


@dataclass(frozen=True)
class PlanCorrection:
    """Les correctifs disponibles, rangés par ce qu'on a le droit d'en faire."""

    manuels: tuple[tuple[str, Fix], ...] = ()
    executables: tuple[tuple[str, Fix], ...] = ()

    @property
    def vide(self) -> bool:
        return not self.manuels and not self.executables

    @property
    def correctifs_sudo(self) -> int:
        return sum(1 for _label, fix in self.executables if fix.requires_sudo)


@dataclass(frozen=True)
class Application:
    """Un correctif joué, et ce qu'il faut en dire."""

    label: str
    code: int
    kind: FixKind

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def avis_differe(self) -> str | None:
        """La clé du message à afficher quand l'effet n'est pas immédiat."""
        if not self.ok:
            return None
        if self.kind is FixKind.NEEDS_RELOGIN:
            return "fix_needs_relogin"
        if self.kind is FixKind.NEEDS_REBOOT:
            return "fix_needs_reboot"
        return None


def planifier(report: DoctorReport) -> PlanCorrection:
    """Partage les correctifs du rapport entre « à dire » et « à jouer »."""
    manuels: list[tuple[str, Fix]] = []
    executables: list[tuple[str, Fix]] = []
    for controle in report.fixable():
        if controle.fix is None:
            continue
        cible = manuels if controle.fix.kind is FixKind.MANUAL else executables
        cible.append((controle.label, controle.fix))
    return PlanCorrection(tuple(manuels), tuple(executables))


def obstacle(plan: PlanCorrection, *, interactif: bool | None = None) -> str | None:
    """La clé du message qui empêche la cascade, ou ``None`` si la voie est libre.

    Un correctif par sudo a besoin d'un terminal pour demander le mot de passe,
    et de ``sudo`` lui-même. Les deux se vérifient **avant** d'en jouer un seul :
    échouer au milieu d'une cascade laisse la machine dans un état que personne
    n'a décrit.
    """
    if not plan.correctifs_sudo:
        return None
    if interactif is None:
        interactif = sys.stdin.isatty()
    if not interactif:
        return "fix_needs_tty"
    if shutil.which("sudo") is None:
        return "fix_no_sudo"
    return None


def appliquer(
    executables: Iterable[tuple[str, Fix]],
    executer: Executeur,
    *,
    sur_debut: Callable[[str, Fix], None] | None = None,
    sur_resultat: Callable[[Application], None] | None = None,
) -> list[Application]:
    """Joue la cascade entière, sans jamais s'arrêter sur un échec.

    Les deux rappels encadrent chaque correctif, pour que l'appelant rende au
    fil de l'eau : ``sur_debut`` nomme la commande avant qu'elle parte, puisque
    sa sortie va arriver sur le terminal sans rien pour l'annoncer, et
    ``sur_resultat`` dit ce qu'elle a donné. Une cascade de dix correctifs qui
    n'afficherait rien avant la fin donnerait l'impression d'avoir gelé.
    """
    resultats: list[Application] = []
    for label, fix in executables:
        if sur_debut is not None:
            sur_debut(label, fix)
        application = Application(label=label, code=executer(fix), kind=fix.kind)
        resultats.append(application)
        if sur_resultat is not None:
            sur_resultat(application)
    return resultats
