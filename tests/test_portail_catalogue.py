"""`learning.portal_url` : un catalogue dit où remettre, et rien de plus.

Le portail qui consomme les résultats d'un apprenant n'est pas forcément le site
de l'auteur de dsoxlab : ce peut être celui d'un formateur, une plateforme
interne, un site statique, un LMS, un portail local — ou aucun. **Le moteur ne
porte donc aucun domaine de formation**, et ces tests le vérifient dans les deux
sens : deux catalogues déclarent deux portails différents, et un catalogue sans
portail ne voit rien s'afficher.

La sécurité du champ n'est pas réimplémentée ici : elle est celle de
`security/urls.py`, avec la politique du portail. Ce qui se mesure dans ce
fichier, c'est que le contrat la **traverse** — parsing tolérant, validation au
point d'usage, et un `validate-structure` qui le dit à l'auteur.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.models import RepoMetadata
from dsoxlab.security.urls import (
    VARIABLE_PORTAIL_LOCAL,
    URLRefusee,
    url_de_portail,
)

runner = CliRunner()

_META = """\
repo:
  id: {ident}
  category: domaine
{learning}"""


def _meta(tmp_path: Path, *, ident: str = "essai", portail: str | None = None) -> Path:
    bloc = "" if portail is None else f"learning:\n  portal_url: \"{portail}\"\n"
    chemin = tmp_path / "meta.yml"
    chemin.write_text(_META.format(ident=ident, learning=bloc), encoding="utf-8")
    return chemin


# ── le contrat ───────────────────────────────────────────────────────────────

def test_un_catalogue_declare_son_portail(tmp_path: Path) -> None:
    meta = _meta(tmp_path, portail="https://formation.example.org/mon-apprentissage/")

    repo = RepoMetadata.from_yaml(meta)

    assert repo.learning.portal_url == "https://formation.example.org/mon-apprentissage/"


def test_deux_catalogues_deux_portails(tmp_path: Path) -> None:
    """Le moteur ne porte aucune adresse par défaut : chacun déclare la sienne."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    premier = RepoMetadata.from_yaml(
        _meta(tmp_path / "a", ident="a", portail="https://un.example.org/p/")
    )
    second = RepoMetadata.from_yaml(
        _meta(tmp_path / "b", ident="b", portail="https://deux.example.net/q/")
    )

    assert premier.learning.portal_url != second.learning.portal_url


def test_un_catalogue_sans_portail_se_lit(tmp_path: Path) -> None:
    """C'est le cas par défaut, et ce n'est pas une anomalie."""
    repo = RepoMetadata.from_yaml(_meta(tmp_path))

    assert repo.learning.portal_url == ""


def test_le_parseur_ne_refuse_pas_une_url_hostile(tmp_path: Path) -> None:
    """La v1 garantit qu'un catalogue se charge. La politique agit ailleurs.

    Refuser ici ferait disparaître tout un catalogue — ses labs compris — pour un
    champ facultatif qu'aucune commande n'a encore lu.
    """
    repo = RepoMetadata.from_yaml(_meta(tmp_path, portail="javascript:alert(1)"))

    assert repo.learning.portal_url == "javascript:alert(1)"


# ── la politique du portail ──────────────────────────────────────────────────

def test_le_portail_exige_le_chiffrement(tmp_path: Path) -> None:
    with pytest.raises(URLRefusee) as leve:
        url_de_portail("http://formation.example.org/p/")
    assert leve.value.cle == "securite_url_schema"


@pytest.mark.parametrize("hostile", [
    "javascript:alert(1)",
    "data:text/html,<script>1</script>",
    "file:///etc/shadow",
    "ftp://exemple.test/",
    "ssh://exemple.test/",
    "https://vrai.test@attaquant.test/",
    "https:///sans-hote",
    "",
])
def test_une_url_de_portail_hostile_est_refusee(hostile: str) -> None:
    with pytest.raises(URLRefusee):
        url_de_portail(hostile)


def test_un_portail_en_https_passe_intact() -> None:
    url = "https://formation.example.org/mon-apprentissage/"
    assert url_de_portail(url) == url


