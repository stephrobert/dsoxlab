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
