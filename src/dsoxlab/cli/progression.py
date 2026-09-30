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

import json
import logging
import os
from pathlib import Path
from typing import Annotated, Any

import typer

from ..config import (
    read_context,
    set_active_lab,
)
from ..i18n import _
from ..interrupt import (
    Interrupted,
)
from ..models.lab import LabDefinition
from ..reporting import (
    console,
    error,
    info,
    machine,
    note,
    print_progress_table,
    print_scores_table,
    success,
    warn,
)
from ..security.terminal import texte_affichable
from ..services import (
    clean_lab,
    next_pending_lab,
    reset_lab,
)
from ..services.lab_service import a_mesure
from ..sessions.store import (
    get_best_scores,
    get_results,
    reset_hints,
)
from ..utils.fichiers import ecrire_atomiquement
from ._barres import (
    _run_ansible_with_progress,
)
from ._commun import (
    LabHomeOption,
    _catalogue,
    _complete_lab_id,
    _interrompu,
    _lab,
    _lang,
    _resolve_lab,
    _root,
    _stop_services,
    _verrou,
)
from ._socle import app
from ._validation import _run_check

logger = logging.getLogger(__name__)



# ── check ─────────────────────────────────────────────────────────────────────

@app.command("check", help=_("cmd_check_help"))
def check(
    lab_id: Annotated[str | None, typer.Argument(help=_("cmd_check_arg"), autocompletion=_complete_lab_id)] = None,
    target: Annotated[str | None, typer.Option("--target", "-t",
        help=_("opt_check_target"))] = None,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lab = _resolve_lab(root, lab_id, _lang(root))
    try:
        result, score, max_score = _run_check(root, lab, target, quiet=as_json)
    except Interrupted as exc:
        _interrompu(exc, f"dsoxlab check {lab.id}")
    if as_json:
        # La sortie brute de pytest est conservée : c'est là que l'appelant
        # trouve le détail des échecs, qu'aucun compteur ne résume.
        machine.emit({
            "lab": machine.lab_dict(lab),
            "check": {
                "ok": result.ok,
                "passed": result.passed,
                "total": result.total,
                "score": score,
                "max_score": max_score,
                # `recorded` dit si la note vaut quelque chose : une exécution
                # qui n'a rien collecté rend 0 sans être inscrite, et un
                # tableau de bord qui l'ignorerait afficherait un lab « raté »
                # là où rien n'a pu être joué.
                "recorded": a_mesure(result),
                "output": result.output,
            },
        })
        if not result.ok:
            raise typer.Exit(1)
        return
    if result.ok:
        success(_("all_tests_passed"))
        info(_("check_tip_submit"))
    else:
        error(_("tests_failed"))
        raise typer.Exit(1)


# ── submit ────────────────────────────────────────────────────────────────────

# ── submit ────────────────────────────────────────────────────────────────────

@app.command("submit", help=_("cmd_submit_help"))
def submit(
    lab_id: Annotated[str | None, typer.Argument(help=_("cmd_submit_arg"), autocompletion=_complete_lab_id)] = None,
    target: Annotated[str | None, typer.Option("--target", "-t",
        help=_("opt_check_target"))] = None,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lab = _resolve_lab(root, lab_id, _lang(root))
    try:
        result, score, max_score = _run_check(root, lab, target)
    except Interrupted as exc:
        _interrompu(exc, f"dsoxlab submit {lab.id}")

    # « Submission recorded » n'est vrai que si quelque chose a été enregistré.
    # Deux cas où rien ne l'est, et où l'annoncer trompait : un lab `validation`,
    # qui défend un guide et ne note personne, et une exécution qui n'a mesuré
    # aucun test — un `conftest.py` qui lève, une machine injoignable. `check`
    # disait déjà le premier ; `submit` l'affirmait au contraire.
    if not lab.is_exercise:
        info(_("check_validation_sans_note"))
    elif not a_mesure(result):
        warn(_("submit_sans_mesure", total=result.total))
    elif result.ok:
        success(_("submit_success", score=score, max_score=max_score))
    else:
        info(_("submit_partial", passed=result.passed, total=result.total, score=score, max_score=max_score))

    # Un lab qui déclare un seuil est un examen blanc, et un examen rend un
    # verdict. Sans lui, un apprenant qui rendait 40/100 sur un mock RHCSA ne
    # lisait nulle part qu'il avait échoué : la note s'affichait, jamais son
    # sens. Un lab ordinaire n'en déclare pas et n'affiche donc rien.
    from ..services.progress_service import exam_percentage, exam_verdict

    verdict = exam_verdict(score, max_score, lab.exam_passing_score)
    if verdict is not None:
        cle = "exam_passed" if verdict else "exam_failed"
        rendu = success if verdict else error
        rendu(_(
            cle,
            pct=exam_percentage(score, max_score),
            threshold=lab.exam_passing_score,
        ))

    _proposer_la_remise(root, lab)

    set_active_lab(root, None)
    console.print()
    # CTA "tape exit" uniquement si on est dans le sous-shell ouvert
    # par ``dsoxlab run`` (cas runtime shell). Sur runtime vm,
    # l'apprenant est revenu sur son poste local — pas de sous-shell
    # à fermer, donc le message serait trompeur.
    if os.environ.get("DSOXLAB_LAB_SESSION"):
        console.print(_("submit_exit_cta"))
    else:
        console.print(_("submit_done"))


def _proposer_la_remise(root: Path, lab: LabDefinition) -> None:
    """Affiche le lien de remise, si ce catalogue déclare un portail.

    Trois conditions, et aucune n'est devinée : la tentative vient d'être
    **enregistrée**, le catalogue **déclare** un portail, et la preuve **tient**
    dans un fragment d'URL. Faute de portail, on ne dit rien du tout — pas
    d'avertissement, pas d'adresse par défaut, parce qu'un catalogue sans portail
    est un cas normal et non une configuration manquante.

    **Réussie ou non.** Le lien s'affiche après une tentative ratée aussi : une
    preuve atteste ce qui s'est passé, et un portail sait en faire une file de
    révision (« non validée, 3 tentatives, dernière 6/8 »). Ne montrer que les
    réussites fabriquerait une progression flatteuse, et l'export complet, lui,
    porte déjà les échecs.

    **Rien n'est envoyé.** Pas de navigateur ouvert, pas de requête, pas de nom
    résolu : l'adresse s'affiche, l'hôte est nommé à part, et l'apprenant décide.
    C'est aussi ce que le texte dit, en toutes lettres, parce qu'un lien qui
    apparaît après un test laisse spontanément croire qu'une transmission a eu
    lieu.

    Aucune de ces situations ne fait échouer `submit` : la tentative est
    enregistrée, et un défaut de portail est un défaut de catalogue.
    """
    from ..discovery.repo import read_repo_metadata
    from ..security import IdentifiantRefuse
    from ..security.urls import URLRefusee
    from ..services.evidence import (
        ChargeTropGrande,
        PreuveIntrouvable,
        construire_document,
        hote_du_portail,
        identifiant_de_catalogue,
        lien_de_remise,
    )

    try:
        repo_meta = read_repo_metadata(root)
    except Exception:  # noqa: BLE001 — un meta.yml illisible n'est pas le sujet
        return
    if repo_meta is None:
        return
    portail = repo_meta.learning.portal_url.strip()
    if not portail:
        return

    try:
        catalog_id = identifiant_de_catalogue(root, repo_meta.id)
        document = construire_document(
            root, {lab.id: lab}, catalog_id=catalog_id, lab_id=lab.id
        )
        lien = lien_de_remise(portail, document)
        hote = hote_du_portail(portail)
    except URLRefusee as refus:
        # L'adresse vient du catalogue : on dit pourquoi elle ne sert pas, sans
        # recopier la chaîne fautive, et on n'affiche aucun lien.
        warn(_("remise_portail_refuse", reason=_(refus.cle, **refus.params)))
        return
    except ChargeTropGrande as trop:
        warn(_("remise_charge_trop_grande", size=trop.taille, max=trop.limite))
        return
    except (IdentifiantRefuse, PreuveIntrouvable):
        # Un identifiant hors contrat est déjà dit par `export`, et une preuve
        # introuvable juste après l'avoir enregistrée ne peut venir que d'un lab
        # `validation`, qui n'atteste rien.
        return

    console.print()
    # `markup=False` partout : l'hôte comme le lien viennent du catalogue.
    console.print(_("remise_portail_declare"))
    console.print(f"  {hote}", markup=False)
    console.print()
    console.print(_("remise_rien_envoye"))
    # soft_wrap : une URL coupée sur deux lignes n'est plus copiable, et celle-ci
    # est longue par construction.
    console.print(lien, soft_wrap=True, markup=False)


# ── scores ────────────────────────────────────────────────────────────────────

# ── scores ────────────────────────────────────────────────────────────────────

@app.command("scores", help=_("cmd_scores_help"))
def scores(
    lab_home: LabHomeOption = None,
    section: Annotated[str | None, typer.Option("--section", "-s", help=_("opt_section"))] = None,
    lab_id: Annotated[str | None, typer.Option("--lab", "-l", help=_("opt_filter_lab"))] = None,
    top: Annotated[int, typer.Option("--top", help=_("opt_top"))] = 20,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    root = _root(lab_home)
    ctx = read_context(root)
    effective_section = section or ctx.section
    results = get_results(root, lab_id=lab_id, section=effective_section, limit=top)
    # Les seuils vivent dans le catalogue, les notes dans la base : le verdict
    # d'un examen demande les deux. On ne balaie que pour les labs affichés.
    affiches = {r["lab_id"] for r in results}
    seuils = {
        lab.id: lab.exam_passing_score
        for lab in _catalogue(root, _lang(root), quiet=as_json)
        if lab.exam_passing_score and lab.id in affiches
    }
    if as_json:
        machine.emit({
            "results": [machine.score_dict(r, seuils.get(r["lab_id"])) for r in results],
            "count": len(results),
        })
        return
    print_scores_table(results, seuils)


# ── export ────────────────────────────────────────────────────────────────────

@app.command("export", help=_("cmd_export_help"))
def export(
    lab_home: LabHomeOption = None,
    lab: Annotated[str | None, typer.Option(
        "--lab", help=_("opt_export_lab"), autocompletion=_complete_lab_id,
    )] = None,
    sortie: Annotated[Path | None, typer.Option(
        "--out", "-o", help=_("opt_export_out"),
    )] = None,
    force: Annotated[bool, typer.Option("--force", help=_("opt_export_force"))] = False,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_export_json"))] = False,
) -> None:
    """Les résultats en un document, entier ou réduit à un seul lab.

    Une commande à part plutôt qu'une option de ``scores``, et la raison tient
    en une phrase : ``scores`` est un **affichage**, borné à vingt lignes par
    défaut et cinquante par la base. Un export borné est pire qu'absent, parce
    que celui qui le lit croit tout avoir.

    ``--lab`` rend la **dernière tentative** enregistrée pour ce lab, dans le
    même document, avec ``count: 1``. Un second format aurait obligé chaque
    consommateur à en gérer deux, pour dire la même chose.

    ``--out`` écrit le document dans un fichier et laisse la sortie standard
    **vide** : c'est le repli universel quand le terminal ne rend pas les liens
    cliquables, quand le navigateur est sur une autre machine, ou quand un
    formateur collecte les preuves autrement. Le fichier n'est pas écrasé sans
    ``--force`` — une preuve remplacée en silence est une preuve perdue.

    ``--json`` est accepté sans rien changer : ce document est machine par
    nature, il n'a pas de forme terminal. L'option existe parce que la
    cohérence de la CLI le suggère et qu'un utilisateur la tapera.
    """
    del as_json  # accepté pour la cohérence, sans effet : voir la docstring
    from ..discovery.repo import read_repo_metadata
    from ..security import IdentifiantRefuse
    from ..services.evidence import (
        PreuveIntrouvable,
        construire_document,
        identifiant_de_catalogue,
    )

    root = _root(lab_home)
    labs = {definition.id: definition for definition in _catalogue(root, _lang(root), quiet=True)}

    if lab is not None and lab not in labs:
        # Un lab inconnu se cherche, une preuve absente se gagne : deux messages.
        error(_("err_lab_not_found", lab_id=texte_affichable(lab)))
        raise typer.Exit(1)

    try:
        repo_meta = read_repo_metadata(root)
    except Exception:  # noqa: BLE001 — un meta.yml illisible ne doit pas priver
        repo_meta = None                # l'apprenant de son propre historique

    try:
        catalog_id = identifiant_de_catalogue(root, repo_meta.id if repo_meta else None)
        document = construire_document(root, labs, catalog_id=catalog_id, lab_id=lab)
    except IdentifiantRefuse as refus:
        error(_("export_identifiant_refuse", field=refus.champ,
                reason=_(refus.cle, **refus.params)))
        # `note` et non `info` : `export` rend un document, et une erreur dure
        # doit laisser la sortie standard VIDE. Un conseil sur stdout suffit à
        # casser le `json.loads` de l'appelant.
        note(_("export_identifiant_refuse_suite"))
        raise typer.Exit(1) from None
    except PreuveIntrouvable as absence:
        error(_(absence.cle, lab_id=texte_affichable(absence.lab_id)))
        raise typer.Exit(1) from None

    if sortie is None:
        machine.emit(document)
        return

    _ecrire_preuve(sortie, document, force=force)


def _ecrire_preuve(sortie: Path, document: dict[str, Any], *, force: bool) -> None:
    """Écrit le document dans un fichier, sans surprise et sans écrasement muet.

    Trois précautions, chacune pour un accident déjà vu ailleurs :

    - **rien n'est écrasé sans ``--force``**, pas même un fichier que dsoxlab a
      écrit lui-même. Une preuve remplacée en silence est une preuve perdue, et
      l'apprenant ne s'en aperçoit qu'en la remettant ;
    - **un lien symbolique n'est jamais suivi** sans le dire. Écrire « dans »
      un lien écrit en réalité ailleurs, à un endroit que l'utilisateur n'a pas
      nommé ;
    - **l'écriture est atomique** (``utils/fichiers.py``) : un Ctrl-C ne laisse
      pas un JSON coupé au milieu d'une accolade, qui se lit comme un fichier
      valide jusqu'à ce qu'on le parse.

    La sortie standard reste vide : c'est le contrat de la sortie machine, et un
    appelant qui redirige `--out` ne veut rien voir passer dans le tube.
    """
    if sortie.is_symlink():
        error(_("export_fichier_lien", path=str(sortie)))
        raise typer.Exit(1)
    if sortie.exists() and not force:
        error(_("export_fichier_existe", path=str(sortie)))
        info(_("export_fichier_existe_suite"))
        raise typer.Exit(1)

    try:
        ecrire_atomiquement(
            sortie,
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            mode=_mode_de_fichier(),
        )
    except OSError as exc:
        error(_("export_fichier_erreur", path=str(sortie), error=str(exc)))
        raise typer.Exit(1) from None

    # Sur stderr : un `--out` redirigé ne doit rien recevoir sur stdout, et la
    # confirmation reste utile à un humain.
    note(_("export_fichier_ecrit", path=str(sortie), count=document["count"]))


def _mode_de_fichier() -> int:
    """Les permissions d'un fichier ordinaire sur cette machine.

    `ecrire_atomiquement` passe par `tempfile.mkstemp`, qui crée en `0600` —
    juste pour un `ssh_config`, trop pour une preuve. Ce document ne porte aucun
    secret (c'est l'invariant de son contrat), et un formateur doit pouvoir le
    lire sans commencer par un `chmod`.

    L'umask est lu en le reposant aussitôt : POSIX n'offre pas de lecture seule,
    et c'est ce que fait n'importe quelle création de fichier. On rend donc ce
    que `open()` aurait produit, ni plus permissif ni moins.
    """
    umask = os.umask(0o022)
    os.umask(umask)
    return 0o666 & ~umask


# ── progress ──────────────────────────────────────────────────────────────────

@app.command("progress", help=_("cmd_progress_help"))
def progress(
    lab_home: LabHomeOption = None,
    section: Annotated[str | None, typer.Option("--section", "-s", help=_("opt_section"))] = None,
    level: Annotated[str | None, typer.Option("--level", "-l", help=_("opt_level"))] = None,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    root = _root(lab_home)
    ctx = read_context(root)
    lang = _lang(root)

    effective_section = section or ctx.section
    effective_level = level or ctx.level

    labs = _catalogue(root, lang, quiet=as_json)
    # Un lab `validation` défend un guide publié et ne note personne : le
    # compter dans une progression fabrique un dénominateur que rien ne peut
    # atteindre. `next` l'écartait déjà ; le contrat l'annonçait pour toute la
    # progression, et c'est ici que la promesse manquait.
    labs = [lab for lab in labs if lab.is_exercise]
    if effective_section:
        labs = [lab for lab in labs if lab.section == effective_section]
    if effective_level:
        labs = [lab for lab in labs if lab.level == effective_level]

    # Sort by bloc then bloc_order for a coherent display
    labs = sorted(labs, key=lambda lab: (lab.bloc, lab.bloc_order, lab.id))

    lab_ids = [lab.id for lab in labs]
    scores_data = get_best_scores(root, lab_ids)
    if as_json:
        faits = [i for i in lab_ids if i in scores_data]
        machine.emit({
            "labs": [machine.lab_dict(lab, scores_data.get(lab.id)) for lab in labs],
            "summary": {
                "total": len(labs),
                "attempted": len(faits),
                "points": sum(scores_data[i][0] for i in faits),
                "max_points": sum(scores_data[i][1] for i in faits),
            },
        })
        return
    print_progress_table(labs, scores_data)


# ── next ──────────────────────────────────────────────────────────────────────

# ── next ──────────────────────────────────────────────────────────────────────

@app.command("next", help=_("cmd_next_help"))
def next_lab(
    lab_home: LabHomeOption = None,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    root = _root(lab_home)
    ctx = read_context(root)
    lang = _lang(root)

    # Erreur dure, en `--json` comme ailleurs : sans contexte il n'y a rien à
    # décrire. La cause part sur stderr, la sortie standard reste vide, et le
    # code de retour ne change pas.
    if not ctx.section:
        error(_("next_no_context"))
        raise typer.Exit(1)

    labs = _catalogue(root, lang, quiet=as_json)
    if ctx.section:
        labs = [lab for lab in labs if lab.section == ctx.section]
    if ctx.level:
        labs = [lab for lab in labs if lab.level == ctx.level]

    scores_data = get_best_scores(root, [lab.id for lab in labs])

    upcoming = next_pending_lab(labs, scores_data)
    if as_json:
        # `next` et `all_done` disent deux choses différentes : un contexte
        # sans lab du tout rendrait aussi `next: null`, et l'appelant fêterait
        # une section terminée qui est en fait vide.
        machine.emit({
            "context": {"section": ctx.section, "level": ctx.level or None},
            "next": None if upcoming is None
            else machine.lab_dict(upcoming, scores_data.get(upcoming.id)),
            "all_done": upcoming is None and bool(labs),
            # `is_exercise` : un lab `validation` ne recevra jamais de
            # résultat, donc le compter comme « restant » annonce un travail
            # qui ne s'achèvera pas. `next` ne le propose déjà pas.
            "remaining": sum(
                1 for lab in labs
                if lab.is_exercise and lab.id not in scores_data
            ),
        })
        return
    if upcoming is None:
        success(_("next_all_done"))
        return
    success(_("next_suggestion", lab_id=texte_affichable(upcoming.id),
                title=texte_affichable(upcoming.title)))


# ── reset ─────────────────────────────────────────────────────────────────────

# ── reset ─────────────────────────────────────────────────────────────────────

@app.command("reset", help=_("cmd_reset_help"))
def reset(
    ctx: typer.Context,
    lab_id: Annotated[str, typer.Argument(help=_("cmd_reset_arg"), autocompletion=_complete_lab_id)],
    target: Annotated[str | None, typer.Option("--target", "-t",
        help=_("opt_run_target"))] = None,
    lab_home: LabHomeOption = None,
) -> None:
    root = _root(lab_home)
    lang = _lang(root)
    try:
        lab = _lab(root, lab_id, lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    ctx.call_on_close(_verrou(root, "reset").release)
    info(_("resetting", lab_id=texte_affichable(lab.id)))
    try:
        if lab.runtime.type.value in ("vm", "kvm", "incus"):
            _run_ansible_with_progress(
                lab.path / "cleanup.yaml",
                lambda cb: reset_lab(lab, target_name=target, on_event=cb),
            )
        else:
            reset_lab(lab, target_name=target)
        reset_hints(root, lab.id)
        success(_("lab_reset"))
    except Interrupted as exc:
        _interrompu(exc, f"dsoxlab reset {lab.id}")
    except RuntimeError as exc:
        error(str(exc))
        raise typer.Exit(2) from None


# ── clean ─────────────────────────────────────────────────────────────────────

# ── clean ─────────────────────────────────────────────────────────────────────

@app.command("clean", help=_("cmd_clean_help"))
def clean(
    ctx: typer.Context,
    lab_id: Annotated[str, typer.Argument(help=_("cmd_clean_arg"), autocompletion=_complete_lab_id)],
    target: Annotated[str | None, typer.Option("--target", "-t",
        help=_("opt_run_target"))] = None,
    lab_home: LabHomeOption = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help=_("opt_yes"))] = False,
) -> None:
    root = _root(lab_home)
    lang = _lang(root)
    try:
        lab = _lab(root, lab_id, lang)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    if not yes:
        typer.confirm(_("confirm_clean", lab_id=texte_affichable(lab.id)), abort=True)

    # Après la confirmation, jamais avant : tenir le verrou pendant qu'on
    # attend une réponse au clavier bloquerait l'autre terminal sur une
    # question que personne ne voit.
    ctx.call_on_close(_verrou(root, "clean").release)
    info(_("cleaning", lab_id=texte_affichable(lab.id)))
    try:
        if lab.runtime.type.value in ("vm", "kvm", "incus"):
            _run_ansible_with_progress(
                lab.path / "cleanup.yaml",
                lambda cb: clean_lab(lab, target_name=target, on_event=cb),
            )
        else:
            clean_lab(lab, target_name=target)
        _stop_services(lab, root)
        success(_("clean_done"))
    except Interrupted as exc:
        _interrompu(exc, f"dsoxlab clean {lab.id}")
    except RuntimeError as exc:
        error(str(exc))
        raise typer.Exit(2) from None


# ── validate-structure ────────────────────────────────────────────────────────