# ── la dérogation locale : deux gardes, pas un ───────────────────────────────

@pytest.mark.parametrize("local", [
    "http://localhost:4321/mon-apprentissage/",
    "http://127.0.0.1:8080/p/",
])
def test_le_mode_local_autorise_le_clair(
    local: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pour qui écrit un portail : rien ne sort de la machine, rien n'est exposé."""
    monkeypatch.setenv(VARIABLE_PORTAIL_LOCAL, "1")

    assert url_de_portail(local) == local


def test_sans_la_variable_localhost_reste_refuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Désactivé par défaut : c'est ce qui en fait une dérogation."""
    monkeypatch.delenv(VARIABLE_PORTAIL_LOCAL, raising=False)

    with pytest.raises(URLRefusee):
        url_de_portail("http://localhost:4321/p/")


def test_le_mode_local_ne_couvre_que_l_hote_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sinon la variable voudrait dire « fais-moi confiance pour tout ».

    Un catalogue déclarant `http://formation.example.org` doit rester refusé sur
    la machine d'un développeur de portail comme sur celle d'un apprenant.
    """
    monkeypatch.setenv(VARIABLE_PORTAIL_LOCAL, "1")

    with pytest.raises(URLRefusee) as leve:
        url_de_portail("http://formation.example.org/p/")
    assert leve.value.cle == "securite_url_schema"


def test_le_mode_local_ne_cede_rien_d_autre(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La dérogation porte sur le schéma seul, pas sur le reste des règles."""
    monkeypatch.setenv(VARIABLE_PORTAIL_LOCAL, "1")

    with pytest.raises(URLRefusee):
        url_de_portail("http://vrai.test@localhost/p/")


# ── aucune sonde réseau, y compris dans validate-structure ───────────────────

def test_valider_un_portail_ne_touche_pas_au_reseau(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sinon un catalogue ferait frapper la CI de son auteur où il veut."""
    import socket
    import urllib.request

    def interdit(*_a: Any, **_k: Any) -> None:
        raise AssertionError("la validation du portail a touché au réseau")

    monkeypatch.setattr(socket, "socket", interdit)
    monkeypatch.setattr(socket, "create_connection", interdit)
    monkeypatch.setattr(socket, "getaddrinfo", interdit)
    monkeypatch.setattr(urllib.request, "urlopen", interdit)

    assert url_de_portail("https://service-interne.test/remise/")


# ── ce que l'auteur du catalogue voit ────────────────────────────────────────

def _declarer_portail(catalogue: Path, portail: str) -> None:
    meta = catalogue / "meta.yml"
    meta.write_text(
        meta.read_text(encoding="utf-8") + f'learning:\n  portal_url: "{portail}"\n',
        encoding="utf-8",
    )


def test_validate_structure_refuse_un_portail_en_clair(catalogue: Path) -> None:
    _declarer_portail(catalogue, "http://formation.example.org/p/")

    resultat = runner.invoke(app, ["validate-structure"])

    assert resultat.exit_code == 1
    assert "learning.portal_url" in resultat.stdout


def test_validate_structure_accepte_un_portail_sain(catalogue: Path) -> None:
    _declarer_portail(catalogue, "https://formation.example.org/p/")

    resultat = runner.invoke(app, ["validate-structure"])

    assert resultat.exit_code == 0, resultat.stdout
    assert "learning.portal_url" not in resultat.stdout


def test_un_portail_hostile_reste_invisible(catalogue: Path) -> None:
    """La raison se dit, la chaîne fautive ne se recopie pas à l'écran."""
    _declarer_portail(catalogue, "javascript:alert(document.cookie)")

    resultat = runner.invoke(app, ["validate-structure"])

    assert resultat.exit_code == 1
    assert "javascript:" not in resultat.stdout


def test_un_bloc_learning_vide_ne_dit_rien(catalogue: Path) -> None:
    """Un champ facultatif absent n'est pas une anomalie à signaler."""
    resultat = runner.invoke(app, ["validate-structure"])

    assert resultat.exit_code == 0, resultat.stdout
    assert "portal_url" not in resultat.stdout
