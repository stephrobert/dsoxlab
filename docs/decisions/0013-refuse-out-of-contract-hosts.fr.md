# ADR-0013 : refuser de toucher un state qui porte des hôtes que ce `meta.yml` ne déclare pas

**Statut :** acceptée
**Date :** 2026-11-14 (0.9.1, issue #357)

**Langue :** [English](./0013-refuse-out-of-contract-hosts.md) · [Français](./0013-refuse-out-of-contract-hosts.fr.md)

## Contexte

Le state Terraform est nommé par `repo.id`, pas par chemin
(`~/.local/state/dsoxlab/<catalog-id>/terraform/<provider>/`). Deux checkouts
d'un même dépôt (deux clones, deux worktrees git) partagent donc le même state.
Quand l'un déclare un hôte que l'autre ignore, un `apply` sans `-target` lancé
par le second sort cet hôte du `for_each`, et Terraform le **détruit**. Le
checkout qui déclarait le moins d'hôtes détruisait ainsi les machines de l'autre
à son premier `provision`, sans un mot, VM en cours de lab comprise.

## Décision

`provision` (avec ou sans `--host`) et `destroy --optional-hosts` nomment chaque
machine du state qui n'est ni un hôte commun ni un hôte optionnel de ce
`meta.yml`, et **refusent** avec le code de sortie **12**
(`HOTES_HORS_CONTRAT`). `provision --prune` les détruit volontairement, en les
nommant. `destroy` les nomme avant la question, même avec `--yes`.

Le refus a été préféré aux deux autres voies :

- **Les garder en silence dans `var.hosts`** est impossible : ce `meta.yml`
  ignore leur taille et leur distribution.
- **Les détruire après un avertissement** perd quand même une VM qu'une autre
  session utilise peut-être en plein lab.

Un refus coûte une commande ; une VM perdue coûte le travail de l'autre.

Le refus vaut **même avec `--host`**, qui ne les détruirait pas : l'écart est
là, et le `provision` suivant sans `--host` les emporterait. Mieux vaut le dire
au premier contact, avant d'avoir monté quoi que ce soit.

## Conséquences

- Un nouveau code de sortie, 12, rejoint le contrat des
  [codes de sortie](../exit-codes.fr.md).
- Un state illisible rend une liste vide : Terraform échouera de lui-même sur ce
  même fichier, avant de planifier quoi que ce soit.
- Le même garde-fou protège le retrait des hôtes optionnels
  ([ADR-0012](./0012-optional-hosts-stable-index.fr.md)), puisque ce retrait
  passe lui aussi par un `apply` sans `-target`.

## Ce qui l'inverserait

Un state nommé par checkout (par chemin) plutôt que par `repo.id`. Deux
checkouts ne partageraient alors plus aucune machine, mais ils cesseraient aussi
de partager le verrou et le work-dir sur lesquels repose
l'[ADR-0002](./0002-per-catalog-flock-lock.fr.md). C'est donc une décision plus
large que celle-ci.
