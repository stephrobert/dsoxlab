"""Ce que `dsoxlab use` a le droit de poser, et pourquoi il refuse le reste.

Trois refus vivent ici, et chacun vient d'un piège observé plutôt que d'une
règle de principe :

1. **`dsoxlab use incus` posait une section nommée « incus ».** Le nom
   ressemble à un provider, le filtre se posait sans un mot, et `list-labs`
   répondait « Aucun lab trouvé ». L'apprenant concluait que le catalogue était
   vide.
2. **Une section inconnue était acceptée en silence**, avec la même suite.
3. **Un provider inconnu** était enregistré dans le contexte, et n'échouait
   qu'au `provision` suivant, loin de la commande fautive.

La lecture est volontairement **brute** : on relit le `meta.yml` plutôt que de
passer par la résolution standard, parce qu'il faut pouvoir valider un provider
alors même que la résolution le laisse indéterminé, ce qui est le cas normal
d'un dépôt qui déclare plusieurs candidats sans choix actif.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..discovery.repo import find_meta_yml


class MetaIllisible(Exception):
    """Le `meta.yml` existe mais ne se charge pas.

    Distinct d'un `meta.yml` absent, qui n'est pas une erreur : un dépôt peut
    n'en avoir aucun, et on ne filtre alors rien.
    """

    def __init__(self, cause: Exception) -> None:
        super().__init__(str(cause))
        self.cause = cause


@dataclass(frozen=True)
class Declarations:
    """Ce que le `meta.yml` déclare, et contre quoi `use` se valide."""

    providers: tuple[str, ...] = ()
    sections: tuple[str, ...] = ()


@dataclass(frozen=True)
class Refus:
    """Une demande rejetée : la clé du message, et de quoi le composer."""

    cle: str
    params: dict[str, object] = field(default_factory=dict)


def lire_declarations(root: Path) -> Declarations:
    """Les providers et sections déclarés, ou rien si le dépôt n'en a pas."""
    chemin = find_meta_yml(root) or (root / "meta.yml")
    if not chemin.is_file():
        return Declarations()
    try:
        brut = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise MetaIllisible(exc) from None

    declare = (brut.get("infra") or {}).get("provider")
    if isinstance(declare, list):
        providers = tuple(str(p) for p in declare if p)
    elif isinstance(declare, str) and declare:
        providers = (declare,)
    else:
        providers = ()

    sections = tuple(
        str(s.get("id")) for s in (brut.get("sections") or []) if s.get("id")
    )
    return Declarations(providers=providers, sections=sections)


def decouper(context: str) -> tuple[str | None, str | None]:
    """``linux/l2`` donne la section et le niveau ; ``linux`` la seule section."""
    morceaux = context.strip().split("/", 1)
    section = morceaux[0] or None
    niveau = morceaux[1] if len(morceaux) > 1 else None
    return section, niveau


def refus_eventuel(
    declarations: Declarations,
    *,
    context: str | None = None,
    provider: str | None = None,
) -> Refus | None:
    """Le premier refus qui s'applique, dans l'ordre où l'erreur est probable."""
    if context is not None:
        demandee, _niveau = decouper(context)
        if (
            context in declarations.providers
            and context not in declarations.sections
        ):
            return Refus("provider_not_a_section", {"name": context})
        # Un `meta.yml` sans bloc « sections » ne déclare rien : on ne filtre
        # pas, faute de quoi tout dépôt sans sections refuserait tout.
        if declarations.sections and demandee and demandee not in declarations.sections:
            return Refus(
                "section_unknown",
                {"name": demandee, "sections": ", ".join(declarations.sections)},
            )

    if (
        provider is not None
        and declarations.providers
        and provider not in declarations.providers
    ):
        return Refus(
            "provider_unknown",
            {"name": provider, "candidates": ", ".join(declarations.providers)},
        )
    return None
