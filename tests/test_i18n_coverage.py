"""Guard: no user-facing string may be hardcoded, anywhere in the package.

The rule already existed in prose ("every displayed text goes through
`_()`"), and prose did not hold: option helps, progress-bar labels and a
handful of error messages had drifted back into literals. Some were French,
so an English run showed French; others were English, so a French run showed
English. Both are the same defect.

Rather than re-audit by hand, this module parses the source and asserts the
invariant. It used to parse **`cli.py` and nothing else**, which is why the
defect kept coming back: the messages a learner reads when something breaks
are raised by `infra/` and `runtimes/`, not printed by `cli.py`. The guard
watched one door out of five.


Le critère : une phrase, pas un littéral
========================================

Interdire *toute* chaîne littérale serait intenable ; n'en interdire aucune
est la situation qu'on répare. La ligne passe ici, et elle a deux moitiés qui
doivent être vraies **ensemble** :

1. **Le puits** — la chaîne atteint-elle un humain ? Trois seulement comptent :

   * les mots-clés ``help=`` et ``description=``, que Typer affiche tels quels ;
   * les helpers d'affichage ``error`` / ``info`` / ``warn`` / ``success``
     appelés par leur nom nu, dont le premier argument est le message ;
   * un ``raise Exc(...)``, parce que la CLI de ce dépôt rend les erreurs par
     ``error(str(exc))`` : le texte d'une exception **est** un texte d'interface,
     c'est ce que le garde-fou restreint à ``cli.py`` ne voyait pas ;
   * un ``.print(...)`` / ``.echo(...)`` / ``.secho(...)``, les verbes de sortie
     de Rich, Typer et Click.

2. **La forme** — le littéral est-il une phrase ? Une phrase, ici, c'est
   **au moins deux mots séparés par une espace**, un mot valant trois lettres
   consécutives ou plus. Un fragment sans espace compte donc pour **un seul**
   mot, quel que soit le nombre de lettres qu'il enchaîne : ``meta.yml``,
   ``challenge/tests``, ``lab_starting`` et ``DSOXLAB_PROVIDER`` sont des jetons,
   pas des phrases. C'est ce qui laisse passer la mise en forme pure autour de
   valeurs déjà traduites — ``f"  ✔ {fqdn} ({ip})"`` ne porte aucun mot — et le
   vocabulaire emprunté à l'outil qu'on relaie (``(skipped)``, ``UNREACHABLE``,
   ``Error:``, ``dsoxlab {version}``), qui n'en porte qu'un.

Le prix de ce réglage est assumé : un message d'un seul mot (``error("Timeout")``)
passe sous le radar. Le rendre détectable demanderait de distinguer un mot d'un
identifiant, ce qu'aucune règle courte ne fait sans se tromper — et un test
qu'on désactive au premier faux positif ne garde plus rien.


Ce que le garde-fou ne regarde pas, et pourquoi
===============================================

**``logger.*`` n'est pas un puits d'interface.** Le journal est un artefact de
diagnostic : il part sur stderr au-delà de ``-v`` et dans le fichier que
``dsoxlab support`` ramasse, il porte des noms d'outils, des codes retour et des
chemins, et il se lit à côté d'une trace Python. Le traduire rendrait deux
rapports de bug incomparables selon la locale de qui les produit, et se heurte
au formatage paresseux (``logger.info("x %s", v)``) que la famille de règles
``G`` impose ici : ``_()`` formate à l'appel, ``logging`` au rendu. Le journal
doit être *cohérent* — il mélange aujourd'hui le français et l'anglais, ce qui
est un vrai défaut — mais cohérent n'est pas traduit, et c'est un autre lot.

**``models/`` est dans le périmètre depuis #139**, et la dette qui l'en tenait
dehors est soldée. Les 24 ``ValueError`` du contrat ont été triées sur une seule
question : *ce message atteint-il un humain qui lit l'interface ?*

* **oui pour un ``meta.yml``** : ``discovery/repo.py`` laisse remonter l'erreur
  et ``cli.py`` l'affiche. Ces raises lèvent une ``ContractError``, qui porte
  ``source``, ``field``, une **clé i18n** et ses paramètres, comme
  ``UnsupportedSchemaVersion`` et ``ProviderUnresolved`` le faisaient déjà. La
  phrase se compose dans la CLI ; le modèle reste agnostique de la langue ;
* **non pour un ``lab.yaml``** : ``discovery/scanner.py`` est son seul lecteur,
  il écarte le lab et journalise la raison. Ces raises lèvent une
  ``LabYamlError``, dont le texte reste technique, car traduire ce qui ne
  s'affiche jamais serait du travail perdu et du bruit dans les tables. Le
  garde-fou la connaît par son nom (voir :data:`JOURNAL_SEULEMENT`), et c'est ce
  qui rend le tri **vérifiable** : le jour où l'un de ces messages doit
  s'afficher, il change de classe et le garde-fou réclame sa clé.

**Les validators sont surveillés par un cinquième puits.** Leurs messages ne
passaient par aucun des quatre autres : ils vivaient dans un champ ``message``
de dataclasse, que ``validate-structure`` affichait tel quel. Ils portent
désormais une clé, et toute phrase écrite en dur dans la construction d'une
``ContentIssue`` / ``MetadataIssue`` / ``StructureIssue`` / ``ContractIssue``
est signalée ici.

**``templates/demo/`` est du contenu pédagogique**, pas le code de l'outil : le
lab de démonstration packagé s'adresse à l'apprenant dans le fichier même qu'il
va lire, et n'a aucune raison de passer par la table de traduction.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import dsoxlab

_RACINE = Path(dsoxlab.__file__).parent

#: Répertoires écartés du garde-fou, avec la raison — voir le docstring.
#: Toute entrée ajoutée ici doit y être justifiée : c'est une porte qu'on
#: choisit de ne pas surveiller, pas un détail de configuration.
#:
#: ``models/`` en est sorti en 0.1.59 : ses erreurs d'interface portent
#: désormais une clé, et celles qui n'en sont pas se nomment.
_HORS_PERIMETRE = ("templates/demo/",)


def _sources() -> list[Path]:
    """Tous les modules du paquet, moins le hors-périmètre documenté."""
    return sorted(
        chemin
        for chemin in _RACINE.rglob("*.py")
        if not chemin.relative_to(_RACINE).as_posix().startswith(_HORS_PERIMETRE)
    )


#: Les helpers d'affichage de `reporting.console`. Leur premier argument est
#: le message vu par l'apprenant.
MESSAGE_FUNCS = {"error", "info", "warn", "success"}

#: Les verbes de sortie de Rich, Typer et Click, appelés sur un objet
#: (`console.print`, `typer.echo`, `progress.console.print`…).
SORTIE_FUNCS = {"print", "echo", "secho"}

#: `typer.Exit` et `SystemExit` portent un code de sortie, jamais un message :
#: les inclure ferait crier le garde-fou sur chaque sortie propre de la CLI.
CONTROLE_DE_FLUX = {"Exit", "SystemExit"}

#: Les exceptions dont le texte ne va **qu'au journal**. `LabYamlError` est
#: levée par la lecture d'un `lab.yaml`, dont `discovery/scanner.py` est le seul
#: appelant : il écarte le lab et journalise la raison, que rien n'affiche.
#: Cette liste est le pendant vérifiable du tri de #139 : une classe y entre
#: seulement si aucun chemin de code ne rend son message à l'écran.
JOURNAL_SEULEMENT = {"LabYamlError"}

#: Les anomalies que `validate-structure` affiche. Elles portent une clé i18n
#: et des paramètres ; une phrase écrite en dur dans leur construction
#: s'afficherait dans une seule langue, ce qui est précisément le défaut de #139.
ISSUE_CLASSES = {"ContentIssue", "MetadataIssue", "StructureIssue", "ContractIssue"}

#: Balises Rich (`[bold]`, `[/green]`…) : de la mise en forme, pas du texte.
_RICH_TAG = re.compile(r"\[/?[a-z0-9 #]+\]", re.IGNORECASE)

#: « Mot » au sens de ce test : trois lettres consécutives ou plus. En dessous,
#: on est dans les symboles, la ponctuation ou les unités, pas dans la phrase.
_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)

#: En deçà de deux mots séparés par une espace, on n'a pas une phrase.
_SEUIL_PHRASE = 2


@pytest.fixture(scope="module")
def arbres() -> list[tuple[str, ast.Module]]:
    """Le paquet couvert, parsé une fois, nommé en chemin relatif."""
    return [
        (
            chemin.relative_to(_RACINE).as_posix(),
            ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin)),
        )
        for chemin in _sources()
    ]


def _is_i18n_call(node: ast.AST) -> bool:
    """Le nœud est-il un appel `_("clé", …)` ?"""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_"
    )


def _parties_litterales(node: ast.AST) -> list[str]:
    """Le texte écrit en dur : la constante, ou les morceaux fixes d'une f-string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return [
            part.value
            for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        ]
    return []


