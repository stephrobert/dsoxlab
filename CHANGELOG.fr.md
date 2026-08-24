# Journal des modifications

**Langue :** [English](./CHANGELOG.md) · [Français](./CHANGELOG.fr.md)

Toutes les modifications notables du projet sont documentées dans ce fichier.

Le format s'appuie sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et le projet suit le [versionnage sémantique](https://semver.org/lang/fr/).

## [Non publié]

## [0.1.67] - 2026-08-24

### Ajouté

- **`dsoxlab catalog` : installer un catalogue, et l'utiliser depuis n'importe
  où** (issue #78). Séparer le moteur des catalogues est une bonne décision
  d'architecture, mais elle était entièrement à la charge de l'utilisateur :
  rien ne disait quels catalogues existent, comment en installer un, ni qu'il
  fallait lancer dsoxlab depuis l'intérieur du répertoire cloné. Cinq
  sous-commandes comblent l'écart :

  ```console
  $ dsoxlab catalog list              # les connus, et ceux qui sont installés
  $ dsoxlab catalog add linux         # le cloner, et le rendre actif
  $ cd ~ && dsoxlab list-labs         # marche, sans se placer dedans
  $ dsoxlab catalog use ansible       # changer l'actif
  $ dsoxlab catalog update [<id>]     # en mettre un à jour, ou tous
  $ dsoxlab catalog remove <id>       # en retirer un
  ```

  **Le répertoire courant reste prioritaire.** Le catalogue actif n'est consulté
  qu'**après** la remontée depuis le répertoire de travail, jamais avant : qui
  se place dans un catalogue cloné à la main s'attend à travailler dessus.
  L'inverse ferait qu'un `catalog add` changerait silencieusement ce que fait un
  `dsoxlab check` lancé dans un dépôt existant : un effet de bord muet, à
  distance, et sur la commande qui note le travail.

  Le registre des catalogues connus est un **manifeste packagé avec l'outil**
  (`templates/catalogues.yml`), pas un service distant : un registre est un
  composant à héberger, surveiller et maintenir disponible, pour un projet qui
  compte aujourd'hui trois catalogues. Un manifeste versionné a de plus un
  mérite qu'un service n'a pas — il est révisable en pull request : proposer un
  catalogue tiers devient une contribution ordinaire. N'importe quelle URL git
  est acceptée aussi, y compris absente du manifeste : le manifeste facilite la
  découverte, il ne restreint rien.

  Le moteur reste neutre vis-à-vis des domaines, et un test l'impose :
  `services/catalog.py` ne contient aucun nom de domaine, seulement des
  identifiants et des URL venus du manifeste ou de la ligne de commande.

### Corrigé

- **Un nom de fonction de test pouvait faire échouer le commit pour fuite de
  secret.** Le hook `trufflehog` tourne avec `--results=verified`, ce qui est la
  bonne exigence : il ne bloque que sur un secret vérifié. Mais son détecteur
  *Lob* reconnaît les clés de test de ce service à leur seul préfixe `test_`, et
  une clé Lob de test est vérifiée **sans appel réseau**. Mesuré contre la
  commande exacte du hook : un nom de **quarante caractères précisément** le
  déclenche, 39 et 41 non.

  Sept noms de tests du dépôt portaient déjà cette forme. Aucun n'avait jamais
  rien déclenché, le hook ne lisant que le diff : ils attendaient le premier
  contributeur qui toucherait à leur fichier. Ils sont renommés, et un test
  refuse désormais cette longueur dans `tests/`, `tests_e2e/` et `fuzz/`, pour
  que le défaut se dise là, en une seconde et avec sa raison, plutôt qu'au
  `pre-push` sous les traits d'une fuite de secret.

  **Le détecteur n'a pas été exclu.** Retirer Lob aurait réglé le symptôme en
  retirant une capacité de détection, pour un service que le projet n'utilise pas
  aujourd'hui mais dont rien ne dit qu'il ne l'utilisera jamais. Renommer coûte
  un mot et n'enlève rien au scan.


- **Le garde-fou de publication n'était pas fiable, de deux façons, toutes deux
  constatées en publiant les 0.1.65 et 0.1.66.** Il garde une publication qui ne
  se défait pas, donc s'y tromper coûte plus cher qu'ailleurs. Rien ne change
  dans la roue publiée : `scripts/` est de l'outillage de développement, d'où
  l'absence de bump de version.

  - *Il comptait les fichiers non suivis comme un arbre sale.* Ce dépôt porte en
    permanence des nœuds `/dev/null` à sa racine (`.bashrc`, `.gitconfig`,
    `.idea`, `.mcp.json`…), que `git status --porcelain` liste en non suivis. Le
    contrôle passait donc ou échouait selon que ces montages étaient visibles à
    cet instant, c'est-à-dire par intermittence, dans l'outil même qui garde une
    publication définitive. Or un garde-fou qui se déclenche au hasard finit
    contourné. Seules les modifications de fichiers **suivis** bloquent
    désormais un tag ; les non suivis sont nommés dans un avertissement, parce
    qu'un `git add` oublié est un vrai risque qu'aucun script ne peut trancher à
    la place de qui écrit le code.
  - *`--publiee <tag>` ignorait le tag qu'on lui donnait* et interrogeait PyPI
    sur la version empaquetée du moment. Une fois la version suivante fusionnée,
    `--publiee v0.1.65` annonçait « la version 0.1.66 est absente de PyPI » :
    un verdict faux, sur une version pourtant bien livrée.

  Le script n'avait aucun test. Il en a cinq, chacun rouge sans sa correction.

## [0.1.66] - 2026-08-24

### Corrigé

- **Un conteneur arrêté était rapporté comme une commande d'initialisation en
  échec.** Quand `post_start` tombait sur un conteneur qui ne tournait plus,
  Docker répondait `container <64 caractères hexadécimaux> is not running`, et
  dsoxlab reprenait cette phrase dans « l'initialisation du service « x » a
  échoué sur « y » ». Deux erreurs à la fois : cela envoyait chercher un défaut
  dans une commande qui n'avait jamais été jouée, et cela désignait le conteneur
  par un identifiant que personne n'avait jamais vu. Le message dit maintenant
  que le conteneur s'est arrêté, donne son **code de sortie** et les **dix
  dernières lignes de ses logs**, et nomme le conteneur tel qu'il a été déclaré.
  Le contrôle n'a lieu qu'après l'échec d'un `docker exec` : un service sain
  n'est jamais interrogé pour rien.

- **Le contrôle de documentation était rouge chez le contributeur et vert en
  intégration continue.** Il lisait tous les Markdown de la racine, y compris
  ceux que git ne suit pas. Un `CLAUDE.md` citant `~/.config/dsoxlab/config.yaml`
  pour dire que ce chemin n'existe pas encore suffisait à faire échouer deux
  tests en local, là où l'intégration continue, qui n'a pas ce fichier, restait
  verte. Le contrôle ne retient plus que les fichiers versionnés, et retombe sur
  tout ce qu'il trouve s'il n'y a pas de dépôt git, pour qu'une archive extraite
  ne rende pas le contrôle vert en le vidant.

### Modifié

- **Les deux tests d'intégration Docker de `services` déclarent enfin la sonde
  `ready_exec` que le contrat recommande** (issue #155). Ils enchaînaient un
  `docker exec` juste après `start()` sans que rien n'ait prouvé que le
  conteneur pouvait en recevoir un : l'attente implicite tenait à la charge de
  la machine. Leurs messages d'échec portent aussi l'état du conteneur, son code
  de sortie et ses logs : un échec intermittent en intégration continue ne
  laisse aucune autre trace, et un `assert x.ok` nu ne laissait rien à
  diagnostiquer.
## [0.1.65] - 2026-08-24

### Ajouté

- **`--json` couvre désormais toutes les commandes dont la sortie a une
  structure.** `show`, `scores`, `next`, `doctor` et `validate-structure`
  rejoignent `list-labs`, `progress`, `check`, `status` et `support` : dix
  commandes, un document chacune, toutes passant par `machine.emit()` et
  portant donc `schema`. Une intégration ne pouvait lire qu'un quart de ce que
  l'outil sait ; pour le reste, elle devait analyser des tableaux Rich dont la
  largeur dépend du terminal.

- **Un verdict se lit sans le traduire.** `doctor` donne à chaque contrôle une
  `key` stable (`kvm`, `pytest`, `libvirt_pool`…) et un `state` en jeton (`ok`,
  `failed`, `choice_required`) ; `validate-structure` donne à chaque anomalie la
  `key` de la règle qui a parlé, ses `params`, et un `kind` qui nomme la
  famille. Le libellé traduit est posé à côté, pour l'affichage seulement. La
  conception paresseuse aurait recopié la phrase affichée dans un champ :
  d'apparence complète, et inutilisable, puisque aucun consommateur ne peut
  distinguer le vert du rouge sans analyser du français ou de l'anglais. Un test
  joue `doctor --json` dans les deux langues et exige des clés et des états
  identiques là où les libellés diffèrent.

- **[Une page de documentation pour la sortie machine](docs/machine-output.fr.md)
  ([EN](docs/machine-output.md))** : chaque document champ par champ, les codes
  de retour, et la règle d'évolution. Un champ ajouté laisse `schema` où il
  est ; un champ qui change de sens l'incrémente. Le texte traduit et la sortie
  brute de pytest sont explicitement hors du contrat ; les jetons stables et les
  codes de retour y sont. Le `fullhelp` a gagné la section correspondante, dans
  les deux langues.

### Corrigé

- **Un diagnostic qui plantait en diagnostiquant.** `virsh version` et
  `incus list` sont joués avec un délai de cinq secondes, et la `TimeoutExpired`
  n'était pas rattrapée : sur un hôte dont la socket libvirt ne répond jamais,
  elle emportait toute la commande `doctor`. Depuis que `doctor --json` est une
  interface, elle emportait avec elle le document de l'appelant et lui rendait
  une trace Python. Une sonde qui ne répond pas est désormais rapportée comme un
  composant qui ne répond pas, avec le geste qui le corrige.

### Modifié

- `doctor --json --fix` est refusé, et dit pourquoi : les commandes de
  remédiation écrivent sur la sortie standard, et le document sortirait précédé
  de la sortie d'apt. On lit le diagnostic d'abord, on agit ensuite.

- `Check` porte son identité (`key`) et en dérive son libellé, au lieu de les
  écrire tous les deux à chaque appel, où rien n'empêchait qu'ils divergent. Son
  `status_key` devient un `state`, pour que le mot affiché au terminal et le
  jeton rendu à un programme viennent de la même source.

Closes #83.

## [0.1.64] - 2026-08-24

### Corrigé

- **Un output Terraform mal formé faisait planter la construction de
  l'inventaire.** `{"hosts": {"value": "10.99.0.11"}}` suffisait : le code
  prenait la valeur pour un objet et appelait `.items()` dessus, ce qui rendait
  un `AttributeError` au moment de jouer un lab, sans jamais dire que la cause
  était un state Terraform périmé. Ce document fait trente-quatre octets et
  personne ne l'avait écrit à la main : c'est le nouveau harnais de fuzzing qui
  l'a trouvé, en moins de trente mille exécutions.

### Ajouté

- **Le fuzzing couvre désormais toutes les entrées que le moteur ne produit pas
  lui-même.** Deux harnais s'ajoutent aux deux existants, et chacun assère un
  contrat différent, parce que chaque entrée est non fiable pour une raison
  différente :

  - **`.dsoxlab-context.json`** vit sur le disque de l'apprenant : édité à la
    main par curiosité, tronqué par un portable refermé au mauvais moment,
    laissé par une version ancienne. Son harnais n'a **aucune exception de
    contrat**, et c'est tout son propos : `read_context` promet de rendre un
    contexte vide plutôt que de lever, parce que perdre le contexte coûte un
    `dsoxlab use` alors qu'une exception coûte la CLI entière.
  - **Les outputs Terraform** viennent d'un binaire externe dont la version,
    les providers et le schéma de sortie bougent sans que dsoxlab le sache. Le
    harnais vise ce que `build_inventory` **fait** du document, et non le
    `json.loads` qui le précède : celui-là est déjà protégé, et le fuzzer n'y
    mesurerait que la bibliothèque standard.

  Le commentaire du job de CI énumère les entrées couvertes et dit, pour
  chacune, pourquoi elle n'est pas fiable.

## [0.1.63] - 2026-08-24

- **La documentation décrivait un produit qui n'existe pas.** Trois
  affirmations de la section « Persistence » des deux README étaient fausses, et
  c'étaient celles que suit un lecteur cherchant ses notes : une base
  `~/.local/share/dsoxlab/progress.db`, un fichier de configuration utilisateur
  `~/.config/dsoxlab/config.yaml`, et `XDG_DATA_HOME` / `XDG_CONFIG_HOME` pour
  les déplacer. La base est `<catalogue>/.dsoxlab.db`, une par catalogue, et
  aucun fichier de configuration n'est lu nulle part. Quatre autres
  affirmations ont suivi le même chemin : une progression « conforme à la
  spécification XDG », `incus` et `kvm` présentés comme des runtimes (il y en a
  deux, `shell` et `vm`, et le backend est le choix du catalogue), une carte
  d'architecture nommant des classes `IncusRuntime` et `KvmRuntime` qui
  n'existent pas, et un champ `runtime.host` dans l'exemple de `lab.yaml` le
  plus en vue, qu'aucun code ne lit.

- L'aide de `--lab-home` annonçait « racine du dépôt linux-training », nommant
  un catalogue comme s'il était le seul, dans les deux langues. Elle dit
  désormais « le catalogue de labs ».

### Ajouté

- **Un contrôle qui interdit à la dérive de recommencer.** Les emplacements de
  fichiers documentés sont désormais confrontés au code comme l'était déjà la
  table des commandes : `scripts/generer-doc.py` relève les emplacements réels
  **en appelant les fonctions que la CLI appelle**, sur un `HOME` jetable, puis
  signale tout chemin qu'une page cite et qui ne correspond à aucun d'eux.
  Prouvé par mutation, et par six tests dans
  `tests/test_documentation_synchrone.py`. Un chemin peut être cité pour dire
  qu'il **n'**existe **pas**, mais par la seule page dont c'est le sujet, et un
  test vérifie qu'il est bien absent du code.

### Modifié

- **Documentation découpée par public**, chaque page nommant son lecteur dès ses
  premières lignes : [l'apprenant](docs/learner.fr.md), [l'auteur de
  catalogue](docs/catalog-author.fr.md), [le formateur](docs/trainer.fr.md),
  plus deux références communes aux trois ([où dsoxlab écrit](docs/files.fr.md)
  et [les commandes](docs/commands.fr.md), toujours produites par la CLI). Les
  deux README gardent leur rôle de porte d'entrée et se lisent maintenant en
  trente secondes. Aucun générateur de site n'est introduit : cette décision
  appartient au propriétaire du dépôt.

- `Documentation` dans `pyproject.toml` pointe sur la documentation de l'outil
  plutôt que sur l'index générique d'un blog. La carte de l'architecture a
  déménagé dans `CONTRIBUTING.fr.md`, corrigée, là où les contributeurs à qui
  elle s'adresse la trouveront.

Closes #86.

## [0.1.62] - 2026-08-24

### Corrigé

- **Le premier `Tab` d'une session ne proposait rien**, le second fonctionnait.
  zsh charge le fichier `#compdef` à la première tabulation et attend qu'il
  produise les propositions **de cette invocation-là** ; le script que typer
  génère se contente de définir la fonction, puis de l'enregistrer pour la
  suite. Un `Tab` muet se lit comme « la complétion ne marche pas », et personne
  ne rappuie une seconde fois pour vérifier une fonctionnalité qu'il croit
  absente : le coût est un abandon silencieux, pas une gêne. Le script installé
  appelle désormais sa fonction après l'avoir enregistrée, et la raison de cette
  divergence avec l'amont est écrite **dans le fichier posé**, pour que personne
  ne la retire un jour sans savoir pourquoi elle existe. Reproduit et vérifié
  dans un zsh réel sous pseudo-terminal, avant et après : un appel direct au
  mécanisme de complétion ne traverse pas la couche en cause.

### Ajouté

- **`dsoxlab completion install` et `dsoxlab completion show`.** Le premier
  installe l'auto-complétion, le second imprime le script sans rien écrire, pour
  qui veut le poser lui-même.

### Déprécié

- **`dsoxlab install` est déprécié, et sera retiré en 0.3.0.** C'était le premier
  nom de commande que voyait un utilisateur dans l'aide, et il promettait
  d'installer l'outil, déjà installé. Il continue de faire ce que fait
  `completion install`, en le signalant.

  Il **n'écrit plus de wrapper** dans `~/.local/bin`. Deux défauts vécus tenaient
  à ce fichier : un chemin contenant une espace cassait le `exec` faute de
  quoting, et surtout `write_text()` sur un lien symbolique écrit dans **la
  cible**, donc le binaire réel d'`uv` était remplacé par un script pointant sur
  lui-même. `uv tool install` et `pipx` posent déjà leur lanceur exactement là :
  le remplacer ne faisait que défaire ce que leur prochaine mise à jour
  remettrait.

## [0.1.61] - 2026-08-24

### Ajouté

- **Les schémas publiés sont désormais éprouvés sur des documents, pas seulement
  sur des noms de clés.** Le contrôle existant compare, par analyse syntaxique
  de `models/`, les clés que le parseur lit aux `properties` du schéma : il
  attrape une clé oubliée ou inventée, et rien de ce qui se trouve à
  l'intérieur. Un `type` faux, un `enum` incomplet, un `pattern` trop lâche ou
  une borne à côté passaient donc sans un mot. Ces défauts-là ne dérangent
  jamais dsoxlab, qui ne lit pas ses propres schémas : ils dérangent l'auteur de
  catalogue, dans son éditeur et dans sa CI. Un schéma faux fait autorité à
  tort, ce qui est la position la moins confortable possible.

  Le contrôle va maintenant dans les deux sens. Le catalogue de démonstration
  packagé, celui que `dsoxlab demo` dépose, est validé fichier par fichier ; et
  seize documents fautifs, **une faute chacun**, doivent être refusés, à
  l'endroit exact de la faute. Chaque cas part du document valide, ce qui rend
  la preuve solide : si la base passe et que la variante échoue, c'est bien la
  faute qui a été refusée, et pas autre chose.

### Interne

- `jsonschema` entre en dépendance de **développement**, jamais de runtime : le
  moteur a son propre parseur et n'a pas à valider par le schéma à l'exécution.

## [0.1.60] - 2026-08-24

### Corrigé

- **Un catalogue mal formé parlait français sous `DSOXLAB_LANG=en`.** Chaque
  message affiché par `validate-structure` venait d'un champ `message` écrit à
  la main dans une dataclass de validator, qu'aucun garde-fou ne pouvait voir :
  les quatre puits que surveille le garde-fou i18n (`help=`, les helpers
  d'affichage, `raise`, les verbes de sortie de Rich) ne couvrent pas une valeur
  rangée dans une dataclass. `ContentIssue`, `MetadataIssue` et `StructureIssue`
  portent désormais une **clé** et ses paramètres, exactement comme
  `ContractIssue` le faisait déjà, et c'est la CLI qui compose la phrase. 39
  clés ajoutées en anglais et en français. `check_doc_url()` suit la même
  règle : il rend une `ContentIssue` au lieu d'un motif qu'il rédigeait.

- **Les erreurs de contrat du `meta.yml` étaient françaises elles aussi**, et
  celles-là atteignent l'écran : `discovery/repo.py` les laisse remonter et
  `cli.py` les affiche. Elles sont levées en `ContractError`, qui porte
  `source`, `field`, une clé i18n et ses paramètres, le patron que
  `UnsupportedSchemaVersion` et `ProviderUnresolved` suivaient déjà. Le modèle
  reste agnostique de la langue ; la CLI dit la phrase et l'encadre du chemin
  du fichier.

- **Un champ mal typé du `meta.yml` rendait un traceback brut sur
  `list-labs`**, parce que le scanner relit ce fichier pour l'ordre des
  sections et que rien n'attrapait l'erreur sur ce chemin, là où les autres
  commandes passaient par `_read_repo` et obtenaient une phrase. Les deux
  chemins passent désormais par le même helper.

### Changé

- Les 24 `ValueError` de `models/` ont été triées sur une seule question : ce
  message atteint-il un humain qui lit l'interface ? 17 oui, par le `meta.yml`,
  et suivent le patron. 7 non : elles viennent d'un `lab.yaml`, dont le seul
  lecteur est `discovery/scanner.py`, qui écarte le lab et journalise la
  raison. Celles-là lèvent une `LabYamlError` dont le texte reste technique,
  parce que traduire ce qui ne s'affiche jamais est du travail perdu et du
  bruit dans les tables de traduction.

- Le garde-fou i18n couvre désormais `models/`, dont l'exclusion en bloc
  disparaît, et gagne un cinquième puits pour les anomalies que
  `validate-structure` affiche. Il connaît `LabYamlError` par son nom, ce qui
  rend le tri **vérifiable** : le jour où l'un de ces messages doit s'afficher,
  il change de classe et le garde-fou réclame sa clé.

Closes #139.

## [0.1.59] - 2026-08-23

### Modifié

- **La description du projet disait ce que l'outil fait pour son auteur.**
  « Un framework CLI neutre vis-à-vis du domaine qui pilote des labs répartis
  dans plusieurs dépôts » était juste quand elle a été écrite. Ce qui a changé
  depuis n'est pas une fonctionnalité, c'est la nature de l'outil : le contrat
  déclaratif, les runtimes interchangeables, la validation et les diagnostics en
  font un moteur que quelqu'un d'autre peut employer pour ses propres exercices.
  Les quatre emplacements (`pyproject.toml`, la description GitHub, les deux
  README et `fullhelp`) portent désormais la même phrase : dsoxlab transforme des
  exercices déclaratifs en environnements **reproductibles, exécutables et
  vérifiables**.

- **`fullhelp` annonçait des runtimes qui n'existent plus.** Il promettait un
  « conteneur incus ou VM KVM » là où le contrat n'expose que deux types,
  `shell` et `vm` : Incus est un backend de `vm`, choisi par le `meta.yml` du
  catalogue, pas un runtime que l'apprenant déclare. Il liait aussi chaque lab à
  un guide d'un site précis, et énumérait des niveaux (`l1`, `lfcs`, `rhcsa`)
  qui appartiennent à un catalogue particulier, alors que c'est le catalogue qui
  nomme ses sections et ses niveaux.

## [0.1.58] - 2026-08-23

### Corrigé

- **`doctor` affichait « 0 lab » sans dire pourquoi.** `list-labs` explique très
  bien, lui : il nomme le fichier, la version en cause et la commande qui
  répare. `doctor` se contentait d'un rouge muet, alors que c'est lui qu'on
  lance quand quelque chose cloche, et lui qu'on colle dans un rapport de bug.
  Le contrôle compare désormais les `lab.yaml` **présents sur le disque** aux
  labs réellement chargés, et nomme l'écart. Cet écart couvre d'un coup les
  trois façons dont un lab devient invisible, sans avoir à deviner laquelle
  s'applique : un `schema_version` trop récent, un fichier qui lève au parsing,
  ou un lab déclaré au `meta.yml` mais absent du disque.

- **Un `lab.yaml` qui lève au parsing n'allait qu'au journal**, que rien
  n'affiche : il disparaissait sans laisser de trace exploitable, ce dont le
  `CLAUDE.md` fait son piège n°4. `CatalogScan` retient désormais le chemin et
  la raison.

### Interne

- La règle de recherche des `lab.yaml` est extraite dans le scanner et exposée
  par `compter_fichiers_labs()`. Un premier jet la dupliquait dans `doctor`, et
  les deux définitions divergeaient dès l'écriture : le comptage ignorait les
  `tp-*/` que le scanner accepte pour les anciens dépôts.

## [0.1.57] - 2026-08-23

### Corrigé

- **Un exécutable absent rendait une trace Python.** La CLI convertit
  soigneusement `CommandError`, `DomainNotFound`, `UnsupportedSchemaVersion` et
  les erreurs du contrat en message traduit suivi d'un code de sortie ;
  `FileNotFoundError`, lui, traversait tout et remontait à l'interpréteur. Or
  une trace dit « l'outil est cassé » alors qu'il manque le plus souvent un
  binaire que l'apprenant peut poser lui-même. Le filet est posé dans
  `_I18nGroup.invoke`, au même endroit que celui du Ctrl-C : c'est le seul point
  qui couvre les vingt-quatre commandes sans en instrumenter aucune. Un nom sans
  séparateur a été cherché dans le `PATH`, donc c'est un exécutable et le code
  rendu est **127**, celui que le shell emploie pour « command not found » ; un
  chemin désigne un fichier et rend **2**.

### Changé

- **`click` n'est plus une dépendance déclarée.** Son dernier importeur a
  disparu en 0.1.50 avec la migration de la complétion vers `autocompletion=`,
  et typer 0.27 ne dépend plus de click : il le vendore. La dépendance était
  donc installée pour rien. Vérifié après retrait : `click` disparaît
  complètement de `uv.lock`, les 544 tests et les 16 tests de bout en bout
  passent, et la roue installée pilote toujours les trois catalogues.

## [0.1.56] - 2026-08-21

### Corrigé

- **Les snapshots ne fonctionnaient sur aucune VM dsoxlab, et l'échec était
  muet.** Le template Terraform packagé démarre ses machines en UEFI — les
  images cloud modernes n'embarquent plus de bootloader BIOS — et libvirt refuse
  les snapshots **internes** sur un firmware pflash : `internal snapshots of a
  VM with pflash based firmware are not supported`. C'est exactement ce que
  demandait `infra/snapshot/kvm.py`. Il prend désormais un snapshot **externe**
  (`--disk-only --atomic`), vérifié sur un domaine UEFI réel.

- **Le chemin du fichier de recouvrement est passé, plus deviné.** Sur un disque
  `type='volume'` — la forme que produit le template — libvirt refuse de le
  déduire lui-même (`cannot generate external snapshot name for disk 'vda'
  without source`), donc un snapshot externe naïf échouait tout autant que
  l'interne. `create` passe maintenant un `--diskspec` par disque inscriptible.
  Le cdrom cloud-init en est exclu : lui en donner un ferait échouer tout le
  snapshot.

- **`run` échoue désormais quand un point de reprise exigé ne peut pas être
  pris.** C'est le changement qui compte le plus. `runtimes/vm.py` avalait
  l'échec dans un `logger.warning`, et aucun `logging.basicConfig` n'existe dans
  ce paquet : un lab qui déclare `snapshot_required: true` démarrait **sans le
  filet qu'il réclame**, `run` sortait en 0, et l'apprenant l'apprenait au
  moment d'en avoir besoin. C'est ce silence qui a laissé la fonctionnalité
  cassée sans que personne ne le voie. Un lab qui se passe de filet déclare
  toujours `snapshot_required: false`, qui est le défaut et ce que déclarent
  aujourd'hui tous les labs de tous les catalogues.

- **Le retour arrière est une autre opération, et il est écrit comme telle.**
  libvirt refuse `snapshot-revert` sur un snapshot externe (`Invalid target
  domain state 'disk-snapshot'`). `revert` arrête désormais la machine, vide le
  fichier de recouvrement par l'API de stockage de libvirt et la redémarre : le
  chemin du disque ne change pas, donc le XML du domaine n'est jamais réécrit et
  le point de reprise reste utilisable. Il refuse d'agir quand le point de
  reprise n'est plus la couche du dessus, plutôt que de jeter le mauvais fichier.

- **`clean` et `destroy` connaissent le fichier de recouvrement.** Un snapshot
  externe laisse un artefact dont Terraform n'a jamais entendu parler : il n'est
  dans aucun state, et le volume qu'il recouvre est supprimé sous lui. `clean`
  retire le point de reprise par `snapshot-delete`, qui refusionne le
  recouvrement et efface le fichier ; `destroy` purge tous les points de reprise
  **avant** que Terraform ne passe, parce qu'après l'`undefine` la métadonnée a
  disparu avec le domaine et le fichier devient introuvable. Même famille de
  défaut que les domaines orphelins de #107.

### Ajouté

- **`reset` donne enfin un effet observable à `snapshot_required`.** Sur un lab
  qui le déclare, `dsoxlab reset` ramène la machine à son point de reprise au
  lieu de rejouer le `cleanup.yaml`, puis rejoue le `setup.yaml`. Les labs qui
  ne le déclarent pas gardent exactement le comportement précédent.

- **Le contrat dit ce qu'un point de reprise capture, et ce qu'il ne capture
  pas.** `docs/contract-v1.fr.md`, sa version anglaise et
  `schemas/lab.schema.json` posent la frontière disque/mémoire : le retour
  arrière redémarre depuis un état disque cohérent, il ne replace pas la machine
  dans la seconde d'avant. Un lab dont l'exercice repose sur un processus en
  cours doit le relancer.
## [0.1.55] - 2026-08-21

### Ajouté

- **Un verrou d'écriture par dépôt, pour que deux terminaux cessent de s'écraser
  l'un l'autre.** Rien n'empêchait deux `dsoxlab` de travailler en même temps sur
  le même dépôt, et deux terminaux ouverts, c'est le cas normal chez un
  apprenant. L'état partagé est éparpillé : `.dsoxlab-context.json` est réécrit
  *en entier* à chaque changement, donc la seconde écriture perdait la première
  sans laisser de trace ; le state Terraform sous
  `~/.local/state/dsoxlab/<repo-id>/` ; l'inventaire et le fragment `ssh_config`
  régénérés ; les conteneurs de `runtime.services`, nommés par dépôt donc
  partagés. Seule la base SQLite de progression était protégée, par SQLite.
  `provision`, `destroy`, `run`, `check`, `submit`, `reset`, `clean` et `use`
  prennent désormais le verrou. Une seconde invocation est refusée avec le code
  de sortie **7** et un message traduit qui nomme la commande détentrice, son PID
  et depuis combien de temps elle tourne.

- **Les commandes de lecture ne sont jamais bloquées.** `list-labs`, `show`,
  `scores`, `progress`, `next`, `status`, `doctor`, `course`, `challenge`,
  `hint`, `guide`, `validate-structure` et `support` ne prennent pas le verrou :
  consulter son catalogue pendant qu'un `provision` tourne dans un autre terminal
  est un usage normal, pas un conflit.

- **Un verrou périmé n'est jamais un fichier à supprimer à la main.** Le verrou
  est un `flock` posé sur un fichier du répertoire d'état du dépôt, juste à côté
  du state Terraform qu'il protège. Le noyau le relâche quand le descripteur se
  ferme : un détenteur tué au `SIGKILL`, ou perdu dans un redémarrage, ne laisse
  rien à nettoyer, et il n'y a donc aucun verrou à « reprendre », ce qui est la
  vraie difficulté de tout verrou par fichier sentinelle. Le fichier, lui,
  survit ; il est tronqué au relâchement pour ne jamais accuser une commande
  terminée depuis longtemps, et il n'est jamais supprimé, parce que l'effacer est
  la course classique où un processus retire l'inode sous les pieds d'un autre.
  Sur un système de fichiers incapable de verrouiller (`ENOLCK`), la commande
  travaille sans filet avec un avertissement au journal, plutôt que de refuser de
  démarrer.

- **`run` rend le verrou avant d'ouvrir la session.** Un verrou tenu « pour toute
  la commande » couvrirait le sous-shell interactif, et c'est précisément là que
  l'apprenant tape `dsoxlab check`, qui serait alors refusé par sa propre
  session.

### Corrigé

- **Un Ctrl-C ne rend plus l'invite sans un mot.** Rien n'attrapait
  `KeyboardInterrupt` en dehors du pager. Typer, tout en bas, en fait un
  `Exit(130)` : le code de retour était donc déjà juste, et c'est précisément ce
  qui rendait le défaut invisible. L'apprenant retrouvait son invite sans savoir
  ce qui venait d'être interrompu, ce qui restait debout, ni quoi rejouer. Chaque
  étape longue nomme désormais ces trois choses, et sort toujours en **130**
  (`128 + SIGINT`, ce que le shell rend lui-même). Une étape mentait aussi sur le
  code, et c'est l'entrée suivante.

- **Terraform est arrêté en deux temps au lieu d'être pris de vitesse.** Il
  tourne maintenant dans sa propre session (`start_new_session`). Dans le groupe
  de processus partagé, le Ctrl-C du terminal atteignait dsoxlab et Terraform au
  même instant : impossible de savoir si le fils avait déjà reçu son signal, et
  lui en envoyer un risquait de compter pour le *second*, celui qui fait sortir
  Terraform sans finir la ressource en cours. Isolé, le fils ne reçoit que ce que
  dsoxlab lui envoie : le premier Ctrl-C lui transmet `SIGINT` et continue de
  drainer sa sortie pour qu'il puisse finir et enregistrer son état, le second
  escalade en `SIGTERM` puis `SIGKILL`. Avant, un second Ctrl-C sortait du
  `finally: proc.wait()` et laissait Terraform continuer, orphelin, à créer des
  machines que plus personne ne suivait.

- **Un playbook interrompu n'est plus rendu comme un playbook en échec.** C'est
  le seul chemin où le code de sortie lui-même était faux. `ansible-runner` pose
  ses propres handlers `SIGINT` et `SIGTERM` dès qu'on ne lui fournit pas de
  `cancel_callback`, et ne les restaure jamais. Deux conséquences, mesurées
  toutes les deux sur la version installée : pendant un playbook, un Ctrl-C ne
  levait aucun `KeyboardInterrupt`, l'exécution était annulée, et l'appelant
  rendait le `rc=254, status=canceled` obtenu en « setup.yaml a échoué » avec le
  code **2** ; et après le playbook, `SIGINT` *et* `SIGTERM` restaient détournés
  pour le reste du processus, si bien qu'un `kill` sur dsoxlab n'avait plus
  d'effet. dsoxlab fournit désormais le callback et restaure les handlers qu'il a
  trouvés.

- **Un `check` interrompu ne laisse plus pytest tourner derrière lui.** La boucle
  de lecture était abandonnée sans attendre le fils : pytest continuait de
  piloter la machine du lab pendant que l'apprenant croyait tout avoir arrêté, et
  le processus restait zombie jusqu'à la sortie de la CLI. Il est maintenant tué,
  et rien n'est enregistré, parce qu'une validation interrompue ne doit coûter
  aucun point.

- **Les autres points d'interruption sont nommés eux aussi** : le téléchargement
  du provider Terraform, l'attente SSH après un provision (l'infrastructure, elle,
  est en place, et rejouer `provision` est idempotent), les services
  conteneurisés (l'un d'eux peut être debout sans avoir été initialisé, ce que le
  prochain `run` répare en rejouant `post_start`) et la session interactive du
  lab. Un Ctrl-C ailleurs est rattrapé par un filet de dernier recours posé sur
  le groupe Click, dernier endroit capable de nommer l'interruption avant que
  typer n'en fasse une sortie 130 muette.
## [0.1.54] - 2026-08-21

### Corrigé

- **Une `section` déclarée n'est plus écrasée par le moteur.** La valeur par
  défaut de `LabDefinition.section` était `linux`, et le scanner se servait de
  cette même chaîne comme sentinelle « rien de déclaré ». Les deux étaient donc
  indiscernables : un lab qui écrivait `section: linux` dans un catalogue d'une
  autre catégorie voyait sa déclaration remplacée en silence. La sentinelle est
  désormais `None`, l'inférence du mode legacy rend `None` au lieu d'inventer
  une valeur, et plus aucun nom de domaine ne vit dans le code qui lit un
  catalogue. Aucun catalogue existant ne change de comportement — aucun des 284
  labs ne déclare `section: linux` — mais le premier auteur tiers y serait
  tombé.

- **Les couleurs de section et de niveau ne viennent plus d'une liste de
  domaines.** `reporting/console.py` associait `linux`, `ansible`, `terraform`,
  `kubernetes`, `rhcsa`… à des couleurs, ce qui est de la connaissance de
  domaine dans le moteur, avec une seule conséquence visible : les catalogues
  de cette liste étaient colorés, tous les autres uniformément blancs. La
  couleur est maintenant tirée du nom lui-même (`crc32` sur une palette fixe) :
  stable d'une exécution à l'autre, et disponible pour tout catalogue.

- **`exam_passing_score` pose enfin un seuil de réussite.** Onze labs d'examen
  en déclaraient un — les examens blancs RHCSA et LFCS, et neuf drills — avec
  un commentaire expliquant le seuil retenu, et personne ne le lisait : un
  apprenant qui rendait 40/100 sur un mock RHCSA ne lisait nulle part qu'il
  avait échoué. Le champ fait désormais partie du contrat, en **pourcentage**
  du barème du lab, et il est rendu par `dsoxlab show` avant l'examen, par
  `dsoxlab submit` sous forme de verdict reçu/recalé, et par `dsoxlab scores`
  dans une colonne Verdict. La comparaison est exacte : 69,5 % du barème échoue
  à une barre de 70 %.

- **`meta.yml` gagne le mécanisme de traduction que le reste du contrat avait
  déjà.** Les titres de section sont les noms de blocs qu'affiche `dsoxlab
  progress`, et les trois catalogues les écrivent en français : une session
  anglaise lisait donc du français. Un catalogue avait tenté `title_en:` /
  `description_en:`, que personne ne lisait. Un `meta.<langue>.yml` posé à côté
  du `meta.yml` surcharge désormais `repo.title`, `repo.description`,
  `sections[].title` et `sections[].description` — même convention par fichier
  que `lab.<langue>.yaml`, avec les sections appariées par `id` plutôt que par
  position. Le catalogue de démonstration packagé en fournit un.

### Ajouté

- **`validate-structure` signale toute clé que personne ne lit.** Le vrai
  correctif des quatre clés mortes n'est pas de solder ces quatre-là : c'est
  qu'une cinquième ne puisse plus s'installer en silence. Le contrôle relit
  `meta.yml`, `lab.yaml` et leurs fichiers de traduction depuis le disque,
  descend dans chaque bloc que le contrat décrit, et nomme chaque clé inconnue
  avec la clé la plus proche que le moteur lit vraiment. Il laisse tranquilles
  les mappings libres — `runtime.targets[].roles`, `runtime.services[].env`,
  `infra.providers.<provider>` — dont les clés appartiennent au catalogue. Les
  clés connues sont tenues contre les schémas JSON publiés par un test, pour
  que les deux ne puissent pas diverger.

  Le **parseur, lui, reste tolérant** : ignorer une clé inconnue est une
  garantie de la v1, et c'est ce qui permet à un outil v1 de survivre à un
  catalogue v1.1. Ceci est un lint, pas le parseur.

  Conséquence sur les catalogues en l'état : `linux-dsoxlab-training` signale
  `runtime.hosts_required` (un lab, redondant avec les deux targets qu'il
  déclare déjà), et `terraform-training` signale `sections[].title_en` et
  `sections[].description_en` (à déplacer dans un `meta.fr.yml`).
  `ansible-training` est propre.

## [0.1.53] - 2026-08-21

### Modifié

- **Le garde-fou i18n analyse désormais tout le paquet, plus le seul `cli.py`.**
  La règle « tout texte affiché passe par `_()` » était déjà tenue par un test,
  ce qui est la bonne façon de la tenir. Mais ce test n'analysait qu'un fichier.
  Tout ce que lèvent `infra/`, `runtimes/`, `services/` et `templates/` lui
  échappait, c'est-à-dire exactement les messages qu'un apprenant lit quand
  quelque chose casse : une session entièrement anglaise répondait `terraform est
  absent du PATH`. La règle avait un gardien qui ne regardait qu'une porte sur
  cinq.

- **Le critère est écrit dans le test, parce que c'est là qu'est la difficulté.**
  Un garde-fou trop laxiste ne garde rien ; trop strict, il se fait désactiver au
  premier faux positif. Un littéral est un texte d'interface quand deux choses
  sont vraies ensemble. Il atteint un humain, par l'un de quatre puits : `help=`
  et `description=`, les helpers `error`/`info`/`warn`/`success`, le texte d'un
  `raise` (cette CLI rend ses erreurs par `error(str(exc))`, donc le message
  d'une exception **est** de l'interface), et les verbes de sortie
  `.print()`/`.echo()`/`.secho()`. Et il s'écrit comme une phrase, définie ici
  comme au moins deux mots séparés par une espace, un fragment sans espace
  comptant pour un seul mot. Cette dernière clause est tout le réglage : elle
  laisse passer `meta.yml`, `challenge/tests`, `lab_starting` et la mise en forme
  pure telle que `f"  ✔ {fqdn} ({ip})"`, tout en attrapant ce qui est écrit pour
  être lu.

- **Deux exclusions sont décidées à voix haute, chacune tenue par son test.**
  `logger.*` n'est pas un puits d'interface : le journal est un artefact de
  diagnostic, lu à côté d'une trace Python, et le traduire rendrait deux rapports
  de bug incomparables selon la langue de qui les produit. `models/` reste hors
  périmètre parce que le bon patron y vit déjà, `UnsupportedSchemaVersion` et
  `ProviderUnresolved` portant des données pendant que la CLI compose la phrase
  traduite ; convertir à ce patron les 24 `ValueError` du contrat est une
  refonte, pas un correctif d'i18n.

### Corrigé

- **43 phrases françaises en dur ne fuient plus dans une session anglaise.**
  Elles sont la conséquence du garde-fou étendu, pas sa raison d'être : il les a
  fait apparaître d'un coup, dans `infra/credentials.py` (13), `runtimes/vm.py`
  (8), `runtimes/services.py` (5), `infra/inventory.py` (4),
  `infra/terraform.py` (4), `infra/ansible.py` (3), `runtimes/manager.py` (2),
  `templates/__init__.py` (2), `infra/snapshot/__init__.py` (1) et
  `services/lab_service.py` (1). Les 38 clés nouvelles ont été ajoutées
  simultanément dans `i18n/strings/en.py` et `i18n/strings/fr.py`, et
  `dsoxlab provision` sans terraform sur le PATH répond maintenant dans la langue
  de la session, ce qui était le symptôme à l'origine de l'issue.
## [0.1.52] - 2026-08-21

### Corrigé

- **Les disques des VM se déclarent par chemin, et AppArmor cesse de tous les
  refuser.** Le template KVM empaqueté demandait un disque déclaré par référence
  de pool (`<disk type='volume'>`), or `virt-aa-helper`, qui fabrique le profil
  AppArmor du domaine à partir de ce XML, ne sait pas résoudre cette forme en
  chemin de fichier. Aucun disque n'entrait donc dans le profil, et qemu se
  voyait tout refuser : `Could not open '…qcow2': Permission denied`, sur une
  machine où `dsoxlab doctor` venait de passer au vert. Cela ressemblait à un
  problème de propriétaire sans en être un : mettre tous les volumes en
  `libvirt-qemu:kvm` n'y changeait rien.

  Les trois disques (système, seed cloud-init et disque additionnel optionnel)
  pointent désormais le chemin absolu de leur volume. Les volumes restent créés
  dans le pool : seule la façon dont le domaine les désigne change. libvirt
  accorde alors les droits de lui-même, droit de verrouillage `k` compris, celui
  sans lequel l'échec devient `Failed to lock byte 100`.

  Rien n'est modifié sur la machine de l'apprenant, et c'est tout l'intérêt.
  Poser `security_driver = "none"` dans `/etc/libvirt/qemu.conf` fait bien
  démarrer le domaine, et éteint du même geste le confinement de toutes les VM
  de la machine : un contre-exemple enseigné, dans un outil DevSecOps, à des
  gens qui apprennent le métier. Une règle AppArmor locale aurait marché aussi,
  mais c'est une modification du système dont ce correctif n'a pas besoin.

  Mesuré sur Ubuntu 24.04.2 avec dmacvicar/libvirt 0.9.8 et le `virt-aa-helper`
  de la distribution, sur deux domaines créés côte à côte à partir du même
  volume : `type='volume'` produit un profil ne portant aucune règle de disque,
  `type='file'` produit `"/var/lib/…/x.qcow2" rwk,`. Ce qui reste à confirmer
  sur une machine réellement neuve, c'est le bout du parcours : les profils
  libvirt de la machine de développement sont en mode `complain`, où toute VM
  démarre dans les deux cas.

- **`doctor` ne confond plus un pool de stockage arrêté avec un pool absent.**
  `virsh pool-list --name` ne liste que les pools **actifs**. Un pool défini
  mais jamais démarré n'y figurait pas, le contrôle le déclarait introuvable, et
  proposait un `pool-define-as` qui échoue aussitôt sur « pool already exists ».
  Terraform, lui, sort sur un message entièrement différent (`storage pool 'x'
  is not active`), et le geste qui débloque est `pool-start`. Les deux états
  sont désormais distingués, chacun avec sa remédiation.

- **La remédiation nomme le pool que le dépôt vise réellement.** L'explication
  « Pool Not Found » affichée après un `provision` en échec codait `default` en
  dur. Un catalogue pointant son propre pool via
  `infra.providers.kvm.storage_pool` se voyait proposer la création d'un pool
  que personne n'utilise. Le nom est maintenant lu dans le message que libvirt a
  produit.

### Ajouté

- **`infra.providers.kvm.storage_pool` entre dans le contrat documenté.** Le
  réglage est lisible par le template empaqueté depuis la 0.1.42 et n'était
  décrit nulle part : un formateur dont le pool ne s'appelle pas `default`
  n'avait aucun moyen de l'apprendre autrement qu'en lisant le Terraform
  empaqueté. `docs/contract-v1.md`, sa version française et
  `schemas/meta.schema.json` le portent désormais, avec `default` pour valeur
  par défaut. Pas de montée de version du contrat : un champ optionnel muni
  d'un défaut ne casse aucun catalogue.

- **Un test lit le template et exige que le contrat en parle.** Il parcourt les
  appels `lookup(var.provider_config, …)` du `main.tf` KVM et tombe sur toute
  clé pilotable depuis `meta.yml` mais absente des trois documents, ou dont le
  défaut a dérivé. Le contrôle bidirectionnel de `tests/test_json_schemas.py` ne
  peut pas voir ces clés, qui ne passent jamais par `models/repo.py` : c'est la
  porte qui manquait.

## [0.1.51] - 2026-08-21

### Ajouté

- **Une suite de bout en bout « boîte noire », `tests_e2e/`.** Les 421 tests
  unitaires parlent tous au moteur depuis l'intérieur. Ils prouvent que les
  fonctions font ce qu'elles disent ; ils ne prouvent jamais que *le programme
  installé* se comporte comme promis. Un point d'entrée cassé, un fichier de
  données absent de la roue, un `console_scripts` mal déclaré : rien de cela
  n'était détectable par une suite verte. La nouvelle suite construit la roue,
  l'installe dans un environnement virtuel jetable et pilote le binaire
  `dsoxlab` par sous-processus, en n'assérant que sur le code de retour, la
  sortie standard, la sortie d'erreur et les fichiers laissés sur le disque.

- **Le parcours de l'inconnu est rejoué en entier :** `demo`, `list-labs`,
  `run`, `check`, `scores`, d'une machine nue jusqu'au 100/100 sur le lab de
  démonstration packagé. Il n'exige ni KVM, ni Incus, ni Docker, ni le moindre
  privilège (le catalogue de démonstration est un lab `shell`), et le job dure
  environ six secondes, construction de la roue comprise.

- **La suite peut échouer, et c'est tout son intérêt.** Le même lab vaut 100/100
  une fois résolu et 0/100 avec un code de retour non nul quand il ne l'est
  pas ; prendre son unique indice fait tomber le même travail parfait à 80/100.
  Exclure le catalogue de démonstration de la roue fait rougir les contrôles
  d'empaquetage et entraîne tout le parcours avec eux : c'est la preuve que le
  sujet du test est bien la distribution, et pas l'arborescence source.

- **La règle « aucun import de `dsoxlab` » est tenue par un test,** sur le
  modèle de `tests/test_i18n_coverage.py`. Trois portes, parce qu'une seule se
  contourne : une analyse syntaxique de chaque fichier de la suite pour
  `import dsoxlab`, une deuxième pour la voie dynamique
  (`importlib.import_module("dsoxlab")`), et une troisième qui lit `sys.modules`
  à l'exécution, qu'aucune astuce syntaxique n'esquive.

### Modifié

- **La CI gagne un job à elle, `End-to-end (black box, installed wheel)`.** Il
  est séparé de la matrice unitaire à dessein : une E2E rouge et une suite
  unitaire rouge ne disent pas la même chose, et seule la première annonce que
  l'outil empaqueté est cassé. `tests_e2e/` porte sa propre `pytest.ini`, donc
  `uv run pytest` continue de ne jouer que la suite unitaire et la porte de
  contribution garde la durée qu'on lui a mesurée.

- L'étape ruff lint désormais aussi `tests_e2e`, ce qui l'aligne sur le hook
  pre-commit, qui a toujours tourné sur tous les fichiers Python de l'arbre.

## [0.1.50] - 2026-08-20

### Modifié

- **La complétion shell ne repose plus sur `shell_complete`, que typer
  déprécie.** Les dix arguments `lab_id` (`show`, `run`, `course`, `challenge`,
  `guide`, `hint`, `check`, `submit`, `reset`, `clean`) passaient par le
  `shell_complete=` de click, un mot-clé dont typer 0.27 avertit et dont il
  annonce la suppression. Le passage à `autocompletion=` n'est pas un
  renommage : la fonction ne reçoit plus les trois positionnels
  `(ctx, param, incomplete)`, mais les paramètres que typer déduit de ses
  annotations, et elle rend désormais des couples `(valeur, aide)` au lieu des
  `CompletionItem` de click, que typer refuse. L'aide affichée à côté de chaque
  proposition, le titre du lab, est préservée : zsh affiche toujours
  `identifiant-du-lab -- Titre du lab`.

- **La suite n'émet plus un seul `DeprecationWarning` de typer,** contre 490 par
  exécution. Une dépréciation noyée dans 490 autres n'est plus un signal, et la
  prochaine, celle qui comptera vraiment, serait arrivée dans ce bruit.

### Ajouté

- **La complétion est enfin couverte par des tests qui la déclenchent
  vraiment.** Rien n'exerçait le mécanisme : la complétion pouvait cesser de
  proposer quoi que ce soit sans que ruff, mypy ni la suite ne bronchent, et la
  panne ne serait apparue que sous la forme d'un `Tab` sans effet chez
  l'apprenant. Les nouveaux tests demandent une complétion à la CLI comme le
  fait le shell, par la variable d'environnement que pose le script zsh généré,
  puis lisent ce qui revient : les propositions, le filtrage par le préfixe
  saisi, l'aide affichée, les dix commandes une par une, et les cas dégradés
  (hors d'un dépôt de labs, avec un `meta.yml` cassé, avec un contrat trop
  récent pour être lu) où le `except` aveugle doit rendre une liste vide plutôt
  qu'une trace Python dans le shell.

## [0.1.49] - 2026-08-20

### Corrigé

- **`doctor` déclarait Terraform vert sans lire son code retour.** Le contrôle
  lançait `terraform version` et ne regardait que la sortie standard : un
  binaire présent mais inutilisable — cache de plugins corrompu, wrapper cassé,
  architecture incompatible — sort en code non nul sans rien écrire sur stdout,
  et le contrôle affichait alors « ok » en se déclarant vert. `provision`
  échouait ensuite sur une machine que `doctor` venait de dire prête, ce qui est
  la pire chose qu'un diagnostic puisse faire. Le code retour est désormais lu,
  et l'échec porte la dernière ligne de l'erreur de Terraform.

- **Un bail DHCP refusé par libvirt disparaissait en silence.** `provision`
  ajoute au mieux les baux statiques manquants d'un réseau KVM existant ; un
  `virsh net-update` en échec ne journalisait rien du tout. Sans ce bail, l'hôte
  n'obtient jamais son adresse, et la panne ne ressortait que bien plus tard en
  « hôte injoignable » sans jamais nommer sa cause. Best-effort veut dire
  « on continue », pas « on se tait » : le refus est désormais journalisé en
  avertissement.

### Modifié

- **Le jeu de règles de lint est déclaré en entier dans `pyproject.toml`.** La
  configuration s'appuyait sur la sélection par défaut de ruff et se contentait
  de l'étendre avec `S`. Ruff 0.16 a élargi ce défaut : la même commande, sur le
  même code, est passée de 0 à 123 erreurs, dont aucune ne relevait de `E`, `F`
  ou `S` — un changement de périmètre que personne n'avait décidé, arrivé avec
  une montée de version. `select` remplace maintenant le défaut au lieu de
  l'étendre (`F`, `E`, `W`, `I`, `UP`, `B`, `S`, `SIM`, `ISC`, `RUF`, `PLE`,
  `PLW`, `BLE`, `DTZ`, `LOG`, `G`, `PTH`, `PYI`, `EXE`, `FURB`), et chaque
  famille écartée y est nommée avec la mesure qui le justifie.

- **Chaque `subprocess.run` dit désormais s'il contrôle son code retour.** Les
  19 appels qui omettaient `check=` ont été repris un par un : les 19 étaient
  délibérés — une sonde dont le code retour EST la réponse, une boucle
  d'attente, une cascade de réparations qui doit survivre à un échec. Ils le
  disent maintenant, par un `check=False` et un commentaire. L'un d'eux, en
  revanche, ne lisait son code retour nulle part : c'était le défaut Terraform
  ci-dessus.

- **`typer` 0.26.8 → 0.27.1, `pre-commit` 4.6.0 → 4.6.2, `ruff` → 0.16.3.**

## [0.1.48] - 2026-08-20

### Corrigé

- **`virsh` était appelé par `sudo` sans nécessité, ce qui éteignait le
  diagnostic là où il sert le plus.** La configuration que recommande libvirt
  est d'ajouter l'utilisateur au groupe `libvirt` : il joint alors l'URI système
  sans `sudo`, et sans qu'aucun `NOPASSWD` n'existe. Exiger `sudo -n` d'emblée
  faisait donc répondre « hyperviseur non interrogeable » sur une machine où
  `virsh list --all` fonctionne parfaitement, et c'est précisément la machine
  d'un apprenant qui découvre l'outil. dsoxlab détecte désormais le chemin qui
  répond, direct d'abord puis `sudo -n`, et déclare l'URI (`--connect
  qemu:///system`) au lieu de dépendre de celle que la distribution choisit :
  la vraie raison d'être de `sudo` ici était l'URI, pas le privilège.

  Le `-n` est conservé sur le repli, et il n'est pas décoratif : la sortie de
  ces commandes est capturée, donc un prompt de mot de passe n'aurait aucun
  terminal où s'afficher et l'appel resterait pendu jusqu'au délai maximal.

  Le backend de snapshot emprunte maintenant la même porte. Ses quatre appels
  codaient `sudo virsh` en dur **sans** `-n` : ce sont eux qui pendaient.

- **Les lignes par hôte de `status` affichaient deux marqueurs**, `✘   ✘
  hote.lab`, parce que `error()` pose déjà le sien. Ce qui se lit comme un
  défaut de rendu dans la sortie qu'on montre à un apprenant.


- **Un `provision` échoué laissait des machines derrière lui, et `destroy`
  sortait en succès sans les voir.** Quand `libvirt_domain` échoue au démarrage,
  le provider a déjà *défini* le domaine mais ne l'inscrit jamais au state
  Terraform. `terraform destroy` n'avait donc rien à supprimer : la commande
  affichait `✔ Infrastructure détruite.` et sortait en 0 alors que les machines
  étaient toujours debout, et tout `apply` suivant mourait sur `domain already
  exists`. Sur une Ubuntu neuve, où le premier provisionnement échoue pour
  d'autres raisons, aucune commande `dsoxlab` n'en sortait, et la procédure de
  récupération documentée par les catalogues est justement `destroy` puis
  `provision`.

  `provision` regarde désormais l'hyperviseur avant de démarrer : les machines
  déclarées dans le `meta.yml` qui y existent sans être au state sont nommées,
  avec la commande `virsh undefine` exacte qui les retire, et la commande sort
  en 5 au lieu de perdre une minute dans un `apply` qui ne peut pas aboutir.
  `destroy` regarde à nouveau une fois Terraform terminé, et retire ce qu'il a
  laissé, après une confirmation explicite : rien ne prouve à `dsoxlab` qu'un
  domaine homonyme soit bien le sien. `--yes` vaut confirmation. Une
  confirmation refusée, ou un retrait qui échoue, sort en 6 et nomme la commande
  manuelle : une machine encore debout ne doit jamais être annoncée détruite.

  Seuls les `infra.hosts[].name` du dépôt courant sont considérés : une machine
  que ce catalogue ne déclare pas n'est jamais nommée, ni retirée. Un
  `provision` réussi suivi d'un `destroy` se comporte exactement comme avant,
  sans un avertissement de plus. (#107)

- **`status` ne demandait jamais son état à libvirt : deux devinettes au lieu
  d'un diagnostic.** La commande capturait la vraie raison de chaque échec SSH,
  hôte par hôte, puis la jetait pour afficher une phrase qui proposait deux
  causes à la fois (« cloud-init tourne peut-être encore, ou alors
  reprovisionne »). Les deux étaient fausses dans le cas observé : trois hôtes,
  un seul qui répond, deux en `No route to host`. Or `EHOSTUNREACH` et
  `ECONNREFUSED` disent des choses **opposées** sur l'état d'une machine, et
  l'outil les traitait pareil.

  Sur un provider dont l'état des machines est interrogeable, `status` demande
  maintenant cet état et nomme une cause, et un geste, par hôte : un domaine
  inexistant renvoie vers `dsoxlab provision` ; un domaine arrêté renvoie vers
  `virsh start` et cite l'état que libvirt rapporte ; un domaine en marche sans
  bail DHCP renvoie vers `virsh console` ; un domaine en marche qui détient son
  adresse renvoie vers cloud-init et vers l'attente. Là où l'hyperviseur ne peut
  pas être interrogé, la couche SSH distingue déjà « personne ne répond à cette
  adresse » de « quelque chose répond et refuse le port ».

  L'interrogation est paresseuse, rien n'est demandé tant que tous les hôtes
  répondent, et elle n'est jamais fatale. Un provider sans état interrogeable,
  un `virsh` absent, un `sudo` refusé ou un démon éteint retombent sur le
  comportement d'avant **et le disent**, parce que transformer « je n'ai pas pu
  regarder » en « rien n'existe » serait un faux diagnostic. La sortie `--json`
  porte `domain`, `domain_state` et `cause` par hôte, plus un bloc `hypervisor`
  qui distingue une réponse vide d'une absence de réponse. (#122)

### Modifié

- **`virsh` est invoqué en `sudo -n virsh`.** La sortie de ces commandes est
  capturée, donc un prompt de mot de passe n'avait aucun terminal où s'afficher
  et l'appel restait pendu jusqu'au timeout. Avec `-n`, `sudo` refuse
  immédiatement et l'appelant peut le dire. Le backend de snapshot KVM, qui
  utilisait la forme interactive, en bénéficie aussi.

- **`status` joue ses sondes SSH sous `LC_ALL=C`.** La raison de l'échec vient
  de `strerror`, que la bibliothèque C traduit : sans ce verrou, `No route to
  host` s'écrit différemment sur chaque poste et aucun diagnostic ne pourrait le
  reconnaître.

- `incus` et `outscale` sont explicitement hors périmètre de l'interrogation de
  l'hyperviseur, et le code écrit pourquoi : le template incus crée des
  ressources `incus_instance`, que le démon incus gère et que `virsh` ne voit
  pas, et Outscale est un cloud distant sans hyperviseur local. Les deux gardent
  leur comportement d'avant, énoncé plutôt que tacite.

## [0.1.47] - 2026-08-20

### Corrigé

- **Le snapshot KVM visait un domaine qui n'existe pas.** Le template Terraform
  packagé ici nomme chaque domaine libvirt avec le `infra.hosts[].name` du
  `meta.yml`, tel quel, donc un FQDN : `control-node.lab`. Le backend de
  snapshot supposait la convention inverse et coupait le FQDN au premier point,
  si bien que `create`, `revert`, `delete` et `list_` visaient tous
  `control-node`, que libvirt ne connaît pas. Vérifié sur un hyperviseur réel :
  `virsh domstate control-node` répond `failed to get domain`, `virsh domstate
  control-node.lab` répond `running`.

  Le nom du domaine est désormais **résolu contre libvirt** au lieu d'être
  reconstruit de tête : le FQDN d'abord, ce que produit le template, puis le
  nom court en repli pour les infrastructures créées par une version antérieure
  du template. Renommer les domaines côté Terraform aurait recréé toutes les VM
  de tous les catalogues pour un bénéfice nul.

  Un hôte qui ne correspond à aucun domaine lève maintenant une erreur qui
  nomme l'hôte, les noms essayés et les domaines qui existent, au lieu de
  laisser remonter le laconique `error: failed to get domain` de `virsh`.
  `delete` reste tolérant et se contente de journaliser, pour qu'un nettoyage
  n'échoue jamais sur ce qui a déjà disparu.

  Rien n'activait ce chemin : aucun lab d'aucun catalogue ne pose
  `snapshot_required: true`, et le module n'avait aucun test. C'est ainsi que
  les deux conventions ont divergé sans bruit. La docstring du module, qui
  énonçait la convention inverse et a autorisé la divergence, est corrigée, et
  la résolution est désormais couverte par des tests.
## [0.1.46] - 2026-08-20

### Ajouté

- **Le contrat d'entrée est versionné : `schema_version` dans `meta.yml` et
  `lab.yaml`.** Ces deux fichiers sont l'interface publique du moteur, et cette
  interface n'avait jusqu'ici aucun numéro. Un champ qui change de sens ne
  pouvait donc être ni annoncé, ni détecté, ni refusé : il se manifestait par un
  lab qui disparaît du catalogue, sans un mot. C'est le symptôme le plus coûteux
  à diagnostiquer de tout le projet.

  L'absence du champ vaut la **version 1** : aucun des 284 labs des trois
  catalogues existants n'a quoi que ce soit à changer, puisque pas un seul ne le
  déclare aujourd'hui. Un fichier qui annonce une version que ce dsoxlab ne lit
  pas est désormais nommé, et nommé différemment selon le fichier. Un `meta.yml`
  venu du futur **arrête la commande** : il décrit tout le catalogue, le lire de
  travers rendrait tout le reste douteux. Un `lab.yaml` isolé venu du futur est
  **écarté avec un avertissement**, le reste du catalogue continuant d'être
  servi : sans cela, personne ne pourrait jamais publier le premier lab v2 sans
  casser le catalogue de tous les apprenants pas encore à jour.

  La lecture est stricte là où le reste du contrat est tolérant : `"1"`, `1.0` et
  `true` sont refusés plutôt qu'arrondis. Un numéro de version n'est pas une
  mesure, et transformer `1.5` en `1` sans un mot est exactement le silence que
  ce champ existe pour supprimer.

  À ne pas confondre avec la version de la sortie JSON (`reporting/machine.py :
  SCHEMA`), qui versionne ce que dsoxlab **écrit** pour d'autres programmes. Deux
  contrats, deux publics, deux rythmes. On ne les incrémente jamais ensemble.

- **`dsoxlab validate-structure` voit maintenant des fichiers qu'aucun autre
  contrôle ne peut voir.** Il lit `schema_version` directement sur le disque,
  avant la découverte. Tous les autres validators itèrent sur des labs déjà
  chargés : un fichier que le parseur rejette a toujours traversé la validation
  sans un mot. Celui-ci le rapporte, nomme le fichier et donne la valeur.

- **`schemas/lab.schema.json` et `schemas/meta.schema.json`, publiés pour les
  éditeurs et pour la CI.** Une ligne `# yaml-language-server: $schema=…` en tête
  de fichier suffit pour que tout éditeur faisant tourner `yaml-language-server`
  complète les champs et souligne les fautes à la frappe. Un dépôt de catalogue
  peut aussi valider son propre YAML en CI sans installer l'outil Python.

  Un schéma qui ment est pire qu'un schéma absent : il fait autorité à tort. Un
  test confronte donc les deux schémas au parseur **dans les deux sens** : il lit
  `models/lab.py` et `models/repo.py`, en extrait les clés qu'ils vont réellement
  chercher, et exige l'égalité avec les `properties` du schéma. Un champ lu par
  le code et absent du schéma échoue ; un champ inventé dans le schéma et lu
  nulle part échoue aussi ; et un nouveau mapping imbriqué dans le parseur échoue
  tant qu'il n'est pas décrit. Les valeurs énumérées sont confrontées aux
  constantes du code plutôt que recopiées.

- **La v1 du contrat est écrite** : [`docs/contract-v1.fr.md`](docs/contract-v1.fr.md)
  et sa version anglaise listent chaque champ, s'il est obligatoire, les valeurs
  énumérées, ce qui peut être ajouté sans changer de version, ce qui exigerait une
  v2, et le chemin de migration vers cette v2 avec la commande qui aidera.

### Modifié

- `discovery/scanner.py` gagne `scan_catalog()`, qui rend les labs **et** les
  fichiers qu'il a dû écarter. `discover_labs()` garde sa signature et son
  comportement, en enveloppe. Les appelants qui veulent dire à l'utilisateur ce
  qui manque le peuvent désormais ; les autres ne changent pas.

## [0.1.45] - 2026-08-19

### Ajouté

- **`dsoxlab demo` : un premier lab jouable juste après l'installation, sans
  rien cloner ni provisionner.** Entre `uv tool install dsoxlab` et le premier
  lab joué, il y avait une connaissance implicite : savoir que les labs vivent
  dans d'autres dépôts, savoir lesquels, savoir qu'il faut se placer dedans. Qui
  installait l'outil et le lançait là où il se trouvait n'obtenait rien, avec un
  code de retour `0` pour dire que tout allait bien.

  Le catalogue de démonstration porte un seul lab `shell`, et **son sujet est
  dsoxlab lui-même** : la boucle run / course / challenge / hint / check, rien
  d'autre. C'est ce qui l'écarte de l'anti-pattern que le projet s'interdit,
  embarquer des templates de labs pour un domaine technique. Le parcourir prend
  cinq minutes et finit sur 100/100, un chemin qu'un test de bout en bout joue
  en entier.

  Une installation existante n'est jamais écrasée : ce répertoire porte la
  progression et les réponses de l'apprenant, et `--force` est exigé pour
  repartir de zéro.

- **La documentation ne peut plus mentir sur la CLI.** Un test ferme les deux
  sens : toute commande citée dans la documentation existe, et toute commande de
  la CLI est décrite dans `fullhelp`, en anglais comme en français. Il a
  immédiatement trouvé que `provision`, `destroy`, `ssh` et `status` n'étaient
  décrites **nulle part** dans le guide, alors que ce sont les quatre commandes
  d'infrastructure. Elles le sont désormais.

- **Le README ouvre sur l'installation de l'utilisateur, pas du contributeur.**
  Il commençait par `git clone` puis `uv tool install --editable .`, une
  procédure de développement, alors que le paquet est publié sur PyPI et que
  `doctor` recommandait déjà l'installation par PyPI. Qui suivait le README se
  retrouvait avec une copie éditable dont il n'avait aucune raison de vouloir.
  Le parcours devient : installer, jouer un lab, puis choisir un catalogue.

- **La table des commandes est générée depuis la CLI**
  (`scripts/generer-doc.py`), entre marqueurs, dans les deux langues. Écrite à
  la main, elle avait dérivé sans bruit : elle décrivait encore `dsoxlab clean`
  exécutant un `cleanup.sh`, que le zéro-bash interdit, et il y manquait `demo`
  et `support`. Un hook pre-commit et un test refusent une version périmée.

### Corrigé

- **La section Persistance était fausse sur ses trois points.** Elle annonçait
  `~/.local/share/dsoxlab/progress.db`, un `~/.config/dsoxlab/config.yaml` et
  une surcharge par `XDG_CONFIG_HOME`. Vérifié dans le code : la base est
  `<catalogue>/.dsoxlab.db`, aucun fichier de configuration n'est lu nulle part,
  et les variables réellement honorées sont `XDG_DATA_HOME`, `XDG_STATE_HOME` et
  `XDG_CACHE_HOME`. La progression est **par catalogue**, ce que la section dit
  désormais.

- **Cinq commandes manquaient au `fullhelp`**, dont quatre de longue date :
  `provision`, `status`, `ssh`, `destroy`, et la nouvelle `demo`. Une commande
  absente du guide n'existe pas pour qui le lit.

## [0.1.44] - 2026-08-19

### Ajouté

- **`dsoxlab support` : un rapport de diagnostic prêt à coller dans une issue.**
  Répondre à « ça ne marche pas » supposait de redemander la version, le
  système, le provider, le catalogue, l'état de chaque dépendance. Chaque
  aller-retour coûte une journée, et l'outil connaissait déjà toutes les
  réponses. La commande les rassemble d'un bloc en Markdown, avec `--json` pour
  le même contenu en document machine.

  **Anonymisé par défaut, et testé comme tel**, parce que ce rapport est fait
  pour être collé publiquement : le répertoire personnel devient `~`, le nom
  d'utilisateur devient `<user>`, les adresses IPv4 publiques deviennent `<ip>`,
  et le nom de machine n'est tout simplement jamais collecté. Les adresses
  privées restent lisibles délibérément : `10.10.30.11` est une VM de lab, elle
  ne désigne personne hors du réseau local, et la masquer rendrait inexploitable
  tout rapport portant sur l'infrastructure.

  Le gabarit d'issue et les deux `CONTRIBUTING` demandent désormais ce rapport
  plutôt que trois champs à recopier à la main.

- **`--verbose` / `-v`, `--debug`, et un journal persistant.** Onze modules du
  moteur écrivent dans un logger, et aucun de ces messages n'atteignait jamais
  un utilisateur ni un fichier. Le cas le plus coûteux est connu : un `lab.yaml`
  qui lève au parsing est avalé par un `logger.warning` puis un `continue`, donc
  le lab disparaît du catalogue **sans un mot**. C'est le premier symptôme que
  rencontre un auteur de catalogue, et le plus difficile à diagnostiquer.

  Les avertissements sont désormais affichés par défaut, parce qu'un lab disparu
  est une perte réelle de contenu, que l'auteur comme l'apprenant ont besoin de
  voir. `-v` ajoute le niveau informatif, `-vv` (ou `--debug`) le détail complet,
  et `DSOXLAB_LOG` fait de même là où la ligne de commande échappe.

  Le diagnostic part toujours sur la **sortie d'erreur**, jamais sur la sortie
  standard : `--json` reste lisible par un programme même en mode verbeux, ce
  qu'un test épingle.

  Un journal tournant est écrit dans `~/.local/state/dsoxlab/dsoxlab.log` quelle
  que soit l'option, borné à 1 Mo et trois archives. C'est lui qui permet de
  joindre une trace à un rapport de bug *après coup*, au lieu de demander à
  l'utilisateur de reproduire avec la bonne option. Un journal impossible à
  écrire (HOME en lecture seule, disque plein) ne fait jamais échouer la
  commande : c'est un confort, pas une dépendance.

## [0.1.43] - 2026-08-19

Trois défauts qui ne se manifestaient que chez l'utilisateur : une complétion
qui ne complétait pas, un lanceur qui ne lançait pas, et une CLI qui refusait
de démarrer à cause de son propre fichier d'état.

### Corrigé

- **La complétion interrogeait la CLI par une variable qu'elle n'écoute pas.**
  Le script généré employait `_DSOXL_COMPLETE`, quand Click dérive
  `_DSOXLAB_COMPLETE` du nom du programme. dsoxlab répondait donc par sa page
  d'aide, que le shell tentait d'évaluer à chaque tabulation. Le fichier zsh
  était mal nommé par-dessus (`_dsoxl` au lieu de `_dsoxlab`), donc zsh ne le
  chargeait jamais, quel qu'en soit le contenu. La variable est désormais
  dérivée du nom du programme au lieu d'être recopiée : les deux ne peuvent
  plus diverger.

- **Le wrapper généré cassait sur tout chemin contenant une espace.** Il
  écrivait `exec /home/moi/My Tools/dsoxlab "$@"` sans quoting, ce que le shell
  découpait en deux arguments avant de répondre « not found ». Le chemin passe
  maintenant par `shlex.quote`.

- **`dsoxlab install` n'écrase plus le lanceur de `uv tool` ni de `pipx`.** Il
  écrit exactement là où ces outils posent le leur. Le dégât était pire qu'un
  simple écrasement, et il a fallu un test de mutation pour le voir : écrire
  dans un lien symbolique écrit dans **sa cible**, donc dsoxlab remplaçait le
  binaire réel de uv par un script qui s'exécutait lui-même. Le lien survivait,
  `resolve()` ne bougeait pas, et la commande bouclait à l'infini. Quand un
  lanceur mène déjà à ce binaire, on n'y touche plus.

- **Un `.dsoxlab-context.json` malformé n'emporte plus toute la CLI.** Le
  `except` ne couvrait que `JSONDecodeError` et `OSError`, alors que `null`
  levait `TypeError`, `"foo"` levait `ValueError`, une racine non-objet levait
  `AttributeError`, et un fichier d'octets arbitraires levait
  `UnicodeDecodeError`, qui descend de `ValueError` et non d'`OSError`. Treize
  formes malformées sont désormais absorbées en un contexte vide, avec un
  avertissement qui nomme le fichier. Perdre le contexte coûte un
  `dsoxlab use` ; lever coûtait toutes les commandes, y compris celles qui
  n'ont rien à voir avec lui.

## [0.1.42] - 2026-08-19

Un audit joué sur une VM Ubuntu 24.04 neuve a mesuré **six interventions non
documentées** entre un `dsoxlab doctor` vert et le premier lab vm jouable. Un
débutant s'arrête à la première. Cette version comble l'écart : le diagnostic
nomme désormais ce qui manque, avant l'échec plutôt qu'après.

### Corrigé

- **`ansible-core` est déclaré en dépendance, et un lab vm peut enfin
  tourner.** `ansible-runner` ne le tire pas, contrairement à ce qu'affirmait
  le commentaire de ce projet : le tool installé pesait 18 Mo et son `bin/` ne
  contenait ni `ansible` ni `ansible-playbook`. Tout `dsoxlab run` sur un lab
  vm sortait en `rc=127`, code shell de « commande introuvable », que rien ne
  traduisait. Le contrôle aggravait le cas en ne testant que l'import du module
  `ansible_runner` : il répondait OK sur une machine où aucun playbook ne
  pouvait tourner. Il teste maintenant les deux moitiés, et le message nomme
  `ansible-core` au lieu d'envoyer réinstaller ce qui est déjà là.

- **`instructor bootstrap` ne sort plus en 0 après avoir affiché une erreur
  bloquante.** Il annonçait « ✘ terraform absent du PATH » et rendait un
  succès. Un apprenant qui vérifie son code de retour, ou un script
  d'installation, en concluait que tout allait bien, alors que la clé SSH
  venait d'être créée pour une infrastructure que rien ne pourrait
  provisionner.

- **Le message d'erreur de Terraform ne renvoie plus vers une commande qui ne
  l'installe pas.** `provision` disait « Lance : dsoxlab instructor bootstrap »,
  qui se contente à son tour de signaler l'absence. La boucle était fermée. Il
  donne désormais l'URL d'installation.

- **`doctor` n'écrit plus « non requis ici » au-dessus d'un composant qui est
  requis.** Sur un catalogue de 64 labs vm sur 84 dont aucun provider n'est
  encore choisi, les deux hyperviseurs figuraient sous « Informatif, non requis
  ici », suivis de « ces composants ne bloquent rien dans ce dépôt ». Les
  contrôles restent délibérément hors du tableau requis, car `--fix`
  proposerait sinon d'installer kvm **et** incus pour un choix qui n'est pas
  fait : c'est le libellé qui devait dire la vérité.

### Ajouté

- **`doctor` vérifie Terraform, `ansible-playbook`, le pool libvirt et l'outil
  ISO.** Terraform n'était vérifié nulle part, alors que `provision` ne peut
  rien faire sans lui. Le pool libvirt `default` n'existe pas sur une
  installation fraîche, et le provisionnement échouait sur un « Pool Not Found »
  brut. Incus fabrique son CD-ROM `agent:config` sur l'hôte, donc sans
  `genisoimage` aucune instance ne démarre. Chacun n'apparaît que là où il
  s'applique : un catalogue entièrement shell n'en voit aucun, et les contrôles
  de configuration se taisent tant que l'hyperviseur lui-même manque, pour
  qu'une seule cause ne produise pas trois lignes rouges.

- **Le pool de stockage libvirt est configurable** par
  `meta.yml: infra.providers.kvm.storage_pool`. Le nom était écrit en dur à
  quatre endroits du template KVM, donc un dépôt ne pouvait pas viser le sien.

- **Les échecs connus du provisionnement viennent avec leur cause et leur
  correctif.** Terraform est exact mais opaque pour qui découvre l'outil. Trois
  messages ont une cause connue et un remède d'une ligne : AppArmor qui refuse
  les disques des VM, le pool de stockage absent, et une machine laissée par un
  provisionnement précédent en échec. Le cas AppArmor n'est avancé qu'**après**
  l'échec et jamais en prédiction : mesuré sur une machine où AppArmor est
  actif, l'override absent, et huit domaines libvirt en fonctionnement sans
  incident, son absence ne prouve donc rien à elle seule.

## [0.1.41] - 2026-08-19

### Ajouté

- **`DSOXLAB_HOST_READY_TIMEOUT` règle la durée pendant laquelle `provision`
  attend qu'un hôte devienne joignable.** Le délai était figé à 180 s. Sur une
  machine modeste, le démarrage simultané de plusieurs VM sature le processeur :
  un rapport d'usage a mesuré un hôte prêt à 181 s, une seconde après l'abandon
  de l'attente, quand un audit sur 8 vCPU mesurait les mêmes hôtes prêts en
  45 s. Le facteur limitant est le processeur au démarrage parallèle, et le
  matériel de l'apprenant est une propriété de sa machine plutôt que du dépôt de
  labs : c'est donc une variable d'environnement et non une clé du `meta.yml`.
  Une valeur qui n'est pas un nombre positif retombe sur le défaut au lieu de
  faire échouer le provisionnement, et le message d'expiration nomme désormais
  la variable.

- **Les VM AlmaLinux installent l'agent Incus depuis le CD-ROM `agent:config`
  quand l'image ne l'a pas fait elle-même.** La famille RHEL ne fournit pas le
  driver 9p (mesuré : aucune entrée `9p` dans `/proc/filesystems`), qui est la
  voie par laquelle les images cloud récupèrent normalement cet agent. Sans
  agent, Incus ne remonte aucune IP et l'attente expire sur une VM qui a
  pourtant parfaitement démarré.

  Il s'agit d'un filet de sécurité et non de la correction d'un défaut
  reproduit : sur Incus 6.0.0 avec `images:almalinux/10/cloud`, l'agent arrive
  déjà par ce même CD-ROM et le provisionnement réussit sans ce bloc. Il couvre
  les environnements où ce n'est pas le cas, ce qu'un utilisateur a rapporté en
  usage réel.

  Le bloc est sans effet partout ailleurs, et il se décide sur la présence de
  `install.sh` plutôt que sur celle de `/dev/sr0`, car le provider KVM attache
  lui aussi un CD-ROM (son seed NoCloud). Il ne peut pas non plus sortir en
  erreur : un `runcmd` en échec fait finir cloud-init en `status: error`, ce qui
  suffit à bloquer cette même attente.

## [0.1.40] - 2026-08-13

### Corrigé

- **Un conteneur debout n'est réutilisé que s'il correspond à la déclaration.**
  La réutilisation se décidait sur le seul nom du conteneur. Deux labs d'un même
  dépôt déclarant un service sous le même `name` mais avec des `ports`, `env`,
  `image` ou `run_args` différents se partageaient donc le conteneur du premier
  arrivé : le second démarrait sur un service qui n'avait ni ses ports ni ses
  arguments de lancement, échouait là où l'apprenant n'avait rien fait de faux,
  et rien n'en disait la raison. La configuration déclarée est désormais
  estampillée sur le conteneur en label au `docker run`, puis comparée à la
  réutilisation ; un conteneur divergent est remplacé. Un conteneur laissé par
  une version antérieure ne porte pas de label : il est traité comme divergent
  et recréé une fois.

## [0.1.39] - 2026-07-28

### Ajouté

- **Les services d'un dépôt partagent un réseau Docker et se joignent par leur
  nom.** Un lab a souvent besoin de plusieurs conteneurs — une application et sa
  base. Sur le bridge par défaut de Docker, aucune résolution par nom n'existe :
  l'application ne peut joindre sa base que par une IP que personne ne connaît
  d'avance, si bien qu'un tel lab ne pouvait tout simplement pas se déclarer.
  Chaque service rejoint désormais un réseau *user-defined* `dsoxlab-<repo_id>`
  avec son `name` déclaré pour alias, ce qui rend `DATASOURCES_DEFAULT_HOST: db`
  écrivable dans un `lab.yaml`. Le réseau est créé à la demande et survit à une
  création concurrente.

## [0.1.38] - 2026-07-28

### Ajouté

- **`runtime.services[].post_start` : un service peut être initialisé, pas
  seulement démarré.** Un conteneur qui boote est rarement un service
  utilisable : une base veut son schéma, un coffre ses secrets, un registre son
  dépôt. Jusqu'ici cette étape retombait sur un script bash à la racine du lab,
  que l'apprenant devait penser à lancer — d'où des labs qui se skippent quand
  le service manque, ou qui échouent quand il est là mais vide. Les commandes
  déclarées sont jouées dans le conteneur une fois le service prêt, par
  `docker exec` et **sans shell** (ni expansion, ni pipe, ni redirection).
  Chaque entrée s'écrit au choix en chaîne lisible
  (`vault kv put secret/lab k=v`, découpée à la manière du shell, guillemets
  respectés) ou en argv explicite (`["vault", "kv", "put", …]`).

  Elles sont **rejouées à chaque démarrage**, y compris sur un conteneur déjà
  debout : c'est ce qui rend l'état de départ identique d'un lab à l'autre,
  quoi qu'ait laissé l'exercice précédent — elles doivent donc être
  idempotentes, au même titre qu'un `setup.yaml`. Une commande en échec lève
  `ServiceError` et arrête le lab en nommant la commande fautive et la sortie du
  service, plutôt que de laisser les tests enregistrer un 0 silencieux.

  dsoxlab reste agnostique du domaine : il exécute ce que le lab déclare, et ne
  sait ni ce qu'est un secret ni ce qu'est un schéma.

- **`runtime.services[].ready_exec` : le seul signal fiable de disponibilité.**
  `ready_tcp` seul est un **faux positif dès que le port est publié** : Docker
  installe son proxy sur le port de l'hôte **au moment du `run`**, et ce proxy
  accepte les connexions avant que le service écoute. Mesuré, pas supposé — une
  connexion réussit sur un `-p 8299:1234` dont le conteneur n'écoute nulle part.
  La sonde déclarée ici s'exécute **dans** le conteneur (`vault status`,
  `pg_isready`, `redis-cli ping`…) et est réessayée jusqu'à son succès ou
  l'expiration de `ready_timeout`. Elle doit être sans effet : l'initialisation,
  c'est `post_start`, qui attend désormais que la sonde soit satisfaite.

### Corrigé

- **`ready_tcp` documenté pour ce qu'il est : un port de l'HÔTE.** La docstring
  disait « dans le conteneur, côté hôte », ce qui se lit dans les deux sens. La
  nuance devient un piège dès qu'un lab remappe pour cohabiter : avec
  `ports: ["8201:8200"]`, un `ready_tcp: 8200` sonde le 8200 de l'hôte, donc le
  service de quelqu'un d'autre, et le déclare prêt.

## [0.1.37] - 2026-07-28

### Corrigé

- **Un lab `shell` peut enfin livrer un module local.** `ShellRuntime` copiait
  chaque fixture sur son **nom de base** : `modules/stockage/main.tf` atterrissait
  donc en `main.tf` et **écrasait silencieusement** le `main.tf` de la racine.
  Tout lab qui enseigne les modules Terraform était de ce fait impossible à
  construire, et la panne était invisible : le workdir avait l'air correct, seul
  son contenu était faux. Le docstring du module promettait déjà
  `<lab>/fixtures/<fichier>` → `<lab>/<workdir>/<fichier>`, exemples en
  sous-répertoire compris : le code contredisait son propre contrat. Le chemin
  déclaré est désormais **préservé**, et les répertoires intermédiaires sont
  créés. Un chemin absolu ou contenant `..` est refusé avec un avertissement au
  lieu d'être suivi, de sorte qu'une fixture n'écrit jamais hors du workdir.
  Strictement additif : aucune des **136** fixtures déclarées dans les trois
  dépôts de labs ne comporte de `/`, donc aucun lab existant ne change de
  comportement.

## [0.1.36] - 2026-07-27

### Ajouté

- **Les services conteneurisés dont un lab a besoin, démarrés automatiquement.**
  Certains labs `shell` ciblent une API que le poste n'héberge pas (un émulateur
  de cloud, une base de données, un registre). Plutôt qu'un `docker run` manuel
  dans chaque scénario, un lab déclare désormais son service dans
  `runtime.services`, et dsoxlab démarre le conteneur avant `run`/`check` et
  l'arrête à `clean`. Le moteur reste **agnostique du domaine** : il lance
  **l'image que le lab déclare**, sur les ports que le lab déclare, et ne connaît
  rien du produit émulé. Chaque conteneur est nommé `dsoxlab-<repo_id>-<service>`,
  et `ready_tcp` attend que le port accepte une connexion avant de continuer. Le
  moteur est Docker ; s'il est injoignable, `run`/`check` échouent avec un
  message clair plutôt qu'une traceback Docker. Vérifié en live contre
  l'émulateur cloud du dépôt : le service monte sur son port et est retiré au
  `clean`.

Les deux corrections viennent d'une campagne de validation complète sur un
catalogue de 84 labs : un incident, et une fuite que la campagne a rendue
visible.

### Corrigé

- **`instructor bootstrap` pouvait écrire une clé SSH hors de tout dépôt de
  labs.** Elle créait `<root>/ssh/id_ed25519` d'après ce que rendait
  `get_lab_home()`, or cette fonction retombe sur le **répertoire courant**
  quand elle ne trouve aucun `meta.yml`. Lancée depuis le dépôt de l'outil, la
  commande y a donc déposé une clé privée sans passphrase, dans un dépôt public
  qu'aucun `.gitignore` ne couvrait. Le hook `detect-private-key` aurait refusé
  le commit (vérifié : il sort en 1 avec « Private key found »), donc rien n'a
  fui, mais un hook se contourne avec `--no-verify` et une clé de lab n'a rien
  à faire là. La commande refuse désormais quand la cible n'a pas de `meta.yml`,
  et nomme la solution (`--lab-home`). Défense en profondeur : `ssh/`, `*.pem`,
  `id_ed25519` et `id_rsa` sont maintenant gitignorés ici.
- **Un descripteur de fichier fuyait à chaque playbook joué.** `_read_stdout()`
  lisait le fichier d'artefact d'`ansible-runner` sans jamais le refermer.
  Anodin sur un lab, mesurable sur une campagne qui en enchaîne 84. Le
  `ResourceWarning` qui le signalait se noyait dans le bruit des
  `DeprecationWarning` de la bibliothèque elle-même : une fois ce bruit filtré,
  un lab `vm` est passé de 26 warnings à zéro.

## [0.1.34] - 2026-07-27

### Corrigé

- **21 textes affichés ignoraient `DSOXLAB_LANG`.** La règle i18n (« tout
  texte affiché passe par `_()` ») n'existait qu'en prose, et la prose ne
  tient pas : des libellés étaient revenus en dur. Les uns en français, donc
  affichés en français sous `DSOXLAB_LANG=en` (aides de
  `dsoxlab use --provider`, `provision --host`, `destroy --host`,
  `Host inconnu`, `Cible Terraform`, tout le pré-vol sudo de `doctor --fix`) ;
  les autres en anglais, donc affichés en anglais sous `DSOXLAB_LANG=fr`
  (tous les libellés de barres de progression : tâches Ansible,
  `Terraform init complete`, `Nothing to do`, progression des tests). Ils
  vivent désormais dans les catalogues EN et FR, qui atteignent 315 clés
  appariées.
- **`destroy --host` avait perdu son avertissement le plus utile** pendant
  l'extraction, il est rétabli : Terraform détruit aussi tout ce qui dépend de
  la cible, donc l'option n'isole **pas** une VM des autres.

### Ajouté

- **Un garde-fou qui maintient la règle vraie**
  (`tests/test_i18n_coverage.py`) : il analyse `cli.py` et rejette tout
  `help=`/`description=` qui n'est pas un appel `_()`, ainsi que toute phrase
  en dur passée à `error/info/warn/success`. La mise en forme pure autour de
  valeurs déjà traduites (`f"  ✔ {fqdn} ({ip})"`) reste acceptée. Le garde-fou
  a été passé sur le commit précédent, où il signale les 21 violations : on
  sait donc qu'il échoue quand il le doit.

## [0.1.33] - 2026-07-27

Les deux changements viennent du retour d'un apprenant sur sa première
session : la première commande lancée affichait trois erreurs, et le premier
cours lu défilait hors de l'écran.

### Corrigé

- **`doctor` annonçait `pytest` introuvable alors que `check` le lançait très
  bien.** Le diagnostic cherchait un binaire `pytest` dans le `PATH`, quand
  `check` passe par `resolve_pytest_cmd()`, qui commence par
  `sys.executable -m pytest`, c'est-à-dire l'environnement de l'outil, où
  pytest et pytest-testinfra sont des dépendances déclarées. Le tableau
  affichait donc du rouge sur un composant qui fonctionnait, et la
  remédiation proposée (`uv add --dev pytest pytest-testinfra`) faisait
  installer à l'apprenant ce qu'il possédait déjà. Les deux chemins partagent
  désormais la même résolution, et un pytest introuvable renvoie à la
  réinstallation de l'outil.

### Modifié

- **`doctor` sépare ce qui bloque ce dépôt de ce qui l'informe.** Un dépôt
  dont tous les labs sont `shell` n'a besoin d'aucun hyperviseur ; un dépôt
  qui a choisi `kvm` n'a pas besoin d'incus. Ces contrôles passent dans un
  tableau *Informatif* qui n'affiche jamais de rouge et que `--fix` ne touche
  pas, avec une ligne qui dit pourquoi ils ne sont pas requis ici. Sur un
  catalogue comme `terraform-training` (aucun bloc `infra:`, tous les labs
  `shell`), le diagnostic est désormais entièrement vert.
- **Un provider non résolu est présenté comme une décision, pas comme une
  panne.** Quand le `meta.yml` déclare plusieurs candidats et qu'aucun n'est
  actif, le contrôle reste bloquant — `provision` ne peut pas tourner — mais
  porte un statut *à choisir* et nomme la commande à taper. Il reste un
  conseil, jamais un correctif automatique : choisir le provider à la place
  de l'apprenant déciderait en silence de la façon dont ses labs tournent.
- **`--fix` annonce ses limites.** Il n'a jamais traité que les composants
  pour lesquels il détient une commande ; la sortie le dit maintenant, et
  renvoie à la remédiation manuelle quand rien n'est automatisable.

### Ajouté

- **Les affichages longs passent par le pager.** `course` déverse un README
  entier quand le lab ne déclare pas de `course.yaml`, soit jusqu'à un
  millier de lignes dans les catalogues existants, que le scrollback d'un
  terminal local ne permet pas de remonter. `course` et `challenge` paginent
  désormais leur sortie dès qu'elle dépasse la hauteur de l'écran. Jamais
  dans un tube ni une redirection, pour qu'une sortie scriptée reste du texte
  brut, et jamais pour ce qui tient déjà à l'écran. `$DSOXLAB_PAGER` (puis
  `$PAGER`) choisit le pager, `less -R` par défaut ; `--no-pager` rétablit le
  déversement brut.

