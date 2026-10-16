"""Les trois garde-fous de qualité mordent-ils ?

``scripts/complexite.py``, ``scripts/code-mort.py`` et
``scripts/complexite-ecran.py`` refusent un commit. Un contrôle qui refuse doit
être éprouvé **sur ce qu'il doit refuser**, sinon il ne mesure que sa propre
existence : c'est la règle du dépôt, « un test se vérifie en le faisant échouer
quand il doit échouer ».

Chaque test ci-dessous construit donc le cas fautif et vérifie que l'outil le
voit, puis le cas légitime et vérifie qu'il se taise. Les faux positifs sont
testés aussi explicitement que les vrais : c'est **l'absence** de bruit qui
rend ces hooks tenables, et l'audit du 2026-10-16 a mesuré que vulture rendait
80 lignes de faux positifs là où ces scripts en rendent zéro.

Les scripts vivent dans ``scripts/``, qui n'est pas un paquet : ils sont chargés
par ``importlib`` depuis leur chemin, comme le fait déjà
``tests/test_check_release.py``.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

RACINE = Path(__file__).resolve().parents[1]
SCRIPTS = RACINE / "scripts"


def _charger(nom_fichier: str) -> ModuleType:
    """Charge un script de ``scripts/`` sous un nom de module propre."""
    chemin = SCRIPTS / nom_fichier
    nom = chemin.stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(nom, chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Enregistré AVANT l'exécution : les dataclasses du module résolvent leurs
    # annotations via sys.modules, et un module absent y lève un AttributeError
    # dont le message ne parle pas du tout du vrai problème.
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def complexite() -> ModuleType:
    return _charger("complexite.py")


@pytest.fixture(scope="module")
def code_mort() -> ModuleType:
    return _charger("code-mort.py")


@pytest.fixture(scope="module")
def ecran() -> ModuleType:
    return _charger("complexite-ecran.py")


class TestComplexiteCognitive:
    """La mesure voit-elle ce que la cyclomatique ne voit pas ?"""

    def test_une_fermeture_imbriquee_coute_plus_quun_if_plat(
        self, complexite: ModuleType
    ) -> None:
        """Le défaut qui a motivé ce script, réduit à son os.

        Les deux fonctions ont le même nombre de branches. Une cyclomatique les
        dirait équivalentes ; la cognitive doit dire que la seconde est pire.
        """
        plat = ast.parse(
            "def f(a, b, c):\n"
            "    if a: return 1\n"
            "    if b: return 2\n"
            "    if c: return 3\n"
            "    return 0\n"
        ).body[0]
        imbrique = ast.parse(
            "def g(a, b, c):\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                return 3\n"
            "    return 0\n"
        ).body[0]
        assert complexite.cognitive(imbrique) > complexite.cognitive(plat)

    def test_une_fonction_sans_branche_mais_a_fermetures_est_vue(
        self, complexite: ModuleType
    ) -> None:
        """Le cas ``_run_ansible_with_progress`` : zéro branche, et illisible.

        Mesuré sur le vrai module : ruff C901 disait 1. La cognitive doit
        compter ce que les fermetures emboîtées coûtent au lecteur.
        """
        source = (
            "def externe(items):\n"
            "    total = 0\n"
            "    def milieu(x):\n"
            "        def interne(y):\n"
            "            for z in y:\n"
            "                if z:\n"
            "                    total += 1\n"
            "        return interne\n"
            "    return milieu\n"
        )
        fn = ast.parse(source).body[0]
        assert complexite.cognitive(fn) > 0
        assert complexite.profondeur(fn) >= 2

    def test_la_profondeur_compte_les_with_et_les_try(
        self, complexite: ModuleType
    ) -> None:
        source = (
            "def f(p):\n"
            "    with open(p) as fichier:\n"
            "        try:\n"
            "            for ligne in fichier:\n"
            "                if ligne:\n"
            "                    pass\n"
            "        except OSError:\n"
            "            pass\n"
        )
        assert complexite.profondeur(ast.parse(source).body[0]) == 4


class TestCliquetDeComplexite:
    """Le relevé ne peut-il vraiment que descendre ?"""

    def _bloc(self, complexite: ModuleType, **valeurs: object) -> object:
        defauts = {
            "cle": "src/dsoxlab/x.py::f",
            "fichier": "src/dsoxlab/x.py",
            "ligne": 1,
            "cognitive": 10,
            "profondeur": 2,
            "lignes": 20,
        }
        return complexite.Bloc(**{**defauts, **valeurs})  # type: ignore[arg-type]

    def test_une_aggravation_fait_echouer(self, complexite: ModuleType) -> None:
        bloc = self._bloc(complexite, cognitive=25)
        ecart = complexite.comparer(
            [bloc], {"src/dsoxlab/x.py::f": {"cognitive": 21, "profondeur": 2, "lignes": 20}}
        )
        assert ecart.regresse
        assert not ecart.progresse

    def test_une_amelioration_non_enterinee_fait_echouer(self, complexite: ModuleType) -> None:
        """Et c'est voulu : une dette payée qui n'est pas enregistrée se reprend.

        Sans cela, le relevé garderait l'ancienne valeur comme plafond, et la
        complexité pourrait remonter jusqu'à elle sans qu'aucun hook ne bronche.
        """
        bloc = self._bloc(complexite, cognitive=12)
        ecart = complexite.comparer(
            [bloc], {"src/dsoxlab/x.py::f": {"cognitive": 21, "profondeur": 2, "lignes": 20}}
        )
        assert ecart.progresse
        assert not ecart.regresse

    def test_un_etat_identique_ne_dit_rien(self, complexite: ModuleType) -> None:
        bloc = self._bloc(complexite, cognitive=21)
        ecart = complexite.comparer(
            [bloc], {"src/dsoxlab/x.py::f": {"cognitive": 21, "profondeur": 2, "lignes": 20}}
        )
        assert not ecart.regresse
        assert not ecart.progresse

    def test_une_fonction_nouvelle_et_lourde_est_refusee(
        self, complexite: ModuleType
    ) -> None:
        bloc = self._bloc(complexite, cognitive=99, cle="src/dsoxlab/neuf.py::f")
        ecart = complexite.comparer([bloc], {})
        assert ecart.regresse
        assert ecart.nouveaux_hors_seuil

    def test_une_fonction_nouvelle_et_simple_passe(self, complexite: ModuleType) -> None:
        bloc = self._bloc(complexite, cognitive=3, profondeur=1, lignes=10)
        assert complexite.comparer([bloc], {}).regresse is False

    def test_le_depot_est_conforme_a_son_propre_releve(
        self, complexite: ModuleType
    ) -> None:
        """Le relevé livré décrit-il le code livré ?

        C'est le test qui attrape un relevé oublié dans un commit : sans lui, le
        hook passerait chez l'auteur et échouerait chez le relecteur.
        """
        ecart = complexite.comparer(complexite.mesurer(), complexite._charger_reference())
        assert not ecart.regresse, "relevé périmé : python3 scripts/complexite.py --figer"
        assert not ecart.progresse, "relevé périmé : python3 scripts/complexite.py --figer"


class TestCodeMort:
    """Le détecteur voit-il les morts sans accuser les vivants ?"""

    def test_une_commande_typer_nest_pas_morte(self, code_mort: ModuleType) -> None:
        """Le faux positif qui rend vulture inutilisable ici : 38 commandes.

        Elles ne sont référencées que par un décorateur, et c'est précisément ce
        que ce détecteur doit savoir.
        """
        noeud = ast.parse(
            '@app.command("status")\ndef etat_du_lab() -> None:\n    pass\n'
        ).body[0]
        assert code_mort._est_enregistre(noeud)

    def test_une_fixture_pytest_nest_pas_morte(self, code_mort: ModuleType) -> None:
        noeud = ast.parse("@pytest.fixture\ndef catalogue():\n    pass\n").body[0]
        assert code_mort._est_enregistre(noeud)

    def test_une_propriete_nest_pas_morte(self, code_mort: ModuleType) -> None:
        noeud = ast.parse("@property\ndef total(self):\n    return 1\n").body[0]
        assert code_mort._est_enregistre(noeud)

    def test_une_fonction_ordinaire_nest_pas_enregistree(
        self, code_mort: ModuleType
    ) -> None:
        """Le contre-test : sans lui, un détecteur qui dirait toujours « vivant »
        passerait les trois tests précédents."""
        noeud = ast.parse("def calculer():\n    pass\n").body[0]
        assert not code_mort._est_enregistre(noeud)

    def test_un_decorateur_inconnu_ne_protege_pas(self, code_mort: ModuleType) -> None:
        noeud = ast.parse("@mon_decorateur\ndef f():\n    pass\n").body[0]
        assert not code_mort._est_enregistre(noeud)

    def test_le_depot_na_aucun_mort_hors_du_releve(self, code_mort: ModuleType) -> None:
        """Les seuls morts tolérés sont ceux dont le relevé porte le motif."""
        tolere = code_mort._charger_reference()
        trouves = {s.cle for s in code_mort.morts()}
        nouveaux = trouves - set(tolere)
        assert not nouveaux, f"code mort non motivé : {sorted(nouveaux)}"

    def test_chaque_tolerance_porte_un_motif_ecrit(self, code_mort: ModuleType) -> None:
        """Un symbole toléré sans raison est un symbole que personne n'osera retirer."""
        for cle, motif in code_mort._charger_reference().items():
            assert "À MOTIVER" not in motif, f"{cle} est toléré sans motif écrit"
            assert len(motif) > 30, f"{cle} : le motif est trop court pour expliquer"


