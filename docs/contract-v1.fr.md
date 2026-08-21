# Le contrat déclaratif, version 1

**Langue :** [English](./contract-v1.md) · [Français](./contract-v1.fr.md)

`meta.yml` et `lab.yaml` sont l'interface publique de dsoxlab. C'est ce
qu'écrit un auteur de catalogue, et c'est la seule chose qui relie son dépôt à
l'outil. Cette page fige ce que la version 1 de cette interface garantit.

Deux schémas JSON décrivent le même contrat pour ton éditeur et pour ta CI :
[`schemas/meta.schema.json`](../schemas/meta.schema.json) et
[`schemas/lab.schema.json`](../schemas/lab.schema.json). Un test les confronte
au parseur, ils ne peuvent donc pas dériver du code en silence.

---

## `schema_version`

Les deux fichiers acceptent un entier `schema_version` à leur racine.

```yaml
schema_version: 1
repo:
  id: ma-formation
  category: mon-domaine
```

| Situation | Ce que fait dsoxlab |
| --- | --- |
| Champ absent (tous les catalogues existants) | Lu en version **1**. Rien à changer. |
| `schema_version: 1` | Lu en version 1. |
| `schema_version:` laissé vide | Lu en version 1 : une valeur vide vaut une absence. |
| Une version plus récente que l'outil, dans un `lab.yaml` | Le lab est **écarté**, et un message nomme le fichier, la version et la réparation. Le reste du catalogue est servi normalement. |
| Une version plus récente que l'outil, dans `meta.yml` | La commande **s'arrête**. Le `meta.yml` décrit tout le catalogue : le lire de travers rendrait tout le reste douteux. |
| Tout ce qui n'est pas un entier YAML supérieur ou égal à 1 | Refusé, et `dsoxlab validate-structure` nomme le fichier et la valeur. |

La lecture est volontairement stricte là où le reste du contrat est tolérant :
`"1"`, `1.0` et `true` sont refusés. Un numéro de version n'est pas une mesure
qu'on arrondit : `1.5` deviendrait `1` sans un mot, et c'est précisément le
silence que ce champ existe pour supprimer.

`dsoxlab validate-structure` lit `schema_version` **directement sur le disque**,
avant la découverte. Cela compte : tous les autres contrôles itèrent sur des
labs déjà chargés, donc un fichier que le parseur rejette traverse d'ordinaire
la validation sans un mot. Celui-ci le voit.

> **À ne pas confondre avec la version de la sortie JSON.** `dsoxlab list-labs
> --json` produit un document qui porte son propre champ `schema`. Celui-là
> versionne ce que dsoxlab **écrit** pour d'autres programmes ; `schema_version`
> versionne ce que dsoxlab **lit** d'un catalogue. Deux contrats, deux publics,
> deux rythmes. On ne les incrémente jamais ensemble par réflexe.

---

## `meta.yml`, à la racine du dépôt

Seuls `repo.id` et `repo.category` sont obligatoires. Un dépôt dont tous les
labs sont `shell` n'a aucun bloc `infra:`, et c'est un cas prévu, pas un oubli.

### `repo` (obligatoire)

| Champ | Obligatoire | Type | Remarques |
| --- | --- | --- | --- |
| `id` | **oui** | chaîne | Slug du dépôt. Sert d'espace de noms au répertoire d'état et aux conteneurs de services. |
| `category` | **oui** | chaîne | Libre. Devient la `section` par défaut de chaque lab. dsoxlab ne connaît aucune liste de domaines. |
| `title` | non | chaîne | Nom lisible. |
| `blog_url` | non | chaîne | Page d'accueil du cours en ligne. |
| `description` | non | chaîne | Un paragraphe. |

### `infra` (optionnel, exigé par `runtime: vm`)

| Champ | Obligatoire | Type | Défaut | Remarques |
| --- | --- | --- | --- | --- |
| `provider` | non | chaîne **ou** liste de chaînes | `kvm` | Providers empaquetés dans l'outil : `kvm`, `incus`, `outscale`. Une liste signifie que l'apprenant choisit. |
| `network` | non | chaîne | | Réseau que rejoignent les VM, dédié à ce dépôt. |
| `cidr` | non | chaîne | | Sous-réseau de ce réseau. |
| `hosts` | non | liste de mappings | `[]` | Les VM. Voir ci-dessous. |
| `providers` | non | mapping | `{}` | Surcharges par provider, lues par le module Terraform correspondant. Valeurs libres : chaque provider a ses variables. Voir ci-dessous celles que lisent les templates empaquetés. |

