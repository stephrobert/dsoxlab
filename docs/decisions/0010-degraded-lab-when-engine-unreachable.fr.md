# ADR-0010 : un lab dont le moteur de conteneurs est injoignable est `degraded`, et dit pourquoi

**Statut :** acceptée ; corrige la moitié de la décision d'origine
**Date :** 2026-08-24 (0.1.84, issue #179 ; développé comme 0.1.78)

**Langue :** [English](./0010-degraded-lab-when-engine-unreachable.md) · [Français](./0010-degraded-lab-when-engine-unreachable.fr.md)

## Contexte

`dsoxlab status` calcule l'état d'un lab à un seul endroit
(`services/lab_state.py`, 0.1.68) : `not_started`, `ready`, `in_progress`,
`validated`, et `degraded` quand un service déclaré ne tourne plus. `degraded`
prime sur tout, parce que c'est le seul état qui appelle un geste immédiat. Un
service jamais démarré n'est **pas** dégradé : c'est le cas normal avant le
premier `run`, et confondre les deux ferait virer au rouge tous les labs à
services.

La décision d'origine avait deux moitiés. Un lab qui ne déclare aucun service
ignore Docker entièrement. Et quand `docker_available()` était faux,
`_services_degrades` rendait une liste vide, c'est-à-dire « rien à signaler ».
La seconde moitié rendait « Docker **était** là et son démon est tombé »
indistinguable de « Docker n'a jamais été installé ». Dans le premier cas, le
lab est bel et bien injouable (`run` y échoue déjà explicitement, code 2), et
pourtant `status` annonçait `ready`, voire `validated` lorsqu'une note existait
d'une session précédente.

## Décision

- Un lab qui **déclare** des services et dont le moteur ne répond pas est
  `degraded`, **quelle que soit la note déjà obtenue**. Le moteur est interrogé
  avant la lecture du score, pour que `status` n'annonce jamais « validé » sur
  un lab qu'on ne peut plus jouer.
- Les deux causes se distinguent (`MOTEUR_ABSENT` : docker n'est pas installé ;
  `MOTEUR_MUET` : le client est là, le démon ne répond pas), parce qu'elles
  appellent des gestes opposés : installer un paquet, ou démarrer un démon et
  vérifier que le compte peut lui parler.
- Un lab qui ne déclare **aucun** service continue d'ignorer le moteur, sans
  même payer une sonde. C'était la moitié juste de la décision d'origine : elle
  est gardée et testée pour elle-même. Un catalogue sans service ne doit pas
  payer un appel, ni virer au rouge parce que Docker est absent d'une machine
  qui n'en a pas besoin.

## Conséquences

- `status` et `status --json` portent `degraded` avec un détail traduit qui
  nomme la cause.
- L'ordre des questions dans `calculer` est l'ordre de ce qui prime : une
  dégradation d'abord, la note ensuite, puis le travail, puis la simple
  préparation.
- `tests/test_moteur_injoignable.py` et `tests/test_lab_state.py` tiennent les
  deux moitiés.

## Ce qui l'inverserait

Un moteur de conteneurs autre que Docker, ou plusieurs moteurs. La règle (un
moteur qui ne répond pas rend `degraded` un lab à services, et la cause est
nommée) resterait ; seule la sonde changerait.
