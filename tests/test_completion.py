"""La complétion au `Tab`, prise par la porte que le shell emprunte vraiment.

Ce module existe parce que la migration de `shell_complete` (contrat click) vers
`autocompletion` (contrat typer) ne se prouve pas en relisant le code. Les deux
contrats diffèrent sur la signature ET sur le type de retour, et l'erreur ne se
voit **nulle part** : ni `ruff`, ni `mypy`, ni la suite ne parlent d'un mécanisme
qu'aucun test ne déclenchait. Une complétion débranchée ne propose simplement
plus rien, en silence, chez l'apprenant.

D'où le parti pris : ces tests n'appellent pas la fonction de complétion, ils
**demandent une complétion à la CLI comme le fait le shell**. Le script que
`dsoxlab install` pose dans `~/.zfunc/_dsoxlab` exécute exactement ceci ::

    env _TYPER_COMPLETE_ARGS="${words[1,$CURRENT]}" _DSOXLAB_COMPLETE=complete_zsh dsoxlab

Les deux variables ci-dessous sont donc celles du vrai script, et la sortie
attendue est celle que zsh évalue : `_arguments '*: :(("id":"titre" …))'`, ou
`_files` quand rien ne correspond.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
import typer.main
from typer.testing import CliRunner

from dsoxlab import cli
from dsoxlab.cli import _COMPLETE_VAR, app

runner = CliRunner()

#: L'instruction que le script généré passe dans `_COMPLETE_VAR`. Typer garde
#: l'ordre « instruction_shell » de click 7, là où click 8 dit « shell_source ».
_INSTRUCTION_ZSH = "complete_zsh"

#: La variable où le script zsh dépose la ligne de commande en cours de frappe.
_ARGS_VAR = "_TYPER_COMPLETE_ARGS"

#: Les dix commandes qui prennent un `lab_id`. La liste est écrite en dur, et
#: c'est voulu : la dériver du code ferait passer au vert un site oublié.
COMMANDES_A_LAB_ID = (
    "show", "run", "course", "challenge", "guide",
    "hint", "check", "submit", "reset", "clean",
)

LAB = """\
id: {id}
title: {titre}
level: beginner
skills: [demo]
distros: [any]
doc_url: https://example.org/docs/demo/
runtime:
  type: shell
  workdir: challenge/work
"""

META = "repo:\n  id: demo-training\n  category: demo\n"

#: Trois labs, dont deux partagent un préfixe : sans quoi un filtre absent
#: passerait inaperçu, toutes les propositions étant de toute façon attendues.
LABS = (
    ("alpha-un", "Monter un volume"),
    ("alpha-deux", "Étendre un volume"),
    ("beta", "Lire un journal"),
)


@pytest.fixture
def catalogue(tmp_path: Path) -> Path:
    """Un dépôt de labs minimal, mais lisible par la découverte."""
    (tmp_path / "meta.yml").write_text(META, encoding="utf-8")
    for lab_id, titre in LABS:
        dossier = tmp_path / "labs" / "demo" / lab_id
        (dossier / "challenge" / "tests").mkdir(parents=True)
        (dossier / "lab.yaml").write_text(
            LAB.format(id=lab_id, titre=titre), encoding="utf-8"
        )
        (dossier / "README.md").write_text("# Demo\n", encoding="utf-8")
        (dossier / "scenario.md").write_text("# Scenario\n", encoding="utf-8")
    return tmp_path


def _tab(racine: Path, saisie: str) -> str:
    """Ce que le shell reçoit après un `Tab` sur ``saisie``.

    ``saisie`` est la ligne de commande telle que zsh la transmet, curseur
    compris : « dsoxlab run alph » complète le mot en cours, « dsoxlab run »
    suivi d'une espace demande toutes les propositions.
    """
    resultat = runner.invoke(
        app,
        [],
        env={
            _COMPLETE_VAR: _INSTRUCTION_ZSH,
            _ARGS_VAR: saisie,
            "LAB_HOME": str(racine),
        },
    )
    assert resultat.exit_code == 0, f"la complétion a échoué : {resultat.output}"
    return resultat.output


# ── ce que la complétion propose ─────────────────────────────────────────────

def test_le_shell_recoit_les_labs_du_depot(catalogue: Path) -> None:
    """Le test qui rougit si la complétion est débranchée, et lui seul suffit."""
    propositions = _tab(catalogue, "dsoxlab run ")

    for lab_id, _titre in LABS:
        assert f'"{lab_id}"' in propositions


def test_le_prefixe_deja_saisi_filtre(catalogue: Path) -> None:
    """Sans filtre, zsh proposerait tout le catalogue à chaque Tab, soit une
    centaine de labs sur les dépôts réels."""
    propositions = _tab(catalogue, "dsoxlab run alpha")

    assert '"alpha-un"' in propositions
    assert '"alpha-deux"' in propositions
    assert '"beta"' not in propositions


def test_le_titre_du_lab_reste_affiche(catalogue: Path) -> None:
    """L'aide de chaque proposition survit à la migration vers `autocompletion`.

    C'est la seule chose que le contrat de typer aurait pu faire perdre : il
    n'accepte plus l'objet `CompletionItem` de click, seulement une chaîne ou
    un couple `(valeur, aide)`. Rendre la chaîne seule aurait été silencieux :
    la complétion aurait continué de fonctionner, sans les titres.
    """
    propositions = _tab(catalogue, "dsoxlab run alpha-un")

    assert '"alpha-un":"Monter un volume"' in propositions


def test_un_prefixe_sans_correspondance_ne_propose_rien(catalogue: Path) -> None:
    """`_files` est la façon dont zsh dit « rien pour moi, montre des fichiers »."""
    assert _tab(catalogue, "dsoxlab run zzz").strip() == "_files"


@pytest.mark.parametrize("commande", COMMANDES_A_LAB_ID)
def test_chaque_commande_a_lab_id_complete(commande: str, catalogue: Path) -> None:
    """Les dix sites, un par un : en oublier un ne se verrait pas autrement."""
    assert '"alpha-un"' in _tab(catalogue, f"dsoxlab {commande} alpha-un")


# ── ce qu'elle ne doit jamais faire : cracher une trace ───────────────────────

def test_hors_d_un_depot_de_labs_rien_ne_casse(tmp_path: Path) -> None:
    """L'apprenant tabule dans ~/Téléchargements : pas de proposition, pas de bruit."""
    assert _tab(tmp_path, "dsoxlab run ").strip() == "_files"


