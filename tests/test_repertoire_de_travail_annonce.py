"""Le répertoire de travail annoncé doit être celui où le travail compte.

`challenge` affichait `<lab>/challenge` en dur sous l'intitulé « Répertoire de
travail », alors que le travail se fait dans `<lab>/<runtime.workdir>`. Un
apprenant a suivi cette ligne, l'a croisée avec un énoncé qui dit
« reponses/cours.txt », et a conclu `challenge/reponses/`. Une demi-heure perdue
sur son premier lab, en suivant l'outil à la lettre (issue #237).

Mesuré sur le lab de démonstration : les trois mêmes fichiers valent **0/100** à
la racine du catalogue et **100/100** sous le workdir. La ligne ne se contentait
donc pas d'être imprécise, elle désignait un endroit où rien n'est lu.

Le chemin vient désormais du contrat. Les 133 labs `shell` des quatre catalogues
déclarent aujourd'hui `challenge/work`, mais c'est une déclaration, pas une
garantie : rien dans le contrat n'impose cette valeur, et le moteur n'a pas à la
supposer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType, Target
from dsoxlab.reporting.console import console, print_lab_challenge


def _lab(chemin: Path, *, workdir: str) -> LabDefinition:
    return LabDefinition(
        id="demo",
        title="Demo",
        level="l1",
        path=chemin,
        doc_url="https://example.test/guide",
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir=workdir),
        skills=["x"],
        distros=["debian13"],
        validation=ValidationConfig(),
    )


def _lab_vm(chemin: Path) -> LabDefinition:
    return LabDefinition(
        id="demo-vm",
        title="Demo VM",
        level="l1",
        path=chemin,
        doc_url="https://example.test/guide",
        runtime=RuntimeConfig(
            type=RuntimeType.VM, targets=[Target(name="rhel", host="n1.lab")]
        ),
        skills=["x"],
        distros=["alma10"],
        validation=ValidationConfig(),
    )


def _poser_challenge(racine: Path) -> None:
    dossier = racine / "challenge"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "README.md").write_text("# Challenge\n\nFais le travail.\n", encoding="utf-8")


def _rendu(lab: LabDefinition, lang: str = "en") -> str:
    """Le rendu de CE challenge, et de rien d'autre.

    On passe par `console.capture()`, l'API de Rich, et non par `capsys` : Rich
    accumule dans son propre tampon avant d'écrire sur la sortie, si bien que
    `capsys` rendait ici le rendu du test précédent. Le défaut ne se voyait pas en
    lançant le test seul, seulement dans la suite complète, ce qui en fait le pire
    des deux.
    """
    with console.capture() as capture:
        print_lab_challenge(lab, lang)
    return capture.get()


@pytest.mark.parametrize("workdir", ["challenge/work", "exercice", "tp/etape-1"])
def test_le_workdir_declare_est_celui_qui_est_annonce(
    tmp_path: Path, workdir: str
) -> None:
    """Trois valeurs, dont deux qu'aucun catalogue n'emploie aujourd'hui.

    C'est le sens du test : le contrat les autorise, donc le moteur doit les
    suivre sans que personne ait à y repasser.
    """
    _poser_challenge(tmp_path)

    sortie = _rendu(_lab(tmp_path, workdir=workdir)).replace("\n", "")

    assert workdir.replace("/", "") in sortie.replace("/", "")


def test_le_repertoire_annonce_n_est_plus_challenge_en_dur(
    tmp_path: Path
) -> None:
    """La régression exacte de #237, celle qui désignait un endroit vide."""
    _poser_challenge(tmp_path)

    sortie = _rendu(_lab(tmp_path, workdir="challenge/work")).replace("\n", "")

    # Rich coupe les longs chemins : on cherche la fin du chemin, pas sa totalité.
    assert "work" in sortie


def test_un_lab_vm_n_annonce_aucun_repertoire_local(
    tmp_path: Path
) -> None:
    """Il n'en a pas : son travail se fait sur la machine.

    Mieux vaut ne rien annoncer que de désigner un chemin où il n'y a rien à
    faire, ce que l'ancien code faisait pour tous les labs `vm`.
    """
    _poser_challenge(tmp_path)

    assert "Working directory" not in _rendu(_lab_vm(tmp_path))


def _challenge_demo() -> Path:
    import dsoxlab

    return (
        Path(dsoxlab.__file__).parent
        / "templates" / "demo" / "labs" / "demo" / "premiers-pas" / "challenge"
    )


def test_l_enonce_de_la_demo_ne_code_aucun_chemin() -> None:
    """Un énoncé qui écrit `challenge/work` recréerait le défaut ailleurs.

    Chaque catalogue déclare son propre `runtime.workdir` ; l'énoncé doit donc
    renvoyer à ce que le moteur annonce, et donner des chemins relatifs.
    """
    for nom in ("README.md", "README.fr.md"):
        texte = (_challenge_demo() / nom).read_text(encoding="utf-8")
        assert "challenge/work" not in texte, f"{nom} code le workdir en dur"
        assert "reponses/cours.txt" in texte, f"{nom} doit garder les chemins relatifs"


def test_l_enonce_de_la_demo_cite_les_fichiers_que_son_test_lit() -> None:
    """Le garde-fou qui manquait vraiment (issue #237).

    Le lab de démonstration est déjà joué à chaque livraison, jusqu'au 100/100,
    par `tests_e2e/test_parcours.py`. Ce test-là demande le workdir à la CLI et
    pose les fichiers au bon endroit : il prouve que le lab **est jouable**, pas
    que son énoncé **mène à le jouer**. C'est par ce trou que #237 est passé.

    On confronte donc les deux surfaces : tout fichier que `test_functional.py`
    lit doit être cité dans l'énoncé, dans les deux langues. Renommer l'un sans
    l'autre fait échouer la suite.
    """
    import ast

    source = (_challenge_demo() / "tests" / "test_functional.py").read_text(
        encoding="utf-8"
    )
    attendus: set[str] = set()
    for noeud in ast.walk(ast.parse(source)):
        if not isinstance(noeud, ast.Assign):
            continue
        cibles = [c.id for c in noeud.targets if isinstance(c, ast.Name)]
        if "ATTENDUS" not in cibles or not isinstance(noeud.value, ast.Dict):
            continue
        attendus = {
            cle.value
            for cle in noeud.value.keys
            if isinstance(cle, ast.Constant) and isinstance(cle.value, str)
        }

    assert attendus, "ATTENDUS n'a pas été relu : ce contrôle ne mesurerait rien"

    for nom in ("README.md", "README.fr.md"):
        texte = (_challenge_demo() / nom).read_text(encoding="utf-8")
        manquants = [f for f in sorted(attendus) if f not in texte]
        assert not manquants, f"{nom} ne cite pas {manquants}, que le test lit pourtant"
