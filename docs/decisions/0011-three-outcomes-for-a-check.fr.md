# ADR-0011 : un contrôle a trois issues, et `unknown` a son propre code de sortie

**Statut :** acceptée
**Date :** 2026-08-24 (0.1.84, issues #172 et #176 ; `unknown` développé comme 0.1.73, `--strict` comme 0.1.79)

**Langue :** [English](./0011-three-outcomes-for-a-check.md) · [Français](./0011-three-outcomes-for-a-check.fr.md)

## Contexte

Les contrôles de `doctor` avaient deux issues, `ok` et `failed`. Une sonde qui
ne pouvait pas mesurer devait choisir l'une ou l'autre. Issue #172 : le contrôle
du pool libvirt invoquait `virsh -c qemu:///system` en direct, sans la détection
du préfixe `sudo -n` que `infra/libvirt.py` a construite pour ce cas. Sur toute
machine où l'URI système exige des droits, la sonde échouait à chaque fois, et
cet échec était rendu `ok` : un contrôle vert en permanence, précisément là où
`provision` allait mourir sur « Pool Not Found ». Tout le lot #172 à #179 avait
cette seule forme : un contrôle qui, faute de pouvoir mesurer, concluait que
tout allait bien.

Il existe deux mensonges symétriques. Le premier est le rouge affiché devant une
commande qui fonctionne. Le second, plus sournois, est le vert affiché faute
d'avoir mesuré.

À part, `doctor` sortait en 0 quel que soit l'état de ses contrôles. C'est le
bon choix pour un humain (un diagnostic n'est pas un échec), mais cela rendait
la commande inutilisable comme portail automatisé : un script devait analyser
le JSON pour savoir si quelque chose manquait (issue #176).

## Décision

**Trois issues : `ok`, `failed`, `unknown`.** Un `/proc/meminfo` illisible ou un
pool libvirt muet n'est ni le vert rassurant d'un « ok » non mérité, ni le rouge
accusateur d'une panne non prouvée. Un contrôle en `unknown` n'entre pas dans
`DoctorReport.failing` (il ne prouve aucune panne), et il ne peint jamais le
verdict global en rouge. Mais son jeton dit à un programme comme à un humain que
rien n'est prouvé dans l'autre sens non plus. Il est exposé par `doctor --json`
et rendu « ? non mesuré ».

**`doctor --strict` traduit le diagnostic en code de sortie, avec deux codes
plutôt qu'un**, parce que les deux situations appellent des gestes différents :

| Mode | Code | Quand |
| --- | --- | --- |
| `doctor` | `0` | toujours, inchangé |
| `doctor --strict` | `9` | un contrôle requis a échoué |
| `doctor --strict` | `10` | un contrôle requis n'a pas pu être mesuré |

`9` se répare, `10` se remesure. Un environnement dont une sonde n'a pas abouti
n'est pas validé pour autant : c'est précisément ce qu'une construction d'image
ne doit pas confondre avec un succès. `9` l'emporte quand les deux coexistent :
une certitude est plus forte qu'une ignorance.

Les alternatives écartées : fondre `unknown` dans `failed` (du rouge pour ce
qu'on ignore), le fondre dans `ok` (le défaut de #172), ou un seul code non nul
pour les deux (un script ne distinguerait plus « réparer » de « remesurer »).

## Conséquences

- Le comportement par défaut ne bouge pas, et `--strict` ne change rien
  d'autre : le tableau et le document restent rendus **avant** que le code ne
  tombe, pour qu'un appelant recevant un code non nul puisse encore lire ce qui
  n'allait pas.
- Tout nouveau contrôle doit pouvoir rendre `unknown` quand sa sonde n'aboutit
  pas. « Un contrôle qui n'a pas pu regarder ne conclut jamais au vert » est la
  première règle des [invariants du projet](../design-principles.fr.md).
- Les codes 9 et 10 font partie du contrat des codes de sortie : ils ne changent
  pas de sens.
- `tests/test_doctor_strict.py` tient les codes.

## Ce qui l'inverserait

Rien en vue. Le jeton d'état `choice_required` existe déjà à côté des trois
issues, pour un contrôle qui attend un choix de l'utilisateur (rendu
« à choisir ») : il ne rouvre pas la question, puisqu'il ne conclut lui non plus
ni au vert ni au rouge. Refondre `unknown` dans `ok` ou dans `failed`
réintroduirait le défaut que cette décision existe pour empêcher.