## [0.1.32] - 2026-07-23

### Ajouté

- **Support de Debian 12 (bookworm) sur les trois providers.** La distro
  `debian12` était déjà associée à une image (URL qcow2 pour kvm, alias
  `images:debian/12/cloud` pour incus) et à un template cloud-init `debian`,
  mais ce template n'existait pas : tout host déclarant `distro: debian12`
  échouait au provision. Ajout de `templates/cloud-init/debian.yaml.tmpl` (mêmes
  comptes de service `student`/`ansible` et même durcissement que les autres
  distros). Debian 12 se provisionne désormais sur kvm, incus et outscale.
- **Distros récentes câblées sur tous les providers** : `debian13` (trixie) et
  `ubuntu26` (26.04 LTS, Resolute Raccoon), en plus de `alma9` et `ubuntu22`.
  Chaque provider expose désormais le même jeu de sept distros (URL d'images
  kvm, alias `images:` incus, OMI pinées outscale), vérifié par
  `test_cloud_init_templates.py`. URL d'images confirmées disponibles avant
  câblage.
- **Test de non-régression sur la cohérence distro/cloud-init**
  (`tests/test_cloud_init_templates.py`) : toute distro mappée par un provider
  doit avoir son template cloud-init, les trois providers doivent exposer le
  même jeu de distros, et `debian12` doit être câblé partout. C'est le garde-fou
  qui a manqué au `debian.yaml.tmpl` absent.

