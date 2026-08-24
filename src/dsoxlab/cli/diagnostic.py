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
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from ..i18n import _
from ..reporting import (
    error,
    info,
    machine,
    print_doctor,
    print_fullhelp,
    success,
    warn,
)
from ..services import (
    collect_checks,
)
from ._commun import (
    LabHomeOption,
    _read_repo,
    _root,
)
from ._socle import app, completion_app

logger = logging.getLogger(__name__)



# ── install ─────────────────────────────────────────────────────────────────

#: Nom du programme, tel que la CLI est installée et invoquée.
_PROG_NAME = "dsoxlab"

#: Variable d'environnement par laquelle le shell demande une complétion.
#: Elle est DÉRIVÉE du nom du programme, comme le fait Click lui-même, et non
#: recopiée : la valeur codée en dur était « _DSOXL_COMPLETE », que la CLI
#: n'écoute pas. Le script généré interrogeait donc dsoxlab avec une variable
#: ignorée, la CLI répondait par sa page d'aide, et le shell tentait de
#: l'évaluer à chaque tabulation.
_COMPLETE_VAR = f"_{_PROG_NAME.replace('-', '_').upper()}_COMPLETE"


#: Ce que dsoxlab ajoute au script que typer génère pour zsh, et pourquoi.
#:
#: Le commentaire part DANS le fichier installé, à dessein : sans lui, la ligne
#: ressemble à une scorie qu'un lecteur pressé retirerait, et le défaut
#: reviendrait sans que personne ne comprenne pourquoi.
_ZSH_PREMIER_TAB = """
# ── ajouté par dsoxlab, et pas par typer ──────────────────────────────────────
# zsh autoload ce fichier au PREMIER Tab, et attend qu'il produise les
# propositions de cette invocation-là. Le script amont se contente de définir la
# fonction puis de l'enregistrer pour la suite : la première tabulation ne rend
# donc rien, et la seconde fonctionne. Un Tab muet se lit comme « la complétion
# ne marche pas », et personne ne rappuie pour vérifier.
# Ne pas retirer cette ligne sans rejouer le cas dans un zsh réel.
_dsoxlab_completion "$@"
"""


def _script_completion(shell: str) -> str:
    """Le script de complétion pour ``shell``, corrigé pour zsh (#134)."""
    from typer.completion import get_completion_script

    script = get_completion_script(
        prog_name=_PROG_NAME, complete_var=_COMPLETE_VAR, shell=shell
    )
    # bash source son script au démarrage du shell, fish le charge par fichier
    # de complétion : ni l'un ni l'autre ne passe par l'autoload qui pose
    # problème. La divergence ne vaut donc que pour zsh.
    return script + _ZSH_PREMIER_TAB if shell == "zsh" else script


def _installer_completion() -> None:
    """Pose le script de complétion du shell courant, et raccorde son rc."""
    shell_name = Path(os.environ.get("SHELL", "bash")).name

    if shell_name == "zsh":
        zfunc_dir = Path.home() / ".zfunc"
        zfunc_dir.mkdir(exist_ok=True)
        # Le nom du fichier compte : zsh autoload la fonction `_dsoxlab` pour
        # compléter `dsoxlab`, et cherche donc un fichier de ce nom exact.
        comp_file = zfunc_dir / f"_{_PROG_NAME}"
        comp_file.write_text(_script_completion("zsh"))
        success(_("install_completion", path=str(comp_file)))

        zshrc = Path.home() / ".zshrc"
        zshrc_content = zshrc.read_text() if zshrc.exists() else ""
        additions = []
        if "fpath=(~/.zfunc $fpath)" not in zshrc_content:
            additions.append("fpath=(~/.zfunc $fpath)")
        if "autoload -Uz compinit" not in zshrc_content:
            additions.append("autoload -Uz compinit && compinit")
        if additions:
            with zshrc.open("a") as f:
                f.write("\n# dsoxlab completion\n" + "\n".join(additions) + "\n")
        info(_("install_rc", path=str(zshrc)))

    elif shell_name == "bash":
        bash_comp_dir = Path.home() / ".bash_completion.d"
        bash_comp_dir.mkdir(exist_ok=True)
        comp_file = bash_comp_dir / "dsoxlab"
        comp_file.write_text(_script_completion("bash"))
        success(_("install_completion", path=str(comp_file)))

        bashrc = Path.home() / ".bashrc"
        source_line = f". {comp_file}"
        bashrc_content = bashrc.read_text() if bashrc.exists() else ""
        if source_line not in bashrc_content:
            with bashrc.open("a") as f:
                f.write(f"\n# dsoxlab completion\n{source_line}\n")
        info(_("install_rc", path=str(bashrc)))

    else:
        info(_("install_completion_unsupported", shell=shell_name))
    info(_("install_reload"))


