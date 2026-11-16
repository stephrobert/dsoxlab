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
import shlex
import shutil
import subprocess
import sys
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.text import Text

from ..i18n import _
from ..reporting import (
    console,
    error,
    info,
    machine,
    note,
    print_doctor,
    print_fullhelp,
    success,
    warn,
)
from ..reporting.doctor_rendu import titre_etape
from ..security.terminal import texte_affichable
from ..services import (
    Fix,
    collect_checks,
)
from ..services.doctor import (
    EXIT_DOCTOR_INDETERMINE,
    EXIT_DOCTOR_REQUIS_KO,
    DoctorReport,
)
from ..services.doctor_controles.incus import _current_user
from ..services.doctor_etapes import Etape
from ..services.remediation import (
    Action,
    Application,
    PlanCorrection,
    chemin_du_playbook,
    etape_verifiee,
    planifier,
    playbook_du_poste,
)
from ..utils.shell import CommandError, run_command
from ._commun import (
    LabHomeOption,
    _read_repo,
    _root,
)
from ._socle import app, completion_app

if TYPE_CHECKING:  # pragma: no cover - imports de typage seulement
    from ..models import RepoMetadata
    from ..services.issue_service import Destination

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
    oui: Annotated[bool, typer.Option("--yes", "-y", help=_("opt_doctor_yes"))] = False,
    clients: Annotated[bool, typer.Option("--clients", help=_("opt_doctor_clients"))] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help=_("opt_doctor_verbose"))] = False,
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

    report = collect_checks(root, _relire(root))

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

    print_doctor(report, verbose=verbose)
    joue = _reparer(report, root, oui=oui, clients=clients) if fix else False

    if strict:
        # Après des correctifs, l'état de la machine a changé : juger sur le
        # rapport d'avant dirait faux, et dans le mauvais sens : un `--fix`
        # réussi sortirait quand même en échec. On remesure.
        _verdict_strict(collect_checks(root, _relire(root)) if joue else report)


def _relire(root: Path) -> RepoMetadata | None:
    """Le meta.yml du catalogue, relu : `--fix` peut avoir choisi le provider.

    Son absence n'est pas une erreur : on diagnostique alors le strict socle
    commun. Un meta.yml illisible non plus : l'erreur est affichée, et c'est
    justement ce qu'un diagnostic doit pouvoir rapporter.
    """
    try:
        return _read_repo(root)
    except typer.Exit:
        return None


def _actions(root: Path, report: DoctorReport) -> dict[str, Action]:
    """Les étapes que dsoxlab fait lui-même, sans commande externe ni sudo."""
    from ..config import set_active_provider
    from ..infra.inventory import ajouter_include_ssh
    from ..services.doctor_controles.catalogue import creer_cle_ssh

    def provider() -> str | None:
        set_active_provider(root, report.provider)
        return None

    def include() -> str | None:
        try:
            ajouter_include_ssh()
        except OSError as exc:
            return str(exc)
        return None

    return {
        "provider": provider,
        "cle_ssh": lambda: creer_cle_ssh(root),
        "ssh_include": include,
    }


def _commande_de(etape: Etape) -> str:
    if etape.remede is not None and etape.remede.lignes:
        return etape.remede.lignes[0] + (" …" if len(etape.remede.lignes) > 1 else "")
    return titre_etape(etape)


def _afficher_plan(plan: PlanCorrection, report: DoctorReport, ansible: list[str]) -> None:
    console.print()
    info(_("fix_plan_titre", count=plan.executables))
    if plan.sans_sudo:
        console.print(Text("  " + _("fix_plan_sans_sudo")))
        for etape in plan.sans_sudo:
            console.print(Text(f"  {etape.numero:>2}. {_commande_de(etape)}"), soft_wrap=True)
    if plan.root:
        console.print(Text("  " + _("fix_plan_root")))
        for etape in plan.root:
            ligne = f"  {etape.numero:>2}. {titre_etape(etape)}"
            if etape.remede is not None and etape.remede.reconnexion:
                ligne += "   " + _("fix_plan_reconnexion")
            console.print(Text(ligne), soft_wrap=True)
        console.print(Text("      " + shlex.join(ansible), style="dim"), soft_wrap=True)
        if not _playbook_jouable(ansible[0]) and shutil.which("uv"):
            console.print(Text("  " + _("fix_plan_ansible_d_abord")), soft_wrap=True)
    _liste_du_plan("fix_plan_reverifiees", [e for e in plan.manuelles if _attend_une_etape(e)])
    _liste_du_plan("fix_plan_manuelles", [e for e in plan.manuelles if not _attend_une_etape(e)])
    for check in report.a_savoir:
        console.print(Text("  " + _("fix_plan_a_savoir", label=check.label)))


