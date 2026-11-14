# ADR-0014 : la table des catalogues se mesure sur les dépôts publiés, elle ne s'écrit jamais à la main

**Statut :** acceptée
**Date :** 2026-11-14 (0.9.2)

**Langue :** [English](./0014-catalog-table-measured-on-published-repos.md) · [Français](./0014-catalog-table-measured-on-published-repos.fr.md)

## Contexte

`src/dsoxlab/templates/catalogues.yml` est ce que `dsoxlab catalog list` montre
à un apprenant, et la table du README en était tirée. Elle s'est périmée trois
fois : le 2026-10-10 elle annonçait trois catalogues quand six existaient, le
2026-10-17 six quand douze existaient, et le 2026-11-14 le README annonçait 414
labs dans 12 catalogues, dont 64 pour Kubernetes, quand les dépôts publiés
portaient 699 labs dans 18 catalogues, dont 111 pour Kubernetes. Sept catalogues
publics manquaient au manifeste, si bien que `catalog list` ne les proposait
jamais (publier-service, proxmox, gitlab-ci, bdd, certificats, artefacts et
mlops).

La cause était la même à chaque fois : un chiffre écrit à la main, et un
contrôle qui ne regardait que le disque local, et seulement quand le manifeste
lui-même changeait.

## Décision

- Le manifeste ne porte plus **aucun chiffre** : seulement l'identité d'un
  catalogue (id, dépôt, descriptions).
- `scripts/gen-catalogues.py` compte les `labs/**/lab.yaml` de la branche par
  défaut de chaque dépôt **publié**, celui qu'un apprenant clone, par l'API
  GitHub, et réécrit la table des deux README.
- Il refuse un dépôt privé ou archivé inscrit au manifeste, et nomme tout dépôt
  public des mêmes propriétaires qui porte des labs sans y être inscrit.
- Un contrôle qui n'a pas pu regarder ne conclut jamais au vert : sans réseau,
  ou sur un arbre git tronqué, il sort en **2** au lieu de conclure.
- Le hook de pre-push le joue à **chaque** push, et pas seulement quand le
  manifeste change, puisque ce sont les catalogues qui bougent ; la CI joue le
  même hook avec le jeton du job, qui ne sert qu'à lever la limite de 60
  requêtes par heure des appels anonymes.

L'alternative écartée : garder les chiffres dans le manifeste et les comparer
au disque local. C'est le contrôle qui a laissé la table dériver trois fois,
parce que le disque local n'est pas ce qu'un apprenant clone.

## Conséquences

- Un push a besoin d'un accès réseau à GitHub ; hors ligne, le hook sort en 2
  plutôt que d'approuver.
- Un catalogue qui ne publie encore aucun lab (certificats, mesuré le
  2026-11-14) reste au manifeste et hors de la table.
- Le jeton ne sert qu'à lire des dépôts **publics** : un dépôt privé n'est
  jamais proposé, même si le jeton le voit.

## Ce qui l'inverserait

Des catalogues qui ne seraient plus publiés sur GitHub, ou un manifeste qui
cesserait d'être ce que lit `catalog list`. La mesure se déplacerait alors là où
les apprenants clonent ; la règle (aucun chiffre écrit à la main) resterait.
