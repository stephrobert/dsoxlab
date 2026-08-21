"""Le harnais de la suite E2E : construire la roue, l'installer, s'en servir.

Cette suite est une boîte noire. Elle n'importe jamais `dsoxlab` (un test le
vérifie, cf. `test_boite_noire.py`) : elle construit la distribution, l'installe
dans un environnement neuf, lance le binaire par sous-processus, et n'assère que
sur le code de retour, la sortie standard, la sortie d'erreur et les fichiers
laissés sur le disque.

**Ce qui fait la valeur du procédé, et ce qu'il faut ne pas casser.**

La roue est le sujet du test, pas un détail d'exécution. Une installation
« editable », ou un `src/` laissé sur le `sys.path`, rendrait la suite verte
tout en ne testant plus l'empaquetage : un fichier de données oublié dans la
roue, un `console_scripts` mal déclaré, un point d'entrée cassé passeraient
inaperçus, et ce sont exactement les défauts que la suite unitaire ne peut pas
voir. D'où trois précautions, toutes vérifiables :

* l'environnement d'installation est un venv créé pour l'occasion, jamais celui
  du projet (`_sans_venv()` retire `VIRTUAL_ENV` de l'appel à uv) ;
* l'environnement d'exécution est reconstruit à la main, sans `PYTHONPATH` et
  avec un `PATH` qui ne contient que le venv et le système ;
* chaque commande part d'un `HOME` neuf, avec ses répertoires XDG à lui, pour
  qu'aucun test ne lise la progression d'un autre ni celle de la machine.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

#: La racine du dépôt : le parent de cette suite. Aucun chemin personnel, et
#: rien qui suppose d'où pytest a été lancé.
DEPOT = Path(__file__).resolve().parent.parent

#: Le lab du catalogue de démonstration packagé. La suite ne le découvre pas
#: par magie : c'est celui que `dsoxlab demo` annonce, et celui qu'un
#: utilisateur joue en premier.
LAB_DEMO = "premiers-pas"

#: Ce qu'il faut produire pour résoudre ce lab, écrit ici comme un apprenant
#: l'aurait lu dans le cours, la mission et l'indice. C'est le seul endroit de
#: la suite où une réponse est connue d'avance : tout le reste passe par la CLI.
REPONSES = {
    "cours.txt": "catalogue",
    "mission.txt": "challenge",
    "indice.txt": "progression",
}

#: Large, parce qu'un runner de CI froid est lent, et fini, parce qu'une suite
#: qui pend est pire qu'une suite rouge.
DELAI = 300


def _uv() -> str:
    """Le chemin d'uv, ou un échec qui dit pourquoi.

    On ne saute pas la suite : une E2E désactivée en silence est une E2E qui
    n'existe pas. Si uv manque, c'est l'environnement qu'il faut réparer.
    """
    chemin = shutil.which("uv")
    if chemin is None:
        pytest.fail(
            "uv est introuvable. Cette suite construit la roue et l'installe "
            "avec uv, comme la CI et comme l'utilisateur qui fait "
            "`uv tool install dsoxlab`."
        )
    return chemin


def _sans_venv() -> dict[str, str]:
    """L'environnement des appels à uv, débarrassé du venv du projet.

    Sans cela, `uv venv` et `uv pip install` viseraient l'environnement actif,
    celui d'où pytest tourne : on installerait la roue par-dessus la source
    déjà présente, et la suite ne prouverait plus rien de l'empaquetage.
    """
    env = dict(os.environ)
    for variable in ("VIRTUAL_ENV", "PYTHONPATH", "UV_PROJECT_ENVIRONMENT"):
        env.pop(variable, None)
    return env


def _executer(commande: list[str]) -> subprocess.CompletedProcess[str]:
    """Une étape de préparation, qui doit réussir ou tout arrêter."""
    return subprocess.run(
        commande,
        cwd=DEPOT,
        env=_sans_venv(),
        # check=True : construire ou installer la roue n'est pas ce que la
        # suite mesure. Un échec ici est une panne du harnais, pas un verdict.
        check=True,
        capture_output=True,
        text=True,
        timeout=DELAI,
    )


@pytest.fixture(scope="session")
def roue(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """La distribution construite, celle que PyPI servirait.

    `DSOXLAB_E2E_WHEEL` permet de fournir une roue déjà construite : c'est ce
    dont une matrice de distributions a besoin pour jouer le même scénario sur
    plusieurs systèmes sans reconstruire à chaque fois.
    """
    fournie = os.environ.get("DSOXLAB_E2E_WHEEL")
    if fournie:
        chemin = Path(fournie).expanduser().resolve()
        assert chemin.is_file(), f"DSOXLAB_E2E_WHEEL pointe sur un fichier absent : {chemin}"
        return chemin

    dist = tmp_path_factory.mktemp("dist")
    _executer([_uv(), "build", "--wheel", "--out-dir", str(dist)])

    roues = sorted(dist.glob("*.whl"))
    assert len(roues) == 1, f"une roue et une seule attendue, obtenu : {roues}"
    return roues[0]


@dataclass(frozen=True)
class Installation:
    """Un dsoxlab installé comme un utilisateur l'installe."""

    #: La distribution d'où tout vient.
    roue: Path
    #: L'environnement créé pour l'occasion.
    venv: Path
    #: Le script console posé par le point d'entrée `dsoxlab`.
    binaire: Path
    #: Le `site-packages` de ce venv, pour prouver ce qui y a été posé.
    site_packages: Path


