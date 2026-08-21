"""Interruption d'une opération longue : un vocabulaire et une politique.

Un ``provision`` dure des minutes. L'apprenant qui perd patience fait Ctrl-C, et
c'est exactement le moment où l'état peut diverger : une VM à moitié créée, un
playbook arrêté au milieu d'un rôle, un conteneur démarré mais non initialisé.

Ce que l'outil faisait avant, et pourquoi c'était le même défaut partout
=======================================================================

Rien n'attrapait ``KeyboardInterrupt`` en dehors du pager. Typer, tout en bas,
en fait un ``Exit(130)`` (``typer/core.py``) : le code de retour était donc déjà
juste, mais l'écran ne disait **rien**. L'apprenant retrouvait son invite sans
savoir ce qui avait été interrompu, ce qui restait debout, ni quelle commande
reprend. C'est la famille de défauts déjà soldée ailleurs dans ce dépôt : un
état à moitié écrit qui ne se signale pas.

Sur le chemin Ansible, le code mentait en plus du silence. Mesuré : un Ctrl-C
pendant un playbook ne lève aucun ``KeyboardInterrupt``, ansible-runner annule
et rend ``rc=254, status='canceled'``, que dsoxlab traduisait en « setup.yaml a
échoué » avec le code de sortie d'un échec. Une interruption s'y présentait donc
comme une panne de l'outil.

La politique, en deux temps
===========================

**Premier Ctrl-C : on arrête proprement.** L'outil dit ce qu'il interrompt et
laisse l'opération en cours se terminer là où c'est possible : Terraform reçoit
son ``SIGINT`` et écrit son state, ansible-runner annule après la tâche
courante. C'est ce qui rend la reprise possible : rejouer la commande suffit.

**Second Ctrl-C : on arrête franchement.** L'outil ne doit jamais donner
l'impression d'être bloqué. Le fils est terminé (``SIGTERM`` puis ``SIGKILL``),
et le message dit que l'état peut être partiel.

Le code de sortie est **130**, soit ``128 + SIGINT``, la convention des shells.
Il dit la vérité, ce que ``1`` ne faisait pas.

Ce que ce module ne fait pas
============================

Il ne compose aucune phrase : ``Interrupted`` porte une **étape**, et c'est la
CLI qui la traduit et nomme la commande de reprise. Le modèle est celui de
``ProviderUnresolved``, où une exception porte des données, pas du texte.
"""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import StrEnum
from types import FrameType
from typing import Any, Self

logger = logging.getLogger(__name__)

#: ``128 + SIGINT``. Le shell rend déjà ce code quand il tue lui-même un
#: processus au Ctrl-C : l'outil dit donc la même chose que son environnement.
EXIT_INTERRUPTED = 130

#: Le seul événement que dsoxlab injecte lui-même dans le flux d'un outil
#: externe (Terraform, ansible-runner) : « un Ctrl-C vient d'arriver »,
#: avec son rang (1 ou 2). Passer par le flux d'events plutôt qu'imprimer
#: depuis `infra/` garde le texte affiché dans `cli.py`, donc traduit, et
#: le fait passer par la console Rich qui possède le terminal à cet instant.
EVENT_INTERRUPT = "dsoxlab_interrupt"


class Stage(StrEnum):
    """Les points de rupture inventoriés, un par opération longue.

    La valeur est **la clé i18n** du message qui décrit ce qui reste en place :
    ``interrupted_<valeur>`` dans ``i18n/strings/{en,fr}.py``. Ajouter une étape
    sans ajouter sa clé se voit dans ``tests/test_interruption.py``.
    """

    TERRAFORM_INIT = "terraform_init"
    TERRAFORM_APPLY = "terraform_apply"
    TERRAFORM_DESTROY = "terraform_destroy"
    ANSIBLE = "ansible"
    SERVICES = "services"
    HOSTS_WAIT = "hosts_wait"
    TESTS = "tests"
    SESSION = "session"
    UNKNOWN = "unknown"


