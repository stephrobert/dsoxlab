"""Le rapport de `support` parle une seule langue, et c'est l'anglais (#227).

Même raisonnement que pour le journal en 0.1.83, avec une condition de plus :
**ce rapport est publié**. Il se cherche mot pour mot dans un moteur de
recherche, se compare entre deux machines aux locales différentes, transporte
déjà un journal anglais — et depuis la 0.1.86, `support --issue` le dépose dans
un formulaire d'issue dont tous les libellés sont anglais. Une session
`DSOXLAB_LANG=en` obtenait pourtant un rapport français : la cohérence de la
0.1.83 s'arrêtait au milieu du fichier.

Ce que ces tests séparent, parce que tout le défaut est là :

- **les clés du document** de `collecter()` sont la sortie de `support --json`,
  donc un contrat pour les programmes. Elles sont françaises et le **restent** ;
  les renommer pour corriger un affichage casserait un consommateur sans rapport
  avec le problème ;
- **les libellés du rendu Markdown** sont anglais, et un seul chemin les produit.

La liste de mots français est reprise du garde-fou du journal : une seule
définition de « ce mot n'existe qu'en français » pour les deux règles.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from dsoxlab.services import support
from tests.test_journal_en_anglais import _MOTS_FRANCAIS

_MOT = re.compile(r"[a-zà-ÿ]+", re.IGNORECASE)

#: Les clés du document, épinglées : c'est le contrat de `support --json`, et un
#: renommage doit casser ce test plutôt que le script de quelqu'un.
_CLES_RACINE = {
    "dsoxlab", "python", "systeme", "distribution", "architecture", "shell",
    "outils", "catalogue", "etat", "journal",
}


def _rapport_complet() -> dict[str, Any]:
    """Un document qui porte **toutes** les sections, valeurs absentes comprises.

    Écrit à la main plutôt que collecté : `collecter()` dépend de la machine, et
    un test qui n'expose pas le cas `None` ne vérifierait jamais le mot rendu à
    la place.
    """
    return {
        "dsoxlab": "0.1.98",
        "python": "3.13.5 (CPython)",
        "systeme": "Linux 6.8.0",
        "distribution": "Ubuntu 24.04",
        "architecture": "x86_64",
        "shell": "unknown",
        "outils": {
            "terraform": "Terraform v1.16.1",
            "docker": "absent",
            "virsh": "present, version unreadable",
        },
        "catalogue": {
            "racine": "~/catalogue",
            "section_active": None,
            "lab_actif": None,
            "id": "demo",
            "categorie": "demo",
            "provider_actif": None,
            "providers_declares": [],
            "providers_terraform": None,
            "hotes_declares": 0,
            "labs_decouverts": 3,
            "labs_vm": 0,
            "erreur": "RuntimeError: boom",
        },
        "etat": {"xdg_state": "~/.local/state/dsoxlab", "journal": "~/x.log"},
        "journal": [],
    }


def test_le_rendu_ne_porte_aucun_mot_francais() -> None:
    """Le garde-fou principal, sur le modèle de `test_journal_en_anglais`."""
    rendu = support.en_markdown(_rapport_complet())

    fautifs = sorted({
        mot for mot in _MOT.findall(rendu) if mot.lower() in _MOTS_FRANCAIS
    })

    assert not fautifs, (
        f"le rapport de support porte des mots français : {fautifs}. "
        "Il est publié dans une issue anglaise : aucun mot ne suit la locale."
    )


def test_les_en_tetes_de_section_sont_en_anglais() -> None:
    """Les quatre sections et le bloc de journal, nommés un par un.

    Une liste explicite plutôt qu'un contrôle par mots : ce sont ces cinq
    titres-là qu'un lecteur d'issue voit en premier.
    """
    rendu = support.en_markdown(_rapport_complet())

    for titre in ("### Environment", "### External tools", "### Catalog",
                  "### Locations", "### Last log lines"):
        assert titre in rendu, f"titre absent ou non traduit : {titre}"


def test_une_valeur_absente_se_dit_en_anglais() -> None:
    """`None` devient un mot, et ce mot est publié : il ne peut pas être « aucun ».

    Le cas est fréquent — aucun lab actif, aucun provider résolu — donc c'est la
    valeur la plus visible du rapport d'un débutant.
    """
    rendu = support.en_markdown(_rapport_complet())

    assert "| active_lab | none |" in rendu
    assert "aucun" not in rendu


def test_un_journal_vide_se_dit_en_anglais() -> None:
    rapport = _rapport_complet()
    rapport["journal"] = []

    assert "_No log entry recorded._" in support.en_markdown(rapport)


def test_les_libelles_de_lignes_sont_traduits() -> None:
    """Les libellés viennent de la table, les clés du document n'ont pas bougé."""
    rendu = support.en_markdown(_rapport_complet())

    for libelle in ("| system |", "| labs_discovered |", "| declared_hosts |",
                    "| active_provider |", "| log |", "| error |"):
        assert libelle in rendu, f"libellé non traduit : {libelle}"
    # Et leurs clés françaises ne fuient pas dans le rendu.
    for cle in ("| systeme |", "| labs_decouverts |", "| hotes_declares |"):
        assert cle not in rendu


@pytest.mark.parametrize("langue", ["fr", "en", "de"])
def test_le_rendu_est_le_meme_quelle_que_soit_la_langue(
    langue: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ce qui est publié ne suit pas la locale de celui qui l'a produit.

    C'est la règle de fond : deux rapports doivent être comparables ligne à
    ligne, y compris entre deux machines qui n'affichent pas la même langue.
    """
    monkeypatch.setenv("DSOXLAB_LANG", langue)
    rapport = _rapport_complet()

    assert support.en_markdown(rapport) == support.en_markdown(rapport)
    assert "### Environment" in support.en_markdown(rapport)


def test_les_cles_du_document_machine_ne_bougent_pas() -> None:
    """Le contrat de `support --json`, épinglé.

    Corriger un affichage ne doit pas renommer une clé : c'est ce qui rendait la
    correction moins triviale qu'elle n'en avait l'air, et c'est la raison de ce
    test.
    """
    rapport = support.collecter(lignes_journal=0)

    assert set(rapport) >= _CLES_RACINE
    # Les clés françaises historiques, nommément : un renommage casse ici.
    assert "systeme" in rapport
    assert "labs_decouverts" in rapport["catalogue"] or "erreur" in rapport["catalogue"]
    assert "xdg_state" in rapport["etat"]


def test_le_document_machine_n_a_pas_de_valeur_francaise() -> None:
    """Les clés restent françaises, les **valeurs** que dsoxlab écrit non.

    `présent, version illisible` et `inconnu` étaient produits par le code, pas
    par le système : ils partaient dans le JSON comme dans le Markdown.
    """
    rapport = support.collecter(lignes_journal=0)

    valeurs = [str(v) for v in rapport["outils"].values()] + [str(rapport["shell"])]
    fautifs = sorted({
        mot for valeur in valeurs
        for mot in _MOT.findall(valeur) if mot.lower() in _MOTS_FRANCAIS
    })

    assert not fautifs, f"valeurs françaises dans le document : {fautifs}"
