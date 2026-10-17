"""Le socle d'un catalogue : ce que `new catalog` produit en plus du contrat.

POURQUOI CE MODULE EXISTE

`new catalog` ne produisait que deux fichiers, `meta.yml` et `.gitignore`. Tout
le reste — README, gouvernance, outillage, intégration continue — a donc été
bâti à la main douze fois, et douze fois différemment. Mesuré à la racine des
douze catalogues avant d'écrire ce module :

    invariant (12/12) : .gitignore, LICENSE, README.md, README.fr.md,
                        conftest.py, labs/, meta.yml, pyproject.toml, scripts/
    dérive (10-11/12) : .github/, .pre-commit-config.yaml, tests/, CHANGELOG,
                        CODE_OF_CONDUCT, CONTRIBUTING, SECURITY
    les deux derniers : 14 et 19 entrées, contre 28 à 43 pour les dix autres

Et sur les README, le même écart : 1 931 octets sans un seul titre de niveau 2
d'un côté, 33 000 octets de l'autre. Un générateur qui ne produit que la graine
laisse cette dérive se recréer à chaque catalogue.

CE QUE CE MODULE PRODUIT, ET CE QU'IL NE PRODUIT PAS

Il produit la **structure**, jamais le contenu pédagogique : les sept sections
de README qui décrivent dsoxlab (le contrat, le cycle de vie, la note, la mise
à jour, contribuer, la licence) sont écrites en entier, parce qu'elles sont les
mêmes dans les douze catalogues. Les sept autres portent un « À remplir »
explicite, parce qu'elles parlent du domaine, et qu'aucun gabarit ne peut le
savoir.

Aucun nom de domaine, aucun produit, aucune URL de blog n'apparaît ici : c'est
la règle d'agnosticisme du moteur, et elle vaut pour ce qu'il écrit autant que
pour ce qu'il exécute.
"""

from __future__ import annotations

# Les actions sont épinglées par SHA de 40 caractères, avec la version en
# commentaire : un tag est déplaçable, un SHA non. Ces quatre-là sont celles
# qui passent aujourd'hui dans la CI des douze catalogues, relevées plutôt
# qu'inventées.
_SHA_HARDEN = "351661ca32ac09a36dc5ee2d536e3128f2a3c8ed"  # v2.22.0
_SHA_CHECKOUT = "3d3c42e5aac5ba805825da76410c181273ba90b1"  # v7.0.1
_SHA_SETUP_UV = "c18668ad3cf93ea998bef934396af7bb5c839dc7"  # v10.2.0


# ── README : quatorze sections, dont sept génériques ─────────────────────────
#
# L'ordre n'est pas arbitraire : il est celui des trois README les plus
# complets de la collection, qui se ressemblaient à un titre près. On dit ce
# que c'est, ce qu'il faut, comment on installe, comment on joue, puis comment
# ça marche, puis le catalogue.

README_EN = """\
# {id}

**Language:** [English](./README.md) · [Français](./README.fr.md)

TO FILL IN: one paragraph. What this catalog teaches, and to whom.

## What it is

TO FILL IN: what a learner can do at the end that they could not do at the
start. Say it in terms of capability, not of topics covered.

Say here why the labs are in this order, if the order matters.

## Requirements

TO FILL IN, and be exact: a requirement that is missing from this list costs
the learner an hour of searching.

- **Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)**
- **`git`**
- **`dsoxlab`**, the engine, installed as a standalone tool (see below).
- TO FILL IN: the tools the labs need on the machine.

TO FILL IN: whether this catalog has `vm` labs. If it does, name the
hypervisor, the RAM and the disk the machines need. If it does not, say so:
`dsoxlab provision` is then never called, and saying it spares the reader a
question.

`dsoxlab doctor` says what this repository needs and what it does not, and
tells apart a check that failed from one it could not measure.

## Install

`dsoxlab` is published on [PyPI](https://pypi.org/project/dsoxlab/). Install it
as a standalone tool, so it stays out of this repository:

```bash
# 1. The dsoxlab CLI (external tool, stays out of this repo)
uv tool install dsoxlab

# 2. This lab catalog
git clone <this repository>
cd {id}

# 3. Check the contract is valid
dsoxlab validate-structure
```

### Your first lab, in five minutes

```bash
export LAB_HOME=$PWD
dsoxlab list-labs                # the catalog, in teaching order
dsoxlab run       <id>           # set the starting state
dsoxlab challenge <id>           # read the mission
dsoxlab check     <id>           # run the tests, record the score
```

`run` is what prepares the lab. Running `check` on a lab you never started
measures nothing, and says so rather than recording a 0.

### Keeping it up to date

```bash
uv tool upgrade dsoxlab        # the engine, published on PyPI
git -C <this repo> pull        # the catalog
```

The engine and the catalog move independently: a new `dsoxlab` never requires
re-cloning the labs, and new labs never require upgrading the tool, as long as
the contract version matches.

## How it works

### The declarative contract (two levels)

The catalog is described by data, not code, which is what keeps the `dsoxlab`
engine domain-agnostic:

- **`meta.yml`** at the root declares the repository identity and the **order**
  of the sections shown by `list-labs`;
- **`lab.yaml`** per lab declares its `skills`, `level`, `runtime` (type,
  fixtures, services), `distros`, `doc_url` and a `validation` block. A
  `lab.fr.yaml` overrides `title` and `description` in French, and nothing else.

`dsoxlab validate-structure` checks the whole contract: `meta.yml` is well
formed, every referenced lab exists with a valid `lab.yaml`, every declared
test and fixture file is really there, and every relative link in a README
leads somewhere.

### The lab lifecycle

```bash
dsoxlab list-labs              # browse the catalog
dsoxlab show      <id>         # metadata and status of one lab
dsoxlab run       <id>         # set the starting state
dsoxlab challenge <id>         # read the mission, no step-by-step
dsoxlab hint      <id>         # reveal a hint (deducted from the score)
dsoxlab check     <id>         # run the tests, compute and record the score
dsoxlab clean     <id>         # undo what the lab set up
dsoxlab progress               # per-section progress, average score
```

### Runtimes

TO FILL IN: one row per runtime this catalog actually uses, and what it asks
of the machine.

| Runtime | What the lab asks for |
|---|---|
| `shell` | a terminal, and TO FILL IN |

### The validation model

Validation **proves the state, it does not trust the learner**. Each lab ships
`pytest` tests under `challenge/tests/` that read what the system holds, never
what a file contains or which commands were typed.

And a lab is proven **in both directions**: the tests must fail before the work
and pass after it. A test that is green before the work is not a test, it is an
assumption about the setup.

TO FILL IN: where the reference solutions live, and whether they are encrypted.
A solution shipped in clear text spoils the lab, and git keeps it forever.

### Scoring, hints, progress

`check` records a score (tests passed out of total, minus the cost of any hints
revealed). Hints are **base64-encoded** in `challenge/hints.yaml`, so that
opening the file does not give them away, and their cost grows with their
precision. History lives in a SQLite database **local to this repository**.

A run that measured nothing is neither a pass nor a failure: if every collected
test skips, `check` records no score and says why. A score of 0 would accuse the
lab of what is missing from the machine.

## Catalog

TO FILL IN: one subsection per section of `meta.yml`, with its labs.

## Contributing

Read [`CONTRIBUTING.md`](./CONTRIBUTING.md). In short: a lab is proven **in both
directions** before it is merged, `dsoxlab validate-structure` is green, and the
statement exists in English and in French.

Anything user-facing is bilingual. A document translated on one side only is
reported by the validator, not left to goodwill.

## License

See [`LICENSE`](./LICENSE).
"""

