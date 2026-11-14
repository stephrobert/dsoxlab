# ADR-0003 : `ansible-core` est une dépendance déclarée, malgré ses 100 Mo

**Statut :** acceptée
**Date :** 2026-08-19 (0.1.42)

**Langue :** [English](./0003-explicit-ansible-core.md) · [Français](./0003-explicit-ansible-core.fr.md)

## Contexte

`ansible-runner` pilote `ansible-core` par programme (l'API officielle de Red
Hat, utilisée par AAP et ansible-navigator). dsoxlab s'en sert pour jouer les
`setup.yaml` et `cleanup.yaml` des labs `vm`.

Le commentaire du `pyproject.toml` a longtemps affirmé le contraire du vrai :
`ansible-runner` ne tire **pas** `ansible-core` en transitif. Mesuré sur une
machine neuve, le tool installé pesait 18 Mo et son `bin/` ne contenait ni
`ansible` ni `ansible-playbook`. Conséquence : tout `dsoxlab run` sur un lab
`vm` sortait en `rc=127`, code shell de « commande introuvable », que rien ne
traduisait.

Le contrôle de `doctor` aggravait le cas : il vérifiait seulement que le module
`ansible_runner` s'importe. Il rendait donc OK sur une machine où aucun playbook
ne pouvait tourner.

Un audit joué sur une VM Ubuntu 24.04 neuve, dans la même version, a mesuré
**six étapes non documentées** entre un `dsoxlab doctor` vert et le premier lab
`vm` jouable. Celle-ci en faisait partie.

## Décision

`ansible-core` est déclaré explicitement dans `[project] dependencies`, à côté
d'`ansible-runner`.

L'alternative écartée : le laisser dehors et documenter une installation
manuelle pour les catalogues `vm`. Cela donne un outil qui ne marche qu'après une
commande que rien ne documente, découverte par un `rc=127` brut.

## Conséquences

- `ansible-core` pèse environ **100 Mo**, y compris pour un catalogue
  entièrement `shell` qui ne s'en servira jamais. C'est le prix d'un outil qui
  marche à l'installation plutôt qu'après une commande que rien ne documente.
- Le contrôle de `doctor` vérifie désormais les deux moitiés (le module et le
  binaire), et son message nomme `ansible-core` au lieu de renvoyer
  l'utilisateur réinstaller ce qu'il a déjà.
- `tests/test_ansible_availability.py` lit le `pyproject.toml` plutôt que
  l'environnement : la déclaration ne peut pas disparaître en silence.

## Ce qui l'inverserait

Qu'`ansible-runner` déclare lui-même `ansible-core`, ou que dsoxlab cesse de
jouer des playbooks Ansible pour les labs `vm`. En faire un extra facultatif ne
vaudrait la peine que si les installations purement `shell` devenaient un
problème mesuré. Jusque-là, les 100 Mo sont le coût accepté.
