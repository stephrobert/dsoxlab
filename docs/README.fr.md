# Documentation de dsoxlab

**Public :** cette page est un aiguillage, et n'appartient à personne en
particulier. Toutes les autres nomment leur lecteur dès leurs premières lignes,
parce qu'un document qui répond à trois publics à la fois n'en sert aucun.

**Langue :** [English](./README.md) · [Français](./README.fr.md)

`dsoxlab` transforme des exercices déclaratifs en environnements de lab
reproductibles, exécutables et vérifiables. Le [README du dépôt](../README.fr.md)
dit ce que c'est en trente secondes ; ces pages disent comment cela fonctionne.

---

## Les trois portes

| Page | Pour vous si… |
| --- | --- |
| **[Pour l'apprenant](./learner.fr.md)** | Vous installez dsoxlab, jouez des labs et voulez comprendre votre note |
| **[Pour l'auteur de catalogue](./catalog-author.fr.md)** | Vous écrivez des labs dans votre propre dépôt |
| **[Pour le formateur](./trainer.fr.md)** | Vous montez les machines et les providers dont les labs ont besoin |

## Références

| Page | Contenu |
| --- | --- |
| [Le contrat v1](./contract-v1.fr.md) | `meta.yml` et `lab.yaml`, champ par champ, avec ce que la v1 garantit |
| [Référence des commandes](./commands.fr.md) | Toutes les commandes, produites par la CLI elle-même |
| [Où dsoxlab écrit](./files.fr.md) | Chaque fichier que dsoxlab crée, et les variables d'environnement qu'il lit |
| [La sortie machine](./machine-output.fr.md) | Ce que rend `--json`, champ par champ, et ce sur quoi on peut bâtir |
| [La marque](./brand.fr.md) | Nom, logo et conditions d'usage |

Les contributeurs ont [CONTRIBUTING.fr.md](../CONTRIBUTING.fr.md) : installation,
contrôles de qualité, carte de l'architecture et conventions de commit.

---

## Deux habitudes qui valent d'être reprises

**Rien n'est écrit deux fois ici.** La table des commandes est produite par la
CLI, et les emplacements de fichiers sont confrontés au code par
`tests/test_documentation_synchrone.py`, qui les dérive en appelant les mêmes
fonctions que la CLI appelle. Les deux contrôles existent parce que les deux
avaient déjà dérivé : la table décrivait un `cleanup.sh` que le contrat
interdit, et la section « Persistence » désignait une base de données qui n'a
jamais existé.

**Ces pages sont du Markdown dans le dépôt, délibérément.** Aucun générateur de
site n'est installé ici : la documentation se lit là où elle s'écrit, se
versionne avec le code qu'elle décrit, et se relit dans la même pull request.
