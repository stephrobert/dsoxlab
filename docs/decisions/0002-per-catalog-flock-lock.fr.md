# ADR-0002 : un verrou d'écriture par catalogue, un `flock` dont le fichier n'est jamais supprimé

**Statut :** acceptée
**Date :** 2026-08-21 (0.1.55)

**Langue :** [English](./0002-per-catalog-flock-lock.md) · [Français](./0002-per-catalog-flock-lock.fr.md)

## Contexte

Deux terminaux ouverts, c'est le cas normal chez un apprenant. Rien n'empêchait
deux `dsoxlab` d'écrire en même temps sur le même état, et cet état est
éparpillé :

- `<repo>/.dsoxlab-context.json`, réécrit **en entier** par `config._persist`
  (deux écritures concurrentes : la dernière gagne, la première est perdue sans
  trace) ;
- le state Terraform sous `~/.local/state/dsoxlab/<catalog-id>/terraform/` ;
- l'inventaire et le fragment `ssh_config` régénérés en cache ;
- les conteneurs de `runtime.services`, nommés par catalogue donc partagés.

La base SQLite `<repo>/.dsoxlab.db` était la seule pièce déjà protégée, par
SQLite.

## Décision

**Où se pose le verrou, et pourquoi pas dans le catalogue.** Sous
`~/.local/state/dsoxlab/<catalog-id>/dsoxlab.lock`, c'est-à-dire à la racine du
répertoire d'état de ce catalogue, celui-là même qui porte le state Terraform.
Le poser dans le dépôt de labs aurait paru plus naturel (c'est là que vivent
`.dsoxlab.db` et `.dsoxlab-context.json`). Mais chaque dépôt fournisseur ignore
ces deux fichiers **nommément**, pas par un motif : un troisième fichier
apparaîtrait en untracked chez tous, et il aurait fallu modifier trois dépôts
pour livrer un verrou.

L'identité est `repo.id` quand le `meta.yml` est lisible, sinon le nom du
répertoire suffixé d'une empreinte de son chemin absolu. Prendre `repo.id` en
premier n'est pas un détail : deux clones du même catalogue partagent le
**même** work-dir Terraform, donc doivent partager le verrou. Les sérialiser
inutilement ne coûte rien ; les laisser s'écrire dessus coûte un state corrompu.

**Un verrou périmé, et pourquoi il n'existe pas ici.** Le verrou est un `flock`
(`LOCK_EX | LOCK_NB`). Le noyau le relâche **de lui-même** quand le descripteur
se ferme, y compris si le processus meurt d'un `SIGKILL`, et il ne survit
évidemment pas à un redémarrage. Il n'y a donc aucun verrou à « reprendre » : la
question de la reprise, qui est la vraie difficulté des verrous par
fichier-sentinelle, ne se pose pas.

Ce qui survit, c'est le **fichier**, et le nom de son ancien détenteur. On le
tronque en le relâchant pour qu'il ne raconte pas une invocation terminée, et on
ne le supprime **jamais** : effacer un fichier de verrou est la course classique
où un processus retire sous les pieds d'un autre l'inode qu'il tient déjà.

Le verrou n'est pas hérité par les sous-processus : Python crée ses descripteurs
non héritables (PEP 446), et `exec` les referme. Le sous-shell ouvert par
`dsoxlab run` ne tient donc rien, ce qui est indispensable, puisque l'apprenant
y tape `dsoxlab check`.

**Qui le prend.** Les commandes qui écrivent (liste de la
0.1.55 : `run`, `check`, `submit`,
`provision`, `destroy`, `clean`, `reset`, `use`). Pas celles qui lisent
(`list-labs`, `show`, `scores`, `progress`, `next`, `status`, `doctor`,
`course`, `challenge`, `hint`, `guide`, `validate-structure`, `support`) :
consulter le catalogue pendant qu'un `provision` tourne dans un autre terminal
est un usage normal, pas un conflit.

## Conséquences

- Une seconde invocation concurrente est refusée avec le code de sortie **7**,
  et un message traduit nomme la commande qui tient le verrou, son PID et depuis
  combien de temps elle tourne. Le code 7 est distinct pour qu'un script qui
  enchaîne des commandes puisse réessayer sur celui-ci et abandonner sur les
  autres.
- `run` rend le verrou avant d'ouvrir la session : un verrou tenu « pour toute
  la commande » couvrirait le sous-shell interactif, où l'apprenant tape
  `dsoxlab check`, qui serait alors refusé par sa propre session.
- Sur un système de fichiers qui ne sait pas verrouiller (`ENOLCK`, `ENOSYS`,
  `EOPNOTSUPP`, `EINVAL`), la commande tourne sans protection, avec un
  avertissement au journal, au lieu de refuser de démarrer. Un `~/.local/state`
  monté sur un NFS sans lockd rendrait sinon l'outil inutilisable, un prix bien
  supérieur au risque couvert.
- Un verrou périmé ne se supprime jamais à la main, et la documentation le dit.

## Ce qui l'inverserait

Un état partagé entre plusieurs machines (un backend Terraform ou un état de
catalogue hors du disque local). Un `flock` ne sérialise que les processus d'un
même noyau : le verrou devrait alors se déplacer là où vit l'état partagé.