### Corrigé

- **Outscale ne mappait des OMI que pour `alma10` et `ubuntu24`** alors que
  `distro_to_template` en promettait cinq. Un host déclarant `alma9`, `ubuntu22`
  ou `debian12` sur outscale se résolvait en OMI vide et un échec Terraform
  opaque. `image_ids` couvre désormais tout le jeu (chaque entrée gardant son
  défaut `""`, un catalogue ne pin que les OMI qu'il utilise), avec les clés
  correspondantes `image_id_alma9` / `image_id_ubuntu22` / `image_id_debian12`
  documentées dans `variables.tf`.
- **`element N has vanished` à l'ajout d'un host sur un réseau KVM existant.**
  Le provider `dmacvicar/libvirt` ne sait pas mettre à jour un réseau en place :
  modifier `ips[].dhcp.hosts` le pousse à recréer le réseau (issue #468), ce qui
  échoue et couperait la connectivité de toutes les VM attachées. Le réseau est
  désormais figé après création (`lifecycle { ignore_changes = [ips] }`) ; les
  baux DHCP des hosts ajoutés ensuite sont posés à chaud via `virsh net-update`,
  dans une nouvelle étape `_ensure_kvm_dhcp_leases` jouée avant l'apply des
  domaines.
- **Collision de MAC entre dépôts partageant un hôte (KVM).** Les MAC étaient
  `52:54:00:cd:00:<idx>`, identiques d'un dépôt à l'autre : deux catalogues qui
  tournent en parallèle donnaient la même MAC à leurs VM de même index, et l'une
  devenait injoignable (`No route to host` silencieux). Les deux octets du
  milieu sont maintenant dérivés d'un hash du `repo.id`, rendant les MAC uniques
  par dépôt : le pendant en couche 2 de l'isolation par CIDR déjà en place. Les
  VM KVM existantes doivent être re-provisionnées pour prendre les nouvelles MAC.

## [0.1.31] - 2026-07-23

### Corrigé

- **`dsoxlab next` proposait les labs dans l'ordre alphabétique.** Le tri
  pédagogique s'appuie sur `bloc_order`, que le scanner ne posait jamais : il
  restait à 0 sauf mention explicite dans un `lab.yaml`, et le tri retombait
  sur l'`id`. Un débutant se voyait proposer `ansible-vault` avant son premier
  playbook, ou l'écriture d'un script Bash avant d'avoir ouvert un terminal.
  Mesuré : **19 sections sur 22** dans le dépôt Ansible.
  Le `meta.yml` est documenté comme pilotant cet ordre ; il le pilote
  désormais vraiment. Le scanner dérive la position depuis
  `sections[].labs[]`, donc aucun dépôt n'a à recopier l'information dans ses
  `lab.yaml` : 197 fichiers n'ont plus besoin d'être touchés. Un `bloc_order`
  explicite reste prioritaire.

## [0.1.30] - 2026-07-23

### Ajouté

- **Trois contrôles de structure supplémentaires.** Le **barème** d'abord :
  dsoxlab note **par test**, donc un lab qui annonce cinq tâches à 20 points
  mais compte six tests attribue en réalité 16,7 points par tâche, et le
  barème affiché ment sans que personne puisse le deviner. Il ne se déclenche
  que si l'énoncé annonce des points par tâche : un examen blanc qui vérifie
  plusieurs points par tâche fait un autre choix, tout aussi valable. La
  **parité des langues** ensuite, un `.fr.md` sans équivalent laissant
  l'autre moitié des apprenants sur un contenu absent ou périmé. Les
  **cibles vm** enfin, dont le FQDN ne se vérifiait qu'au moment de jouer le
  lab, sur la machine de l'apprenant et après provisionnement, alors qu'il
  est lisible dans le contrat.
- **`validate-structure` contrôle désormais le contenu, pas seulement la
  présence des fichiers.** Trois dérives silencieuses, qu'aucun test
  fonctionnel n'attrape parce qu'elles ne cassent pas l'exécution d'un lab :
  un **lien relatif mort** dans un Markdown (le dépôt Ansible en comptait 150
  le jour où le contrôle y a été écrit), une **solution laissée en clair**
  (irrattrapable : git la garde pour toujours), et un **`doc_url` qui ne
  répond plus**, via l'option `--check-urls` puisqu'elle sort sur le réseau.
  Ces contrôles étaient recopiés à la main dans chaque dépôt de labs ; ils
  profitent maintenant à tous. Le contrôle des solutions ne s'applique qu'aux
  dépôts qui tiennent un répertoire `solution/` : son absence n'est pas une
  faute, c'est un autre choix.

## [0.1.29] - 2026-07-23

### Corrigé

- **`check-release.py` concluait « Tout est bon » alors qu'il venait de
  signaler une CI en cours.** Son premier usage réel l'a montré : le message
  final contredisait l'avertissement, et invitait à taguer précisément quand
  `RELEASING` demande d'attendre. Une CI en cours est désormais une
  **attente** et non une simple note : le script sort en 2 avec « il est trop
  tôt », distinct de l'échec (1) où quelque chose est à corriger, et du feu
  vert (0).

## [0.1.28] - 2026-07-23

### Ajouté

- **Un contrôle local à lancer avant de poser un tag** :
  `python3 scripts/check-release.py`. Le garde-fou ajouté en 0.1.27 vit dans
  le workflow, donc il ne parle qu'une fois le tag poussé : il faut alors le
  supprimer en local et sur le dépôt distant. Ce script rejoue les mêmes
  vérifications à froid, plus celles que `RELEASING` confiait à la vigilance
  humaine : arbre propre, `main` à jour, tag cohérent avec `pyproject.toml`,
  section de CHANGELOG présente **dans les deux langues**, `uv.lock` aligné,
  version encore libre sur PyPI, CI verte sur le commit. Il affiche tous les
  verdicts d'une traite, puis la commande exacte à lancer.

## [0.1.27] - 2026-07-23

### Corrigé

- **Le workflow de release publiait sous un tag qui ne correspondait pas à la
  version empaquetée.** Le build lit `pyproject.toml`, le tag ne sert qu'aux
  notes : rien ne vérifiait qu'ils concordent. Deux fois de suite, un tag posé
  sur un commit dont la version avait déjà bougé a produit une publication
  fausse. `v0.1.22` a republié 0.1.21, et `v0.1.25` a construit puis publié
  0.1.26 sous le mauvais tag, si bien que PyPI n'a jamais reçu de 0.1.25. Le
  workflow refuse désormais et dit quoi faire.

## [0.1.26] - 2026-07-23

> Publiée sous le tag `v0.1.25`, posé sur un commit qui portait déjà le bump
> 0.1.26 : PyPI n'a donc jamais reçu de 0.1.25, et tout ce que cette version
> annonçait est présent ici.

### Corrigé

- **L'icône de runtime décalait l'affichage.** Les emoji de largeur double, et
  leur sélecteur de variante, sont comptés pour une colonne par Rich mais rendus
  sur deux par le terminal : la ligne glissait et la bordure du panneau se
  brisait. L'icône est retirée de `show` et de `list-labs`. Elle affichait de
  toute façon « ? » sur tous les labs `vm` : sa table connaissait `kvm` et
  `incus`, les deux alias rétro-compat, mais pas `vm`, la valeur canonique du
  contrat.
- **Une section inconnue passée à `use` était acceptée sans un mot.**
  `dsoxlab use l2` posait le filtre, puis `list-labs` répondait « Aucun lab
  trouvé » : l'apprenant croyait le catalogue vide alors qu'il venait de poser
  un filtre ne correspondant à rien. La commande refuse maintenant et liste les
  sections déclarées dans le `meta.yml`.
- **La difficulté restait en anglais en français.** `show` affichait
  « Difficulté : intermediate ». Les trois valeurs employées par les dépôts de
  labs sont traduites ; le champ restant libre par contrat, toute autre valeur
  s'affiche telle quelle plutôt que de disparaître.

## [0.1.25] - 2026-07-23

### Ajouté

- **dsoxlab signale qu'une version plus récente existe.** Un apprenant
  installe la CLI une fois et ne revient jamais vérifier : il joue des labs
  avec des défauts corrigés depuis longtemps, et remonte des problèmes déjà
  résolus. La vérification a lieu une fois par jour et l'avis s'affiche en
  dernier, pour être lu.

  Il est construit pour ne jamais gêner. Le message part sur **stderr**, jamais
  sur stdout : un document `--json` reste lisible quoi qu'il arrive. Il est tu
  quand stderr n'est pas un terminal, ce qui laisse les journaux de CI propres.
  Toute défaillance (hors ligne, PyPI en panne, proxy hostile, réponse
  illisible) est avalée en silence : vérifier une version n'est jamais une
  raison de casser un `check`. Le résultat est mis en cache un jour, pour
  qu'une salle de formation ne martèle pas PyPI. Désactivation par
  `DSOXLAB_NO_UPDATE_CHECK=1`.

## [0.1.24] - 2026-07-23

### Ajouté

- **`destroy` demande désormais confirmation.** La commande effaçait un parc
  entier sans un mot : tapée dans le mauvais dépôt, elle détruisait les VM et
  leurs données sans retour possible. Elle demande maintenant confirmation, et
  `--yes` / `-y` préserve l'usage scripté (CI, procédure de récupération
  documentée).

### Corrigé

- **`check` ne plante plus sur un dépôt qui déclare plusieurs providers sans
  qu'aucun soit actif.** La lecture des outputs Terraform lève
  `ProviderUnresolved` et la traceback remontait telle quelle depuis
  `inventory.py`. L'apprenant reçoit maintenant le même message actionnable que
  pour les commandes d'infra : choisir un provider avec
  `dsoxlab use --provider <nom>` ou `DSOXLAB_PROVIDER=<nom>`. Les labs shell,
  qui n'ont besoin d'aucune infrastructure, ne sont concernés dans aucun cas.

### Modifié

- **`destroy --host` ne prétend plus isoler une VM.** Mesuré sur un parc de
  trois hôtes : `terraform destroy -target` détruit aussi tout ce qui dépend de
  la cible, si bien que demander un seul hôte planifiait **7** ressources à
  détruire, et non 4. L'aide de l'option annonçait « détruit une seule VM », ce
  qui est faux et dangereux. Elle décrit maintenant le comportement réel et
  renvoie vers `destroy` + `provision`, seule façon fiable de récupérer une
  machine inaccessible ; un avertissement est affiché à l'exécution.

## [0.1.23] - 2026-07-22

> Le tag `v0.1.22` a été posé sur le mauvais commit, avant la fusion de sa pull
> request : le workflow a republié la 0.1.21 et PyPI n'a jamais reçu de 0.1.22.
> Tout ce que cette version portait est donc livré ici.

### Corrigé

- **`check --json` polluait sa propre sortie.** En cas d'échec, la sortie brute
  de pytest précédait le document JSON, rendant le flux inanalysable. Le garde
  manquait sur cette seule branche, et c'est le cas le plus fréquent en usage
  réel : un lab qui passe ne l'emprunte jamais, ce qui explique précisément que
  le contrôle initial soit passé à côté. Le texte reste disponible pour
  l'appelant dans `check.output`.

- **`status --json` n'émettait aucun document** quand le `meta.yml` ne déclare
  aucun hôte. Un catalogue entièrement `shell` est un cas normal, pas une
  erreur : il rend désormais un document avec `total: 0`, au lieu d'une phrase
  Rich et d'un code de sortie 0.

- **Les plans Terraform redeviennent stables, donc `provision` est rejouable.**
  L'`instance-id` du cloud-init était construit avec `timestamp()`, donc il
  changeait à chaque exécution : Terraform planifiait un remplacement du disque
  cloud-init à chaque fois, et le provider libvirt le refuse (« Storage volumes
  cannot be updated »). Rejouer un provision échouait donc sur n'importe quel
  dépôt, ne laissant que `destroy` puis `provision` comme issue. L'identifiant
  dérive désormais d'un hachage du contenu cloud-init, et le nom du volume
  aussi : plan stable quand rien n'a bougé, remplacement propre quand quelque
  chose a bougé.

### Ajouté

- **`dsoxlab course` affiche désormais le README du lab, et non le seul
  scenario.** Les deux fichiers sont complémentaires et étaient traités comme
  concurrents : `scenario` pose la situation en quelques lignes, `README`
  explique les commandes et déroule les exercices. Seul le premier était
  affiché, si bien que la moitié la plus riche n'était atteignable par aucune
  commande (mesuré : 10 465 lignes de code dans les README d'un seul dépôt,
  exposées par rien). L'apprenant en concluait qu'il n'y avait pas de cours et
  allait chercher la réponse dans l'énoncé du challenge. `course` affiche
  maintenant le scenario, puis le README, dans la langue demandée.

- **Un fragment SSH par formation, dans `~/.ssh/config.d/<repo-id>.conf`.**
  Écrit par `provision`, rafraîchi par `status`, retiré par `destroy`. Les
  énoncés demandent de se connecter à une machine par son nom, mais ce nom
  n'est ni dans le DNS ni dans `/etc/hosts` : un `ssh alma-rhcsa-1.lab`
  échouait. Il fonctionne désormais, sans `-F` ni préfixe `dsoxlab`. Un
  avertissement est émis quand `~/.ssh/config` ne contient pas la ligne
  `Include ~/.ssh/config.d/*.conf`, car le fragment serait écrit mais jamais
  lu. Il est retiré au `destroy`, pour ne laisser aucune configuration pointant
  des adresses recyclées.

- **Le panneau d'accueil nomme la machine du lab** pour un lab en
  `session: local` qui se joue malgré tout sur un hôte : l'apprenant sait où se
  connecter sans avoir à deviner le nom.

- **`bloc` et `bloc_order` dans le catalogue JSON.** La CLI trie dessus, mais
  ils n'étaient pas publiés : une intégration ne pouvait regrouper que par
  `section`, laquelle vaut `repo.category` par défaut. Mesuré : 84 labs sous un
  nœud unique dans `linux-dsoxlab-training`.

## [0.1.21] - 2026-07-22

### Ajouté

- **`runtime.session` dans `lab.yaml`** — un lab `vm` déclare désormais où
  s'ouvre sa session interactive : `target` (défaut, session SSH sur
  `targets[].host`, comportement inchangé) ou `local`, un sous-shell sur le
  poste de l'apprenant, à la racine du dépôt.

  Certains catalogues se pilotent **depuis** le poste et non **dans** la
  machine : l'apprenant écrit son code dans le dépôt et lance ses commandes
  vers les hôtes du lab, qui restent provisionnés et ciblés par le
  `setup.yaml`. Pour ceux-là, `dsoxlab run` ouvrait une session SSH sur un
  hôte ne contenant ni le dépôt ni ses outils : la session s'ouvrait, mais il
  n'y avait rien à y faire. Le panneau d'accueil annonce maintenant où l'on
  atterrit, et `validate-structure` refuse toute valeur hors des deux
  acceptées, qui retomberait silencieusement sur le SSH.

