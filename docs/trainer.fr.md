# dsoxlab pour le formateur

**Public :** vous montez l'infrastructure dont les labs ont besoin, machines,
providers, comptes, snapshots. Écrire les labs est [une autre
page](./catalog-author.fr.md), les jouer [une troisième](./learner.fr.md).

**Langue :** [English](./trainer.md) · [Français](./trainer.fr.md)

---

## Seuls les labs `vm` demandent tout cela

Un catalogue fait de labs `shell` n'a besoin d'aucune infrastructure :
l'exercice se joue sur la machine de l'apprenant, `dsoxlab provision` n'est
jamais appelé, et le `meta.yml` ne porte aucun bloc `infra:`. C'est un catalogue
conforme, pas un catalogue incomplet.

Tout ce qui suit concerne les catalogues qui déclarent `runtime.type: vm`.

---

## L'infrastructure est empaquetée dans l'outil

Les modules Terraform (`kvm`, `incus`, `outscale`) et les templates cloud-init
(AlmaLinux, Ubuntu, Debian) vivent **dans dsoxlab**. Un catalogue ne livre
**aucun** Terraform ni cloud-init : il déclare `infra:` dans son `meta.yml` et
pose sa clé publique dans `ssh/id_ed25519.pub`.

`dsoxlab provision` recopie les templates vers
`~/.local/state/dsoxlab/<catalog-id>/`, génère
`.dsoxlab.auto.tfvars.json` depuis le `meta.yml`, et lance Terraform là. Le
state n'atterrit jamais dans le dépôt de labs.

```yaml
# meta.yml
infra:
  provider: kvm                 # ou une liste de candidats
  network: lab-linux            # réseau libvirt de ce catalogue
  cidr: 10.10.10.0/24
  hosts:
    - name: alma-1.lab
      distro: alma10
      ram_mb: 2048
      vcpu: 2
      disk_gb: 20
      extra_disk_gb: 5          # second disque (/dev/vdb), pour les labs LVM ou RAID
```

Ne déclarez pas d'adresses IP : elles viennent des sorties Terraform, et
l'inventaire en est dérivé. La référence champ par champ, y compris les
surcharges `infra.providers.<provider>`, est dans
[le contrat v1](./contract-v1.fr.md).

Chaque catalogue qui provisionne des machines a intérêt à posséder son propre
réseau libvirt : deux catalogues ne se disputent alors jamais le même
sous-réseau.

---

## Démarrer

```bash
dsoxlab instructor bootstrap    # génère <catalogue>/ssh/id_ed25519 si absente,
                                # et vérifie terraform + ansible-runner
dsoxlab doctor                  # ce que ce catalogue exige, et ce qui manque
dsoxlab provision               # terraform apply sur le provider courant
dsoxlab status                  # atteint-on chaque hôte déclaré, et sinon pourquoi
dsoxlab ssh <hôte>              # une session interactive sur l'un d'eux
dsoxlab destroy                 # tout démonter
```

`provision --host <fqdn>` ne vise qu'une machine, et l'option est répétable ;
sans elle, tout le plan est appliqué. Les ressources partagées (le réseau, les
images de base) sont de toute façon gérées par le graphe de dépendances de
Terraform.

`dsoxlab doctor` range ses constats en **deux tableaux** : ce qui est *requis
pour ce catalogue*, et ce qui n'est qu'*informatif*. Le classement ne dépend que
de trois faits, jamais du domaine : le catalogue a-t-il des labs `vm`, quel
provider est actif, quels providers déclare-t-il. Un hyperviseur que ce
catalogue n'utilise pas n'apparaît jamais en rouge.

---

## Choisir un provider

Première règle qui s'applique : `DSOXLAB_PROVIDER` dans l'environnement, puis
`active_provider` du fichier de contexte (posé par `dsoxlab use --provider`),
puis un `meta.yml` qui n'en déclare qu'un. Plusieurs candidats sans choix
explicite n'est pas une erreur en soi : seules les commandes d'infrastructure
refusent d'avancer, et elles le disent.

