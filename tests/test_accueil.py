"""L'accueil de `dsoxlab` sans argument : ce qu'il propose, et à qui.

`dsoxlab` seul affichait l'aide de Typer — vingt-cinq commandes alignées, sans
indication du premier geste. Pour qui ouvre le terminal de l'appliance et tape
le seul mot qu'il connaisse, c'est un mur.

Ce qui est éprouvé ici est la DÉCISION, pas la mise en forme : quels gestes
proposer selon l'état de la machine, et quels catalogues restent à poser. Lire
la sortie Rich mesurerait la largeur du terminal et les couleurs ; on interroge
donc les deux fonctions pures qui portent le raisonnement.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from dsoxlab.i18n.strings import en, fr
from dsoxlab.reporting.console import (
    _ACCUEIL_PARCOURS,
    _ACCUEIL_PRET,
    _ACCUEIL_SANS_CATALOGUE,
    catalogues_restants,
    gestes_pour,
)

#: Un manifeste réduit, de la forme que `lire_manifeste()` rend :
#: (identifiant, description, dépôt).
CONNUS = [
    ("linux", "Administration Linux", "https://github.com/stephrobert/linux-dsoxlab-training"),
    ("ansible", "Ansible", "https://github.com/stephrobert/ansible-training"),
    ("python", "Python", "https://github.com/stephrobert/python-dsoxlab-training"),
]


def _commandes(entrees: tuple[tuple[str, str], ...]) -> list[str]:
    return [commande for commande, _cle in entrees]


@contextmanager
def _dans(repertoire: Path) -> Iterator[None]:
    """Joue le bloc depuis ce répertoire, et revient toujours au précédent.

    `_machines_a_monter()` lit le catalogue du répertoire courant : le lui
    changer est la seule façon de l'éprouver, et le laisser changé ferait
    échouer les tests suivants dans un ordre imprévisible.
    """
    avant = Path.cwd()
    os.chdir(repertoire)
    try:
        yield
    finally:
        os.chdir(avant)


# ── La décision : quel geste pour quel état ─────────────────────────────────


def test_sans_catalogue_on_propose_d_en_installer_un() -> None:
    """Proposer « start » à qui n'a aucun catalogue ne l'avance pas."""
    commandes = _commandes(gestes_pour(installes=[], actif=None))
    assert any(c.startswith("dsoxlab catalog add") for c in commandes)
    assert not any("start" in c for c in commandes)


def test_avec_des_catalogues_mais_aucun_actif_on_propose_d_en_choisir_un() -> None:
    """Et la commande porte le nom d'un catalogue RÉELLEMENT installé.

    Proposer `catalog use linux` à qui n'a installé que `python` serait un
    conseil faux, que l'utilisateur jouerait avant de découvrir qu'il échoue.
    """
    commandes = _commandes(gestes_pour(installes=["python"], actif=None))
    assert "dsoxlab catalog use python" in commandes


def test_pret_a_jouer_on_propose_de_jouer() -> None:
    commandes = _commandes(gestes_pour(installes=["linux"], actif="linux"))
    assert "dsoxlab list-labs" in commandes
    assert "dsoxlab start <lab>" in commandes
    assert not any("catalog add" in c for c in commandes)


@pytest.mark.parametrize(
    ("installes", "actif"),
    [([], None), (["linux"], None), (["linux"], "linux")],
)
def test_doctor_est_proposé_dans_tous_les_états(installes: list[str], actif: str | None) -> None:
    """Quel que soit l'état : savoir ce que la machine peut faire vaut toujours."""
    assert "dsoxlab doctor" in _commandes(gestes_pour(installes=installes, actif=actif))


# ── Les catalogues restants ─────────────────────────────────────────────────


def test_un_catalogue_installe_par_son_nom_ne_reste_pas_installable() -> None:
    restants = catalogues_restants(CONNUS, installes=["linux"], depots_installes=[])
    assert "linux" not in [cle for cle, _d in restants]
    assert "ansible" in [cle for cle, _d in restants]


def test_un_catalogue_installe_par_son_URL_ne_reste_pas_installable() -> None:
    """Le défaut mesuré : `catalog add <url>` nomme le catalogue d'après l'URL.

    Sur une machine réelle, `kubernetes-dsoxlab-training` était installé et
    `kubernetes` s'affichait encore comme restant à poser. La comparaison porte
    donc sur l'URL, qui ne dépend pas de la façon dont il a été installé.
    """
    restants = catalogues_restants(
        CONNUS,
        installes=["linux-dsoxlab-training"],
        depots_installes=["https://github.com/stephrobert/linux-dsoxlab-training"],
    )
    assert "linux" not in [cle for cle, _d in restants]


@pytest.mark.parametrize(
    "variante",
    [
        "https://github.com/stephrobert/linux-dsoxlab-training",
        "https://github.com/stephrobert/linux-dsoxlab-training/",
        "https://github.com/stephrobert/linux-dsoxlab-training.git",
    ],
)
def test_les_formes_d_une_meme_URL_valent_la_meme_chose(variante: str) -> None:
    """Un `.git` ou une barre finale ne font pas un autre dépôt."""
    restants = catalogues_restants(CONNUS, installes=[], depots_installes=[variante])
    assert "linux" not in [cle for cle, _d in restants]


