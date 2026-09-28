"""Le lien de remise : un affichage, jamais une transmission.

Après une tentative enregistrée, un apprenant doit pouvoir porter son résultat
au portail de son catalogue sans exporter puis importer à la main. Le mécanisme
doit rester valable quand dsoxlab tourne dans WSL, dans VirtualBox, dans une VM
distante ou dans le cloud : **un pont `localhost` ne peut donc pas en être le
moyen**. Ce qui reste valable partout, c'est un lien affiché.

D'où la forme, et chaque détail répond à une contrainte :

- un **fragment** ``#dsoxlab=<base64url>``, jamais une query string : le fragment
  reste côté navigateur, donc ni les journaux du serveur, ni ceux d'un reverse
  proxy, ni un CDN ne voient passer les résultats ;
- **base64url sans remplissage**, parce qu'un ``+``, un ``/`` ou un ``=`` ne
  traversent pas un fragment sans dommage ;
- **aucune compression** : la preuve tient en moins d'un kilo-octet, et un
  décompresseur chez le destinataire serait une surface d'attaque pour rien.

Et surtout : **dsoxlab n'envoie rien**. Pas de navigateur ouvert, pas de requête,
pas de nom résolu. Les tests qui le prouvent sont les plus importants de ce
fichier, parce que c'est la promesse qu'un lecteur du code ne peut pas vérifier
d'un coup d'œil.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.cli.progression import _proposer_la_remise
from dsoxlab.discovery.scanner import scan_catalog
from dsoxlab.security.urls import URLRefusee
from dsoxlab.services.evidence import (
    LIMITE_FRAGMENT,
    ChargeTropGrande,
    charge_utile,
    hote_du_portail,
    lien_de_remise,
)
from dsoxlab.sessions.store import record_result

runner = CliRunner()

PORTAIL = "https://formation.example.org/mon-apprentissage/"

_DOCUMENT: dict[str, Any] = {
    "schema": "dsoxlab-evidence-v1",
    "generated_at": "2026-09-28T10:00:00+00:00",
    "producer": {"name": "dsoxlab", "version": "0.3.0"},
    "catalog": {"id": "essai", "version": None},
    "results": [{"lab_id": "premier", "validated": True}],
    "count": 1,
}


@pytest.fixture
def en_anglais(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixe la langue des messages, pour pouvoir les citer dans un test.

    `dsoxlab.i18n` charge ses chaînes **une fois par processus**, dans un global
    paresseux. Un test qui vérifie un libellé sans vider ce cache mesure donc la
    langue qu'un test précédent a chargée — vert ou rouge selon l'ordre
    d'exécution, ce qui ne mesure plus rien.
    """
    import dsoxlab.i18n as i18n

    monkeypatch.setenv("DSOXLAB_LANG", "en")
    monkeypatch.setattr(i18n, "_strings", None)


def _lien_dans(sortie: str) -> str:
    """L'URL de remise, extraite de ce que la commande a affiché.

    Une expression plutôt qu'un découpage en mots : l'URL est précédée d'une
    phrase, et coller les lignes avant de découper produirait
    « résultat :https://… », qui ne commence pas par le schéma.
    """
    trouve = re.search(r"https://\S+", sortie)
    assert trouve is not None, sortie
    return trouve.group(0)


def _declarer_portail(catalogue: Path, portail: str) -> None:
    meta = catalogue / "meta.yml"
    meta.write_text(
        meta.read_text(encoding="utf-8") + f'learning:\n  portal_url: "{portail}"\n',
        encoding="utf-8",
    )


def _tentative(catalogue: Path, *, score: int = 100, passed: int = 8) -> None:
    record_result(
        catalogue,
        lab_id="premier",
        section="domaine",
        score=score,
        max_score=100,
        passed_tests=passed,
        total_tests=8,
        hints_used=0,
    )


def _lab(catalogue: Path) -> Any:
    scan = scan_catalog(catalogue, lang="en")
    return next(lab for lab in scan.labs if lab.id == "premier")


def _decoder(lien: str) -> dict[str, Any]:
    fragment = urlparse(lien).fragment
    cle, _, charge = fragment.partition("=")
    assert cle == "dsoxlab"
    return dict(json.loads(
        base64.urlsafe_b64decode(charge + "=" * (-len(charge) % 4)).decode("utf-8")
    ))


# ── l'encodage : ce que le consommateur exige ────────────────────────────────

def test_la_charge_est_du_base64url_sans_remplissage() -> None:
    """Le base64 standard est refusé côté portail, et pour de bonnes raisons.

    ``+`` et ``/`` ne traversent pas une URL sans être réencodés, et un ``=`` de
    fin se fait ronger par les outils qui recopient des liens.
    """
    charge = charge_utile(_DOCUMENT)

    assert "+" not in charge
    assert "/" not in charge
    assert "=" not in charge


