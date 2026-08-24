"""Point d'entrée CLI — dsoxlab.

Usage:
    dsoxlab use linux/l1
    dsoxlab list-labs
    dsoxlab show <id>
    dsoxlab run <id>
    dsoxlab check <id>
    dsoxlab reset <id>
    dsoxlab clean <id>
    dsoxlab validate-structure
    dsoxlab doctor
    dsoxlab quit

Convention de ce module : un ``except`` qui a déjà rendu la cause en une phrase
traduite (``error(...)``) sort par ``raise typer.Exit(n) from None``. Le ``from
None`` n'est pas un raccourci, c'est l'affirmation que la cause a été dite à
l'utilisateur, et qu'un chaînage d'exceptions n'ajouterait qu'une trace Python
au-dessus d'un message déjà écrit pour lui. Partout ailleurs, on chaîne.
"""

from __future__ import annotations

import logging
import subprocess

import typer

from ..i18n import _
from ..reporting import (
    error,
    info,
    success,
)
from ._commun import (
    LabHomeOption,
    _root,
)
from ._socle import instructor_app

logger = logging.getLogger(__name__)



# ── instructor : commandes formateur ─────────────────────────────────────────


@instructor_app.command("bootstrap", help=_("cmd_instructor_bootstrap_help"))
def instructor_bootstrap(
    lab_home: LabHomeOption = None,
) -> None:
    """Génère la clé SSH du lab si absente et vérifie les prérequis.

    Crée ``<repo>/ssh/id_ed25519`` (+ .pub) sans passphrase. La clé
    publique est ensuite injectée dans le tfvars par dsoxlab provision
    pour être propagée aux VMs via cloud-init.

    Vérifie la présence de ``terraform`` et ``ansible-runner``.
    """
    root = _root(lab_home)

    # Une clé privée ne se crée pas n'importe où. Sans `meta.yml`, `root` n'est
    # pas un dépôt de labs : `get_lab_home()` a simplement retenu le répertoire
    # courant en dernier recours. Le cas est vécu : lancée depuis le dépôt de
    # l'outil, la commande y a déposé une paire de clés hors de tout .gitignore.
    # Le hook `detect-private-key` l'aurait arrêtée au commit, mais un hook se
    # contourne (`--no-verify`) et ne protège que ce dépôt-ci. La clé n'avait
    # de toute façon rien à faire là : on refuse plutôt que de deviner.
    if not (root / "meta.yml").is_file():
        error(_("bootstrap_not_a_lab_repo", root=root))
        raise typer.Exit(1)

    ssh_dir = root / "ssh"
    private_key = ssh_dir / "id_ed25519"
    public_key = ssh_dir / "id_ed25519.pub"

    if private_key.is_file() and public_key.is_file():
        info(_("bootstrap_key_exists", path=private_key))
    else:
        info(_("bootstrap_generating_key", path=private_key))
        ssh_dir.mkdir(parents=True, exist_ok=True)
        ssh_dir.chmod(0o700)
        # check=False : l'échec est traduit en message + Exit(2) juste en
        # dessous. Une CalledProcessError sortirait la trace Python de
        # ssh-keygen au visage du formateur, sans lui dire quoi faire.
        result = subprocess.run(
            [
                "ssh-keygen",
                "-t", "ed25519",
                "-N", "",  # pas de passphrase
                "-C", "dsoxlab-lab",
                "-f", str(private_key),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            error(_("bootstrap_keygen_failed", stderr=result.stderr.strip()))
            raise typer.Exit(2)
        success(_("bootstrap_key_created", path=private_key))

    # Vérifie les outils requis
    from ..infra import ansible as ansible_infra
    from ..infra import terraform as tf

    manquant = False

    if not tf.is_available():
        error(_("bootstrap_no_terraform"))
        manquant = True
    else:
        info(_("bootstrap_terraform_ok"))

    if not ansible_infra.is_available():
        error(_("bootstrap_no_ansible_runner"))
        manquant = True
    else:
        info(_("bootstrap_ansible_runner_ok"))

    # Sortir en 0 après avoir affiché une erreur bloquante trompe autant un
    # apprenant qui vérifie son code de retour qu'un script d'installation :
    # la clé SSH est bien créée, mais rien ne pourra la provisionner. Le code
    # de retour doit dire la même chose que l'écran.
    if manquant:
        raise typer.Exit(1)


# ── demo ──────────────────────────────────────────────────────────────────────
