# L'appliance : une machine virtuelle prête à jouer

**Public :** qui travaille sous Windows ou macOS et veut jouer des labs sans
rien installer, et qui préfère une machine jetable à la sienne.

**Langue :** [English](./appliance.md) · [Français](./appliance.fr.md)

L'appliance est une machine virtuelle Debian 13 où dsoxlab, Ansible, Terraform
et un bureau sont déjà en place. On l'importe, on la démarre, on joue.

![L'appliance dsoxlab : « dsoxlab doctor » dans un terminal du bureau
XFCE](./assets/appliance-bureau.png)

*L'appliance dans VirtualBox, quelques minutes après l'import : `dsoxlab
doctor` sur le bureau, 86 labs découverts, et le seul choix qui reste à faire —
l'hyperviseur — nommé avec la commande qui le règle.*

**Sous Linux, c'est la mauvaise réponse**, et cette page le dit franchement :
télécharger un demi-gigaoctet pour s'épargner `uv tool install dsoxlab` n'a
aucun sens. Elle existe pour les systèmes où cette commande n'est pas une
option.

## Télécharger

Les images sont attachées aux Releases GitHub des **versions mineures** (0.2.0,
0.3.0…), pas à chaque correctif : republier un demi-gigaoctet pour une ligne
coûterait cher et n'apporterait rien. Celle de la dernière version mineure est
la bonne — l'image n'épingle aucune version de dsoxlab et installe la dernière
au premier démarrage.

| Fichier | Pour | Éprouvé |
| --- | --- | --- |
| `dsoxlab-appliance-<version>.ova` | VirtualBox — Windows, Linux, Mac Intel | oui : import, démarrage, bureau |
| la même `.ova` | VMware Workstation et Fusion | pas directement ; l'OVF valide contre le schéma DMTF et déclare ce que VMware attend (`vmx-13`, LsiLogic, E1000, `streamOptimized`) |
| `dsoxlab-appliance-<version>.qcow2` | QEMU/KVM, libvirt, Proxmox | oui |
| `SHA256SUMS` | vérifier ce qu'on a téléchargé | — |