### Corrigé

- **`dsoxlab run` annonçait un mauvais emplacement.** Le message de démarrage
  affirmait « Vous êtes dans `challenge/work/` » quel que soit le runtime, y
  compris pour les labs `vm`, où l'apprenant n'atterrit jamais dans ce
  répertoire. Il nomme désormais l'endroit réel : le workdir pour `shell`,
  l'hôte connecté pour une session `target`, la racine du dépôt pour une
  session `local`. Le message `shell` lit en outre le vrai `runtime.workdir`
  au lieu de supposer la valeur par défaut.

- **Le panneau d'accueil listait des commandes intapables.** Pour un lab `vm`,
  il affichait six commandes `dsoxlab …` puis ouvrait une session SSH sur
  l'hôte du lab, où dsoxlab n'est pas installé et ne l'a jamais été : toutes
  répondaient `command not found`. Le panneau nomme désormais l'hôte auquel
  il va connecter et précise que ces commandes vivent sur le poste de
  l'apprenant, derrière `exit`. Pour une session `local`, il nomme le
  répertoire du lab auquel les chemins de la mission se rapportent, et amorce
  par `dsoxlab challenge`.

- **Sortie lisible par un programme** : `--json` sur `list-labs`, `progress`,
  `check` et `status`. Chaque document porte une version de `schema`, et la
  sortie standard ne contient rien d'autre que du JSON : les messages
  d'ambiance, la barre de progression pytest et le rappel du contexte actif
  sont tus dans ce mode.

  C'est ce dont toute intégration a besoin : sans cela, une extension
  d'éditeur, un tableau de bord ou un script de suivi devraient analyser la
  sortie Rich, dont les tableaux, les couleurs et les retours à la ligne
  dépendent de la largeur du terminal et ont vocation à changer.

