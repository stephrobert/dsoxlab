"""La documentation ne peut plus mentir sur la CLI.

Tout ce qu'un binaire peut affirmer de lui-même ne doit pas être recopié à la
main : une commande renommée, retirée ou ajoutée laisse sinon derrière elle une
documentation qui décrit un outil qui n'existe plus. Personne ne s'en aperçoit,
parce que rien ne lit la documentation en même temps que le code.

Ce module ferme trois sens :

1. **Toute commande citée dans la documentation existe** dans la CLI.
2. **Toute commande de la CLI est décrite** dans `fullhelp`, en anglais comme en
   français. C'est la règle que le projet s'était donnée sans pouvoir la tenir :
   « ne jamais laisser le fullhelp décrire une commande qui n'existe plus ».
3. **Tout emplacement de fichier cité par la documentation existe** dans le
   code. La section « Persistence » des deux README a annoncé des mois durant
   une base `~/.local/share/dsoxlab/progress.db` et un
   `~/.config/dsoxlab/config.yaml` que rien ne lit (issue #86) : les
   emplacements de référence sont donc relevés **en appelant le code**, jamais
   recopiés ici.

Il attrape donc aussi bien la commande oubliée que la commande fantôme, et le
chemin inventé.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

from dsoxlab.cli import app
from dsoxlab.i18n.strings.en import STRINGS as EN
from dsoxlab.i18n.strings.fr import STRINGS as FR

RACINE = Path(__file__).resolve().parent.parent

#: Documents qui s'adressent à un utilisateur ou à un contributeur, et qui
#: peuvent donc citer des commandes. Le CHANGELOG en est exclu : il raconte le
#: passé, où une commande retirée a toute sa place.
DOCUMENTS = [
    "README.md",
    "README.fr.md",
    "CONTRIBUTING.md",
    "CONTRIBUTING.fr.md",
    "RELEASING.md",
    "docs/README.md",
    "docs/README.fr.md",
    "docs/learner.md",
    "docs/learner.fr.md",
    "docs/catalog-author.md",
    "docs/catalog-author.fr.md",
    "docs/trainer.md",
    "docs/trainer.fr.md",
    "docs/files.md",
    "docs/files.fr.md",
    "docs/commands.md",
    "docs/commands.fr.md",
    "docs/contract-v1.md",
    "docs/contract-v1.fr.md",
]

#: `dsoxlab <mot>` dans un texte. On ignore ce qui suit un tiret : `dsoxlab
#: --version` est une option, pas une commande.
_APPEL = re.compile(r"(?<![\w/.-])dsoxlab[ \t]+(?!-)([a-z][a-z0-9-]*)")

#: Bloc de code clôturé, et code en ligne entre accents graves.
_BLOC = re.compile(r"```.*?```", re.DOTALL)
_EN_LIGNE = re.compile(r"`([^`\n]+)`")


def _appels_de_commande(texte: str) -> set[str]:
    """Les commandes appelées dans un document, et elles seules.

    On ne lit QUE le code : blocs clôturés et accents graves. La prose emploie
    le même mot sans l'appeler (« dsoxlab lui-même », « dsoxlab itself »,
    « dsoxlab tourne »), et une extraction naïve prenait ces mots pour des
    commandes inexistantes. Un contrôle qui crie au loup sur de la grammaire
    finit désactivé, ce qui est pire que son absence.
    """
    fragments = _BLOC.findall(texte)
    fragments += _EN_LIGNE.findall(_BLOC.sub("", texte))
    return {m.group(1) for fragment in fragments for m in _APPEL.finditer(fragment)}


def _commandes_cli() -> set[str]:
    """Les noms de commandes réellement enregistrés sur l'application Typer."""
    noms = {c.name for c in app.registered_commands if c.name}
    for groupe in app.registered_groups:
        if groupe.name:
            noms.add(groupe.name)
    return noms


COMMANDES = _commandes_cli()


def test_la_cli_declare_bien_des_commandes() -> None:
    """Garde-fou : une extraction cassée rendrait tout ce module vert à vide."""
    assert len(COMMANDES) >= 20, f"seulement {len(COMMANDES)} commandes trouvées"
    assert "check" in COMMANDES and "doctor" in COMMANDES


