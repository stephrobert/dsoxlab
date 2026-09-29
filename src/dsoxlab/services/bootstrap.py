"""Le socle d'un catalogue, joué une fois après le provisionnement.

Un catalogue Kubernetes doit poser un cluster kubeadm avant que le moindre lab
ait un sens : containerd, dépôt `pkgs.k8s.io`, `kubeadm init`, CNI, attente du
nœud `Ready`. Plusieurs minutes, et ce socle n'appartient à **aucun lab** — il
appartient au catalogue.

Faute d'un point d'accroche après le provisionnement, chaque `setup.yaml` devait
inclure `../../shared/kubeadm-cluster.yml`. Trois défauts, énoncés dans l'issue
#213 : un auteur peut l'oublier, et son lab échoue alors sur une machine nue sans
que le message dise pourquoi ; le chemin relatif couple le lab à sa profondeur
dans `labs/`, donc réorganiser les sections casse tous les `setup.yaml` ; et
`reset` rejoue le socle, puisque le point de reprise est pris avant `setup.yaml`.

Ce module comble ce trou. Rien ici ne connaît Kubernetes : le catalogue déclare
`infra.bootstrap`, dsoxlab le joue sur les hôtes de son inventaire.

Pourquoi le point de reprise devient juste, gratuitement
========================================================

Le socle est joué à la fin de `provision`, donc **avant** le point de reprise que
`run` prend juste avant `setup.yaml`. Un `reset` de lab ramène désormais à un
cluster sain plutôt qu'à une machine nue, ce qui est la sémantique utile — et
aucune ligne n'a été écrite pour l'obtenir.

Une fois, et pas une de plus
============================

L'empreinte du playbook est conservée dans l'état du dépôt. Tant qu'elle ne
change pas, le socle n'est pas rejoué : c'est ce que l'issue demande. Quand
l'auteur du catalogue modifie son playbook, elle change, et le socle se rejoue —
ce qui est la seule chose utile à faire d'un socle qui a changé.

Le marqueur **ne s'écrit qu'après un succès**. C'est un invariant du projet, et il
vient d'un incident : le premier démarrage de l'appliance se marquait fait même
quand rien n'avait été installé, ce qui condamnait la machine en silence.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import xdg_state_home
from ..models import RepoMetadata
from ..utils.fichiers import ecrire_atomiquement

logger = logging.getLogger(__name__)

#: Où l'on retient qu'un socle a été posé. Dans l'état du dépôt, comme les
#: empreintes de points de départ des labs : ce n'est ni du contrat, ni du cache
#: — le perdre ferait rejouer un socle, pas disparaître un lab.
FICHIER_ETAT = "bootstrap.json"


class BootstrapAbsent(FileNotFoundError):
    """``infra.bootstrap`` est déclaré et le fichier n'est pas utilisable.

    Même règle que les fixtures d'un lab (issue #177) : un socle déclaré et
    introuvable n'est pas un socle facultatif. Le dire ici, avec le chemin
    attendu, plutôt que de laisser le premier lab échouer sur une machine nue.

    Porte une **clé** de traduction et son paramètre, jamais une phrase : c'est
    la commande qui parle la langue de l'apprenant.
    """

    def __init__(self, cle: str, chemin: str) -> None:
        self.cle = cle
        self.chemin = chemin
        super().__init__(f"{cle}: {chemin}")


@dataclass(frozen=True)
class Verdict:
    """Ce qu'il y avait à faire, et ce qui a été fait."""

    joue: bool
    """Le playbook a-t-il été exécuté cette fois-ci ?"""

    raison: str
    """Clé i18n qui dit pourquoi : joué, déjà à jour, ou rien à faire."""

    empreinte: str = ""
    """L'empreinte du playbook joué, ou celle déjà enregistrée."""


def chemin_du_playbook(repo_meta: RepoMetadata) -> Path | None:
    """Le playbook de socle, ou ``None`` si ce catalogue n'en déclare pas.

    Le chemin est relatif à la racine du dépôt, comme tout ce que le contrat
    déclare. Un chemin absolu ou remontant hors du dépôt est refusé : le contrat
    décrit un catalogue, il ne désigne pas des fichiers de la machine.
    """
    declare = repo_meta.infra.bootstrap.strip()
    if not declare:
        return None

    candidat = Path(declare)
    if candidat.is_absolute() or ".." in candidat.parts:
        raise BootstrapAbsent("bootstrap_hors_depot", declare)
    return repo_meta.path / candidat