def _mots_de_phrase(node: ast.AST) -> list[str]:
    """Les mots du littéral, à raison d'**un par fragment séparé d'espaces**.

    Compter un mot par fragment est tout le réglage du test. Sans ce plafond,
    ``lab_starting``, ``meta.yml`` ou ``challenge/tests`` vaudraient deux mots
    et le garde-fou crierait sur des clés, des chemins et des identifiants.
    Avec lui, il ne reste que ce qui s'écrit comme une phrase.

    Rend une liste vide dès que le compte n'atteint pas le seuil : un appelant
    n'a jamais à connaître le seuil, seulement à tester la vérité de la liste.
    """
    mots: list[str] = []
    for partie in _parties_litterales(node):
        for fragment in _RICH_TAG.sub(" ", partie).split():
            if _WORD.search(fragment):
                mots.append(fragment)
    return mots if len(mots) >= _SEUIL_PHRASE else []


def _nom_appele(func: ast.AST) -> str:
    """Le nom terminal d'un appelé : `warn`, `print` pour `console.print`…"""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _coupables(module: str, tree: ast.Module) -> list[str]:
    """Les phrases en dur qui atteindraient l'utilisateur dans ce module."""
    trouves: list[str] = []

    def _retenir(node: ast.AST, quoi: str) -> None:
        mots = _mots_de_phrase(node)
        if mots:
            extrait = " ".join(mots)[:60]
            trouves.append(f"{module}:{node.lineno} — {quoi} : {extrait!r}")

    for node in ast.walk(tree):
        # ── Puits 1 : les libellés que Typer affiche tels quels ───────────────
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                litteral = isinstance(kw.value, ast.JoinedStr) or (
                    isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)
                )
                if kw.arg in {"help", "description"} and litteral:
                    trouves.append(f"{module}:{kw.value.lineno} — {kw.arg}=")

        # ── Puits 2 : les helpers d'affichage, appelés par leur nom nu ────────
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in MESSAGE_FUNCS
            and node.args
            and not _is_i18n_call(node.args[0])
        ):
            _retenir(node.args[0], node.func.id)

        # ── Puits 3 : le texte d'une exception, rendu par `error(str(exc))` ───
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            nom = _nom_appele(node.exc.func)
            if nom not in CONTROLE_DE_FLUX and nom not in JOURNAL_SEULEMENT:
                arguments = list(node.exc.args) + [kw.value for kw in node.exc.keywords]
                for argument in arguments:
                    if not _is_i18n_call(argument):
                        _retenir(argument, f"raise {nom}")

        # ── Puits 4 : les verbes de sortie de Rich, Typer et Click ────────────
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in SORTIE_FUNCS
            and node.args
            and not _is_i18n_call(node.args[0])
        ):
            _retenir(node.args[0], f".{node.func.attr}()")

        # ── Puits 5 : les anomalies que `validate-structure` affiche ──────────
        if isinstance(node, ast.Call) and _nom_appele(node.func) in ISSUE_CLASSES:
            for argument in list(node.args) + [kw.value for kw in node.keywords]:
                _retenir(argument, _nom_appele(node.func))
                # Le message d'un validator vit souvent dans `params={...}` :
                # une phrase glissée en valeur s'afficherait telle quelle.
                if isinstance(argument, ast.Dict):
                    for valeur in argument.values:
                        _retenir(valeur, _nom_appele(node.func))

    return trouves