@completion_app.command("install", help=_("cmd_completion_install_help"))
def completion_install() -> None:
    _installer_completion()


@completion_app.command("show", help=_("cmd_completion_show_help"))
def completion_show(
    shell: Annotated[str | None, typer.Option("--shell", help=_("opt_completion_shell"))] = None,
) -> None:
    """Imprime le script, sans rien écrire : à rediriger où l'on veut."""
    nom = shell or Path(os.environ.get("SHELL", "bash")).name
    if nom not in ("zsh", "bash", "fish"):
        error(_("install_completion_unsupported", shell=nom))
        raise typer.Exit(2)
    # `print` et non `info` : c'est une sortie destinée à être redirigée, elle
    # ne doit porter ni couleur ni encadrement.
    print(_script_completion(nom))


@app.command("install", help=_("cmd_install_help"))
def install() -> None:
    """Déprécié depuis 0.1.62, retiré en 0.3.0 : voir `completion install`.

    Le nom promettait d'installer l'outil, déjà installé. La commande posait en
    plus un wrapper dans ``~/.local/bin``, exactement où ``uv tool install`` et
    ``pipx`` posent le leur : le remplacer ne faisait que défaire ce que leur
    prochaine mise à jour remettrait. Il n'est donc plus écrit du tout.
    """
    warn(_("install_deprecie"))
    _installer_completion()


# ── use ──────────────────────────────────────────────────────────────────────

# ── doctor ────────────────────────────────────────────────────────────────────