def empreinte_du_playbook(chemin: Path) -> str:
    """L'empreinte du contenu, pour savoir si le socle a changé depuis.

    Le contenu et non la date : un `git clone` réécrit les dates de tous les
    fichiers, et un socle inchangé serait rejoué à chaque changement de machine.
    """
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def _fichier_etat(repo_meta: RepoMetadata) -> Path:
    """Sous ``XDG_STATE_HOME``, dans l'état du dépôt, comme le work-dir Terraform.

    Namespacé par ``repo.id`` : deux catalogues posent deux socles, et l'un ne
    doit pas faire croire à l'autre que le sien est en place.
    """
    return xdg_state_home() / "dsoxlab" / repo_meta.id / FICHIER_ETAT


def empreinte_enregistree(repo_meta: RepoMetadata) -> str:
    """L'empreinte du dernier socle posé avec succès, ou une chaîne vide.

    Un fichier illisible vaut « rien d'enregistré » : rejouer un socle
    idempotent coûte du temps, se tromper coûte un lab qui échoue.
    """
    chemin = _fichier_etat(repo_meta)
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(donnees, dict):
        return ""
    valeur = donnees.get("digest")
    return valeur if isinstance(valeur, str) else ""


def enregistrer(repo_meta: RepoMetadata, empreinte: str, hosts: list[str]) -> None:
    """Retient qu'un socle a été posé — appelé **après** un succès, jamais avant."""
    ecrire_atomiquement(
        _fichier_etat(repo_meta),
        json.dumps(
            {"digest": empreinte, "hosts": sorted(hosts)},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )


def oublier(repo_meta: RepoMetadata) -> bool:
    """Efface le marqueur : les machines qui portaient ce socle n'existent plus.

    Appelé par ``destroy``, et ce n'est pas un détail de ménage. Sans lui, le
    marqueur survit à la destruction : un ``provision`` qui reconstruit des
    machines neuves avec un playbook inchangé **saute le socle**, et les labs
    tournent alors sur une machine nue — exactement la panne que ce champ
    devait supprimer.

    Rend ``True`` si un marqueur a été retiré, pour que l'appelant puisse le
    dire. Un marqueur absent n'est pas une anomalie : le catalogue n'en déclare
    peut-être aucun.
    """
    chemin = _fichier_etat(repo_meta)
    try:
        chemin.unlink()
    except FileNotFoundError:
        return False
    except OSError as souci:
        # Ne jamais faire échouer un `destroy` réussi pour un fichier d'état :
        # le pire qui puisse arriver est un socle rejoué, qui est idempotent.
        logger.warning("could not remove the bootstrap marker: %s", souci)
        return False
    return True


def a_jouer(repo_meta: RepoMetadata, *, force: bool = False) -> tuple[Path, str] | None:
    """Le playbook à jouer et son empreinte, ou ``None`` s'il n'y a rien à faire.

    Rend ``None`` dans deux cas qui n'ont rien à voir et que l'appelant distingue
    par son message : le catalogue ne déclare pas de socle, ou le socle déjà posé
    est à jour.

    Lève :class:`BootstrapAbsent` quand le fichier déclaré n'existe pas.
    """
    chemin = chemin_du_playbook(repo_meta)
    if chemin is None:
        return None
    if not chemin.is_file():
        raise BootstrapAbsent("bootstrap_absent", str(chemin))

    empreinte = empreinte_du_playbook(chemin)
    if not force and empreinte == empreinte_enregistree(repo_meta):
        return None
    return chemin, empreinte


def inventaire_du_socle(inventaire: dict[str, Any]) -> dict[str, Any]:
    """L'inventaire tel que le socle le reçoit : tous les hôtes du dépôt.

    Un socle vise le **catalogue**, pas un lab : il n'y a donc pas de groupe
    ``lab_target`` à respecter ici. Les playbooks de socle ciblent ``all`` ou
    ``labenv``, les deux groupes que l'inventaire porte déjà.
    """
    return inventaire
