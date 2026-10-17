# Contribuer à dsoxlab

**Langue :** [English](./CONTRIBUTING.md) · [Français](./CONTRIBUTING.fr.md)

Merci de votre intérêt pour l'amélioration de `dsoxlab`. Ce document explique
comment configurer le projet, les conventions suivies et les règles qui
préservent la santé du moteur.

Le projet est bilingue pour ses utilisateurs. Sa **langue de travail est le
français** : commentaires de code, docstrings, messages de commit et issues
s'écrivent en français — c'est ce que ce dépôt fait depuis toujours sur plusieurs
milliers de lignes, et la langue de son mainteneur.

Ce qui **sort** du dépôt est une autre affaire, et c'est bilingue ou anglais par
conception : toute chaîne affichée passe par `_()` en anglais **et** en français,
la documentation vit en fichiers appariés (`docs/x.md` + `docs/x.fr.md`), et le
journal est en anglais seul — il se cherche mot pour mot et se compare entre
machines aux locales différentes.

**Une contribution rédigée en anglais est bienvenue et ne sera pas refusée.**
Cette page affirmait l'inverse, que tout, commentaires de code compris, était en
anglais, alors que le code disait le contraire partout. Une règle de gouvernance
que le dépôt contredit fait écrire du faux avec assurance, ce qui est pire que
pas de règle du tout.

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
2. **Une CLI, un point d'entrée.** `src/dsoxlab/cli/` est l'unique point
   d'entrée — un paquet de 17 modules depuis que le `cli.py` monolithique a
   dépassé 3 000 lignes. Chercher `src/dsoxlab/cli.py` ne rend plus rien. Les
   scripts shell d'orchestration n'ont leur place nulle part : ni ici, ni dans les
   dépôts de labs, où le validator les rejette.
3. **Typage strict.** `mypy --strict` doit rester vert. Tout annoter, ne pas
   propager de dictionnaires non typés.
4. **Portabilité.** Aucun chemin ou hôte personnel codé en dur. Utiliser
   `pathlib.Path` et les variables XDG (`XDG_DATA_HOME`, `XDG_CONFIG_HOME`).
