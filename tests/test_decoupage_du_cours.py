"""Un cours sans `course.yaml` se découpe-t-il correctement ?

Le contrat prévoit un `course.yaml` pour servir un cours section par section.
**Aucun catalogue ne l'écrit** : mesuré le 2026-10-16, 0 sur les 310 labs des
cinq catalogues présents. `course` affichait donc `scenario.md` + `README.md`
d'un bloc, soit une médiane de 363 lignes sur `linux-dsoxlab-training` et un
maximum de 1 080.

Le découpage est maintenant déduit des titres que les documents portent déjà.
Deux choses s'éprouvent ici, et la seconde est la plus importante :

1. le **choix du niveau** de titre, qui ne peut pas être fixe : `ansible` met
   15 titres de niveau 2 par lab, `linux` en met deux et cache son cours sous
   sept titres de niveau 3 ;
2. le fait que **rien ne se perde**. Une première version écartait le texte
   précédant le premier titre comme un simple en-tête : sur `linux`, cela
   jetait le contenu de « ## Rappel » et l'introduction du cours, vingt-six
   lignes qui n'apparaissaient plus nulle part. Une capture l'a montré, pas une
   mesure.
"""

from __future__ import annotations

from pathlib import Path

from dsoxlab.services.course_service import (
    LIGNES_MAX,
    choisir_decoupage,
    decouper,
    manifeste_automatique,
)

# Le cas `ansible` : des titres de niveau 2, nombreux et courts.
NIVEAU_2 = """# Titre du lab

## Premier point

Du texte.

## Deuxième point

Du texte aussi.

## Troisième point

Encore.
"""

# Le cas `linux` : deux titres de niveau 2, le cours sous des niveaux 3.
NIVEAU_3 = (
    "# Titre du lab\n\n## Rappel\n\nUn rappel utile.\n\n## Le cours\n\n"
    "Une introduction au cours.\n\n"
    + "".join(
        f"### Sous-partie {i}\n\n" + "Du contenu.\n" * 30 + "\n" for i in range(1, 5)
    )
)


class TestChoixDuNiveau:
    def test_des_titres_de_niveau_2_suffisants_sont_retenus(self) -> None:
        decoupe = choisir_decoupage(NIVEAU_2)
        assert [titre for titre, _corps in decoupe] == [
            "Premier point",
            "Deuxième point",
            "Troisième point",
        ]

    def test_le_niveau_3_est_retenu_quand_le_niveau_2_donne_des_pavés(self) -> None:
        """Le cas qui interdit un niveau fixe.

        Au niveau 2, ce document donne deux sections dont une de plus de cent
        lignes : c'est le défaut qu'on voulait corriger, pas sa correction.
        """
        decoupe = choisir_decoupage(NIVEAU_3)
        titres = [titre for titre, _corps in decoupe]
        assert "Sous-partie 1" in titres
        assert "Le cours" not in titres, "le niveau 2 ne doit pas avoir été retenu"

    def test_un_document_sans_titre_ne_se_decoupe_pas(self) -> None:
        assert choisir_decoupage("Juste du texte, sans aucun titre.\n") == []

    def test_un_titre_dans_un_bloc_de_code_nest_pas_un_titre(self) -> None:
        """`## quelque chose` entre deux ``` est un commentaire shell.

        Découper dessus couperait le cours au milieu d'un exemple.
        """
        texte = (
            "# Lab\n\n## Vraie section\n\nTexte.\n\n"
            "```bash\n## ceci est un commentaire\necho bonjour\n```\n\n"
            "## Autre vraie section\n\nTexte.\n"
        )
        titres = [titre for titre, _corps in decouper(texte, 2)]
        assert titres == ["Vraie section", "Autre vraie section"]


class TestRienNeSePerd:
    def test_le_preambule_devient_une_section(self) -> None:
        """Le défaut qu'une capture a montré et qu'aucune mesure n'a vu."""
        decoupe = choisir_decoupage(NIVEAU_3)
        tout = "\n".join(corps for _titre, corps in decoupe)
        assert "Un rappel utile." in tout
        assert "Une introduction au cours." in tout

    def test_aucune_ligne_de_contenu_ne_disparait(self) -> None:
        """Comptage strict : ce qui entre dans le découpage en ressort."""
        decoupe = decouper(NIVEAU_2, 2)
        rendu = {
            ligne.strip()
            for _titre, corps in decoupe
            for ligne in corps.splitlines()
            if ligne.strip()
        }
        attendu = {
            ligne.strip()
            for ligne in NIVEAU_2.splitlines()
            if ligne.strip() and not ligne.startswith("#")
        }
        assert attendu <= rendu

    def test_un_preambule_vide_ne_cree_pas_de_section_fantome(self) -> None:
        texte = "## Direct\n\nDu texte.\n"
        assert [titre for titre, _c in decouper(texte, 2)] == ["Direct"]


class TestManifesteDeduit:
    def test_les_identifiants_sont_courts_et_uniques(self, tmp_path: Path) -> None:
        """Un identifiant se tape : `--section pwd-cd-se-situer`.

        Couper au caractère donnait « contexte-construire-une-arborescence-a-l »,
        tronqué au milieu d'un mot.
        """
        (tmp_path / "README.md").write_text(NIVEAU_2, encoding="utf-8")
        manifeste = manifeste_automatique(tmp_path, "Titre")

        assert manifeste is not None
        identifiants = [s.id for s in manifeste.sections]
        assert len(identifiants) == len(set(identifiants)), "unicité"
        assert all(len(i) <= 40 for i in identifiants)
        assert all(" " not in i for i in identifiants)

    def test_les_sections_portent_leur_texte_et_pas_un_fichier(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text(NIVEAU_2, encoding="utf-8")
        manifeste = manifeste_automatique(tmp_path, "Titre")

        assert manifeste is not None
        assert manifeste.automatique is True
        for section in manifeste.sections:
            assert section.contenu, "une section déduite porte son texte"
            assert section.file == "", "il n'y a aucun fichier à pointer"

    def test_un_lab_sans_document_ne_rend_rien(self, tmp_path: Path) -> None:
        assert manifeste_automatique(tmp_path, "Titre") is None

    def test_un_document_dune_seule_section_ne_rend_rien(self, tmp_path: Path) -> None:
        """Une seule section n'est pas un découpage : autant afficher le bloc."""
        (tmp_path / "README.md").write_text("# Lab\n\n## Unique\n\nTexte.\n", encoding="utf-8")
        assert manifeste_automatique(tmp_path, "Titre") is None

    def test_le_francais_est_prefere_quand_il_existe(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(NIVEAU_2, encoding="utf-8")
        (tmp_path / "README.fr.md").write_text(
            "# Lab\n\n## Un\n\nEn français.\n\n## Deux\n\nAussi.\n\n## Trois\n\nEt.\n",
            encoding="utf-8",
        )
        manifeste = manifeste_automatique(tmp_path, "Titre", lang="fr")

        assert manifeste is not None
        assert "En français." in (manifeste.sections[0].contenu or "")

    def test_le_seuil_de_taille_est_celui_du_module(self) -> None:
        """Le seuil vaut deux écrans de terminal, et il est déclaré, pas deviné."""
        assert 40 <= LIGNES_MAX <= 80
