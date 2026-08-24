"""Découvrir, installer et retrouver un catalogue de labs (issue #78).

La séparation moteur / catalogues est une bonne décision d'architecture, mais
elle était entièrement à la charge de l'utilisateur : rien ne disait quels
catalogues existent, comment en installer un, ni où se placer pour l'utiliser.

Ce module couvre les cinq commandes et, surtout, la **résolution** : c'est elle
qui touche `get_lab_home()`, donc le chemin critique de toutes les autres
commandes. Deux invariants s'y opposent et doivent tenir ensemble :

- un catalogue installé se trouve depuis n'importe quel répertoire ;
- le répertoire courant reste prioritaire, pour qu'aucun catalogue déjà cloné
  ne cesse de fonctionner du jour où l'on en installe un autre.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dsoxlab.config import get_lab_home
from dsoxlab.services import catalog


@pytest.fixture(autouse=True)
def xdg_jetable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Un XDG jetable : aucun test ne doit écrire dans le vrai ~/.local."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("LAB_HOME", raising=False)
    return tmp_path


def _depot_git(racine: Path, *, avec_meta: bool = True) -> Path:
    """Un dépôt git local qui tient lieu de catalogue distant."""
    racine.mkdir(parents=True, exist_ok=True)
    if avec_meta:
        (racine / "meta.yml").write_text(
            "repo:\n  id: essai\n  category: essai\n", encoding="utf-8")
    else:
        (racine / "LISEZMOI.md").write_text("pas un catalogue\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(racine)], check=True, timeout=30)
    subprocess.run(["git", "-C", str(racine), "add", "-A"], check=True, timeout=30)
    subprocess.run(
        ["git", "-C", str(racine), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", "initial"],
        check=True, timeout=30,
    )
    return racine


# ── Le manifeste packagé ────────────────────────────────────────────────────

def test_le_manifeste_packagé_est_lisible() -> None:
    """Garde-fou : un manifeste illisible rendrait tous les tests suivants vides."""
    connus = catalog.lire_manifeste()
    assert connus, "le manifeste packagé doit déclarer au moins un catalogue"
    assert all(c.id and c.depot for c in connus)


def test_le_moteur_ne_code_aucun_nom_de_catalogue() -> None:
    """L'invariant du projet : la spécificité vit dans la donnée, pas dans le code.

    Le manifeste cite « linux », « ansible », « terraform » ; le code, jamais.
    Un `if identifiant == "linux"` rouvrirait le couplage que la séparation
    moteur / catalogues existe pour empêcher.
    """
    source = Path(catalog.__file__).read_text(encoding="utf-8").lower()
    for domaine in ("linux", "ansible", "kubernetes", "terraform"):
        assert domaine not in source, f"« {domaine} » est cité dans services/catalog.py"


# ── add : le cas nominal, et les deux cas que l'issue exige ─────────────────

def test_add_installe_et_rend_actif(tmp_path: Path) -> None:
    distant = _depot_git(tmp_path / "distant" / "essai-labs")

    pose = catalog.ajouter(f"file://{distant}")

    assert pose.actif
    assert (pose.racine / "meta.yml").is_file()
    assert catalog.nom_actif() == "essai-labs"


def test_add_sur_un_catalogue_deja_installe_refuse_sans_force(tmp_path: Path) -> None:
    """Le répertoire porte la progression et le travail : on ne l'écrase pas."""
    distant = _depot_git(tmp_path / "distant" / "essai-labs")
    catalog.ajouter(f"file://{distant}")

    # Une trace du travail de l'apprenant, que --force perdrait.
    (catalog.racine_catalogues() / "essai-labs" / ".dsoxlab.db").write_text(
        "progression", encoding="utf-8")

    with pytest.raises(catalog.CatalogueError) as exc:
        catalog.ajouter(f"file://{distant}")
    assert "essai-labs" in str(exc.value)
    assert (catalog.racine_catalogues() / "essai-labs" / ".dsoxlab.db").is_file()


