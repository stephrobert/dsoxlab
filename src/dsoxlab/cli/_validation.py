"""Le verdict d'un lab, et la phrase qui explique un échec.

Tout ce que le paquet partage pour **noter et diagnostiquer** vit ici : jouer
pytest en streamant les verdicts (``_run_check_with_progress``), enregistrer
la note sous verrou (``_run_check`` / ``_valider``), compter les anomalies de
``validate-structure`` (``_compter``), et composer la phrase actionnable d'un
échec d'infrastructure (``_undefine_command``, ``_diagnostic_message``).

Même convention que ``_commun`` : un ``except`` qui a déjà rendu la cause en
une phrase traduite (``error(...)``) sort par ``raise typer.Exit(n) from
None``, l'affirmation que la cause a été dite à l'utilisateur.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from ..config import read_context
from ..i18n import _
from ..infra.inventory import InfraNotProvisioned
from ..models import LabDefinition, ProviderUnresolved
from ..reporting import (
    console,
    error,
    info,
    print_check_result,
)
from ..services import (
    CheckResult,
    check_lab,
    evaluate_lab,
    host_diagnosis,
)
from ._commun import _ensure_services, _verrou

#: Les familles de contrôle de ``validate-structure``, dans l'ordre où elles
#: sont jouées. Elles figurent **toutes** dans ``counts``, à zéro s'il le faut :
#: un tableau de bord qui n'aurait pas la clé ne saurait pas si la famille est
#: saine ou si cette version de l'outil ne la connaît pas.
_FAMILLES_ANOMALIES = (
    "contract", "unknown_key", "structure", "content", "doc_url", "metadata",
)


def _compter(anomalies: list[dict[str, Any]]) -> dict[str, int]:
    """Le nombre d'anomalies par famille, toutes familles présentes."""
    compte = dict.fromkeys(_FAMILLES_ANOMALIES, 0)
    for anomalie in anomalies:
        compte[str(anomalie["kind"])] += 1
    return compte



def _run_check_with_progress(
    lab: LabDefinition, target: str | None = None, *, quiet: bool = False,
) -> CheckResult:
    """Lance ``check_lab`` en streamant les verdicts pytest dans une
    progress bar Rich.

    ``target`` sélectionne la target du lab sur laquelle valider (labs
    multi-distrib). None = la target ``default`` du lab.

    Affiche un ✔/✘/⊘ par test et une barre M of N. En cas d'échec,
    le caller imprime le résumé/traceback contenu dans ``result.output``.
    """
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    state: dict[str, Any] = {"done": 0, "task_id": None}

    # Mode machine : la barre et les verdicts partent sur stdout et
    # rendraient le document JSON illisible. On lance les tests sans rien
    # afficher — mesuré, sans cela la sortie commence par « ℹ Validation… ».
    if quiet:
        return check_lab(lab, target=target)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        transient=False,
        console=console,
    ) as progress:
        task = progress.add_task("Collecte des tests…", total=None)
        state["task_id"] = task

        def on_event(event: dict[str, Any]) -> None:
            etype = event.get("type")
            if etype == "collected":
                total = event.get("total", 0) or None
                progress.update(
                    task,
                    description=_("progress_tests_running", lab_id=lab.id),
                    total=total,
                )
            elif etype == "verdict":
                nodeid = event.get("nodeid", "?")
                verdict = event.get("verdict", "?")
                # Raccourcit le nodeid pour l'affichage : ne garde que test_xxx::test_yyy
                short = nodeid.rsplit("/", 1)[-1]
                state["done"] += 1
                progress.update(task, completed=state["done"])
                if verdict == "PASSED":
                    progress.console.print(f"  [green]✔[/green] {short}")
                elif verdict in ("FAILED", "ERROR"):
                    progress.console.print(f"  [red]✘ {short}  [dim]({verdict})[/dim][/red]")
                elif verdict == "SKIPPED":
                    progress.console.print(f"  [dim]⊘ {short}  (skipped)[/dim]")
                else:
                    progress.console.print(f"  [yellow]·[/yellow] {short}  [dim]({verdict})[/dim]")
            # Les autres lignes (log/header/traceback) sont gardées dans
            # result.output et imprimées seulement si le check échoue.

        result = check_lab(lab, target=target, on_event=on_event)
        progress.update(task, description=_("progress_tests_done", lab_id=lab.id))

    return result


