# ADR-0006 : le journal s'écrit en anglais, l'interface est traduite

**Statut :** acceptée
**Date :** 2026-08-24 (0.1.84, issue #140 ; développé comme 0.1.83)

**Langue :** [English](./0006-log-in-english.md) · [Français](./0006-log-in-english.fr.md)

## Contexte

Tout texte affiché à l'utilisateur passe par `_()`, en anglais et en français.
Le journal (`~/.local/state/dsoxlab/dsoxlab.log`) est autre chose : c'est le
fichier que `dsoxlab support` collecte et qu'un utilisateur colle dans un
rapport de bug.

Le journal mélangeait le français et l'anglais. Ce n'est pas un détail
d'esthétique. Mesuré avant d'être corrigé : **41 messages français contre 4
anglais**.

Les appels `logger.*` sont **délibérément exclus** du garde-fou i18n
(`tests/test_i18n_coverage.py`), et cette exclusion tient toujours : un message
de journal n'est pas un texte d'interface, il ne passe pas par `_()`, et le
traduire à l'exécution rendrait deux rapports incomparables selon la locale de
qui les produit. Mais l'exclusion justifiait de ne pas le **traduire**, pas de
le laisser incohérent.

## Décision

Le journal parle une seule langue, et c'est l'**anglais**. L'interface reste
traduite.

L'anglais l'emporte pour trois raisons, dans l'ordre de poids :

1. un message de journal se cherche **mot pour mot** dans un moteur de
   recherche ;
2. il se compare entre deux machines aux locales différentes ;
3. il est lu par quelqu'un qui **diagnostique**, pas par quelqu'un qui apprend,
   et il voisine déjà avec les sorties de terraform, ansible et virsh, qui sont
   anglaises.

Les alternatives écartées : traduire le journal à l'exécution (deux rapports
incomparables), ou laisser chaque message dans la langue de son auteur (l'état
qui a été mesuré).

## Conséquences

- `tests/test_journal_en_anglais.py` tient la règle. Sans ce test, elle se
  déferait ligne par ligne, ce qui est exactement ce qui s'est passé pour
  l'interface avant que son propre garde-fou n'existe.
- Le détecteur s'appuie sur une courte liste de mots qui n'existent qu'en
  français, pour produire **zéro** faux positif, au prix de laisser passer une
  partie du français. C'est un garde-fou, pas un correcteur.
- La règle est écrite là où un contributeur la rencontre : le gabarit de PR, et
  [les invariants du projet](../design-principles.fr.md).
- Le même raisonnement a ensuite mis en anglais le document de preuve publié
  (`docs/machine-output.fr.md`) : ce qui est publié ne suit pas la locale de qui
  l'a produit.

## Ce qui l'inverserait

Un journal qui cesse d'être une pièce de diagnostic partagée hors de la machine
(par exemple si `support` ne le collectait plus). Tant qu'il se colle dans des
issues et se compare entre machines, une seule langue vaut mieux que deux.
