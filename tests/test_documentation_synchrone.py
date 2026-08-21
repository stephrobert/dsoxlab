"""La documentation ne peut plus mentir sur la CLI.

Tout ce qu'un binaire peut affirmer de lui-même ne doit pas être recopié à la
main : une commande renommée, retirée ou ajoutée laisse sinon derrière elle une
documentation qui décrit un outil qui n'existe plus. Personne ne s'en aperçoit,
parce que rien ne lit la documentation en même temps que le code.

Ce module ferme les deux sens :

1. **Toute commande citée dans la documentation existe** dans la CLI.
2. **Toute commande de la CLI est décrite** dans `fullhelp`, en anglais comme en
   français. C'est la règle que le projet s'était donnée sans pouvoir la tenir :
   « ne jamais laisser le fullhelp décrire une commande qui n'existe plus ».

Il attrape donc aussi bien la commande oubliée que la commande fantôme.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

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


def test_la_table_des_commandes_du_readme_est_a_jour() -> None:
    """La table du README est produite par la CLI, et doit le rester.

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