README_FR = """\
# {id}

**Langue :** [English](./README.md) · [Français](./README.fr.md)

À REMPLIR : un paragraphe. Ce que ce catalogue apprend, et à qui.

## Ce que c'est

À REMPLIR : ce qu'un apprenant saura faire à la fin et ne savait pas faire au
début. Dis-le en capacité, pas en liste de sujets couverts.

Dis ici pourquoi les labs sont dans cet ordre, si l'ordre compte.

## Prérequis

À REMPLIR, et sois exact : un prérequis absent de cette liste coûte une heure
de recherche à l'apprenant.

- **Python 3.11+ et [`uv`](https://docs.astral.sh/uv/)**
- **`git`**
- **`dsoxlab`**, le moteur, installé en outil autonome (voir plus bas).
- À REMPLIR : les outils dont les labs ont besoin sur le poste.

À REMPLIR : si ce catalogue a des labs `vm`, nomme l'hyperviseur, la RAM et le
disque que les machines demandent. S'il n'en a pas, dis-le : `dsoxlab provision`
n'est alors jamais appelé, et le dire épargne une question au lecteur.

`dsoxlab doctor` dit ce dont ce dépôt a besoin et ce dont il n'a pas besoin, et
distingue un contrôle qui a échoué d'un contrôle qu'il n'a pas pu mesurer.

## Installation

`dsoxlab` est publié sur [PyPI](https://pypi.org/project/dsoxlab/).
Installe-le en outil autonome, pour qu'il reste hors de ce dépôt :

```bash
# 1. La CLI dsoxlab (outil externe, hors de ce dépôt)
uv tool install dsoxlab

# 2. Ce catalogue de labs
git clone <ce dépôt>
cd {id}

# 3. Vérifier que le contrat est valide
dsoxlab validate-structure
```

### Votre premier lab, en cinq minutes

```bash
export LAB_HOME=$PWD
dsoxlab list-labs                # le catalogue, dans l'ordre pédagogique
dsoxlab run       <id>           # poser l'état de départ
dsoxlab challenge <id>           # lire la mission
dsoxlab check     <id>           # lancer les tests, enregistrer le score
```

C'est `run` qui prépare le lab. Un `check` joué sur un lab jamais démarré ne
mesure rien, et le dit au lieu d'enregistrer un 0.

### Garder à jour

```bash
uv tool upgrade dsoxlab        # le moteur, publié sur PyPI
git -C <ce dépôt> pull         # le catalogue
```

Le moteur et le catalogue avancent indépendamment : un nouveau `dsoxlab` ne
demande jamais de recloner les labs, et de nouveaux labs ne demandent jamais de
mettre l'outil à jour, tant que la version du contrat correspond.

## Comment ça marche

### Le contrat déclaratif, à deux niveaux

Le catalogue est décrit par des données, pas par du code, et c'est ce qui garde
le moteur `dsoxlab` indépendant du domaine :

- **`meta.yml`** à la racine déclare l'identité du dépôt et l'**ordre** des
  sections affichées par `list-labs` ;
- **`lab.yaml`** par lab déclare ses `skills`, son `level`, son `runtime`
  (type, fixtures, services), ses `distros`, son `doc_url` et un bloc
  `validation`. Un `lab.fr.yaml` surcharge `title` et `description` en
  français, et rien d'autre.

`dsoxlab validate-structure` contrôle tout le contrat : `meta.yml` bien formé,
chaque lab référencé présent avec un `lab.yaml` valide, chaque fichier de test
et de fixture déclaré réellement là, et chaque lien relatif d'un README qui
mène quelque part.

### Le cycle de vie d'un lab

```bash
dsoxlab list-labs              # parcourir le catalogue
dsoxlab show      <id>         # métadonnées et état d'un lab
dsoxlab run       <id>         # poser l'état de départ
dsoxlab challenge <id>         # lire la mission, sans pas-à-pas
dsoxlab hint      <id>         # révéler un indice (déduit du score)
dsoxlab check     <id>         # lancer les tests, calculer et enregistrer le score
dsoxlab clean     <id>         # défaire ce que le lab a posé
dsoxlab progress               # avancement par section, score moyen
```

### Les runtimes

À REMPLIR : une ligne par runtime réellement employé par ce catalogue, et ce
qu'il demande au poste.

| Runtime | Ce que le lab demande |
|---|---|
| `shell` | un terminal, et À REMPLIR |

### Le modèle de validation

La validation **prouve l'état, elle ne fait pas confiance à l'apprenant**.
Chaque lab porte des tests `pytest` sous `challenge/tests/` qui lisent ce que
le système contient, jamais ce qu'un fichier contient ni quelles commandes ont
été tapées.

Et un lab est prouvé **dans les deux sens** : les tests doivent échouer avant
le travail et passer après. Un test vert avant le travail n'est pas un test,
c'est une hypothèse sur le setup.

À REMPLIR : où vivent les solutions de référence, et si elles sont chiffrées.
Une solution livrée en clair gâche le lab, et git la garde pour toujours.

### Score, indices, avancement

`check` enregistre un score (tests réussis sur total, moins le coût des indices
révélés). Les indices sont **en base64** dans `challenge/hints.yaml`, pour qu'on
n'y accède pas en ouvrant le fichier, et leur coût croît avec leur précision.
L'historique vit dans une base SQLite **locale à ce dépôt**.

Une exécution qui n'a rien mesuré n'est ni une réussite ni un échec : si tous
les tests collectés skippent, `check` n'enregistre aucune note et dit pourquoi.
Un 0 accuserait le lab de ce qui manque au poste.

## Catalogue

À REMPLIR : une sous-section par section du `meta.yml`, avec ses labs.

## Contribuer

Lis [`CONTRIBUTING.fr.md`](./CONTRIBUTING.fr.md). En bref : un lab est prouvé
**dans les deux sens** avant d'être fusionné, `dsoxlab validate-structure` est
vert, et l'énoncé existe en anglais et en français.

Tout ce qui s'affiche est bilingue. Un document traduit d'un seul côté est
signalé par le validateur, et non laissé à la bonne volonté.

## Licence

Voir [`LICENSE`](./LICENSE).
"""


# ── meta.<lang>.yml : la surcharge de langue du catalogue ────────────────────

META_FR = """\
# Surcharge française du catalogue. Elle ne porte QUE `repo.title`,
# `repo.description`, et les `title` / `description` des sections, appariés
# par `id` et non par position.
#
# La langue par défaut de l'outil est l'anglais : `meta.yml` porte donc
# l'anglais, et ce fichier le français. Sans lui, une session anglaise lit les
# titres de sections tels qu'ils sont écrits dans `meta.yml`.

repo:
  title: {id}
  description: |
    À remplir : ce que ce catalogue apprend, et à qui.

sections:
  - id: premiers-pas
    title: Premiers pas
    description: À remplir.
"""


# ── conftest.py : le helper bilingue, qui doit vivre dans le catalogue ───────

CONFTEST = '''\
"""Les helpers partagés par les tests de ce catalogue.

POURQUOI CE FICHIER EST ICI ET PAS DANS DSOXLAB

Un test de lab doit rester jouable par un simple `pytest`, sans l'outil
installé : c'est le test de non-couplage du catalogue. Un
`from dsoxlab… import` en tête d'un fichier de tests le casserait. dsoxlab ne
reconnaît donc que la FORME de l'appel, `message(en=…, fr=…)`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def message(en: str, fr: str) -> str:
    """Le message d'une assertion, dans la langue de l'apprenant.

    Quand un test échoue, `dsoxlab check` affiche le message écrit par
    l'auteur : c'est la seule consigne que l'apprenant reçoit à cet instant. Or
    tout le reste du catalogue existe dans les deux langues, et ce texte-là ne
    peut pas : le contrat impose un nom de fichier unique,
    `challenge/tests/test_functional.py`. Il n'y a donc pas de version anglaise
    possible par duplication, d'où ce choix à l'exécution.

    Usage :

        from conftest import message

        assert chemin.exists(), message(
            en="/etc/myapp is missing. Create it.",
            fr="/etc/myapp est absent. Crée-le.",
        )
    """
    langue = os.environ.get("DSOXLAB_LANG", "en").lower()
    return fr if langue.startswith("fr") else en


def workdir_lab(fichier_test: str | Path) -> Path:
    """Le répertoire de travail du lab auquel appartient un fichier de test.

    `<lab>/challenge/work` par défaut ; `LAB_WORKDIR` le surcharge, ce dont le
    mode formateur se sert pour jouer la solution de référence ailleurs.
    """
    surcharge = os.environ.get("LAB_WORKDIR")
    if surcharge:
        return Path(surcharge)
    return Path(fichier_test).resolve().parents[2] / "challenge" / "work"


def exiger_workdir(workdir: Path, lab_id: str) -> None:
    """Skippe un lab qui n'a pas été démarré, au lieu de le noter 0.

    Un répertoire de travail absent ne dit pas que l'apprenant a échoué : il
    dit que `dsoxlab run` n'a pas été joué. Les deux appellent des gestes
    opposés, donc on skippe en le nommant. dsoxlab 0.4.1 et au-delà
    n'enregistrent aucune note quand TOUS les tests skippent.
    """
    if not workdir.is_dir():
        pytest.skip(
            f"le lab {lab_id} n'a pas été démarré : joue `dsoxlab run {lab_id}`"
        )
'''


# ── pyproject.toml : l'outillage de test du catalogue ────────────────────────

PYPROJECT = """\
# Ce dépôt n'est pas un paquet : ce fichier ne sert qu'à configurer les outils.
# dsoxlab s'installe en outil autonome (`uv tool install dsoxlab`) et apporte
# lui-même pytest et pytest-testinfra, pour qu'un catalogue n'ait aucun outil
# de test à installer.

[project]
name = "{id}"
version = "0.1.0"
description = "À remplir."
requires-python = ">=3.11"
dependencies = []

[tool.pytest.ini_options]
testpaths = ["tests", "labs"]
# `challenge/work` contient le travail de l'apprenant : il n'est jamais
# collecté, sous peine de ramasser ses fichiers temporaires comme des tests.
norecursedirs = ["challenge/work", ".git", ".venv"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "S"]
# S101 : `assert` est l'outil de travail d'un test, pas un défaut.
per-file-ignores = {{ "labs/**/tests/*.py" = ["S101"], "tests/*.py" = ["S101"] }}
"""


# ── Gouvernance : les documents que dix des douze catalogues portent ────────

CONTRIBUTING_EN = """\
# Contributing

## The one rule

**A lab is graded on the state of the system, never on the commands typed.**

A test that reads back what the learner wrote proves nothing: they could have
written it without understanding it, and they could have reached the same state
by another path that the test would wrongly reject.

```python
# NO: we re-read what the learner wrote
assert "myoption" in config_text

# YES: we ask the system what it actually does
assert service.is_running and service.is_enabled
```

## A lab is proven in both directions

Before a lab is merged:

1. `dsoxlab run <id>` then `dsoxlab check <id>` must score **0**. A test that
   is green before the work is not a test, it is an assumption about the setup.
2. With the reference solution in place, `dsoxlab check <id>` must score
   **100**.
3. `dsoxlab clean <id>` must give the machine back as it was. A lab that leaves
   something behind is not that lab's problem, it is the next lab's.

## Everything user-facing is bilingual

The statement exists in English and in French: `README.md` and `README.fr.md`,
`scenario.md` and `scenario.fr.md`, `lab.yaml` and `lab.fr.yaml`.

Assertion messages are a special case: the contract imposes a single file name,
`challenge/tests/test_functional.py`, so there is no English version by
duplication. Use the `message(en=…, fr=…)` helper of `conftest.py`.

## Before opening a pull request

```bash
dsoxlab validate-structure     # the contract, offline
pytest tests/                  # this repository's own guardrails
dsoxlab list-labs              # FIRST: a lab.yaml that raises disappears here
```

Run `list-labs` **before** `validate-structure`: the validator iterates over
the labs already loaded, so a lab whose `lab.yaml` raises passes validation
without a word.
"""