## [0.1.20] - 2026-07-20

### Corrigé

- **`lvm2` est absent de l'image cloud AlmaLinux 9**, et tout lab de stockage
  échouait sur `Failed to find required executable "vgs"` : pas au montage, mais dès
  le premier appel de module LVM. Le commentaire du gabarit affirmait que « lvm2,
  parted et xfsprogs sont dans l'image AlmaLinux Cloud » : vrai en 10, faux en 9. Il
  dit désormais ce qui a été réellement vérifié sur la 9.8, et `lvm2` est installé
  explicitement. Mesuré sur un catalogue de labs : **78 tests en erreur** dus à ce
  seul paquet.

- **`cloud-init status --wait` était lancé sans privilèges**, et sortait donc en
  `PermissionError: /run/cloud-init/cloud.cfg` (rc=1) sur AlmaLinux 9. Le `|| true`
  final avalait cet échec : `wait_for_hosts_ready` rendait la main *avant* la fin de
  cloud-init tout en paraissant l'avoir attendue. C'est désormais `sudo -n`, qui
  rend rc=0. Le `-n` garde la commande non interactive : un hôte où sudo réclamerait
  un mot de passe bloquerait au lieu d'échouer.

## [0.1.19] - 2026-07-20

### Corrigé

- **cloud-init finissait en `status: error` sur chaque nœud KVM, et `dsoxlab
  provision` restait bloqué sur son attente.** Le runcmd lançait `systemctl enable
  --now qemu-guest-agent`, or cette unité déclare
  `BindsTo=dev-virtio\x2dports-org.qemu.guest_agent.0.device` et le provider KVM ne
  déclare **aucun channel virtio**, délibérément (cf. la note dans
  `templates/terraform/kvm/main.tf` : le schéma du provider libvirt le rendait
  impraticable). Le device n'apparaît donc jamais : `--now` attendait **90 secondes
  par nœud**, échouait, et le script runcmd sortait en 1, ce que cloud-init
  rapporte comme un module `scripts_user` en échec.

  Le nœud était pourtant pleinement fonctionnel (comptes créés, paquets installés,
  sshd et firewalld actifs) : le symptôme était uniquement un provisionnement qui
  ne rendait jamais la main. Retirer `--now` conserve l'activation pour le jour où
  un channel existera, et la commande rend désormais la main en **0 s au lieu de
  90**.

