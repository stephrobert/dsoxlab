"""Les outils que les commandes lancent : python, pytest, shell, git, terraform, ansible.

Extrait de ``services/doctor.py`` (issue #199), sans changement de
comportement. Voir ce module pour les principes du diagnostic.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from ...i18n import _
from ...infra import ansible as ansible_infra
from ...models import RepoMetadata
from .modele import STATE_UNKNOWN, Check, _check, _doctor, _fix, _installer

# ── checks unitaires ──────────────────────────────────────────────────────────

def _check_python() -> Check:
    return _check("python", True, sys.version.split()[0])


def _check_pytest(root: Path) -> Check:
    """Diagnostique pytest par la résolution qu'utilise réellement ``check``."""
    cmd = _doctor().resolve_pytest_cmd(root)
    if cmd is None:
        return _check(
            "pytest", False, _("detail_pytest_missing"),
            hint="uv tool install --force dsoxlab",
        )
    if cmd[0] == sys.executable:
        return _check("pytest", True, _("detail_pytest_bundled"))
    return _check("pytest", True, _("detail_pytest_via", cmd=" ".join(cmd)))


def _check_shell() -> Check:
    return _check("shell", True, _("detail_shell_always"))


def _sonder(
    commande: list[str], *, delai: float = 5, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str] | None:
    """Joue une sonde, ou rend ``None`` si elle ne répond pas.

    Un diagnostic qui plante en diagnostiquant emporte toute la commande, et
    depuis que ``doctor --json`` est une interface, il emporte aussi le document
    de l'appelant : une ``TimeoutExpired`` remonte alors en trace Python là où
    l'appelant attendait du JSON. ``virsh version`` pend jusqu'au délai sur un
    hôte dont libvirt ne répond plus, et c'est un cas courant, pas un cas d'école.

    ``check=False`` : un code retour non nul EST le diagnostic. C'est l'absence
    de réponse, elle, qui vaut ``None``.
    """
    try:
        return subprocess.run(
            commande, capture_output=True, text=True, timeout=delai,
            check=False, env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _check_terraform() -> Check:
    """Terraform provisionne les machines, quel que soit le provider.

    Il ne figurait dans aucun contrôle, alors que ``provision`` s'arrête net
    sans lui. Pire, son message renvoyait vers ``dsoxlab instructor bootstrap``,
    qui se contente de signaler l'absence sans jamais l'installer : l'apprenant
    tournait en rond entre deux commandes qui lui disaient la même chose.
    """
    if shutil.which("terraform") is None:
        return _check(
            "terraform", False, _("detail_terraform_missing"),
            hint="https://developer.hashicorp.com/terraform/install",
        )
    # Le binaire peut être dans le PATH sans être exécutable, ou disparaître
    # entre les deux appels. Un diagnostic qui plante en cherchant à
    # diagnostiquer est le pire des cas : il emporte toute la commande.
    result = _doctor()._sonder(["terraform", "version"])
    if result is None:
        return _check(
            "terraform", False, _("detail_terraform_missing"),
            hint="https://developer.hashicorp.com/terraform/install",
        )
    # Un terraform présent mais qui sort en erreur passait pour vert : le code
    # retour n'était pas lu, et « ok » s'affichait faute de stdout. `provision`
    # échouait ensuite sur une machine que `doctor` venait de déclarer prête.
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return _check(
            "terraform", False,
            detail[-1] if detail else _("detail_terraform_broken"),
            hint="https://developer.hashicorp.com/terraform/install",
        )
    first = result.stdout.splitlines()[0] if result.stdout else "ok"
    return _check("terraform", True, first)


def _check_collections(root: Path) -> Check:
    """Les collections Ansible que les playbooks du catalogue appellent.

    Rapporté par deux utilisateurs (kubernetes-dsoxlab-training#94) : sur une
    machine fraîche, **tous** les labs de ce catalogue échouaient au `run`, sur
    un `couldn't resolve module/action 'community.general.modprobe'`.
    `ansible-core` ne fournit que `ansible.builtin`, les collections ne sont
    pas des paquets Python, et rien ne les installe.

    Le défaut est resté invisible chez le mainteneur, dont la machine portait
    douze collections accumulées au fil des années. C'est exactement ce qu'un
    diagnostic doit dire à sa place, et il le dit en lisant le catalogue : pas
    de liste écrite ici, donc rien de spécifique à un domaine.
    """
    from ..collections_ansible import geste_d_installation, mesurer

    besoins = mesurer(root)
    if not besoins.exigees:
        return _check("collections", True, _("detail_collections_aucune"))
    if not besoins.mesurable:
        # `ansible-galaxy` n'a pas répondu : on ne peint pas en rouge ce qu'on
        # n'a pas pu regarder, et `--strict` a son propre code pour cela.
        return _check(
            "collections", False, _("detail_collections_non_mesure"),
            forced_state=STATE_UNKNOWN,
        )
    if not besoins.manquantes:
        # Un vrai pluriel, pas un « (s) » : un diagnostic qu'on lit vingt fois
        # par semaine se lit mieux écrit comme on parle.
        exigees = len(besoins.exigees)
        return _check(
            "collections", True,
            _("detail_collections_ok") if exigees == 1
            else _("detail_collections_ok_n", count=exigees),
        )
    manquantes = besoins.manquantes
    cle = (
        "detail_collections_manquantes" if len(manquantes) == 1
        else "detail_collections_manquantes_n"
    )
    return _check(
        "collections", False,
        _(cle, names=", ".join(manquantes), file=besoins.exigees[manquantes[0]]),
        fix=_fix(geste_d_installation(besoins)),
    )


def _check_ansible() -> Check:
    """``run`` sur un lab vm joue un playbook : il faut ``ansible-playbook``.

    ``ansible-runner`` ne tire pas ``ansible-core``. Le contrôle portait sur
    l'import de la bibliothèque, donc il était vert sur une machine où aucun
    playbook ne pouvait tourner, et ``run`` sortait en ``rc=127`` sans que rien
    ne relie les deux.
    """
    if not ansible_infra.has_ansible_playbook():
        return _check(
            "ansible", False, _("detail_ansible_missing"),
            fix=_fix(["uv", "tool", "install", "ansible-core"]),
        )
    return _check("ansible", True, _("detail_ansible_ok"))


def _check_iso_tool() -> Check:
    """Incus fabrique le CD-ROM ``agent:config`` sur l'hôte.

    Sans ``mkisofs`` ni ``genisoimage``, aucune instance de type
    ``virtual-machine`` ne démarre : « Neither mkisofs nor genisoimage could be
    found in $PATH ». Rien ne le documentait, et la remédiation d'incus se
    limitait à installer incus.
    """
    for outil in ("genisoimage", "mkisofs", "xorrisofs"):
        if shutil.which(outil):
            return _check("iso_tool", True, outil)
    return _check(
        "iso_tool", False, _("detail_iso_tool_missing"),
        fix=_fix(_installer(["genisoimage"], ["xorriso"])),
    )


def _check_git() -> Check:
    """``catalog add`` clone : sans git, la deuxième commande du parcours échoue.

    git n'est pas une dépendance Python — ``uv tool install`` ne l'apporte pas —
    et il ne figurait dans aucun contrôle. Son absence remontait en trace
    Python sur la commande d'accueil, ce qui est le plus mauvais moment pour
    montrer une trace à quelqu'un.
    """
    if shutil.which("git") is None:
        return _check(
            "git", False, _("detail_git_missing"),
            hint="https://git-scm.com/downloads",
        )
    result = _doctor()._sonder(["git", "--version"])
    if result is None:
        # Présent dans le PATH mais muet : ni vert ni rouge, on ne sait pas.
        return _check("git", False, _("detail_git_muet"), forced_state=STATE_UNKNOWN)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return _check("git", False, detail[-1] if detail else _("detail_git_muet"),
                      hint="https://git-scm.com/downloads")
    return _check("git", True, result.stdout.strip() or "ok")


def _check_tf_providers(repo_meta: RepoMetadata | None) -> Check:
    """Quelle version de chaque provider Terraform tourne pour ce dépôt.

    La contrainte du template (``~> 0.9``) ne le dit pas : deux postes qui
    l'honorent tous les deux peuvent avoir des versions différentes, et c'est
    celle-là qui décide. Comprendre l'issue #234 a demandé de comparer à la main
    deux rapports `support` qui ne la portaient ni l'un ni l'autre.

    Toujours ``ok`` : c'est une information, pas un prérequis. Aucun plancher
    n'est connu pour ces providers, et en inventer un serait refuser des postes
    sur une supposition.
    """
    from ...infra.terraform import providers_epingles

    if repo_meta is None:
        return _check("tf_providers", True, _("detail_tf_providers_absents"))

    try:
        epingles = providers_epingles(repo_meta)
    except Exception:  # noqa: BLE001 : un diagnostic ne casse pas la commande
        epingles = {}

    if not epingles:
        return _check("tf_providers", True, _("detail_tf_providers_absents"))

    rendu = ", ".join(f"{nom} {version}" for nom, version in sorted(epingles.items()))
    return _check("tf_providers", True, _("detail_tf_providers", providers=rendu))
