# ADR-0001 : deux runtimes, et les providers en dessous

**Statut :** acceptée
**Date :** 2026-07-15

**Langue :** [English](./0001-two-runtimes.md) · [Français](./0001-two-runtimes.fr.md)

## Contexte

Un lab a besoin d'un endroit où tourner. Certains exercices se jouent sur le
poste de l'apprenant (un shell, Terraform, un émulateur en conteneur). D'autres
ont besoin d'une machine à eux, jointe en SSH. Ces machines peuvent venir de
plusieurs backends : KVM/libvirt, Incus, Outscale, et d'autres étaient prévus
(Proxmox, AWS, GCP, Azure, Vagrant).

Le premier contrat nommait le backend dans le lab : `runtime.type: kvm` ou
`runtime.type: incus`. Un lab se trouvait alors lié à un hyperviseur. Chaque
nouveau backend aurait demandé un nouveau type de runtime, un nouvel adaptateur
et une nouvelle valeur à apprendre pour chaque auteur de catalogue.

## Décision

Il existe **deux runtimes, et deux seulement** : `shell` et `vm`.

- `shell` tourne sur le poste de l'apprenant. Sa préparation est déclarative
  (`runtime.workdir`, `runtime.fixtures`), plus un `setup.yaml` facultatif joué
  sur `localhost`.
- `vm` est **agnostique du provider** : un même lab tourne sur KVM, Incus,
  Outscale ou un backend futur, sans modification. Le backend qui sert la VM est
  une décision du **catalogue**, prise dans `meta.yml: infra.provider`, pas une
  décision du lab.

Les valeurs `kvm` et `incus` de `runtime.type` restent des alias de
rétrocompatibilité, traités par `VmRuntime` exactement comme `vm`. Aucun retrait
n'est prévu. Un nouveau lab écrit `vm`.

## Conséquences

- `runtimes/` porte deux adaptateurs, `ShellRuntime` et `VmRuntime`, choisis par
  `RuntimeManager`. La partie propre à un backend vit dans les templates
  Terraform packagés (`templates/terraform/<provider>/`) et dans `infra/`, pas
  dans un runtime.
- Ajouter un provider est une pull request sur dsoxlab seul : un dossier de
  template qui respecte le contrat de `templates/terraform/README.md`. Les
  catalogues basculent par `meta.yml: infra.provider` ou
  `DSOXLAB_PROVIDER=<provider>`.
- Un catalogue sans bloc `infra:` (tous ses labs en `shell`) n'appelle jamais
  `provision`. `terraform-dsoxlab-training` est ce cas, et c'est le
  contre-exemple qui attrape les régressions de neutralité vis-à-vis du domaine.
- Les alias ont un coût permanent : tout endroit qui choisit selon le type de
  runtime doit accepter `vm`, `kvm` et `incus` ensemble. Une table d'affichage
  qui connaissait `kvm` et `incus` mais pas `vm` a ainsi affiché « ? » sur
  chaque lab `vm` (corrigé en 0.1.26, le
  2026-07-23).

## Ce qui l'inverserait

Un genre d'environnement qui n'est ni un shell local ni une machine jointe en
SSH (par exemple un runtime qui exige sa propre bibliothèque cliente). La règle
n'est alors pas d'étirer `vm` : on l'isole dans `runtimes/<nom>.py`, on le rend
facultatif par `is_available()`, et on n'importe jamais sa bibliothèque comme
dépendance d'exécution de l'outil.
