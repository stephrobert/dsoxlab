# Décisions d'architecture

**Public :** qui s'apprête à changer l'un des choix durables de dsoxlab, ou se
demande pourquoi il a été fait ainsi. Contributeurs et relecteurs d'abord.

**Langue :** [English](./README.md) · [Français](./README.fr.md)

Une ADR (*architecture decision record*, fiche de décision d'architecture) écrit
**une** décision : le contexte qui l'a imposée, ce qui a été décidé, ce que cela
coûte, et ce qui la rendrait fausse. C'est la réponse à « pourquoi ce choix ? »,
rangée là où on la trouve, au lieu d'un long commentaire au milieu du module qui
l'applique.

[Les invariants du projet](../design-principles.fr.md) disent **ce qui est
vrai** et quel test le tient. Ces pages disent **pourquoi on l'a choisi** plutôt
que les autres voies. Les deux se renvoient l'un à l'autre.

---

## Le format

Chaque fiche a la même forme, courte et fixe :

- **Statut** et **Date** (la version qui a porté la décision) ;
- **Contexte** : ce qui a imposé un choix, avec les mesures de l'époque ;
- **Décision** : ce qui a été retenu, et ce qui a été écarté ;
- **Conséquences** : ce que cela coûte et ce que cela apporte ;
- **Ce qui l'inverserait** : les conditions où il faudrait la rouvrir.

Deux règles les gardent utiles :

- **Une mesure garde sa date.** Un chiffre sans sa date est un souvenir, pas un
  fait. Déplacer un raisonnement ici ne le résume jamais.
- **Le code garde une ligne et un renvoi** (`# Voir docs/decisions/0002-…md`).
  Un commentaire qui explique une seule ligne reste où il est ; seul le
  raisonnement d'architecture déménage ici. `tests/test_decisions.py` vérifie
  que chaque fiche a ses sections et sa jumelle anglaise, et que chaque renvoi
  vers `docs/decisions/` dans le dépôt mène à un fichier existant.

Une décision renversée ne s'efface pas : son statut change, et une nouvelle
fiche dit ce qui l'a remplacée.

---

## Les décisions

| N° | Décision | Date |
| --- | --- | --- |
| [0001](./0001-two-runtimes.fr.md) | Deux runtimes, et les providers en dessous | 2026-07-15 |
| [0002](./0002-per-catalog-flock-lock.fr.md) | Un verrou d'écriture par catalogue, un `flock` dont le fichier n'est jamais supprimé | 2026-08-21 |
| [0003](./0003-explicit-ansible-core.fr.md) | `ansible-core` est une dépendance déclarée, malgré ses 100 Mo | 2026-08-19 |
| [0004](./0004-mutable-upstream-images.fr.md) | Les images amont sont mutables, délibérément | 2026-08-24 |
| [0005](./0005-non-blocking-first-boot-packages.fr.md) | Les paquets du premier démarrage ne bloquent pas, mais une fin ratée se dit | 2026-08-24 |
| [0006](./0006-log-in-english.fr.md) | Le journal s'écrit en anglais, l'interface est traduite | 2026-08-24 |
| [0007](./0007-json-output-contract-distinct-from-schema-version.fr.md) | `--json` est un contrat à part, versionné à l'écart de `schema_version` | 2026-08-20 |
| [0008](./0008-explicit-ruff-rule-set.fr.md) | Le jeu de règles Ruff est déclaré en entier, jamais hérité du défaut | 2026-08-20 |
| [0009](./0009-missing-fixture-fails-run.fr.md) | Une fixture qui ne peut pas être copiée fait échouer `run`, tout ou rien | 2026-08-24 |
| [0010](./0010-degraded-lab-when-engine-unreachable.fr.md) | Un lab dont le moteur de conteneurs est injoignable est `degraded`, et dit pourquoi | 2026-08-24 |
| [0011](./0011-three-outcomes-for-a-check.fr.md) | Un contrôle a trois issues, et `unknown` a son propre code de sortie | 2026-08-24 |
| [0012](./0012-optional-hosts-stable-index.fr.md) | Les hôtes optionnels ont un index stable et partent par un `apply` sans `-target` | 2026-11-14 |
| [0013](./0013-refuse-out-of-contract-hosts.fr.md) | Refuser de toucher un state qui porte des hôtes que ce `meta.yml` ne déclare pas | 2026-11-14 |
| [0014](./0014-catalog-table-measured-on-published-repos.fr.md) | La table des catalogues se mesure sur les dépôts publiés, elle ne s'écrit jamais à la main | 2026-11-14 |

Les numéros suivent l'ordre d'écriture des fiches, pas l'ordre des décisions :
les huit premières étaient déjà écrites quelque part dans le code quand ce
répertoire a été créé (issue #203).

## En ajouter une

Copier une fiche existante, prendre le numéro suivant, écrire les deux langues,
ajouter une ligne à cette table et à sa jumelle anglaise, et remplacer le long
commentaire du code par une ligne et un renvoi.