@pytest.mark.parametrize("document", DOCUMENTS)
def test_les_commandes_citees_existent(document: str) -> None:
    """Une commande renommée laisse une documentation qui envoie dans le mur."""
    chemin = RACINE / document
    if not chemin.is_file():
        pytest.skip(f"{document} absent de ce dépôt")

    citees = _appels_de_commande(chemin.read_text(encoding="utf-8"))
    inconnues = sorted(citees - COMMANDES)
    assert not inconnues, (
        f"{document} cite des commandes qui n'existent pas : {inconnues}\n"
        f"Commandes réelles : {sorted(COMMANDES)}"
    )


@pytest.mark.parametrize("langue", ["en", "fr"])
def test_toute_commande_est_decrite_dans_le_fullhelp(langue: str) -> None:
    """L'inverse, et le plus utile : la commande ajoutée sans sa documentation.

    C'est ce contrôle qui aurait attrapé `support` et `demo` si j'avais oublié
    de les décrire, au lieu de le découvrir chez un utilisateur.
    """
    catalogue = EN if langue == "en" else FR
    fullhelp = catalogue["fullhelp_commands"]

    # `instructor` est un groupe : le fullhelp le décrit par sa sous-commande.
    attendues = COMMANDES - {"instructor"}
    manquantes = sorted(cmd for cmd in attendues if cmd not in fullhelp)

    assert not manquantes, (
        f"fullhelp ({langue}) ne décrit pas : {manquantes}\n"
        "Une commande absente du guide n'existe pas pour qui le lit."
    )


def test_le_fullhelp_ne_decrit_aucune_commande_fantome() -> None:
    """L'autre sens : une commande retirée qui survit dans le guide.

    On ne lit que les lignes en `[cyan]…[/cyan]`, qui sont la liste des
    commandes du guide, pour ne pas confondre avec la prose autour.
    """
    for langue, catalogue in (("en", EN), ("fr", FR)):
        citees = set(
            re.findall(r"\[cyan\]([a-z][a-z0-9-]*)", catalogue["fullhelp_commands"])
        )
        fantomes = sorted(citees - COMMANDES)
        assert not fantomes, (
            f"fullhelp ({langue}) décrit des commandes inexistantes : {fantomes}"
        )


def test_le_catalogue_de_demonstration_ne_cite_que_des_commandes_reelles() -> None:
    """Le lab de démonstration ENSEIGNE la boucle : s'il la nomme mal, il
    apprend une erreur, et c'est le tout premier contact avec l'outil."""
    from dsoxlab.templates import demo_catalog

    inconnues: dict[str, list[str]] = {}
    for markdown in sorted(demo_catalog().rglob("*.md")):
        citees = _appels_de_commande(markdown.read_text(encoding="utf-8"))
        manquantes = sorted(citees - COMMANDES)
        if manquantes:
            inconnues[markdown.name] = manquantes

    assert not inconnues, f"commandes inexistantes citées : {inconnues}"


def test_la_table_des_commandes_est_a_jour() -> None:
    """La table de `docs/commands.md` est produite par la CLI, et doit le rester.

    Écrite à la main, elle dérivait sans bruit : elle annonçait encore
    `dsoxlab clean` exécutant un `cleanup.sh`, alors que le zéro-bash est un
    invariant du contrat, et il y manquait `demo` et `support`.

    Ce test joue le générateur en mode vérification. Il échoue si quelqu'un
    ajoute une commande sans régénérer, ce qui est précisément le moment où la
    documentation se met à mentir.
    """
    import subprocess
    import sys

    generateur = RACINE / "scripts" / "generer-doc.py"
    if not generateur.is_file():
        pytest.skip("générateur absent de ce dépôt")

    # check=False : le code retour non nul EST le cas que ce test attrape,
    # et l'assertion en fait un message qui dit comment régénérer la doc.
    proc = subprocess.run(
        [sys.executable, str(generateur), "--verifier"],
        capture_output=True, text=True, cwd=RACINE, check=False,
    )
    assert proc.returncode == 0, (
        f"la documentation a dérivé de la CLI :\n{proc.stdout}\n"
        "Régénère-la : python3 scripts/generer-doc.py"
    )


# ── le contrat décrit les réglages que les templates lisent vraiment ──────────

#: Les surcharges de `infra.providers.<provider>` ne passent pas par
#: `models/repo.py` : elles sont transmises telles quelles au module Terraform,
#: qui les lit par `lookup(var.provider_config, …)`. Le contrôle bidirectionnel
#: de `tests/test_json_schemas.py` ne peut donc pas les voir, et une clé
#: pilotable mais décrite nulle part reste introuvable pour l'auteur d'un
#: catalogue. Ce test-ci lit le template et exige que le contrat en parle.
_LOOKUP = re.compile(
    r'lookup\(\s*var\.provider_config\s*,\s*"(\w+)"\s*,\s*"([^"]*)"\s*\)'
)