def _run_check(
    root: Path, lab: LabDefinition, target: str | None = None, *, quiet: bool = False,
) -> tuple[CheckResult, int, int]:
    """Lance les tests, enregistre le résultat, retourne (result, score, max_score).

    ``target`` (option ``--target``) l'emporte sur la target active de la
    session ; à défaut, la target ``default`` du lab s'applique.
    """
    # Même logique que pour --target : on refuse de NOTER ce qui n'a pas pu
    # tourner. Un lab VM sans infrastructure n'est pas un échec de l'apprenant
    # et ne doit pas lui coûter un 0/100 dans son historique. pytest tourne en
    # sous-processus, donc l'erreur du conftest ne remonterait pas jusqu'ici :
    # il faut vérifier AVANT.
    if lab.runtime.type.value in ("vm", "kvm", "incus"):
        from ..discovery.repo import read_repo_metadata
        from ..infra.inventory import build_inventory, read_terraform_outputs

        repo_meta = read_repo_metadata(root)
        if repo_meta is not None:
            try:
                build_inventory(
                    repo_meta,
                    terraform_outputs=read_terraform_outputs(repo_meta),
                )
            except InfraNotProvisioned:
                error(_("infra_not_provisioned"))
                raise typer.Exit(2) from None
            except ProviderUnresolved as exc:
                # Un dépôt qui déclare plusieurs providers sans qu'aucun ne
                # soit actif : lire les outputs Terraform est impossible, mais
                # ce n'est pas une faute de l'apprenant. Sans ce garde-fou, la
                # traceback remontait telle quelle depuis inventory.py.
                if not exc.candidates:
                    error(_("provider_none_declared"))
                else:
                    error(_("provider_required",
                            candidates=", ".join(exc.candidates),
                            first=exc.candidates[0]))
                raise typer.Exit(2) from None

    # Un --target explicite et inconnu est une ERREUR : on sort avant de
    # lancer quoi que ce soit, sinon une faute de frappe enregistrerait un
    # 0/100 dans l'historique de l'apprenant.
    if target is not None and lab.runtime.target(target) is None:
        declared = ", ".join(t.name for t in lab.runtime.targets) or "—"
        error(_("unknown_target", target=target, declared=declared))
        raise typer.Exit(1)

    # À défaut, la target de session. Elle vaut pour TOUS les labs du dépôt :
    # si celui-ci ne la déclare pas (lab shell, lab mono-target), on l'ignore
    # simplement — ce n'est pas une erreur de l'apprenant.
    if target is None:
        session_target = read_context(root).active_target
        if session_target and lab.runtime.target(session_target) is not None:
            target = session_target

    # Le verrou couvre les services ET pytest. Les tests pilotent la machine
    # du lab (ou ses conteneurs) : deux validations concurrentes se marchent
    # dessus, et la seconde note un état que la première est en train de
    # changer. Il est pris ICI, pas au début : tout ce qui précède ne fait que
    # lire, et refuser une faute de frappe sur `--target` pour cause de verrou
    # serait absurde.
    with _verrou(root, "check"):
        return _valider(root, lab, target, quiet=quiet)