CONTRIBUTING_FR = """\
# Contribuer

## La règle unique

**Un lab est noté sur l'état du système, jamais sur les commandes tapées.**

Un test qui relit ce que l'apprenant a écrit ne prouve rien : il a pu l'écrire
sans le comprendre, et il a pu atteindre le même état par un autre chemin que
le test rejetterait à tort.

```python
# NON : on relit ce que l'apprenant a écrit
assert "monoption" in texte_de_config

# OUI : on demande au système ce qu'il fait vraiment
assert service.is_running and service.is_enabled
```

## Un lab est prouvé dans les deux sens

Avant qu'un lab soit fusionné :

1. `dsoxlab run <id>` puis `dsoxlab check <id>` doivent rendre **0**. Un test
   vert avant le travail n'est pas un test, c'est une hypothèse sur le setup.
2. La solution de référence posée, `dsoxlab check <id>` doit rendre **100**.
3. `dsoxlab clean <id>` doit rendre la machine telle qu'elle était. Un lab qui
   laisse quelque chose derrière lui n'embête pas ce lab-là, il embête le
   suivant.

## Tout ce qui s'affiche est bilingue

L'énoncé existe en anglais et en français : `README.md` et `README.fr.md`,
`scenario.md` et `scenario.fr.md`, `lab.yaml` et `lab.fr.yaml`.

Les messages d'assertion sont un cas à part : le contrat impose un nom de
fichier unique, `challenge/tests/test_functional.py`, donc il n'y a pas de
version anglaise par duplication. Emploie le helper `message(en=…, fr=…)` de
`conftest.py`.

## Avant d'ouvrir une demande de fusion

```bash
dsoxlab validate-structure     # le contrat, hors ligne
pytest tests/                  # les garde-fous propres à ce dépôt
dsoxlab list-labs              # D'ABORD : un lab.yaml qui lève disparaît ici
```

Joue `list-labs` **avant** `validate-structure` : le validateur itère sur les
labs déjà chargés, donc un lab dont le `lab.yaml` lève passe la validation sans
un mot.
"""

CODE_OF_CONDUCT_EN = """\
# Code of Conduct

## Our pledge

We pledge to make participation in this project a harassment-free experience
for everyone, regardless of age, body size, visible or invisible disability,
ethnicity, sex characteristics, gender identity and expression, level of
experience, education, socio-economic status, nationality, personal appearance,
race, religion, or sexual identity and orientation.

## Our standards

Examples of behaviour that contributes to a positive environment:

- showing empathy and kindness toward other people;
- being respectful of differing opinions, viewpoints and experiences;
- giving and gracefully accepting constructive feedback;
- accepting responsibility and apologising to those affected by our mistakes.

Examples of unacceptable behaviour:

- sexualised language or imagery, and sexual attention or advances of any kind;
- trolling, insulting or derogatory comments, and personal or political attacks;
- public or private harassment;
- publishing others' private information without their explicit permission.

## Enforcement

Instances of abusive, harassing or otherwise unacceptable behaviour may be
reported to the maintainers. All complaints will be reviewed and investigated
promptly and fairly, and the privacy and security of the reporter will be
respected.

## Attribution

This Code of Conduct is adapted from the [Contributor
Covenant](https://www.contributor-covenant.org), version 2.1.
"""

CODE_OF_CONDUCT_FR = """\
# Code de conduite

## Notre engagement

Nous nous engageons à faire de la participation à ce projet une expérience sans
harcèlement pour tout le monde, quels que soient l'âge, la corpulence, le
handicap visible ou invisible, l'origine ethnique, les caractéristiques
sexuelles, l'identité et l'expression de genre, le niveau d'expérience, le
niveau d'études, la situation économique, la nationalité, l'apparence, la race,
la religion, ou l'identité et l'orientation sexuelles.

## Nos règles

Des comportements qui contribuent à un environnement positif :

- faire preuve d'empathie et de bienveillance envers les autres ;
- respecter les opinions, les points de vue et les expériences différents ;
- donner et accepter de bonne grâce des retours constructifs ;
- assumer ses erreurs et s'excuser auprès de ceux qu'elles ont touchés.

Des comportements inacceptables :

- un langage ou une imagerie sexualisés, et toute attention ou avance sexuelle ;
- les provocations, les commentaires insultants ou dénigrants, et les attaques
  personnelles ou politiques ;
- le harcèlement, public ou privé ;
- la publication d'informations privées sans autorisation explicite.

## Application

Les comportements abusifs, harcelants ou autrement inacceptables peuvent être
signalés aux mainteneurs. Chaque signalement sera examiné rapidement et
équitablement, et la vie privée comme la sécurité de l'auteur du signalement
seront respectées.

## Attribution

Ce code de conduite est adapté du [Contributor
Covenant](https://www.contributor-covenant.org), version 2.1.
"""

SECURITY_EN = """\
# Security policy

## What this repository contains

A catalog of training labs: declarative files (`meta.yml`, `lab.yaml`),
statements in Markdown, Ansible playbooks, and `pytest` tests. **It executes
nothing by itself**: labs are played by the `dsoxlab` CLI, which lives in its
own repository.

## Reporting a vulnerability

Do **not** open a public issue. Use GitHub's private vulnerability reporting on
this repository, or write to the maintainers.

Please include what you found, how to reproduce it, and what you think the
impact is. You will get an acknowledgement, and a fix or an explanation of why
it is not one.

## What counts as a vulnerability here

- **A secret committed by mistake**: a token, a private key, a vault password.
  Report it even if it looks revoked: it stays in git history.
- **A lab that runs something unexpected on the learner's machine**, beyond
  what its statement announces.
- **A reference solution readable in clear text** where it is meant to be
  encrypted: it is not a system flaw, but it destroys the exercise.

## What does not

A lab that deliberately sets up a vulnerable system is the subject being
taught, not a defect. A lab that asks the learner to weaken a configuration
does so inside its own machine, which `dsoxlab destroy` gives back.
"""

SECURITY_FR = """\
# Politique de sécurité

## Ce que contient ce dépôt

Un catalogue de labs de formation : des fichiers déclaratifs (`meta.yml`,
`lab.yaml`), des énoncés en Markdown, des playbooks Ansible et des tests
`pytest`. **Il n'exécute rien par lui-même** : les labs sont joués par la CLI
`dsoxlab`, qui vit dans son propre dépôt.

## Signaler une vulnérabilité

N'ouvre **pas** d'issue publique. Emploie le signalement privé de GitHub sur ce
dépôt, ou écris aux mainteneurs.

Indique ce que tu as trouvé, comment le reproduire, et l'impact que tu lui
prêtes. Tu recevras un accusé de réception, puis une correction ou l'explication
de pourquoi ce n'en est pas une.

## Ce qui compte comme une vulnérabilité ici

- **Un secret commité par erreur** : un jeton, une clé privée, un mot de passe
  de vault. Signale-le même s'il semble révoqué : il reste dans l'historique
  git.
- **Un lab qui exécute sur le poste de l'apprenant autre chose** que ce que son
  énoncé annonce.
- **Une solution de référence lisible en clair** là où elle est censée être
  chiffrée : ce n'est pas une faille du système, mais cela détruit l'exercice.

## Ce qui n'en est pas

Un lab qui monte délibérément un système vulnérable enseigne précisément ce
sujet, ce n'est pas un défaut. Un lab qui demande d'affaiblir une configuration
le fait dans sa propre machine, que `dsoxlab destroy` rend.
"""

CHANGELOG_EN = """\
# Changelog

All notable changes to this catalog are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this catalog
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**What a version means here.** A catalog is not a library: a MINOR bump adds
labs, a PATCH fixes a statement or a test without changing what a lab proves,
and a MAJOR renames or removes labs, which breaks the progress already recorded
by learners.

## [Unreleased]

### Added

- The catalog skeleton, created by `dsoxlab new catalog`.
"""

CHANGELOG_FR = """\
# Journal des modifications

Les changements notables de ce catalogue sont consignés ici. Le format suit
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), et ce catalogue suit
le [versionnage sémantique](https://semver.org/lang/fr/).

**Ce qu'une version veut dire ici.** Un catalogue n'est pas une bibliothèque :
un incrément MINEUR ajoute des labs, un CORRECTIF corrige un énoncé ou un test
sans changer ce qu'un lab prouve, et un incrément MAJEUR renomme ou retire des
labs, ce qui casse la progression déjà enregistrée des apprenants.

## [Non publié]

### Ajouté

- Le squelette du catalogue, créé par `dsoxlab new catalog`.
"""


# ── Intégration continue : les trois contrôles qu'un catalogue doit jouer ───

