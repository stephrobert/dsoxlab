# Premiers pas avec dsoxlab

Ce lab ne parle ni de Linux, ni de Terraform, ni d'Ansible. **Son sujet est
dsoxlab lui-même** : la boucle que vous répéterez sur tous les autres labs,
quel que soit le catalogue.

## La boucle

Un lab passe toujours par les cinq mêmes gestes.

| Geste | Ce qu'il fait |
|---|---|
| `dsoxlab run <id>` | Prépare le lab et vous dépose dans son répertoire de travail |
| `dsoxlab course <id>` | Affiche le cours, cette page même |
| `dsoxlab challenge <id>` | Affiche la mission : ce que vous devez produire |
| `dsoxlab hint <id>` | Révèle un indice de plus, à un coût sur votre score |
| `dsoxlab check <id>` | Joue les tests et enregistre le score |

Deux d'entre eux méritent un mot.

**`check` lit l'état que vous avez produit, jamais les commandes que vous avez
tapées.** Il n'y a donc pas d'historique à satisfaire ni de formulation exacte à
deviner : les tests regardent les fichiers. C'est ce qui vous laisse arriver au
résultat comme vous l'entendez.

**`hint` coûte des points, et le dit avant de les dépenser.** Ce n'est pas une
punition : un indice pris sciemment coûte moins cher qu'une heure perdue.
`dsoxlab scores` montre ce qu'un lab a finalement rapporté.

## Où vous travaillez

`dsoxlab run` vous place dans le répertoire de travail du lab. Tout ce que vous
y créez est ce qui sera validé. Rien d'autre sur votre machine n'est touché.

## Le mot du cours

La mission ci-dessous vous demande un mot qui figure ici, et uniquement ici.
Le voici :

    catalogue

Lisez maintenant la mission : `dsoxlab challenge premiers-pas`.