def _valider(
    root: Path, lab: LabDefinition, target: str | None, *, quiet: bool,
) -> tuple[CheckResult, int, int]:
    """Joue les tests et enregistre la note. Appelé sous verrou."""
    # Les services conteneurisés (émulateur cloud, base…) doivent être debout
    # avant que pytest ne s'exécute : les tests pilotent l'API qu'ils exposent.
    _ensure_services(lab, root)

    if not quiet:
        info(_("validating", lab_id=lab.id))
    result = _run_check_with_progress(lab, target, quiet=quiet)
    if not result.ok and not quiet:
        # En cas d'échec, dump l'output brut (tracebacks, summary pytest)
        # pour que l'apprenant voie les erreurs détaillées.
        #
        # « and not quiet » : sans lui, la sortie pytest précédait le document
        # JSON sur stdout dès qu'un test échouait, et le flux n'était plus
        # analysable. Le cas le plus fréquent en usage réel, et le plus facile
        # à manquer : un lab qui passe n'emprunte jamais cette branche.
        # L'appelant en mode machine retrouve ce texte dans check.output.
        console.print(result.output)

    evaluation = evaluate_lab(root, lab, result)
    if not evaluation.enregistre and not quiet:
        # Rien n'a été mesuré : le dire, plutôt que d'afficher un 0 que
        # l'apprenant lirait comme un exercice raté.
        error(_("check_rien_mesure"))
        info(_("check_rien_mesure_suite"))
        return result, evaluation.score, evaluation.max_score
    if quiet:
        # Mode machine : le tableau Rich et le message de confirmation
        # pollueraient le document JSON. Le résultat est tout de même
        # enregistré, comme dans le mode normal.
        return result, evaluation.score, evaluation.max_score
    print_check_result(
        lab.id,
        result.passed,
        result.total,
        evaluation.max_score,
        evaluation.score,
        evaluation.hints_used,
        evaluation.hints_cost,
    )
    info(_("check_result_saved", score=evaluation.score, max_score=evaluation.max_score))
    return result, evaluation.score, evaluation.max_score


def _undefine_command(orphans: dict[str, str]) -> str:
    """La commande exacte qui retire des machines restées sur l'hyperviseur.

    Rendue copiable telle quelle : dire « supprime-les » sans donner le geste
    laisse l'apprenant chercher ``virsh undefine``, qu'aucune page du parcours
    ne lui a montré. ``sudo`` sans ``-n``, ici : c'est un humain qui la tape,
    un mot de passe demandé au terminal ne pose aucun problème.
    """
    return "; ".join(
        f"sudo virsh undefine --nvram {domain}" for domain in sorted(orphans.values())
    )


def _diagnostic_message(hote: dict[str, Any]) -> str:
    """La phrase qui nomme la cause d'un hôte muet, et le geste qui la corrige.

    Une cause, un message, une action. L'ancien texte en proposait deux à la
    fois — « cloud-init tourne peut-être encore, ou alors reprovisionne » — pour
    tous les hôtes et toutes les pannes : l'apprenant devait trancher lui-même
    entre deux conseils dont l'un coûtait une infrastructure entière.
    """
    cause = hote["cause"]
    domaine = hote.get("domain") or hote["fqdn"]
    if cause == host_diagnosis.CAUSE_DOMAIN_ABSENT:
        return _("status_cause_domain_absent", host=hote["fqdn"])
    if cause == host_diagnosis.CAUSE_DOMAIN_NOT_RUNNING:
        return _("status_cause_domain_not_running",
                 domain=domaine, state=hote.get("domain_state") or "?")
    if cause == host_diagnosis.CAUSE_DOMAIN_NO_LEASE:
        return _("status_cause_domain_no_lease", domain=domaine)
    if cause == host_diagnosis.CAUSE_BOOTING:
        return _("status_cause_booting", domain=domaine)
    if cause == host_diagnosis.CAUSE_SSH_REFUSED:
        return _("status_cause_ssh_refused", ip=hote["ip"])
    if cause == host_diagnosis.CAUSE_UNREACHABLE:
        return _("status_cause_unreachable", ip=hote["ip"])
    if cause == host_diagnosis.CAUSE_SSH_TIMEOUT:
        return _("status_cause_ssh_timeout", ip=hote["ip"])
    if cause == host_diagnosis.CAUSE_SSH_DENIED:
        return _("status_cause_ssh_denied", ip=hote["ip"])
    return _("status_cause_unknown", reason=hote.get("reason") or "?")