def test_add_avec_force_reinstalle(tmp_path: Path) -> None:
    distant = _depot_git(tmp_path / "distant" / "essai-labs")
    catalog.ajouter(f"file://{distant}")
    (catalog.racine_catalogues() / "essai-labs" / ".dsoxlab.db").write_text(
        "progression", encoding="utf-8")

    catalog.ajouter(f"file://{distant}", force=True)

    assert not (catalog.racine_catalogues() / "essai-labs" / ".dsoxlab.db").exists()


@pytest.mark.parametrize(("url", "attendu"), [
    ("https://github.com/org/linux-labs", "linux-labs"),
    ("https://github.com/org/linux-labs.git", "linux-labs"),
    ("https://github.com/org/linux-labs/", "linux-labs"),
    ("git@github.com:org/Linux-Labs.git", "linux-labs"),
    ("file:///chemin/vers/essai-labs", "essai-labs"),
])
def test_l_identifiant_se_deduit_de_l_url(url: str, attendu: str) -> None:
    """Le `.git` d'une URL de clone ne doit pas devenir un nom de répertoire."""
    identifiant, depot = catalog.resoudre(url)
    assert identifiant == attendu
    assert depot == url, "l'URL est passée telle quelle à git"


def test_une_url_dont_le_segment_est_inutilisable_est_refusee() -> None:
    with pytest.raises(catalog.CatalogueError):
        catalog.resoudre("https://github.com/org/..")


def test_un_identifiant_du_manifeste_donne_son_depot() -> None:
    connu = catalog.lire_manifeste()[0]
    identifiant, depot = catalog.resoudre(connu.id)
    assert (identifiant, depot) == (connu.id, connu.depot)


def test_add_d_un_catalogue_inconnu_le_dit(tmp_path: Path) -> None:
    with pytest.raises(catalog.CatalogueError) as exc:
        catalog.ajouter("catalogue-qui-n-existe-pas")
    assert "catalogue-qui-n-existe-pas" in str(exc.value)


def test_add_d_un_depot_sans_meta_ne_laisse_rien(tmp_path: Path) -> None:
    """Un dépôt git quelconque n'est pas un catalogue, et un demi-clone non plus.

    Sans ce nettoyage, `catalog list` montrerait comme installé un répertoire
    qu'aucune commande ne sait lire.
    """
    distant = _depot_git(tmp_path / "distant" / "pas-un-catalogue", avec_meta=False)

    with pytest.raises(catalog.CatalogueError):
        catalog.ajouter(f"file://{distant}")

    assert not (catalog.racine_catalogues() / "pas-un-catalogue").exists()


# ── list, use, update, remove ───────────────────────────────────────────────

def test_list_montre_l_installe_et_marque_l_actif(tmp_path: Path) -> None:
    assert catalog.installes() == []

    premier = _depot_git(tmp_path / "distant" / "un")
    second = _depot_git(tmp_path / "distant" / "deux")
    catalog.ajouter(f"file://{premier}")
    catalog.ajouter(f"file://{second}")

    poses = {p.id: p for p in catalog.installes()}
    assert set(poses) == {"un", "deux"}
    # Le dernier installé est l'actif : c'est le geste que l'utilisateur vient
    # de faire, et celui dont il attend l'effet.
    assert poses["deux"].actif and not poses["un"].actif


def test_use_change_l_actif(tmp_path: Path) -> None:
    premier = _depot_git(tmp_path / "distant" / "un")
    second = _depot_git(tmp_path / "distant" / "deux")
    catalog.ajouter(f"file://{premier}")
    catalog.ajouter(f"file://{second}")

    catalog.definir_actif("un")

    assert catalog.nom_actif() == "un"


def test_use_sur_un_catalogue_absent_le_dit(tmp_path: Path) -> None:
    with pytest.raises(catalog.CatalogueError) as exc:
        catalog.definir_actif("jamais-installe")
    assert "jamais-installe" in str(exc.value)


