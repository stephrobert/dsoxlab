# ADR-0005 : les paquets du premier démarrage ne bloquent pas, mais une fin ratée se dit

**Statut :** acceptée
**Date :** 2026-08-24 (0.1.84, issue #178)

**Langue :** [English](./0005-non-blocking-first-boot-packages.md) · [Français](./0005-non-blocking-first-boot-packages.fr.md)

## Contexte

Chaque template cloud-init pose un bloc `packages:` installé au **premier
démarrage** de la machine : 15 entrées pour AlmaLinux, 14 pour Debian et Ubuntu
(compté le 2026-08-24, recompté identique le 2026-11-14). C'est autant de dépendances réseau, au moment le plus
fragile du cycle de vie d'un lab.

**Ce que ça coûte.** Hors ligne, derrière un proxy d'entreprise, ou sur un
miroir lent, cloud-init finit en `degraded`. Le symptôme était le pire
possible : `wait_for_hosts_ready` jouait
`cloud-init status --wait >/dev/null 2>&1 || true`, si bien que l'état et le
code de retour partaient tous les deux à la poubelle. `provision` annonçait des
hôtes **prêts**, puis les labs échouaient sur des commandes absentes, et rien ne
reliait les deux. C'est aussi ce qui gonfle le premier démarrage dans le budget
d'attente de `wait_for_hosts_ready`.

## Décision

**Écarté : bloquer sur un `degraded`.** cloud-init ne dit pas *quel* paquet a
manqué : il rend un état global. Faire échouer `provision` traiterait `tree`
absent comme `lvm2` absent, alors que le premier n'empêche aucun lab et que le
second en casse toute une famille. Un blocage sans granularité se contourne, et
un garde-fou qu'on contourne ne garde plus rien.

**Écarté pour l'instant : pré-cuire les images.** C'est la vraie réponse : un
paquet déjà présent n'est pas une dépendance réseau. Mais construire et publier
des images est un projet à part entière, avec son propre cycle de vie et sa
propre chaîne d'approvisionnement. Il vit hors de ce dépôt.

**Écarté : déclarer les paquets lab par lab.** Ce serait la solution la plus
juste sur le papier : chaque lab annonce ce dont il a besoin, et `run` le
vérifie. Cela change le contrat `lab.yaml` de la v1, gelé, pour un bénéfice que
les deux mesures ci-dessous obtiennent sans rien casser.

**Retenu : rendre l'échec visible, aux trois moments où il compte.**

1. **Avant.** Le contrôle `egress` de `dsoxlab doctor` joint les miroirs
   d'images déclarés par les templates. Sur un dépôt qui provisionne des VM, il
   est **requis** : une salle sans accès sortant se voit avant de lancer quoi que
   ce soit, pas trois labs plus tard.
2. **Pendant.** `wait_for_hosts_ready` lit désormais le code de retour de
   `cloud-init status --wait` et sa sortie `--long`, au lieu de les jeter dans
   `/dev/null`. Un hôte dont la configuration a mal fini le **dit à l'écran**,
   avec ce que cloud-init a rapporté.
3. **Après.** Le message nomme l'hôte, ce qui rend le geste de reprise
   immédiat : `ssh <hôte>` puis `sudo cloud-init status --long` pour lire le
   détail, et l'installation manuelle du paquet manquant.

Rendre la main reste la bonne décision : ce qui compte pour continuer, c'est que
cloud-init ait **terminé**. Mais terminer mal doit se dire.

## Conséquences

- `provision` n'échoue pas sur un cloud-init `degraded` : il avertit et nomme
  l'hôte.
- `egress` est un contrôle requis de `doctor` sur tout catalogue qui provisionne
  des VM.
- `tests/test_cloud_init_degrade.py` tient la moitié « pendant ».

## Ce qui l'inverserait

Le jour où les images sont pré-cuites, ce bloc `packages:` se vide de tout ce
qui n'est pas propre à la machine, et le contrôle `egress` cesse d'être requis
pour provisionner. C'est le sens de la marche, pas un contournement de plus.
