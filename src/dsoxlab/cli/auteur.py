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
from pathlib import Path
from typing import Annotated, Any

import typer

from ..i18n import _
from ..reporting import (
    console,
    error,
    info,
    machine,
    print_structure_reports,
    success,
)
from ..services import (
    validate_all_metadata,
    validate_all_structure,
)
from ._commun import (
    LabHomeOption,
    _root,
)
from ._socle import app
from ._validation import _compter

logger = logging.getLogger(__name__)



@app.command("validate-structure", help=_("cmd_validate_help"))
def validate_structure_cmd(
    lab_home: LabHomeOption = None,
    check_urls: Annotated[bool, typer.Option(
        "--check-urls", help=_("opt_check_urls"),
    )] = False,
    as_json: Annotated[bool, typer.Option("--json", help=_("opt_json"))] = False,
) -> None:
    from ..discovery.repo import read_repo_metadata
    from ..discovery.scanner import discover_labs
    from ..validators.content import (
        ContentIssue,
        check_doc_url,
        validate_internal_links,
        validate_language_parity,
        validate_scoring,
        validate_solutions_encrypted,
        validate_targets,
    )
    from ..validators.contract import validate_schema_versions, validate_unknown_keys

    root = _root(lab_home)

    def _rendu(chemin: Path) -> Path:
        try:
            return chemin.relative_to(root)
        except ValueError:
            return chemin

    # Le document machine se construit au fil des contrôles, dans le même ordre
    # que l'affichage : une seule passe, deux rendus, et donc aucun risque que
    # l'un rapporte une anomalie que l'autre tait.
    documents: list[dict[str, Any]] = []

    def _rendre(entete: str, lignes: list[str]) -> None:
        """Affiche un groupe d'anomalies, sauf en mode machine."""
        if as_json or not lignes:
            return
        console.print(_(entete))
        for ligne in lignes:
            console.print(ligne)

    # D'ABORD, et à la source : un `schema_version` illisible ou trop récent
    # empêche le fichier d'être découvert, donc TOUS les contrôles suivants
    # l'ignoreraient — c'est le trou connu du validator, qui n'itère que sur ce
    # qui a déjà été chargé. Ce contrôle-ci relit les fichiers du disque.
    contract = validate_schema_versions(root)
    documents += [
        machine.issue_dict("contract", a.key, a.params, path=a.path)
        for a in contract.issues
    ]
    _rendre("contract_issues_header", [
        f"  [red]✘[/red] {_rendu(a.path)}: {_(a.key, **a.params)}"
        for a in contract.issues
    ])
    # Le meta.yml décrit tout le catalogue : illisible, il rend chaque
    # contrôle suivant douteux, et la découverte lèverait de toute façon.
    # Un lab isolé, lui, n'empêche pas de valider les 283 autres.
    if not contract.ok and contract.meta_is_unreadable:
        if as_json:
            # Même forme de document que la sortie complète : un appelant ne
            # doit pas avoir deux structures à gérer selon l'endroit où la
            # validation s'est arrêtée.
            machine.emit({
                "ok": False,
                "labs_checked": 0,
                "doc_urls_checked": False,
                "issues": documents,
                "counts": _compter(documents),
            })
            raise typer.Exit(1)
        error(_("labs_have_issues"))
        raise typer.Exit(1)

    # Ensuite, toujours à la source : les clés que le moteur n'ira jamais lire.
    # Le parseur les ignore et continuera de le faire — c'est une garantie de
    # la v1 — mais « toléré » n'est pas « voulu » : onze labs d'examen ont posé
    # un seuil de réussite que personne ne lisait, sans que rien ne le dise.
    unknown = validate_unknown_keys(root)
    documents += [
        machine.issue_dict("unknown_key", a.key, a.params, path=a.path)
        for a in unknown.issues
    ]
    _rendre("unknown_keys_header", [
        f"  [red]✘[/red] {_rendu(a.path)}: {_(a.key, **a.params)}"
        for a in unknown.issues
    ])

    structure_reports = validate_all_structure(root)
    metadata_reports = validate_all_metadata(root)

    documents += [
        machine.issue_dict("structure", i.key, i.params, lab=r.lab_id, path=i.path)
        for r in structure_reports for i in r.issues
    ]
    if not as_json:
        print_structure_reports(structure_reports)

    # Contrôles de contenu : locaux, donc jouables hors ligne et par défaut.
    # Un lien mort ou une solution en clair ne casse aucun test fonctionnel,
    # c'est bien pourquoi rien ne les attrapait.
    labs = discover_labs(root)
    # Les cibles vm se valident contre infra.hosts : un FQDN inconnu ne se
    # voyait qu'au run, sur la machine de l'apprenant, après provisionnement.
    try:
        repo_meta = read_repo_metadata(root)
        host_names = {h.name for h in repo_meta.infra.hosts} if repo_meta else set()
    except Exception:  # noqa: BLE001 - meta.yml illisible : les autres contrôles restent utiles
        host_names = set()

    content_issues: list[tuple[str, Path, ContentIssue]] = []
    for lab in labs:
        rapports = [
            validate_internal_links(lab),
            validate_scoring(lab),
            validate_language_parity(lab),
            validate_targets(lab, host_names),
        ]
        # « solution/<chemin du lab depuis labs/> » : convention respectée par
        # les dépôts qui tiennent leurs corrigés hors des labs. Absent = pas
        # de contrôle, ce n'est pas une faute.
        try:
            relatif = lab.path.relative_to(root / "labs")
        except ValueError:
            relatif = None
        if relatif is not None:
            rapports.append(
                validate_solutions_encrypted(lab, root / "solution" / relatif)
            )
        for rapport in rapports:
            for souci in rapport.issues:
                content_issues.append((lab.id, souci.path, souci))

    documents += [
        machine.issue_dict("content", s.key, s.params, lab=lab_id, path=chemin)
        for lab_id, chemin, s in content_issues
    ]
    _rendre("content_issues_header", [
        f"  [red]✘[/red] {lab_id} — {_rendu(chemin)}: {_(s.key, **s.params)}"
        for lab_id, chemin, s in content_issues
    ])

    url_issues: list[tuple[str, str, ContentIssue]] = []
    if check_urls:
        # Sur stdout : tue en mode machine, où un « ℹ » suffit à rendre le
        # document illisible.
        if not as_json:
            info(_("checking_doc_urls", count=len(labs)))
        for lab in labs:
            injoignable = check_doc_url(lab)
            if injoignable is not None:
                url_issues.append((lab.id, lab.doc_url, injoignable))
        documents += [
            # L'URL entre dans les paramètres : c'est le fait que l'appelant
            # veut, et il n'a pas à relire le catalogue pour l'obtenir.
            machine.issue_dict(
                "doc_url", r.key, {**r.params, "url": url}, lab=lab_id, path=r.path,
            )
            for lab_id, url, r in url_issues
        ]
        _rendre("doc_url_issues_header", [
            f"  [red]✘[/red] {lab_id} — {url} — {_(r.key, **r.params)}"
            for lab_id, url, r in url_issues
        ])

    issues = [r for r in metadata_reports if not r.ok]
    documents += [
        machine.issue_dict("metadata", i.key, i.params, lab=r.lab_id, field=i.field)
        for r in issues for i in r.issues
    ]
    _rendre("metadata_issues_header", [
        f"  [red]✘[/red] {r.lab_id} — {i.field}: {_(i.key, **i.params)}"
        for r in issues for i in r.issues
    ])

    all_ok = (
        contract.ok
        and unknown.ok
        and all(r.ok for r in structure_reports)
        and not issues
        and not content_issues
        and not url_issues
    )
    if as_json:
        machine.emit({
            "ok": all_ok,
            "labs_checked": len(labs),
            # `--check-urls` est le seul contrôle réseau, et le seul qui ne
            # tourne pas par défaut : sans ce champ, un appelant ne peut pas
            # distinguer « aucune URL morte » de « les URL n'ont pas été
            # regardées ».
            "doc_urls_checked": check_urls,
            "issues": documents,
            "counts": _compter(documents),
        })
        # Le verdict et le code de retour sont ceux du mode terminal : seule la
        # forme de la sortie change.
        if not all_ok:
            raise typer.Exit(1)
        return
    if all_ok:
        success(_("all_labs_valid"))
    else:
        error(_("labs_have_issues"))
        raise typer.Exit(1)


# ── doctor ────────────────────────────────────────────────────────────────────
