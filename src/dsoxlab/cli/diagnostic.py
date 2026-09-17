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
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer

from ..i18n import _
from ..reporting import (
    console,
    error,
    info,
    machine,
    print_doctor,
    print_fullhelp,
    success,
    warn,
)
from ..services import (
    Fix,
    FixKind,
    collect_checks,
)
from ..services.doctor import (
    EXIT_DOCTOR_INDETERMINE,
    EXIT_DOCTOR_REQUIS_KO,
    DoctorReport,
)
from ..utils.shell import CommandError, run_command
from ._commun import (
    LabHomeOption,
    _read_repo,
    _root,
)
from ._socle import app, completion_app

if TYPE_CHECKING:  # pragma: no cover - import de typage seulement
    from ..models import RepoMetadata

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

def _verdict_strict(report: DoctorReport) -> None:
    """Traduit le diagnostic en code de sortie, pour un appelant automatisé.

    Par défaut ``doctor`` sort en 0 quoi qu'il arrive, et c'est le bon choix
    pour un humain : un diagnostic n'est pas un échec. Mais il rendait la
    commande inutilisable comme portail — un script devait analyser le JSON
    pour savoir si quelque chose manquait.

    Deux codes plutôt qu'un, parce qu'il y a deux situations et qu'elles
    appellent des gestes différents : réparer ce qui manque, ou refaire une
    mesure qui n'a pas abouti. L'échec établi l'emporte sur l'indéterminé, la
    certitude étant l'information la plus forte des deux.
    """
    if report.failing():
        raise typer.Exit(EXIT_DOCTOR_REQUIS_KO)
    if report.indetermines():
        raise typer.Exit(EXIT_DOCTOR_INDETERMINE)


