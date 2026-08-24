"""L'état d'un lab, calculé à un seul endroit.

« Où en suis-je ? » n'avait pas de réponse dans l'outil. L'état existait, mais
éparpillé : le contexte actif dans un JSON, la note dans une base SQLite, le
répertoire de travail sur le disque, les conteneurs chez Docker. Chaque commande
en reconstituait un morceau à sa façon, donc aucune ne pouvait répondre.

Cinq états, et une seule fonction qui les calcule :

    non commencé ──run──▶ prêt ──travail──▶ en cours ──note──▶ validé
                             │                  │                │
                             └──────────────────┴────────────────┘
                                    dépendance tombée
                                            ▼
                                        dégradé

``dégradé`` n'est pas une étape du parcours mais un constat qui se superpose : un
service déclaré qui ne tourne plus rend le lab injouable, quel que soit
l'avancement. Il prime donc sur les autres, parce que c'est la seule information
qui appelle un geste immédiat.

**Le jeton et le libellé sont séparés**, comme pour ``doctor`` : ``state`` est
stable et se lit sans traduire, ``label`` est traduit et se lit avec les yeux.
Une intégration qui filtre sur « validé » ne doit pas dépendre de la langue de
qui a lancé la commande.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..config import xdg_state_home
from ..i18n import _
from ..locking import lock_identity
from ..models.lab import LabDefinition
from ..models.runtime import RuntimeType
from ..sessions import store

#: Rien n'a encore été préparé pour ce lab.
NOT_STARTED = "not_started"
#: L'environnement est prêt, et rien n'y a été touché.
READY = "ready"
#: Le travail a commencé : le répertoire de travail diffère de ce que `run` y a posé.
IN_PROGRESS = "in_progress"
#: Une note a été obtenue par `check` ou `submit`.
VALIDATED = "validated"
#: Une dépendance déclarée est tombée : le lab est injouable en l'état.
DEGRADED = "degraded"

#: Ordre de parcours, pour les affichages qui veulent une progression.
ETATS = (NOT_STARTED, READY, IN_PROGRESS, VALIDATED)


@dataclass(frozen=True)
class LabState:
    """L'état d'un lab, et de quoi le dire à un humain comme à un programme."""

    lab_id: str
    state: str
    label: str
    detail: str
    best_score: int | None = None
    max_score: int | None = None


def _empreintes_dir(root: Path) -> Path:
    """Où les empreintes de départ sont retenues.

    Sous ``XDG_STATE_HOME`` et non dans le lab : c'est un état recalculable,
    dont la perte coûte au pire un état affiché « prêt » là où le travail avait
    commencé. L'écrire dans le catalogue le ferait apparaître dans un
    ``git status``, ou pire, dans un commit d'apprenant.
    """
    return xdg_state_home() / "dsoxlab" / lock_identity(root) / "labs"


def _empreinte_workdir(workdir: Path) -> str:
    """Empreinte du contenu d'un répertoire de travail.

    Les chemins **et** le contenu : renommer un fichier est un travail, en vider
    un aussi. Les mtimes en sont exclus à dessein, une copie ou un `touch` ne
    devant pas passer pour du travail.
    """
    digest = hashlib.sha256()
    if not workdir.is_dir():
        return ""
    for chemin in sorted(workdir.rglob("*")):
        relatif = chemin.relative_to(workdir).as_posix()
        digest.update(relatif.encode("utf-8"))
        if chemin.is_file():
            try:
                digest.update(chemin.read_bytes())
            except OSError:
                # Un fichier illisible reste une différence observable : on note
                # son chemin, déjà pris en compte, et on continue.
                continue
    return digest.hexdigest()


#: Marque posée pour un lab dont le travail n'est pas observable localement.
_PREPARE = "prepare"


def enregistrer_depart(root: Path, lab: LabDefinition) -> None:
    """Retient le point de départ au moment où `run` vient de préparer le lab.

    Sans lui, « en cours » serait indistinguable de « prêt » : un répertoire de
    travail existe dès que `run` l'a créé, qu'on y ait touché ou non.

    Pour un lab ``shell``, ce point de départ est l'empreinte du travail. Pour un
    lab ``vm``, le travail se fait sur la machine et aucune empreinte locale ne
    le verrait : on retient alors une simple marque, qui dit que la préparation
    a eu lieu et rien de plus.
    """
    if lab.runtime.type is RuntimeType.SHELL:
        workdir = (lab.path / lab.runtime.workdir).resolve()
        contenu = _empreinte_workdir(workdir)
    else:
        contenu = _PREPARE
    fichier = _empreintes_dir(root) / f"{lab.id}.sha256"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(contenu + "\n", encoding="utf-8")


def _depart_connu(root: Path, lab_id: str) -> str | None:
    fichier = _empreintes_dir(root) / f"{lab_id}.sha256"
    try:
        return fichier.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def oublier_depart(root: Path, lab_id: str) -> None:
    """Efface le point de départ, quand `clean` ou `reset` défait la préparation."""
    fichier = _empreintes_dir(root) / f"{lab_id}.sha256"
    try:
        fichier.unlink()
    except OSError:
        return


def _services_degrades(lab: LabDefinition, repo_id: str) -> list[str]:
    """Les services déclarés qui ne tournent plus.

    On n'interroge Docker que si le lab en déclare : un catalogue sans service
    ne doit pas payer un appel, ni virer au rouge parce que Docker est absent
    d'une machine qui n'en a pas besoin.
    """
    if not lab.runtime.services:
        return []
    from ..runtimes import services as svc

    if not svc.docker_available():
        return []
    tombes: list[str] = []
    for service in lab.runtime.services:
        etat = svc.status(service, repo_id)
        # `absent` n'est pas une dégradation : le lab n'a simplement pas été
        # démarré. C'est un service qui a existé puis s'est arrêté qui l'est.
        if etat.detail == "stopped":
            tombes.append(service.name)
    return tombes


def calculer(root: Path, lab: LabDefinition, repo_id: str) -> LabState:
    """L'état d'un lab, et lui seul : aucune commande ne doit le recalculer.

    L'ordre des questions est l'ordre de ce qui prime. Une dégradation d'abord,
    puisqu'elle appelle un geste immédiat quel que soit l'avancement ; la note
    ensuite, parce qu'un lab validé le reste ; puis le travail, puis la simple
    préparation.
    """
    scores = store.get_best_scores(root, [lab.id])
    meilleur, maximum = scores.get(lab.id, (None, None))

    tombes = _services_degrades(lab, repo_id)
    if tombes:
        return LabState(
            lab_id=lab.id, state=DEGRADED,
            label=_("lab_state_degraded"),
            detail=_("lab_state_degraded_detail", services=", ".join(sorted(tombes))),
            best_score=meilleur, max_score=maximum,
        )

    if meilleur is not None:
        return LabState(
            lab_id=lab.id, state=VALIDATED,
            label=_("lab_state_validated"),
            detail=_("lab_state_validated_detail", score=meilleur, max=maximum),
            best_score=meilleur, max_score=maximum,
        )

    if lab.runtime.type is RuntimeType.SHELL:
        workdir = (lab.path / lab.runtime.workdir).resolve()
        if not workdir.is_dir():
            return LabState(
                lab_id=lab.id, state=NOT_STARTED,
                label=_("lab_state_not_started"),
                detail=_("lab_state_not_started_detail", lab=lab.id),
            )
        depart = _depart_connu(root, lab.id)
        if depart is not None and depart != _empreinte_workdir(workdir):
            return LabState(
                lab_id=lab.id, state=IN_PROGRESS,
                label=_("lab_state_in_progress"),
                detail=_("lab_state_in_progress_detail", path=str(workdir)),
            )
        return LabState(
            lab_id=lab.id, state=READY,
            label=_("lab_state_ready"),
            detail=_("lab_state_ready_detail", path=str(workdir)),
        )

    # Runtime vm : le travail se fait sur la machine, hors de portée d'une
    # empreinte locale. Le point de départ enregistré par `run` dit donc
    # seulement que la préparation a eu lieu.
    if _depart_connu(root, lab.id) is not None:
        return LabState(
            lab_id=lab.id, state=IN_PROGRESS,
            label=_("lab_state_in_progress"),
            detail=_("lab_state_in_progress_vm"),
        )
    return LabState(
        lab_id=lab.id, state=NOT_STARTED,
        label=_("lab_state_not_started"),
        detail=_("lab_state_not_started_detail", lab=lab.id),
    )