CI = """\
# La CI d'un catalogue de labs joue trois contrôles, et aucun ne demande
# d'infrastructure : ils sont donc tous jouables sur un runner public.
#
#   1. le contrat est valide, hors ligne (`validate-structure`) ;
#   2. les garde-fous propres au dépôt passent (`pytest tests/`) ;
#   3. le python du catalogue est propre (`ruff`).
#
# Ce qu'elle NE fait PAS, et c'est délibéré : jouer les labs. Un lab `vm`
# demande un hyperviseur, et un lab `shell` demande les outils de son domaine.
# L'attestation se joue sur une machine de formateur, et son verdict est
# versionné dans `validation-labs.json`.
#
# Les actions sont épinglées par SHA de 40 caractères : un tag est déplaçable,
# un SHA non.

name: CI

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  contrat:
    name: Contract, guardrails and lint
    runs-on: ubuntu-24.04
    steps:
      - name: Harden the runner
        uses: step-security/harden-runner@{sha_harden} # v2.22.0
        with:
          egress-policy: audit

      - name: Checkout
        uses: actions/checkout@{sha_checkout} # v7.0.1
        with:
          persist-credentials: false

      - name: Install uv
        uses: astral-sh/setup-uv@{sha_uv} # v10.2.0

      - name: Install dsoxlab
        run: uv tool install dsoxlab

      - name: List the labs
        # D'ABORD : un `lab.yaml` qui lève au parsing disparaît du catalogue
        # sans un mot, et `validate-structure` n'itère que sur ce qui a chargé.
        # Un catalogue vide ici est un défaut, pas un succès.
        run: |
          dsoxlab list-labs
          test "$(dsoxlab list-labs --json | python3 -c \\
            'import json,sys; print(len(json.load(sys.stdin)["labs"]))')" -gt 0

      - name: Validate the contract
        run: dsoxlab validate-structure

      - name: Repository guardrails
        run: uv run --with pytest --with pyyaml pytest tests/ -q

      - name: Lint
        run: uvx ruff check .
"""

PRE_COMMIT = """\
# Les hooks de ce catalogue. Ils mesurent ce qu'une relecture ne voit pas.
#
# `pass_filenames: false` partout : ces contrôles portent sur le dépôt entier,
# pas sur les fichiers d'un commit. Un lab retiré du `meta.yml` casse le
# catalogue sans qu'aucun fichier du commit ne le montre.

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: local
    hooks:
      - id: contrat-valide
        name: le contrat du catalogue est valide
        entry: dsoxlab validate-structure
        language: system
        pass_filenames: false

      - id: garde-fous
        name: les garde-fous du dépôt passent
        entry: uv run --with pytest --with pyyaml pytest tests/ -q
        language: system
        pass_filenames: false

      # La règle d'écriture du projet interdit le tiret cadratin en français :
      # il se remplace par la ponctuation qui dit son rôle. Mesuré sur un
      # catalogue sans ce hook : 51 `lab.fr.yaml`, 172 README de labs et 86
      # scénarios en portaient un.
      - id: pas-de-tiret-cadratin
        name: ni emoji ni tiret cadratin dans ce que lit l'apprenant
        entry: python3 tests/outils/pas_de_tiret_cadratin.py
        language: system
        pass_filenames: false
"""


# ── Les garde-fous : ce qu'un catalogue doit vérifier sur lui-même ──────────

TEST_CONTRAT = '''\
"""Le catalogue tient ses propres promesses, et pas seulement le contrat.

`dsoxlab validate-structure` vérifie le CONTRAT. Ces tests vérifient ce que ce
dépôt-ci promet en plus, et que l'outil ne peut pas connaître.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

RACINE = pathlib.Path(__file__).resolve().parent.parent


def _labs() -> list[pathlib.Path]:
    return sorted(RACINE.glob("labs/**/lab.yaml"))


def test_aucun_lab_na_disparu_en_silence() -> None:
    """Un répertoire de lab sans `lab.yaml` lisible est un défaut muet.

    `validate-structure` itère sur ce qui a CHARGÉ : un `lab.yaml` qui lève au
    parsing disparaît du catalogue en silence, et la validation passe sans un
    mot. Ce test est le seul qui attrape ce cas.

    Deux situations que « zéro lab » confond, et qu'on sépare donc :

        labs/ vide                   un catalogue neuf, rien à conclure
        labs/ peuplé, aucun lab.yaml un défaut, et on le nomme
    """
    repertoires = [
        chemin
        for chemin in (RACINE / "labs").rglob("*")
        if chemin.is_dir() and not chemin.name.startswith(".")
    ]
    if not repertoires:
        pytest.skip(
            "labs/ est vide : catalogue neuf, crée un lab avec "
            "`dsoxlab new lab <id>`"
        )

    assert _labs(), (
        f"{len(repertoires)} répertoire(s) sous labs/ mais aucun lab.yaml "
        "lisible : un lab.yaml lève au parsing et a disparu du catalogue en "
        "silence. Joue `dsoxlab list-labs` pour le voir."
    )


def test_chaque_lab_est_declare_dans_le_meta() -> None:
    """Un lab présent sur le disque mais absent du meta.yml n'est pas ordonné.

    Il reste jouable, mais il n'apparaît dans aucune section : ni `list-labs`
    ni `next` ne savent où le placer.
    """
    meta = yaml.safe_load((RACINE / "meta.yml").read_text(encoding="utf-8"))
    declares = {
        chemin
        for section in (meta.get("sections") or [])
        for chemin in (section.get("labs") or [])
    }
    sur_le_disque = {
        p.parent.relative_to(RACINE / "labs").as_posix() for p in _labs()
    }
    orphelins = sorted(sur_le_disque - declares)

    assert not orphelins, (
        f"{len(orphelins)} lab(s) sur le disque mais absents des sections du "
        f"meta.yml : {orphelins}"
    )


def test_le_meta_ne_declare_pas_de_lab_absent() -> None:
    """L'inverse, que `validate-structure` ne vérifie pas.

    Le validateur itère sur `discover_labs()`, donc sur ce qui existe : un lab
    déclaré dans le meta.yml mais absent du disque passe sans un mot.
    """
    meta = yaml.safe_load((RACINE / "meta.yml").read_text(encoding="utf-8"))
    declares = {
        chemin
        for section in (meta.get("sections") or [])
        for chemin in (section.get("labs") or [])
    }
    manquants = sorted(
        c for c in declares if not (RACINE / "labs" / c / "lab.yaml").is_file()
    )

    assert not manquants, (
        f"{len(manquants)} lab(s) déclarés dans le meta.yml mais absents du "
        f"disque : {manquants}"
    )


def test_parite_des_langues() -> None:
    """Un énoncé traduit d'un seul côté est signalé, pas laissé à la relecture."""
    boiteux = []
    for lab in _labs():
        base = lab.parent
        for nom in ("README", "scenario"):
            en = base / f"{nom}.md"
            fr = base / f"{nom}.fr.md"
            if en.is_file() != fr.is_file():
                boiteux.append(f"{base.name}/{nom}")

    assert not boiteux, f"traduits d'un seul côté : {boiteux}"
'''

