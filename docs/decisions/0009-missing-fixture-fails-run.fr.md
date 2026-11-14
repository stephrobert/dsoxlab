# ADR-0009 : une fixture qui ne peut pas être copiée fait échouer `run`, tout ou rien

**Statut :** acceptée ; renverse une décision antérieure
**Date :** 2026-08-24 (0.1.84, issue #177 ; développé comme 0.1.76)

**Langue :** [English](./0009-missing-fixture-fails-run.md) · [Français](./0009-missing-fixture-fails-run.fr.md)

## Contexte

`ShellRuntime` itère sur `runtime.fixtures`, **pas** sur le contenu du
répertoire `fixtures/`. Les deux peuvent donc diverger, et les deux écarts
possibles produisaient le même dégât, sans un mot :

- une fixture *déclarée mais absente du disque* partait en `logger.warning` ;
- une fixture *présente mais non déclarée* n'était jamais lue.

Dans les deux cas, `dsoxlab run` créait un `challenge/work` vide, sortait en
**0**, et l'apprenant n'avait rien à faire. C'est le défaut qui a rendu **7 labs
de `terraform-training` injouables le 2026-07-28**, tous marqués faits. Il se
cachait d'autant mieux que les outils de vérification des corrigés
(`scripts/verify-solutions.py` et le `conftest.py` de mode formateur des
catalogues) copient, eux, le répertoire entier : la solution passait au vert
pendant que le parcours apprenant était cassé.

Ce comportement venait d'une décision antérieure : une faute de frappe dans une
entrée ne devait pas priver l'apprenant de tout son workdir.

## Décision

La décision antérieure est **renversée**. Une fixture qui ne peut pas être
copiée fait échouer `run`, qui sort en code **2** (`FixtureError`).

C'est le fichier manquant qui prive l'apprenant, pas le refus : une erreur
d'auteur n'est pas quelque chose qu'il peut réparer, et un exercice amputé
échoue au `check` pour des raisons qu'il cherchera dans son propre travail.

La validation précède **toute copie** : c'est tout ou rien, parce qu'un workdir
à moitié rempli a l'air de marcher. Toutes les fixtures fautives sont nommées
d'un coup, pour que l'auteur corrige en une passe plutôt qu'en autant de `run`
qu'il a de fixtures. Un chemin absolu ou contenant `..` est refusé de la même
façon : une fixture ne sort jamais du workdir.

## Conséquences

- `validate-structure` compare `fixtures/` à la déclaration dans les deux sens
  (déclarée mais absente, présente mais non déclarée, chemin qui sort du
  workdir), dans le lot par défaut hors ligne. La CI d'un catalogue attrape donc
  la faute avant un apprenant.
- Les fichiers cachés (`.gitkeep`) en sont exemptés : les signaler serait un
  faux positif que chaque auteur apprendrait à ignorer, et un contrôle qu'on
  apprend à ignorer ne contrôle plus rien.
- Les 7 labs de `terraform-training` ont été réparés depuis, et les trois
  catalogues mesurés étaient indemnes le 2026-08-24.
- `tests/test_fixtures_declarees.py` et `tests/test_shell_fixtures.py` tiennent
  la règle.

## Ce qui l'inverserait

Une fixture réellement facultative, que le contrat v1 n'a aucun moyen de dire.
Il faudrait alors un nouveau champ facultatif qui la marque comme telle, pas un
retour à l'oubli silencieux.