def test_remove_retire_et_oublie_l_actif(tmp_path: Path) -> None:
    distant = _depot_git(tmp_path / "distant" / "essai-labs")
    catalog.ajouter(f"file://{distant}")

    catalog.retirer("essai-labs")

    assert catalog.installes() == []
    assert catalog.nom_actif() is None, (
        "un actif qui désigne un catalogue retiré doit être oublié"
    )


def test_retirer_un_catalogue_absent_le_dit(tmp_path: Path) -> None:
    with pytest.raises(catalog.CatalogueError):
        catalog.retirer("jamais-installe")


def test_update_rend_ce_que_git_a_fait(tmp_path: Path) -> None:
    distant = _depot_git(tmp_path / "distant" / "essai-labs")
    catalog.ajouter(f"file://{distant}")

    detail = catalog.mettre_a_jour("essai-labs")

    assert "up to date" in detail.lower() or detail == ""


def test_mettre_a_jour_un_catalogue_absent_le_dit(tmp_path: Path) -> None:
    with pytest.raises(catalog.CatalogueError):
        catalog.mettre_a_jour("jamais-installe")


# ── La résolution : le cœur de l'issue ──────────────────────────────────────

def test_un_catalogue_actif_est_trouve_depuis_n_importe_ou(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le critère de l'issue : plus besoin de se placer dans le répertoire."""
    distant = _depot_git(tmp_path / "distant" / "essai-labs")
    pose = catalog.ajouter(f"file://{distant}")

    ailleurs = tmp_path / "un-repertoire-quelconque"
    ailleurs.mkdir()
    monkeypatch.chdir(ailleurs)

    assert get_lab_home() == pose.racine


def test_le_repertoire_courant_reste_prioritaire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aucun catalogue déjà cloné ne cesse de fonctionner.

    L'inverse ferait qu'un `catalog add` changerait silencieusement ce que fait
    un `dsoxlab check` lancé dans un dépôt existant : un effet de bord muet, à
    distance, et sur la commande qui note le travail.
    """
    distant = _depot_git(tmp_path / "distant" / "essai-labs")
    catalog.ajouter(f"file://{distant}")

    sur_place = tmp_path / "catalogue-clone-a-la-main"
    sur_place.mkdir()
    (sur_place / "meta.yml").write_text("repo:\n  id: local\n", encoding="utf-8")
    monkeypatch.chdir(sur_place)

    assert get_lab_home() == sur_place.resolve()


def test_lab_home_reste_au_dessus_de_tout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    distant = _depot_git(tmp_path / "distant" / "essai-labs")
    catalog.ajouter(f"file://{distant}")

    force = tmp_path / "force"
    force.mkdir()
    monkeypatch.setenv("LAB_HOME", str(force))

    assert get_lab_home() == force.resolve()


def test_sans_catalogue_actif_on_retombe_sur_le_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ailleurs = tmp_path / "vide"
    ailleurs.mkdir()
    monkeypatch.chdir(ailleurs)

    assert get_lab_home() == ailleurs.resolve()


def test_un_actif_qui_ne_correspond_plus_a_rien_est_ignore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L'utilisateur a pu retirer le répertoire à la main.

    Une commande ne doit pas échouer sur un état que l'outil sait recalculer.
    """
    fichier = catalog._fichier_actif()
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text("disparu\n", encoding="utf-8")

    ailleurs = tmp_path / "vide"
    ailleurs.mkdir()
    monkeypatch.chdir(ailleurs)

    assert catalog.nom_actif() is None
    assert get_lab_home() == ailleurs.resolve()


@pytest.mark.parametrize("mauvais", ["../evade", "/absolu", "avec espace", ""])
def test_un_identifiant_ne_peut_pas_sortir_du_repertoire(
    mauvais: str,
) -> None:
    """Un identifiant sert de nom de répertoire : il ne doit rien pouvoir remonter."""
    with pytest.raises(catalog.CatalogueError):
        catalog.definir_actif(mauvais)
