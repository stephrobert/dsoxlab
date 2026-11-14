# ADR-0007 : `--json` est un contrat à part, versionné à l'écart de `schema_version`

**Statut :** acceptée
**Date :** 2026-08-20 (0.1.46, quand `schema_version` est arrivé à côté du `SCHEMA` existant)

**Langue :** [English](./0007-json-output-contract-distinct-from-schema-version.md) · [Français](./0007-json-output-contract-distinct-from-schema-version.fr.md)

## Contexte

Toute intégration (extension d'éditeur, tableau de bord web, script de suivi) a
besoin de lire l'état du catalogue et de la progression. Sans sortie machine,
elle devrait analyser la sortie Rich : des tableaux dont la largeur dépend du
terminal, des couleurs, des retours à la ligne. Le moindre ajustement
d'affichage casserait l'intégration, et l'affichage est fait pour bouger.

dsoxlab expose donc deux interfaces publiques, dans des sens opposés :

- `meta.yml` et `lab.yaml`, ce que dsoxlab **lit** d'un catalogue. Sans numéro
  de version, un champ qui change de sens ne pouvait être ni annoncé, ni
  détecté, ni refusé : il se manifestait par un lab qui disparaît du catalogue,
  sans message. C'est le symptôme le plus coûteux à diagnostiquer de tout le
  projet.
- les documents `--json`, ce que dsoxlab **écrit** pour d'autres programmes.

## Décision

**`--json` est un contrat**, tenu par trois règles (`reporting/machine.py`) :

1. **Rien d'autre que du JSON sur la sortie standard.** En mode machine, les
   messages d'ambiance (contexte actif, astuces, avis de version) partent sur la
   sortie d'erreur : un « ℹ » en tête de flux rendrait le document illisible
   pour l'appelant.
2. **Le format est versionné.** Chaque document porte un `schema`, pour qu'un
   consommateur sache s'il parle la même langue avant de lire le reste.
3. **Un verdict se lit sans traduire.** Un contrôle porte une **clé** stable et
   un **état** en jeton (`ok`, `failed`…), et seulement *ensuite* un libellé
   traduit. Recopier le texte affiché dans un champ rendrait l'interface
   inutilisable tout en paraissant complète : personne ne peut savoir si c'est
   vert ou rouge sans analyser du français ou de l'anglais.

Le mode machine ne change **jamais** le verdict ni le code de retour d'une
commande : il en change la forme.

**`reporting/machine.py: SCHEMA` et `schema_version` sont deux contrats.**
`SCHEMA` versionne ce que dsoxlab écrit ; `schema_version` versionne ce qu'il
lit. Deux contrats, deux publics, deux rythmes d'évolution : ils ne doivent
jamais être couplés, ni incrémentés ensemble par réflexe. `SCHEMA` évolue aussi
indépendamment de la version du paquet.

L'alternative écartée : un seul numéro de version pour « le format dsoxlab ».
Un auteur de catalogue et un auteur de tableau de bord seraient alors prévenus
de changements qui ne les concernent pas, et une incrémentation faite pour l'un
ressemblerait à une rupture pour l'autre.

## Conséquences

- Ajouter un champ laisse `schema` où il est. Changer le sens d'un champ, le
  renommer, le retirer, ou changer le sens d'un jeton `state` ou `kind`
  l'incrémente.
- Le texte traduit (`label`, `message`, `detail`, `notes`) et la sortie brute
  d'un autre outil (`check.output`) ne font explicitement **pas** partie du
  contrat.
- Le document de preuve porte un nom différent, à dessein :
  `"schema": "dsoxlab-evidence-v1"`, une chaîne, parce que ce document quitte
  dsoxlab, et que `{"schema": 1}` ne dit pas de quoi c'est le schéma 1.
- Côté entrée, la valeur par défaut d'un `schema_version` absent **ne suit
  pas** `SUPPORTED_SCHEMA_VERSION` : le jour où la v2 existera, un fichier muet
  restera un fichier v1, écrit avant que la version existe.
- [La sortie machine](../machine-output.fr.md) et
  [le contrat v1](../contract-v1.fr.md) publient les deux règles ;
  `tests/test_json_output.py` et `tests/test_schema_version.py` les tiennent.

## Ce qui l'inverserait

Rien de prévisible ne fusionne les deux : leurs lecteurs sont des personnes
différentes. Ce qui pourrait changer, c'est la *forme* du contrat de sortie (un
autre transport que la sortie standard, par exemple), qui recevrait une nouvelle
valeur de `schema`, pas un numéro partagé.