@app.command("doctor", help=_("cmd_doctor_help"))
def doctor(
    lab_home: LabHomeOption = None,
    fix: Annotated[bool, typer.Option("--fix", help=_("opt_fix"))] = False,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    root = _root(lab_home)

    # `--fix` joue des commandes système (`apt`, `systemctl`, `usermod`) dont la
    # sortie va sur la sortie standard, qu'aucune option ne détourne. Les deux
    # options ensemble produiraient donc un document précédé de la sortie d'apt,
    # c'est-à-dire un flux qu'aucun appelant ne peut lire. On le dit plutôt que
    # de rendre du JSON cassé.
    if as_json and fix:
        error(_("doctor_json_sans_fix"))
        raise typer.Exit(1)

    # Le meta.yml décide de ce qui est bloquant ici : un dépôt sans lab `vm`
    # n'a besoin d'aucun hyperviseur, et un dépôt qui a choisi son provider
    # n'a pas besoin des autres. Son absence n'est pas une erreur : on
    # diagnostique alors le strict socle commun.
    try:
        repo_meta = _read_repo(root)
    except typer.Exit:
        # Un meta.yml illisible est justement ce qu'un diagnostic doit
        # pouvoir rapporter : l'erreur est déjà affichée, on poursuit sur
        # le socle commun plutôt que de sortir sans rien dire d'autre.
        repo_meta = None
    report = collect_checks(root, repo_meta)

    if as_json:
        # Le code de retour ne change pas : `doctor` sort en 0 même quand un
        # contrôle échoue, et le verdict se lit dans `ok`. Un `--json` qui
        # inventerait un code non nul ferait diverger les deux modes.
        machine.emit(machine.doctor_dict(report))
        return

    print_doctor(report)

    if fix:
        failing = [(c.label, c.fix) for c in report.fixable() if c.fix]
        if not failing:
            info(_("fix_nothing"))
            return

        # Pr\u00e9-conditions sudo : si au moins un fix d\u00e9marre par "sudo", on
        # v\u00e9rifie que l'env est compatible avant d'attaquer (TTY pour
        # taper le password, sudo dispo, et id\u00e9alement on cache le
        # password une seule fois pour toute la cascade).
        sudo_fixes = [c for _, c in failing if c.strip().startswith("sudo ")]
        if sudo_fixes:
            if not sys.stdin.isatty():
                error(_("fix_needs_tty"))
                raise typer.Exit(1)
            if shutil.which("sudo") is None:
                error(_("fix_no_sudo"))
                raise typer.Exit(1)

            # Pr\u00e9-cache les credentials sudo : un seul prompt password
            # pour toute la cascade. Sans ce sudo -v, l'apprenant
            # pourrait avoir \u00e0 retaper son password \u00e0 chaque commande
            # (si sudo timestamp_timeout=0 ou si la cascade d\u00e9passe 5min).
            info(_("fix_sudo_preauth", count=len(sudo_fixes)))
            # check=False : un mot de passe refusé ou un Ctrl-C sur le prompt
            # sudo est une réponse de l'utilisateur, pas une panne. On la
            # traduit en message et en code de sortie, pas en trace Python.
            preauth = subprocess.run(["sudo", "-v"], check=False)
            if preauth.returncode != 0:
                error(_("fix_sudo_failed"))
                raise typer.Exit(1)

        info(_("fix_count", count=len(failing)))
        for label, fix_cmd in failing:
            info(f"[bold]{label}[/bold] \u2192 {fix_cmd}")
            # check=False : `--fix` joue une CASCADE. Un correctif en \u00e9chec
            # doit \u00eatre signal\u00e9 puis laisser tourner les suivants ; lever ici
            # abandonnerait les r\u00e9parations restantes sur la premi\u00e8re qui rate.
            result = subprocess.run(fix_cmd, shell=True, text=True, check=False)  # noqa: S602
            if result.returncode == 0:
                success(_("fix_success", label=label))
            else:
                error(_("fix_failure", label=label, code=result.returncode))
        info(_("fix_rerun"))


# ── provision / destroy / ssh / status ────────────────────────────────────────






# ── demo ──────────────────────────────────────────────────────────────────────

@app.command("demo", help=_("cmd_demo_help"))
def demo(
    force: Annotated[bool, typer.Option("--force", help=_("opt_demo_force"))] = False,
) -> None:
    """Installe le catalogue de démonstration et dit quoi faire ensuite."""
    from ..services.demo import DemoExistante, installer

    try:
        installation = installer(force=force)
    except DemoExistante as exc:
        # Ne pas écraser : ce répertoire porte la progression et les réponses.
        error(_("demo_deja_installee", path=str(exc)))
        info(_("demo_deja_installee_suite", path=str(exc)))
        raise typer.Exit(1) from None
    except OSError as exc:
        error(_("demo_echec", error=str(exc)))
        raise typer.Exit(1) from None

    success(_("demo_installee", path=str(installation.racine)))

    # La marche à suivre est construite depuis le catalogue réellement
    # installé : elle ne peut donc pas décrire un lab qui n'y serait plus.
    premier = installation.labs[0] if installation.labs else ""
    info(_("demo_suite", path=str(installation.racine), lab=premier))


# ── catalog ───────────────────────────────────────────────────────────────────

# ── support ───────────────────────────────────────────────────────────────────

@app.command("support", help=_("cmd_support_help"))
def support(
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
    lignes: Annotated[
        int, typer.Option("--log-lines", help=_("opt_support_log_lines"))
    ] = 30,
) -> None:
    """Rapport de diagnostic anonymisé, prêt à coller dans une issue."""
    from ..services.support import collecter, en_markdown

    rapport = collecter(lignes_journal=max(0, lignes))

    if as_json:
        machine.emit(rapport)
        return

    # `print` et non la console Rich : ce texte est fait pour être copié dans
    # une issue. Rich l'habillerait de couleurs et le couperait à la largeur du
    # terminal, ce qui casserait les tableaux Markdown une fois collés.
    print(en_markdown(rapport))
    info(_("support_hint"))


# ── fullhelp ──────────────────────────────────────────────────────────────────

# ── fullhelp ──────────────────────────────────────────────────────────────────

@app.command("fullhelp", help=_("cmd_fullhelp_help"))
def fullhelp() -> None:
    print_fullhelp()
