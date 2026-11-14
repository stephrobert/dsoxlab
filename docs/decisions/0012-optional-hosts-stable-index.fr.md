# ADR-0012 : les hôtes optionnels ont un index stable et partent par un `apply` sans `-target`

**Statut :** acceptée
**Date :** 2026-11-14 (0.9.0, issue #365)

**Langue :** [English](./0012-optional-hosts-stable-index.md) · [Français](./0012-optional-hosts-stable-index.fr.md)

## Contexte

Deux labs de haute disponibilité du catalogue Kubernetes demandent deux plans de
contrôle et un répartiteur de charge de plus, environ **5,6 Go**. Ajoutés à
`infra.hosts`, ils auraient fait dépasser **16 Go** à tous les apprenants de ce
catalogue, pour deux labs. D'où `infra.optional_hosts` dans le `meta.yml` : des
hôtes déclarés une fois, montés par les seuls labs qui les citent.

Deux mécanismes des templates packagés ne résistaient pas à des hôtes qui vont
et viennent :

- **Des adresses tirées du rang dans `var.hosts`.** Monter un hôte optionnel
  sans son voisin aurait déplacé une adresse d'un provisionnement au suivant. Or
  le provider libvirt échoue sur **toute** mise à jour en place d'un domaine en
  marche : mesuré en 0.8.1 (le 2026-11-09) avec `dmacvicar/libvirt` **0.9.7**,
  son `.id` passait de 21 à 22 entre l'envoi et la relecture (« Provider
  produced inconsistent result after apply »). Un banc sur domaine arrêté ne le
  voit pas.
- **`terraform destroy -target` pour retirer un hôte.** Terraform note ses
  dépendances au niveau de la ressource, pas de l'instance. Mesuré sur un parc
  de trois hôtes (0.1.24, le 2026-07-23) : demander un seul hôte planifiait
  **7** ressources à détruire, et non 4.

## Décision

**L'adresse d'un hôte dérive d'un index explicite**, `hosts[].index`, sa
position dans la liste **complète** du `meta.yml`, hôtes communs d'abord, jamais
sa position dans la liste réellement envoyée à Terraform. Les trois templates
packagés (kvm, incus, outscale) le lisent.

**Les hôtes optionnels partent par un `apply` sans `-target`**, dont
`var.hosts` ne les porte plus : ils sortent du `for_each`, et Terraform planifie
la destruction de **leurs seules instances**. Pas de `destroy -target`, qui
emporte les autres machines.

Le revers est assumé : cet `apply` réaligne aussi le reste sur la configuration,
comme le ferait un `provision`. Les hôtes communs ne sont jamais détruits par
lui, puisqu'ils restent dans `var.hosts`.

**Un `provision` garde les hôtes optionnels déjà au state.** Un `provision` du
catalogue ne doit pas détruire les machines qu'un lab a montées, et c'est ce
qu'il ferait en les retirant de `var.hosts`. Un state illisible fait retenir
tous les hôtes optionnels : au pire on en crée un de trop, alors que les écarter
en détruirait.

## Conséquences

- Pour un catalogue sans hôte optionnel, l'index vaut l'ancien rang : aucune
  adresse ne bouge. Mesuré le 2026-11-14 sur le catalogue Kubernetes (trois
  machines KVM en marche) : un `terraform plan` sur une copie de son state, avec
  les templates et les variables de la 0.9.0, n'a montré aucun changement.
- Mesuré sur un hyperviseur libvirt 10 réel le 2026-11-14 (un hôte commun, deux
  optionnels) : le `run` d'un lab qui cite le second hôte optionnel l'a monté en
  `.13` (sa position), et non en `.12` (son rang parmi les hôtes montés) ; un
  second `provision` a laissé un plan sans changement et les deux identifiants
  de domaine libvirt intacts ; `destroy --optional-hosts` l'a retiré seul. Le
  même parcours sur Incus 7.2, le même jour, a donné le même résultat une fois
  corrigée la clé vide `user.lab.role` (0.9.1).
- `clean` et `reset` gardent les hôtes optionnels : reconstruire plusieurs
  machines à chaque essai coûte des minutes. `destroy --optional-hosts` les
  retire, et eux seuls.
- Un `apply` sans `-target` détruirait aussi les machines qu'un **autre**
  `meta.yml` partageant le même state a déclarées. Ce risque est l'objet de
  l'[ADR-0013](./0013-refuse-out-of-contract-hosts.fr.md).

## Ce qui l'inverserait

Un provider Terraform qui noterait les dépendances par instance, et rendrait sûr
un destroy ciblé, ôterait le besoin de la voie par `apply`. L'index stable reste
tant qu'une adresse se déduit d'une position.
