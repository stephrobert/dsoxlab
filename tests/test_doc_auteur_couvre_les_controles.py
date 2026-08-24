"""La documentation auteur couvre tous les contrôles de `validate-structure`.

Corriger une phrase périmée ne protège de rien : elle repérimera. Ce module
attaque la cause — **rien ne reliait mécaniquement ce que le validateur détecte
à ce que la documentation en dit**.

L'incident qui l'a motivé : `docs/catalog-author.md` a annoncé pendant douze
versions qu'une fixture non déclarée passait en silence (« nothing says so »),
alors que 0.1.84 avait ajouté `content_fixture_undeclared` pour la signaler. Le
comportement, le CHANGELOG et le `CLAUDE.md` avaient suivi ; cette page non, et
rien ne pouvait le dire.

Le principe retenu est le seul qui tienne sans jugement humain : **toute clé
d'anomalie qu'un validator peut produire est citée dans la page auteur.** Ajouter
un contrôle sans le documenter devient rouge, et le message nomme la clé
manquante.

Ce que ce test ne prétend pas faire : vérifier que la *phrase* qui entoure la clé
est juste. Aucun test ne sait lire « nothing says so ». Mais il force à ouvrir la
page au moment où le comportement change, et c'est ce moment-là qui manquait.
"""

from __future__ import annotations

import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
VALIDATORS = RACINE / "src" / "dsoxlab" / "validators"
DOCS = (RACINE / "docs" / "catalog-author.md",
        RACINE / "docs" / "catalog-author.fr.md")

#: Clés qu'un auteur de catalogue ne peut ni provoquer ni corriger : elles
#: relèvent de l'outil ou du réseau, pas du contrat qu'il écrit. Nommées une par
#: une avec leur raison — une exemption par motif finirait par couvrir des cas
#: qu'on n'a pas examinés.
_HORS_PAGE_AUTEUR = {
    "content_doc_url_unreachable":
        "dépend du réseau au moment du contrôle, pas du catalogue ; "
        "seul `--check-urls` la produit",
    "content_doc_url_status":
        "même raison : c'est la réponse HTTP du site, pas une faute d'auteur",
    "content_solution_unreadable":
        "un corrigé illisible sur le disque est un incident de fichier, pas "
        "une règle du contrat",
}


def _cles_des_validators() -> dict[str, str]:
    """Chaque clé d'anomalie qu'un validator peut produire, avec son module.

    Lues dans l'arbre syntaxique plutôt que listées à la main : une clé ajoutée
    doit faire échouer ce test, pas attendre qu'un lecteur la remarque.
    """
    trouvees: dict[str, str] = {}
    for chemin in sorted(VALIDATORS.glob("*.py")):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            nom = getattr(noeud.func, "id", "")
            if not nom.endswith("Issue"):
                continue
            for kw in noeud.keywords:
                if kw.arg == "key" and isinstance(kw.value, ast.Constant):
                    trouvees[str(kw.value.value)] = chemin.name
            # `MetadataIssue("champ", "cle", {...})` : la clé est en 2e position.
            if nom == "MetadataIssue" and len(noeud.args) >= 2:
                second = noeud.args[1]
                if isinstance(second, ast.Constant):
                    trouvees[str(second.value)] = chemin.name
    return trouvees


def test_la_lecture_des_validators_est_representative() -> None:
    """Sans ce contrôle, une lecture cassée rendrait le suivant toujours vert.

    C'est le défaut que tout ce module corrige, et il vaut d'abord pour lui.
    """
    assert len(_cles_des_validators()) >= 25


def test_chaque_controle_est_documente_en_anglais() -> None:
    absentes = _absentes(DOCS[0])

    assert absentes == [], (
        "ces contrôles existent dans les validators mais ne sont cités nulle "
        f"part dans docs/catalog-author.md : {absentes}\n"
        "Un auteur ne peut pas corriger ce qu'aucune page ne lui explique. "
        "Documente-les, ou inscris-les dans _HORS_PAGE_AUTEUR avec leur raison."
    )


def test_chaque_controle_est_documente_en_francais() -> None:
    absentes = _absentes(DOCS[1])

    assert absentes == [], (
        "ces contrôles ne sont cités nulle part dans "
        f"docs/catalog-author.fr.md : {absentes}"
    )


def _absentes(page: Path) -> list[str]:
    texte = page.read_text(encoding="utf-8")
    return sorted(
        cle for cle in _cles_des_validators()
        if cle not in _HORS_PAGE_AUTEUR and cle not in texte
    )


def test_chaque_exemption_designe_un_controle_existant() -> None:
    """Une exemption dont le contrôle a disparu couvre le vide, et le cache.

    Elle survivrait au renommage de la clé qu'elle dispensait, et dispenserait
    silencieusement la suivante portant le même nom.
    """
    connues = _cles_des_validators()

    orphelines = sorted(c for c in _HORS_PAGE_AUTEUR if c not in connues)

    assert orphelines == [], f"exemptions sans contrôle correspondant : {orphelines}"


def test_la_page_ne_cite_aucun_controle_disparu() -> None:
    """L'autre sens du drift, celui qui a produit cette issue.

    Une page qui décrit un contrôle retiré enseigne une règle qui n'existe plus
    — exactement ce qu'a fait « an undeclared fixture … nothing says so » pendant
    douze versions.
    """
    connues = set(_cles_des_validators())
    fantomes: list[str] = []

    for page in DOCS:
        texte = page.read_text(encoding="utf-8")
        for mot in set(texte.split()):
            nu = mot.strip("`(),.:;*")
            if nu.startswith(("content_", "struct_", "metadata_")) and nu not in connues:
                fantomes.append(f"{page.name}: {nu}")

    assert fantomes == [], (
        f"ces clés sont citées dans la documentation mais n'existent plus : "
        f"{sorted(fantomes)}"
    )
