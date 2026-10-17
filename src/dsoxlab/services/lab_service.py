"""Orchestration métier : actions sur les labs."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..discovery.repo import find_meta_yml
from ..discovery.scanner import discover_labs
from ..i18n import _
from ..interrupt import Interrupted, Stage
from ..models.hint import HintFile
from ..models.lab import LabDefinition
from ..runtimes.base import EventCallback, SessionSpec
from ..runtimes.manager import RuntimeManager
from ..sessions.store import hints_cost_total, hints_used_count, record_result
from ..utils.shell import CommandError, run_command
from ..validators.metadata import MetadataReport, validate_metadata
from ..validators.structure import StructureReport, validate_structure

_manager = RuntimeManager()


@dataclass
class CheckResult:
    ok: bool
    output: str
    passed: int
    total: int
    #: Les tests collectés qui n'ont PAS été exécutés. Sans ce compte, une
    #: suite entièrement skippée se confondait avec une suite entièrement
    #: ratée : `total` les comptait, donc `a_mesure()` répondait oui.
    skipped: int = 0


@dataclass(frozen=True)
class ScoreResult:
    """Un lab validé et noté : ce que les tests ont donné, et ce que ça vaut.

    ``hints_cost`` est ce que les indices demandés ont retiré du barème, et
    ``max_score`` reste le barème PLEIN du lab (pas le barème amputé) : on veut
    pouvoir afficher « 70/100, dont 20 de pénalité d'indices » plutôt qu'un
    « 70/80 » qui masquerait le coût des indices.
    """

    check: CheckResult
    score: int
    max_score: int
    hints_used: int
    hints_cost: int

    enregistre: bool = True
    """L'exécution a-t-elle été inscrite dans l'historique ?

    Faux quand rien n'a pu être mesuré : voir ``evaluate_lab``. L'appelant doit
    alors dire qu'aucun test n'a été collecté, et surtout ne pas présenter le
    0 comme une note.
    """


def _parse_counts(output: str) -> tuple[int, int, int]:
    """Extrait (passed, total, skipped) depuis la sortie de pytest.

    On lit la ligne de RÉSUMÉ que pytest produit lui-même ("3 failed, 1 passed
    in 0.02s") : c'est la seule source fiable.

    Compter les occurrences de " PASSED"/" FAILED"/" ERROR" dans la sortie
    brute — ce que faisait cette fonction — est faux dès qu'un lab manipule ces
    mots : les messages d'assertion les affichent. Un lab qui filtre des lignes
    « ERROR » (l1-get-help, l1-grep-regex, l1-redirections-pipes…) gonflait son
    total, et le score de l'apprenant s'en trouvait FAUSSÉ : 1/5 au lieu de
    1/4. Bug vécu, trouvé en jouant les labs.
    """
    # La dernière ligne qui porte un compte est le résumé final : les lignes
    # de verdict par test ("… PASSED [ 25%]") n'ont pas ce format.
    resumes = [
        ligne
        for ligne in output.splitlines()
        if re.search(r"\b\d+ (passed|failed|error|skipped)", ligne)
    ]
    resume = resumes[-1] if resumes else ""

    def _compte(mot: str) -> int:
        m = re.search(rf"(\d+) {mot}", resume)
        return int(m.group(1)) if m else 0

    passed = _compte("passed")
    skipped = _compte("skipped")
    total = passed + _compte("failed") + _compte("error") + skipped

    if total == 0:
        # Aucun résumé exploitable (pytest a planté avant) : on retombe sur le
        # comptage des verdicts, ancré sur le format "<nodeid> VERDICT" pour ne
        # pas ramasser les mots présents dans les messages.
        verdicts = re.findall(r"::\S+\s+(PASSED|FAILED|ERROR|SKIPPED)\b", output)
        passed = verdicts.count("PASSED")
        skipped = verdicts.count("SKIPPED")
        total = len(verdicts)
    return passed, total, skipped


def _resultat(output: str, *, ok: bool) -> CheckResult:
    """Un CheckResult lu dans une sortie de pytest, comptes compris.

    Les deux chemins d'exécution de `check_lab` en construisent un, et ils
    répétaient le même trio. Un seul endroit compte, donc un seul endroit à
    corriger le jour où pytest change le format de son résumé.
    """
    passed, total, skipped = _parse_counts(output)
    return CheckResult(
        ok=ok, output=output, passed=passed, total=total, skipped=skipped,
    )


@dataclass(frozen=True)
class EchecDeTest:
    """Un test en échec, tel qu'on peut le dire à un apprenant.

    ``message`` est l'assertion que l'AUTEUR DU LAB a écrite, et c'est la pièce
    la plus précieuse : les labs de ce contrat y mettent le geste de réparation
    (« Crée le fichier, par exemple : mkdir -p reponses && echo … »). Il vaut
    ``None`` quand l'échec n'en portait pas, ce qui est le cas d'une erreur de
    collecte.
    """

    nom: str
    message: str | None = None

    @property
    def phrase(self) -> str:
        """Le nom du test, lu comme une phrase.

        Les labs nomment leurs tests en phrases (``test_le_mot_du_cours``)
        précisément pour qu'ils se lisent : il n'y a qu'à retirer le préfixe et
        les tirets bas.
        """
        return self.nom.removeprefix("test_").replace("_", " ")


#: Début d'une section de la zone FAILURES : ``____ test_nom ____``.
_SECTION_ECHEC = re.compile(r"^_{3,}\s*(?:[\w\[\]./-]+::)?(\w+)\s*_{3,}$")

#: Première ligne du message d'assertion dans cette section.
_MESSAGE_ECHEC = re.compile(r"^E\s{2,}(?:\w*(?:Error|Exception|Failed)\s*:\s*)?(.+)$")


def echecs_de_tests(output: str) -> list[EchecDeTest]:
    """Les tests que pytest a déclarés en échec, avec leur message, sans trace.

    Pourquoi cette fonction existe
    ------------------------------

    ``check`` déversait ``result.output`` en entier dès qu'un test échouait.
    Mesuré sur le lab de démonstration et ses trois tests rouges : **26 lignes**
    de traceback avant le panneau de résultat, dont deux chemins absolus repliés
    sur trois lignes chacun, un ``assert False``, un
    ``+ where exists = PosixPath(...).exists`` et deux séparateurs de section.

    Mais **tout** n'était pas du bruit, et c'est le piège : au milieu de ces 26
    lignes se trouvait la phrase que l'auteur du lab avait écrite dans son
    ``assert``, avec le geste de réparation. La première version de cette
    fonction ne rendait que les noms des tests, et jetait donc l'information la
    plus utile de l'écran. C'est une capture avant/après qui l'a montré, pas une
    mesure : le compteur de lignes de trace, lui, était satisfait.

    Deux formats de nodeid sont lus, parce que pytest produit l'un ou l'autre
    selon la largeur du terminal et la présence de ``-q`` :

    - la section « short test summary info » : ``FAILED chemin::test_nom`` ;
    - les verdicts par test : ``chemin::test_nom FAILED``.

    Et le message est repris de la zone ``FAILURES``, qui est la seule à le
    porter. Un test sans section ``FAILURES`` (erreur de collecte) rend donc un
    ``EchecDeTest`` sans message, et l'appelant n'a qu'un nom à montrer.

    Rend une liste vide quand rien n'est reconnaissable, ce qui est le cas si
    pytest a planté avant de collecter : l'appelant doit alors montrer la sortie
    brute, puisqu'elle est tout ce qui existe.
    """
    messages = _messages_par_test(output)
    noms: list[str] = []
    for ligne in output.splitlines():
        depouillee = ligne.strip()
        if depouillee.startswith(("FAILED", "ERROR")) or re.search(
            r"::\S+\s+(FAILED|ERROR)\b", depouillee
        ):
            # Le nodeid peut être replié par pytest sur un terminal étroit :
            # on cherche le nom du test, pas la ligne entière.
            trouve = re.search(r"::(\w+)", depouillee)
            if trouve and trouve.group(1) not in noms:
                noms.append(trouve.group(1))
    return [EchecDeTest(nom=nom, message=messages.get(nom)) for nom in noms]


def _sections_dechec(output: str) -> dict[str, list[str]]:
    """La zone ``FAILURES`` découpée par test : nom du test, lignes brutes.

    Séparé de l'extraction du message pour une raison mesurable : la version
    qui faisait les deux dans une seule boucle atteignait une complexité
    cognitive de 23, pour cinq ``continue`` et un état à trois variables. Le
    garde-fou du dépôt l'a refusée, et il avait raison.
    """
    sections: dict[str, list[str]] = {}
    courant: str | None = None
    for ligne in output.splitlines():
        entete = _SECTION_ECHEC.match(ligne.strip())
        if entete:
            courant = entete.group(1)
            sections[courant] = []
        elif courant is not None:
            sections[courant].append(ligne)
    return sections


def _message_de_section(lignes: list[str]) -> str | None:
    """Ce que l'auteur du lab a écrit dans son ``assert``, et rien d'autre.

    Seules les lignes préfixées par ``E`` portent le message. La lecture
    s'arrête au premier ``assert`` : ce qui suit est la reconstruction que
    pytest fait de l'expression (``+ where False = exists()``), utile à un
    développeur et illisible pour qui apprend l'administration d'un système.
    """
    retenues: list[str] = []
    for ligne in lignes:
        if not ligne.startswith("E"):
            continue
        corps = _MESSAGE_ECHEC.match(ligne)
        if corps is None:
            continue
        texte = corps.group(1).strip()
        if texte.startswith(("assert", "+ where", "+  where")):
            break
        retenues.append(texte)
    return "\n".join(retenues).strip() or None


def _messages_par_test(output: str) -> dict[str, str]:
    """Le message d'assertion de chaque test en échec, s'il en a un."""
    trouves = {
        nom: _message_de_section(lignes)
        for nom, lignes in _sections_dechec(output).items()
    }
    return {nom: message for nom, message in trouves.items() if message}


def compute_score(passed: int, total: int, max_score: int, hints_cost: int) -> int:
    """Note un lab : proportion de tests réussis, appliquée au barème amputé des indices.

    Le coût des indices est retiré du barème AVANT la règle de trois, et non du
    score final : demander de l'aide plafonne ce qu'on peut obtenir, plutôt que
    de pénaliser après coup quelqu'un qui a tout réussi. Le barème ne descend
    jamais sous zéro, donc un apprenant qui a consommé tous les indices obtient
    0, jamais un score négatif.

    ``total`` à zéro (pytest n'a pas pu collecter) rend 0 : on ne devine pas un
    score depuis une exécution qui n'a rien mesuré.
    """
    if total <= 0:
        return 0
    base = max(0, max_score - hints_cost)
    return round((passed / total) * base)


def a_mesure(result: CheckResult) -> bool:
    """L'exécution a-t-elle mesuré quelque chose ?

    Un seul endroit décide, parce que deux lecteurs en dépendent :
    ``evaluate_lab`` pour savoir s'il enregistre, et la sortie machine pour
    dire à un programme si la note vaut quelque chose. Dupliquer la règle la
    ferait diverger le jour où elle change.
    """
    # Mesurer, c'est EXÉCUTER. Cinq tests collectés puis skippés donnent un
    # `total` de cinq et n'ont rien mesuré : l'ancien `total > 0` répondait
    # oui, et le moteur inscrivait un 0 dans l'historique d'un lab que
    # personne n'avait joué, sous une ligne annonçant le succès.
    return result.total > result.skipped


def evaluate_lab(root: Path, lab: LabDefinition, result: CheckResult) -> ScoreResult:
    """Note un ``CheckResult`` et l'enregistre dans l'historique de l'apprenant.

    Cette fonction était le cœur de ``_run_check`` dans ``cli.py``, où elle
    était entrelacée avec des ``typer.Exit`` et des appels d'affichage : toute
    autre interface (TUI, export) aurait dû redupliquer la formule de score.
    Elle n'imprime rien et ne traduit rien ; l'appelant présente le résultat.
    """
    hint_file = HintFile.load(lab.path / "challenge")
    max_score = hint_file.points
    hints_cost = hints_cost_total(root, lab.id)
    used = hints_used_count(root, lab.id)
    score = compute_score(result.passed, result.total, max_score, hints_cost)

    if not lab.is_exercise:
        # Un lab `validation` défend un guide publié : ses tests mesurent des
        # FAITS, pas une personne. Inscrire une note reviendrait à noter le
        # guide, et à faire entrer dans la progression d'un apprenant une
        # avancée qui n'est pas la sienne. Les tests tournent — c'est tout
        # l'objet du lab — et rien n'en sort.
        return ScoreResult(
            check=result,
            score=score,
            max_score=max_score,
            hints_used=used,
            hints_cost=hints_cost,
            enregistre=False,
        )

    if not a_mesure(result):
        # Rien n'a été mesuré : pytest n'a pas pu collecter, faute d'un
        # conftest qui lève, d'une machine injoignable ou d'une dépendance
        # absente. Inscrire ce 0 le rendrait indiscernable d'un lab tenté et
        # raté, et la suite en dépend : `status` afficherait « validé », et
        # `next` sauterait un lab que l'apprenant n'a jamais pu jouer.
        #
        # `compute_score` refusait déjà de deviner un score ; ce refus n'allait
        # pas jusqu'à la base.
        return ScoreResult(
            check=result,
            score=score,
            max_score=max_score,
            hints_used=used,
            hints_cost=hints_cost,
            enregistre=False,
        )

    record_result(
        root,
        lab_id=lab.id,
        # `or ""` : la colonne `section` est NOT NULL, et un lab qu'aucune
        # règle n'a rattaché n'en a pas. Vide se filtre comme absent ; None
        # ferait lever l'insertion.
        section=lab.section or "",
        score=score,
        max_score=max_score,
        passed_tests=result.passed,
        total_tests=result.total,
        hints_used=used,
    )
    return ScoreResult(
        check=result,
        score=score,
        max_score=max_score,
        hints_used=used,
        hints_cost=hints_cost,
    )


def get_all_labs(root: Path, lang: str = "en") -> list[LabDefinition]:
    return discover_labs(root, lang=lang)


def find_lab(labs: list[LabDefinition], lab_id: str) -> LabDefinition:
    """Le lab d'identifiant ``lab_id`` dans un catalogue déjà balayé.

    Extrait de :func:`get_lab` pour que la CLI, qui a besoin du balayage
    complet (elle y lit aussi les fichiers écartés), n'ait pas à en refaire un
    second ni à recopier le message d'erreur.
    """
    for lab in labs:
        if lab.id == lab_id:
            return lab
    raise ValueError(_("err_lab_not_found", lab_id=lab_id))


def get_lab(root: Path, lab_id: str, lang: str = "en") -> LabDefinition:
    return find_lab(discover_labs(root, lang=lang), lab_id)


def run_lab(
    lab: LabDefinition,
    target_name: str | None = None,
    *,
    on_event: EventCallback | None = None,
    root: Path | None = None,
) -> None:
    """Prépare et démarre l'environnement du lab (setup uniquement).

    ``root`` sert à retenir le point de départ du travail, ce qui permet à
    ``dsoxlab status`` de distinguer plus tard un lab *prêt* d'un lab *en
    cours*. Il est optionnel pour ne casser aucun appelant, et l'enregistrement
    n'a lieu qu'**après** un démarrage réussi : marquer un départ qui n'a pas eu
    lieu ferait dire « en cours » d'un lab que rien n'a préparé.
    """
    runtime = _manager.get(lab)
    runtime.start(lab, target_name, on_event=on_event)
    if root is not None:
        from .lab_state import enregistrer_depart

        enregistrer_depart(root, lab)


def open_lab_session(lab: LabDefinition) -> None:
    """Ouvre une session interactive dans le répertoire du lab (bloquant pour shell)."""
    runtime = _manager.get(lab)
    runtime.open_session(lab)


def lab_session_spec(lab: LabDefinition) -> SessionSpec | None:
    """Décrit la session interactive du lab sans l'ouvrir.

    Permet d'afficher la commande à taper plutôt que de l'exécuter, et laisse
    une interface qui ne peut pas céder son TTY choisir son mode d'attachement.
    """
    runtime = _manager.get(lab)
    return runtime.session_spec(lab)


def stop_lab(lab: LabDefinition, target_name: str | None = None) -> None:
    runtime = _manager.get(lab)
    runtime.stop(lab, target_name)


def reset_lab(
    lab: LabDefinition,
    target_name: str | None = None,
    *,
    on_event: EventCallback | None = None,
) -> None:
    """Remet le lab à l'état initial (clean + start)."""
    runtime = _manager.get(lab)
    runtime.reset(lab, target_name, on_event=on_event)


def clean_lab(
    lab: LabDefinition,
    target_name: str | None = None,
    *,
    on_event: EventCallback | None = None,
) -> None:
    """Supprime toutes les ressources créées par le lab."""
    runtime = _manager.get(lab)
    runtime.clean(lab, target_name, on_event=on_event)


def lab_status(lab: LabDefinition, target_name: str | None = None) -> str:
    runtime = _manager.get(lab)
    return runtime.status(lab, target_name)


def resolve_pytest_cmd(repo_root: Path) -> list[str] | None:
    """Trouve la bonne façon de lancer pytest avec testinfra disponible.

    Publique parce que ``doctor`` doit diagnostiquer **exactement** ce que
    ``check`` exécutera. Tant que le diagnostic cherchait un binaire dans le
    PATH de son côté, il annonçait un pytest introuvable là où ``check``
    tournait très bien via l'environnement de l'outil.

    Ordre de résolution :

    1. ``sys.executable -m pytest`` (l'env du tool dsoxlab — pytest +
       pytest-testinfra sont déclarés en dependencies de dsoxlab donc
       installés par ``uv tool install dsoxlab``). C'est le mode
       cible : l'apprenant n'a rien à installer localement, dsoxlab
       embarque tout. Le subprocess hérite du PYTHONPATH du tool dsoxlab
       et peut importer ``dsoxlab.*`` depuis le conftest.py du repo de labs.
    2. ``<repo_root>/.venv/bin/pytest`` (fallback venv local).
    3. ``uv run pytest`` dans le repo (uv crée/sync à la volée).
    4. ``pytest`` système.

    Retourne ``None`` si vraiment aucun pytest disponible (rare —
    nécessite que dsoxlab ait été mal installé).
    """
    # Test rapide : dsoxlab tool a bien pytest dans son env ?
    try:
        import pytest as _pytest_check  # noqa: F401
        return [sys.executable, "-m", "pytest"]
    except ImportError:
        pass  # dsoxlab installé sans pytest (cas rare, fallback ci-dessous)

    venv_pytest = repo_root / ".venv" / "bin" / "pytest"
    if venv_pytest.is_file():
        return [str(venv_pytest)]

    uv_path = shutil.which("uv")
    if uv_path:
        return [uv_path, "run", "--quiet", "pytest"]

    pytest_path = shutil.which("pytest")
    if pytest_path:
        return [pytest_path]

    return None


_PYTEST_VERDICT_RE = re.compile(
    r"^(?P<nodeid>\S+::\S+)\s+(?P<verdict>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)"
)


def _collect_test_count(
    pytest_cmd: list[str],
    tests_dir: Path,
    repo_root: Path,
    env: dict[str, str],
) -> int:
    """Compte les tests via ``pytest --collect-only -q``.

    Retourne 0 si la collecte échoue (pytest streame quand même les
    verdicts, donc on peut afficher une barre indéterminée).
    """
    try:
        result = run_command(
            [*pytest_cmd, "--collect-only", "-q", str(tests_dir)],
            cwd=repo_root,
            timeout=60,
            check=False,
            env=env,
        )
    except CommandError:
        return 0
    if not result.ok:
        return 0
    # Format pytest -q : une ligne par test, puis ligne vide, puis "N tests collected".
    m = re.search(r"(\d+)\s+tests?\s+collected", result.stdout)
    if m:
        return int(m.group(1))
    # Fallback : compter les lignes nodeid (contenant "::").
    return sum(1 for line in result.stdout.splitlines() if "::" in line)


def check_lab(
    lab: LabDefinition,
    *,
    target: str | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> CheckResult:
    """Lance les tests pytest du lab et retourne un CheckResult détaillé.

    ``target`` sélectionne la target du lab (``runtime.targets[].name``) sur
    laquelle les tests doivent porter. Son FQDN est exporté aux tests via
    ``DSOXLAB_TARGET_HOST`` : c'est ce qui permet à un lab multi-distrib
    d'être réellement validé sur la distrib choisie, au lieu que les tests
    codent un hôte en dur. Si ``target`` est None, la target ``default`` du
    lab est utilisée.

    Si ``on_event`` est fourni, les évènements suivants sont émis pour
    afficher une progress bar côté CLI :

    - ``{"type": "collected", "total": int}`` une fois après collecte.
    - ``{"type": "verdict", "nodeid": str, "verdict": "PASSED"|"FAILED"|...}``
      pour chaque test terminé.
    - ``{"type": "log", "line": str}`` pour les autres lignes (header,
      tracebacks, summary). Le caller décide de les afficher ou non.
    """
    tests_dir = lab.path / "challenge" / "tests"
    if not tests_dir.is_dir():
        return CheckResult(
            ok=False,
            output="Répertoire challenge/tests/ introuvable",
            passed=0, total=0,
        )

    meta_path = find_meta_yml(lab.path)
    repo_root = meta_path.parent if meta_path else lab.path.parent
    pytest_cmd = resolve_pytest_cmd(repo_root)
    if pytest_cmd is None:
        return CheckResult(
            ok=False,
            output=(
                "pytest introuvable. Réinstalle dsoxlab :\n"
                "  uv tool install --force dsoxlab\n"
                "(pytest+pytest-testinfra sont embarqués dans le tool)."
            ),
            passed=0, total=0,
        )

    # Désactive la fixture _apply_lab_state (rejouerait solution.yaml
    # côté formateur, écrasant le travail manuel de l'apprenant).
    env = os.environ.copy()
    env.setdefault("LAB_NO_REPLAY", "1")
    # Le répertoire d'état du lab (#298) : la préparation y range ce que les
    # tests doivent connaître sans l'exposer dans le workdir.
    from .lab_state import repertoire_etat

    env["LAB_STATE_DIR"] = str(repertoire_etat(repo_root, lab.id))

    # Expose aux tests le FQDN de la target choisie. Sans ça, un lab
    # multi-distrib ne peut que coder son hôte en dur : la target Ubuntu
    # serait déclarée mais jamais testée — le contrat mentirait.
    resolved = lab.runtime.target(target)
    if target and resolved is None:
        declared = ", ".join(t.name for t in lab.runtime.targets) or "aucune"
        return CheckResult(
            ok=False,
            output=(
                f"Target '{target}' inconnue pour le lab {lab.id}.\n"
                f"Targets déclarées : {declared}."
            ),
            passed=0, total=0,
        )
    if resolved is not None and resolved.host:
        env["DSOXLAB_TARGET_HOST"] = resolved.host

    if on_event is None:
        # Mode legacy : capture en bloc, pas de streaming.
        try:
            result = run_command(
                [*pytest_cmd, "-v", str(tests_dir)],
                cwd=repo_root,
                timeout=300,
                check=False,
                env=env,
            )
            output = result.stdout + result.stderr
            return _resultat(output, ok=result.ok)
        except CommandError as exc:
            return CheckResult(ok=False, output=str(exc), passed=0, total=0)

    # Mode streaming : pré-collecte pour le total, puis Popen ligne par ligne.
    total_collected = _collect_test_count(pytest_cmd, tests_dir, repo_root, env)
    on_event({"type": "collected", "total": total_collected})

    output_lines: list[str] = []
    try:
        proc = subprocess.Popen(
            [*pytest_cmd, "-v", "--no-header", "--tb=short", str(tests_dir)],
            cwd=repo_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        return CheckResult(ok=False, output=str(exc), passed=0, total=0)

    assert proc.stdout is not None
    try:
        for brute in proc.stdout:
            line = brute.rstrip("\n")
            output_lines.append(line)
            m = _PYTEST_VERDICT_RE.match(line)
            if m:
                on_event({
                    "type": "verdict",
                    "nodeid": m.group("nodeid"),
                    "verdict": m.group("verdict"),
                })
            else:
                on_event({"type": "log", "line": line})
    except KeyboardInterrupt:
        # Sans ce nettoyage, pytest survivait à la commande qui l'avait lancé :
        # il continue de piloter la VM du lab pendant que l'apprenant croit
        # avoir tout arrêté, et le processus reste zombie jusqu'à la sortie.
        proc.kill()
        with suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)
        # Rien n'est enregistré : une validation interrompue ne vaut pas un
        # 0/100 dans l'historique de l'apprenant.
        raise Interrupted(Stage.TESTS) from None

    rc = proc.wait(timeout=300)
    output = "\n".join(output_lines)
    return _resultat(output, ok=(rc == 0))


def validate_all_structure(root: Path) -> list[StructureReport]:
    labs = discover_labs(root)
    return [validate_structure(lab) for lab in labs]


def validate_all_metadata(root: Path) -> list[MetadataReport]:
    labs = discover_labs(root)
    return [validate_metadata(lab) for lab in labs]
