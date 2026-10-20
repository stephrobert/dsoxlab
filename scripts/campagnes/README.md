# Les campagnes de réattestation, et leur ordonnancement

## Pourquoi ce dossier existe

Le 2026-10-19, une campagne de réattestation a produit **59 faux ROUGE sur
kubernetes et 16 sur iam** avant d'être arrêtée. Aucune des deux causes ne
tenait aux labs, et surtout : **les deux étaient écrites dans le `CLAUDE.md` du
catalogue concerné.** Le script de campagne portait ses prérequis en listes
codées en dur, construites de mémoire au lieu d'être lues.

> `kubernetes/CLAUDE.md` : « Aucun point d'accroche après le provisionnement.
> Le socle partagé est donc inclus par *chaque* `setup.yaml`. »

Des VM fraîchement provisionnées ne portent donc aucun cluster, et le
validateur de ce catalogue photographie le cluster **avant** de jouer le lab :
chaque lab rendait ROUGE en deux secondes sur un `FileNotFoundError:
'kubectl'`, sans avoir été joué. Un faux ROUGE coûte plus cher qu'une absence
de verdict : il envoie chercher un défaut dans un lab qui n'en a pas, et il
écrase un relevé qui disait vrai.

## Le principe : un descripteur par catalogue, jamais une liste dans le code

Chaque `<catalogue>.yml` de ce dossier déclare ce que SON catalogue exige, avec
**la source qui le documente**. Le pilote (`scripts/campagne.py`) ne contient
aucun nom de catalogue : il lit ce dossier. Ajouter un catalogue, corriger un
prérequis ou en bloquer un ne demande donc pas de toucher au code, et aucune
liste ne peut dériver de la réalité sans que le fichier le dise.

C'est la même règle que `scripts/etat-des-catalogues.py` applique au comptage
des labs : **ce qui se mesure ne s'écrit pas en dur**, et ce qui s'écrit porte
sa source.

## Le format

```yaml
catalogue: kubernetes-dsoxlab-training
labs_vm: 64
bloque: false            # true = le pilote refuse de lancer, avec la raison
raison_du_blocage: ""

etapes:                  # jouées dans cet ordre, chacune avec son pourquoi
  - nom: provision
  - nom: run_prealable
    lab: cka-kubectl-debug
    pourquoi: |
      Le cluster n'existe qu'après le setup d'un lab.
    source: CLAUDE.md, section « Le socle partagé »
  - nom: campagne
  - nom: destroy

pieges:                  # ce qui produit un faux verdict, et son symptôme
  - symptome: "FileNotFoundError: 'kubectl'"
    cause: le cluster n'est pas monté
    source: CLAUDE.md
```

## Ce que le pilote garantit

- il **refuse** un catalogue marqué `bloque`, en citant sa raison ;
- il joue les étapes **dans l'ordre déclaré**, et s'arrête au premier échec
  d'étape plutôt que d'enchaîner sur une campagne qui ne mesurera rien ;
- il **détecte une série de rouges** (trois verdicts rouges portant le même
  motif) et interrompt le catalogue : c'est la signature d'un harnais cassé,
  pas de labs cassés ;
- il ne commite rien. Un relevé se relit avant d'entrer dans l'historique.

## L'ordre des catalogues

Il est déclaré dans `_ordre.yml`, avec les raisons. Deux contraintes mesurées
le 2026-10-19 :

- `ansible` passe **en dernier** : il revendique `db1.lab` comme `bdd`, seule
  collision de nom d'hôte des huit `meta.yml` (les réseaux, eux, sont tous
  distincts, de `10.10.20.0/24` à `10.10.110.0/24`) ;
- un seul catalogue à la fois, et destruction entre chaque : les huit stacks
  cumulées demandent 41 Go là où la machine en offre 46.