@pytest.fixture(scope="session")
def installation(roue: Path, tmp_path_factory: pytest.TempPathFactory) -> Installation:
    """Installe la roue dans un environnement neuf, et rien d'autre dedans."""
    venv = tmp_path_factory.mktemp("outil") / "venv"

    # Le même interpréteur que celui qui fait tourner pytest : la matrice de
    # versions Python de la CI garde ainsi son sens jusqu'ici.
    _executer([_uv(), "venv", "--python", sys.executable, str(venv)])
    _executer([_uv(), "pip", "install", "--python", str(venv / "bin" / "python"), str(roue)])

    paquets = sorted((venv / "lib").glob("python3.*/site-packages"))
    assert len(paquets) == 1, f"un seul site-packages attendu, obtenu : {paquets}"

    return Installation(
        roue=roue,
        venv=venv,
        binaire=venv / "bin" / "dsoxlab",
        site_packages=paquets[0],
    )


@dataclass(frozen=True)
class Poste:
    """Le poste d'un utilisateur : un HOME neuf et le binaire installé."""

    binaire: Path
    maison: Path
    #: Le répertoire neutre : pas de `meta.yml` au-dessus, donc pas de
    #: catalogue. C'est là qu'on vérifie ce que l'outil dit quand il n'a rien.
    neutre: Path
    env: dict[str, str]

    def lance(
        self, *arguments: str, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Lance `dsoxlab <arguments>` et rend le résultat brut.

        `stdin` est fermé : `dsoxlab run` ouvre un sous-shell interactif, qui
        lit une fin de fichier et rend la main aussitôt. C'est ce qui permet de
        dérouler un lab sans terminal.
        """
        return subprocess.run(
            [str(self.binaire), *arguments],
            cwd=str(cwd or self.maison),
            env=self.env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=DELAI,
            # check=False : la suite joue des parcours où l'échec est ATTENDU
            # (un lab non résolu vaut 0 et sort en 1). Ce sont les assertions
            # qui jugent, jamais subprocess.
            check=False,
        )


@pytest.fixture
def poste(installation: Installation, tmp_path: Path) -> Poste:
    """Un poste vierge par test : rien ne fuit d'un test à l'autre."""
    maison = tmp_path / "maison"
    neutre = maison / "neutre"
    for sous in (maison / ".local" / "share", maison / ".local" / "state",
                 maison / ".cache", neutre):
        sous.mkdir(parents=True, exist_ok=True)

    env = {
        # PATH reconstruit : rien de l'environnement de développement ne peut
        # servir de béquille. `PYTHONPATH` est absent par construction, ce qui
        # interdit au `src/` du dépôt de se glisser dans l'exécution.
        "PATH": f"{installation.venv / 'bin'}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(maison),
        "XDG_DATA_HOME": str(maison / ".local" / "share"),
        "XDG_STATE_HOME": str(maison / ".local" / "state"),
        "XDG_CACHE_HOME": str(maison / ".cache"),
        # Aucun appel réseau : la CI tourne derrière une politique d'egress, et
        # un avis de mise à jour n'a rien à faire dans un test.
        "DSOXLAB_NO_UPDATE_CHECK": "1",
        # Langue figée : les assertions portent sur des phrases affichées.
        "DSOXLAB_LANG": "en",
        # Rich : sans couleur et à largeur fixe, sinon un repli de ligne ferait
        # échouer une assertion sur la forme au lieu du fond.
        "NO_COLOR": "1",
        "TERM": "dumb",
        "COLUMNS": "200",
        # `run` ouvre `$SHELL` ; sans entrée, il rend la main immédiatement.
        "SHELL": "/bin/sh",
        # Le rendu porte des caractères non ASCII. Sans locale héritée, il faut
        # le dire, sinon l'écriture sur un flux redirigé lève.
        "PYTHONIOENCODING": "utf-8",
    }

    return Poste(binaire=installation.binaire, maison=maison, neutre=neutre, env=env)


@pytest.fixture
def catalogue(poste: Poste) -> Path:
    """Le catalogue de démonstration, posé par la CLI elle-même.

    C'est le premier maillon du parcours que promet le README : rien n'est
    cloné, rien n'est copié à la main, l'outil se suffit à lui-même.
    """
    resultat = poste.lance("demo")
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout

    racine = poste.maison / ".local" / "share" / "dsoxlab" / "demo"
    assert (racine / "meta.yml").is_file(), (
        "le catalogue packagé n'est pas arrivé sur le disque : signe que les "
        "fichiers de données manquent à la roue"
    )
    return racine


@pytest.fixture
def resoudre() -> Callable[[Path], None]:
    """Rend le geste de l'apprenant : écrire les réponses dans le workdir.

    Le répertoire de travail est passé par l'appelant, qui l'a lu dans la
    sortie `--json` de la CLI. La suite ne recopie donc aucun chemin du
    contrat : elle utilise celui que le programme annonce.
    """

    def _resoudre(workdir: Path) -> None:
        reponses = workdir / "reponses"
        reponses.mkdir(parents=True, exist_ok=True)
        for fichier, mot in REPONSES.items():
            (reponses / fichier).write_text(mot + "\n", encoding="utf-8")

    return _resoudre
