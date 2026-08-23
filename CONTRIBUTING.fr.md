# Contribuer à dsoxlab

**Langue :** [English](./CONTRIBUTING.md) · [Français](./CONTRIBUTING.fr.md)

Merci de votre intérêt pour l'amélioration de `dsoxlab`. Ce document explique
comment configurer le projet, les conventions suivies et les règles qui
préservent la santé du moteur.

Le projet est bilingue pour ses utilisateurs, mais **la langue de contribution
est l'anglais** : issues, pull requests, commentaires de code et messages de
commit sont rédigés en anglais pour que tout le monde puisse participer.

## Table des matières

- [Règles fondamentales](#règles-fondamentales)
- [Mise en place](#mise-en-place)
- [Carte de l'architecture](#carte-de-larchitecture)
- [Contrôles qualité](#contrôles-qualité)
  - [Scanners de workflow](#scanners-de-workflow)
  - [Fuzzer le contrat non fiable](#fuzzer-le-contrat-non-fiable)
- [Hooks pre-commit](#hooks-pre-commit)
- [Internationalisation (i18n)](#internationalisation-i18n)
- [Conventions de commit](#conventions-de-commit)
- [Pull requests](#pull-requests)
- [Signaler un bug ou demander une fonctionnalité](#signaler-un-bug-ou-demander-une-fonctionnalité)

## Règles fondamentales

Non négociables. Une modification qui enfreint l'une d'elles ne sera pas mergée.

1. **Le moteur reste neutre vis-à-vis du domaine.** Rien sous `src/dsoxlab/` ne
   doit contenir de logique spécifique à un domaine (Linux, Ansible,
   Kubernetes…). Si vous écrivez `if category == "linux"`, la logique appartient
   au contrat du dépôt de labs (`meta.yml` / `lab.yaml`), pas au moteur.
2. **Une CLI, un point d'entrée.** `src/dsoxlab/cli.py` est l'unique point
   d'entrée. Les scripts shell d'orchestration vivent dans les dépôts de labs,
   jamais ici.
3. **Typage strict.** `mypy --strict` doit rester vert. Tout annoter, ne pas
   propager de dictionnaires non typés.
4. **Portabilité.** Aucun chemin ou hôte personnel codé en dur. Utiliser
   `pathlib.Path` et les variables XDG (`XDG_DATA_HOME`, `XDG_CONFIG_HOME`).
5. **Toute chaîne affichée est traduite.** Aucune chaîne en dur dans `cli.py` ou
   `reporting/`. Voir [i18n](#internationalisation-i18n).

## Mise en place

Prérequis : **Python 3.11+** et [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/stephrobert/dsoxlab.git
cd dsoxlab
uv sync                      # crée le venv et installe les dépendances de dev
uv tool install --editable . # optionnel : expose `dsoxlab` sur le PATH
```

Testez sur un vrai dépôt de labs pour valider la neutralité (au moins deux,
par exemple `linux-training` et `ansible-training`) :

```bash
cd ~/Projets/linux-dsoxlab-training && dsoxlab list-labs
cd ~/Projets/ansible-training && dsoxlab list-labs
```

## Carte de l'architecture

```text
src/dsoxlab/
├── cli.py            ← point d'entrée Typer (+ le groupe de commandes i18n)
├── config.py         ← LAB_HOME, contexte actif, .dsoxlab-context.json
├── locking.py        ← verrou d'écriture par catalogue (flock), code de sortie 7
├── logging_setup.py  ← le journal qu'écrit chaque commande, quelle que soit la verbosité
├── i18n/             ← get_lang(), _(), strings/en.py + strings/fr.py
├── models/           ← schémas typés du contrat déclaratif
├── discovery/        ← scan du meta.yml et de tous les lab.yaml du catalogue
├── services/         ← orchestration métier (lab, progression, guide, doctor…)
├── sessions/         ← persistance SQLite (results + hint_requests)
├── runtimes/         ← BaseRuntime, ShellRuntime, VmRuntime, RuntimeManager
├── infra/            ← Terraform, Ansible, inventaire, snapshots, identifiants
├── validators/       ← structure, métadonnées et contenu d'un catalogue
├── reporting/        ← sorties terminal Rich, et le JSON de --json
├── utils/            ← wrapper subprocess centralisé
└── templates/        ← Terraform, cloud-init et le catalogue de démonstration
```

Il existe deux runtimes, et deux seulement : `shell` et `vm`. Les valeurs `kvm`
et `incus` de `runtime.type` sont des alias historiques traités par
`VmRuntime` ; quel backend sert réellement une VM vient de
`meta.yml: infra.provider`.

`infra/inventory.py` est la surface publique qu'un catalogue consomme : son
`conftest.py` importe `build_inventory`, `read_terraform_outputs` et
`write_ssh_config` pour construire l'inventaire testinfra sans coder la moindre
adresse IP.

Le moteur reste indépendant de l'arborescence d'un dépôt : `discovery/`
fonctionne sur n'importe quel arbre déclaré par le `meta.yml`.

## Contrôles qualité

À lancer avant d'ouvrir une pull request. La CI exécute les mêmes contrôles.

```bash
uv run ruff check src/dsoxlab tests tests_e2e fuzz scripts   # lint + sécurité (règles flake8-bandit S)
uv run mypy src/dsoxlab                                      # typage (strict)
uv run pytest                                                # tests unitaires
uv run pytest tests_e2e                                      # bout en bout, sur la roue construite
```

### Les deux suites, et pourquoi elles sont séparées

`tests/` importe le paquet et prouve que les fonctions font ce qu'elles disent.
`tests_e2e/` ne l'importe jamais : elle construit la roue, l'installe dans un
environnement virtuel jetable et pilote le binaire `dsoxlab` par sous-processus,
en n'assérant que sur les codes de retour, la sortie standard, la sortie
d'erreur et les fichiers laissés sur le disque. C'est la seule façon qu'un
fichier de données absent de la roue, ou un point d'entrée `console_scripts`
cassé, fasse rougir une construction.

Une règle porte tout l'édifice, et un test porte la règle : **aucun fichier de
`tests_e2e/` n'importe `dsoxlab`**. Ajoutez un tel import et
`test_boite_noire.py` passe au rouge : c'est le moyen le plus rapide de
comprendre à quoi sert cette suite. `tests_e2e/` a sa propre `pytest.ini`, donc
le `testpaths` du projet la tient hors d'un simple `uv run pytest`.

### Scanners de workflow

Si vous touchez à `.github/workflows/`, quatre scanners bloquent la CI et
doivent rester à **zéro finding**. Ils analysent le YAML des workflows, donc ils
tournent sans aucune dépendance du projet :

```bash
actionlint                                    # syntaxe, scopes de permission invalides, shellcheck
zizmor --offline .github/workflows/           # failles de workflow
poutine analyze_local . --fail-on-violation   # chaînes d'exploitation CI/CD
plumber analyze                               # graphe de confiance + réglages du dépôt
```

Les règles qu'ils imposent, à connaître avant d'écrire une ligne de YAML :

- **Chaque action est épinglée par un SHA de commit de 40 caractères**, suivi
  d'un commentaire `# vX.Y.Z`. Jamais `@v4`, jamais `@main` : un tag est
  mutable, donc c'est un trou de supply chain.
- **`step-security/harden-runner` est le premier step de chaque job.**
- `permissions: {}` au niveau workflow, permissions minimales par job.
- `actions/checkout` avec `persist-credentials: false`, un runner figé
  (`ubuntu-24.04`, pas `ubuntu-latest`), un `timeout-minutes` et un `name:`.
- **Ne jamais interpoler `${{ … }}` dans un bloc `run:`.** Passez la valeur par
  un bloc `env:`, sinon zizmor signale une injection de template.
- Une nouvelle action tierce doit être ajoutée à `trustedGithubActions` dans
  `.plumber.yaml`. Si son créateur n'est pas vérifié sur le Marketplace,
  acquittez-la dans `.poutine.yml` **par son purl exact** — jamais en
  désactivant la règle, ce qui la rendrait aveugle à toutes les autres actions.

Un piège mérite sa propre ligne : **les status checks requis portent les noms de
jobs exacts**. Renommer un job fait taire silencieusement l'ancien check, qui
n'est alors plus jamais satisfait, et les pull requests restent bloquées. Ne
renommez qu'en mettant à jour la protection de branche dans le même geste.

### Fuzzer le contrat non fiable

`lab.yaml` et `meta.yml` viennent des dépôts fournisseurs de labs : ce sont les
entrées non fiables du moteur. `discovery/scanner.py` rattrape
`(KeyError, ValueError, yaml.YAMLError)` et ignore le lab fautif avec un
warning — **toute exception hors de ce tuple échappe au filet et fait planter la
CLI** sur une commande sans rapport.

Les harnais de `fuzz/` vérifient ce contrat, et un run court amorcé bloque la
CI. Lancez une campagne plus longue en local dès que vous touchez à un parser :

```bash
uv sync --group fuzz
mkdir -p /tmp/fuzz-lab
uv run --group fuzz python fuzz/fuzz_lab_yaml.py \
    /tmp/fuzz-lab fuzz/corpus/lab_yaml/ \
    -dict=fuzz/dict/yaml_contract.dict -atheris_runs=100000
```

Passez le répertoire de travail **en premier** : libFuzzer écrit ses trouvailles
dans le premier dossier de corpus, et `fuzz/corpus/` est un jeu de graines
choisi à la main. Un crash écrit un reproducteur `crash-*` que vous rejouez en
le passant comme unique argument. Si vous ajoutez un champ au contrat, ajoutez
une graine : des octets aléatoires ne reconstruisent jamais un mot-clé par
hasard, donc le corpus et `fuzz/dict/yaml_contract.dict` sont ce qui permet au
fuzzer d'atteindre votre code.

## Hooks pre-commit

Ce dépôt est public : une série de hooks [pre-commit](https://pre-commit.com/)
protège chaque commit contre les fuites de secrets ou de clés privées et contre
l'ajout d'artefacts indésirables. Installez-les une fois après le clonage :

```bash
uv run pre-commit install --install-hooks
```

À chaque **commit** : contrôles d'hygiène (espaces en fin de ligne, fin de
fichier, validité YAML/JSON/TOML, gros fichiers, conflits de merge), détection
de clé privée, scan de secrets TruffleHog, `ruff` (lint + sécurité, autofix) et
`mypy --strict`. La suite `pytest` complète tourne au **push**. Tout lancer à la
main :

```bash
uv run pre-commit run --all-files
```

## Internationalisation (i18n)

Quand vous ajoutez ou modifiez une chaîne affichée :

- Ajoutez la clé dans **les deux** fichiers `src/dsoxlab/i18n/strings/en.py`
  **et** `src/dsoxlab/i18n/strings/fr.py`.
- L'anglais est la langue source ; la valeur française doit être une traduction
  fidèle, avec des diacritiques corrects.
- Vérifiez les deux langues :

  ```bash
  DSOXLAB_LANG=en dsoxlab <commande>
  DSOXLAB_LANG=fr dsoxlab <commande>
  ```

Quand vous ajoutez, retirez ou modifiez une commande ou une option, mettez à
jour **simultanément** : l'aide `help=_("…")` dans `cli.py`, les clés EN + FR,
et la section `fullhelp_commands` correspondante dans les deux langues. Ne
laissez jamais `fullhelp` décrire une commande qui n'existe plus.

## Conventions de commit

Nous utilisons les Conventional Commits avec un scope de module :

```
<type>(<module>): <description courte>
```

Types : `feat`, `fix`, `docs`, `refactor`, `chore`, `test`, `ci`. Exemples :

- `feat(runtimes): declare containerized services in lab.yaml`
- `fix(runtimes/vm): make snapshot revert idempotent when the snapshot is absent`
- `docs(contract): document the meta.fr.yml overrides`

Gardez des commits ciblés et un historique lisible. Avant un commit groupé,
consultez `git log --oneline -5` pour coller au style.

## Pull requests

- Partez d'un `main` à jour, gardez un périmètre restreint, remplissez le
  gabarit de PR. Supprimez la branche une fois mergée.
- Assurez-vous que lint, typage et tests sont verts — plus les scanners de
  workflow si vous avez touché à `.github/workflows/`.
- Quand le comportement change, mettez à jour **les deux** fichiers
  `CHANGELOG.md` et `CHANGELOG.fr.md`. Le projet est bilingue : une entrée en
  anglais seul est une entrée incomplète.
- Quand le comportement change, bumpez aussi la version dans `pyproject.toml` et
  régénérez `uv.lock` (`uv lock`). Il n'y a rien à bumper dans
  `src/dsoxlab/__init__.py` : `__version__` est lu depuis les métadonnées du
  paquet installé, précisément pour qu'il ne puisse pas diverger de
  `pyproject.toml`.
- Si vous ajoutez une commande ou une option, confirmez la checklist i18n
  ci-dessus.

## Signaler un bug ou demander une fonctionnalité

Utilisez les gabarits d'issue GitHub. Pour un bug, lancez `dsoxlab support` et
collez sa sortie : elle rassemble d'un bloc la version, le système, les outils
externes, le catalogue et les dernières lignes de journal, ce qui évite un
aller-retour qui coûte sinon une journée. Le rapport est anonymisé par défaut,
il ne porte donc ni chemin personnel, ni adresse publique, ni nom de machine ;
`dsoxlab support --json` rend le même contenu pour un programme.

Ajoutez la commande exacte jouée, et l'écart entre le comportement attendu et
observé. Si dsoxlab ne démarre pas du tout, `dsoxlab --version` et votre OS
suffisent. Pour un problème de sécurité, suivez plutôt
[SECURITY.md](./SECURITY.md) au lieu d'ouvrir une issue publique.