## [0.1.18] - 2026-07-20

> **La 0.1.17 n'a jamais été publiée.** Son tag a été posé sur le commit de la
> 0.1.16 : la Release GitHub `v0.1.17` porte donc des artefacts `dsoxlab-0.1.16`,
> et PyPI est resté à la 0.1.16. Le correctif ci-dessous, annoncé pour la 0.1.17,
> est livré par cette version.

### Corrigé

- **`alma9` et `ubuntu22` étaient déclarés mais inutilisables sur le provider
  `kvm`.** Tous deux figurent dans la table Terraform `distro_to_template` : un
  dépôt de labs pouvait donc légitimement écrire `distro: alma9` dans son
  `meta.yml`, alors qu'aucun des deux n'avait d'entrée dans `default_image_urls`.
  Le `coalesce()` qui résout l'image n'avait plus rien à quoi se raccrocher et le
  plan échouait, sauf si le dépôt surchargeait à la main
  `providers.kvm.image_url_<distro>`.

  Les deux embarquent désormais leur image cloud amont, comme les distributions
  déjà listées. Toute distribution que le provider mappe a de nouveau une URL ; le
  provider `incus` gérait déjà `alma9` (`images:almalinux/9/cloud`), et `outscale`
  attend légitimement une OMI pinée par le dépôt.

  Le point compte particulièrement pour la formation RHCE : l'examen EX294 se passe
  sur RHEL 9, donc un catalogue qui le vise a besoin que `alma9` fonctionne sans
  bricolage.

