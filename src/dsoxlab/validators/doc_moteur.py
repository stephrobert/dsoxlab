"""La documentation du moteur recopiée dans un catalogue, et devenue fausse (#201).

Un catalogue qui recopie ce que dsoxlab documente finit par dire faux : le
moteur change, la copie reste. L'inventaire du 2026-11-14 a trouvé 50 fichiers
faux dans 21 catalogues, nés pour la plupart du squelette de `new catalog`.

Ce contrôle ne juge pas qu'une page **redécrit** le moteur, ce qui demanderait
de deviner. Il cherche des phrases **connues pour être fausses**, chacune avec
la version depuis laquelle elle l'est et la page du moteur qui fait foi. Sur
les 446 Markdown hors `labs/` des catalogues mesurés, ces motifs touchent les
37 fichiers attendus et aucun autre.

La liste se tient ici : un changement de comportement du moteur qui rend une
phrase fausse y ajoute son motif, dans le même commit.

Portée : les Markdown **versionnés** hors de `labs/` et de `solution/`. Un
CHANGELOG est exclu : un journal daté cite à bon droit un comportement ancien.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .contract import ContractIssue, ContractReport


@dataclass(frozen=True)
class PhrasePerimee:
    """Une phrase fausse, ce qui la rend fausse, et depuis quand."""

    ident: str
    motif: re.Pattern[str]
    depuis: str
    page: str
    """La page de dsoxlab qui fait foi, relative à son répertoire ``docs/``."""


PHRASES: tuple[PhrasePerimee, ...] = (
    PhrasePerimee(
        "list_labs_avant",
        re.compile(
            r"(run|joue) `list-labs` \*\*(before|avant)\*\* `validate-structure`"
            r"|validator iterates over the labs already loaded"
            r"|validateur itère sur les labs déjà chargés"
            r"|n'itère que sur ce qui a chargé"
            r"|only validates labs that were already discovered"
            r"|does not report a lab declared in `meta\.yml` but missing"
            r"|ne signale pas un lab déclaré dans `meta\.yml` mais absent"
            r"|`dsoxlab list-labs` first, `validate-structure` second",
            re.IGNORECASE,
        ),
        "0.1.97",
        "catalog-author.md",
    ),
    PhrasePerimee(
        "status_joignabilite",
        re.compile(
            r"dsoxlab status`?\s*#\s*(check they answer|vérifie qu'elles répondent)"
            r"|UNREACHABLE` (on|sur) a? ?managed node \| `dsoxlab status`",
            re.IGNORECASE,
        ),
        "0.1.67",
        "commands.md",
    ),
    PhrasePerimee(
        "runtime_host",
        re.compile(r"(every|chaque) `runtime\.host` (points|pointe)", re.IGNORECASE),
        "0.1.0",
        "contract-v1.md",
    ),
    PhrasePerimee(
        "fixtures_a_plat",
        re.compile(r"copiée?s? à plat|copied flat", re.IGNORECASE),
        "0.1.37",
        "contract-v1.md",
    ),
)


def _markdown_versionnes(root: Path) -> list[Path]:
    """Les Markdown que git suit, ou tous ceux du disque hors d'un dépôt git."""
    try:
        res = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "*.md"],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        res = None
    if res is not None and res.returncode == 0:
        chemins = [root / nom for nom in res.stdout.split("\0") if nom]
    else:
        chemins = [p for p in root.rglob("*.md")
                   if not any(part.startswith(".") for part in p.relative_to(root).parts)]
    return [
        p for p in chemins
        if p.is_file()
        and p.relative_to(root).parts[0] not in ("labs", "solution")
        and not p.name.upper().startswith("CHANGELOG")
    ]


def validate_doc_moteur(root: Path) -> ContractReport:
    """Une anomalie par phrase périmée trouvée, et par fichier."""
    rapport = ContractReport()
    for chemin in sorted(_markdown_versionnes(root)):
        texte = re.sub(r"\s+", " ", chemin.read_text(encoding="utf-8", errors="replace"))
        for phrase in PHRASES:
            trouve = phrase.motif.search(texte)
            if trouve is None:
                continue
            rapport.issues.append(ContractIssue(
                path=chemin,
                key=f"doc_perimee_{phrase.ident}",
                params={
                    "file": str(chemin.relative_to(root)),
                    "excerpt": trouve.group(0)[:120],
                    "since": phrase.depuis,
                    "page": phrase.page,
                },
            ))
    return rapport