Résolution du provider, première règle gagnante : `DSOXLAB_PROVIDER`, puis le
contexte de session posé par `dsoxlab use --provider`, puis une chaîne brute ou
une liste à un seul élément. Non résolu n'est pas une erreur : seules les
commandes d'infrastructure en exigent un.

### `infra.providers.<provider>`

Contenu libre, transmis tel quel au module Terraform du provider concerné. Une
clé mérite d'être nommée, parce qu'une machine neuve en a besoin :

| Champ | Provider | Obligatoire | Type | Défaut | Remarques |
| --- | --- | --- | --- | --- | --- |
| `storage_pool` | `kvm` | non | chaîne | `default` | Pool libvirt où sont créés les volumes. |

Le défaut est précisément ce qu'une installation de libvirt ne fournit pas
toujours : sur une Ubuntu 24.04 fraîche, `virsh pool-list --all` est vide, et
`provision` s'arrête sur un `Pool Not Found` brut de Terraform. Deux issues,
toutes deux prévues : créer le pool `default` (`dsoxlab doctor` affiche les
quatre commandes), ou pointer cette clé sur un pool que l'on possède déjà. Ne
jamais éditer le template empaqueté.

```yaml
infra:
  provider: kvm
  providers:
    kvm:
      storage_pool: labs-pool
```

### `infra.hosts[]`

| Champ | Obligatoire | Type | Défaut | Remarques |
| --- | --- | --- | --- | --- |
| `name` | **oui** | chaîne | | FQDN. Tout `runtime.targets[].host` et toute valeur de `roles` d'un lab doivent figurer ici. |
| `distro` | non | chaîne | | Pilote l'image et le cloud-init. Empaquetés aujourd'hui : `alma10`, `alma9`, `ubuntu26`, `ubuntu24`, `ubuntu22`, `debian13`, `debian12`. |
| `role` | non | chaîne | | Libre, exposé en host_var Ansible. |
| `ram_mb` | non | entier | `1024` | |
| `vcpu` | non | entier | `1` | |
| `disk_gb` | non | entier | `10` | |
| `extra_disk_gb` | non | entier | `0` | Deuxième disque, pour les labs qui exigent un vrai périphérique bloc (partitionnement, LVM, RAID). |
| `ip` | non | chaîne | | **Historique.** Les adresses viennent du provider et sont injectées dans l'inventaire généré. Ne pas les déclarer. |

### `sections[]` (optionnel)

| Champ | Obligatoire | Type | Remarques |
| --- | --- | --- | --- |
| `id` | **oui** | chaîne | Slug de la section. |
| `title` | non | chaîne | Affiché comme nom de bloc. |
| `description` | non | chaîne | Une ligne courte. |
| `labs` | non | liste de chaînes | Chemins relatifs à `<dépôt>/labs/`, dans l'ordre pédagogique. |

`sections` ordonne et nomme les blocs. Il ne décide jamais de l'existence d'un
lab : celle-ci tient à la présence de `labs/**/lab.yaml`, et le rattachement se
fait sur le chemin, jamais sur l'identifiant du lab.

### `meta.<langue>.yml`

Un `meta.fr.yml` posé à côté de `meta.yml` surcharge `repo.title`,
`repo.description`, `sections[].title` et `sections[].description` pour cette
langue, **et rien d'autre**. Toute autre clé y est ignorée, `labs` compris :
l'ordre pédagogique vit dans `meta.yml` et ne se traduit pas.

Les sections sont appariées par **`id`**, jamais par position : une section
insérée en tête de `meta.yml` décalerait sinon toutes les traductions
suivantes, en silence.

```yaml
# meta.yml — le fichier de base est en anglais, comme partout dans le contrat
sections:
  - id: getting-started
    title: Discover the tool
```

```yaml
# meta.fr.yml
sections:
  - id: getting-started
    title: Découvrir l'outil
```

