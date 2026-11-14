"""Ce que le catalogue déclare : ses labs, sa racine, ses labs ``vm``.

Extrait de ``services/doctor.py`` (issue #199), sans changement de
comportement. Voir ce module pour les principes du diagnostic.
"""

from __future__ import annotations

from pathlib import Path

from ...i18n import _
from ...models import LabDefinition
from ...models.runtime import RuntimeType
from .modele import Check, _check

#: Types de runtime qui exigent une VM provisionnée. Les deux alias
#: historiques comptent autant que la valeur cible.
_VM_RUNTIMES = frozenset({RuntimeType.VM, RuntimeType.KVM, RuntimeType.INCUS})


def _check_labs(
    root: Path,
    labs: list[LabDefinition],
    vus: int,
    *,
    infra_declaree: bool = False,
) -> Check:
    """Le compte des labs, et **ce qui manque** quand il ne colle pas.

    Un « 0 lab » muet oblige l'utilisateur à retrouver seul une information que
    `list-labs` possède déjà. Trois causes rendent un lab invisible : un
    `schema_version` trop récent, un `lab.yaml` qui lève au parsing, ou un lab
    déclaré dans le `meta.yml` mais absent du disque. Plutôt que de deviner
    laquelle s'applique, on compare les fichiers présents aux labs chargés :
    l'écart les couvre toutes les trois.

    ``infra_declaree`` dit qu'un bloc ``infra.hosts`` existe. Zéro lab n'est
    alors pas un défaut mais la description du dépôt (issue #230) : une stack de
    VM jetables n'a aucune raison de porter un exercice, et ce rouge était le
    seul que voyait son utilisateur.
    """
    ecart = vus - len(labs)
    if not labs and infra_declaree:
        return _check("labs", True, _("detail_labs_infra_seule", root=root))

    detail = _("detail_labs_count", count=len(labs))
    if ecart > 0:
        detail += " " + _("detail_labs_ecart", ecart=ecart, presents=vus)
    # Seul un écart POSITIF dit quelque chose : des fichiers présents que le
    # moteur n'a pas su charger. L'inverse ne peut pas venir d'un catalogue réel,
    # et vaut zéro information.
    #
    # La remédiation n'est pas la même selon la cause, et c'est tout l'intérêt
    # de la distinguer : **aucun** fichier vu, c'est qu'il n'y a pas de
    # catalogue ici, et le geste est d'en poser un ; des fichiers vus mais non
    # chargés, c'est un contrat à corriger. Sans elle, ce rouge arrivait nu sur
    # un poste neuf, juste après une installation réussie, et rien ne disait
    # quoi faire.
    if vus == 0:
        geste = _("remediation_labs_aucun_catalogue")
    elif ecart > 0:
        geste = _("remediation_labs_illisibles")
    else:
        geste = ""
    return _check("labs", len(labs) > 0 and ecart <= 0, detail, hint=geste)


def _check_lab_home(root: Path) -> Check:
    return _check("lab_home", True, str(root))


# ── assemblage ────────────────────────────────────────────────────────────────

def uses_vm(labs: list[LabDefinition]) -> bool:
    """Ce dépôt a-t-il au moins un lab qui exige une VM provisionnée ?"""
    return any(lab.runtime.type in _VM_RUNTIMES for lab in labs)
