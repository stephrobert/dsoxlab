# Brief — Audit de la complexité et de la qualité du code de DSOXLab

**Statut :** à réaliser  
**Nature :** cadrage d'un audit et de pistes d'amélioration, **sans implémentation dans cette PR**  
**Dépôt :** `stephrobert/dsoxlab`

## 1. Objectif

Évaluer objectivement la maintenabilité du code Python de DSOXLab, identifier les modules et fonctions qui méritent d'être simplifiés, puis proposer un plan de refactoring **progressif, mesurable et sans régression fonctionnelle**.

**Priorité : exploiter les contrôles existants avant d'ajouter de nouveaux outils.** Distinguer la dette réelle, les faux positifs et les indicateurs qui manquent.

## 2. Existant à auditer

Le dépôt dispose déjà de `.pre-commit-config.yaml`, `pyproject.toml`, de contrôles dans la CI et de scripts maison :

| Contrôle | Outil / source | But |
| --- | --- | --- |
| Qualité et sécurité Python | Ruff | Style, erreurs, risques identifiés par les règles activées |
| Typage | Mypy strict | Cohérence des annotations et des appels |
| Régression | Pytest | Tests fonctionnels et unitaires |
| Secrets | TruffleHog et pre-commit-hooks | Éviter la publication de secrets |
| Complexité du code | `scripts/complexite.py` | Complexité cognitive, profondeur, longueur des fonctions |
| Code potentiellement mort | `scripts/code-mort.py` | Symboles non utilisés, avec prise en compte de Typer et pytest |
| Complexité des écrans | `scripts/complexite-ecran.py` | Lisibilité et charge cognitive des sorties terminal |

Les scripts spécialisés utilisent des **relevés de référence** et un principe de *cliquet* : éviter toute aggravation de la dette existante, et enregistrer les améliorations pour qu'elles ne soient pas perdues.

Seuils relevés dans `scripts/complexite.py` pour les nouveaux blocs : complexité cognitive > 20, profondeur > 5, longueur > 80 lignes. Les blocs hérités plus complexes restent suivis par la référence et ne sont pas arbitrairement bloqués d'un coup.

### Écart précis déjà identifié

Le commentaire d'ouverture de `scripts/complexite.py` présente **Ruff C901** comme le contrôle de complexité cyclomatique et affirme que `pyproject.toml` le plafonne. Or, dans la configuration consultée, **C901 n'est pas sélectionné** et aucun plafond correspondant n'y figure.

**Action d'audit :** confirmer cet écart et choisir entre activation de C901 avec une stratégie de dette existante, ou correction de la documentation si un autre contrôle remplit effectivement ce rôle. Ne pas activer un blocage global sans connaître les résultats initiaux.

## 3. Travail demandé

### A. État des lieux, sans modifier le code

1. Inventorier les hooks `pre-commit`, `pre-push` et les contrôles exécutés en CI ; vérifier leurs périmètres, leurs exclusions, leurs seuils, leur fréquence et leur parité.
2. Exécuter en environnement contrôlé les commandes de diagnostic existantes, notamment :
   - `python3 scripts/complexite.py --pires 20`
   - `python3 scripts/complexite.py --verifier`
   - `python3 scripts/code-mort.py --verifier`
   - `python3 scripts/complexite-ecran.py --verifier`
   - `uv run ruff check src/dsoxlab tests tests_e2e fuzz scripts`
   - `uv run mypy src/dsoxlab`
   - `uv run pytest`
3. Relever l'état **réel** des métriques (ne pas prendre les seuils pour des mesures), la répartition par module et les 20 fonctions les plus problématiques.
4. Examiner les faux positifs, en particulier le code dynamique Typer, les fixtures Pytest et les symboles utilisés dans les catalogues externes.
5. Vérifier qu'un hook ne se contente pas de passer parce qu'il ne couvre pas les fichiers concernés, et qu'un outil n'est pas supposé actif alors qu'il ne l'est pas.

### B. Analyse de maintenabilité

Pour les points les plus complexes, rechercher notamment :

- longues fonctions multipliant conditions et imbrications ;
- responsabilités mêlées (CLI, orchestration, système, affichage, persistance) ;
- logique dupliquée, exceptions et erreurs mal propagées ;
- couplage entre modules et interfaces implicites avec les catalogues ;
- transformations de commandes shell et dépendances système difficilement testables ;
- tests insuffisants pour changer un comportement en sécurité ;
- code mort **confirmé**, non simplement suspecté.

