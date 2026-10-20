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
from .scaffold_socle import fichiers_du_socle

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
    #: La section du `meta.yml` où le lab a été inscrit, ou `None` si la forme
    #: du fichier n'a pas été reconnue. L'appelant le dit alors, plutôt que de
    #: laisser croire à une inscription qui n'a pas eu lieu.
    section: str | None = None


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

# Où remettre une preuve d'apprentissage, si ce catalogue a un portail. En
# `https` : le lien porte les résultats d'un apprenant. dsoxlab n'envoie rien —
# il affiche une adresse, et l'apprenant décide.
#
# learning:
#   portal_url: https://formation.example.org/mon-apprentissage/

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

# Artefacts des outils Python. Ils apparaissent au premier `pytest` ou au
# premier `uv run`, et un `git status` encombré fait manquer les vrais
# changements. Mesuré sur sept catalogues neufs : les trois premiers
# répertoires y étaient en non-suivi dès leur première suite de tests.
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.venv/
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

**Audience:** the learner.

TO FILL IN: what this lab teaches, in one sentence.

## What you will be able to do

- TO FILL IN.
"""

#: La version française de l'énoncé. Le fichier SANS suffixe porte l'anglais,
#: parce que c'est la langue par défaut de l'outil ; `.fr.md` porte le
#: français. Les produire tous les deux est la seule façon qu'un lab créé par
#: l'outil soit conforme à la règle bilingue sans retouche.
_LAB_FR = """\
# Surcharge française du lab {id}. Elle ne porte QUE `title` et
# `description` : tout autre champ y est ignoré en silence, parce que le
# contrat ne se traduit pas.
title: "À remplir"
description: "À remplir : ce que l'apprenant saura faire à la fin."
"""

_README_FR = """\
# {id}

**Public :** l'apprenant.

À remplir : ce que ce lab apprend, en une phrase.

## Ce que vous saurez faire

- À remplir.
"""

_SCENARIO = """\
# Scenario

TO FILL IN: the situation, as the learner would meet it.

A scenario says **where we are and what is wrong**, not the steps to take:
finding those is the learner's work.

## Mission

TO FILL IN.
"""

_SCENARIO_FR = """\
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
    # Le socle : tout ce qu'un catalogue de la collection porte en plus du
    # contrat. Il vit dans son propre module, parce que ce sont des gabarits et
    # non de la logique, et parce qu'un seul endroit doit décider de ce qu'un
    # catalogue porte — le jour où la collection en ajoute un, il s'ajoute là
    # et tous les nouveaux catalogues l'ont.
    fichiers += [
        _ecrire(racine / relatif, contenu)
        for relatif, contenu in fichiers_du_socle(identifiant).items()
    ]
    (racine / "labs").mkdir(parents=True, exist_ok=True)
    # `ssh/` ne sert qu'aux labs `vm`, mais le créer vide ne coûte rien et
    # évite au formateur de se demander où `instructor bootstrap` écrira.
    (racine / "ssh").mkdir(parents=True, exist_ok=True)
    return Creation(racine=racine, fichiers=tuple(fichiers))


