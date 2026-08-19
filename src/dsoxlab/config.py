"""Configuration globale : résolution de LAB_HOME, chemins et contexte actif."""

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_CONTEXT_FILE = ".dsoxlab-context.json"


@dataclass
class ActiveContext:
    section: str | None = None
    level: str | None = None
    lang: str | None = None
    active_lab: str | None = None
    active_target: str | None = None
    active_provider: str | None = None
    """Provider sélectionné par ``dsoxlab use <name>``. Override par
    ``DSOXLAB_PROVIDER`` env var. Lu par ``read_repo_metadata`` pour
    résoudre ``infra.provider`` quand ``meta.yml`` en déclare plusieurs."""
    course_pos: int = 0  # 1-based index of last section read (0 = not started)

    def label(self) -> str:
        if self.section and self.level:
            return f"{self.section}/{self.level}"
        if self.section:
            return self.section
        return "(aucun)"


def xdg_state_home() -> Path:
    """Racine XDG des données d'état, celles qui survivent à un redémarrage.

    Publique et unique : le work-dir Terraform, le journal et tout ce qui
    viendra ensuite doivent atterrir sous la même racine, sinon un
    ``XDG_STATE_HOME`` personnalisé n'en déplace qu'une partie.
    """
    env = os.environ.get("XDG_STATE_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".local" / "state"


def get_context_path(root: Path) -> Path:
    return root / _CONTEXT_FILE


def _texte(valeur: object) -> str | None:
    """Un champ texte du contexte, ou ``None`` si la valeur n'en est pas un.

    Ce fichier est écrit par l'outil, mais rien ne garantit son contenu : un
    éditeur, une résolution de conflit, un disque plein ou une copie entre
    machines peuvent le laisser dans n'importe quel état. Une valeur d'un autre
    type se propagerait ensuite dans toute la CLI, loin de sa cause.
    """
    return valeur if isinstance(valeur, str) else None


def _position(valeur: object) -> int:
    """La position de lecture du cours, jamais négative.

    ``int(valeur)`` levait ``TypeError`` sur ``null`` et ``ValueError`` sur
    ``"foo"``, deux exceptions que le ``except`` ne couvrait pas : un contexte
    corrompu faisait alors planter la CLI **entière**, y compris les commandes
    qui n'ont rien à voir avec le cours.
    """
    # bool est un int en Python : `true` deviendrait la position 1, ce qui est
    # une coïncidence de typage, pas une intention.
    if isinstance(valeur, bool):
        return 0
    if isinstance(valeur, int):
        return max(0, valeur)
    if isinstance(valeur, str):
        try:
            return max(0, int(valeur.strip()))
        except ValueError:
            return 0
    return 0


def read_context(root: Path) -> ActiveContext:
    """Lit le contexte actif depuis le fichier local.

    Retourne un contexte vide dès que le fichier est absent, illisible ou
    malformé. Un fichier d'état local n'est pas une entrée de confiance : le
    perdre coûte à l'apprenant un ``dsoxlab use``, alors qu'une exception lui
    coûte la CLI tout entière, sans lui dire quel fichier supprimer.
    """
    path = get_context_path(root)
    if not path.exists():
        return ActiveContext()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        # UnicodeDecodeError descend de ValueError, pas d'OSError : un fichier
        # d'octets arbitraires passait donc à travers l'ancien filet.
        logger.warning("Contexte illisible, ignoré : %s", path)
        return ActiveContext()

    # La racine du document peut être n'importe quel type JSON. Sur une liste
    # ou une chaîne, `.get()` n'existe pas et lève un AttributeError que rien
    # n'attrapait.
    if not isinstance(data, dict):
        logger.warning("Contexte non conforme (racine %s), ignoré : %s",
                       type(data).__name__, path)
        return ActiveContext()

    return ActiveContext(
        section=_texte(data.get("section")),
        level=_texte(data.get("level")),
        lang=_texte(data.get("lang")),
        active_lab=_texte(data.get("active_lab")),
        active_target=_texte(data.get("active_target")),
        active_provider=_texte(data.get("active_provider")),
        course_pos=_position(data.get("course_pos")),
    )


def _persist(root: Path, ctx: ActiveContext) -> None:
    """Écrit le contexte sur disque en omettant les champs vides/None."""
    raw = asdict(ctx)
    # On omet les champs qui sont None ou 0 pour rester lisible
    data = {k: v for k, v in raw.items() if v not in (None, "", 0)}
    path = get_context_path(root)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_context(
    root: Path,
    section: str | None,
    level: str | None,
    lang: str | None = None,
    active_target: str | None = None,
) -> None:
    """Persiste le contexte actif dans le fichier local.

    Préserve les autres champs (active_lab, course_pos) qui ne sont pas
    passés en arguments. ``active_target`` peut être passé pour
    mémoriser la cible préférée de l'apprenant.
    """
    existing = read_context(root)
    if section is not None:
        existing.section = section
    if level is not None:
        existing.level = level
    if lang is not None:
        existing.lang = lang[:2].lower()
    if active_target is not None:
        existing.active_target = active_target or None
    _persist(root, existing)


def set_course_pos(root: Path, pos: int) -> None:
    """Met à jour la position courante dans le cours (1-based)."""
    ctx = read_context(root)
    ctx.course_pos = pos if pos > 0 else 0
    _persist(root, ctx)


def set_active_lab(root: Path, lab_id: str | None) -> None:
    """Met à jour le lab actif dans le contexte."""
    ctx = read_context(root)
    ctx.active_lab = lab_id
    _persist(root, ctx)


def set_active_target(root: Path, target: str | None) -> None:
    """Met à jour la target active dans le contexte (peut être None pour effacer)."""
    ctx = read_context(root)
    ctx.active_target = target
    _persist(root, ctx)


def set_active_provider(root: Path, provider: str | None) -> None:
    """Met à jour le provider actif dans le contexte (peut être None pour effacer).

    Persistant entre commandes : ``dsoxlab use kvm`` puis ``dsoxlab provision``,
    ``dsoxlab status``, ``dsoxlab destroy`` réutilisent automatiquement ``kvm``.
    """
    ctx = read_context(root)
    ctx.active_provider = provider
    _persist(root, ctx)


def clear_context(root: Path) -> None:
    """Supprime le fichier de contexte actif."""
    path = get_context_path(root)
    if path.exists():
        path.unlink()


def get_lab_home() -> Path:
    """Retourne la racine du dépôt fournisseur de labs courant.

    Ordre de priorité :

    1. Variable d'environnement ``LAB_HOME`` (chemin explicite).
    2. Remontée depuis le CWD pour trouver ``meta.yml`` (mode framework).
    3. CWD lui-même (fallback).

    `dsoxlab` étant installé globalement (ex. ``uv tool install``), il
    fonctionne depuis le CWD où l'apprenant s'est placé : un dépôt
    fournisseur (`linux-training`, `ansible-training`, …). On NE retourne
    JAMAIS le parent du package Python — ce serait le dépôt de la CLI
    elle-même, qui ne contient pas de labs.
    """
    env = os.environ.get("LAB_HOME")
    if env:
        return Path(env).expanduser().resolve()

    cwd = Path.cwd().resolve()
    current = cwd
    while True:
        if (current / "meta.yml").is_file():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Fallback : CWD (utile pour les tests ou les dépôts sans meta.yml).
    return cwd