def _liste_du_plan(cle: str, etapes: list[Etape]) -> None:
    if not etapes:
        return
    console.print(Text("  " + _(cle)))
    for etape in etapes:
        console.print(Text(f"  {etape.numero:>2}. {titre_etape(etape)}"), soft_wrap=True)


def _commande_playbook(chemin: Path) -> list[str]:
    """L'appel d'ansible-playbook, avec la demande de mot de passe si sudo en exige un."""
    binaire = shutil.which("ansible-playbook") or str(Path.home() / ".local/bin/ansible-playbook")
    commande = [binaire, "-i", "localhost,", "-c", "local", str(chemin)]
    sans_mot_de_passe = subprocess.run(
        ["sudo", "-n", "true"], capture_output=True, check=False,
    ).returncode == 0 if shutil.which("sudo") else False
    if not sans_mot_de_passe:
        commande.insert(1, "--ask-become-pass")
    return commande


def _interactif() -> bool:
    """Un humain peut-il répondre ? Isolé pour que les tests le simulent."""
    return sys.stdin.isatty()


def _confirmer(plan: PlanCorrection, *, oui: bool) -> bool:
    """Rien ne part sans `[y/N]` ou `--yes`, et sans terminal rien ne part sans `--yes`."""
    if oui:
        return True
    if not _interactif():
        error(_("fix_needs_yes"))
        raise typer.Exit(1)
    if typer.confirm(_("fix_confirmer", count=plan.executables), default=False):
        return True
    info(_("fix_annule"))
    return False


def _reparer(report: DoctorReport, root: Path, *, oui: bool, clients: bool) -> bool:
    """Joue le plan de `--fix`, et dit si la machine a changé.

    Le booléen rendu décide de la remesure de `--strict` : sans étape jouée,
    remesurer coûterait un diagnostic complet pour un rapport identique.
    """
    actions = _actions(root, report)
    plan = planifier(report, clients=clients, actions=actions)
    if not plan.executables:
        info(_("fix_rien_a_lancer") if plan.manuelles else _("fix_nothing"))
        return False

    chemin = chemin_du_playbook()
    ansible = _commande_playbook(chemin) if plan.root else []
    _afficher_plan(plan, report, ansible)
    if not _confirmer(plan, oui=oui):
        return False

    def remesurer() -> DoctorReport:
        return collect_checks(root, _relire(root))

    restantes = [*plan.sans_sudo, *plan.root]
    if (
        _jouer_sans_sudo(plan.sans_sudo, actions, remesurer, restantes)
        and plan.root
        and _jouer_root(plan.root, ansible, chemin, remesurer, restantes)
    ):
        _dire_les_attendues([e for e in plan.manuelles if _attend_une_etape(e)], remesurer())
    return True


def _attend_une_etape(etape: Etape) -> bool:
    """Un contrôle sans commande qui ne faisait qu'attendre une autre étape (le
    firmware EFI attend libvirt) : il se revérifie, il n'est pas « à faire »."""
    return all(c.apres is not None for c in etape.controles)


def _dire_les_attendues(etapes: list[Etape], apres: DoctorReport) -> None:
    for etape in etapes:
        if etape_verifiee(etape, apres):
            success(_("fix_attendue_ok", step=etape.numero, label=titre_etape(etape)))
        else:
            warn(_("fix_attendue_ko", step=etape.numero, label=titre_etape(etape)))


def _jouer_sans_sudo(
    etapes: list[Etape], actions: dict[str, Action],
    remesurer: Callable[[], DoctorReport], restantes: list[Etape],
) -> bool:
    """Les étapes sans privilège, une à une, revérifiées ; rend False au premier échec."""
    for etape in etapes:
        code, message = _jouer(etape, actions)
        verifiee = code == 0 and etape_verifiee(etape, remesurer())
        application = Application(etape, code, verifiee, message)
        _dire_le_resultat(application)
        if not application.ok:
            _arreter(restantes[restantes.index(etape):])
            return False
    if not any(e.remede is not None and e.remede.root for e in restantes):
        info(_("fix_rerun"))
    return True


