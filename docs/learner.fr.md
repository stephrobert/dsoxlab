# dsoxlab pour l'apprenant

**Public :** vous voulez jouer des labs. Vous n'écrivez pas de catalogue et vous
ne montez pas une plateforme de formation : ces deux métiers ont [leurs propres
pages](./README.fr.md).

**Langue :** [English](./learner.md) · [Français](./learner.fr.md)

---

## Installer

Python 3.11 ou plus récent, et c'est tout le prérequis.

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

Les labs vivent dans leurs propres dépôts, publiés séparément du moteur. Clonez
en un, puis lancez `dsoxlab` depuis l'intérieur : le catalogue où vous êtes est
celui que dsoxlab sert.

```bash
git clone https://github.com/stephrobert/linux-dsoxlab-training.git
cd linux-dsoxlab-training

dsoxlab doctor                  # ce que ce catalogue exige, et ce qui manque
dsoxlab list-labs
dsoxlab show <lab-id>
dsoxlab run <lab-id>
```

`dsoxlab doctor` ne rapporte que ce dont *ce* catalogue a besoin : un catalogue
fait de labs shell ne réclame jamais d'hyperviseur. `dsoxlab doctor --fix`
répare ce qui peut l'être sans risque.

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

Deux codes de sortie méritent d'être reconnus :

| Code | Sens |
| --- | --- |
| `7` | Une autre commande dsoxlab écrit déjà dans ce catalogue. Le message la nomme : l'attendre, ou fermer l'autre terminal |
| `130` | Vous avez interrompu la commande (Ctrl-C). Le message indique comment reprendre |

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