Les deux images sont **x86-64**. Voir [Apple Silicon](#apple-silicon-m1-m4)
plus bas.

**Seuls les deux derniers jeux d'images sont conservés.** Les versions mineures
plus anciennes gardent leur page, leur changelog et leurs distributions Python,
mais leurs `.ova` et `.qcow2` sont retirés — environ 900 Mo chacun, pour des
images qui n'épinglent aucune version de dsoxlab et ne pèsent donc rien d'autre
que leur poids une fois la suivante publiée. Prenez la dernière ; il n'y a
aucune raison d'en vouloir une plus ancienne.

## Importer et démarrer

Dans VirtualBox : **Fichier → Importer un appareil virtuel**, choisir le
`.ova`, accepter. En ligne de commande,
`VBoxManage import dsoxlab-appliance-<version>.ova`.

La machine annonce 4 vCPU et 8 Go. À baisser si la vôtre est plus petite — 2
vCPU et 4 Go suffisent aux labs `shell` — dans **Configuration → Système**.

Pour les labs `vm`, en revanche, **gardez les 8 Go** : les machines du lab
tournent *dans* l'appliance, et `dsoxlab doctor` compare la mémoire disponible à
celle que le catalogue déclare. Mesuré avec le catalogue Linux, qui déclare
5120 Mo : à 4 Go, `doctor` refuse de commencer en disant exactement ce qui
manque.

Première connexion, en console ou sur le bureau :

| | |
| --- | --- |
| utilisateur | `student` |
| mot de passe | `dsoxlab` |

**Ce mot de passe doit être changé à cette première connexion** : le mot de
passe de construction est public, il est dans ce dépôt. La machine le demande
d'elle-même.

## Ce que fait le premier démarrage

L'image n'épingle rien, donc le premier démarrage construit ce qui aurait
vieilli :

1. il installe la **dernière version publiée de dsoxlab** ;
2. il installe les **hyperviseurs** (KVM, libvirt, Incus) — *seulement* si
   l'hôte expose la virtualisation imbriquée, ce qu'il vérifie au lieu de le
   supposer ;
3. il installe le **bureau XFCE** et Firefox ;
4. il **redémarre**, parce que l'appartenance aux groupes et la cible graphique
   ne prennent effet qu'au démarrage suivant.

Comptez quelques minutes, selon votre connexion. La console affiche chaque
étape.

**Si quelque chose échoue, la machine le dit et recommence au démarrage
suivant.** Elle ne se marque pas configurée : une appliance à moitié installée
qui se croit complète est pire qu'une appliance qui l'avoue. La cause
habituelle est l'absence de réseau dans la machine virtuelle — vérifiez sa
carte réseau, puis redémarrez-la.

## Jouer les labs `vm` : la virtualisation imbriquée

Les labs de type `shell` fonctionnent partout. Les labs de type `vm` démarrent
de vraies machines *dans* l'appliance, ce qui demande que l'hôte l'autorise :

- **VirtualBox** : `VBoxManage modifyvm <nom> --nested-hw-virt on`, appliance
  éteinte. Dans l'interface, **Configuration → Système → Processeur → Activer
  VT-x/AMD-V imbriqué**.
- **VMware** : *Virtualiser Intel VT-x/EPT ou AMD-V/RVI*.
- **QEMU/libvirt** : le module `kvm_intel`/`kvm_amd` de l'hôte doit avoir
  `nested=1`, et le modèle de CPU doit être transmis (`host-passthrough`).

Vous n'avez pas à deviner si c'est pris en compte :

```console
$ dsoxlab doctor
```

nomme ce que cette machine sait faire et ce qui manque, et dit en toutes
lettres que la virtualisation imbriquée s'active sur l'hyperviseur **hôte**,
cette machine éteinte.

![dsoxlab provisionnant les machines d'un lab depuis le terminal de
l'appliance](./assets/appliance-lab-vm.png)

*`dsoxlab start` sur un lab `vm`, dans l'appliance : les seize contrôles requis
au vert, puis Terraform qui monte les trois machines du lab — des VM dans la
VM.*

## Apple Silicon (M1-M4)

**L'appliance ne tourne pas sur un Mac Apple Silicon**, et prétendre le
contraire coûterait un après-midi. Les deux images sont x86-64 ; Parallels,
VMware Fusion et UTM virtualisent de l'arm64 sur ces machines et n'émulent pas
une autre architecture à une vitesse utilisable. UTM sait émuler du x86-64 par
l'interpréteur de QEMU, à environ un dixième de la vitesse native : de quoi
regarder un démarrage, pas de quoi jouer un lab.

Une image arm64 est la réponse évidente, et elle est prévue plutôt que faite,
pour deux raisons qu'il vaut mieux connaître :

- les runners arm64 hébergés par GitHub **n'exposent pas `/dev/kvm`**, donc la
  CI devrait construire cette image en émulation, pendant des heures ;
- la virtualisation imbriquée sur Apple Silicon n'existe qu'à partir du **M3**
  avec macOS 15 ou plus récent. Même avec une image arm64, les labs `vm`
  resteraient donc hors de portée sur la plupart des Mac ; seuls les labs
  `shell` tourneraient.

En attendant, sur un Mac Apple Silicon, installez l'outil :
`uv tool install dsoxlab`. Tous les labs `shell` fonctionnent, c'est-à-dire
tout le catalogue Terraform et une bonne part des autres.

## Ce qu'il y a dedans

Debian 13, minimale, plus ce qu'un poste de lab demande : `git`, `curl`, `vim`,
`python3`, `man`, Ansible, Terraform, et après le premier démarrage dsoxlab, les
hyperviseurs et le bureau. La documentation et les locales autres qu'anglaise et
française sont exclues des paquets, ce qui fait l'essentiel du demi-gigaoctet
qu'on ne télécharge pas.

La recette vit dans [`packer/`](../packer/) et la CI la construit sur un runner
hébergé par GitHub. Elle est reproductible : rien n'est fait à la main dans
l'image.

## Limites connues

- **Un utilisateur, une machine.** L'appliance n'est pas un serveur de classe
  partagé ; un formateur qui sert plusieurs apprenants veut plutôt
  [la page du formateur](./trainer.fr.md).
- **Le disque fait 20 Go.** De quoi loger un catalogue et quelques VM de lab,
  pas un cluster Kubernetes à trois nœuds. À agrandir dans votre hyperviseur au
  besoin.
- **Aucune mise à jour automatique.** `uv tool upgrade dsoxlab` met l'outil à
  jour ; l'image, elle, n'est reconstruite qu'aux versions mineures.
