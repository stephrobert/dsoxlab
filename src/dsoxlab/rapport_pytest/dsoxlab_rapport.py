"""Plugin pytest embarqué : écrit un rapport structuré, une ligne JSON par phase.

Module AUTONOME : bibliothèque standard et pytest seulement, aucun import de
``dsoxlab``. Il est chargé par ``-p dsoxlab_rapport`` dans un sous-processus dont
``PYTHONPATH`` porte ce répertoire en tête, ce qui couvre les quatre façons de
lancer pytest que ``resolve_pytest_cmd`` sait produire.

Il est inerte sans ``DSOXLAB_RAPPORT`` : même chargé par erreur, il n'écrit rien.
Il ne déclare ni option, ni marqueur, et n'altère ni les verdicts ni le code de
sortie, pour ne jamais entrer en conflit avec le ``conftest.py`` d'un catalogue
(``--strict-markers``, ``--import-mode=importlib``...). Toute erreur interne est
avalée : un rapport manquant est un cas prévu côté lecteur, un pytest cassé par
son propre plugin ne l'est pas.

Format (v1), une ligne JSON par évènement :

- ``{"t": "debut", "v": 1}`` en première ligne ;
- ``{"t": "phase", "nodeid", "phase", "issue", "origine", "message"}`` ;
- ``{"t": "fin"}`` à la fermeture de la session. Son absence signale un pytest
  interrompu : le lecteur tient alors le rapport pour inconnu.

``issue`` vaut ``passed``, ``failed`` ou ``skipped`` (``xfail`` compte comme
``skipped``). ``origine`` vaut ``author`` quand l'exception est une
``AssertionError`` portant un message écrit par l'auteur, ou un ``pytest.fail``
(le message est alors repris, borné), et ``technical`` sinon. Le texte d'une
exception technique n'est JAMAIS écrit : il n'est pas destiné à l'affichage.
"""

from __future__ import annotations

import json
import os
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

_VARIABLE = "DSOXLAB_RAPPORT"
_MESSAGE_MAX = 1000
_MARQUE_ASSERT = "\nassert "


def _ecrire(entree: dict[str, Any]) -> None:
    chemin = os.environ.get(_VARIABLE)
    if not chemin:
        return
    with suppress(OSError, ValueError), Path(chemin).open("a", encoding="utf-8") as fichier:
        fichier.write(json.dumps(entree, ensure_ascii=False) + "\n")


def _message_auteur(excinfo: Any) -> tuple[str, str | None]:
    """L'origine du message d'un échec, et le message de l'auteur s'il existe.

    La réécriture d'assertions de pytest rend ``"<message>\\nassert <expr>..."``
    pour ``assert cond, "<message>"``. On coupe donc avant le DERNIER
    ``\\nassert``. Une assertion nue (``assert x == 1``) rend ``"assert x == 1"``
    : rien n'a été écrit pour l'apprenant, l'origine est ``technical``.
    """
    with suppress(Exception):  # un plugin ne casse jamais pytest
        valeur = excinfo.value
        if isinstance(valeur, pytest.fail.Exception):
            texte = str(valeur).strip()
            return ("author", texte[:_MESSAGE_MAX]) if texte else ("author", None)
        if isinstance(valeur, AssertionError):
            texte = str(valeur)
            position = texte.rfind(_MARQUE_ASSERT)
            if position >= 0:
                # La réécriture indente de deux espaces chaque ligne de
                # continuation du message (mesuré sur pytest 9.1.1) : on les retire.
                texte = texte[:position].replace("\n  ", "\n")
            elif texte.startswith("assert "):
                texte = ""
            texte = texte.strip()
            if texte:
                return "author", texte[:_MESSAGE_MAX]
    return "technical", None


@pytest.hookimpl
def pytest_sessionstart(session: Any) -> None:
    _ecrire({"t": "debut", "v": 1})


@pytest.hookimpl
def pytest_sessionfinish(session: Any, exitstatus: Any) -> None:
    _ecrire({"t": "fin"})


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Any:
    outcome = yield
    with suppress(Exception):
        rapport = outcome.get_result()
        if rapport.passed:
            issue = "passed"
        elif rapport.failed:
            issue = "failed"
        else:
            issue = "skipped"
        origine: str | None = None
        message: str | None = None
        if issue == "failed" and call.excinfo is not None:
            origine, message = _message_auteur(call.excinfo)
        _ecrire({
            "t": "phase",
            "nodeid": rapport.nodeid,
            "phase": rapport.when,
            "issue": issue,
            "origine": origine,
            "message": message,
        })


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector: Any) -> Any:
    outcome = yield
    with suppress(Exception):
        rapport = outcome.get_result()
        if rapport.failed:
            _ecrire({
                "t": "phase",
                "nodeid": rapport.nodeid,
                "phase": "collect",
                "issue": "failed",
                "origine": "technical",
                "message": None,
            })
