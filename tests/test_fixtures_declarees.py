"""Le répertoire ``fixtures/`` et la déclaration doivent dire la même chose (#177).

``ShellRuntime`` itère sur ``runtime.fixtures``, **pas** sur le contenu du
répertoire. Les deux écarts possibles produisaient le même dégât, en silence :

- une fixture **déclarée mais absente** partait en ``logger.warning`` ;
- une fixture **présente mais non déclarée** n'était jamais lue.

Dans les deux cas ``dsoxlab run`` créait un ``challenge/work`` vide, sortait en
**0**, et l'apprenant n'avait rien à faire. Le défaut a rendu **7 labs de
`terraform-training` injouables le 2026-07-28**, tous marqués faits — et il se
cachait d'autant mieux que les outils de vérification des corrigés copient, eux,
le répertoire entier : la solution passait au vert pendant que le parcours
apprenant était cassé.

Ce module éprouve les **deux** niveaux, parce qu'ils servent deux moments
différents : le validator prévient l'auteur en CI, le runtime protège
l'apprenant qui joue un lab déjà publié.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.models.lab import LabDefinition
from dsoxlab.runtimes.shell import FixtureError, ShellRuntime
from dsoxlab.validators.content import validate_fixtures

_ENTETE = """\
id: l1-demo
title: Demo lab
level: beginner
skills: [demo]
distros: [any]
doc_url: https://example.org/docs/demo/
"""


def _lab(tmp_path: Path, *, declarees: str, sur_disque: dict[str, str],
         runtime: str = "shell") -> LabDefinition:
    """Écrit un lab dont la déclaration et le disque peuvent diverger."""
    base = tmp_path / "labs" / "l1-demo"
    base.mkdir(parents=True, exist_ok=True)
    if runtime == "shell":
        corps = f"runtime:\n  type: shell\n  workdir: challenge/work\n{declarees}"
    else:
        corps = ("runtime:\n  type: vm\n  targets:\n    - name: cible\n"
                 "      host: hote.lab\n")
    (base / "lab.yaml").write_text(_ENTETE + corps, encoding="utf-8")

    for chemin_relatif, contenu in sur_disque.items():
        fichier = base / "fixtures" / chemin_relatif
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(contenu, encoding="utf-8")
    return LabDefinition.from_yaml(base / "lab.yaml")


def _cles(lab: LabDefinition) -> list[str]:
    return [souci.key for souci in validate_fixtures(lab).issues]


# ── Le validator : prévenir l'auteur, en CI ─────────────────────────────────

def test_une_fixture_livree_mais_muette_est_signalee(tmp_path: Path) -> None:
    """Le cas exact des 7 labs : `fixtures/` porte des fichiers, rien ne les déclare.

    C'est le plus traître des deux, parce que l'auteur voit ses fichiers et
    conclut que le travail est fait.
    """
    lab = _lab(tmp_path, declarees="  fixtures: []\n",
               sur_disque={"acces.log": "…"})

    assert _cles(lab) == ["content_fixture_undeclared"]


def test_une_fixture_declaree_sans_fichier_est_vue(tmp_path: Path) -> None:
    lab = _lab(tmp_path, declarees="  fixtures:\n    - absente.log\n",
               sur_disque={})

    assert _cles(lab) == ["content_fixture_missing"]


def test_une_declaration_conforme_ne_dit_rien(tmp_path: Path) -> None:
    """Le garde-fou du garde-fou : un lab correct ne doit produire aucun bruit.

    Sans lui, un contrôle trop zélé se ferait désactiver plutôt que corriger.
    """
    lab = _lab(tmp_path, declarees="  fixtures:\n    - acces.log\n",
               sur_disque={"acces.log": "…"})

    assert _cles(lab) == []


def test_un_chemin_qui_remonte_l_arborescence_est_refuse(tmp_path: Path) -> None:
    lab = _lab(tmp_path, declarees="  fixtures:\n    - ../../etc/passwd\n",
               sur_disque={})

    assert _cles(lab) == ["content_fixture_escapes"]


def test_un_sous_repertoire_declare_est_accepte(tmp_path: Path) -> None:
    """Le chemin déclaré est préservé : un lab à modules doit rester possible."""
    lab = _lab(tmp_path,
               declarees="  fixtures:\n    - modules/stockage/main.tf\n",
               sur_disque={"modules/stockage/main.tf": "resource {}"})

    assert _cles(lab) == []


def test_un_fichier_cache_n_est_pas_une_fixture(tmp_path: Path) -> None:
    """Un `.gitkeep` sert à versionner un répertoire vide, pas à être copié.

    Le signaler serait un faux positif que chaque auteur apprendrait à ignorer,
    et un contrôle qu'on apprend à ignorer ne contrôle plus rien.
    """
    lab = _lab(tmp_path, declarees="  fixtures: []\n",
               sur_disque={".gitkeep": ""})

    assert _cles(lab) == []


def test_un_lab_vm_n_est_pas_concerne(tmp_path: Path) -> None:
    """`fixtures` n'a de sens que pour le runtime shell."""
    lab = _lab(tmp_path, declarees="", sur_disque={"trace.log": "…"},
               runtime="vm")

    assert _cles(lab) == []