class Interrupted(Exception):
    """Une opération longue a été interrompue par l'utilisateur.

    Hérite d'``Exception`` et **pas** de ``RuntimeError``, délibérément : la CLI
    est pleine de ``except RuntimeError as exc: error(str(exc))``, qui
    afficherait ici le nom de l'étape comme s'il s'agissait d'un échec. Les
    commandes qui ont un message dédié attrapent ``Interrupted`` en premier ;
    les autres tombent dans le filet de ``cli.main()``.
    """

    def __init__(self, stage: Stage, *, hard: bool = False) -> None:
        self.stage = stage
        #: L'utilisateur a insisté (second Ctrl-C) : l'arrêt n'a pas été
        #: gracieux, et l'état laissé peut être partiel.
        self.hard = hard
        super().__init__(stage.value)

    @property
    def message_key(self) -> str:
        """Clé i18n décrivant ce que cette interruption a laissé derrière elle."""
        return f"interrupted_{self.stage.value}"


@contextmanager
def interruptible(stage: Stage) -> Iterator[None]:
    """Traduit un Ctrl-C survenu dans ce bloc en ``Interrupted(stage)``.

    Pour les opérations dont dsoxlab ne pilote pas le processus fils (attente
    SSH, sondes de conteneur, pytest) : il n'y a rien à arrêter proprement, mais
    il y a tout à dire sur ce qui reste en place.
    """
    try:
        yield
    except KeyboardInterrupt:
        raise Interrupted(stage) from None


class SignalRelay:
    """Prend la main sur ``SIGINT``/``SIGTERM`` le temps d'une opération.

    Écrit pour ansible-runner, qui pose **ses propres** handlers dès qu'on ne
    lui fournit pas de ``cancel_callback``, et ne les restaure jamais. Deux
    conséquences mesurées dans ``ansible_runner.utils.signal_handler`` :

    - pendant un playbook, un Ctrl-C ne lève **aucun** ``KeyboardInterrupt`` :
      il arme un drapeau, le playbook s'annule, et l'appelant reçoit un
      ``status='canceled'`` qu'il prenait pour un échec ;
    - après le playbook, ``SIGINT`` **et** ``SIGTERM`` restent détournés pour le
      reste du processus. Un ``kill`` sur dsoxlab n'avait alors plus d'effet.

    En fournissant notre relais comme ``cancel_callback``, ansible-runner
    n'installe rien, et ce gestionnaire de contexte restaure ce qu'il a trouvé.
    """

    def __init__(self, on_notice: Callable[[int], None] | None = None) -> None:
        self._on_notice = on_notice
        self.count = 0
        # Valeur opaque rendue par `signal.getsignal` : son seul usage est
        # d'être remise telle quelle, jamais inspectée.
        self._precedents: dict[int, Any] = {}

    def is_requested(self) -> bool:
        """Un arrêt a-t-il été demandé ? Signature du ``cancel_callback``."""
        return self.count > 0

    def _handler(self, signum: int, frame: FrameType | None) -> None:
        del frame
        self.count += 1
        logger.info("signal %d reçu (%d fois)", signum, self.count)
        if self._on_notice is not None:
            try:
                self._on_notice(self.count)
            except Exception:  # un affichage ne casse pas un arrêt
                logger.exception("notification d'interruption en échec")
        if self.count >= 2:
            # Le premier signal a demandé l'annulation ; le second dit que
            # l'utilisateur n'attend plus. On repasse par le chemin normal de
            # Python pour que les `finally` (verrou, affichage Rich, terminal)
            # jouent quand même : sortir par le signal laisserait le curseur
            # caché et le verrou en place jusqu'à la mort du processus.
            raise KeyboardInterrupt

    def __enter__(self) -> Self:
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT, signal.SIGTERM):
                self._precedents[sig] = signal.getsignal(sig)
                signal.signal(sig, self._handler)
        return self

    def __exit__(self, *exc: object) -> None:
        del exc
        for sig, precedent in self._precedents.items():
            signal.signal(sig, precedent)
        self._precedents.clear()