## [0.1.16] - 2026-07-20

### Ajouté

- **`dsoxlab guide [<id>]` ouvre le cours en ligne d'un lab dans le navigateur.**
  Le cours n'est pas embarqué dans le dépôt de labs : chaque lab déclare un
  `doc_url` qui pointe vers le site du formateur. Ouvrir la vraie page, plutôt que
  d'en rapatrier le contenu, la laisse s'afficher telle qu'elle est publiée (images,
  blocs de code, navigation) et évite d'avoir à suivre la structure HTML d'un site
  tiers. `--print` écrit l'URL au lieu d'ouvrir un navigateur : c'est ce qu'on veut
  en SSH, où `webbrowser` n'a rien à ouvrir.

- **`guide_url()` dans le nouveau `services/guide_service.py`**, une fonction pure
  qui compose l'URL et n'ouvre rien. Elle ajoute des paramètres de campagne
  (`utm_source=dsoxlab`, `utm_medium=lab`, `utm_campaign=<lab_id>`) pour qu'un
  formateur puisse voir quels labs amènent réellement des lecteurs vers quels
  guides.

  Ce marquage est nécessaire, pas décoratif : un lien suivi depuis une interface
  locale transmet au mieux `http://localhost:<port>` comme referrer, au pire rien du
  tout, si bien que ces lectures seraient sinon indistinguables du trafic direct.
  Les paramètres de requête déjà présents et les ancres `#section` sont conservés,
  donc un lab peut viser une section précise d'un guide. `source` et `medium` sont
  surchargeables, ce qui permettra à une future interface web de se distinguer de la
  CLI.

## [0.1.15] - 2026-07-20

### Ajouté

- **`services/progress_service.py`** : `build_progress()`, `next_pending_lab()` et
  `pedagogical_sort_key()` exposent la progression de l'apprenant sous forme de
  données typées (`BlocProgress`), et non plus de balisage terminal.
- **`evaluate_lab()` et `compute_score()`** dans `services/lab_service.py` : noter
  une exécution et l'enregistrer devient un seul appel de service, qui rend un
  `ScoreResult`.
- **`SessionSpec` et `Runtime.session_spec()`** : un runtime peut désormais
  *décrire* sa session interactive au lieu de l'ouvrir, et `lab_session_spec()`
  l'expose comme service. `SessionSpec.display()` rend la commande telle qu'un
  apprenant la taperait, quoting compris.

  `open_session()` appelle `subprocess.call`, qui s'empare du terminal courant. Cela
  rendait deux choses impossibles : montrer la commande plutôt que l'exécuter, et
  laisser une interface qui ne peut pas céder son TTY choisir son mode
  d'attachement. L'exécution est maintenant à un seul endroit
  (`BaseRuntime.open_session`), et chaque runtime ne fait plus que décrire.

### Corrigé

- **`dsoxlab ssh`, `dsoxlab status` et la session interactive VM se connectaient
  encore en `student`.** La 0.1.14 a basculé l'inventaire et le `ssh_config` généré
  vers le compte de service `ansible`, mais avait laissé `student@` codé en dur à
  trois endroits : ces commandes et le `ssh_config` généré n'étaient donc pas
  d'accord sur le compte de connexion. Sur un lab qui restreint `AllowUsers` au
  compte de l'automatisation, `dsoxlab ssh` se retrouvait verrouillé hors du nœud
  qu'il venait de provisionner. Le compte est désormais lu depuis l'inventaire
  (`ansible_user`) dans les trois cas, et il ne reste plus aucun compte codé en dur
  dans le paquet.

### Modifié

