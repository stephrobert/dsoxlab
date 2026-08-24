"""Point d'entrée de la CLI, et assemblage du paquet.

`cli.py` était passé de fichier d'entrée à fourre-tout : 3 289 lignes et
34 commandes, alors que la logique métier vit bien ailleurs (`services/`,
`runtimes/`, `infra/`). Ce n'était pas un défaut de conception mais de
trajectoire, chaque commande nouvelle y ajoutant ses options, sa validation et
son orchestration.

Le paquet est découpé **par public** :

- `contexte`, `parcours`, `indices`, `progression` : l'apprenant, de « quels
  labs existent » à « quelle note ai-je obtenue » ;
- `infrastructure`, `destruction`, `etat` : monter, défaire et regarder ;
- `catalogues` : installer un catalogue et en changer ;
- `auteur`, `instructeur`, `diagnostic` : écrire des labs, les encadrer, savoir
  ce qui ne va pas.

Cinq modules privés portent ce que tous partagent : `_socle` (l'application
Typer et ses sous-applications), `_commun` (les helpers de résolution du
contexte), `_amorcage` (le callback global, `--version` et l'avis de mise à
jour), `_validation` (jouer les tests et rendre le verdict), `_barres` (le
rendu des barres de progression d'Ansible et de Terraform).

**Le point d'entrée public ne change pas.** `dsoxlab.cli:main` reste
l'`entry point` déclaré, et `from dsoxlab.cli import app` continue de
fonctionner : plusieurs tests l'importent ainsi, et un consommateur externe le
pourrait.
"""

from __future__ import annotations

from ..i18n import _
from ..infra.inventory import InfraNotProvisioned
from ..interrupt import EXIT_INTERRUPTED, Interrupted
from ..models import ContractError, UnsupportedSchemaVersion
from ..reporting.console import error, warn
from ..services.lab_service import evaluate_lab, get_all_labs, open_lab_session
from ..sessions.store import get_best_scores

# L'import de ces modules est ce qui ENREGISTRE les commandes sur l'app — et,
# pour `_amorcage`, le callback global : sans lui, `dsoxlab --help` serait vide
# et aucune langue ne serait initialisée.
from . import (  # noqa: F401  (importés pour leur effet d'enregistrement)
    _amorcage,
    auteur,
    catalogues,
    contexte,
    destruction,
    diagnostic,
    etat,
    indices,
    infrastructure,
    instructeur,
    parcours,
    progression,
)
from ._commun import (
    _complete_lab_id,
    _phrase_contrat,
)
from ._socle import (
    _I18nGroup,
    app,
    catalog_app,
    completion_app,
    infra_app,
    instructor_app,
)
from ._validation import _run_check, _run_check_with_progress
from .diagnostic import _COMPLETE_VAR, _PROG_NAME, _script_completion

#: L'ordre dans lequel `dsoxlab --help` présente les commandes.
#:
#: Explicite, et non plus hérité de l'endroit où quelqu'un a collé un
#: décorateur. Typer affiche les commandes dans leur ordre d'enregistrement,
#: donc le découpage en modules le réordonnait sans qu'aucun test ne le dise —
#: or `dsoxlab --help` est la première chose que lit un utilisateur.
#:
#: Une commande absente de cette liste s'affiche à la fin plutôt que de
#: disparaître, et un test refuse qu'elle y reste inconnue.
_ORDRE_COMMANDES = (
    "install",
    "use", "list-labs", "show",
    "run", "course", "challenge", "guide", "hint",
    "check", "submit", "scores", "progress", "next", "reset", "clean",
    "validate-structure",
    "doctor",
    "provision", "destroy", "status", "ssh",
    "demo", "support", "fullhelp",
)

#: Même chose pour les sous-applications.
_ORDRE_GROUPES = ("instructor", "completion", "catalog", "infra")


def _rang(nom: str | None, ordre: tuple[str, ...]) -> int:
    return ordre.index(nom) if nom in ordre else len(ordre)


app.registered_commands.sort(key=lambda c: _rang(c.name, _ORDRE_COMMANDES))
app.registered_groups.sort(key=lambda g: _rang(g.name, _ORDRE_GROUPES))
# ── point d'entrée console ────────────────────────────────────────────────────

def main() -> None:
    """Point d'entrée de la commande ``dsoxlab``.

    Enveloppe l'app Typer pour rendre les erreurs ATTENDUES en une phrase
    actionnable, jamais en traceback Python. Une infrastructure non
    provisionnée est une situation normale (premier lancement, après un
    ``destroy``) : l'apprenant doit lire quoi faire, pas une pile d'appels.

    Les erreurs inattendues, elles, continuent de remonter avec leur
    traceback — c'est ce qu'on veut pour un vrai bug.
    """
    try:
        app()
    except Interrupted as exc:
        # Interruption d'une commande qui n'avait pas de consigne de reprise à
        # donner, ou survenue hors des étapes inventoriées. On dit au moins ce
        # qui a été interrompu, et on sort en 130 plutôt qu'en 1.
        warn(_(exc.message_key))
        if exc.hard:
            warn(_("interrupted_hard"))
        raise SystemExit(EXIT_INTERRUPTED) from None
    except InfraNotProvisioned:
        error(_("infra_not_provisioned"))
        raise SystemExit(1) from None
    # Filet de dernier recours : les commandes qui lisent le catalogue passent
    # par `_read_repo` ou `_catalogue`, qui disent déjà la même chose plus tôt.
    # Celles qui liraient un meta.yml par un autre chemin ne doivent pas pour
    # autant rendre un traceback là où une phrase suffit.
    except UnsupportedSchemaVersion as exc:
        error(_(
            "schema_version_meta_too_new",
            path=exc.source, found=exc.found, supported=exc.supported,
        ))
        raise SystemExit(1) from None
    # Filet de dernier recours, comme au-dessus : une commande qui lirait un
    # meta.yml par un autre chemin doit rendre la phrase, pas un traceback.
    except ContractError as exc:
        error(_phrase_contrat(exc))
        raise SystemExit(1) from None


__all__ = [
    # La surface publique du paquet. Les noms préfixés d'un souligné y figurent
    # parce que des tests les atteignent par `dsoxlab.cli` : les déclarer ici
    # dit qu'ils sont joints depuis l'extérieur, là où un `noqa` ne ferait que
    # taire l'outil.
    "_COMPLETE_VAR",
    "_PROG_NAME",
    "_I18nGroup",
    "_complete_lab_id",
    "_phrase_contrat",
    "_run_check",
    "_run_check_with_progress",
    "_script_completion",
    "app",
    "catalog_app",
    "completion_app",
    "evaluate_lab",
    "get_all_labs",
    "get_best_scores",
    "infra_app",
    "instructor_app",
    "main",
    "open_lab_session",
]