@app.command("doctor", help=_("cmd_doctor_help"))
def doctor(
    lab_home: LabHomeOption = None,
    fix: Annotated[bool, typer.Option("--fix", help=_("opt_fix"))] = False,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
    strict: Annotated[bool, typer.Option("--strict", help=_("opt_doctor_strict"))] = False,
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
        # Le document est rendu AVANT le verdict : `validate-structure` fait de
        # même, et un appelant qui reçoit un code non nul doit quand même
        # pouvoir lire ce qui n'allait pas.
        if strict:
            _verdict_strict(report)
        return

    print_doctor(report)

    if fix:
        correctifs = [
            (c.label, c.fix) for c in report.fixable() if c.fix is not None
        ]
        if not correctifs:
            info(_("fix_nothing"))
            if strict:
                _verdict_strict(report)
            return

        # Un correctif MANUAL n'est JAMAIS exécuté : le geste appartient à
        # l'humain, `--fix` se contente de le nommer. Tout le reste s'exécute,
        # y compris les catégories à effet différé : c'est le message d'après
        # qui change, pas la décision de jouer la commande.
        manuels = [
            (label, correctif) for label, correctif in correctifs
            if correctif.kind is FixKind.MANUAL
        ]
        executables = [
            (label, correctif) for label, correctif in correctifs
            if correctif.kind is not FixKind.MANUAL
        ]
        for label, correctif in manuels:
            info(_("fix_manual", label=label, command=correctif.display))
        if not executables:
            if strict:
                _verdict_strict(report)
            return

        # Pré-conditions sudo : si au moins un correctif passe par sudo, on
        # vérifie que l'env est compatible avant d'attaquer (TTY pour
        # taper le password, sudo dispo, et idéalement on cache le
        # password une seule fois pour toute la cascade).
        sudo_fixes = [c for _label, c in executables if c.requires_sudo]
        if sudo_fixes:
            if not sys.stdin.isatty():
                error(_("fix_needs_tty"))
                raise typer.Exit(1)
            if shutil.which("sudo") is None:
                error(_("fix_no_sudo"))
                raise typer.Exit(1)

            # Pré-cache les credentials sudo : un seul prompt password
            # pour toute la cascade. Sans ce sudo -v, l'apprenant
            # pourrait avoir à retaper son password à chaque commande
            # (si sudo timestamp_timeout=0 ou si la cascade dépasse 5min).
            info(_("fix_sudo_preauth", count=len(sudo_fixes)))
            # check=False : un mot de passe refusé ou un Ctrl-C sur le prompt
            # sudo est une réponse de l'utilisateur, pas une panne. On la
            # traduit en message et en code de sortie, pas en trace Python.
            preauth = subprocess.run(["sudo", "-v"], check=False)
            if preauth.returncode != 0:
                error(_("fix_sudo_failed"))
                raise typer.Exit(1)

        info(_("fix_count", count=len(executables)))
        for label, correctif in executables:
            info(f"[bold]{label}[/bold] → {correctif.display}")
            code = _executer_correctif(correctif)
            if code == 0:
                success(_("fix_success", label=label))
                # Dire l'effet différé au moment du succès, sans quoi le
                # prochain `doctor` remontre la même ligne rouge et
                # l'utilisateur conclut, à tort, que le correctif a échoué.
                if correctif.kind is FixKind.NEEDS_RELOGIN:
                    warn(_("fix_needs_relogin", label=label))
                elif correctif.kind is FixKind.NEEDS_REBOOT:
                    warn(_("fix_needs_reboot", label=label))
            else:
                error(_("fix_failure", label=label, code=code))
        info(_("fix_rerun"))

    if strict:
        # Après des correctifs, l'état de la machine a changé : juger sur le
        # rapport d'avant dirait faux, et dans le mauvais sens — un `--fix`
        # réussi sortirait quand même en échec. On remesure.
        _verdict_strict(collect_checks(root, repo_meta) if fix else report)


def _executer_correctif(correctif: Fix) -> int:
    """Joue les commandes d'un correctif, dans l'ordre, sans shell.

    Chaque argv part tel quel à ``run_command`` : aucun token n'est redécoupé
    en route, un argument portant une espace arrive entier à la commande. La
    séquence s'arrête au premier échec, dont le code est rendu. ``check=False``
    parce que `--fix` joue une CASCADE : un correctif en échec doit être
    signalé puis laisser tourner les suivants ; lever ici abandonnerait les
    réparations restantes sur la première qui rate.

    La sortie capturée est rejouée sur les flux d'origine : l'utilisateur
    voit ce qu'apt ou systemctl ont dit, en particulier quand ça a raté.
    """
    for commande in correctif.commands:
        try:
            resultat = run_command(list(commande), check=False, timeout=900)
        except CommandError as exc:
            # Commande introuvable ou délai dépassé : le wrapper l'a déjà
            # journalisé, on rend un échec franc avec ce qu'on sait.
            if exc.result.stderr:
                sys.stderr.write(exc.result.stderr + "\n")
            return 1
        if resultat.stdout:
            sys.stdout.write(resultat.stdout)
        if resultat.stderr:
            sys.stderr.write(resultat.stderr)
        if resultat.returncode != 0:
            return resultat.returncode
    return 0


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
    issue: Annotated[
        bool, typer.Option("--issue", help=_("opt_support_issue"))
    ] = False,
    print_only: Annotated[
        bool, typer.Option("--print", help=_("opt_support_print"))
    ] = False,
    moteur: Annotated[
        bool, typer.Option("--engine", help=_("opt_support_engine"))
    ] = False,
    catalogue: Annotated[
        bool, typer.Option("--catalog", help=_("opt_support_catalog"))
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help=_("opt_yes"))] = False,
    lab_home: LabHomeOption = None,
) -> None:
    """Rapport de diagnostic anonymisé, prêt à coller dans une issue."""
    from ..services.support import collecter, en_markdown

    if as_json and issue:
        # `--json` promet un document et rien d'autre sur la sortie standard ;
        # `--issue` dialogue et ouvre un navigateur. Les deux ensemble ne
        # veulent rien dire, et le silence ferait croire que l'issue est partie.
        error(_("issue_json_exclusif"))
        raise typer.Exit(2)
    if moteur and catalogue:
        error(_("issue_cible_ambigue"))
        raise typer.Exit(2)
    if print_only and not issue:
        error(_("issue_print_sans_issue"))
        raise typer.Exit(2)

    rapport = collecter(lignes_journal=max(0, lignes))

    if as_json:
        machine.emit(rapport)
        return

    # `print` et non la console Rich : ce texte est fait pour être copié dans
    # une issue. Rich l'habillerait de couleurs et le couperait à la largeur du
    # terminal, ce qui casserait les tableaux Markdown une fois collés.
    print(en_markdown(rapport))

    if not issue:
        info(_("support_hint"))
        return

    _ouvrir_issue(
        rapport,
        root=_root(lab_home),
        vers_moteur=moteur,
        vers_catalogue=catalogue,
        print_only=print_only,
        assume_yes=yes,
    )


