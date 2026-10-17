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
        ".pre-commit-config.yaml": PRE_COMMIT,
        "tests/test_contrat_du_catalogue.py": TEST_CONTRAT,
        "tests/outils/pas_de_tiret_cadratin.py": TEST_TIRET,
    }