class TestComplexiteEcran:
    """Les sept grandeurs mesurent-elles ce qu'elles prétendent ?"""

    def test_une_troncature_est_comptee(self, ecran: ModuleType) -> None:
        lignes = ["│ automatisation-lire… │ Lire le r… │"]
        assert ecran._compter_troncatures(lignes) == 2

    def test_les_colonnes_sont_lues_sur_les_separateurs(self, ecran: ModuleType) -> None:
        lignes = ["┏━━━┳━━━┳━━━┓", "│ a │ b │ c │"]
        assert ecran._compter_colonnes(lignes) == 3

    def test_les_gestes_proposes_sont_denombres(self, ecran: ModuleType) -> None:
        lignes = [
            "  dsoxlab catalog add linux   installer un catalogue",
            "  dsoxlab demo                un lab",
            "  dsoxlab demo                (répété, compté une fois)",
        ]
        gestes = ecran._compter_gestes(lignes)
        assert gestes == ["dsoxlab catalog add", "dsoxlab demo"]

    def test_le_jargon_est_releve(self, ecran: ModuleType) -> None:
        vus = ecran._compter_jargon(["Le provider kvm exige un pool libvirt."])
        assert {"provider", "kvm", "pool", "libvirt"} <= set(vus)

    def test_un_texte_du_domaine_nest_pas_du_jargon(self, ecran: ModuleType) -> None:
        """« lab », « score », « indice » sont ce que le parcours enseigne."""
        assert ecran._compter_jargon(["Ce lab vaut 100 points, un indice coûte 5."]) == []

    def test_une_trace_pytest_est_reconnue(self, ecran: ModuleType) -> None:
        lignes = [
            "E   assert False",
            "E    +  where False = exists()",
            "FAILED tests/test_functional.py::test_x",
            "Ce qui reste à faire :",
        ]
        assert ecran._compter_traces(lignes) == 3

    def test_un_ecran_lourd_score_plus_quun_ecran_simple(self, ecran: ModuleType) -> None:
        lourd = ecran.Ecran(
            commande="list-labs",
            lignes=94,
            tronque=104,
            colonnes=8,
            gestes=0,
            jargon=0,
            traces=0,
            largeur_min=160,
            code_retour=0,
        )
        simple = ecran.Ecran(
            commande="list-labs",
            lignes=12,
            tronque=0,
            colonnes=3,
            gestes=1,
            jargon=0,
            traces=0,
            largeur_min=80,
            code_retour=0,
        )
        assert lourd.score > simple.score

    def test_un_ecran_muet_sans_geste_est_une_impasse(self, ecran: ModuleType) -> None:
        """« Aucun lab trouvé. » en rendant 0 : léger, et sans suite.

        La seule grandeur qui punit la brièveté, pour que « simplifier » ne
        puisse pas se confondre avec « se taire ».
        """
        muet = ecran.Ecran(
            commande="list-labs",
            lignes=1,
            tronque=0,
            colonnes=0,
            gestes=0,
            jargon=0,
            traces=0,
            largeur_min=80,
            code_retour=0,
            impasse=1,
        )
        assert muet.score >= ecran.POIDS["impasse"]

    def test_un_parcours_paie_ses_commandes_et_ses_cd(self, ecran: ModuleType) -> None:
        """Un ``cd`` imposé est la friction la plus chère : l'apprenant le tape."""
        vide = ecran.Parcours("x", [], cd_imposes=0)
        avec_cd = ecran.Parcours("x", [], cd_imposes=1)
        assert avec_cd.score - vide.score == ecran.POIDS["cd_imposes"]