C'est la même convention par fichier que `lab.<langue>.yaml` et
`course.<langue>.yaml`. Un suffixe de langue par champ (`title_en:`) ne fait
**pas** partie du contrat et n'est lu par personne : `dsoxlab
validate-structure` le signale.

---

## `lab.yaml`, un par lab

### Racine

| Champ | Obligatoire | Type | Défaut | Remarques |
| --- | --- | --- | --- | --- |
| `id` | **oui** | chaîne | | Unique dans le dépôt. La clé de la CLI. |
| `title` | **oui** | chaîne | | Titre anglais. |
| `level` | **oui** | chaîne | | Libre, jamais validé contre une liste. |
| `skills` | **oui** | liste de chaînes | | Ne doit pas être vide. |
| `distros` | **oui** | liste de chaînes | | Ne doit pas être vide. |
| `doc_url` | **oui** | chaîne | | `http(s)` uniquement. |
| `section` | non | chaîne | `repo.category` | Déclarée, elle est **toujours** conservée — y compris quand sa valeur se trouve nommer un domaine technique. |
| `description` | non | chaîne | `""` | |
| `track` | non | liste de chaînes | `[]` | |
| `difficulty` | non | chaîne | `beginner` | Jamais validé, seulement affiché. |
| `estimated_time` | non | chaîne | `30m` | Seulement affiché. |
| `certification_tags` | non | liste de chaînes | `[]` | Libre : l'outil reste agnostique du domaine. |
| `lab_type` | non | énuméré | `lab` | `lab`, `challenge` ou `capstone`. |
| `exam_passing_score` | non | entier | `0` | Seuil de réussite d'un examen blanc, en **pourcentage** du barème. Voir plus bas. |
| `bloc` | non | entier | dérivé | Normalement **pas écrit** : dérivé de `meta.yml` `sections[].labs[]`. |
| `bloc_order` | non | entier | dérivé | Même remarque. |
| `runtime` | non | mapping | défauts shell | Voir ci-dessous. |
| `validation` | non | mapping | voir plus bas | Purement déclaratif. |

`id`, `title` et `level` sont exigés par le **parseur** : sans eux, le fichier
n'est pas un lab. `skills`, `distros` et `doc_url` sont exigés par
`dsoxlab validate-structure` : le fichier se lit sans eux, mais le lab n'est pas
publiable.

### `exam_passing_score`

Un `lab_type: capstone` est un examen blanc, et un examen sans seuil de
réussite n'en est pas un. Déclare la barre, et dsoxlab rend un verdict :

```yaml
lab_type: capstone
exam_passing_score: 70   # pour cent du barème du lab
```

| Où | Ce que ça donne |
| --- | --- |
| `dsoxlab show` | Le seuil, avant que l'apprenant ne commence. |
| `dsoxlab submit` | « Examen réussi » ou « Examen échoué », avec le pourcentage et la barre. |
| `dsoxlab scores` | Une colonne **Verdict**, sur les catalogues qui portent au moins un examen. |

C'est un **pourcentage**, pas un nombre de points. Le barème d'un lab est celui
des `points` de son `challenge/hints.yaml` (100 par défaut, mais libre) : un
seuil absolu voudrait donc dire autre chose d'un lab à l'autre.

La comparaison est exacte : `score × 100 ≥ seuil × barème`. Une copie qui vaut
69,5 % du barème échoue à une barre de 70 %. Un seuil d'examen ne s'arrondit
pas en faveur du candidat.

Absent, ou à `0`, le lab n'est pas un examen et aucun verdict n'est jamais
rendu — c'est le cas de tout lab qui n'est ni un capstone ni un drill.
`dsoxlab validate-structure` refuse une valeur hors de `1..100`.

### `runtime`

| Champ | Obligatoire | Type | Défaut | Remarques |
| --- | --- | --- | --- | --- |
| `type` | non | énuméré | `shell` | `shell`, `vm`, et les alias de rétro-compatibilité `kvm` et `incus`. Écrire `vm` dans les nouveaux labs. |
| `targets` | pour `vm` | liste de mappings | `[]` | Ne doit pas être vide pour `vm`. |
| `default` | non | chaîne | | Doit correspondre à un `targets[].name`. |
| `snapshot_required` | non | booléen | `false` | Engage l'outil, ne l'informe pas. Voir plus bas. |
| `session` | non | énuméré | `target` | `target` : session SSH sur l'hôte. `local` : sous-shell local. N'a de sens que pour `vm`. |
| `workdir` | pour `shell` | chaîne | `challenge/work` | Ne doit pas être vide pour `shell`. Ignoré pour `vm`. |
| `fixtures` | non | liste de chaînes | `[]` | Chemins relatifs à `<lab>/fixtures/`, préservés sous `workdir`. |
| `services` | non | liste de mappings | `[]` | Conteneurs dont le lab a besoin le temps de l'exercice. |
| `topology` | non | chaîne | `local` | **Déprécié.** Plus rien ne le lit. |

Une fixture **non déclarée** n'est **pas copiée**, même présente dans
`fixtures/`. Un chemin absolu, ou qui contient `..`, est refusé : une fixture
n'écrit jamais hors du workdir.

#### `runtime.snapshot_required`

Ce champ **engage l'outil**. Déclarer `true` change trois commandes :

| Commande | Avec `snapshot_required: true` |
| --- | --- |
| `run` | Prend un point de reprise **avant** le `setup.yaml`, et **échoue** s'il n'y arrive pas. Le lab ne démarre pas sans le filet qu'il réclame. |
| `reset` | Ramène la machine au point de reprise au lieu de rejouer le `cleanup.yaml`, puis rejoue le `setup.yaml`. |
| `clean` | Retire le point de reprise, et avec lui le fichier de recouvrement qu'il avait créé. |

Un lab qui se passe de filet déclare `false`, ce qui est le défaut et ce que
déclarent aujourd'hui tous les labs de tous les catalogues.

**Ce qu'un point de reprise dsoxlab capture, et ce qu'il ne capture pas.** Sur
le provider `kvm`, c'est un **snapshot externe de disque** (`virsh
snapshot-create-as --disk-only --atomic`), jamais un snapshot interne : le
template Terraform packagé démarre ses machines en UEFI, et libvirt refuse les
snapshots internes sur un firmware pflash. Trois conséquences, écrites ici
plutôt que laissées à découvrir :

- **le disque est capturé, la mémoire ne l'est pas.** Le retour arrière
  redémarre la machine depuis un état disque cohérent, il ne la replace pas
  dans la seconde d'avant. Pour un lab c'est le bon compromis, mais un lab dont
  l'exercice repose sur un processus en cours doit le relancer, pas l'attendre ;
- **un point de reprise crée un fichier de recouvrement** à côté du disque.
  `clean` et `destroy` le retirent, rien d'autre : un lab qui prend un point de
  reprise et n'est jamais nettoyé en laisse un jusqu'à la destruction de
  l'infrastructure ;
- **revenir en arrière n'est pas un `virsh snapshot-revert`.** dsoxlab arrête la
  machine, vide le recouvrement et la redémarre. Le point de reprise survit,
  donc il resert ; mais il doit rester la couche du dessus du disque, et dsoxlab
  refuse le retour arrière quand ce n'est plus le cas, plutôt que de jeter le
  mauvais fichier.

#### `runtime.targets[]`

| Champ | Obligatoire | Type | Remarques |
| --- | --- | --- | --- |
| `name` | **oui** | chaîne | Identifiant court de la CLI, passé à `--target`. |
| `host` | **oui** | chaîne | FQDN, doit figurer dans `meta.yml` `infra.hosts[].name`. |
| `label_en` | non | chaîne | |
| `label_fr` | non | chaîne | |
| `roles` | non | mapping | Hôtes additionnels par rôle. Chaque rôle devient le groupe Ansible `lab_<role>`. |

#### `runtime.services[]`

| Champ | Obligatoire | Type | Défaut | Remarques |
| --- | --- | --- | --- | --- |
| `name` | **oui** | chaîne | | Unique dans le lab. C'est aussi le **nom d'hôte** sous lequel les autres services le joignent. |
| `image` | **oui** | chaîne | | Image, tag compris. dsoxlab lance exactement ce que tu déclares. |
| `ports` | non | liste de chaînes | `[]` | Publications Docker `-p`, `hôte:conteneur`. |
| `run_args` | non | liste de chaînes | `[]` | Arguments bruts ajoutés au `docker run`. |
| `env` | non | mapping | `{}` | `-e NOM=valeur`. |
| `ready_tcp` | non | entier | `0` | Port **de l'hôte** à sonder. Sur un port publié, il ment à lui seul : le proxy Docker accepte avant que le service écoute. |
| `ready_exec` | non | chaîne ou argv | `[]` | Sonde jouée **dans** le conteneur, réessayée jusqu'au succès. Le seul signal de disponibilité fiable. |
| `ready_timeout` | non | entier | `90` | Secondes, pour les deux sondes. |
| `post_start` | non | liste de chaînes ou d'argv | `[]` | Commandes jouées dans le conteneur une fois prêt. **Rejouées à chaque démarrage**, elles doivent donc être idempotentes. |

### `validation`

| Champ | Obligatoire | Type | Défaut |
| --- | --- | --- | --- |
| `functional` | non | booléen | `true` |
| `security` | non | booléen | `false` |
| `persistence_after_reboot` | non | booléen | `false` |

Purement déclaratif. dsoxlab ne lit jamais ce bloc pour décider quoi que ce
soit : ce sont les tests qui prouvent.

### `lab.<langue>.yaml`

Un `lab.fr.yaml` posé à côté de `lab.yaml` surcharge `title` et `description`
pour cette langue, **et rien d'autre**. Toute autre clé y est ignorée, et
`validate-structure` le dit. Un `id` y est toléré sans être lu : il nomme le
lab pour qui ouvre le fichier.

---

## Valeurs énumérées de la v1

| Champ | Valeurs |
| --- | --- |
| `lab_type` | `lab`, `challenge`, `capstone` |
| `runtime.type` | `shell`, `vm`, `kvm`, `incus` |
| `runtime.session` | `target`, `local` |
| `schema_version` | `1` |

Tout le reste est libre à dessein : `level`, `difficulty`, `section`, `skills`,
`distros`, `track`, `certification_tags` et `repo.category` appartiennent au
catalogue, pas au moteur. Une liste fermée y ferait connaître un domaine
technique à dsoxlab, ce qu'il ne doit pas.

---

## Ce que la v1 garantit, et ce qui la casserait

**Stable.** Chaque champ ci-dessus garde son nom, son type et son sens pendant
toute la vie de la v1. Un fichier valide en v1 reste lisible par tout dsoxlab
qui déclare lire la v1.

**Permis sans changer de version :**

- ajouter un champ **optionnel**. Un dsoxlab plus ancien l'ignore, ce qu'il
  faisait déjà de toute clé inconnue ;
- ajouter une valeur à un énuméré, quand l'employer reste optionnel ;
- relâcher une contrainte (un champ qui devient optionnel).

**Exige une version 2 :**

- retirer un champ, ou le renommer ;
- rendre obligatoire un champ optionnel ;
- changer le type ou le sens d'un champ existant ;
- retirer une valeur d'un énuméré ;
- changer un défaut.

Les clés inconnues sont **ignorées par le parseur**, **refusées par les schémas
JSON** (`additionalProperties: false`) et **signalées par `dsoxlab
validate-structure`**. La combinaison est voulue, et chaque pièce répond à un
besoin différent :

- le **moteur** reste tolérant, pour qu'un outil v1 survive à un catalogue
  v1.1. Cela ne changera pas : c'est ce qui fait tenir le versionnement ;
- ton **éditeur** souligne `skils:` pendant que tu l'écris ;
- `validate-structure` échoue dessus, parce que toléré n'est pas voulu. Quatre
  clés écrites de bonne foi vivaient dans les catalogues réels sans que
  personne ne les lise, dont un `exam_passing_score` dans onze labs d'examen :
  leur auteur croyait poser un seuil de réussite, et rien ne le posait. À la
  racine d'un `lab.yaml`, une clé inconnue est une faute de frappe ou une
  attente déçue, presque jamais une extension délibérée.

Le contrôle porte sur `meta.yml`, `lab.yaml` et leurs fichiers de traduction,
et il descend dans chaque bloc que le contrat décrit. Il ne descend **pas**
dans les mappings libres — `runtime.targets[].roles`,
`runtime.services[].env`, `infra.providers.<provider>` — dont les clés
appartiennent au catalogue.

Si un schéma ou `validate-structure` signale une clé à laquelle tu crois, c'est
que cette clé n'est pas dans le contrat : vérifie sur cette page.

---

## Chemin de migration vers une future v2

Il n'en existe aucune aujourd'hui : `1` est la seule version que dsoxlab lit, et
aucun catalogue ne déclare le champ. Voici le chemin qu'elle prendra, énoncé
maintenant pour ne pas être improvisé plus tard.

1. **Une v2 s'annonce dans le CHANGELOG**, avec la liste exacte de ce qui
   change, avant que le moindre outil ne l'impose.
2. **L'outil apprend la v2 avant que les catalogues s'en servent.** Un dsoxlab
   qui lit la v2 continue de lire les fichiers v1 tels quels. Les deux versions
   cohabitent pendant au moins une version mineure.
3. **On met l'outil à jour d'abord**, le catalogue ensuite :
   `uv tool upgrade dsoxlab`. Cet ordre n'est pas une préférence. Un fichier v2
   lu par un outil v1 est écarté ; un fichier v1 lu par un outil v2 fonctionne
   toujours.
4. **On migre fichier par fichier.** `schema_version` vaut par fichier, pas par
   dépôt : un catalogue peut porter des labs v1 et v2 à la fois. C'est
   exactement pourquoi un lab illisible est écarté plutôt que fatal : sans cela,
   personne ne pourrait jamais publier le premier lab v2 sans casser le
   catalogue de tous les apprenants pas encore à jour.
5. **`dsoxlab validate-structure` est la commande qui aide.** Elle lit
   `schema_version` sur le disque, avant la découverte, et rapporte donc en une
   passe tous les fichiers en retard ou en avance, y compris ceux qu'aucun autre
   contrôle ne peut voir.

---

## Se servir des schémas

### Dans ton éditeur

Pose cette ligne en tête du fichier. L'extension YAML de VS Code, et tout
éditeur qui fait tourner `yaml-language-server`, complètent alors les champs et
soulignent les fautes à la frappe.

Dans `lab.yaml` :

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/stephrobert/dsoxlab/main/schemas/lab.schema.json
id: mon-lab
title: Mon lab
```

