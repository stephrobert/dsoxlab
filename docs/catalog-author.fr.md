# dsoxlab pour l'auteur de catalogue

**Public :** vous écrivez des labs, dans votre propre dépôt. Vous voulez savoir
ce que dsoxlab lit, ce qu'il refuse, et où il vous ignorera en silence.

**Langue :** [English](./catalog-author.md) · [Français](./catalog-author.fr.md)

La référence champ par champ est [le contrat v1](./contract-v1.fr.md). Cette
page est le mode d'emploi autour : comment un catalogue est agencé, dans quel
ordre le contrôler, et quels pièges coûtent le plus de temps.

---

## Ce qu'est un catalogue

Un dépôt avec un `meta.yml` à la racine et un `lab.yaml` par lab sous `labs/`.
Rien d'autre ne le lie à dsoxlab : aucune dépendance à installer, aucun plugin à
écrire. Retirer dsoxlab doit laisser les labs jouables à la main
(`ansible-playbook setup.yaml` puis `pytest`) : c'est le test de non-couplage, et
c'est lui qui garde le moteur neutre vis-à-vis du domaine.

```text
ma-formation/
├── meta.yml                    ← catalogue : identité, topologie, ordre des sections
├── meta.fr.yml                 ← optionnel : titres et descriptions en français
├── ssh/id_ed25519.pub          ← seulement si le catalogue déclare des labs vm
└── labs/
    └── mon-domaine/l1/premier-lab/
        ├── lab.yaml            ← obligatoire
        ├── README.md           ← obligatoire
        ├── scenario.md         ← obligatoire
        ├── setup.yaml          ← obligatoire pour runtime vm (Ansible)
        ├── cleanup.yaml        ← obligatoire pour runtime vm (Ansible)
        ├── fixtures/           ← optionnel, pour runtime shell
        └── challenge/
            ├── README.md       ← la mission affichée par `dsoxlab challenge`
            ├── hints.yaml      ← optionnel : les indices et leur coût
            └── tests/
                └── test_functional.py   ← obligatoire, nom exact
```

`challenge/tests/test_functional.py` est le seul nom de fichier de test que le
validator exige. Rien n'interdit d'en poser d'autres à côté : pytest collecte le
répertoire.

---

## L'ordre des opérations

**`dsoxlab list-labs` d'abord, `dsoxlab validate-structure` ensuite.** Pas
l'inverse, et c'est le conseil le plus utile de cette page.

Un `lab.yaml` qui lève au parsing fait **disparaître son lab en silence** : le
scanner journalise un avertissement et passe au suivant. `validate-structure`
itère ensuite sur les labs **découverts avec succès** : il valide les
survivants et ne dit rien du disparu. Un lab absent de `list-labs` est presque
toujours un `lab.yaml` qui lève.

L'avertissement, lui, atteint bien `~/.local/state/dsoxlab/dsoxlab.log` (et
`dsoxlab support` le collecte) : le diagnostic est à une commande, une fois
qu'on sait où regarder.

Une exception depuis la 0.1.46 : un `schema_version` que cet outil ne sait pas
lire s'affiche à l'écran et nomme le fichier, au lieu de s'évanouir.

---

## Ce que `validate-structure` vérifie

Trois familles, toutes locales et hors ligne par défaut.

**Structure.** `lab.yaml`, `README.md`, `scenario.md`, `challenge/tests/` et
`challenge/tests/test_functional.py`. Un lab `vm` exige en plus `setup.yaml` et
`cleanup.yaml`, un `runtime.targets[]` non vide, et un `runtime.default` qui
corresponde à l'une de ces cibles. Un lab `shell` exige un `runtime.workdir` non
vide.

**Métadonnées.** `id`, `title`, `level` et `doc_url` non vides, `skills` et
`distros` non vides, `doc_url` en `http(s)`, `lab_type` parmi
`lab | challenge | capstone`, et `exam_passing_score` entre 1 et 100 quand il est
déclaré.

**Contenu.** Tout lien relatif d'un Markdown du lab pointe sur un fichier
existant ; le barème annoncé correspond à la note réellement calculée ; un
document traduit d'un seul côté est signalé ; `runtime.targets[].host` et les
`roles` existent dans les hôtes du `meta.yml` ; et aucun fichier d'un répertoire
`solution/` n'est lisible en clair (un catalogue sans `solution/` n'est pas en
faute, il a fait un autre choix).

`--check-urls` ajoute le seul contrôle réseau : chaque `doc_url` doit répondre.