def _jouer_root(
    etapes: list[Etape], ansible: list[str], chemin: Path,
    remesurer: Callable[[], DoctorReport], restantes: list[Etape],
) -> bool:
    """Les étapes root, toutes par le playbook du poste, puis revérifiées une à une."""
    if not _interactif() and "--ask-become-pass" in ansible:
        # Sans terminal, personne ne peut taper le mot de passe : les étapes
        # root s'affichent en bloc à coller (décision 2).
        _bloc_root(etapes)
        return False
    if not _playbook_jouable(ansible[0]) and not _installer_ansible():
        warn(_("fix_pas_d_ansible"))
        _bloc_root(etapes)
        return False
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(playbook_du_poste(etapes, _current_user()), encoding="utf-8")
    info(_("fix_playbook", path=str(chemin)))
    code = subprocess.run(ansible, check=False).returncode
    apres = remesurer()
    for etape in etapes:
        application = Application(etape, code, code == 0 and etape_verifiee(etape, apres))
        _dire_le_resultat(application)
        if not application.ok:
            _arreter(restantes[restantes.index(etape):])
            return False
    if any(e.remede is not None and e.remede.reconnexion for e in etapes):
        warn(_("fix_reconnexion_finale"))
    info(_("fix_rerun"))
    return True


def _playbook_jouable(binaire: str) -> bool:
    return Path(binaire).is_file() and os.access(binaire, os.X_OK)


def _installer_ansible() -> bool:
    """Le playbook du poste a besoin d'Ansible : `--fix` l'installe d'abord, sans sudo.

    Décision 3 du 2026-11-16. Le cas réel : une AlmaLinux 10 sans git ni
    catalogue, où la seule étape est root (installer git) et où aucune étape
    « installer Ansible » n'est au plan, faute de lab `vm`.
    """
    if shutil.which("uv") is None:
        return False
    info(_("fix_installe_ansible"))
    if _executer_correctif(Fix((("uv", "tool", "install", "ansible-core"),))) != 0:
        return False
    return _playbook_jouable(shutil.which("ansible-playbook")
                             or str(Path.home() / ".local/bin/ansible-playbook"))


def _jouer(etape: Etape, actions: dict[str, Action]) -> tuple[int, str | None]:
    """Joue une étape sans sudo : une action de dsoxlab, ou un correctif sans shell."""
    _dire_la_commande(etape)
    action = actions.get(etape.cle)
    if action is not None:
        message = action()
        return (0, None) if message is None else (1, message)
    correctif = next((c.fix for c in etape.controles if c.fix is not None), None)
    if correctif is None:
        return 1, None
    return _executer_correctif(correctif), None


def _dire_la_commande(etape: Etape) -> None:
    """La commande est nommée avant de partir : sa sortie arrive sur le même
    terminal, et sans cette ligne rien ne dit à qui elle appartient."""
    console.print(Text(f"  → {etape.numero}. {_commande_de(etape)}", style="bold"), soft_wrap=True)


def _dire_le_resultat(application: Application) -> None:
    etape = application.etape
    titre = titre_etape(etape)
    if application.code != 0:
        error(_("fix_etape_ko", step=etape.numero, label=titre, code=application.code))
        if application.message:
            console.print(Text("    " + application.message), soft_wrap=True)
        return
    if not application.verifiee:
        error(_("fix_etape_non_verifiee", step=etape.numero, label=titre))
        return
    success(_("fix_etape_ok", step=etape.numero, label=titre))
    # L'effet différé se dit au moment du succès, sans quoi le prochain
    # `doctor` remontre la même ligne rouge et l'utilisateur conclut, à tort,
    # que le correctif a échoué.
    avis = application.avis_differe
    if avis is not None:
        warn(_(avis, label=titre))


def _arreter(restantes: list[Etape]) -> None:
    numeros = ", ".join(str(e.numero) for e in restantes)
    error(_("fix_arret", steps=numeros))


def _bloc_root(etapes: list[Etape]) -> None:
    """Le repli : les étapes root à coller, puisque dsoxlab ne les lance pas."""
    warn(_("fix_bloc_root"))
    for etape in etapes:
        console.print(Text(f"  {etape.numero:>2}. {titre_etape(etape)}", style="bold"))
        assert etape.remede is not None
        for ligne in etape.remede.lignes:
            console.print(Text("      " + ligne), soft_wrap=True)