#: Clés que le template lit pour son propre compte, et qui ne relèvent pas du
#: contrat : dsoxlab les pose lui-même dans les tfvars, un auteur ne les écrit
#: jamais. Les documenter inviterait à les déclarer à la main.
_POSEES_PAR_L_OUTIL = {"ssh_pubkey", "region", "profile", "cidr"}


def test_les_reglages_kvm_du_contrat_sont_documentes() -> None:
    """Une clé lue par le template packagé doit figurer dans le contrat.

    `storage_pool` a vécu deux versions en étant lisible par le template et
    absent des trois documents qui décrivent le contrat : un formateur dont le
    pool ne s'appelle pas `default` n'avait aucun moyen de l'apprendre autrement
    qu'en lisant le Terraform empaqueté.
    """
    from dsoxlab.templates import template_root

    main_tf = (template_root() / "terraform" / "kvm" / "main.tf").read_text(
        encoding="utf-8"
    )
    lues = {
        cle: defaut
        for cle, defaut in _LOOKUP.findall(main_tf)
        if cle not in _POSEES_PAR_L_OUTIL and not cle.startswith("image_url_")
    }
    assert lues, "aucun lookup(var.provider_config, …) trouvé : ce test ne lit plus rien"

    schema = json.loads((RACINE / "schemas" / "meta.schema.json").read_text("utf-8"))
    decrites = schema["properties"]["infra"]["properties"]["providers"][
        "additionalProperties"
    ].get("properties", {})

    for cle, defaut in sorted(lues.items()):
        assert cle in decrites, (
            f"« {cle} » est pilotable depuis meta.yml mais absent de "
            "schemas/meta.schema.json"
        )
        assert decrites[cle].get("default") == defaut, (
            f"le schéma annonce « {decrites[cle].get('default')} » comme défaut "
            f"de « {cle} », le template applique « {defaut} »"
        )
        for document in ("docs/contract-v1.md", "docs/contract-v1.fr.md"):
            texte = (RACINE / document).read_text(encoding="utf-8")
            assert f"`{cle}`" in texte, f"« {cle} » n'est décrit nulle part dans {document}"


# ── les emplacements de fichiers cités existent-ils ? ─────────────────────────
#
# Le mécanisme vit dans `scripts/generer-doc.py`, avec la table des commandes :
# c'est le même principe (comparer la documentation à ce que le code FAIT) et
# le même point d'entrée, celui que joue aussi le hook pre-commit. Ces tests
# l'appellent directement, pour dire *quoi* est faux plutôt que *qu'un* truc
# l'est, et pour éprouver le contrôle sur des textes fabriqués.