def _repo_meta_tolerant(root: Path) -> RepoMetadata | None:
    """Le ``meta.yml``, ou ``None`` s'il ne se lit pas. Ne sort jamais.

    ``_read_repo`` sort en 1 sur un contrat illisible, ce qui est juste partout
    ailleurs. Pas ici : un catalogue cassé est précisément ce qu'on veut
    signaler, et refuser d'ouvrir l'issue à cause de lui serait le comble.
    """
    from ..discovery.repo import read_repo_metadata

    try:
        return read_repo_metadata(root)
    except Exception as exc:  # noqa: BLE001 : aucune cause ne doit empêcher le rapport
        logger.warning("unreadable meta.yml for issue routing: %s", exc)
        return None


def _contexte_issue(rapport: dict[str, Any]) -> tuple[dict[str, str], str]:
    """Les champs déductibles du rapport, et l'identifiant du lab actif.

    Rien n'est inventé : chaque valeur vient du rapport déjà collecté. Ce qui
    n'y figure pas reste vide, et c'est à l'apprenant de l'écrire.
    """
    catalogue = rapport.get("catalogue") or {}
    lab_actif = str(catalogue.get("lab_actif") or "")
    section = str(catalogue.get("section_active") or "")

    reproduce = ""
    if lab_actif:
        # Un canevas, pas une affirmation : on sait quel lab est ouvert, pas ce
        # que l'apprenant a tapé. Les deux premières lignes lui épargnent la
        # recopie, la troisième est la seule qui compte et reste à lui.
        etapes = [f"1. dsoxlab use {section}"] if section else []
        etapes.append(f"{len(etapes) + 1}. dsoxlab run {lab_actif}")
        etapes.append(f"{len(etapes) + 1}. ")
        reproduce = "\n".join(etapes)

    champs = {
        "lab": lab_actif,
        "os": str(rapport.get("distribution") or ""),
        "runtime": str(catalogue.get("runtime_lab_actif") or ""),
        "reproduce": reproduce,
    }
    return champs, lab_actif


def _ouvrir_issue(
    rapport: dict[str, Any],
    *,
    root: Path,
    vers_moteur: bool,
    vers_catalogue: bool,
    print_only: bool,
    assume_yes: bool,
) -> None:
    """Route, montre, demande, puis ouvre. Jamais dans un autre ordre."""
    from ..services.issue_service import (
        Cible,
        Repli,
        construire_lien,
        resoudre_destination,
    )
    from ..services.support import en_markdown

    champs, lab_actif = _contexte_issue(rapport)

    # Le lab actif décide, faute d'instruction contraire : un défaut rencontré
    # dans un lab est, le plus souvent, un défaut de ce lab.
    if vers_catalogue:
        cible = Cible.CATALOGUE
    elif vers_moteur:
        cible = Cible.MOTEUR
    else:
        cible = Cible.CATALOGUE if lab_actif else Cible.MOTEUR

    destination = resoudre_destination(root, _repo_meta_tolerant(root), cible=cible)
    if destination is None:
        error(_("issue_sans_destination"))
        raise typer.Exit(2)

    lien = construire_lien(
        destination,
        contexte=champs,
        rapport=en_markdown(rapport),
        rapport_court=en_markdown({**rapport, "journal": []}),
    )

    info(_(
        "issue_destination",
        depot=destination.libelle,
        cible=_(destination.cible.cle_i18n),
        origine=_(destination.origine.cle_i18n),
    ))
    if lien.repli is Repli.SANS_JOURNAL:
        warn(_("issue_repli_sans_journal"))
    elif lien.repli is Repli.VIDE:
        warn(_("issue_repli_vide"))

    if print_only:
        # soft_wrap : une URL coupée sur deux lignes n'est plus copiable. Même
        # raison que pour `guide --print`, et même geste.
        console.print(lien.url, soft_wrap=True)
        return

    if not assume_yes and not typer.confirm(_("issue_confirmer", depot=destination.libelle)):
        info(_("issue_abandon"))
        return

    console.print(lien.url, soft_wrap=True)
    if not webbrowser.open(lien.url):
        error(_("issue_sans_navigateur"))


# ── fullhelp ──────────────────────────────────────────────────────────────────

@app.command("fullhelp", help=_("cmd_fullhelp_help"))
def fullhelp() -> None:
    print_fullhelp()