def _executer_correctif(correctif: Fix) -> int:
    """Joue les commandes d'un correctif, dans l'ordre, sans shell.

    Chaque argv part tel quel à ``run_command`` : aucun token n'est redécoupé
    en route, un argument portant une espace arrive entier à la commande. La
    séquence s'arrête au premier échec, dont le code est rendu.

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

    # Rendre la démonstration ACTIVE, et c'est le parcours joué qui l'a imposé :
    # sans cela, les trois commandes affichées juste en dessous échouaient
    # toutes les trois sur « Lab introuvable » pour qui n'avait pas fait le
    # `cd` que ce message glissait sur une ligne séparée. `catalog add` posait
    # déjà son catalogue actif et le disait ; `demo` affichait un chemin de
    # quatre-vingt-dix caractères et laissait l'apprenant le recopier.
    #
    # L'échec est volontairement silencieux : la démonstration est installée,
    # et un pointeur qu'on n'a pas pu écrire ne doit pas transformer un succès
    # en erreur. Le chemin reste affiché juste après, donc le `cd` demeure
    # possible.
    from ..services import catalog

    try:
        catalog.definir_actif(installation.racine)
    except Exception:
        # Un `except Exception` nu est accepté ici parce que la cause ne change
        # pas le geste : la démonstration est posée, le pointeur est un confort.
        logger.warning("could not mark the demo catalog as active", exc_info=True)

    # La marche à suivre est construite depuis le catalogue réellement
    # installé : elle ne peut donc pas décrire un lab qui n'y serait plus.
    premier = installation.labs[0] if installation.labs else ""
    info(_("demo_suite", lab=premier))
    note(_("demo_repertoire", path=str(installation.racine)))


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


def _router_issue(
    root: Path,
    repo_meta: RepoMetadata | None,
    *,
    vers_moteur: bool,
    vers_catalogue: bool,
) -> Destination | None:
    """Le dépôt visé : le catalogue dès qu'on en a un et qu'on sait où lui écrire.

    Le lab actif ne décide plus (issue #228). Il décidait jusqu'en 0.1.86, et
    cela renvoyait au moteur quiconque n'avait pas encore lancé de lab, **depuis
    la racine d'un catalogue**, section active posée et ``repo.issues_url``
    déclaré. Or c'est exactement la situation de celui dont le ``run`` vient
    d'échouer, ou qui n'arrive pas à provisionner : son rapport partait au
    moteur alors que la cause pouvait être le ``setup.yaml`` d'un lab.

    La règle tient désormais en une phrase, et c'est ce qui la rend tenable : on
    écrit au catalogue quand on en a un sous la main et qu'on sait où lui
    écrire, au moteur sinon. Elle ne distingue pas selon l'origine de l'adresse
    (``repo.issues_url`` ou remote ``origin``) : deux règles là où une suffit
    seraient deux règles à expliquer, et ``--engine`` reste le recours de celui
    qui sait que son défaut vient de l'outil.
    """
    from ..services.issue_service import Cible, resoudre_destination

    if vers_moteur:
        return resoudre_destination(root, repo_meta, cible=Cible.MOTEUR)
    if vers_catalogue:
        return resoudre_destination(root, repo_meta, cible=Cible.CATALOGUE)

    # `repo_meta is None` veut dire « pas de catalogue ici, ou illisible ». Dans
    # les deux cas on ne peut rien affirmer sur un lab, donc le moteur.
    if repo_meta is not None:
        trouve = resoudre_destination(root, repo_meta, cible=Cible.CATALOGUE)
        if trouve is not None:
            return trouve
    return resoudre_destination(root, repo_meta, cible=Cible.MOTEUR)


def _contexte_issue(rapport: dict[str, Any]) -> dict[str, str]:
    """Les champs déductibles du rapport.

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
    return champs


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
    from ..services.issue_service import Repli, construire_lien
    from ..services.support import en_markdown

    champs = _contexte_issue(rapport)

    destination = _router_issue(
        root,
        _repo_meta_tolerant(root),
        vers_moteur=vers_moteur,
        vers_catalogue=vers_catalogue,
    )
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
        # Le libellé est tiré de l'URL du catalogue : il s'affiche, il ne
        # met pas Rich en forme.
        depot=texte_affichable(destination.libelle),
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
        #
        # markup=False : l'URL est validée par la politique de
        # `security/urls.py`, donc sans caractère de contrôle, mais le corps
        # pré-rempli porte le rapport de diagnostic et le nom du dépôt vient du
        # catalogue. Rien de tout cela n'a à piloter l'affichage.
        console.print(lien.url, soft_wrap=True, markup=False)
        return

    demande = _("issue_confirmer", depot=texte_affichable(destination.libelle))
    if not assume_yes and not typer.confirm(demande):
        info(_("issue_abandon"))
        return

    console.print(lien.url, soft_wrap=True, markup=False)
    # L'ouverture reste demandée : la confirmation ci-dessus nomme le dépôt
    # visé, et `--yes` est un accord donné d'avance par l'utilisateur. Une
    # valeur du catalogue ne déclenche à elle seule aucune navigation.
    if not webbrowser.open(lien.url):
        error(_("issue_sans_navigateur"))


# ── fullhelp ──────────────────────────────────────────────────────────────────

@app.command("fullhelp", help=_("cmd_fullhelp_help"))
def fullhelp() -> None:
    print_fullhelp()