def test_un_meta_yml_illisible_ne_leve_pas(tmp_path: Path) -> None:
    """YAML cassé en cours d'édition : la lecture du dépôt lève, pas la complétion."""
    (tmp_path / "meta.yml").write_text("repo: [ceci nest pas: un mapping\n", encoding="utf-8")

    assert _tab(tmp_path, "dsoxlab run ").strip() == "_files"


def test_un_contrat_trop_recent_ne_leve_pas(tmp_path: Path) -> None:
    """`UnsupportedSchemaVersion` est une exception ATTENDUE, et bien réelle.

    Un dépôt de labs écrit pour un dsoxlab plus récent la déclenche à chaque
    lecture du `meta.yml`. La CLI la rend en une phrase ; la complétion, elle,
    n'a rien à dire à ce moment-là et doit se taire.
    """
    (tmp_path / "meta.yml").write_text(
        "schema_version: 99\nrepo:\n  id: demo\n  category: demo\n", encoding="utf-8"
    )

    assert _tab(tmp_path, "dsoxlab run ").strip() == "_files"


def test_toute_panne_de_lecture_est_avalee(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le `except Exception` est délibéré : on le prouve avec une panne absurde.

    Les cas ci-dessus sont des exceptions qu'on sait nommer. Celui-ci couvre
    l'intention du filet : quoi qu'il arrive en lisant le catalogue, le shell
    de l'apprenant ne reçoit pas de traceback Python.
    """
    def boum(*_args: object, **_kwargs: object) -> list[object]:
        raise MemoryError("panne qu'aucun appelant n'anticipe")

    monkeypatch.setattr(cli, "get_all_labs", boum)

    assert _tab(catalogue, "dsoxlab run ").strip() == "_files"


# ── le contrat de typer, et l'avertissement qu'il émettait ────────────────────

def test_la_fonction_rend_des_couples_valeur_aide(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Typer n'accepte qu'une chaîne ou un couple, et son `assert` sur `str` casse.

    Rendre un `CompletionItem` de click ferait échouer l'adaptateur de typer
    *pendant* la complétion, donc dans le shell, donc nulle part où on le
    verrait. Le vérifier ici est moins cher.
    """
    monkeypatch.setenv("LAB_HOME", str(catalogue))

    propositions = cli._complete_lab_id("alpha")

    assert sorted(propositions) == [
        ("alpha-deux", "Étendre un volume"),
        ("alpha-un", "Monter un volume"),
    ]
    assert all(isinstance(valeur, str) and isinstance(aide, str) for valeur, aide in propositions)


def test_le_script_installe_pousse_ces_variables() -> None:
    """Le harnais ci-dessus tire les mêmes leviers que le script de `install`.

    Sans ce contrôle, ces tests pourraient rester verts sur un protocole que
    plus personne n'emprunte : il suffirait que typer change de variable pour
    que le shell de l'apprenant cesse de compléter sans qu'un test bronche.
    """
    from typer.completion import get_completion_script

    script = get_completion_script(  # noqa: S604 (`shell` = nom du shell Typer, pas un subprocess shell=True)
        prog_name=cli._PROG_NAME, complete_var=_COMPLETE_VAR, shell="zsh"
    )

    assert f"{_COMPLETE_VAR}={_INSTRUCTION_ZSH}" in script
    assert _ARGS_VAR in script


def test_construire_la_cli_n_avertit_plus() -> None:
    """490 avertissements par exécution de la suite noyaient le prochain.

    `shell_complete` est déprécié par typer, qui le dit une fois par argument
    et par construction de la commande. Le contrôle porte sur l'absence de
    l'avertissement, pas sur l'absence du mot-clé : un renommage partiel ne
    passerait pas.
    """
    with warnings.catch_warnings(record=True) as journal:
        warnings.simplefilter("always")
        typer.main.get_command(app)

    deprecations = [
        str(a.message) for a in journal if issubclass(a.category, DeprecationWarning)
    ]
    assert deprecations == []
