"""Découper un cours qui n'a pas été découpé.

Le contrat prévoit un ``course.yaml`` pour servir un cours section par
section. **Aucun catalogue ne l'écrit** : mesuré le 2026-10-16 sur les cinq
catalogues présents, 0 sur 310 labs. ``course`` retombait donc sur
``scenario.md`` + ``README.md`` affichés d'un bloc, soit une médiane de 363
lignes sur ``linux-dsoxlab-training`` et un maximum de 1 080. Le pager ajouté
en 0.1.33 traitait le symptôme ; la cause est qu'un découpage existant demandait
d'écrire un fichier de plus par lab, pour 310 labs.

Ce module le fait à partir des titres que les documents portent déjà, et
``course.yaml`` garde la priorité partout où il existe : un auteur qui veut
choisir son découpage le peut toujours.

Le choix du niveau de titre, et pourquoi il n'est pas fixe
=========================================================

Mesuré sur les 310 labs : les catalogues ne structurent pas pareil.

======================  ===============================  ==================
catalogue               structure                        niveau pertinent
======================  ===============================  ==================
``ansible``             15 titres ``##`` par lab          2
``terraform``           10 titres ``##``                  2
``python``, ``devsecops``  4 titres ``##``                2
``linux``               1 ``## Le cours``, 7 ``###``      **3**
======================  ===============================  ==================

Un niveau fixe à 2 aurait donc rendu, sur ``linux``, **deux sections de
180 lignes** : le défaut qu'on voulait corriger. La règle essaie donc les
niveaux 2 puis 3 et retient le premier qui donne au moins
:data:`SECTIONS_MIN` sections dont aucune ne dépasse :data:`LIGNES_MAX` ; à
défaut, celui dont la plus grande section est la plus petite.

Résultat mesuré après application : 4 à 16 sections par lab, médiane 7 sur
``linux`` et 15 sur ``ansible``.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from ..i18n import _
from ..models.course import CourseManifest, CourseSection

#: En dessous de ce nombre de sections, découper n'apprend rien : deux parts de
#: cent lignes se lisent comme deux cents lignes.
SECTIONS_MIN = 3

#: Au-delà de cette taille, une section n'est plus une section : c'est le
#: document qu'on voulait découper. Deux écrans de terminal.
LIGNES_MAX = 60

#: Niveaux de titre essayés, dans l'ordre de préférence.
NIVEAUX = (2, 3)

#: Les documents de cours, dans l'ordre où ils se lisent. Le même que celui de
#: l'affichage d'un bloc, pour que le découpage ne change pas l'ordre du propos.
DOCUMENTS = ("scenario.md", "README.md")

_CLOTURE_CODE = re.compile(r"^\s*```")


def _titre_de_niveau(niveau: int) -> re.Pattern[str]:
    return re.compile(rf"^{'#' * niveau}\s+(.+?)\s*$")


#: Nombre de mots retenus pour un identifiant de section. Quatre suffisent à
#: distinguer les sections d'un même cours, et l'identifiant se tape : couper
#: au caractère donnait « contexte-construire-une-arborescence-a-l », tronqué
#: au milieu d'un mot et donc impossible à retenir.
_MOTS_IDENTIFIANT = 4

#: Mots trop courts ou trop communs pour distinguer une section. Les retirer
#: rapproche l'identifiant de ce que l'auteur voulait dire.
_MOTS_VIDES = frozenset(
    {"le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "et", "a",
     "au", "aux", "en", "the", "an", "of", "to", "and", "in"}
)


def _slug(titre: str) -> str:
    """Un identifiant de section, utilisable en argument de ``--section``.

    Les accents sont retirés et les mots joints par des tirets : l'identifiant
    se tape, donc il doit tenir sur un clavier sans composition.
    """
    sans_accent = "".join(
        c
        for c in unicodedata.normalize("NFKD", titre.lower())
        if not unicodedata.combining(c)
    )
    mots = [m for m in re.findall(r"[a-z0-9]+", sans_accent) if m not in _MOTS_VIDES]
    return "-".join(mots[:_MOTS_IDENTIFIANT]) or "section"


def decouper(texte: str, niveau: int) -> list[tuple[str, str]]:
    """Les sections d'un Markdown à ce niveau de titre : (titre, contenu).

    Un titre **dans un bloc de code** n'est pas un titre : ``## quelque chose``
    entre deux ``` est un commentaire shell, et découper dessus couperait le
    cours au milieu d'un exemple. Le compteur de clôtures les ignore donc.

    **Ce qui précède le premier titre devient une section**, et ce n'est pas un
    détail : une première version l'écartait comme un simple en-tête. Sur
    ``linux-dsoxlab-training``, dont le cours se découpe au niveau 3, cela
    jetait tout le contenu de « ## Rappel » et l'introduction de « ## Le
    cours », soit vingt-six lignes qui n'apparaissaient plus nulle part. Le
    préambule porte alors un titre vide, et l'appelant lui en donne un.
    """
    motif = _titre_de_niveau(niveau)
    sections: list[tuple[str, list[str]]] = [("", [])]
    dans_code = False
    for ligne in texte.splitlines():
        if _CLOTURE_CODE.match(ligne):
            dans_code = not dans_code
        if not dans_code and (trouve := motif.match(ligne)):
            sections.append((trouve.group(1), []))
        else:
            sections[-1][1].append(ligne)
    decoupe = [(titre, "\n".join(corps).strip()) for titre, corps in sections]
    # Le préambule ne devient une section que s'il porte du TEXTE. Un document
    # qui commence par « # Titre du lab » suivi du premier titre n'a pas de
    # préambule : garder cette section donnerait une entrée de sommaire dont le
    # contenu est un titre déjà affiché par ailleurs.
    if decoupe and not _porte_du_texte(decoupe[0][1]):
        decoupe.pop(0)
    return decoupe


def _porte_du_texte(corps: str) -> bool:
    """Reste-t-il autre chose que des titres dans ce fragment ?"""
    return any(
        ligne.strip() and not ligne.lstrip().startswith("#")
        for ligne in corps.splitlines()
    )


def choisir_decoupage(texte: str) -> list[tuple[str, str]]:
    """Le meilleur découpage de ce texte, ou une liste vide s'il n'y en a pas.

    « Meilleur » au sens de la règle décrite en tête de module : des sections
    assez nombreuses et assez courtes, en préférant le niveau de titre le plus
    haut, qui suit le découpage voulu par l'auteur.
    """
    candidats = [(n, decouper(texte, n)) for n in NIVEAUX]
    # Un découpage qui n'a trouvé QUE le préambule n'est pas un découpage : le
    # document ne porte aucun titre de ce niveau, et le garder rendrait une
    # section unique et sans titre.
    candidats = [
        (n, d) for n, d in candidats if d and any(titre for titre, _c in d)
    ]
    if not candidats:
        return []

    def plus_grande(decoupe: list[tuple[str, str]]) -> int:
        return max(len(corps.splitlines()) for _titre, corps in decoupe)

    for _niveau, decoupe in candidats:
        if len(decoupe) >= SECTIONS_MIN and plus_grande(decoupe) <= LIGNES_MAX:
            return decoupe
    return min(candidats, key=lambda c: plus_grande(c[1]))[1]


def _documents_du_lab(lab_path: Path, lang: str) -> str:
    """Les documents de cours concaténés, dans leur version localisée.

    La règle de localisation est celle du reste de l'outil : ``README.fr.md``
    l'emporte sur ``README.md`` quand la langue est le français, et son absence
    n'est pas une faute.
    """
    morceaux: list[str] = []
    for nom in DOCUMENTS:
        tige, suffixe = nom.rsplit(".", 1)
        candidats = [f"{tige}.{lang}.{suffixe}", nom] if lang != "en" else [nom]
        for candidat in candidats:
            chemin = lab_path / candidat
            if chemin.is_file():
                morceaux.append(chemin.read_text(encoding="utf-8", errors="replace"))
                break
    return "\n\n".join(morceaux)


def _titre_du_preambule(corps: str) -> str:
    """Le premier titre que porte le préambule, ou un libellé traduit."""
    for ligne in corps.splitlines():
        if ligne.startswith("#"):
            titre = ligne.lstrip("#").strip()
            if titre:
                return titre
    return _("course_section_ouverture")


def manifeste_automatique(
    lab_path: Path, titre: str, lang: str = "en"
) -> CourseManifest | None:
    """Un ``CourseManifest`` déduit des titres du cours, ou ``None``.

    Rend ``None`` quand les documents ne portent pas de titre exploitable : il
    reste alors l'affichage d'un bloc, qui est honnête pour un cours de
    cinquante lignes. Mesuré : 3 labs sur 310 sont dans ce cas.

    Les sections portent leur **contenu**, pas un chemin de fichier : il n'y a
    pas de fichier à pointer, et c'est la seule différence avec un
    ``course.yaml``. Tout le reste de la mécanique (position mémorisée,
    ``--next``, ``--prev``, sommaire, fin de cours) s'applique sans changement.
    """
    texte = _documents_du_lab(lab_path, lang)
    if not texte.strip():
        return None
    decoupe = choisir_decoupage(texte)
    if len(decoupe) < 2:
        # Une seule section n'est pas un découpage : autant afficher le bloc.
        return None

    sections: list[CourseSection] = []
    vus: set[str] = set()
    for rang, (brut, corps) in enumerate(decoupe, 1):
        # Le préambule n'a pas de titre : on lui donne le premier titre qu'il
        # porte lui-même, ce qui est presque toujours « Rappel » ou le titre du
        # lab, et à défaut un libellé traduit.
        titre_section = brut or _titre_du_preambule(corps)
        identifiant = _slug(titre_section)
        if identifiant in vus:
            # Deux titres identiques dans un même cours : l'identifiant doit
            # rester unique, sinon `--section` en désignerait un au hasard.
            identifiant = f"{identifiant}-{rang}"
        vus.add(identifiant)
        sections.append(
            CourseSection(
                id=identifiant, title=titre_section, file="", contenu=corps
            )
        )
    return CourseManifest(title=titre, sections=sections, automatique=True)
