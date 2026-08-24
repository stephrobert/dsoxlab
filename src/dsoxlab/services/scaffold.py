"""Créer un catalogue ou un lab conforme au contrat, sans le connaître par cœur.

Écrire un catalogue supposait jusqu'ici de retenir le contrat, ou de copier un
dépôt existant. Les deux chemins produisent les mêmes erreurs : un fichier
obligatoire oublié, un nom de fichier de test qui ne correspond pas à celui
qu'attend le validator, une fixture livrée mais non déclarée. Et la sanction est
muette — le lab disparaît du catalogue sans un mot, parce qu'un `lab.yaml` qui
lève au parsing n'est jamais examiné par `validate-structure`.

**Les gabarits sont des chaînes de ce module, pas des fichiers packagés.** Le
dépôt s'interdit d'embarquer des templates de labs, et un répertoire
`templates/scaffold/` ressemblerait à s'y méprendre à ce qu'il proscrit. Ici, ce
qui est produit est une **structure vide** : des emplacements à remplir, aucun
contenu pédagogique, aucun nom de domaine.

Le squelette produit doit passer `validate-structure` **sans retouche**, et le
test généré doit **échouer** tant que l'exercice n'est pas résolu : un squelette
vert d'emblée apprendrait la mauvaise habitude, celle d'un lab qui note sans
rien vérifier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..i18n import _

#: Un identifiant sert de nom de répertoire et de clé CLI : on le borne pour
#: qu'il ne puisse ni remonter l'arborescence, ni porter d'espace.
_ID_VALIDE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

RUNTIMES = ("shell", "vm")


class ScaffoldError(RuntimeError):
    """La création a échoué, avec un message déjà traduit."""


@dataclass(frozen=True)
class Creation:
    """Ce qui a été écrit, pour que la CLI le raconte sans le deviner."""

    racine: Path
    fichiers: tuple[Path, ...]


_META = """\
# Catalogue {id}, décrit par le contrat v1 de dsoxlab.
#
# `repo.id` sert de clé pour l'état local de ce catalogue : le changer
# déplace ces emplacements.
schema_version: 1

repo:
  id: {id}
  category: {id}
  title: {id}
  description: |
    À remplir : ce que ce catalogue apprend, et à qui.

# Un catalogue sans lab `vm` n'a pas besoin de bloc `infra:`. Décommente-le le
# jour où un lab déclare `runtime.type: vm`.
#
# infra:
#   provider: kvm
#   network: {id}-net
#   cidr: 10.10.10.0/24
#   hosts:
#     - name: hote.lab
#       distro: alma10

sections:
  - id: premiers-pas
    title: Premiers pas
    description: À remplir.
    labs: []
"""

_GITIGNORE = """\
# Progression et contexte : locaux à chaque machine, jamais versionnés.
.dsoxlab.db
.dsoxlab-context.json

# Clé privée d'automatisation, posée par `dsoxlab instructor bootstrap`.
ssh/id_ed25519

# Répertoires de travail des labs `shell` : ce que l'apprenant y écrit lui
# appartient, et le catalogue les recrée à chaque `run`.
labs/**/challenge/work/
"""

_LAB_COMMUN = """\
# Lab {id}. Les champs marqués REQUIS sont exigés par le validator : sans eux,
# le lab est refusé, ou pire, disparaît du catalogue sans un mot.
id: {id}                      # REQUIS
title: "À remplir"            # REQUIS
level: l1                     # REQUIS
description: "À remplir : ce que l'apprenant saura faire à la fin."
skills:                       # REQUIS, non vide
  - a-remplir
distros:                      # REQUIS, non vide
  - any
doc_url: https://example.org/a-remplir   # REQUIS, http(s)
lab_type: lab
estimated_time: 30m
"""

_LAB_SHELL = """\
runtime:
  type: shell
  workdir: challenge/work
  # Une fixture NON déclarée ici n'est PAS copiée, même présente dans
  # fixtures/ : le répertoire de travail serait vide et l'apprenant sans rien
  # à faire.
  fixtures: []
validation:
  functional: true
"""

_LAB_VM = """\
runtime:
  type: vm
  targets:                    # REQUIS pour vm, non vide
    - name: cible
      host: hote.lab          # doit exister dans meta.yml: infra.hosts[]
  default: cible
validation:
  functional: true
  persistence_after_reboot: false
"""

_README = """\
# {id}

**Public :** l'apprenant.

À remplir : ce que ce lab apprend, en une phrase.

## Ce que vous saurez faire

- À remplir.
"""

_SCENARIO = """\
# Scénario

À remplir : la situation, telle que l'apprenant la rencontrerait.

Un scénario dit **où on est et ce qui ne va pas**, pas la marche à suivre :
c'est le travail de l'apprenant de la trouver.

## Mission

