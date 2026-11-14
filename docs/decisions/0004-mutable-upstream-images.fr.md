# ADR-0004 : les images amont sont mutables, délibérément

**Statut :** acceptée
**Date :** 2026-08-24 (0.1.84)

**Langue :** [English](./0004-mutable-upstream-images.md) · [Français](./0004-mutable-upstream-images.fr.md)

## Contexte

Les sept URL d'images des templates Terraform packagés pointent des chemins
**mutables** : `latest` chez AlmaLinux, `current` chez Ubuntu et Debian. Aucune
somme de contrôle n'est épinglée.

**Ce que le mutable coûte.** Une image amont peut changer sous nos pieds : une
régression de l'éditeur, un cloud-init qui bouge, un paquet retiré. La
reproductibilité d'un `provision` n'est donc pas garantie dans le temps.

**Ce qu'épingler coûterait, et pourquoi c'est pire ici.** Ubuntu et Debian
republient leurs images cloud toutes les quelques semaines, correctifs de
sécurité inclus. Une somme épinglée devrait être relevée à chaque fois. Non
faite, elle servirait aux apprenants une image de plus en plus périmée, avec ses
vulnérabilités connues. Le durcissement deviendrait alors le vecteur du problème
qu'il prétend traiter.

## Décision

Les chemins mutables sont gardés, et aucune somme n'est épinglée. C'est une
décision, pas un oubli.

Ce qui rend le risque acceptable ici :

- les URL sont en HTTPS, sur les domaines officiels des trois distributions
  (`cloud-images.ubuntu.com`, `cloud.debian.org`, `repo.almalinux.org`) : la
  confiance repose sur TLS et sur l'éditeur, comme pour n'importe quel
  `apt install` ;
- une VM de lab est **jetable** : elle vit le temps d'un exercice, ne porte
  aucune donnée, et `destroy` la retire ;
- elle n'est **pas exposée** : le réseau libvirt est local à la machine de
  l'apprenant.

## Conséquences

- Un `provision` rejoué à quelques mois d'écart peut ne pas démarrer la même
  image. Une régression amont se voit dans les labs, pas dans la CI de dsoxlab.
- Les apprenants reçoivent toujours les derniers correctifs de sécurité de
  l'éditeur, sans que personne ait à relever une somme.

## Ce qui l'inverserait

Si dsoxlab sert un jour des VM au-delà du training (c'est la piste de
`ROADMAP-VM-GENERALISTE`), le calcul s'inverse : une machine qui dure et qui
porte du travail mérite une image épinglée. Le geste, alors : relever le
`SHA256SUMS` publié par chaque distribution à côté de son image, le porter dans
un fichier versionné, et le vérifier après téléchargement. Ce n'est pas fait
aujourd'hui parce que ce n'est pas encore justifié, pas parce que ce serait
difficile.
