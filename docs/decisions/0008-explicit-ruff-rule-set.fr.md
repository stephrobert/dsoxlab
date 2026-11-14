# ADR-0008 : le jeu de règles Ruff est déclaré en entier, jamais hérité du défaut

**Statut :** acceptée
**Date :** 2026-08-20 (0.1.49)

**Langue :** [English](./0008-explicit-ruff-rule-set.md) · [Français](./0008-explicit-ruff-rule-set.fr.md)

## Contexte

La section `[tool.ruff.lint]` du `pyproject.toml` disait « E/F sont actifs par
défaut » et se contentait d'un `extend-select` qui ajoutait `S`. Ruff 0.16 a
élargi son jeu par défaut : la même commande, sur le même code, est passée de
**0 à 123 erreurs**, dont aucune ne relevait de `E`, `F` ou `S`. Personne
n'avait décidé ce changement de périmètre : il est arrivé avec une montée de
version. Une configuration qui s'appuie sur le défaut d'un linter se fait donc
déplacer par lui.

## Décision

`select` **remplace** le défaut au lieu de l'étendre. Le `pyproject.toml` est la
seule autorité sur ce que ce projet applique, et une future version de Ruff ne
peut plus répondre à sa place. Chaque famille retenue porte, sur sa ligne, un
commentaire qui dit ce qu'elle attrape.

Familles **délibérément écartées**, chacune mesurée sur ce code le 2026-08-20
(décomptes entre parenthèses) :

- **TRY (86).** TRY003 (69) refuse les messages d'erreur écrits sur place, alors
  que ce contrat déclaratif tire sa valeur de phrases qui nomment le fichier et
  le champ fautifs. TRY004 (13) exigerait un `TypeError` là où les coercions du
  contrat lèvent `ValueError` ; or `discovery/scanner.py` et le harnais de fuzz
  attrapent exactement `(KeyError, ValueError, YAMLError)`. Obéir ferait planter
  la CLI sur un `lab.yaml` mal typé au lieu de l'écarter.
- **PLR (71).** Seuils arbitraires (nombre d'arguments, de branches).
- **PLC (88).** Style d'import et de comparaison, sans classe de défaut
  derrière.
- **N (11).** N818 renommerait onze exceptions publiques (`HostReadyTimeout`…)
  que les dépôts de labs importent : une rupture d'API pour une convention de
  nommage.
- **INP (2).** Vise les tests du lab de démonstration packagé, qui sont du
  CONTENU pédagogique, pas un paquet Python.
- **PERF (5).** Micro-optimisation d'un CLI ; les boucles visées portent des
  commentaires qu'une compréhension avalerait.
- **ANN, D, ARG, EM, FBT, TID, TC, SLF, T20, ERA, COM.** Soit redondantes avec
  mypy strict, soit purement stylistiques.

## Conséquences

- Une montée de version de Ruff ne peut ajouter des règles que si quelqu'un les
  ajoute à `select`.
- Chaque famille écartée a sa mesure écrite : rouvrir la question part de
  chiffres, pas de goûts.
- Les règles ignorées à l'intérieur des familles retenues (`S603`, `S607`,
  `S101`, `E501`, `RUF001` à `RUF003`) restent commentées ligne à ligne dans le
  `pyproject.toml`, puisque chaque commentaire explique une ligne.
- Dans la même version, les 19 appels `subprocess.run` sans `check=` ont été
  revus un par un. Les 19 étaient délibérés et disent désormais `check=False`
  avec un commentaire. L'un d'eux ne lisait son code de retour nulle part :
  c'était le bug du contrôle Terraform de `doctor`, corrigé en 0.1.49.
  `PLW1510` tient désormais cette règle.

## Ce qui l'inverserait

Rien ne rend le défaut sûr à nouveau : la raison, c'est qu'il bouge. Ce qui
change avec le temps, c'est le *contenu* de `select` et de la liste des
écartées. Une famille entre quand ses signalements mesurés sur ce code sont de
vrais défauts. Les décomptes ci-dessus vieillissent, et se remesurent avant
d'être cités à nouveau.