def test_la_charge_se_decode_sans_perte() -> None:
    assert _decoder(lien_de_remise(PORTAIL, _DOCUMENT)) == _DOCUMENT


def test_la_charge_n_est_pas_compressee() -> None:
    """Un décompresseur chez le destinataire serait une surface d'attaque.

    Une charge pathologique se décompresse en gigaoctets, pour ne rien gagner sur
    un document de quelques centaines d'octets. Le test le prouve en décodant
    directement en UTF-8 : si la charge était compressée, ce serait illisible.
    """
    charge = charge_utile(_DOCUMENT)
    brut = base64.urlsafe_b64decode(charge + "=" * (-len(charge) % 4))

    assert brut.decode("utf-8").startswith('{"schema":')


def test_une_charge_trop_grande_est_refusee() -> None:
    """Un lien tronqué échoue chez le destinataire, longtemps après le geste."""
    enorme = {**_DOCUMENT, "results": [{"lab_id": "x" * LIMITE_FRAGMENT}]}

    with pytest.raises(ChargeTropGrande):
        charge_utile(enorme)


# ── le fragment, jamais la query ─────────────────────────────────────────────

def test_la_preuve_voyage_dans_le_fragment() -> None:
    """Une query string l'écrirait dans les journaux du serveur et du CDN."""
    parties = urlparse(lien_de_remise(PORTAIL, _DOCUMENT))

    assert parties.query == ""
    assert parties.fragment.startswith("dsoxlab=")


def test_un_fragment_declare_est_remplace() -> None:
    """Une URL n'en porte qu'un, et celui du catalogue ne dirait rien d'utile."""
    lien = lien_de_remise("https://formation.example.org/p/#ancre", _DOCUMENT)

    assert "#ancre" not in lien
    assert _decoder(lien)["count"] == 1


def test_le_chemin_du_portail_est_conserve() -> None:
    """Le portail choisit sa page ; on ne lui en impose aucune."""
    parties = urlparse(lien_de_remise(PORTAIL, _DOCUMENT))

    assert parties.path == "/mon-apprentissage/"


# ── la politique d'URL, réutilisée telle quelle ──────────────────────────────

@pytest.mark.parametrize("hostile", [
    "javascript:alert(1)",
    "http://formation.example.org/p/",
    "https://vrai.test@attaquant.test/p/",
    "data:text/html,<script>1</script>",
])
def test_un_portail_hostile_ne_donne_aucun_lien(hostile: str) -> None:
    """La même primitive que `doc_url` : #270 n'écrit pas son propre contrôle."""
    with pytest.raises(URLRefusee):
        lien_de_remise(hostile, _DOCUMENT)


