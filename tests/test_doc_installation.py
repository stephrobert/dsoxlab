"""La doc d'installation dit les commandes de la table des remèdes, mot pour mot.

Décision 5 du 2026-11-16 : la doc d'installation et le diagnostic donnent les
mêmes commandes, avec ``sudo`` partout. Avant, la doc annonçait que ``--fix``
ne connaissait qu'apt et que Terraform se réduisait à un lien, alors que le
diagnostic, lui, avait changé. Ce test part de la table, pas de la doc : une
commande ajoutée ou corrigée dans la table et oubliée ici le fait échouer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.services.doctor_controles import remedes

DOCS = Path(__file__).resolve().parent.parent / "docs"

#: Les deux familles que dsoxlab éprouve, et dont la doc donne les commandes.
FAMILLES = {
    "ubuntu": "ID=ubuntu\nID_LIKE=debian\n",
    "almalinux": 'ID="almalinux"\nID_LIKE="rhel centos fedora"\n',
}


def _lignes(tmp_path: Path, contenu: str) -> list[tuple[str, str]]:
    fichier = tmp_path / "os-release"
    fichier.write_text(contenu, encoding="utf-8")
    systeme = remedes.systeme(fichier)
    lignes = []
    for cle in remedes.TABLE:
        remede = remedes.remede(cle, systeme)
        if remede is not None:
            lignes.extend((cle, ligne) for ligne in remede.lignes)
    return lignes


@pytest.mark.parametrize("page", ["learner.md", "learner.fr.md"])
@pytest.mark.parametrize("famille", list(FAMILLES))
def test_chaque_commande_de_la_table_est_dans_la_doc(
    tmp_path: Path, page: str, famille: str,
) -> None:
    texte = (DOCS / page).read_text(encoding="utf-8")
    absentes = [
        f"{cle}: {ligne}" for cle, ligne in _lignes(tmp_path, FAMILLES[famille])
        if ligne not in texte
    ]
    assert absentes == [], f"{page} ne dit pas ces commandes de la table ({famille})"


@pytest.mark.parametrize("page", ["learner.md", "learner.fr.md"])
def test_la_doc_ne_promet_plus_un_lien_a_la_place_d_une_commande(page: str) -> None:
    texte = (DOCS / page).read_text(encoding="utf-8")
    assert "developer.hashicorp.com/terraform/install" not in texte
    assert "sed -i '1i Include" not in texte