- **La logique métier ne vit plus dans la couche de présentation.** La formule de
  score était dans `cli.py` (`_run_check`), entrelacée avec des `typer.Exit` et des
  appels d'affichage, et l'agrégation de progression était dans
  `reporting/console.py`, qui produisait du balisage Rich au fil du calcul. Les deux
  étaient donc inatteignables depuis ailleurs et intestables sans capturer une
  sortie terminal : toute seconde interface aurait dû réimplémenter la formule de
  score et la règle « quelle est la prochaine étape ».

  Ce sont désormais des fonctions pures sur des données simples.
  `print_progress_table()` ne fait plus que du rendu, la commande `next` ne fait
  plus que présenter, et les règles qu'elles portent sont couvertes par des tests
  unitaires (14 nouveaux tests, dont celui qui compte le plus : un indice abaisse le
  plafond, il n'est pas soustrait du score final).

  Aucun changement de comportement : mêmes scores, même ordre, même rendu, vérifié
  sur `ansible-training` et sur `linux-dsoxlab-training`.

## [0.1.14] - 2026-07-20

### Ajouté

- **Un compte de service `ansible` dédié sur chaque nœud provisionné.** Les
  gabarits cloud-init (AlmaLinux et Ubuntu) créent désormais un compte `ansible`
  à côté du compte humain `student`, avec le même durcissement : clé SSH
  uniquement, aucun mot de passe de connexion, appartenance à `wheel`/`sudo` et
  `sudo NOPASSWD:ALL`.

  Séparer le compte de *service* utilisé par l'automatisation du compte *humain*
  est la bonne pratique : la traçabilité garde du sens et chaque compte peut être
  révoqué sans verrouiller l'autre. `student` reste le compte humain sur le
  control node ; `ansible` est le compte par lequel dsoxlab et les playbooks des
  labs se connectent. Le `NOPASSWD:ALL` global est assumé, car ce compte pilote
  une automatisation généraliste (dnf, systemd, LVM, SELinux, firewalld) : la
  sécurité vient de la dédicace du compte, pas d'un bridage de ses règles sudo.

- **Les paquets absents de l'image cloud minimale AlmaLinux.** `firewalld` n'est
  pas fourni dans l'image cloud AlmaLinux 10 : `systemctl enable --now firewalld`
  visait donc une unité inexistante et tous les labs de pare-feu échouaient.
  Ajoutés avec lui :

  - `python3-firewall`, requis par le module `ansible.posix.firewalld`, qui sinon
    échoue sur *Failed to import the required Python library (firewall)*.
  - `policycoreutils-python-utils`, qui fournit `semanage`, l'outil RHCSA de
    référence pour la gestion des ports et des contextes SELinux.

  Ce sont des *prérequis d'exécution* Ansible : leur place est dans l'image de
  base, pour que chaque nœud managé soit prêt pour Ansible sans amorçage par lab.

### Modifié

- **CASSANT : le compte SSH par défaut devient `ansible`, et non plus
  `student`.** `build_inventory()` et `write_ssh_config()` utilisent désormais
  `ansible` comme valeur par défaut de `ssh_user` : l'inventaire et le
  `ssh_config` générés se connectent avec le compte de service.

### Migration

Les nœuds provisionnés avant la 0.1.14 n'ont pas de compte `ansible` et
deviennent injoignables avec ce nouveau défaut. Il faut les reprovisionner :

```console
dsoxlab destroy && dsoxlab provision
```

Dans les dépôts de labs, tout ce qui restreint la connexion (`AllowUsers`,
`remote_user`, `ansible_user`) doit désormais viser `ansible`, jamais `student`.
Le pointer sur `student` verrouille l'automatisation hors du nœud.

## [0.1.13] - 2026-07-17

### Modifié

- **Licence : CC BY 4.0 → Apache-2.0.** Creative Commons
  [déconseille ses licences pour du logiciel](https://creativecommons.org/faq/#can-i-apply-a-creative-commons-license-to-software) :
  elles n'accordent aucun brevet, leurs termes sont écrits pour des œuvres de
  création et non pour du code, et PyPI ne pouvait classer le paquet qu'en
  `Other/NOASSERTION`. Pour une CLI publiée sur PyPI et importée par des dépôts
  de labs tiers, cela laissait une réelle ambiguïté juridique aux utilisateurs.

  **Apache-2.0 est la licence logicielle la plus proche des termes précédents.**
  Elle conserve les deux obligations qu'imposait CC BY 4.0 — créditer l'auteur,
  et indiquer si les fichiers ont été modifiés (§4.b) — et y ajoute la concession
  de brevet explicite qui manquait à CC BY 4.0. L'attribution vit désormais dans
  le fichier [NOTICE](./NOTICE), que le §4.d impose de transmettre avec toute
  œuvre dérivée.

  **Les versions jusqu'à la 0.1.12 incluse restent sous CC BY 4.0** : cette
  concession est irrévocable pour quiconque les a reçues. Seules les versions à
  partir de la 0.1.13 sont sous Apache-2.0.

## [0.1.12] - 2026-07-17

### Corrigé

- **La provenance de build n'atteste plus un fichier qui n'est pas publié.**
  `uv build` dépose un `dist/.gitignore` d'un octet, et
  `attest-build-provenance` inclut les fichiers cachés dans son glob (au
  contraire du glob shell qui alimente `gh release create`) : l'attestation de
  la v0.1.11 listait donc `.gitignore` à côté de la wheel et du sdist. Les
  artefacts sont désormais nommés explicitement. Anodin en soi, mais une
  attestation doit nommer exactement ce qui est publié, rien de plus.

## [0.1.11] - 2026-07-17

### Corrigé

- **Un `lab.yaml` ou un `meta.yml` malformé pouvait faire planter la CLI au lieu
  d'être ignoré.** `discovery/scanner.py` rattrape `(KeyError, ValueError,
  yaml.YAMLError)` et ignore le lab fautif avec un warning — mais les parsers
  pouvaient lever hors de ce contrat, et l'exception remontait alors en
  traceback brut sur une commande sans rapport (`list-labs`, `progress`…).
  Comme un `lab.yaml` provient d'un *dépôt fournisseur de labs*, c'est l'entrée
  non fiable du moteur. Cinq cas, tous trouvés par les nouveaux harnais de
  fuzzing :
  - un `lab.yaml` **vide** (ou réduit à des commentaires) → `AttributeError`,
    `yaml.safe_load` rendant `None` ;
  - un document dont la **racine est une liste ou un scalaire**, dans les deux
    fichiers ;
  - **`runtime: vm`** écrit à la place du bloc `runtime:`, et
    `runtime.targets: true` → `AttributeError` / `TypeError` ;
  - **`infra.hosts:` écrit en mapping** au lieu d'une liste → `TypeError` sur
    `h["name"]`, l'itération portant sur les clés ;
  - une **clé présente mais vide** comme `vcpu:` ou `bloc:` → `int(None)` lève
    `TypeError`, `.get("vcpu", 1)` rendant `None` et non le défaut quand la clé
    existe.

  Chacun de ces cas lève désormais un `ValueError` portant le chemin du fichier
  et le champ fautif : le lab est ignoré et le reste du catalogue se charge. Un
  `ip:` vide ne donne plus non plus la chaîne littérale « None ».

### Ajouté

- **Des harnais de fuzzing sur le contrat YAML non fiable** (`fuzz/`), rejoués
  en régression courte dans la CI. Ils vérifient le *contrat* — toute exception
  hors de `(KeyError, ValueError, yaml.YAMLError)` fait échouer le run — plutôt
  que de simplement exécuter les parsers. Livrés avec un corpus de graines et un
  dictionnaire libFuzzer des mots-clés du contrat ; `uv sync --group fuzz`
  installe atheris (tenu hors du groupe `dev`).
- **`actionlint` et `poutine` en gates CI**, aux côtés du job zizmor existant,
  tous deux installés depuis un binaire de release dont le SHA-256 est vérifié
  contre les checksums publiés. `poutine --fail-on-violation` en fait une gate,
  pas un rapport. Les jobs lourds attendent désormais les trois scanners.
- **`step-security/harden-runner`** en premier step de chaque job
  (`egress-policy: audit`), et un `.poutine.yml` qui acquitte trois actions
  vérifiées à la main par leur purl, sans désactiver la règle.
- **La provenance de build attachée à la Release GitHub** sous le nom
  `provenance.intoto.jsonl`. L'attestation existante est enregistrée sur l'API
  d'attestation de GitHub, qui est un artefact *distinct* de l'asset de release
  qu'attend le contrôle Signed-Releases d'OpenSSF Scorecard.

## [0.1.10] - 2026-07-16

### Corrigé

- **Les scores étaient faux sur les labs dont les données contiennent
  « ERROR », « PASSED » ou « FAILED »** : `_parse_counts()` comptait les
  occurrences de ces mots dans la sortie brute de pytest, messages d'assertion
  compris. Un lab qui filtre des lignes `ERROR` (`l1-get-help`,
  `l1-grep-regex`, `l1-redirections-pipes`, `l3-service-diagnose`…) gonflait son
  propre total — `dsoxlab check` annonçait `1/5` pour un lab de 4 tests, et le
  score de l'apprenant s'en trouvait sous-évalué (20 pts au lieu de 25). La
  ligne de résumé que pytest produit lui-même fait désormais foi, avec un repli
  ancré sur les node-ids.

## [0.1.9] - 2026-07-16

### Corrigé

- **KVM : deux dépôts de labs ne se disputent plus le même volume de base.**
  L'image de base libvirt s'appelait `dsoxlab-base-<distro>.qcow2`, sans
  l'identifiant du dépôt. Or le pool libvirt est *partagé* entre tous les
  dépôts, alors que chacun garde son **propre** state Terraform. Le second
  dépôt à provisionner sur une distro déjà utilisée par un autre échouait donc
  sur `storage volume 'dsoxlab-base-alma10.qcow2' exists already` : son state
  ignorait simplement le volume créé par le premier. Concrètement,
  `linux-dsoxlab-training` (alma10) bloquait `ansible-training` (alma10) sur la
  même machine. Le volume devient `dsoxlab-base-<repo-id>-<distro>.qcow2` : les
  catalogues cohabitent vraiment, comme le contrat le promet déjà avec leurs
  réseaux libvirt séparés. L'image cloud est dupliquée par dépôt (sparse, ~600 Mo
  à 2 Go) : c'est le prix de l'isolation.

  Terraform reçoit une variable `repo_id`, déclarée par les trois providers
  (`kvm`, `incus`, `outscale`) puisque les tfvars sont communs ; seul `kvm` crée
  un volume local, lui seul était touché. Incus tire des alias d'images publiques
  et Outscale utilise des AMI : aucune collision possible.

  **Impact à la mise à jour.** Sur un dépôt provisionné en ≤ 0.1.8, le prochain
  `dsoxlab provision` renomme le volume de base, ce que Terraform traite comme un
  *remplacement* : les VMs sont recréées. Rien n'est perdu (les VMs de labs sont
  jetables par conception, et le travail de l'apprenant vit dans le dépôt,
  `challenge/`, jamais sur la VM), mais l'état des labs en cours sur les VMs
  disparaît. Enchaîner `dsoxlab destroy` puis `dsoxlab provision` pour un cycle
  propre.

## [0.1.8] - 2026-07-16

### Corrigé

- **Plus de traceback Python quand l'infrastructure n'est pas provisionnée** :
  un apprenant qui lançait un lab VM avant `dsoxlab provision` (premier
  lancement, ou après un `destroy`) recevait un `ValueError: target_fqdn '...'
  n'est pas dans la liste des hôtes connus : []` brut. C'est une situation
  normale, pas un bug — `build_inventory()` lève désormais
  `InfraNotProvisioned`, que la CLI rend en une phrase actionnable (EN+FR)
  indiquant de lancer `dsoxlab provision`. Un point d'entrée `main()` l'attrape
  pour toutes les commandes : aucune ne peut plus afficher de traceback pour ça.
- **`check` n'enregistre plus un 0/100 en l'absence d'infrastructure** : pytest
  tourne en sous-processus, donc l'erreur d'hôte manquant ne pouvait pas
  remonter jusqu'à la CLI — l'exécution était notée comme un échec de
  l'apprenant et sauvegardée dans son historique. `check`/`submit` vérifient
  maintenant l'inventory avant de noter, et sortent sans rien enregistrer.

## [0.1.7] - 2026-07-16

### Ajouté

- **Les labs multi-distrib deviennent réels** : `check`/`submit` acceptent
  `--target/-t` et exportent le FQDN de la cible résolue aux tests via
  `DSOXLAB_TARGET_HOST`. Jusqu'ici `runtime.targets[]` n'était que déclaratif —
  un lab pouvait déclarer une cible Ubuntu pendant que ses tests codaient
  l'hôte RHEL en dur : choisir Ubuntu ne changeait rien et le contrat mentait.
  Les tests demandent désormais l'hôte choisi (helper `lab_target_host()` dans
  le `conftest.py` du dépôt), donc un même lab peut être réellement validé sur
  plusieurs distributions.

### Corrigé

- **Une faute de frappe dans `--target` n'enregistre plus un 0/100** : une
  cible explicite inconnue est désormais une erreur (`unknown_target`, EN+FR)
  levée avant le lancement des tests, au lieu d'un check échoué sauvegardé dans
  l'historique de l'apprenant.
- **Une cible de session ne casse plus les labs qui ne la déclarent pas** :
  l'`active_target` persistée par `use --target` n'est appliquée qu'aux labs
  qui la déclarent ; les labs shell et mono-cible l'ignorent silencieusement.

## [0.1.6] - 2026-07-16

### Corrigé

- **Inventory KVM après un provision ciblé** : `terraform apply -target`
  n'évalue pas les outputs racine, donc les IP des hôtes KVM (DHCP libvirt)
  manquaient et `dsoxlab check` échouait « Aucun host dans l'inventory » pour
  tout lab KVM. `apply()` lance désormais un `terraform apply -refresh-only`
  après un apply ciblé pour recalculer le map d'outputs `hosts` sans recréer de
  ressource.

### Ajouté

- **Détection de conflit de provider** : `dsoxlab provision` s'arrête avec un
  message d'aide (EN + FR) si un autre provider (incus/KVM) a encore de l'infra
  active — ils partagent le nom de réseau et le subnet du lab et ne peuvent pas
  tourner en même temps.

## [0.1.5] - 2026-07-15

### Ajouté

- **hints i18n** : le format moderne d'indice (`text_en` / `text_fr`) accepte
  désormais aussi des valeurs encodées en base64, pour que les indices soient à
  la fois bilingues et obfusqués dans le fichier. Le loader tente le base64
  d'abord, avec repli sur le texte brut.

### Modifié

- **challenge i18n** : le brief de challenge localisé est résolu en
  `challenge/README.<lang>.md` (ex. `README.fr.md`), cohérent avec
  `scenario.<lang>.md` et le `README.<lang>.md` racine — au lieu de l'ancien
  nommage `README_FR.md`.

## [0.1.4] - 2026-07-15

### Corrigé

- **progress** : `dsoxlab progress` affiche désormais un nom de bloc clair (le
  titre de la section meta.yml, ex. « Fondamentaux (l1) ») au lieu de `?`, et la
  colonne Bloc est alignée à gauche. Chaque lab est rattaché à sa section
  meta.yml à la découverte (`bloc` + nouveau `bloc_name`), donc le récapitulatif
  regroupe par vraie section plutôt que par un `bloc=0` non affecté.

## [0.1.3] - 2026-07-15

### Ajouté

- **labs multi-hôtes** : un mapping `runtime.targets[].roles` (ex.
  `roles: {server: alma-rhcsa-2.lab}`) permet à un lab `vm` d'utiliser plusieurs
  hôtes à la fois. Chaque rôle devient un groupe Ansible `lab_<role>` (en plus de
  `lab_target`, l'hôte primaire où tournent les tests), pour que `setup.yaml` /
  `solution.yaml` / `cleanup.yaml` configurent un serveur et un client sans coder
  de FQDN en dur. Les hôtes de rôle sont validés contre l'inventory provisionné
  au runtime. Rétro-compatible : sans `roles`, lab mono-hôte comme avant.

## [0.1.2] - 2026-07-15

### Ajouté

- **provision** : après `terraform apply`, `dsoxlab provision` attend désormais
  que chaque hôte soit réellement joignable — `sshd` démarré, compte `student`
  créé et cloud-init terminé (`cloud-init status --wait`) — avant de rendre la
  main. Cela supprime l'échec « unreachable » (dark) qui frappait le tout premier
  `dsoxlab run` juste après le provisioning : plus besoin de relancer à la main.
  Un `HostReadyTimeout` retombe sur un avertissement (la VM démarre peut-être
  encore).

### Corrigé

- **version** : `__version__` est désormais lu depuis les métadonnées du paquet
  installé au lieu d'une chaîne codée en dur, pour que `dsoxlab --version` reste
  aligné sur `pyproject.toml` (il était figé à `0.1.0`).

## [0.1.1] - 2026-07-15

### Corrigé

- **incus** : `provision --host X` ne crée plus le disque additionnel des
  *autres* hôtes, et `destroy --host X` supprime désormais le disque additionnel
  de cet hôte. Une variable Terraform `target_hosts` restreint le `for_each` du
  volume extra, et `host_targets` cible le volume propre à l'hôte pour que
  `-target` le nettoie.
  ([#1](https://github.com/stephrobert/dsoxlab/issues/1))

## [0.1.0] - 2026-07-15

Première version publique.

### Ajouté

- CLI basée sur Typer (`dsoxlab`) pilotant des labs pratiques répartis dans
  plusieurs dépôts, via un contrat déclaratif (`meta.yml` + `lab.yaml`).
- Découverte du catalogue qui scanne le `meta.yml` du dépôt courant et chaque
  `lab.yaml`.
- Trois runtimes : `shell`, `incus` (conteneurs) et `kvm` (Terraform +
  libvirt), chacun opt-in et auto-descriptif.
- Templates de provisioning pour Incus, KVM/libvirt et Outscale (HCL Terraform
  et cloud-init).
- Validation au niveau du système via `pytest` + `pytest-testinfra`, incluant
  les tests de persistance après reboot.
- Scoring et suivi de progression persistés dans une base SQLite XDG locale,
  avec des indices à coût variable.
- Validateurs de structure et de métadonnées (`dsoxlab validate-structure`).
- Diagnostics de l'environnement (`dsoxlab doctor [--fix]`).
- Interface utilisateur bilingue (anglais/français) pilotée par `DSOXLAB_LANG`.

[Unreleased]: https://github.com/stephrobert/dsoxlab/compare/v0.1.20...HEAD
[0.1.20]: https://github.com/stephrobert/dsoxlab/compare/v0.1.19...v0.1.20
[0.1.19]: https://github.com/stephrobert/dsoxlab/compare/v0.1.18...v0.1.19
[0.1.18]: https://github.com/stephrobert/dsoxlab/compare/v0.1.16...v0.1.18
[0.1.16]: https://github.com/stephrobert/dsoxlab/compare/v0.1.15...v0.1.16
[0.1.15]: https://github.com/stephrobert/dsoxlab/compare/v0.1.14...v0.1.15
[0.1.14]: https://github.com/stephrobert/dsoxlab/compare/v0.1.13...v0.1.14
[0.1.13]: https://github.com/stephrobert/dsoxlab/compare/v0.1.12...v0.1.13
[0.1.12]: https://github.com/stephrobert/dsoxlab/compare/v0.1.11...v0.1.12
[0.1.11]: https://github.com/stephrobert/dsoxlab/compare/v0.1.10...v0.1.11
[0.1.10]: https://github.com/stephrobert/dsoxlab/compare/v0.1.9...v0.1.10
[0.1.9]: https://github.com/stephrobert/dsoxlab/compare/v0.1.8...v0.1.9
[0.1.8]: https://github.com/stephrobert/dsoxlab/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/stephrobert/dsoxlab/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/stephrobert/dsoxlab/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/stephrobert/dsoxlab/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/stephrobert/dsoxlab/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/stephrobert/dsoxlab/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/stephrobert/dsoxlab/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/stephrobert/dsoxlab/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/stephrobert/dsoxlab/releases/tag/v0.1.0