def _generateur() -> Any:
    """Charge `scripts/generer-doc.py` comme un module (son nom porte un tiret)."""
    chemin = RACINE / "scripts" / "generer-doc.py"
    spec = importlib.util.spec_from_file_location("generer_doc", chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generateur() -> Any:
    generateur_py = RACINE / "scripts" / "generer-doc.py"
    if not generateur_py.is_file():
        pytest.skip("générateur absent de ce dépôt")
    return _generateur()


@pytest.fixture(scope="module")
def refs(generateur: Any) -> Any:
    """Les emplacements réels, relevés une seule fois (ils coûtent un processus)."""
    return generateur.references()


def test_les_references_sont_relevees_sur_le_code(generateur: Any, refs: Any) -> None:
    """Garde-fou : un relevé cassé rendrait tous les contrôles suivants verts à vide.

    Il vaut aussi documentation exécutable des quatre emplacements que le code
    produit et que la documentation décrit.
    """
    assert ".dsoxlab.db" in refs.noms_depot
    assert ".dsoxlab-context.json" in refs.noms_depot

    fermees = {"/".join(seg) for seg in refs.fermees}
    for attendu in (
        "dsoxlab/dsoxlab.log",
        "dsoxlab/*/dsoxlab.lock",
        "dsoxlab/*/ssh_config",
    ):
        assert any(chemin.endswith(attendu) for chemin in fermees), (
            f"aucun emplacement réel ne finit par « {attendu} » : {sorted(fermees)}"
        )


def test_aucune_page_ne_cite_un_chemin_inexistant(generateur: Any, refs: Any) -> None:
    """Le contrôle sur le dépôt réel, avec le nom de la page et du chemin fautif."""
    problemes = generateur.verifier_chemins(refs)
    assert not problemes, "\n" + "\n".join(problemes)


def test_le_controle_refuse_les_chemins_de_l_issue_86(
    generateur: Any, refs: Any
) -> None:
    """La preuve par mutation : les trois affirmations fausses sont rejetées.

    Elles sont réintroduites ici telles qu'elles étaient écrites dans les deux
    README. Un contrôle qui n'a jamais rien refusé ne prouve rien.
    """
    texte = """
    - **Scores and hints:** `~/.local/share/dsoxlab/progress.db` (XDG).
    - **User config:** `~/.config/dsoxlab/config.yaml` (optional).
    - Session: `<repo>/.dsoxlab-session.json`
    """
    inconnus = generateur.chemins_inconnus(texte, refs)
    assert inconnus == [
        "~/.config/dsoxlab/config.yaml",
        "~/.local/share/dsoxlab/progress.db",
        ".dsoxlab-session.json",
    ], inconnus


def test_la_dispense_ne_vaut_que_pour_la_page_qui_la_porte(
    generateur: Any, refs: Any
) -> None:
    """Une page peut citer un chemin POUR DIRE qu'il n'existe pas. Une seule.

    Sans cette restriction, la dispense rouvrirait la porte qu'elle ferme :
    n'importe quelle page pourrait réannoncer `progress.db` comme un
    emplacement réel, et le contrôle se tairait.
    """
    texte = "`~/.local/share/dsoxlab/progress.db`"

    dispensee = generateur.dispenses_de("docs/files.md")
    assert generateur.chemins_inconnus(texte, refs, dispenses=dispensee) == []
    assert generateur.chemins_inconnus(
        texte, refs, dispenses=generateur.dispenses_de("README.md")
    ) == ["~/.local/share/dsoxlab/progress.db"]


def test_le_controle_accepte_les_emplacements_reels(generateur: Any, refs: Any) -> None:
    """L'autre sens : ce que le code produit vraiment doit passer.

    Y compris écrit avec les paramètres que la documentation emploie
    (`<catalog-id>`, `<provider>`), qui n'existent dans aucun chemin réel.
    """
    texte = """
    `<catalog>/.dsoxlab.db` `<catalog>/.dsoxlab-context.json`
    `~/.local/state/dsoxlab/dsoxlab.log`
    `~/.local/state/dsoxlab/<catalog-id>/terraform/<provider>/`
    `~/.local/state/dsoxlab/<catalog-id>/dsoxlab.lock`
    `~/.cache/dsoxlab/<catalog-id>/inventory.json`
    `~/.cache/dsoxlab/<catalog-id>/ssh_config`
    `~/.cache/dsoxlab/version-check.json`
    `~/.local/share/dsoxlab/demo/`
    `~/.ssh/config.d/<catalog-id>.conf`
    """
    # `~/.local/bin/dsoxlab` a quitté cette liste en 0.1.62 : `install` ne
    # l'écrit plus. Il n'est donc plus un emplacement réel, mais un chemin que
    # les pages citent pour dire qu'il n'existe pas, et c'est la dispense
    # nominative qui l'autorise. Le contrôle a d'ailleurs signalé la dérive
    # tout seul, le lendemain de sa pose.
    assert generateur.chemins_inconnus(texte, refs) == []


def test_un_repertoire_de_travail_reste_hors_perimetre(
    generateur: Any, refs: Any
) -> None:
    """Un exemple de chemin utilisateur n'affirme rien sur l'outil.

    `~/Projets/mon-catalogue` est un endroit où l'on a cloné un catalogue, pas
    un emplacement que dsoxlab produit. Un contrôle qui crie au loup dessus
    finirait désactivé.
    """
    assert generateur.chemins_inconnus("`cd ~/Projets/mon-catalogue`", refs) == []


def test_les_chemins_declares_absents_le_sont_toujours(
    generateur: Any, refs: Any
) -> None:
    """L'autre bout de la dispense, et il compte autant.

    Le jour où `~/.config/dsoxlab/config.yaml` deviendra réel (issue #78), la
    page qui l'annonce inexistant deviendra fausse à son tour. Ce test le dit
    ce jour-là, au lieu de laisser la dispense couvrir un nouveau mensonge.
    """
    devenus_reels = generateur.absents_devenus_reels(refs)
    assert not devenus_reels, (
        f"le code produit désormais {devenus_reels} : mets à jour la page qui "
        "les annonce absents, puis retire-les de CHEMINS_ABSENTS"
    )


def test_toute_page_de_documentation_est_controlee(generateur: Any) -> None:
    """Une page ajoutée sans être contrôlée est une page qui pourra mentir."""
    pages = {str(p.relative_to(RACINE)) for p in generateur.documents_documentation()}
    assert "docs/files.md" in pages and "docs/files.fr.md" in pages
    assert not any(p.startswith("CHANGELOG") for p in pages), (
        "le CHANGELOG raconte le passé : un chemin retiré depuis y a sa place"
    )


# ── une page publiée s'adresse à quelqu'un, dans les deux langues ─────────────


def _pages_docs() -> list[Path]:
    return sorted(p for p in (RACINE / "docs").glob("*.md") if not p.name.endswith(".fr.md"))


def test_chaque_page_existe_dans_les_deux_langues() -> None:
    """La parité EN/FR est une promesse du projet, pas une intention.

    Une page traduite d'un seul côté se dégrade en silence : le lecteur français
    tombe sur l'anglais sans savoir si c'est un oubli ou un choix.
    """
    manquantes = [
        page.name
        for page in _pages_docs()
        if not page.with_suffix("").with_suffix(".fr.md").is_file()
        and not (page.parent / f"{page.stem}.fr.md").is_file()
    ]
    assert not manquantes, f"pages sans version française : {manquantes}"


@pytest.mark.parametrize("langue", ["", ".fr"])
def test_chaque_page_nomme_son_public(langue: str) -> None:
    """« Chaque page nomme son public en tête » (issue #86).

    Une documentation qui répond à l'apprenant, à l'auteur et au formateur dans
    le même paragraphe ne répond à aucun des trois. Le contrôle ne juge pas la
    prose : il exige la ligne qui déclare le destinataire, dans les vingt
    premières lignes.
    """
    marqueurs = ("**Audience:**", "**Public :**")
    sans_public = []
    for page in _pages_docs():
        chemin = page if langue == "" else page.parent / f"{page.stem}.fr.md"
        if not chemin.is_file():
            continue
        entete = "\n".join(chemin.read_text(encoding="utf-8").splitlines()[:20])
        if not any(marqueur in entete for marqueur in marqueurs):
            sans_public.append(chemin.name)
    assert not sans_public, (
        f"pages qui ne nomment pas leur public : {sans_public}\n"
        "Ajoute une ligne « **Audience:** … » (ou « **Public :** … ») en tête."
    )


def test_une_page_non_versionnee_ne_fait_pas_foi(
    generateur: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Un Markdown que git ne suit pas ne décrit pas le produit, donc ne le juge pas.

    Le cas réel : un `CLAUDE.md` d'agent, non versionné, cite
    `~/.config/dsoxlab/config.yaml` pour dire que ce chemin n'existe pas encore.
    Le contrôle le lisait comme une page de documentation et rendait la suite
    **rouge chez le contributeur, verte en intégration continue**, où le fichier
    n'existe pas. Un écart dans ce sens est le pire : il apprend à ne pas croire
    la suite, à l'endroit précis où elle est censée faire foi.
    """
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=30)
    (tmp_path / "docs").mkdir()
    versionnee = tmp_path / "README.md"
    versionnee.write_text("page suivie\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"],
                   check=True, timeout=30)
    libre = tmp_path / "CLAUDE.md"
    libre.write_text("cite `~/.config/dsoxlab/config.yaml`\n", encoding="utf-8")

    monkeypatch.setattr(generateur, "RACINE", tmp_path)
    pages = generateur.documents_documentation()

    assert versionnee in pages, "une page suivie par git doit rester contrôlée"
    assert libre not in pages, (
        "un Markdown non versionné ne doit pas être lu comme de la documentation"
    )


def test_hors_depot_git_toutes_les_pages_comptent(
    generateur: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Sans git, le contrôle retombe sur tout ce qu'il trouve plutôt que sur rien.

    Une archive extraite, un export sans `.git` : filtrer sur `git ls-files` y
    rendrait la liste vide, donc le contrôle vert à vide, ce qui est exactement
    l'échec silencieux que ce fichier existe pour empêcher.
    """
    (tmp_path / "docs").mkdir()
    page = tmp_path / "README.md"
    page.write_text("hors dépôt\n", encoding="utf-8")

    monkeypatch.setattr(generateur, "RACINE", tmp_path)

    assert generateur._pages_versionnees() is None
    assert page in generateur.documents_documentation()
