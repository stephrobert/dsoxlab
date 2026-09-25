# Codes de sortie

**Public :** vous écrivez quelque chose qui *appelle* dsoxlab : une étape de
CI, un script de construction, un enrobage. Un code est ce sur quoi vous
branchez quand il n'y a aucun document à lire.

**Langue :** [English](./exit-codes.md) · [Français](./exit-codes.fr.md)

Un code de sortie est le contrat le plus dur que cet outil expose. Un document
JSON peut gagner un champ ; une phrase traduite peut changer de mot. Un code,
une fois qu'un script le lit, ne peut plus bouger sans casser cet appelant en
silence — et sans un mot, puisqu'un code ne porte aucun message.

Ils vivent donc tous au même endroit, `src/dsoxlab/exit_codes.py`, dans un
énuméré `ExitCode`. Deux tests tiennent le fichier honnête : aucune valeur ne
peut servir deux fois, et chaque code doit figurer sur cette page **et** sur sa
version anglaise. Un code non documenté est un contrat que personne ne peut lire.

## La table

| Code | Nom | Ce qu'il veut dire | Le geste qu'il appelle |
| --- | --- | --- | --- |
| `0` | — | la commande a fait ce qu'on lui demandait | rien |
| `1` | `ECHEC` | la commande a tourné, et la réponse est non : identifiant de lab inconnu, test rouge, hôte qui ne répond pas, aucun contexte actif | lire le message ; la réponse porte sur ton travail, pas sur ton installation |
| `2` | `IMPOSSIBLE` | la commande n'a pas pu s'exécuter : infrastructure non provisionnée, provider non packagé, fixture déclarée absente du disque, point de reprise exigé impossible, fichier attendu introuvable | **préparer** quelque chose — ce n'est pas une faute dans ton travail |
| `3` | `TERRAFORM_ABSENT` | Terraform n'est pas installé, donc `provision` et `destroy` n'ont aucun moyen d'agir | l'installer ; un pipeline peut l'automatiser |
| `4` | `TERRAFORM_ECHOUE` | Terraform a répondu, et il a échoué | lire sa sortie ; dsoxlab nomme les causes qu'il reconnaît, comme un pool de stockage plein ou absent |
| `5` | `ORPHELINS` | un `provision` a laissé des domaines orphelins — définis sur l'hyperviseur, absents du state — ou en a trouvé avant de commencer | jouer la ligne `virsh undefine` que le message affiche |
| `6` | `ORPHELINS_NON_RETIRES` | un `destroy` n'a pas pu retirer ces orphelins | les retirer à la main, puis rejouer `destroy` |
| `7` | `VERROU` | une autre commande dsoxlab tient déjà le verrou de ce dépôt | **réessayer** — c'est le seul code où réessayer est juste. Le message nomme le processus qui le détient |
| `8` | `HOTES_INJOIGNABLES` | un `provision` a rendu la main sans que tous les hôtes ciblés répondent | `dsoxlab status` dit lequel et pourquoi ; souvent plus de temps ou plus de vCPU |
| `9` | `DOCTOR_REQUIS_KO` | `doctor --strict` : un contrôle **requis** a échoué, c'est établi | **réparer** ce que le tableau nomme |
| `10` | `DOCTOR_INDETERMINE` | `doctor --strict` : un contrôle requis n'a pas pu être mesuré | **remesurer** — rien n'est conclu, donc rien n'est validé |
| `127` | `EXECUTABLE_INTROUVABLE` | un exécutable attendu n'est pas dans le `PATH` | l'installer. 127 est le code que le shell rend lui-même ici, donc un script sait déjà le lire |
| `130` | `INTERROMPU` | `128 + SIGINT`, un Ctrl-C | le message donne le geste de reprise |

## Lire la table comme un script

Trois distinctions sont délibérées, et ce sont elles qui justifient cette page.

**`7` est le seul code sur lequel réessayer.** Sa cause est temporaire par
nature : une autre invocation écrit. Tous les autres décrivent un état qui ne
changera pas de lui-même.

**`9` et `10` sont séparés parce que les gestes diffèrent.** Le premier se
répare, le second se remesure. Un environnement dont une sonde n'a pas abouti
n'est pas validé pour autant, et une construction automatisée ne doit pas
confondre cela avec un succès. Quand les deux coexistent, `9` l'emporte : une
certitude est plus forte qu'une ignorance.

**`1` et `2` séparent « non » de « impossible ».** Un `check` sur un lab qui
échoue sort en `1` : l'outil a travaillé, la réponse est négative. Un `run` sur
un lab dont une fixture déclarée manque sort en `2` : rien n'a été mesuré, parce
que le lab n'a même pas pu démarrer.

## Là où les codes ne sont pas

`doctor` sans `--strict` sort en **0 quoi qu'il trouve**, délibérément : pour un
humain, un diagnostic n'est pas un échec. Le verdict vit dans le champ `ok` de
`--json`. C'est `--strict`, et non `--json`, qui traduit le diagnostic en `9` ou
`10`.

`--json` ne change jamais un verdict non plus. Une commande qui sort en `1`
affiche quand même son document d'abord, pour qu'un appelant recevant un code non
nul puisse lire ce qui n'allait pas. Voir
[la sortie machine](./machine-output.fr.md).

## Ajouter un code

1. Ajouter le membre à `ExitCode`, avec un commentaire disant ce qu'il signifie.
2. Ajouter une ligne ici **et** dans `exit-codes.md`.
3. Le lever par `typer.Exit(ExitCode.TON_CODE)`, jamais par un nombre nu.

`tests/test_codes_de_sortie.py` échoue si l'étape 2 est oubliée, et si un
littéral au-delà de `4` est passé à `typer.Exit` dans `src/dsoxlab/`.
