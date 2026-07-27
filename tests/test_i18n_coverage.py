"""Guard: no user-facing string may be hardcoded in `cli.py`.

The rule already existed in prose ("every displayed text goes through
`_()`"), and prose did not hold: option helps, progress-bar labels and a
handful of error messages had drifted back into literals. Some were French,
so an English run showed French; others were English, so a French run showed
English. Both are the same defect.

Rather than re-audit by hand, this module parses `cli.py` and asserts the
invariant. It deliberately checks only what can be decided without judgement:

* `help=` and `description=` keywords must be `_()` calls, no exception;
* a bare string literal handed to `error/info/warn/success` is forbidden;
* an f-string handed to those is allowed **only** if its literal parts carry
  no word, i.e. it is pure layout around already-translated values
  (`f"  ✔ {fqdn} ({ip})"` passes, `f"Host inconnu : {fqdn}"` does not).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import dsoxlab

CLI = Path(dsoxlab.__file__).parent / "cli.py"

#: Les helpers d'affichage de `reporting.console`. Leur premier argument est
#: le message vu par l'apprenant.
MESSAGE_FUNCS = {"error", "info", "warn", "success"}

#: Balises Rich (`[bold]`, `[/green]`…) : de la mise en forme, pas du texte.
_RICH_TAG = re.compile(r"\[/?[a-z0-9 #]+\]", re.I)

#: « Mot » au sens de ce test : trois lettres consécutives ou plus. En dessous,
#: on est dans les symboles, la ponctuation ou les unités, pas dans la phrase.
_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)


@pytest.fixture(scope="module")
def tree() -> ast.Module:
    return ast.parse(CLI.read_text(encoding="utf-8"), filename=str(CLI))


def _is_i18n_call(node: ast.AST) -> bool:
    """Le nœud est-il un appel `_("clé", …)` ?"""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_"
    )


def _literal_words(node: ast.JoinedStr) -> list[str]:
    """Les mots portés par les parties littérales d'une f-string."""
    mots: list[str] = []
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            mots += _WORD.findall(_RICH_TAG.sub("", part.value))
    return mots


def test_option_help_and_progress_labels_go_through_i18n(tree: ast.Module) -> None:
    """`help=` et `description=` sont affichés tels quels : jamais de littéral."""
    coupables: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg not in {"help", "description"}:
                continue
            if isinstance(kw.value, (ast.Constant, ast.JoinedStr)) and not _is_i18n_call(
                kw.value
            ):
                coupables.append(f"cli.py:{kw.value.lineno} — {kw.arg}=")

    assert not coupables, (
        "Ces libellés s'afficheraient dans une seule langue :\n  "
        + "\n  ".join(coupables)
    )


def test_messages_are_translated_or_pure_layout(tree: ast.Module) -> None:
    """Aucun `error/info/warn/success` ne porte de phrase en dur."""
    coupables: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in MESSAGE_FUNCS or not node.args:
            continue

        premier = node.args[0]
        if _is_i18n_call(premier):
            continue
        if isinstance(premier, ast.Constant) and isinstance(premier.value, str):
            coupables.append(f"cli.py:{premier.lineno} — {premier.value[:50]!r}")
        elif isinstance(premier, ast.JoinedStr):
            mots = _literal_words(premier)
            if mots:
                coupables.append(f"cli.py:{premier.lineno} — mots en dur : {mots}")

    assert not coupables, (
        "Ces messages ne suivraient pas DSOXLAB_LANG :\n  " + "\n  ".join(coupables)
    )


def test_the_guard_would_actually_catch_a_regression() -> None:
    """Un test qui ne peut pas échouer ne prouve rien : on le fait échouer.

    Sans ce contrôle, une heuristique trop laxiste (ou un `_WORD` mal réglé)
    laisserait les deux tests ci-dessus passer sur n'importe quel code.
    """
    fautif = ast.parse('error("Host inconnu")\ninfo(f"Cible : {x}")\n')
    trouves = 0
    for node in ast.walk(fautif):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in MESSAGE_FUNCS or not node.args:
            continue
        premier = node.args[0]
        if isinstance(premier, ast.Constant):
            trouves += 1
        elif isinstance(premier, ast.JoinedStr) and _literal_words(premier):
            trouves += 1

    assert trouves == 2, "le garde-fou ne détecte plus les chaînes en dur"


def test_pure_layout_is_not_flagged() -> None:
    """Et il ne doit pas crier sur de la mise en forme sans texte."""
    layout = ast.parse('success(f"  ✔ {fqdn} ({ip})")\ninfo(f"[bold]{a}[/bold] → {b}")\n')
    for node in ast.walk(layout):
        if isinstance(node, ast.JoinedStr):
            assert not _literal_words(node)
