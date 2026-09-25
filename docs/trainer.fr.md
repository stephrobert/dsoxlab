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

## Versions prises en charge

| Composant | Pris en charge | Comment cela a été établi |
| --- | --- | --- |
| **libvirt** | **8.0 ou plus récent** | Les trois versions ont provisionné pour de vrai, et la VM devait **répondre en SSH**, pas seulement « Terraform n'a pas protesté ». **8.0** dans une VM Ubuntu 22.04, où le défaut de [#234](https://github.com/stephrobert/dsoxlab/issues/234) avait d'abord été reproduit mot pour mot ; **9.0** dans une VM Debian 12, que personne n'avait jamais éprouvé ; **10.0** sur la machine de référence, avec un vrai lab `vm` du catalogue Linux. Rien en dessous de 8.0 n'a été éprouvé, et c'est la seule raison pour laquelle un plancher subsiste. |
| Provider `dmacvicar/libvirt` | `~> 0.9` | La contrainte que déclare le template packagé. Aucun plancher n'est connu dans cette plage, donc aucun n'est imposé. |

Le plancher a valu 9.0 le temps de la 0.1.91, parce que le firmware EFI dont
dsoxlab laissait le choix à libvirt ne survivait pas à la relecture du XML par le
provider Terraform. Cette cause a disparu : le template **désigne** désormais son
loader, découvert par `virsh domcapabilities`. Maintenir le plancher aurait puni
des postes pour un défaut qui n'existe plus, et un seuil qui survit à sa raison
exclut sans rien protéger.

`dsoxlab doctor` contrôle le plancher libvirt et refuse une version en dessous,
en nommant la cause. Il affiche aussi la version du provider **réellement
épinglée** pour ce catalogue, celle que `terraform init` a écrite dans l'état et
non celle que le template réclame : deux machines qui honorent `~> 0.9` peuvent
faire tourner des versions différentes. Cette version figure désormais dans
`dsoxlab support`, si bien qu'une issue la porte sans que personne ait à la
demander.

En dessous du plancher, l'outil n'est pas bloqué pour autant : seul `provision`
est concerné, et un catalogue dont tous les labs sont `shell` ne l'appelle jamais.

---

## Faire tourner dsoxlab dans une machine virtuelle

Un lab `vm` a besoin de `/dev/kvm`. Dans une machine virtuelle, cela suppose la
**virtualisation imbriquée**, et l'imbrication est une caractéristique de
l'**hôte**, pas de l'invité : rien d'installé dans l'invité ne la produit. Elle
s'active à l'extérieur, invité éteint.

| Hôte | Où elle s'active |
| --- | --- |
| **KVM / libvirt / Incus** | `/sys/module/kvm_intel/parameters/nested` (ou `kvm_amd`) doit valoir `Y`. Un `options kvm_intel nested=1` dans `/etc/modprobe.d/` le rend permanent. |
| **VMware Workstation / Fusion** | *Virtualize Intel VT-x/EPT*, dans les réglages processeur de la VM, machine éteinte. |
| **VirtualBox** | L'imbrication VT-x/AMD-V, qui dépend du processeur — et qui est indisponible sur un Windows où Hyper-V ou WSL2 tient déjà l'hyperviseur. |
| **macOS sur Apple Silicon** | Ni VirtualBox ni KVM n'y existent, et les images packagées sont en x86_64 : c'est une voie distincte (UTM/QEMU), pas une case à cocher. |

`dsoxlab doctor` nomme ce cas au lieu de le laisser deviner. Quand `/dev/kvm`
manque, il commence par regarder où il tourne, via `systemd-detect-virt` puis, à
défaut, le drapeau `hypervisor` de `/proc/cpuinfo`. Dans une machine virtuelle, il
dit que l'imbrication n'est pas disponible et nomme l'hyperviseur détecté ; sur
une machine physique, il renvoie au BIOS ou au setup UEFI. Il proposait avant les
deux d'un coup, ce qui revenait à envoyer la moitié de ses lecteurs visiter un
BIOS que leur machine n'a pas.

Dimensionnement, si l'invité doit faire tourner les labs `vm` d'un catalogue
complet : **4 vCPU et 8 Go pour l'invité lui-même**, mesurés et non estimés — les
trois hôtes du catalogue Linux se partagent 5120 Mo, et c'est le processeur qui
décide s'ils répondent tous dans la fenêtre de 180 secondes. Un invité à 2 vCPU a
déjà été vu annonçant un hôte prêt à 181 secondes.

Un catalogue dont tous les labs sont `shell` n'a besoin de rien de tout cela : il
n'appelle jamais `provision`, et `doctor` garde tous les contrôles d'hyperviseur
dans le tableau informatif.

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