### Chaque clé, et ce qu'elle veut dire

Le validateur nomme chaque anomalie par une clé stable. Un test tient cette table
en phase avec le code : ajouter un contrôle sans le documenter ici fait échouer
la suite.

| Clé | Ce que ça veut dire |
| --- | --- |
| `struct_missing_file` | un fichier requis est absent |
| `struct_missing_dir` | `challenge/tests/` est absent |
| `struct_vm_targets_empty` | un lab `vm` ne déclare aucune `runtime.targets` |
| `struct_default_unknown` | `runtime.default` nomme une target que `targets[]` ne définit pas |
| `struct_shell_workdir_empty` | un lab `shell` ne déclare pas de `runtime.workdir` |
| `struct_session_unknown` | `runtime.session` n'est ni `target` ni `local` |
| `metadata_field_empty` | un champ requis est vide |
| `metadata_list_empty` | `skills` ou `distros` est une liste vide |
| `metadata_doc_url_scheme` | `doc_url` n'est pas en http(s) |
| `metadata_lab_type_invalid` | `lab_type` sort de l'énuméré |
| `metadata_exam_score_invalid` | `exam_passing_score` est hors bornes |
| `content_broken_links` | un lien relatif ne pointe sur rien |
| `content_missing_english` | un document n'est traduit que d'un côté |
| `content_scoring_points_mismatch` | les tâches totalisent un autre nombre de points que celui annoncé |
| `content_scoring_count_mismatch` | l'en-tête annonce un autre nombre de tâches notées |
| `content_scoring_tasks_vs_tests` | tâches notées et tests ne se correspondent pas |
| `content_target_host_unknown` | l'hôte d'une target est absent de `infra.hosts[]` |
| `content_role_host_unknown` | une entrée de `roles` nomme un hôte inconnu |
| `content_solution_plaintext` | un fichier de `solution/` est lisible en clair |
| `content_fixture_missing` | une fixture est déclarée mais absente de `fixtures/` |
| `content_fixture_undeclared` | un fichier est dans `fixtures/` sans être déclaré |
| `content_fixture_escapes` | un chemin de fixture est absolu ou contient `..` |
| `content_doc_url_no_scheme` | `doc_url` ne porte aucun schéma d'URL |
| `content_doc_url_scheme` | `doc_url` emploie un schéma autre que http(s) |
| `schema_version_too_new` | le fichier déclare un `schema_version` que ce dsoxlab ne sait pas lire |

**Ce qu'il ne peut pas vérifier :** qu'un lab listé dans `meta.yml` existe sur le
disque. Le validator parcourt ce que la découverte a déjà chargé. D'où l'ordre
ci-dessus.

---

## Les pièges

**1. `runtime.type` vaut `vm`, pas `kvm` ni `incus`.** Ces deux valeurs sont des
alias tolérés, traités à l'identique. Le vrai backend vient de
`meta.yml: infra.provider`. Écrivez `vm`.

**2. `runtime.host` n'existe pas.** Aucun code ne le lit, il est donc ignoré en
silence. Le FQDN vit dans `runtime.targets[].host`.

**3. La découverte se fait par chemin, jamais par `id`.** Un lab existe si et
seulement si `labs/**/lab.yaml` existe. Le `meta.yml` ne fait qu'**ordonner** les
labs et **nommer** les blocs ; le rattachement compare le chemin relatif depuis
`labs/` aux entrées `sections[].labs[]`. L'`id` n'est qu'une clé CLI.

**4. Le zéro-bash est imposé.** Le validator **rejette** `cleanup.sh`,
`runtime/kvm.sh`, `runtime/incus.sh`, `runtime/shell.sh` et `Makefile` dans un
répertoire de lab. La préparation est déclarative (`lab.yaml`) ou Ansible
(`setup.yaml`).

**5. `fixtures/` et `runtime.fixtures` doivent dire la même chose.** Le runtime
shell itère sur `runtime.fixtures`, **pas** sur le répertoire `fixtures/` — les
deux peuvent donc diverger, et les deux sens échouaient en silence. Depuis la
0.1.84, plus aucun :

| Situation | Ce qui se passe |
| --- | --- |
| déclarée, absente du disque | `run` **échoue** (code 2) et nomme toutes les fautives d'un coup |
| présente sur le disque, non déclarée | `validate-structure` la signale (`content_fixture_undeclared`) |
| chemin qui sort du workdir | signalé, et refusé à l'exécution (`content_fixture_escapes`) |