5. **Toute chaîne affichée est traduite.** Aucune chaîne en dur sous `cli/` ou
   dans `reporting/`. Voir [i18n](#internationalisation-i18n). Deux choses ne
   sont **délibérément pas** traduites, et des tests l'imposent : le journal et le
   rapport de `support`, tous deux en anglais parce qu'ils se comparent entre
   machines et se publient.

Ces cinq règles portent sur la forme du code. Il en existe un second jeu, sur ce
qu'un contrôle peut conclure et sur ce qu'un échec doit à son lecteur : **[les
invariants du projet](./docs/design-principles.fr.md)**. Chacun porte l'incident
qui l'a révélé et le test qui le tient, et chacun suffit à refuser une
modification — « ce contrôle rend `ok` quand sa sonde échoue » n'appelle aucun
autre argument.

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
├── cli/              ← paquet Typer, 17 modules (ex-cli.py monolithique)
│   ├── _socle.py         app et ses sous-applications (catalog, infra…)
│   ├── _commun.py        helpers partagés (_root, _lab, le verrou, services…)
│   ├── parcours.py       run, course, challenge, guide
│   ├── progression.py    check, submit, scores, progress, next, reset, clean
│   └── …                 un module par groupe de commandes, ordonnés par
│                         _ORDRE_COMMANDES dans __init__.py
├── exit_codes.py     ← tous les codes de sortie, dans un énuméré ExitCode
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

### Payer la dette en même temps qu'on produit

Trois contrôles mesurent la **dérive** plutôt qu'un absolu, et c'est ce qui les
rend tenables : un seuil absolu n'était pas jouable (35 blocs dépassent déjà les
seuils, et les interdire d'un coup bloquerait tout commit), un cliquet l'est.

```bash
python3 scripts/complexite.py              # le classement, pour lire
python3 scripts/code-mort.py               # les symboles sans appelant
python3 scripts/complexite-ecran.py        # ce que l'apprenant a sous les yeux
```

Chacun porte un relevé de référence dans `scripts/*-reference.json`, et chacun
**refuse deux choses** : qu'une mesure monte, et qu'elle descende sans que le
relevé soit mis à jour. Le second cas surprend, et il est délibéré : une dette
payée qui n'est pas enregistrée laisse l'ancienne valeur comme plafond, et la
complexité peut remonter jusqu'à elle sans qu'aucun hook ne bronche.

```bash
python3 scripts/complexite.py --figer      # après avoir simplifié
python3 scripts/code-mort.py --figer       # après avoir retiré ou branché
python3 scripts/complexite-ecran.py --figer
```

**Ce que chacun mesure, et pourquoi il ne suffisait pas d'ajouter un lint.**

`ruff C901` mesure la complexité cyclomatique. Elle ne voit pas les fermetures :
mesuré sur `cli/_barres.py`, `_run_ansible_with_progress` affiche une
cyclomatique de **1** pour 91 lignes et trois fonctions emboîtées qui se passent
un état mutable. `scripts/complexite.py` mesure donc ce que ruff ignore, la
complexité **cognitive**, la profondeur d'imbrication et la longueur.

`scripts/code-mort.py` remplace vulture, qui rendait 108 lignes sur ce dépôt
dont environ 80 de faux positifs structurels : les 38 commandes Typer, qui ne
sont référencées que par un décorateur, et une quarantaine de fixtures pytest,
injectées par nom. Ce script connaît ces mécanismes, plus le `__all__`, la
documentation et la surface Python que les dépôts de labs importent. Il peut
donc faire échouer un commit, ce que vulture ne pouvait pas.

`scripts/complexite-ecran.py` est le seul contrôle qui regarde **la sortie** et
non le code. Il exécute de vraies commandes à 80, 100, 120 et 160 colonnes et
mesure huit grandeurs : hauteur, troncatures, colonnes de tableau, gestes
proposés, termes de jargon, lignes de sortie d'outil brute, largeur minimale
lisible, et impasses. La dernière punit la brièveté, pour que « simplifier » ne
puisse pas se confondre avec « se taire » : un écran qui répond en une ligne
sans proposer de geste coûte autant qu'un tableau illisible.

Les scores sont arbitraires et le détail est toujours affiché à côté : ils
servent à comparer deux versions du même écran, pas à décerner une note.

**Une hausse peut être légitime.** Un écran qui explique davantage est plus
lourd, et c'est parfois le bon choix. On la fige alors sciemment, en disant dans
le message de commit pourquoi elle était nécessaire. Ce qui est interdit, c'est
qu'elle passe sans que personne l'ait décidée.

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
de clé privée, scan de secrets TruffleHog, `ruff` (lint + sécurité, autofix),
`mypy --strict`, et les deux cliquets de dette (complexité cognitive, code sans
appelant). Au **push** : la suite `pytest` complète et la charge d'écran des
parcours, qui joue de vraies commandes et prend une dizaine de secondes. Tout
lancer à la main :

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
jour **simultanément** : l'aide `help=_("…")` dans son module de `cli/`, les clés EN + FR,
et la section `fullhelp_commands` correspondante dans les deux langues. Ne
laissez jamais `fullhelp` décrire une commande qui n'existe plus.

## Rendu terminal

Six règles, chacune née d'un défaut mesuré sur un écran réel. Elles valent pour
tout ce qui passe par `reporting/console.py`.

- **Une seule couleur par état, jamais une par élément.** Le verdict de `check`
  affichait une barre verte à côté d'un score rouge : deux couleurs pour un
  seul fait, qui se contredisaient à l'œil. Vert, jaune ou rouge, et les deux
  ensemble.
- **La sémantique des couleurs est fixe** : cyan pour ce qui se tape, jaune
  pour un avertissement, vert et rouge pour un résultat. Un panneau d'accueil
  encadré de jaune dit « attention » à qui lit vite.
- **Aucune ligne qui ne dit rien.** « Hints : aucun » occupait un tiers d'un
  panneau pour annoncer une absence. Une information absente ne s'affiche pas.
- **Des colonnes alignées plutôt que des phrases qui se replient.** L'accueil
  de `run` listait ses commandes en phrases : elles se repliaient au milieu et
  la suite repartait en marge, où elle se lisait comme une autre entrée. Une
  `Table.grid` à deux colonnes règle le cas, et elle impose d'écrire des
  descriptions qui tiennent.
- **Pas de rembourrage gratuit.** Un écran qui revient après chaque commande se
  mérite court : deux lignes vides ajoutées « pour aérer » coûtent plus qu'elles
  ne rendent.
- **De vrais pluriels.** `indice(s) utilisé(s)` est la marque d'un texte que
  personne n'a relu : deux clés, et l'appelant choisit selon le compte.

Deux conséquences pratiques. Le nom d'une commande (`dsoxlab check`) n'est pas
une chaîne traduisible : c'est ce que l'utilisateur tape, il vit dans le code,
et le garde-fou i18n l'accepte dès qu'une constante nommée dit ce qu'il est.
Et une cellule de tableau porte une mesure, pas une phrase : si elle se replie
sur trois lignes, c'est le texte qu'il faut raccourcir, pas la colonne qu'il
faut élargir.

Pour mesurer plutôt que juger, `python3 scripts/complexite-ecran.py` compte ce
que chaque écran impose au lecteur. Il mesure la **charge**, jamais la beauté :
une sortie peut être courte et laide.

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