def _inscrire_dans_une_section(meta: Path, chemin_relatif: str) -> str | None:
    """Ajoute le lab aux `labs:` de la PREMIÈRE section, et dit laquelle.

    Pourquoi par texte et non par un aller-retour YAML : un `yaml.safe_load`
    suivi d'un `yaml.dump` perd tous les commentaires du `meta.yml`, et ce
    fichier est à moitié fait de commentaires qui expliquent le contrat. Les
    effacer pour ajouter une ligne serait un mauvais échange.

    Rend l'identifiant de la section, ou `None` si la forme du fichier n'est
    pas reconnue. Dans ce cas on ne touche à rien et l'appelant le dit : un lab
    non inscrit reste jouable, mais `next` ne sait pas où le placer, et le
    deviner en silence serait pire que de demander.
    """
    source = meta.read_text(encoding="utf-8")
    marqueur = "\nsections:\n"
    if marqueur not in source:
        return None

    # La première section déclarée, et son `labs:`.
    debut = source.index(marqueur) + len(marqueur)
    tete = source[debut:]
    if not tete.lstrip().startswith("- id:"):
        return None
    section = tete[tete.index("- id:") + len("- id:"):].split("\n", 1)[0].strip()

    # Borner la recherche à la PREMIÈRE section, et à elle seule.
    #
    # Sans cette borne, `tete` couvrait tout le reste du fichier : la branche
    # « section neuve » ci-dessous trouvait alors le premier `labs: []` de
    # N'IMPORTE QUELLE section. La fonction annonçait donc la première section,
    # dont elle venait de lire le nom, et écrivait dans une autre.
    #
    # Ce n'est pas une erreur de rangement, c'est un message qui MENT, et la
    # position dont il parle EST l'ordre pédagogique : `discovery/scanner.py`
    # en dérive `bloc_order`, et `next` s'en sert.
    #
    # Mesuré le 2026-10-19 sur bdd-dsoxlab-training : deux labs sont partis
    # dans une autre section que celle annoncée, et ce sont exactement les
    # deux qui ont été créés tant qu'une section vide subsistait. Les suivants
    # ont été rangés dans la première section, ce qui est le comportement
    # documenté, et non le défaut.
    #
    # Le défaut demande donc DEUX sections dont une vide pour se montrer, et
    # un meta.yml d'une seule section ne le montre jamais : c'est ce qui lui a
    # permis de survivre.
    suivante = re.search(r"^  - id:", tete[1:], re.MULTILINE)
    if suivante is not None:
        tete = tete[: suivante.start() + 1]

    # Une section neuve, telle que `new catalog` l'écrit : la liste est vide.
    if "    labs: []\n" in tete:
        position = debut + tete.index("    labs: []\n")
        meta.write_text(
            source[:position]
            + f"    labs:\n      - {chemin_relatif}\n"
            + source[position + len("    labs: []\n"):],
            encoding="utf-8",
        )
        return section

    # Une section qui porte déjà des labs : on ajoute à la FIN de sa liste, et
    # non en tête. Cette position EST l'ordre pédagogique, dont
    # `discovery/scanner.py` dérive `bloc_order` et dont `next` se sert : un
    # lab créé en second doit venir en second.
    if "    labs:\n" not in tete:
        return None
    position = debut + tete.index("    labs:\n") + len("    labs:\n")
    fin = position
    for ligne in source[position:].splitlines(keepends=True):
        if not ligne.startswith("      - "):
            break
        fin += len(ligne)
    meta.write_text(
        source[:fin] + f"      - {chemin_relatif}\n" + source[fin:],
        encoding="utf-8",
    )
    return section


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
        # Les versions françaises : la règle du projet veut tout ce qui
        # s'affiche en deux langues, et `validators/content.py` signale un
        # document traduit d'un seul côté. Un lab créé sans elles était donc
        # immédiatement non conforme.
        _ecrire(base / "README.fr.md", _README_FR.format(id=identifiant)),
        _ecrire(base / "scenario.fr.md", _SCENARIO_FR),
        _ecrire(base / "lab.fr.yaml", _LAB_FR.format(id=identifiant)),
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

    # Le lab entre dans une section : sans cela il reste jouable, mais il
    # n'appartient à aucun bloc, et `next` ne sait pas où le placer dans la
    # progression. `discovery/scanner.py` dérive `bloc` et `bloc_order` de
    # cette position, donc l'omettre prive le lab de son ordre pédagogique.
    section = _inscrire_dans_une_section(
        racine_catalogue / "meta.yml",
        base.relative_to(racine_catalogue / "labs").as_posix(),
    )
    return Creation(racine=base, fichiers=tuple(fichiers), section=section)
