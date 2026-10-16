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
from pathlib import Path
from typing import Annotated

import typer

from ..exit_codes import ExitCode
from ..i18n import _
from ..reporting import (
    error,
    info,
    success,
)
from ._commun import (
    LabHomeOption,
    _catalogue,
    _lang,
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


# ── instructor audit : ce qu'un apprenant ne trouvera pas tout seul ──────────


@instructor_app.command("audit", help=_("cmd_instructor_audit_help"))
def instructor_audit(
    lab_home: LabHomeOption = None,
    export: Annotated[Path | None, typer.Option("--export", help=_("opt_audit_export"))] = None,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    """La grille qu'un formateur applique avant de confier un catalogue.

    Elle est née d'une lecture de labs à la place d'un apprenant, sur cinq
    catalogues : `linux` et `terraform` donnent tout ce qu'il faut, tandis que
    certains labs d'`ansible` ne portent **aucun** message d'assertion, et que
    leurs missions ne disent pas comment valider. Un apprenant y voit quels
    tests échouent, et rien sur ce qu'il doit corriger.

    `validate-structure` répond à « ce catalogue respecte-t-il le contrat ? ».
    Celle-ci répond à « un apprenant peut-il faire le travail avec ce qu'on lui
    donne ? », et les deux sont séparées parce qu'un catalogue parfaitement
    conforme peut être injouable.
    """
    from ..reporting import machine, note, print_audit_pedagogique
    from ..services.audit_pedagogique import (
        ATTENTION,
        MANQUE,
        dossier_pour_relecture,
        examiner,
    )

    root = _root(lab_home)
    lang = _lang(root)
    labs = _catalogue(root, lang, quiet=as_json)
    rapport = examiner(labs, lang)

    if export is not None:
        dossier = dossier_pour_relecture(labs, lang)
        try:
            export.write_text(dossier, encoding="utf-8")
        except OSError as exc:
            # La même clé que `export`, et pour la même situation : un fichier
            # qu'on n'a pas pu écrire, nommé avec la cause rendue par l'OS.
            error(_("export_fichier_erreur", path=str(export), error=str(exc)))
            raise typer.Exit(ExitCode.IMPOSSIBLE) from None
        note(_("audit_export_ecrit", path=export, lignes=len(dossier.splitlines())))

    if as_json:
        machine.emit({
            "ok": rapport.ok,
            "labs_examined": rapport.labs_examines,
            "findings": [
                {
                    "lab": c.lab_id,
                    "key": c.cle,
                    "level": c.niveau,
                    "message": c.phrase(),
                    "params": c.params,
                }
                for c in rapport.constats
            ],
            "counts": {
                MANQUE: len(rapport.par_niveau(MANQUE)),
                ATTENTION: len(rapport.par_niveau(ATTENTION)),
            },
            # Le suivi de la parité des langues se fait ici, pas par des
            # constats : un chiffre se compare d'une version à l'autre, et se
            # garde en CI. Les noms sont stables, c'est un contrat public.
            "assertions": {
                "total": rapport.assertions.total,
                "with_message": rapport.assertions.avec_message,
                "without_message": rapport.assertions.sans_message,
                "single_language": rapport.assertions.monolingues,
                "both_languages": rapport.assertions.bilingues,
                "unreachable_helper": rapport.assertions.helper_injoignable,
            },
        })
        if not rapport.ok:
            raise typer.Exit(ExitCode.ECHEC)
        return

    print_audit_pedagogique(rapport)
    if not rapport.ok:
        raise typer.Exit(ExitCode.ECHEC)
