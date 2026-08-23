"""Un exécutable absent se nomme, il ne rend pas une trace Python (#138).

La CLI convertit déjà `CommandError`, `DomainNotFound`, `UnsupportedSchemaVersion`
et les erreurs du contrat en message traduit suivi d'un code de sortie.
`FileNotFoundError` traversait tout et remontait à l'interpréteur : l'apprenant
lisait une trace, qui dit « l'outil est cassé » alors qu'il lui manque le plus
souvent un binaire qu'il peut poser lui-même.

Le filet vit dans `_I18nGroup.invoke`, au même endroit que celui du Ctrl-C :
c'est le seul point qui couvre toutes les commandes sans en instrumenter aucune.
"""

from __future__ import annotations

import typer
from typer.testing import CliRunner

from dsoxlab import cli
from dsoxlab.i18n import _load

runner = CliRunner()


def _app_qui_leve(erreur: BaseException) -> typer.Typer:
    """Une application minimale bâtie sur le même groupe que la vraie CLI."""
    app = typer.Typer(cls=cli._I18nGroup)

    @app.command("sonde")
    def sonde() -> None:
        raise erreur

    # Une seconde commande, sans laquelle typer expose l'application comme une
    # commande unique : le groupe n'est alors jamais construit, et le filet
    # qu'on teste n'existe pas dans ce montage. La vraie CLI en a vingt-quatre.
    @app.command("temoin")
    def temoin() -> None:
        return None

    return app


def test_un_executable_absent_rend_127_et_le_nomme() -> None:
    """127 est le code que le shell rend pour « command not found »."""
    absent = FileNotFoundError(2, "No such file or directory")
    absent.filename = "terraform"

    resultat = runner.invoke(_app_qui_leve(absent), ["sonde"])

    assert resultat.exit_code == 127, resultat.output
    assert "terraform" in resultat.output
    assert "Traceback" not in resultat.output


def test_un_fichier_absent_rend_2_et_le_nomme() -> None:
    """Un chemin n'est pas une commande : il ne mérite pas le code du shell."""
    absent = FileNotFoundError(2, "No such file or directory")
    absent.filename = "/etc/dsoxlab/absent.yaml"

    resultat = runner.invoke(_app_qui_leve(absent), ["sonde"])

    assert resultat.exit_code == 2, resultat.output
    assert "/etc/dsoxlab/absent.yaml" in resultat.output
    assert "Traceback" not in resultat.output


def test_le_message_existe_dans_les_deux_langues() -> None:
    """Une clé posée d'un seul côté lève un KeyError à l'exécution, sur un
    chemin d'erreur — donc au pire moment, et seulement dans une langue."""
    for langue in ("en", "fr"):
        table = _load(langue)
        for cle in ("err_executable_introuvable", "err_fichier_introuvable"):
            assert cle in table, f"{cle} manque en {langue}"
            assert "{nom}" in table[cle], f"{cle} en {langue} n'emploie pas {{nom}}"


def test_la_traduction_se_compose_sans_jamais_lever() -> None:
    """Le garde-fou du garde-fou : une clé présente mais mal formée ne se voit
    qu'à l'exécution."""
    for langue in ("en", "fr"):
        cli_i18n = _load(langue)
        rendu = cli_i18n["err_executable_introuvable"].format(nom="terraform")
        assert "terraform" in rendu
        assert "{" not in rendu