def test_construire_le_lien_ne_touche_pas_au_reseau(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le handoff est strictement passif : rien n'est résolu, rien n'est appelé."""
    import socket
    import urllib.request

    def interdit(*_a: Any, **_k: Any) -> None:
        raise AssertionError("la construction du lien a touché au réseau")

    monkeypatch.setattr(socket, "socket", interdit)
    monkeypatch.setattr(socket, "create_connection", interdit)
    monkeypatch.setattr(socket, "getaddrinfo", interdit)
    monkeypatch.setattr(urllib.request, "urlopen", interdit)

    assert lien_de_remise(PORTAIL, _DOCUMENT)


# ── ce que l'apprenant voit après submit ─────────────────────────────────────

def test_sans_portail_rien_ne_s_affiche(
    catalogue: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un catalogue sans portail est un cas normal, pas une configuration
    manquante : aucun avertissement, aucune adresse par défaut."""
    _tentative(catalogue)

    _proposer_la_remise(catalogue, _lab(catalogue))

    assert capsys.readouterr().out == ""


def test_l_hote_est_nomme_a_part_du_lien(
    catalogue: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ce qu'on lit d'une URL de 600 caractères, c'est son début.

    Nommer l'hôte en clair est ce qui permet de voir **où** la preuve irait.
    """
    _declarer_portail(catalogue, PORTAIL)
    _tentative(catalogue)

    _proposer_la_remise(catalogue, _lab(catalogue))
    sortie = capsys.readouterr().out

    assert "formation.example.org" in sortie
    assert "#dsoxlab=" in sortie.replace("\n", "")


def test_le_texte_dit_que_rien_n_est_envoye(
    catalogue: Path, en_anglais: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un lien qui apparaît après un test laisse croire à une transmission."""
    _declarer_portail(catalogue, PORTAIL)
    _tentative(catalogue)

    _proposer_la_remise(catalogue, _lab(catalogue))

    assert "Nothing has been sent by dsoxlab" in capsys.readouterr().out


def test_aucun_navigateur_n_est_ouvert(
    catalogue: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L'invariant central de cette issue, et celui qu'on ne voit pas en lisant.

    L'utilisateur reste celui qui décide d'ouvrir ou de copier le lien.
    """
    import webbrowser

    ouvertures: list[object] = []
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: ouvertures.append(a))
    _declarer_portail(catalogue, PORTAIL)
    _tentative(catalogue)

    _proposer_la_remise(catalogue, _lab(catalogue))

    assert ouvertures == []


def test_le_service_de_preuve_n_ouvre_rien() -> None:
    """Le pendant statique du test ci-dessus, pour ce que le patch ne voit pas.

    `webbrowser.open` se piège ; `xdg-open`, `open` et `start` passeraient par un
    sous-processus, et `run_command` est légitimement employé ailleurs dans le
    même module (un `git rev-parse`). Piéger `subprocess` ferait donc échouer la
    remise pour une autre raison — mesuré : c'est ce qu'une première version de
    ce test faisait, et elle ne mesurait plus l'ouverture.
    """
    import ast

    chemin = (
        Path(__file__).resolve().parent.parent
        / "src" / "dsoxlab" / "services" / "evidence.py"
    )
    module = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))

    # Les docstrings de ce module parlent justement de ce qu'il ne fait pas :
    # chercher dans le texte brut attraperait sa propre explication. On regarde
    # donc ce que le module IMPORTE et les chaînes qu'il ÉVALUE.
    docstrings = {
        noeud.body[0].value
        for noeud in ast.walk(module)
        if isinstance(noeud, ast.Module | ast.FunctionDef | ast.ClassDef)
        and noeud.body
        and isinstance(noeud.body[0], ast.Expr)
        and isinstance(noeud.body[0].value, ast.Constant)
    }

    importes: set[str] = set()
    for noeud in ast.walk(module):
        if isinstance(noeud, ast.Import):
            importes |= {alias.name.split(".")[0] for alias in noeud.names}
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            importes.add(noeud.module.split(".")[0])

    litterales = {
        noeud.value
        for noeud in ast.walk(module)
        if isinstance(noeud, ast.Constant)
        and isinstance(noeud.value, str)
        and noeud not in docstrings
    }

    assert "webbrowser" not in importes, importes
    assert "subprocess" not in importes, importes
    for suspecte in litterales:
        assert "xdg-open" not in suspecte, suspecte
        assert not suspecte.startswith("open"), suspecte


def test_un_portail_hostile_dit_pourquoi_sans_le_montrer(
    catalogue: Path, en_anglais: None, capsys: pytest.CaptureFixture[str]
) -> None:
    _declarer_portail(catalogue, "javascript:alert(document.cookie)")
    _tentative(catalogue)

    _proposer_la_remise(catalogue, _lab(catalogue))
    sortie = capsys.readouterr().out

    assert "javascript:" not in sortie
    assert "#dsoxlab=" not in sortie
    assert "cannot be used" in sortie


def test_un_portail_ne_peut_pas_piloter_le_terminal(
    catalogue: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le test que l'issue réclame : aucune séquence injectée par un catalogue.

    Les crochets ne sont pas des caractères de contrôle, donc la politique d'URL
    les laisse passer — c'est l'affichage qui doit les rendre littéralement.
    """
    _declarer_portail(catalogue, "https://formation.example.org/[bold]VOLE[/bold]/")
    _tentative(catalogue)

    _proposer_la_remise(catalogue, _lab(catalogue))
    sortie = capsys.readouterr().out.replace("\n", "")

    assert "[bold]VOLE[/bold]" in sortie


def test_une_tentative_ratee_donne_aussi_un_lien(
    catalogue: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Décision documentée : le lien s'affiche aussi après un échec.

    Une preuve atteste ce qui s'est passé, et un portail en fait une file de
    révision. Ne montrer que les réussites fabriquerait une progression
    flatteuse, et l'export complet porte déjà les échecs.
    """
    _declarer_portail(catalogue, PORTAIL)
    _tentative(catalogue, score=40, passed=4)

    _proposer_la_remise(catalogue, _lab(catalogue))
    sortie = capsys.readouterr().out

    assert _decoder(_lien_dans(sortie))["results"][0]["validated"] is False


def test_le_lien_apparait_apres_un_vrai_submit(catalogue: Path) -> None:
    """Le bout en bout : branché à `submit`, pas seulement écrit à côté."""
    _declarer_portail(catalogue, PORTAIL)

    resultat = runner.invoke(app, ["submit", "premier"], env={"COLUMNS": "400"})

    assert resultat.exit_code == 0, resultat.output
    assert "formation.example.org" in resultat.output
    assert "#dsoxlab=" in resultat.output.replace("\n", "")


def test_l_hote_se_lit_seul(catalogue: Path) -> None:
    """`hote_du_portail` sert l'affichage ; il passe par la même politique."""
    assert hote_du_portail(PORTAIL) == "formation.example.org"
    with pytest.raises(URLRefusee):
        hote_du_portail("javascript:alert(1)")