# ── Le garde-fou lui-même ─────────────────────────────────────────────────────


def test_le_paquet_ne_porte_aucune_phrase_en_dur(
    arbres: list[tuple[str, ast.Module]],
) -> None:
    """Aucun puits d'interface ne porte de phrase écrite en dur.

    Un échec ici se répare en ajoutant la clé dans `i18n/strings/en.py` **et**
    `i18n/strings/fr.py`, jamais en élargissant `_HORS_PERIMETRE`.
    """
    coupables: list[str] = []
    for module, tree in arbres:
        coupables += _coupables(module, tree)

    assert not coupables, (
        "Ces textes ne suivraient pas DSOXLAB_LANG :\n  " + "\n  ".join(coupables)
    )


def test_le_perimetre_couvre_bien_les_chemins_dinfra(
    arbres: list[tuple[str, ast.Module]],
) -> None:
    """Le périmètre est un invariant, pas une conséquence de l'arborescence.

    Le défaut d'origine n'était pas une chaîne oubliée, c'était un garde-fou
    qui ne regardait qu'un fichier. Si un jour `infra/` ou `runtimes/` sortait
    de la couverture, la régression serait invisible : elle se verrait ici.
    """
    couverts = {module for module, _tree in arbres}
    for attendu in (
        # `cli.py` est devenu un paquet en 0.1.69 : on nomme des modules de
        # publics différents, pour qu'un découpage futur qui en oublierait un
        # se voie ici plutôt que de retirer la règle en silence.
        "cli/__init__.py",
        "cli/_commun.py",
        "cli/contexte.py",
        "cli/progression.py",
        "cli/diagnostic.py",
        "infra/terraform.py",
        "infra/inventory.py",
        "infra/credentials.py",
        "runtimes/vm.py",
        "runtimes/services.py",
        "services/lab_service.py",
        "reporting/console.py",
    ):
        assert attendu in couverts, f"{attendu} n'est plus analysé par le garde-fou"