Privilégier des exemples concrets avec **fichier, fonction, métriques et raison du refactoring**. Une bonne note de lint ne prouve pas qu'une architecture soit simple ; à l'inverse, une valeur élevée ne justifie pas seule une réécriture.

### C. Évaluer les outils complémentaires, uniquement en cas de manque avéré

Comparer l'apport marginal de :

- **Radon / Xenon** : complexité cyclomatique et indice de maintenabilité ;
- **Complexipy** : mesure de complexité cognitive externe, à rapprocher prudemment de l'algorithme maison ;
- **Vulture** : détection de code mort, en tenant compte des faux positifs déjà documentés ;
- **Ruff C901** : règle cyclomatique effectivement activée ou non ;
- outils de couverture de tests et d'analyse de dépendances entre modules si utiles.

Ne pas multiplier les métriques redondantes ni les hooks lents. Les scores produits par des implémentations différentes de la complexité cognitive ne doivent pas être considérés comme directement équivalents.

## 4. Méthode de priorisation

Produire un tableau d'actions classées avec, pour chaque sujet :

| Champ | Attendu |
| --- | --- |
| Zone | Fichier, symbole, responsabilités |
| Constat | Mesure observée, duplication ou problème de conception vérifiable |
| Risque | Bugs, difficulté de maintenance, dépendance externe, risque de régression |
| Proposition | Extraction, découpage, suppression vérifiée, découplage, ajout de tests |
| Effort | Petit / moyen / important, avec justification |
| Priorité | P1 / P2 / P3 selon impact et faisabilité |
| Preuve de réussite | Métrique avant/après et tests qui restent verts |

**P1** : défaut avéré ou zone critique difficile à faire évoluer sans risque.  
**P2** : dette importante avec bénéfice concret et couverture de tests suffisante ou améliorable.  
**P3** : simplification cosmétique, changement à risque élevé ou gain faible.

Privilégier les refactorings ciblés plutôt qu'une réécriture générale.

## 5. Règles pour la future mise en œuvre

- Préserver les interfaces et comportements publics de DSOXLab, la CLI, les codes de retour, les rendus FR/EN et les contrats utilisés par les dépôts de labs.
- Ajouter d'abord les tests de caractérisation nécessaires lorsque le comportement est fragile ou insuffisamment couvert.
- Ne jamais supprimer un symbole au seul motif qu'un analyseur le déclare inutilisé : vérifier les appels dynamiques et externes.
- Garder le mécanisme de cliquet : après une réduction réelle de dette, mettre à jour la référence selon la procédure prévue.
- En cas de nouvelle règle, mesurer son impact et prévoir une adoption progressive ; **pas de suppression massive de règles ni de contournement permanent des échecs**.
- Intégrer les contrôles seulement là où leur coût est adapté : hooks rapides au commit, suites lourdes au push ou en CI.

## 6. Livrables de l'audit

1. Une **photographie chiffrée** de la complexité et des contrôles réellement actifs, avec date, commande et version des outils.
2. Une **liste priorisée** des fonctions/modules à simplifier et du gain attendu.
3. Un **inventaire des lacunes** : contrôles manquants, désactivés, inefficaces ou redondants, notamment la question de C901.
4. Des recommandations pour les règles de pre-commit / CI avec estimation du coût et des faux positifs.
5. Une proposition de découpage en petites PR de refactoring, chacune avec ses tests de non-régression.

## 7. Critères d'acceptation

- Les constats sont fondés sur les résultats des outils, pas sur une supposition.
- Les seuils actuels et leurs limitations sont explicités.
- La divergence de configuration/documentation concernant **Ruff C901** est tranchée.
- Les priorités reposent sur des exemples vérifiables et distinguent complexité, risque de régression et impact utilisateur.
- Aucune modification du fonctionnement de DSOXLab n'est imposée par ce document seul.

**Hors périmètre de cette PR :** installer de nouveaux outils, modifier `pyproject.toml`, `.pre-commit-config.yaml`, les scripts, le code source, les tests ou leurs références. Ce fichier est un **brief destiné à une future intervention**.
