# Les paquets installés au premier démarrage

Chaque template pose un bloc `packages:` installé au **premier démarrage** de la
machine. Ces paquets **ne bloquent pas** `provision` : cloud-init ne dit pas
quel paquet a manqué, et un blocage sans granularité traiterait `tree` absent
comme `lvm2` absent. En revanche, une fin ratée se dit, à trois moments : le
contrôle `egress` de `dsoxlab doctor` avant, la lecture de
`cloud-init status --wait` et `--long` par `wait_for_hosts_ready` pendant, et
un message qui nomme l'hôte après.

Le raisonnement complet, les trois voies écartées (bloquer, pré-cuire les
images, déclarer les paquets lab par lab) et ce qui changerait la décision :
[ADR-0005](../../../../docs/decisions/0005-non-blocking-first-boot-packages.fr.md)
(`docs/decisions/0005-non-blocking-first-boot-packages.md`).

## Le miroir des paquets Ubuntu

Le template Ubuntu choisit son miroir **depuis la machine**, au démarrage, par
un `bootcmd` : il essaie `archive.ubuntu.com`, puis des miroirs nationaux
officiels hébergés hors de Canonical (`fr`, `de`, `nl`, `ch`), et garde le
premier dont la poche `-security` répond. Les sources des paquets et de
sécurité passent alors sur ce miroir, et `apt: preserve_sources_list: true`
empêche `apt_configure`, qui passe après, de les réécrire. Le miroir retenu est
noté dans `/var/lib/dsoxlab/miroir-apt`.

La raison : `archive.ubuntu.com` et `security.ubuntu.com` sont servis par les
mêmes serveurs et tombent ensemble. Le 2026-11-19, ils ne répondaient plus en
HTTP alors que le ping passait, et aucune machine Ubuntu ne recevait ses
paquets. `gb` et `us` ne figurent pas dans la liste : ils pointent sur ces
mêmes serveurs.