La validation précède **toute** copie : c'est donc tout ou rien, parce qu'un
répertoire de travail à moitié rempli a l'air de marcher, et que l'apprenant
cherche alors l'erreur dans son propre travail. Ce défaut a rendu **7 labs
injouables le 2026-07-28**, tous marqués faits — il se cachait d'autant mieux
que les outils de vérification des corrigés copient, eux, le répertoire entier :
la solution passait au vert pendant que le parcours apprenant était cassé.

Les fichiers cachés (`.gitkeep`) sont exemptés : ils servent à versionner un
répertoire vide, et les signaler serait un faux positif que chaque auteur
apprendrait à ignorer.

Le chemin déclaré est préservé : `modules/stockage/main.tf` atterrit sous
`<workdir>/modules/stockage/main.tf`, répertoires intermédiaires compris.

**6. Une clé hors contrat est signalée, pas refusée.** Depuis la 0.1.54,
`validate-structure` nomme toute clé que le moteur ne lira jamais, avec la plus
proche qu'il lit vraiment au même niveau. Le parseur reste tolérant à dessein,
c'est une garantie de la v1 : ce contrôle est un lint, pas un refus de charger.

---

## Des tests qui prouvent

Un lab est noté par pytest avec `pytest-testinfra`, et les deux sont embarqués
dans dsoxlab : un catalogue n'installe aucun outillage de test.

Écrivez des assertions sur l'**état du système**, jamais sur les commandes
tapées. Pour un lab `vm`, le `conftest.py` du catalogue construit les hôtes
testinfra depuis l'inventaire que dsoxlab génère :

```python
from dsoxlab.infra.inventory import build_inventory, read_terraform_outputs, write_ssh_config
```

C'est le seul import qu'un catalogue fait de dsoxlab, et il existe pour qu'aucun
lab ne code une adresse IP en dur. L'hôte à inspecter est nommé par
`DSOXLAB_TARGET_HOST`, que `dsoxlab check --target <nom>` pose : sans le lire, un
lab multi-distributions ne teste jamais que son hôte par défaut.

Trois groupes Ansible sont injectés à l'exécution : `labenv` (tous les hôtes du
`meta.yml`, porteur des host_vars), `lab_target` (la cible résolue, celle que les
playbooks d'un lab doivent viser) et un `lab_<role>` par entrée de `roles`.

---

## Traductions

| Fichier | Surcharge |
| --- | --- |
| `lab.fr.yaml` | `title` et `description` de ce lab, et rien d'autre |
| `meta.fr.yml` | `repo.title`, `repo.description`, `sections[].title` et `sections[].description`, appariés **par `id`** |
| `course.fr.yaml` | Les titres de sections du cours |

Les fichiers de base portent l'anglais, puisque l'anglais est la langue par
défaut de l'outil.

`course.yaml` est ce qui permet à `dsoxlab course` d'afficher **une section à la
fois**, avec `--next`, `--prev` et `--section`, et de retenir où l'apprenant
s'est arrêté :

```yaml
sections:
  - id: navigation
    title: Se déplacer dans l'arborescence
    file: course/01-navigation.md
```

Sans lui, `course` retombe sur `scenario.md` + `README.md` affichés d'un bloc,
ce qui explique la longueur des cours longs.

---

## Les schémas, dans l'éditeur et en CI

Deux schémas JSON décrivent le même contrat, et un test les confronte au parseur
dans les deux sens pour qu'ils ne dérivent pas :
[`schemas/meta.schema.json`](../schemas/meta.schema.json) et
[`schemas/lab.schema.json`](../schemas/lab.schema.json).

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/stephrobert/dsoxlab/main/schemas/lab.schema.json
id: mon-lab
title: Mon lab
```

Tout éditeur qui fait tourner `yaml-language-server` complète alors les champs et
souligne les fautes à la frappe. En CI, la validation se fait sans installer
dsoxlab :

```bash
uvx check-jsonschema \
  --schemafile https://raw.githubusercontent.com/stephrobert/dsoxlab/main/schemas/lab.schema.json \
  $(find labs -name lab.yaml)
```

Remplacez `main` par un tag de version dans l'URL pour figer le schéma.

---

## Pour aller plus loin

- [Le contrat v1, champ par champ](./contract-v1.fr.md)
- [Où dsoxlab écrit](./files.fr.md)
- [L'infrastructure, pour le formateur](./trainer.fr.md)
