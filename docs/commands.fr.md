# Toutes les commandes dsoxlab

**Public :** tout le monde. Cette page est une référence, pas un tutoriel : les
trois guides ([apprenant](./learner.fr.md), [auteur de
catalogue](./catalog-author.fr.md), [formateur](./trainer.fr.md)) disent quand
se servir de quoi.

**Langue :** [English](./commands.md) · [Français](./commands.fr.md)

La table ci-dessous est **produite par la CLI elle-même** via
`scripts/generer-doc.py`, et un test échoue dès qu'elle dérive. L'éditer à la
main ne sert à rien : la prochaine exécution l'écrase.

Pour les options d'une commande, `dsoxlab <commande> --help`. Pour le guide
complet de la plateforme dans le terminal, `dsoxlab fullhelp`.

<!-- BEGIN COMMANDES : généré par scripts/generer-doc.py, ne pas éditer -->

| Commande | Rôle |
| --- | --- |
| `dsoxlab catalog add` | Installe un catalogue par son nom ou par l'URL de son dépôt. |
| `dsoxlab catalog list` | Liste les catalogues connus et ceux qui sont installés. |
| `dsoxlab catalog remove` | Retire un catalogue installé. |
| `dsoxlab catalog update` | Met à jour un catalogue installé (tous, si aucun n'est nommé). |
| `dsoxlab catalog use` | Choisit le catalogue actif, celui qu'on utilise hors de son répertoire. |
| `dsoxlab challenge` | Affiche la mission du challenge (challenge/README.md). |
| `dsoxlab check` | Exécute les tests, calcule le score (hints déduits) et enregistre le résultat. |
| `dsoxlab clean` | Supprime toutes les ressources créées par le lab. |
| `dsoxlab completion install` | Installe l'auto-complétion pour le shell courant (zsh, bash). |
| `dsoxlab completion show` | Imprime le script de complétion sur la sortie standard, sans rien écrire. |
| `dsoxlab course` | Affiche une section du cours, ou le sommaire si aucune section n'est précisée. |
| `dsoxlab demo` | Installe un catalogue de démonstration et joue un premier lab, sans rien cloner ni provisionner. |
| `dsoxlab destroy` | Détruit l'infrastructure du lab (terraform destroy), machines restées hors du state comprises. |
| `dsoxlab doctor` | Diagnostique l'environnement (runtimes, outils, labs détectés). |
| `dsoxlab fullhelp` | Affiche le guide complet de la plateforme (concepts, workflow, commandes). |
| `dsoxlab guide` | Ouvre le guide en ligne du lab dans le navigateur. |
| `dsoxlab hint` | Affiche le prochain indice du challenge (déduit des points au score final). |
| `dsoxlab infra status` | Vérifie la connectivité SSH des hôtes déclarés dans meta.yml, et nomme la cause quand l'un reste muet. |
| `dsoxlab install` | Déprécié : utilise « dsoxlab completion install ». Installe l'auto-complétion. |
| `dsoxlab instructor bootstrap` | Génère la clé SSH du lab (si absente) et vérifie que terraform/ansible-runner sont installés. |
| `dsoxlab list-labs` | Liste tous les labs disponibles (filtrés par contexte actif si défini). |
| `dsoxlab new catalog` | Crée un catalogue vide : meta.yml, labs/, .gitignore, ssh/. |
| `dsoxlab new lab` | Crée un lab conforme, découvert dès le prochain list-labs. |
| `dsoxlab next` | Recommande le prochain lab ou challenge à compléter dans le contexte actif. |
| `dsoxlab progress` | Affiche la progression par bloc (labs complétés, score moyen, challenges et capstones). |
| `dsoxlab provision` | Provisionne l'infrastructure du lab (terraform apply sur le provider courant). |
| `dsoxlab reset` | Remet le lab à l'état initial (clean + redémarrage). |
| `dsoxlab run` | Prépare et démarre l'environnement du lab. |
| `dsoxlab scores` | Affiche l'historique des scores enregistrés. |
| `dsoxlab show` | Affiche le détail et le statut d'un lab. |
| `dsoxlab ssh` | Ouvre une session SSH interactive sur un hôte du lab. |
| `dsoxlab status` | Où en est le lab actif : non commencé, prêt, en cours, validé. |
| `dsoxlab submit` | Soumission finale : lance les tests, enregistre le score, puis tapez 'exit' pour quitter la session. |
| `dsoxlab support` | Produit un rapport de diagnostic anonymisé, à coller dans une issue. |
| `dsoxlab use` | Définit le contexte actif (section et/ou niveau par défaut). Utilisez --reset pour l'effacer. |
| `dsoxlab validate-structure` | Vérifie la structure et les métadonnées de tous les labs. |

<!-- END COMMANDES -->

## Les codes de sortie qui veulent dire quelque chose

| Code | Sens |
| --- | --- |
| `5` | `provision` a trouvé des machines qu'un provisioning en échec a laissées hors du state Terraform. Le message nomme la commande qui les retire |
| `6` | `destroy` n'a pas pu retirer ces machines |
| `7` | Une autre commande dsoxlab tient déjà le verrou d'écriture de ce catalogue. Le message la nomme |
| `130` | La commande a été interrompue (Ctrl-C), et dit comment reprendre |

Chacun existe pour la même raison : un échec qui ne se dit pas est pire qu'un
échec. `destroy` sortait en succès en laissant des machines debout.

## Options globales

`--verbose` / `-v` (répétable), `--debug` (équivalent à `-vv`) et `--version`,
toutes avant la commande. Quelle que soit la verbosité, le journal complet est
écrit dans `~/.local/state/dsoxlab/dsoxlab.log`, et jamais sur la sortie
standard : `--json` reste lisible par un programme même en mode bavard.