Dans `meta.yml` :

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/stephrobert/dsoxlab/main/schemas/meta.schema.json
repo:
  id: ma-formation
  category: mon-domaine
```

C'est un commentaire YAML : dsoxlab l'ignore, comme tout outil qui ne le
cherche pas.

### En CI, sans installer dsoxlab

Les URL sont de simples fichiers, que n'importe quel validateur JSON Schema sait
récupérer. C'est tout l'intérêt de les publier : un dépôt de catalogue peut
vérifier son propre YAML sans dépendre de l'outil Python.

### Quelle URL employer

Deux formes, qui répondent à deux questions différentes.

| Forme | URL | À employer quand |
| --- | --- | --- |
| Mouvante | `https://raw.githubusercontent.com/stephrobert/dsoxlab/main/schemas/lab.schema.json` | Tu écris un catalogue et tu veux que le schéma suive le contrat au fil de ses évolutions. C'est le `$id` du schéma lui-même. |
| Épinglée | `https://raw.githubusercontent.com/stephrobert/dsoxlab/v0.1.46/schemas/lab.schema.json` | Tu es en CI et tu veux un résultat qui ne bouge pas sous tes pieds. Remplace `v0.1.46` par la version que tu vises. |

**Pourquoi `raw.githubusercontent.com` plutôt qu'un domaine à nous.** Une URL de
schéma n'a qu'un métier : résoudre, pour toujours, vers exactement les octets
vers lesquels elle résolvait hier. Un tag sur un dépôt public fait cela sans
aucune infrastructure à tenir, sans certificat à renouveler et sans redirection
à oublier, et il est versionné par la release elle-même : le tag qui porte le
code porte le schéma qui le décrit. Un domaine dédié ajouterait un service à
maintenir en vie pour un fichier qui ne change pas, et un service qui meurt
emporte l'éditeur de tous les auteurs. Le prix est une URL que personne ne
trouvera jolie, et une dépendance à GitHub, que le dépôt a déjà.

**Pourquoi `$id` pointe vers `main` et non vers un tag.** `$id` est l'identité
du schéma, pas celle d'une release. Le réestampiller à chaque tag donnerait au
même schéma une identité différente dans chaque version, ce que `$id` existe
justement pour éviter. L'épinglage a sa place dans la ligne que tu écris dans
ton fichier, où tu peux la choisir ; l'identité a la sienne dans le schéma, où
tu ne le peux pas.
