"""Quels hôtes `provision` attend après un apply, et surtout lesquels il n'attend pas.

L'output `hosts` du template dérive de `var.hosts`, donc de TOUS les hôtes
déclarés au `meta.yml`, et non de ceux que cet apply a créés. Avec `--host`,
attendre cette liste revient à réclamer une réponse à des machines qu'on a
explicitement demandé de ne pas monter : `provision` sortait en 8 à tous les
coups dès qu'un dépôt déclare plus d'un hôte, c'est-à-dire presque toujours
(issue #246).

La règle était noyée dans une fonction de 288 lignes, donc invérifiable
autrement qu'en provisionnant pour de vrai.
"""

from __future__ import annotations

from dsoxlab.cli.infrastructure import _hotes_a_attendre
from dsoxlab.infra.terraform import ProvisionResult

TOPOLOGIE = {
    "control-node.lab": "10.10.20.11",
    "web1.lab": "10.10.20.12",
    "web2.lab": "10.10.20.13",
    "db1.lab": "10.10.20.14",
}


def _resultat() -> ProvisionResult:
    return ProvisionResult(outputs={}, hosts=dict(TOPOLOGIE))


def test_sans_ciblage_on_attend_toute_la_topologie() -> None:
    assert _hotes_a_attendre(_resultat(), None) == [
        "control-node.lab", "db1.lab", "web1.lab", "web2.lab",
    ]


def test_avec_ciblage_on_n_attend_que_les_machines_demandees() -> None:
    """Le cas de l'issue #246 : attendre les trois autres faisait sortir en 8
    alors que la seule machine demandée répondait."""
    assert _hotes_a_attendre(_resultat(), ["web1.lab"]) == ["web1.lab"]


def test_un_ciblage_multiple_garde_l_ordre_stable() -> None:
    """Trié, et pas dans l'ordre de la ligne de commande : l'affichage qui
    suit doit être le même d'une exécution à l'autre."""
    attendus = _hotes_a_attendre(_resultat(), ["web2.lab", "db1.lab"])
    assert attendus == ["db1.lab", "web2.lab"]


def test_un_hote_cible_absent_de_la_topologie_n_est_pas_attendu() -> None:
    """La commande refuse déjà un `--host` inconnu en amont. Si l'output ne le
    porte pas malgré tout, on ne va pas attendre une machine qui n'existe
    nulle part : ce serait huit minutes pour sortir en 8."""
    assert _hotes_a_attendre(_resultat(), ["fantome.lab"]) == []


def test_une_liste_de_ciblage_vide_vaut_pas_de_ciblage() -> None:
    """`--host` jamais donné arrive en liste vide selon le chemin d'appel."""
    assert len(_hotes_a_attendre(_resultat(), [])) == len(TOPOLOGIE)