```bash
dsoxlab use --provider kvm      # durablement, pour ce catalogue
DSOXLAB_PROVIDER=incus dsoxlab provision   # le temps d'une commande
```

Chaque provider garde son propre state Terraform, sous
`~/.local/state/dsoxlab/<catalog-id>/terraform/<provider>/`. Changer de provider
ne détruit donc pas ce que l'autre tient, ce qui est commode, et aussi la façon
dont on oublie une flotte allumée. `dsoxlab status` est l'habitude qui ne coûte
rien.

---

## Deux comptes, et ce que cela change pour les labs

cloud-init crée les deux mêmes comptes sur chaque nœud, durcis à l'identique
(membre de `wheel`/`sudo`, `sudo NOPASSWD:ALL`, clé SSH uniquement, sans mot de
passe de login, `ssh_pwauth: false`) :

| Compte | Rôle |
| --- | --- |
| `ansible` | Le compte de **service** de l'automatisation. C'est lui que dsoxlab et les playbooks des labs utilisent pour se connecter (`ansible_user: ansible`, repris dans le `ssh_config` généré) |
| `student` | Le compte **humain**, sur la machine que pilote l'apprenant |

La séparation est délibérée : traçabilité et révocation. La conséquence pour les
auteurs de labs est concrète : tout ce qui restreint la connexion (`AllowUsers`,
`remote_user`) doit viser **`ansible`**, jamais `student`, sous peine de voir la
commande dsoxlab suivante s'enfermer dehors.

---

## Les snapshots

`snapshot_required: true` dans le `runtime` d'un lab **engage l'outil**, il ne
l'informe pas :

- `run` prend un point de reprise du **disque** avant de jouer `setup.yaml`, et
  **échoue** s'il n'y arrive pas : un lab qui réclame un filet ne démarre pas
  sans lui ;
- `reset` ramène la machine à ce point plutôt que de rejouer `cleanup.yaml` ;
- `clean` retire le point de reprise, et avec lui le fichier de recouvrement
  qu'il avait créé.

L'état mémoire n'est pas capturé : la reprise repart d'un disque cohérent, pas
de la seconde d'avant.

---

## Les machines qui survivent à leur state

Un `provision` en échec peut laisser des domaines définis sur l'hyperviseur mais
hors du state Terraform. Reprovisionner par-dessus produirait une flotte que
personne ne suit : dsoxlab refuse plutôt, et deux codes de sortie disent de quel
côté cela a lâché.

| Code | Sens |
| --- | --- |
| `5` | `provision` a trouvé des domaines orphelins et s'est arrêté. Le message nomme la commande qui les retire |
| `6` | `destroy` n'a pas pu les retirer. Quelque chose sur l'hyperviseur les tient encore |

`destroy` retire aussi ces orphelins, après confirmation (`--yes` la saute), et
sort en non-zéro s'il en reste un. Un `destroy` qui rapportait un succès en
laissant les machines debout est le défaut que cela a remplacé.

---

## Où tout est conservé

Le state Terraform, le verrou d'écriture, l'inventaire et le `ssh_config`
générés : tout est listé sur [Où dsoxlab écrit](./files.fr.md). Deux points
qu'un formateur a intérêt à garder en tête :

- **Le `ssh_config` généré est un cache**
  (`~/.cache/dsoxlab/<catalog-id>/`). Il se régénère à la demande, mais il se
  purge aussi : ce qui pointerait dessus (un `Include`, un profil d'IDE) doit
  survivre à sa disparition. Le fragment écrit dans
  `~/.ssh/config.d/<catalog-id>.conf` est celui qui est stable.
- **Un catalogue, un verrou.** Une seconde commande concurrente qui écrit sort
  en code `7` et nomme la première. Deux clones du même catalogue partagent le
  verrou, parce qu'ils partagent le state Terraform.

---

## Pour aller plus loin

- [Le contrat v1, champ par champ](./contract-v1.fr.md)
- [Où dsoxlab écrit](./files.fr.md)
- [Écrire les labs](./catalog-author.fr.md)
