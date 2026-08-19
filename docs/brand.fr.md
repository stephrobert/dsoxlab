# La marque

**Langue :** [English](./brand.md) · [Français](./brand.fr.md)

![dsoxlab](assets/brand/dsoxlab-lockup-light.svg)

Une fiole, et un prompt dedans. La fiole est le lab : quelque chose qu'on
déclare, qu'on prépare, qu'on jette et qu'on prépare à nouveau. Le prompt est ce
qui s'y exécute vraiment. Deux formes, une idée, et c'est tout l'argument du
projet dessiné plutôt qu'écrit : un lab n'est pas un document qu'on lit, c'est
un environnement qui s'exécute et que quelque chose vérifie.

Le mot sépare `dsox` de `lab` par la couleur. `dsoxlab` n'est un mot que
personne n'a déjà vu, et sept lettres d'une seule encre se lisent comme une
tache ; la coupure donne à l'œil les deux moitiés dont il a besoin.

## Ce qui a été délibérément écarté

Une proposition antérieure dessinait la fiole entourée de serveurs, d'un éditeur
de code, d'un cube de conteneur et de bulles montantes, en dégradés avec une
ombre portée, au-dessus d'une signature `DEVOPS TRAINING, EXECUTED` très
espacée. Rien de tout cela n'a survécu, et les raisons méritent d'être écrites
pour qu'on ne les réintroduise pas.

**Cinq sujets, c'est quatre de trop.** Cette planche le démontrait contre
elle-même : ses propres favicons gardaient la fiole et laissaient tomber le
reste. Les serveurs, l'éditeur et le cube n'existaient qu'à une taille à
laquelle personne ne voit jamais un logo.

**Les dégradés, les ombres et les reflets ne survivent à rien.** Ni à l'encre
unique, ni à l'impression, ni à 16 pixels. Sur la version noire de cette même
planche, le `>_` disparaissait, or c'est la seule partie qui porte du sens.

**Une signature qu'on ne peut pas lire ne signe rien.** En capitales fines très
espacées, elle était déjà une bouillie grise sur la déclinaison horizontale,
à une taille où le logo est encore grand.

Ce qui a été gardé est ce qui était bon : la fiole avec un prompt dedans, et la
coupure bicolore du nom.

## Les fichiers

Tout est dans [`assets/brand/`](assets/brand/), en SVG uniquement.

| Fichier | Usage |
|---|---|
| `dsoxlab-lockup-light.svg` | le défaut, sur fond clair |
| `dsoxlab-lockup-dark.svg` | sur fond sombre ; le bleu s'éclaircit, ce n'est pas le même |
| `dsoxlab-lockup-mono.svg` | encre unique, hérite de `currentColor` |
| `dsoxlab-icon.svg` / `dsoxlab-icon-dark.svg` | le signe seul, à partir de 24 px |
| `dsoxlab-icon-mono.svg` | le signe seul, encre unique, pour les favicons et les terminaux |

## Comment il s'intègre, et pourquoi ainsi

GitHub bascule sur le thème du lecteur par `<picture>`, qui est le mécanisme
supporté :

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/dsoxlab-lockup-dark.svg">
  <img src="docs/assets/brand/dsoxlab-lockup-light.svg" alt="dsoxlab" width="240">
</picture>
```

**Le mot est en courbes, pas en texte**, et c'est ce qui rend le fichier sûr. Un
SVG qui porte `<text font-family="Poppins">` s'affiche avec ce que le navigateur
du lecteur possède, Helvetica, Arial ou DejaVu, parce que GitHub ne lui sert
aucune webfont ; et un logotype composé dans la mauvaise grotesque se lit comme
une erreur. Les sept glyphes sont du Poppins SemiBold converti en courbes, donc
le fichier est autonome : même rendu sur GitHub, dans une présentation, dans un
PDF, sur une machine qui n'a jamais entendu parler de cette police.

Poppins est sous licence SIL Open Font License. Seules ces sept formes de
glyphes circulent dans ce dépôt, jamais la police.

## L'employer

- **Zone de respiration** : la hauteur du col de la fiole sur chaque côté. Rien
  n'y entre.
- **Tailles minimales** : 24 px pour le logotype, 20 px pour le signe seul. En
  dessous, le `>_` se referme et il ne reste que la fiole, encore reconnaissable
  mais qui ne dit plus ce que la marque veut dire.
- **Le prompt est plus fin que la fiole**, à dessein : le contenant et ce qui s'y
  exécute ne pèsent pas pareil. Les redessiner à la même épaisseur aplatit le
  signe.
- **Sur fond sombre, prenez le fichier sombre.** Le `#2563EB` est net sur blanc
  et se referme sur du bleu nuit, d'où les deux versions.

Ne recolorez pas le signe en une seule encre autrement que par
`dsoxlab-*-mono.svg`, ne séparez pas la fiole du prompt, ne composez pas le mot
dans une autre police, n'ajoutez pas de signature, et n'ajoutez aucun effet :
une ombre sur un signe de trois traits se lit comme un défaut de rendu.

## Le modifier

La géométrie est contrainte par deux dégagements qui se calculent plutôt qu'ils
ne se jugent, et le premier jet violait les deux :

- à `y=27`, la paroi gauche de la fiole occupe jusqu'à `x=17.1`, donc le chevron
  commence à `x=20` ;
- la base occupe à partir de `y=39`, donc l'underscore se pose à `y=35` et pas
  plus bas.

Déplacez l'une des deux formes à la main et le signe commence à se toucher,
ce que faisait exactement la première version. **Régénérez le mot plutôt que de
le retaper** : les courbes viennent de Poppins SemiBold via fontTools et ne
s'éditent pas comme du texte. Les fichiers d'icône ne portent aucun texte et
s'éditent directement.

## Deux choses que ce dépôt ne peut pas versionner

- **L'aperçu social**, la carte affichée quand on partage le lien du dépôt.
  C'est un réglage GitHub et non un fichier : Settings → Social preview, un PNG
  de 1280×640. Rastérisez le logotype clair sur fond blanc en 2x pour l'obtenir.
- **L'avatar du compte**, que GitHub prend sur le propriétaire et non sur le
  dépôt.

## Licence

**Le nom *dsoxlab* et le logo ne sont pas couverts par la licence Apache 2.0**
qui couvre le code. Ils peuvent être employés pour désigner ce projet, dans un
article, une conférence, une comparaison, une liste d'outils, sans rien
demander. Ils ne peuvent pas servir de marque à un fork, à un produit ou à un
service, ni d'une façon qui laisserait croire que le projet approuve ce qu'il
n'approuve pas.

C'est le partage ordinaire pour un projet open source, et il est écrit ici parce
qu'un lecteur qui veut bien faire ne devrait pas avoir à le deviner.