TEST_TIRET = '''\
#!/usr/bin/env python3
"""Ni emoji ni tiret cadratin dans ce que lit l'apprenant.

La règle d'écriture du projet interdit le tiret cadratin en français : il se
remplace par la ponctuation qui dit son rôle (deux-points s'il introduit,
point-virgule s'il rompt, parenthèses s'il met entre), jamais par un autre
tiret.

Ce contrôle porte sur ce que l'apprenant LIT : les énoncés français, les titres
des `lab.fr.yaml`, et les deux README. Pas sur le code, pas sur les
commentaires anglais.

Mesuré sur un catalogue qui n'avait pas ce hook : 51 `lab.fr.yaml`, 172 README
de labs et 86 scénarios portaient un tiret cadratin. Une campagne de
remplacement sans le hook serait défaite au prochain lab écrit.
"""

from __future__ import annotations

import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent.parent
CADRATIN = "\\u2014"
MOTIFS = ("README.fr.md", "scenario.fr.md", "lab.fr.yaml", "hints.yaml")


def main() -> int:
    fautifs: list[str] = []
    cibles = [RACINE / "README.fr.md", RACINE / "meta.fr.yml"]
    for motif in MOTIFS:
        cibles += sorted(RACINE.glob(f"labs/**/{motif}"))

    for chemin in cibles:
        if not chemin.is_file():
            continue
        for numero, ligne in enumerate(
            chemin.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if CADRATIN in ligne:
                relatif = chemin.relative_to(RACINE)
                fautifs.append(f"{relatif}:{numero}  {ligne.strip()[:80]}")

    if fautifs:
        print(f"{len(fautifs)} ligne(s) avec un tiret cadratin en français :",
              file=sys.stderr)
        for f in fautifs:
            print(f"  {f}", file=sys.stderr)
        print("\\nRemplace-le par la ponctuation qui dit son rôle : deux-points "
              "s'il introduit, point-virgule s'il rompt, parenthèses s'il met "
              "entre.", file=sys.stderr)
        return 1

    print(f"{len(cibles)} fichier(s) lus par l'apprenant, aucun tiret cadratin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


#: Le workflow de publication : empaquette, atteste hors du build, publie.
#
# Un catalogue neuf n'en avait pas, et n'avait donc AUCUN moyen de publier :
# mesuré le 2026-10-17, quatre catalogues ont dû le recevoir à la main, et la
# copie a échoué sur un `tar` qui réclamait des fichiers propres au dépôt
# d'origine. D'où les deux listes de son bundle, REQUIS et FACULTATIFS, et le
# cliquet de `tests/test_socle_du_catalogue.py` qui compare la première au
# contenu réel du socle.
RELEASE = r"""# Publie une release GitHub avec un bundle tar.gz du catalogue de labs.
# Pas de PyPI, pas de wheel : ce dépôt est du CONTENU. L'artefact publié est
# une archive tar.gz du catalogue (labs + contrat), plus son empreinte SHA-256.
# Déclenché par un tag `vX.Y.Z`.
#
# TROIS JOBS, ET LEUR SÉPARATION EST LE SUJET. Le premier construit, le
# deuxième atteste, le troisième publie. Ce découpage n'est pas cosmétique :
# c'est ce qui fait passer la provenance de SLSA Build Level 2 à Level 3.
# Attester depuis le job de build donnerait le niveau 2, parce que le processus
# qui fabrique l'archive serait aussi celui qui signe ce qu'il en dit. Ici la
# signature vit dans `attester.yml`, un workflow réutilisable qui ne voit que
# l'empreinte, et qui est le seul à porter `attestations: write`.
#
# Chaîne de provenance attachée à chaque release (cible « binaire ») :
#   - provenance SLSA niveau 3 → `gh attestation verify --signer-workflow …`
#   - provenance.intoto.jsonl  → asset attendu par Scorecard Signed-Releases
#   - signature Cosign keyless → `cosign verify-blob` (voir RELEASING.md)
name: Release

on:
  push:
    tags:
      - "v*"

# Deny-by-default : chaque job opte pour les scopes dont il a besoin.
permissions: {{}}

concurrency:
  group: release-${{{{ github.ref }}}}
  cancel-in-progress: false

jobs:
  # 1. Construire. Ce job ne peut ni attester ni publier : il n'a que la
  #    lecture. Tout ce qu'il produit part en artefact de workflow.
  build:
    name: Construire le bundle tar.gz
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    permissions:
      contents: read
    outputs:
      pkg: ${{{{ steps.bundle.outputs.pkg }}}}
      digest: ${{{{ steps.bundle.outputs.digest }}}}
    steps:
      - name: Harden the runner
        uses: step-security/harden-runner@351661ca32ac09a36dc5ee2d536e3128f2a3c8ed # v2.22.0
        with:
          egress-policy: audit

      - name: Checkout
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Build tar.gz bundle
        id: bundle
        run: |
          set -euo pipefail
          VERSION="${{GITHUB_REF_NAME#v}}"
          PKG="{id}-${{VERSION}}"
          # Contenu publié : le catalogue de labs, le contrat, l'outillage et
          # la gouvernance. Exclus : pilotage local, généré, VCS.
          #
          # DEUX LISTES, ET LA DIFFÉRENCE N'EST PAS UN DÉTAIL
          #
          # Un chemin absent fait échouer tar sous `set -euo pipefail`, et la
          # release entière avec lui. Or certains chemins ne sont pas requis :
          # ils sont propres à certains catalogues. `curriculums.yml` est un
          # programme de certification, `mise.toml` et `validation-labs.json`
          # de l'outillage, `scripts` et `uv.lock` n'existent pas encore dans
          # un catalogue qui vient d'être créé.
          #
          # Mesuré le 2026-10-17 : le premier tag d'un catalogue n'a RIEN
          # publié pour cette raison, sur un « Cannot stat » que personne
          # n'allait chercher dans un job de build.
          #
          # Un REQUIS qui manque reste une erreur, et le message le nomme au
          # lieu de laisser tar parler depuis le milieu de sa liste.
          REQUIS=(labs meta.yml meta.fr.yml conftest.py pyproject.toml tests
                  README.md README.fr.md LICENSE CONTRIBUTING.md
                  CONTRIBUTING.fr.md CODE_OF_CONDUCT.md CODE_OF_CONDUCT.fr.md
                  SECURITY.md SECURITY.fr.md RELEASING.md RELEASING.fr.md
                  CHANGELOG.md CHANGELOG.fr.md)
          FACULTATIFS=(curriculums.yml mise.toml validation-labs.json scripts uv.lock)

          manquants=()
          for chemin in "${{REQUIS[@]}}"; do
            [ -e "$chemin" ] || manquants+=("$chemin")
          done
          if [ "${{#manquants[@]}}" -gt 0 ]; then
            printf 'Release impossible : %s absent(s) de la racine du dépôt.\n' \
              "${{manquants[*]}}" >&2
            exit 1
          fi

          A_EMPAQUETER=("${{REQUIS[@]}}")
          for chemin in "${{FACULTATIFS[@]}}"; do
            [ -e "$chemin" ] && A_EMPAQUETER+=("$chemin")
          done

          tar --exclude-vcs \
              --exclude="todo" \
              --exclude="ROADMAP-*.md" \
              --exclude=".venv" \
              --exclude="__pycache__" \
              --exclude="*.pyc" \
              --exclude=".pytest_cache" \
              --exclude=".mypy_cache" \
              --exclude=".ruff_cache" \
              --exclude=".dsoxlab-context.json" \
              --exclude=".dsoxlab.db" \
              -czf "${{PKG}}.tar.gz" \
              "${{A_EMPAQUETER[@]}}"
          sha256sum "${{PKG}}.tar.gz" > "${{PKG}}.tar.gz.sha256"
          # L'empreinte nue, pour la passer au workflow d'attestation : il
          # signe une empreinte, pas un fichier, et n'a donc jamais l'archive
          # entre les mains.
          DIGEST="$(cut -d' ' -f1 < "${{PKG}}.tar.gz.sha256")"
          {{
            echo "pkg=${{PKG}}"
            echo "digest=${{DIGEST}}"
          }} >> "$GITHUB_OUTPUT"

      - name: Publier l'archive en artefact de workflow
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: bundle
          path: |
            ${{{{ steps.bundle.outputs.pkg }}}}.tar.gz
            ${{{{ steps.bundle.outputs.pkg }}}}.tar.gz.sha256
          if-no-files-found: error
          retention-days: 1

  # 2. Attester, hors de portée du build. Le workflow appelé est le seul du
  #    dépôt à recevoir `attestations: write`, et il ne reçoit qu'une empreinte.
  provenance:
    name: Provenance SLSA
    needs: build
    # POURQUOI `./` ET NON `$/`, LA FORME QUE ZIZMOR RECOMMANDE ICI.
    #
    # `$/` est la forme « self-repository », publiée par GitHub en juillet
    # 2026. Sur le fond elle est meilleure : elle ne dépend pas de l'état du
    # système de fichiers, donc elle ne peut pas charger un fichier qu'une
    # étape précédente aurait déposé. Elle a pourtant été retirée d'ici, et la
    # raison tient en une phrase : l'outillage de sécurité ne sait pas encore
    # la lire, et un analyseur qui ne comprend pas une construction ne peut pas
    # la juger sûre.
    #
    # Mesuré le 2026-09-15, sur cette ligne exactement :
    #   - actionlint 1.7.12 la rejette comme un format invalide ;
    #   - zizmor 1.26.1 refuse de charger le fichier et n'audite plus RIEN ;
    #   - Plumber la prend pour une action tierce non épinglée et venant d'une
    #     source non autorisée : deux constats HIGH, score 70/100 au lieu de
    #     100/100.
    #
    # Le workflow appelé est celui qui SIGNE la provenance. C'est la dernière
    # ligne du dépôt sur laquelle se priver du regard des analyseurs. `./` est
    # comprise par les trois, et zizmor ne lui reproche qu'un point de style,
    # acquitté juste en dessous.
    #
    # À reconsidérer quand actionlint et Plumber sauront lire `$/`.
    uses: ./.github/workflows/attester.yml # zizmor: ignore[self-repository]
    permissions:
      id-token: write
      attestations: write
      contents: read
    with:
      subject-name: ${{{{ needs.build.outputs.pkg }}}}.tar.gz
      subject-digest: sha256:${{{{ needs.build.outputs.digest }}}}

  # 3. Publier. Ce job écrit la release, mais il ne peut pas attester : sans
  #    `attestations: write`, il ne saurait pas fabriquer la provenance qu'il
  #    attache.
  publish:
    name: Publier la release
    needs: [build, provenance]
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    permissions:
      contents: write # créer la release et y attacher les assets
      id-token: write # OIDC keyless pour la signature cosign
    steps:
      - name: Harden the runner
        uses: step-security/harden-runner@351661ca32ac09a36dc5ee2d536e3128f2a3c8ed # v2.22.0
        with:
          egress-policy: audit

      - name: Récupérer l'archive
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1
        with:
          name: bundle

      - name: Récupérer le bundle de provenance
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1
        with:
          name: provenance

      - name: Install Cosign
        uses: sigstore/cosign-installer@6f9f17788090df1f26f669e9d70d6ae9567deba6 # v4.1.2

      # Signature keyless (OIDC + log Rekor public) : aucune clé privée stockée.
      # PKG vient de l'environnement : c'est une variable shell, pas une
      # interpolation ${{{{ }}}} dans un run (règle template-injection).
      - name: Sign the bundle (keyless Sigstore)
        env:
          PKG: ${{{{ needs.build.outputs.pkg }}}}
        run: |
          set -euo pipefail
          cosign sign-blob --yes \
            --bundle "${{PKG}}.tar.gz.cosign.bundle" \
            "${{PKG}}.tar.gz"

      # L'archive est vérifiée AVANT d'être publiée : son empreinte doit être
      # celle que le job de build a annoncée et que le workflow d'attestation a
      # signée. Sans ce contrôle, un artefact de workflow altéré entre les deux
      # jobs serait publié avec une provenance qui ne le décrit pas.
      - name: Vérifier que l'archive est bien celle qui a été attestée
        env:
          PKG: ${{{{ needs.build.outputs.pkg }}}}
          DIGEST: ${{{{ needs.build.outputs.digest }}}}
        run: |
          set -euo pipefail
          echo "${{DIGEST}}  ${{PKG}}.tar.gz" | sha256sum -c -

      - name: Create GitHub release
        env:
          GH_TOKEN: ${{{{ github.token }}}}
          PKG: ${{{{ needs.build.outputs.pkg }}}}
        run: |
          set -euo pipefail
          # `--repo` est obligatoire ICI : ce job ne fait aucun checkout, donc
          # `gh` n'a pas de `.git` où lire le dépôt, et répondait
          # « fatal: not a git repository ». Mesuré sur la première release
          # jamais lancée de la flotte.
          gh release create "${{GITHUB_REF_NAME}}" \
            --repo "${{GITHUB_REPOSITORY}}" \
            --title "${{GITHUB_REF_NAME}}" \
            --generate-notes \
            "${{PKG}}.tar.gz" \
            "${{PKG}}.tar.gz.sha256" \
            "${{PKG}}.tar.gz.cosign.bundle" \
            provenance.intoto.jsonl
"""


#: Le workflow réutilisable qui signe la provenance, appelé par `release.yml`.
#
# Il est à part parce que SLSA Build Level 3 exige que la signature se fasse
# hors de portée du build : attester depuis le job qui fabrique l'archive
# donnerait le niveau 2, le processus qui construit étant aussi celui qui
# signe ce qu'il en dit.
ATTESTER = r"""# Atteste la provenance d'un artefact, et rien d'autre.
#
# POURQUOI CE FICHIER EXISTE, alors que trois lignes dans release.yml
# suffiraient à produire une attestation. C'est la différence entre SLSA Build
# Level 2 et Level 3, et elle tient à un seul mot : isolation.
#
# La documentation GitHub la formule ainsi : « Artifact attestations by itself
# provides SLSA v1.0 Build Level 2 », et « Reusable workflows can provide
# isolation between the build process and the calling workflow, to meet SLSA
# v1.0 Build Level 3 ».
#
# Autrement dit : tant que le job qui CONSTRUIT l'archive est aussi celui qui
# SIGNE sa provenance, rien n'empêche techniquement le processus de build de
# fabriquer une provenance qui ment. Le niveau 3 exige que la signature se fasse
# hors de sa portée. Ce workflow réutilisable est cette frontière : il est le
# seul du dépôt à recevoir la permission `attestations: write`, il ne voit
# jamais le contenu de l'archive, seulement son empreinte, et il n'exécute
# aucun code du dépôt.
#
# Le badge du README annonçait déjà le niveau 3 avant ce fichier, alors que le
# workflow produisait du niveau 2. C'est ce qu'il corrige.
#
# La preuve se lit côté vérification. L'identité inscrite dans le certificat
# n'est pas celle du workflow de release mais celle de CE fichier, ce qui se
# contrôle avec :
#
#   gh attestation verify <archive> \
#     --repo <owner>/<repo> \
#     --signer-workflow <owner>/<repo>/.github/workflows/attester.yml
#
# Une archive attestée depuis le job de build échouerait à ce contrôle.
name: Attester la provenance

on:
  workflow_call:
    inputs:
      subject-name:
        description: "Nom de l'artefact tel qu'il doit apparaître dans l'attestation."
        required: true
        type: string
      subject-digest:
        description: "Empreinte de l'artefact, au format algorithme:hexadécimal."
        required: true
        type: string
      artefact-provenance:
        description: "Nom de l'artefact de workflow où déposer le bundle de provenance."
        required: false
        default: provenance
        type: string

# Deny-by-default : le job opte pour les scopes dont il a besoin.
permissions: {{}}

jobs:
  attester:
    name: Attester la provenance du bundle
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    permissions:
      # Les deux permissions qui signent. Elles ne sont accordées nulle part
      # ailleurs dans ce dépôt, et c'est tout l'intérêt.
      id-token: write # OIDC : l'identité qui signe est celle de ce workflow
      attestations: write # enregistrer l'attestation auprès de GitHub
      contents: read
    steps:
      - name: Harden the runner
        uses: step-security/harden-runner@351661ca32ac09a36dc5ee2d536e3128f2a3c8ed # v2.22.0
        with:
          egress-policy: audit

      # Aucun checkout : ce job n'a pas à lire le dépôt. Il reçoit une
      # empreinte et signe cette empreinte. Moins il en voit, moins il peut
      # être influencé par ce qu'il atteste.
      - name: Attester la provenance du build
        id: attest
        uses: actions/attest-build-provenance@4d101475d8b20a2381f78447822ac1eab6504dd8 # v4.2.2
        with:
          subject-name: ${{{{ inputs.subject-name }}}}
          subject-digest: ${{{{ inputs.subject-digest }}}}

      # Scorecard Signed-Releases cherche un asset `*.intoto.jsonl` attaché à la
      # release, et non l'attestation seule : ce sont deux artefacts distincts.
      # Le bundle repart donc en artefact de workflow, pour que le job de
      # publication l'attache sans jamais avoir eu le droit de le produire.
      - name: Déposer le bundle de provenance
        env:
          BUNDLE: ${{{{ steps.attest.outputs.bundle-path }}}}
        run: |
          set -euo pipefail
          cp "${{BUNDLE}}" provenance.intoto.jsonl
          ls -l provenance.intoto.jsonl

      - name: Publier le bundle en artefact de workflow
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: ${{{{ inputs.artefact-provenance }}}}
          path: provenance.intoto.jsonl
          if-no-files-found: error
          retention-days: 1
"""


#: La marche à suivre pour publier, en anglais.
RELEASING_EN = r"""# Releasing {id}

**Language:** [English](./RELEASING.md) · [Français](./RELEASING.fr.md)

This repository ships **lab content**, not a Python package. A release
publishes a **`tar.gz` bundle** of the catalogue as an asset of a GitHub
Release: no PyPI, no wheel, no external artifact registry.

## What a release contains

The `release.yml` workflow builds
`{id}-<version>.tar.gz` with:

- `labs/`, `meta.yml`, `meta.fr.yml`, `curriculums.yml`, `conftest.py`,
  `pyproject.toml`, `uv.lock` and `mise.toml`,
- `scripts/` and `tests/`, because a catalogue that claims to validate itself
  must ship the means to do so,
- `validation-labs.json`, the proof that every lab was played in both
  directions by the real dsoxlab commands, with its date and the versions of dsoxlab and of the tools the labs use,
- the governance documents (`README`, `LICENSE`, `CONTRIBUTING`,
  `CODE_OF_CONDUCT`, `SECURITY`, `CHANGELOG`, `RELEASING`), **in both
  languages**: the
  archive is what someone who does not have the repository receives.

The lock file travels with `pyproject.toml` deliberately. A `>=` constraint
lets every installation resolve whatever it likes; an archive that claims to
ship the means to validate itself would not be saying *with what*.

It **excludes** the reference solutions (`solution/`, encrypted, they are the
answers), unversioned local steering and generated files (caches, dsoxlab
runtime state). An exclusion that matches nothing does not fail `tar`, unlike a path that is listed but absent,
which has already broken a release in the sibling Linux catalogue.

Four artifacts accompany the archive:

| Artifact | Purpose |
| --- | --- |
| `<pkg>.tar.gz.sha256` | integrity digest |
| `provenance.intoto.jsonl` | SLSA provenance, what Scorecard Signed-Releases reads |
| `<pkg>.tar.gz.cosign.bundle` | keyless Cosign signature bundle |
| (registry side) | GitHub's native build attestation |

## Why three jobs, and not one

The workflow is split into **build**, **attest**, **publish**, and that split is
the only thing separating SLSA Build Level 2 from Level 3.

GitHub's documentation puts it in two sentences: "Artifact attestations by
itself provides SLSA v1.0 Build Level 2", and "Reusable workflows can provide
isolation between the build process and the calling workflow, to meet SLSA v1.0
Build Level 3". As long as the job that builds the archive is also the one that
signs its provenance, nothing technically stops the build process from
producing provenance that lies. Level 3 requires the signing to happen out of
its reach.

Hence `.github/workflows/attester.yml`, called as a reusable workflow:

- it is the **only workflow in the repository** granted `attestations: write`;
- it receives **a name and a digest**, never the archive nor the repository: it
  performs no `checkout`;
- the publish job can write the release but **cannot attest**, lacking that
  permission;
- the archive is re-checked against its digest **before** publication, so that
  an artifact altered between two jobs is not published with provenance that
  does not describe it.

The call reads `uses: ./.github/workflows/attester.yml`, and not the newer
`$/` "self-repository" form, even though zizmor recommends the latter. The
reason is worth recording: security tooling cannot read `$/` yet, and an
analyser that does not understand a construct cannot judge it safe. Measured on
2026-09-15, on that exact line: actionlint rejects it as an invalid format,
zizmor 1.26.1 refuses to load the file and audits nothing at all, and Plumber
takes it for an unpinned third-party action from an unauthorised source, two
HIGH findings and a score of 70/100 instead of 100/100. The called workflow is
the one that *signs*: it is the last line in the repository on which to give up
the analysers' scrutiny.

## Cutting a release

1. Check that the catalogue is green, not merely shippable:

   ```bash
   dsoxlab validate-structure --check-urls
   pre-commit run --all-files --hook-stage pre-push
   python3 scripts/verify-solutions.py --deux-sens --check
   python3 scripts/valider-labs.py      # writes validation-labs.json
   ```

2. **Re-attest the labs that changed since their verdict.** A lab whose tests,
   files, shared `conftest.py` or descriptors changed after the commit that
   recorded its verdict is no longer attested by `validation-labs.json`. From
   the site repository (`test-astro-5`, cloned next to this one), run:

   ```bash
   python3 scripts/reattester-labs.py --depot {id}           # plan and safeguards
   python3 scripts/reattester-labs.py --depot {id} --apply   # replay and commit
   ```

   The script replays each lab marked "to re-attest" through
   `scripts/valider-labs.py`, one at a time (modified tests and labs first,
   then shared `conftest.py`, then descriptors), checks that the
   `validation-labs.json` diff only touches those labs, reruns `--check` and
   `pytest tests/`, and makes a **local** commit of the record alone. It
   refuses a dirty repository and an active lab. A RED verdict is not
   committed: fix the lab, then run it again.

   Before tagging, run the dry-run again: it must print
   **"0 lab(s) à réattester"**. Then push the record commit with the rest of
   the release.

3. Move the `CHANGELOG.md` and `CHANGELOG.fr.md` entries under a new version.
4. Tag and push the tag, which triggers `release.yml`:

   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

5. The workflow builds the `tar.gz`, attests its provenance, signs it keyless
   and creates the GitHub Release with auto-generated notes.

## Verifying a release

Integrity and contents:

```bash
sha256sum -c {id}-<version>.tar.gz.sha256
tar tzf {id}-<version>.tar.gz | head
```

Build provenance. Proves the archive really was produced by this repository's
workflow, and not rebuilt by someone else:

```bash
gh attestation verify {id}-<version>.tar.gz \
  --repo stephrobert/{id}
```

**The check that establishes Build Level 3** names the signing workflow. It
fails if the provenance was produced anywhere other than the isolated attester
workflow, and it is the one to run on the first release to confirm the chain
holds:

```bash
gh attestation verify {id}-<version>.tar.gz \
  --repo stephrobert/{id} \
  --signer-workflow stephrobert/{id}/.github/workflows/attester.yml
```

Keyless Cosign signature. **Both** certificate flags are mandatory: without
them, `cosign verify-blob` accepts any identity, which empties the verification
of its meaning.

```bash
cosign verify-blob \
  --bundle {id}-<version>.tar.gz.cosign.bundle \
  --certificate-identity-regexp "https://github.com/stephrobert/{id}/.github/workflows/release.yml@.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  {id}-<version>.tar.gz
```

> **Cosign version trap.** The CI installs **Cosign 3.x**, which writes a new
> bundle format. A local **Cosign 2.x** answers `no signatures found` on a
> perfectly signed archive: the release is not broken, the local tool cannot
> read the format. Check `cosign version` and align it before concluding
> anything.

## GitHub settings to do once

Two workflows need configuration that does not live in the repository:

- **`plumber.yml`** expects a `security` environment, restricted to the `main`
  branch, holding the `PLUMBER_ADMIN_TOKEN` secret: a fine-grained PAT with
  Administration, Contents and Metadata read access. Without it the workflow
  still runs, on the job token, but the `branchMustBeProtected` control abstains
  and the score stays incomplete.
- **Protection of the `main` branch**, through the "Protection de main" ruleset:
  that is what Scorecard and Plumber measure. Linear history, deletion and force
  pushes forbidden, pull request required with review thread resolution, and the
  CI jobs as required status checks.

### The "Protection de main" ruleset, ready to apply

A ruleset is a GitHub setting, not a file of the repository: it does not travel
with a `git push`. It is set **once**, after the repository is created and the
CI has run for the first time (a required check must have run at least once for
GitHub to offer it). The payload below takes over the rules of the sibling
catalogs; the contexts are the job names of `ci.yml`, the CodeQL matrix giving
two.

No approval is required (`required_approving_review_count: 0`): the repository
has a single maintainer, who cannot approve their own pull request. Going
through a pull request, resolving threads and a green CI stay mandatory.

```bash
gh api --method POST repos/stephrobert/{id}/rulesets \
  --input - <<'JSON'
{{
  "name": "Protection de main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {{"ref_name": {{"include": ["~DEFAULT_BRANCH"], "exclude": []}}}},
  "rules": [
    {{"type": "deletion"}},
    {{"type": "non_fast_forward"}},
    {{"type": "required_linear_history"}},
    {{"type": "pull_request", "parameters": {{
      "required_approving_review_count": 0,
      "dismiss_stale_reviews_on_push": true,
      "require_code_owner_review": false,
      "require_last_push_approval": false,
      "required_review_thread_resolution": true}}}},
    {{"type": "required_status_checks", "parameters": {{
      "strict_required_status_checks_policy": true,
      "required_status_checks": [
        {{"context": "Zizmor (workflow static analysis)"}},
        {{"context": "Actionlint (workflow syntax)"}},
        {{"context": "Poutine (CI/CD exploit chains)"}},
        {{"context": "Pre-commit parity (all hooks)"}},
        {{"context": "Contrat du catalogue (leçons jumelées comprises)"}},
        {{"context": "CodeQL (python)"}},
        {{"context": "CodeQL (actions)"}}]}}}}
  ]
}}
JSON
```

This block has **never been applied**: the repository does not exist on GitHub
yet. On first application, read the created ruleset back in *Settings > Rules*
and check that a direct push to `main` is refused.
"""


#: La marche à suivre pour publier, en français.
RELEASING_FR = r"""# Publier une version de {id}

**Langue :** [English](./RELEASING.md) · [Français](./RELEASING.fr.md)

Ce dépôt livre du **contenu de labs**, pas un paquet Python. Une version publie
un **bundle `tar.gz`** du catalogue comme asset d'une Release GitHub : pas de
PyPI, pas de wheel, aucun registre d'artefacts externe.

## Ce que contient une version

Le workflow `release.yml` construit
`{id}-<version>.tar.gz` avec :

- `labs/`, `meta.yml`, `meta.fr.yml`, `curriculums.yml`, `conftest.py`,
  `pyproject.toml`, `uv.lock` et `mise.toml`,
- `scripts/` et `tests/`, parce qu'un catalogue qui prétend se valider doit
  livrer de quoi le faire,
- `validation-labs.json`, la preuve que chaque lab a été joué dans les deux
  sens par les vraies commandes dsoxlab, avec sa date et les versions de dsoxlab et des outils employés par les labs,
- les documents de gouvernance (`README`, `LICENSE`, `CONTRIBUTING`,
  `CODE_OF_CONDUCT`, `SECURITY`, `CHANGELOG`, `RELEASING`), **dans les deux
  langues** :
  l'archive est ce que reçoit quelqu'un qui n'a pas le dépôt.

Le verrou voyage avec `pyproject.toml` délibérément. Une contrainte `>=` laisse
chaque installation résoudre ce qu'elle veut ; une archive qui prétend livrer
de quoi se valider ne dirait pas **avec quoi**.

Il **exclut** les solutions de référence (`solution/`, chiffrées, ce sont les
réponses), le pilotage local non versionné et les fichiers générés (caches,
état runtime de dsoxlab). Une exclusion qui ne correspond à rien ne fait pas
échouer `tar`, contrairement à un chemin listé mais absent, ce qui a déjà
cassé une release dans le dépôt Linux jumeau.

Quatre artefacts accompagnent l'archive :

| Artefact | Rôle |
| --- | --- |
| `<pkg>.tar.gz.sha256` | empreinte d'intégrité |
| `provenance.intoto.jsonl` | provenance SLSA, ce que lit Scorecard Signed-Releases |
| `<pkg>.tar.gz.cosign.bundle` | bundle de signature Cosign keyless |
| (côté registre) | attestation de build native GitHub |

## Pourquoi trois jobs, et pas un seul

Le workflow est découpé en **construire**, **attester**, **publier**, et ce
découpage est la seule chose qui sépare SLSA Build Level 2 de Level 3.

La documentation GitHub le dit en deux phrases : « Artifact attestations by
itself provides SLSA v1.0 Build Level 2 », et « Reusable workflows can provide
isolation between the build process and the calling workflow, to meet SLSA
v1.0 Build Level 3 ». Tant que le job qui construit l'archive est aussi celui
qui signe sa provenance, rien n'empêche techniquement le processus de build de
produire une provenance qui ment. Le niveau 3 exige que la signature se fasse
hors de sa portée.

D'où `.github/workflows/attester.yml`, appelé comme workflow réutilisable :

- il est le **seul du dépôt** à recevoir la permission `attestations: write` ;
- il ne reçoit qu'un **nom et une empreinte**, jamais l'archive ni le dépôt : il
  ne fait aucun `checkout` ;
- le job de publication, lui, peut écrire la release mais **ne peut pas
  attester**, faute de cette permission ;
- l'archive est recomparée à son empreinte **avant** publication, pour qu'un
  artefact altéré entre deux jobs ne soit pas publié avec une provenance qui ne
  le décrit pas.

L'appel s'écrit `uses: ./.github/workflows/attester.yml`, et non la forme
« self-repository » `$/`, plus récente, que zizmor recommande pourtant. La
raison mérite d'être consignée : l'outillage de sécurité ne sait pas encore
lire `$/`, et un analyseur qui ne comprend pas une construction ne peut pas la
juger sûre. Mesuré le 2026-09-15, sur cette ligne exactement : actionlint la
rejette comme un format invalide, zizmor 1.26.1 refuse de charger le fichier et
n'audite plus rien, et Plumber la prend pour une action tierce non épinglée
venant d'une source non autorisée, deux constats HIGH et un score de 70/100 au
lieu de 100/100. Le workflow appelé est celui qui SIGNE : c'est la dernière
ligne du dépôt sur laquelle se priver du regard des analyseurs.

## Produire une version

1. Vérifier que le catalogue est vert, et pas seulement livrable :

   ```bash
   dsoxlab validate-structure --check-urls
   pre-commit run --all-files --hook-stage pre-push
   python3 scripts/verify-solutions.py --deux-sens --check
   python3 scripts/valider-labs.py      # écrit validation-labs.json
   ```

2. **Réattester les labs qui ont changé depuis leur verdict.** Un lab dont les
   tests, les fichiers, un `conftest.py` commun ou les descripteurs ont été
   modifiés après le commit qui a inscrit son verdict n'est plus attesté par
   `validation-labs.json`. Depuis le dépôt du site (`test-astro-5`, cloné à
   côté de ce dépôt), lancer :

   ```bash
   python3 scripts/reattester-labs.py --depot {id}           # plan et garde-fous
   python3 scripts/reattester-labs.py --depot {id} --apply   # rejoue et commite
   ```

   Le script rejoue chaque lab « à réattester » par `scripts/valider-labs.py`,
   un par un (tests et lab modifiés d'abord, puis `conftest.py` commun, puis
   descripteurs), vérifie que le diff de `validation-labs.json` ne touche que
   ces labs, relance `--check` et `pytest tests/`, puis fait un commit **local**
   du seul relevé. Il refuse un dépôt non propre et un lab actif. Un verdict
   ROUGE n'est pas commité : corriger le lab, puis relancer.

   Avant de taguer, relancer le dry-run : il doit afficher
   **« 0 lab(s) à réattester »**. Pousser ensuite le commit du relevé avec le
   reste de la version.

3. Basculer les entrées de `CHANGELOG.md` sous une nouvelle version.
4. Taguer et pousser le tag, ce qui déclenche `release.yml` :

   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

5. Le workflow construit le `tar.gz`, atteste sa provenance, le signe en
   keyless et crée la Release GitHub avec des notes générées automatiquement.

## Vérifier une version

Intégrité et contenu :

```bash
sha256sum -c {id}-<version>.tar.gz.sha256
tar tzf {id}-<version>.tar.gz | head
```

Provenance du build. Prouve que l'archive a bien été produite par le workflow de
ce dépôt, et non reconstruite par quelqu'un d'autre :

```bash
gh attestation verify {id}-<version>.tar.gz \
  --repo stephrobert/{id}
```

**La vérification qui atteste le niveau 3** nomme le workflow signataire. Elle
échoue si la provenance a été produite ailleurs que par le workflow
d'attestation isolé, et c'est elle qu'il faut lancer à la première release pour
confirmer que la chaîne tient :

```bash
gh attestation verify {id}-<version>.tar.gz \
  --repo stephrobert/{id} \
  --signer-workflow stephrobert/{id}/.github/workflows/attester.yml
```

Signature Cosign keyless. Les **deux** options de certificat sont obligatoires :
sans elles, `cosign verify-blob` accepte n'importe quelle identité, ce qui vide
la vérification de son sens.

```bash
cosign verify-blob \
  --bundle {id}-<version>.tar.gz.cosign.bundle \
  --certificate-identity-regexp "https://github.com/stephrobert/{id}/.github/workflows/release.yml@.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  {id}-<version>.tar.gz
```

> **Piège de version Cosign.** La CI installe **Cosign 3.x**, qui écrit un
> nouveau format de bundle. Un **Cosign 2.x** local répond `no signatures found`
> sur une archive pourtant parfaitement signée : la release n'est pas cassée,
> c'est l'outil local qui ne sait pas lire le format. Vérifiez `cosign version`
> et alignez-le avant de conclure quoi que ce soit.

## Réglages GitHub à faire une fois

Deux workflows ont besoin d'une configuration qui ne vit pas dans le dépôt :

- **`plumber.yml`** attend un environnement `security`, restreint à la branche
  `main`, portant le secret `PLUMBER_ADMIN_TOKEN` : un PAT à portée fine avec
  Administration, Contents et Metadata en lecture. Sans lui, le workflow tourne
  quand même, sur le jeton du job, mais le contrôle `branchMustBeProtected`
  s'abstient et le score reste incomplet.
- **La protection de la branche `main`**, par le ruleset « Protection de main » :
  c'est elle que Scorecard et Plumber mesurent. Historique linéaire, suppression
  et poussée en force interdites, passage par pull request avec résolution des
  fils de discussion, et les jobs de la CI en contrôles obligatoires.

### Le ruleset « Protection de main », prêt à appliquer

Un ruleset est un réglage GitHub, pas un fichier du dépôt : il ne voyage pas
avec un `git push`. Il se pose **une fois**, après la création du dépôt et le
premier passage de la CI (un contrôle obligatoire doit avoir tourné au moins
une fois pour que GitHub le propose). La charge ci-dessous reprend les règles
des catalogues voisins ; les contextes sont les noms des jobs de `ci.yml`, la
matrice CodeQL en donnant deux.

Aucune approbation n'est exigée (`required_approving_review_count: 0`) : le
dépôt n'a qu'un mainteneur, qui ne peut pas approuver sa propre pull request.
Le passage par pull request, la résolution des fils et la CI verte restent
obligatoires.

```bash
gh api --method POST repos/stephrobert/{id}/rulesets \
  --input - <<'JSON'
{{
  "name": "Protection de main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {{"ref_name": {{"include": ["~DEFAULT_BRANCH"], "exclude": []}}}},
  "rules": [
    {{"type": "deletion"}},
    {{"type": "non_fast_forward"}},
    {{"type": "required_linear_history"}},
    {{"type": "pull_request", "parameters": {{
      "required_approving_review_count": 0,
      "dismiss_stale_reviews_on_push": true,
      "require_code_owner_review": false,
      "require_last_push_approval": false,
      "required_review_thread_resolution": true}}}},
    {{"type": "required_status_checks", "parameters": {{
      "strict_required_status_checks_policy": true,
      "required_status_checks": [
        {{"context": "Zizmor (workflow static analysis)"}},
        {{"context": "Actionlint (workflow syntax)"}},
        {{"context": "Poutine (CI/CD exploit chains)"}},
        {{"context": "Pre-commit parity (all hooks)"}},
        {{"context": "Contrat du catalogue (leçons jumelées comprises)"}},
        {{"context": "CodeQL (python)"}},
        {{"context": "CodeQL (actions)"}}]}}}}
  ]
}}
JSON
```

Ce bloc n'a **jamais été appliqué** : le dépôt n'existe pas encore sur GitHub.
À la première application, relire le ruleset créé dans *Settings > Rules* et
vérifier qu'une poussée directe sur `main` est refusée.
"""


def licence_par_defaut() -> str:
    """Le texte de CC BY 4.0, lu dans les gabarits packagés.

    Onze des douze catalogues de la collection l'emploient. Ce n'est pas une
    décision que l'outil impose : la CLI dit qu'il l'a posée, et l'auteur
    remplace le fichier si son catalogue a une autre licence.
    """
    from ..templates import licence

    return licence().read_text(encoding="utf-8")


def fichiers_du_socle(identifiant: str) -> dict[str, str]:
    """Les fichiers du socle, par chemin relatif à la racine du catalogue.

    Un seul endroit décide de ce qu'un catalogue porte : ce dictionnaire. Le
    jour où la collection en ajoute un, il s'ajoute ici et tous les nouveaux
    catalogues l'ont, sans qu'on ait à s'en souvenir.
    """
    return {
        "LICENSE": licence_par_defaut(),
        "README.md": README_EN.format(id=identifiant),
        "README.fr.md": README_FR.format(id=identifiant),
        "meta.fr.yml": META_FR.format(id=identifiant),
        "conftest.py": CONFTEST,
        "pyproject.toml": PYPROJECT.format(id=identifiant),
        "CONTRIBUTING.md": CONTRIBUTING_EN,
        "CONTRIBUTING.fr.md": CONTRIBUTING_FR,
        "CODE_OF_CONDUCT.md": CODE_OF_CONDUCT_EN,
        "CODE_OF_CONDUCT.fr.md": CODE_OF_CONDUCT_FR,
        "SECURITY.md": SECURITY_EN,
        "SECURITY.fr.md": SECURITY_FR,
        "CHANGELOG.md": CHANGELOG_EN,
        "CHANGELOG.fr.md": CHANGELOG_FR,
        ".github/workflows/ci.yml": CI.format(
            sha_harden=_SHA_HARDEN, sha_checkout=_SHA_CHECKOUT, sha_uv=_SHA_SETUP_UV,
        ),
        ".github/workflows/release.yml": RELEASE.format(id=identifiant),
        ".github/workflows/attester.yml": ATTESTER.format(id=identifiant),
        "RELEASING.md": RELEASING_EN.format(id=identifiant),
        "RELEASING.fr.md": RELEASING_FR.format(id=identifiant),
        ".pre-commit-config.yaml": PRE_COMMIT,
        "tests/test_contrat_du_catalogue.py": TEST_CONTRAT,
        "tests/outils/pas_de_tiret_cadratin.py": TEST_TIRET,
    }