def test_les_deux_ecarts_se_signalent_ensemble(tmp_path: Path) -> None:
    """Un rapport par lab, pas par exécution : l'auteur corrige en une passe."""
    lab = _lab(tmp_path, declarees="  fixtures:\n    - absente.log\n",
               sur_disque={"presente.log": "…"})

    assert sorted(_cles(lab)) == ["content_fixture_missing",
                                  "content_fixture_undeclared"]


# ── Le runtime : protéger l'apprenant, sur un lab déjà publié ───────────────

def test_run_refuse_de_demarrer_sur_une_fixture_absente(tmp_path: Path) -> None:
    """Le cœur du défaut : `run` sortait en 0 sur un répertoire de travail vide."""
    lab = _lab(tmp_path, declarees="  fixtures:\n    - absente.log\n",
               sur_disque={})

    with pytest.raises(FixtureError) as exc:
        ShellRuntime().start(lab)

    assert "absente.log" in str(exc.value)


def test_aucune_fixture_n_est_copiee_si_l_une_manque(tmp_path: Path) -> None:
    """Tout ou rien : un workdir à moitié rempli a l'air de marcher.

    C'est pire qu'un refus, parce que l'apprenant cherche l'erreur chez lui.
    """
    lab = _lab(tmp_path,
               declarees="  fixtures:\n    - presente.log\n    - absente.log\n",
               sur_disque={"presente.log": "…"})

    with pytest.raises(FixtureError):
        ShellRuntime().start(lab)

    workdir = lab.path / "challenge" / "work"
    assert not (workdir / "presente.log").exists(), (
        "la fixture valide ne doit pas être copiée si une autre manque"
    )


def test_le_refus_nomme_toutes_les_fautes(tmp_path: Path) -> None:
    """Sinon l'auteur corrige une fixture par `run`, autant de fois qu'il en a."""
    lab = _lab(tmp_path,
               declarees="  fixtures:\n    - une.log\n    - deux.log\n",
               sur_disque={})

    with pytest.raises(FixtureError) as exc:
        ShellRuntime().start(lab)

    message = str(exc.value)
    assert "une.log" in message and "deux.log" in message


def test_une_fixture_conforme_arrive_bien_dans_le_workdir(tmp_path: Path) -> None:
    """L'autre bout : le comportement nominal ne doit pas se perdre."""
    lab = _lab(tmp_path,
               declarees="  fixtures:\n    - modules/stockage/main.tf\n",
               sur_disque={"modules/stockage/main.tf": "resource {}"})

    ShellRuntime().start(lab)

    copie = lab.path / "challenge" / "work" / "modules" / "stockage" / "main.tf"
    assert copie.read_text(encoding="utf-8") == "resource {}", (
        "le chemin déclaré est préservé, il n'est pas aplati sur le nom de base"
    )