À remplir.
"""

#: Le test généré ÉCHOUE, il n'est pas `skip`. Un test sauté ne dit rien : ni
#: que le travail reste à faire, ni qu'il est fait. Un test rouge dit la
#: première chose, et c'est celle qui compte pour qui vient d'écrire un
#: squelette.
_TEST = '''\
"""Tests fonctionnels du lab {id} — SQUELETTE, à écrire.

Ce fichier échoue volontairement. Il ne s'agit pas d'une erreur : tant que les
tests ne sont pas écrits, `dsoxlab check` doit rendre un échec plutôt qu'un
succès qui ne prouve rien.

Ce qu'un test de lab vérifie, c'est **l'état du système**, jamais qu'une
commande a été tapée : un apprenant qui atteint le bon état par un autre chemin
a réussi. Quand le sujet le justifie, vérifiez aussi que l'état survit à un
redémarrage.
"""

from __future__ import annotations


def test_a_ecrire() -> None:
    """Remplacez-moi par ce que le lab doit prouver."""
    raise AssertionError(
        "Les tests de ce lab restent à écrire. Vérifiez l'état du système "
        "produit par la mission, pas les commandes tapées pour y arriver."
    )
'''

_SETUP = """\
---
# Joué par `dsoxlab run` avant d'ouvrir la session : il pose la situation que
# le scénario décrit.
- name: Préparer le lab {id}
  hosts: lab_target
  become: true
  tasks:
    - name: À remplir
      ansible.builtin.debug:
        msg: "Remplacez cette tâche par la mise en situation."
"""

_CLEANUP = """\
---
# Joué par `dsoxlab clean` et `dsoxlab reset` : il défait ce que setup.yaml a
# posé, pour que le lab se rejoue à l'identique.
- name: Défaire le lab {id}
  hosts: lab_target
  become: true
  tasks:
    - name: À remplir
      ansible.builtin.debug:
        msg: "Remplacez cette tâche par le retour à l'état initial."
"""


def _valider_identifiant(identifiant: str) -> None:
    if not _ID_VALIDE.match(identifiant):
        raise ScaffoldError(_("scaffold_id_invalide", name=identifiant))


def _ecrire(chemin: Path, contenu: str) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def creer_catalogue(identifiant: str, destination: Path) -> Creation:
    """Écrit un catalogue vide mais conforme, prêt à recevoir des labs."""
    _valider_identifiant(identifiant)
    racine = destination / identifiant
    if racine.exists():
        # Ne jamais écrire par-dessus : ce répertoire porte peut-être déjà du
        # travail, et un squelette l'écraserait sans retour possible.
        raise ScaffoldError(_("scaffold_existe_deja", path=str(racine)))

    fichiers = [
        _ecrire(racine / "meta.yml", _META.format(id=identifiant)),
        _ecrire(racine / ".gitignore", _GITIGNORE),
    ]
    (racine / "labs").mkdir(parents=True, exist_ok=True)
    (racine / "ssh").mkdir(parents=True, exist_ok=True)
    return Creation(racine=racine, fichiers=tuple(fichiers))


def creer_lab(identifiant: str, racine_catalogue: Path, *, runtime: str) -> Creation:
    """Écrit un lab conforme au contrat, découvert dès le prochain `list-labs`.

    Le squelette diffère selon le runtime, parce que le contrat l'exige : un lab
    `shell` déclare son `workdir`, un lab `vm` ses `targets` et ses deux
    playbooks.
    """
    _valider_identifiant(identifiant)
    if runtime not in RUNTIMES:
        raise ScaffoldError(_("scaffold_runtime_inconnu", name=runtime,
                              connus=", ".join(RUNTIMES)))
    if not (racine_catalogue / "meta.yml").is_file():
        raise ScaffoldError(_("scaffold_hors_catalogue", path=str(racine_catalogue)))

    base = racine_catalogue / "labs" / identifiant
    if base.exists():
        raise ScaffoldError(_("scaffold_existe_deja", path=str(base)))

    corps = _LAB_SHELL if runtime == "shell" else _LAB_VM
    fichiers = [
        _ecrire(base / "lab.yaml", _LAB_COMMUN.format(id=identifiant) + corps),
        _ecrire(base / "README.md", _README.format(id=identifiant)),
        _ecrire(base / "scenario.md", _SCENARIO),
        _ecrire(base / "challenge" / "tests" / "test_functional.py",
                _TEST.format(id=identifiant)),
    ]
    if runtime == "vm":
        fichiers += [
            _ecrire(base / "setup.yaml", _SETUP.format(id=identifiant)),
            _ecrire(base / "cleanup.yaml", _CLEANUP.format(id=identifiant)),
        ]
    else:
        # Le répertoire de travail existe dès la création : sans lui, le lab
        # est conforme mais `run` n'a rien à préparer.
        (base / "challenge" / "work").mkdir(parents=True, exist_ok=True)
        (base / "fixtures").mkdir(parents=True, exist_ok=True)
    return Creation(racine=base, fichiers=tuple(fichiers))
