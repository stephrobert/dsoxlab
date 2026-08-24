"""La CI valide les templates Terraform, et rien ne peut le retirer en silence (#175).

La CI couvrait le lint, mypy, les tests unitaires, le fuzzing et une suite e2e
sur la roue installée. Mais **aucun `terraform validate`** nulle part, aucun
provisionnement, et une suite e2e qui ne joue que le lab de démonstration —
lequel est `shell`.

Les templates sont épinglés en `~> 0.9` (kvm) et `~> 0.3` (incus) : une version
mineure du provider peut casser le schéma, et **le dépôt a déjà vécu ce cas**,
les commentaires de `templates/terraform/kvm/main.tf` documentant la rupture
0.8 → 0.9. Les tests unitaires existants sur ces templates
(`test_kvm_disques_apparmor.py`, `test_cloud_init_templates.py`) sont des
assertions **textuelles** : ils vérifient qu'un fichier contient une chaîne, pas
que Terraform sait le lire.

Ce module ne rejoue pas `terraform validate` — un test qui se sauterait faute de
binaire rendrait un vert qui ne prouve rien, et c'est précisément le défaut que
tout ce lot corrige. Il garde le **job**, pour qu'on ne puisse pas le retirer, le
renommer ou lui faire oublier un provider sans qu'un test rouge le dise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

RACINE = Path(__file__).resolve().parent.parent
CI = RACINE / ".github" / "workflows" / "ci.yml"
TEMPLATES = RACINE / "src" / "dsoxlab" / "templates" / "terraform"


def _workflow() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def _job() -> dict:
    jobs = _workflow()["jobs"]
    assert "terraform" in jobs, (
        "le job qui valide les templates a disparu de la CI ; sans lui, une "
        "régression de template se découvre chez un apprenant"
    )
    return jobs["terraform"]


def _script_de_validation() -> str:
    return "\n".join(
        etape.get("run", "") for etape in _job()["steps"] if "run" in etape
    )


# ── Le job existe et couvre tout ce qui est packagé ─────────────────────────

def test_la_ci_porte_un_job_de_validation_terraform() -> None:
    assert _job()["steps"], "le job existe mais ne fait rien"


def test_les_providers_packages_sont_tous_valides() -> None:
    """Le critère qui compte : ajouter un provider sans l'ajouter au job serait
    livrer du Terraform que rien n'a jamais lu.

    La liste est dérivée du disque, pas écrite à la main : un quatrième provider
    fait rougir ce test tant qu'il n'est pas couvert.
    """
    packages = sorted(
        chemin.name for chemin in TEMPLATES.iterdir()
        if chemin.is_dir() and any(chemin.glob("*.tf"))
    )
    script = _script_de_validation()

    manquants = [p for p in packages if p not in script]
    assert manquants == [], (
        f"providers packagés mais absents du job CI : {manquants}"
    )
    assert len(packages) >= 3, f"lecture du disque trop maigre : {packages}"


def test_le_job_joue_init_puis_validate() -> None:
    """`validate` seul échouerait sur les providers non téléchargés."""
    script = _script_de_validation()

    assert "terraform" in script and "init" in script and "validate" in script
    assert "-backend=false" in script, (
        "le backend n'a pas à être initialisé pour valider une configuration"
    )


def test_le_job_valide_en_place() -> None:
    """`-chdir` plutôt qu'une copie, et ce n'est pas un détail de style.

    Le template outscale atteint son cloud-init par
    `${path.module}/../../cloud-init/`. Copier les seuls `.tf` dans un
    répertoire isolé casse ce chemin et fait échouer un template parfaitement
    valide — un faux rouge, rencontré en écrivant ce job.
    """
    assert "-chdir=" in _script_de_validation()


def test_le_job_nomme_le_provider_en_echec() -> None:
    """Sinon il faut relire tout un journal pour savoir lequel des trois."""
    script = _script_de_validation()

    assert "::error::" in script
    assert "broken" in script, "le job doit collecter les échecs, pas s'arrêter au premier"


# ── Le job est un portail, pas un rapport ───────────────────────────────────

def test_le_job_bloque_la_ci() -> None:
    """Un job qui sort toujours en 0 informe, il ne garde rien."""
    assert "exit 1" in _script_de_validation()


def test_le_binaire_terraform_est_verifie() -> None:
    """Même exigence que poutine : l'archive de l'éditeur et sa somme publiée.

    Aucune action tierce n'est ajoutée à la chaîne d'approvisionnement pour un
    binaire qu'on ne lance que deux fois.
    """
    script = _script_de_validation()

    assert "sha256sum -c" in script, "le binaire téléchargé doit être vérifié"
    assert "releases.hashicorp.com" in script, "l'archive doit venir de l'éditeur"


def test_la_version_de_terraform_est_epinglee() -> None:
    """`latest` ferait dépendre le verdict du jour où la CI tourne."""
    versions = [
        etape.get("env", {}).get("TERRAFORM_VERSION")
        for etape in _job()["steps"]
    ]
    epinglee = next((v for v in versions if v), None)

    assert epinglee is not None, "la version de terraform n'est pas épinglée"
    assert epinglee[0].isdigit(), f"version non littérale : {epinglee}"


# ── La décision sur les images amont est écrite ─────────────────────────────

def test_le_choix_des_images_mutables_est_documente() -> None:
    """Le troisième critère de l'issue : une décision écrite, pas un silence.

    Les URL d'images pointent des `latest` / `current` mutables. C'est un choix
    défendable — une somme épinglée non tenue à jour servirait aux apprenants
    une image de plus en plus vulnérable — mais un choix non écrit ne se
    distingue pas d'un oubli.
    """
    readme = (TEMPLATES / "README.md").read_text(encoding="utf-8")

    assert "mutable" in readme.lower()
    for domaine in ("cloud-images.ubuntu.com", "cloud.debian.org",
                    "repo.almalinux.org"):
        assert domaine in readme, f"{domaine} n'est pas couvert par la décision"