def test_tout_installe_ne_laisse_rien_a_proposer() -> None:
    """Lister des catalogues déjà posés serait du bruit."""
    assert catalogues_restants(
        CONNUS, installes=["linux", "ansible", "python"], depots_installes=[]
    ) == []


# ── Les clés, dans les deux langues ─────────────────────────────────────────


def test_chaque_commande_proposee_porte_un_libelle_traduit_des_deux_cotes() -> None:
    """Une clé posée d'un seul côté afficherait un libellé vide dans l'autre langue.

    Le garde-fou i18n vérifie qu'aucune phrase n'est écrite en dur ; il ne dit
    rien des clés oubliées dans un seul fichier. C'est ce que ce test couvre.
    """
    cles = {
        cle
        for entrees in (
            _ACCUEIL_SANS_CATALOGUE,
            _ACCUEIL_PRET,
            _ACCUEIL_PARCOURS,
        )
        for _commande, cle in entrees
    }
    manquantes_en = sorted(c for c in cles if c not in en.STRINGS)
    manquantes_fr = sorted(c for c in cles if c not in fr.STRINGS)
    assert not manquantes_en, f"absentes de en.py : {manquantes_en}"
    assert not manquantes_fr, f"absentes de fr.py : {manquantes_fr}"


def test_aucune_commande_de_l_accueil_n_est_traduite() -> None:
    """Une commande s'écrit pareil dans toutes les langues.

    Elle vit donc dans une donnée, et jamais dans les tables de traduction —
    sans quoi une version française proposerait des commandes introuvables.
    """
    commandes = {
        commande
        for entrees in (_ACCUEIL_SANS_CATALOGUE, _ACCUEIL_PRET, _ACCUEIL_PARCOURS)
        for commande, _cle in entrees
    }
    for table, nom in ((en.STRINGS, "en"), (fr.STRINGS, "fr")):
        fautives = sorted(c for c in commandes if c in table.values())
        assert not fautives, f"{nom}.py traduit des commandes : {fautives}"


# ── Le premier contact : ce qu'on montre à qui ne connaît pas l'outil ───────


def test_le_premier_geste_propose_est_la_demonstration() -> None:
    """L'ordre compte : `demo` avant `catalog add`.

    Quelqu'un qui ne connaît pas l'outil n'a pas à choisir une formation parmi
    six avant d'avoir vu à quoi ressemble un lab. `demo` ne clone rien, ne
    provisionne rien, et tient en cinq minutes.
    """
    commandes = _commandes(gestes_pour(installes=[], actif=None))
    assert commandes[0] == "dsoxlab demo"


def test_un_catalogue_sans_machines_ne_declenche_pas_le_bloc_infra(
    tmp_path: Path,
) -> None:
    """Le bloc qui nomme provider, hyperviseur et provision n'est pas pour tout
    le monde : il était montré même à qui n'avait rien installé."""
    from dsoxlab.cli._amorcage import _machines_a_monter

    (tmp_path / "meta.yml").write_text(
        "repo:\n  id: sans-machines\n  category: python\n", encoding="utf-8"
    )
    with _dans(tmp_path):
        assert _machines_a_monter() is False


def test_un_catalogue_a_machines_declenche_le_bloc_infra(tmp_path: Path) -> None:
    """Le critère est celui de `doctor` depuis la 0.1.88 : `infra.hosts` non vide.

    Deux écrans qui décideraient différemment de ce qu'est un catalogue « à
    machines » finiraient par se contredire.
    """
    from dsoxlab.cli._amorcage import _machines_a_monter

    (tmp_path / "meta.yml").write_text(
        "repo:\n  id: avec-machines\n  category: linux\n"
        "infra:\n  provider: kvm\n  hosts:\n    - name: web1.lab\n",
        encoding="utf-8",
    )
    with _dans(tmp_path):
        assert _machines_a_monter() is True


def test_un_repertoire_sans_catalogue_ne_declenche_rien(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un accueil ne doit jamais être ce qui casse : sans catalogue, il se taît.

    Le `XDG_STATE_HOME` est isolé, et ce n'est pas une précaution de forme :
    `_machines_a_monter()` interroge `get_lab_home()`, qui suit le **catalogue
    actif** de la machine avant le répertoire courant. Sans cette isolation, le
    test lisait le catalogue réellement actif du poste et passait ou échouait
    selon ce qu'un développeur y avait laissé.
    """
    from dsoxlab.cli._amorcage import _machines_a_monter

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("LAB_HOME", raising=False)
    with _dans(tmp_path):
        assert _machines_a_monter() is False


def test_un_catalogue_actif_hors_de_catalogs_compte_quand_meme() -> None:
    """`demo` pose son catalogue ailleurs, et il est actif : l'accueil le voit.

    Le défaut se voyait en jouant le parcours : juste après `dsoxlab demo`,
    l'accueil annonçait « Aucun catalogue installé pour l'instant » et
    proposait `dsoxlab demo` à qui venait de le faire. `installes` ne liste que
    `catalogs/`, et la démonstration vit sous `share/dsoxlab/demo`.
    """
    commandes = _commandes(gestes_pour(installes=[], actif="demo"))
    assert "dsoxlab list-labs" in commandes
    assert not any(c == "dsoxlab demo" for c in commandes)