# ── Le garde-fou mord-il ? Une famille de cas par test ────────────────────────
#
# Un test qui ne peut pas échouer ne prouve rien. Chaque famille que le
# garde-fou prétend couvrir est donc jouée ici sur du code fautif écrit à la
# main, puis sur son équivalent légitime.


def _analyse(source: str) -> list[str]:
    return _coupables("sonde.py", ast.parse(source))


def test_il_mord_sur_un_libelle_typer() -> None:
    assert _analyse('typer.Option("--x", help="Force the rebuild")')
    assert not _analyse('typer.Option("--x", help=_("opt_force"))')


def test_il_mord_sur_un_helper_daffichage() -> None:
    assert _analyse('error("Host inconnu dans meta.yml")')
    assert _analyse('info(f"Cible retenue : {x}")')
    assert not _analyse('error(_("host_unknown", fqdn=f))')


def test_il_mord_sur_le_texte_porte_par_une_exception() -> None:
    assert _analyse('raise RuntimeError("terraform absent du PATH")')
    assert _analyse('raise ServiceError(f"Le service {n} n\'a jamais répondu")')
    assert not _analyse('raise TerraformNotInstalled(_("terraform_missing"))')


def test_il_mord_sur_un_verbe_de_sortie() -> None:
    assert _analyse('console.print("Aucun lab trouvé")')
    assert _analyse('progress.console.print(f"  Tâche échouée : {t}")')
    assert not _analyse('console.print(_("no_labs_found"))')


def test_il_laisse_passer_la_mise_en_forme() -> None:
    """La frontière écrite dans le CLAUDE.md : du décor autour d'un traduit."""
    assert not _analyse('success(f"  ✔ {fqdn} ({ip})")')
    assert not _analyse('console.print(f"[bold]{a}[/bold] → {b}")')
    assert not _analyse('console.print(f"dsoxlab {__version__}")')
    assert not _analyse('console.print(f"  [dim]⊘ {short}  (skipped)[/dim]")')


def test_il_laisse_passer_les_jetons_techniques() -> None:
    """Un identifiant, un chemin, une clé : un seul mot, donc pas une phrase."""
    assert not _analyse('error(_("lab_starting"))')
    assert not _analyse('raise RuntimeError(f"{lab.path}/challenge/tests")')
    assert not _analyse('raise KeyError("DSOXLAB_PROVIDER")')


def test_il_ignore_les_sorties_de_controle_de_flux() -> None:
    """`typer.Exit(1)` n'est pas un message, et n'a pas à être traduit."""
    assert not _analyse('raise typer.Exit(1)')
    assert not _analyse('raise SystemExit(1)')


def test_il_mord_sur_une_anomalie_de_validator() -> None:
    """Le défaut de #139 : une phrase française dans un champ de dataclasse."""
    assert _analyse('StructureIssue(path=p, message="Fichier manquant : lab.yaml")')
    assert _analyse('MetadataIssue("doc_url", "URL invalide, schéma attendu")')
    assert _analyse('ContentIssue(path=f, params={"x": "solution en clair, chiffre-la"})')
    assert not _analyse('StructureIssue(path=p, key="struct_missing_file")')
    assert not _analyse(
        'ContentIssue(path=f, key="content_broken_links", params={"links": cibles})'
    )


def test_une_erreur_de_contrat_affichee_doit_porter_sa_cle() -> None:
    """`models/` est dans le périmètre : une phrase levée là s'afficherait."""
    assert _analyse('raise ContractError(source, "infra", "reçu un mapping vide")')
    assert not _analyse(
        'raise ContractError(source, "infra.hosts", "contract_field_not_mapping_list")'
    )


def test_une_erreur_qui_ne_va_qu_au_journal_reste_libre() -> None:
    """Le pendant du tri : ce que personne n'affiche n'a pas à être traduit.

    Le jour où l'un de ces messages doit s'afficher, il change de classe pour
    `ContractError`, et le test ci-dessus le réclame.
    """
    assert not _analyse('raise LabYamlError(f"{p}: runtime.targets[0] doit contenir un name")')
    assert _analyse('raise ValueError(f"{p}: runtime.targets[0] doit contenir un name")')


def test_le_journal_reste_hors_du_perimetre() -> None:
    """Décision explicite, pas un oubli : voir le docstring du module.

    Ce test existe pour qu'un futur lecteur voie que le cas a été tranché.
    Le jour où l'on décide l'inverse, c'est lui qu'il faut retourner.
    """
    assert not _analyse('logger.warning("snapshot-delete a échoué pour %s", d)')
    assert not _analyse('logger.info("Host %s prêt (tentative %d).", f, n)')
