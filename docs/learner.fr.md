# dsoxlab pour l'apprenant

**Public :** vous voulez jouer des labs. Vous n'écrivez pas de catalogue et vous
ne montez pas une plateforme de formation : ces deux métiers ont [leurs propres
pages](./README.fr.md).

**Langue :** [English](./learner.md) · [Français](./learner.fr.md)

---

## Installer

Deux prérequis, et pas un de plus : **Python 3.11 ou plus récent**, et
[`uv`](https://docs.astral.sh/uv/getting-started/installation/) ou `pipx` pour
installer dsoxlab. Si vous n'avez ni l'un ni l'autre, `uv` s'installe en une
ligne et ne demande aucun droit d'administration.

```bash
uv tool install dsoxlab      # ou : pipx install dsoxlab
dsoxlab --version
```

Rien à cloner, rien à compiler. En option, `dsoxlab install` ajoute la
complétion pour bash et zsh (rechargez votre shell ensuite).

---

## Votre premier lab, en cinq minutes

Nul besoin de catalogue pour commencer. `dsoxlab demo` installe un catalogue de
démonstration d'un seul lab, dont le sujet est dsoxlab lui-même : la boucle que
vous répéterez sur tous les autres.

```bash
dsoxlab demo                    # l'installe et dit quoi faire ensuite
cd ~/.local/share/dsoxlab/demo

dsoxlab course premiers-pas     # la leçon
dsoxlab run premiers-pas        # vous dépose dans le répertoire de travail
dsoxlab challenge premiers-pas  # la mission
dsoxlab check premiers-pas      # les tests, et la note
```

Ni VM, ni conteneur, ni Docker : il tourne partout où dsoxlab tourne.

---

## Ensuite, un vrai catalogue

Les labs vivent dans leurs propres dépôts, publiés séparément du moteur.
Installez-en un par son nom — l'outil connaît `linux`, `ansible` et
`terraform` — ou par n'importe quelle URL git. `catalog add` le clone sous
`~/.local/share/dsoxlab/catalogs/` et le rend **actif**, c'est-à-dire celui que
dsoxlab sert quand vous n'êtes pas dans un répertoire de catalogue. Un simple
`git clone` fonctionne aussi, et alors le catalogue où vous êtes est celui
qu'il sert.

```bash
dsoxlab catalog add linux       # ou une URL git, ou : git clone … && cd …
dsoxlab doctor                  # ce que ce catalogue exige, et ce qui manque
dsoxlab list-labs
dsoxlab show <lab-id>
dsoxlab start <lab-id>          # contexte, prérequis, infrastructure, session
```

`start` est la commande à apprendre en premier. Un lab demande des étapes dans
un ordre que rien ne vous dit — poser le contexte, vérifier les prérequis,
monter les machines quand le lab en veut, préparer puis ouvrir la session — et
`start` les joue **en annonçant chacune avec la seule commande qui la rejoue
seule**. Quand une étape échoue, le message la nomme avec sa commande, et rien
au-delà n'est tenté : vous ne cherchez jamais laquelle de `use`, `doctor`,
`provision` ou `run` vous avez sautée.

`dsoxlab doctor` ne rapporte que ce dont *ce* catalogue a besoin : un catalogue
fait de labs shell ne réclame jamais d'hyperviseur. `dsoxlab doctor --fix`
répare ce qui peut l'être sans risque.

### Ce qu'un lab `vm` demande à votre machine

Deux sortes de labs, et seule la première est gratuite. Un lab **`shell`** se
joue dans un répertoire de votre machine : le lab de démonstration en est un,
et tout le catalogue Terraform aussi. Un lab **`vm`** démarre de vraies
machines virtuelles à côté de vous — 66 des 86 labs du catalogue Linux le
font — et votre machine doit donc pouvoir les faire tourner :

- **Linux, avec KVM.** Les hyperviseurs packagés sont KVM/libvirt et Incus, et
  aucun des deux n'existe sous Windows ou macOS : là-bas, les labs `vm`
  passent par [l'appliance](./appliance.fr.md). Dans une machine virtuelle,
  ils réclament en plus la virtualisation imbriquée, qui s'active sur l'hôte
  et non dans l'invité.
- **libvirt et QEMU.** `dsoxlab doctor --fix` les installe là où le remède est
  un `apt install`, le seul gestionnaire de paquets que les remèdes
  connaissent aujourd'hui, et vous ajoute au groupe `kvm` — ce qui prend effet
  à votre prochaine connexion.
- **Terraform.** `doctor` le nomme et renvoie à sa page d'installation, mais ne
  peut pas l'installer : HashiCorp le distribue par son propre dépôt. Ansible
  ne demande rien, il vient avec dsoxlab.
- **Une paire de clés SSH pour le catalogue**, produite par `dsoxlab instructor
  bootstrap`. Le mot « instructor » nomme la commande, lancez-la quand même :
  un catalogue que vous clonez ne porte aucune clé — son `.gitignore` exclut
  tout le répertoire `ssh/`, une clé privée n'ayant rien à faire dans un
  dépôt — et `provision` refuse de démarrer sans elle.

Rien de tout cela ne se devine : `dsoxlab doctor` le range entre ce que ce
catalogue exige et ce qui est informatif, et dit quoi faire de chaque ligne.

---

## La boucle

| Étape | Commande | Effet |
| --- | --- | --- |
| 1 | `dsoxlab list-labs` | Parcourir le catalogue. `--section`, `--level`, `--type`, `--bloc` le réduisent |
| 2 | `dsoxlab use <section>/<niveau>` | Fixer un contexte actif, pour que les commandes suivantes cessent de demander |
| 3 | `dsoxlab show <id>` | Compétences, runtime, durée estimée, statut |
| 4 | `dsoxlab course <id>` | La leçon, section par section quand le lab les déclare |
| 5 | `dsoxlab run <id>` | Préparer l'environnement et y ouvrir une session |
| 6 | `dsoxlab challenge <id>` | La mission à accomplir |
| 7 | `dsoxlab hint <id>` | L'indice suivant, au prix de quelques points |
| 8 | `dsoxlab check <id>` | Jouer les tests, calculer la note, l'enregistrer |
| 9 | `dsoxlab submit <id>` | Pareil, puis clore la session pour de bon |
| 10 | `dsoxlab reset <id>` / `clean <id>` | Repartir de zéro, ou démonter l'environnement |

Dès qu'un lab est actif dans la session, l'identifiant devient optionnel :
`dsoxlab check` sait dans quel lab vous êtes.

`dsoxlab next` recommande la suite dans le contexte actif, `dsoxlab progress`
montre où vous en êtes bloc par bloc, et `dsoxlab scores` liste votre
historique.

### Ce que `run` ouvre vraiment

Un lab `shell` vous rend un sous-shell dans le répertoire de travail du lab, sur
votre propre machine. Un lab `vm` provisionne ou réutilise les machines déclarées
par le catalogue et ouvre une session SSH sur la cible. Dans les deux cas on en
sort par `exit`, et `dsoxlab check` fonctionne depuis cette session comme depuis
l'extérieur.

---

## Lire le cours

Deux commandes, deux choses différentes :

- **`dsoxlab course`** affiche la leçon livrée avec le lab, dans le terminal.
- **`dsoxlab guide`** ouvre le guide en ligne du lab dans un onglet du
  navigateur : il s'affiche exactement comme publié, avec ses images et sa
  navigation. `--print` imprime l'URL à la place, ce qu'il faut en SSH.

`course` et `challenge` passent par un pagineur dès que leur sortie dépasse la
hauteur du terminal : un cours de plusieurs centaines de lignes reste lisible
sans dépendre du scrollback. Les tubes et les redirections ne sont jamais
paginés, ils reçoivent le texte entier.

```bash
DSOXLAB_PAGER='bat --plain' dsoxlab course   # choisir son pagineur (défaut : less -R)
dsoxlab course --no-pager                    # tout afficher d'un coup
dsoxlab course > cours.txt                   # jamais paginé : texte brut
```

---

## Votre note

La note part de **100**, ou du barème que déclare le `challenge/hints.yaml` du
lab, et chaque indice pris coûte des points. `check` calcule la note finale et
l'enregistre, `scores` affiche l'historique.

Un lab qui déclare `exam_passing_score` est un examen : `submit` en rend un
**verdict réussi ou échoué** face à ce seuil, exprimé en pourcentage du barème
propre au lab.

Les tests lisent l'**état du système**, pas les commandes que vous avez tapées.
Aucun crédit pour avoir tapé la bonne commande, aucune pénalité pour être arrivé
au même état autrement.

---

## Langue

Chaque message existe en anglais et en français.

```bash
DSOXLAB_LANG=fr dsoxlab list-labs     # le temps d'un appel
dsoxlab use linux --lang fr           # durablement, pour ce catalogue
```

Priorité : `DSOXLAB_LANG` > le fichier de contexte du catalogue > le `LANG` du
système > `en`.

---

## Où vit votre progression

Dans le catalogue lui-même : `<catalogue>/.dsoxlab.db` pour les notes et les
indices, `<catalogue>/.dsoxlab-context.json` pour le contexte actif. La
progression est donc **par catalogue**, et copier le répertoire du catalogue
copie votre historique avec lui. La liste complète des emplacements est sur
[Où dsoxlab écrit](./files.fr.md).

---

## Quand quelque chose se passe mal

- **`dsoxlab doctor`** dit ce que ce catalogue exige et ce qui manque, en deux
  tableaux : ce qui vous bloque ici, et ce qui n'est qu'informatif.
- **`dsoxlab support`** produit un rapport de diagnostic anonymisé, prêt à
  coller dans une issue (aucun chemin personnel, aucune adresse publique).
  `--json` rend le même contenu sous forme de document machine.
- **Le journal est toujours écrit**, quelle que soit la verbosité, dans
  `~/.local/state/dsoxlab/dsoxlab.log`. Inutile de rejouer une commande pour
  savoir ce qu'elle a fait : `-v`, `-vv` et `--debug` ne changent que ce qui
  arrive à votre terminal.

Quatre codes de sortie méritent d'être reconnus :

| Code | Sens |
| --- | --- |
| `1` | La commande s'est exécutée, et la réponse est non : un test qui échoue, un identifiant de lab inconnu. Cela concerne votre travail, pas votre installation |
| `2` | La commande n'a pas pu s'exécuter : pas encore d'infrastructure, une fixture absente du lab. Quelque chose est à préparer, et le message dit quoi |
| `7` | Une autre commande dsoxlab écrit déjà dans ce catalogue. Le message la nomme : l'attendre, ou fermer l'autre terminal |
| `130` | Vous avez interrompu la commande (Ctrl-C). Le message indique comment reprendre |

[La liste complète](./exit-codes.fr.md) intéresse un script, pas vous.

---

## Rester à jour

dsoxlab regarde une fois par jour si une version plus récente existe sur PyPI et
le dit en fin de commande, sur la sortie d'erreur. Hors ligne, il se tait.

```bash
uv tool upgrade dsoxlab            # ou : pipx upgrade dsoxlab
DSOXLAB_NO_UPDATE_CHECK=1 …        # couper l'avis
```

---

## Pour aller plus loin

- [Toutes les commandes, produites par la CLI elle-même](./commands.fr.md)
- [Où dsoxlab écrit](./files.fr.md)
- [Écrire son propre catalogue](./catalog-author.fr.md)
- [Monter les machines qu'un lab `vm` demande](./trainer.fr.md)
- [L'appliance](./appliance.fr.md), si installer l'outil n'est pas une option
