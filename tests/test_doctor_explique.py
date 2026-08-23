"""`doctor` dit ce qu'il ne trouve pas, au lieu d'un « 0 lab » muet (#132).

`list-labs` explique très bien : il nomme le fichier, la version et la commande
qui répare. `doctor` affichait « ✘ KO — 0 lab » sans un mot, alors que c'est lui
qu'on lance quand quelque chose cloche, et lui qu'on colle dans un rapport de
bug.

Trois causes rendent un lab invisible : un `schema_version` trop récent, un
`lab.yaml` qui lève au parsing, ou un lab déclaré au `meta.yml` mais absent du
disque. Plutôt que de deviner laquelle s'applique, le contrôle compare les
fichiers présents aux labs chargés : l'écart les couvre toutes les trois.
"""

from __future__ import annotations

from pathlib import Path

from dsoxlab.discovery.scanner import compter_fichiers_labs, scan_catalog

LAB = """id: {ident}
title: Lab {ident}
level: beginner
skills: [demo]
distros: [any]
doc_url: https://example.invalid/doc
runtime:
  type: shell
  workdir: challenge/work
"""


def _catalogue(racine: Path, *, sains: int = 1, casses: int = 0) -> Path:
    (racine / "meta.yml").write_text(
        "repo:\n  id: essai\n  category: demo\n", encoding="utf-8"
    )
    for i in range(sains):
        d = racine / "labs" / "demo" / f"bon{i}"
        d.mkdir(parents=True)
        (d / "lab.yaml").write_text(LAB.format(ident=f"bon{i}"), encoding="utf-8")
    for i in range(casses):
        d = racine / "labs" / "demo" / f"casse{i}"
        d.mkdir(parents=True)
        # Sans `level`, le parseur lève : c'est un champ requis du contrat.
        (d / "lab.yaml").write_text(
            LAB.format(ident=f"casse{i}").replace("level: beginner\n", ""),
            encoding="utf-8",
        )
    return racine


def test_le_compte_couvre_les_fichiers_illisibles(tmp_path: Path) -> None:
    """C'est l'écart qui porte l'information, pas le nombre de labs chargés."""
    racine = _catalogue(tmp_path, sains=2, casses=1)

    assert compter_fichiers_labs(racine) == 3
    assert len(scan_catalog(racine).labs) == 2


def test_un_fichier_qui_leve_est_retenu_et_nomme(tmp_path: Path) -> None:
    """Il n'allait qu'au journal, que rien n'affiche : le lab disparaissait
    alors sans laisser de trace exploitable."""
    racine = _catalogue(tmp_path, sains=1, casses=1)

    scan = scan_catalog(racine)

    assert len(scan.illisibles) == 1
    chemin, raison = scan.illisibles[0]
    assert chemin.name == "lab.yaml"
    assert "casse0" in str(chemin)
    assert raison, "la raison ne doit pas être vide"


def test_un_catalogue_sain_ne_signale_aucun_ecart(tmp_path: Path) -> None:
    """Le contre-exemple : sans lui, un contrôle qui crie toujours ne dit rien."""
    racine = _catalogue(tmp_path, sains=3)

    assert compter_fichiers_labs(racine) == len(scan_catalog(racine).labs) == 3
    assert scan_catalog(racine).illisibles == []


def test_le_comptage_voit_les_anciens_depots_en_tp(tmp_path: Path) -> None:
    """La règle de recherche est celle du scanner, pas une seconde définition.

    Un premier jet comptait sous `labs/` seulement, et ignorait les `tp-*/` que
    le scanner accepte pour les anciens dépôts : deux définitions de « où sont
    les labs » qui divergeaient déjà.
    """
    (tmp_path / "meta.yml").write_text(
        "repo:\n  id: essai\n  category: demo\n", encoding="utf-8"
    )
    ancien = tmp_path / "tp-01"
    ancien.mkdir()
    (ancien / "lab.yaml").write_text(LAB.format(ident="ancien"), encoding="utf-8")

    assert compter_fichiers_labs(tmp_path) == 1
