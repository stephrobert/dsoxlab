# Contribuer à dsoxlab

**Langue :** [English](./CONTRIBUTING.md) · [Français](./CONTRIBUTING.fr.md)

Merci de votre intérêt pour l'amélioration de `dsoxlab`. Ce document explique
comment configurer le projet, les conventions suivies et les règles qui
préservent la santé du moteur.

Le projet est bilingue pour ses utilisateurs, mais **la langue de contribution
est l'anglais** : issues, pull requests, commentaires de code et messages de
commit sont rédigés en anglais pour que tout le monde puisse participer.

## Table des matières

- [Règles fondamentales](#règles-fondamentales)
- [Mise en place](#mise-en-place)
- [Contrôles qualité](#contrôles-qualité)
- [Internationalisation (i18n)](#internationalisation-i18n)
- [Conventions de commit](#conventions-de-commit)
- [Pull requests](#pull-requests)
- [Signaler un bug ou demander une fonctionnalité](#signaler-un-bug-ou-demander-une-fonctionnalité)

## Règles fondamentales

Non négociables. Une modification qui enfreint l'une d'elles ne sera pas mergée.

1. **Le moteur reste neutre vis-à-vis du domaine.** Rien sous `src/dsoxlab/` ne
   doit contenir de logique spécifique à un domaine (Linux, Ansible,
   Kubernetes…). Si vous écrivez `if category == "linux"`, la logique appartient
   au contrat du dépôt de labs (`meta.yml` / `lab.yaml`), pas au moteur.
2. **Une CLI, un point d'entrée.** `src/dsoxlab/cli.py` est l'unique point
   d'entrée. Les scripts shell d'orchestration vivent dans les dépôts de labs,
   jamais ici.
3. **Typage strict.** `mypy --strict` doit rester vert. Tout annoter, ne pas
   propager de dictionnaires non typés.
4. **Portabilité.** Aucun chemin ou hôte personnel codé en dur. Utiliser
   `pathlib.Path` et les variables XDG (`XDG_DATA_HOME`, `XDG_CONFIG_HOME`).
5. **Toute chaîne affichée est traduite.** Aucune chaîne en dur dans `cli.py` ou
   `reporting/`. Voir [i18n](#internationalisation-i18n).

## Mise en place

Prérequis : **Python 3.11+** et [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/stephrobert/dsoxlab.git
cd dsoxlab
uv sync                      # crée le venv et installe les dépendances de dev
uv tool install --editable . # optionnel : expose `dsoxlab` sur le PATH
```

Testez sur un vrai dépôt de labs pour valider la neutralité (au moins deux,
par exemple `linux-training` et `ansible-training`) :

```bash
cd ~/Projets/linux-training && dsoxlab list-labs
```

## Contrôles qualité

À lancer avant d'ouvrir une pull request. La CI exécute les mêmes contrôles.

```bash
uv run ruff check src/dsoxlab tests   # lint + sécurité (règles flake8-bandit S)
uv run mypy src/dsoxlab               # typage (strict)
uv run pytest                         # tests
```

## Hooks pre-commit

Ce dépôt est public : une série de hooks [pre-commit](https://pre-commit.com/)
protège chaque commit contre les fuites de secrets ou de clés privées et contre
l'ajout d'artefacts indésirables. Installez-les une fois après le clonage :

```bash
uv run pre-commit install --install-hooks
```

À chaque **commit** : contrôles d'hygiène (espaces en fin de ligne, fin de
fichier, validité YAML/JSON/TOML, gros fichiers, conflits de merge), détection
de clé privée, scan de secrets TruffleHog, `ruff` (lint + sécurité, autofix) et
`mypy --strict`. La suite `pytest` complète tourne au **push**. Tout lancer à la
main :

```bash
uv run pre-commit run --all-files
```

## Internationalisation (i18n)

Quand vous ajoutez ou modifiez une chaîne affichée :

- Ajoutez la clé dans **les deux** fichiers `src/dsoxlab/i18n/strings/en.py`
  **et** `src/dsoxlab/i18n/strings/fr.py`.
- L'anglais est la langue source ; la valeur française doit être une traduction
  fidèle, avec des diacritiques corrects.
- Vérifiez les deux langues :

  ```bash
  DSOXLAB_LANG=en dsoxlab <commande>
  DSOXLAB_LANG=fr dsoxlab <commande>
  ```

Quand vous ajoutez, retirez ou modifiez une commande ou une option, mettez à
jour **simultanément** : l'aide `help=_("…")` dans `cli.py`, les clés EN + FR,
et la section `fullhelp_commands` correspondante dans les deux langues. Ne
laissez jamais `fullhelp` décrire une commande qui n'existe plus.

## Conventions de commit

Nous utilisons les Conventional Commits avec un scope de module :

```
<type>(<module>): <description courte>
```

Types : `feat`, `fix`, `docs`, `refactor`, `chore`, `test`. Exemples :

- `feat(discovery): support multi-repo via ~/.config/dsoxlab/config.yaml`
- `fix(runtimes/kvm): make snapshot revert idempotent when snapshot is absent`
- `docs(readme): document the incus runtime`

Gardez des commits ciblés et un historique lisible. Avant un commit groupé,
consultez `git log --oneline -5` pour coller au style.

## Pull requests

- Partez de `main`, gardez un périmètre restreint, remplissez le gabarit de PR.
- Assurez-vous que lint, typage et tests sont verts.
- Mettez à jour la documentation et `CHANGELOG.md` quand le comportement change.
- Si vous ajoutez une commande ou une option, confirmez la checklist i18n
  ci-dessus.

## Signaler un bug ou demander une fonctionnalité

Utilisez les gabarits d'issue GitHub. Pour un bug, indiquez la sortie de
`dsoxlab --version`, votre OS, la commande exacte, et l'écart entre le
comportement attendu et observé. Pour un problème de sécurité, suivez plutôt
[SECURITY.md](./SECURITY.md) au lieu d'ouvrir une issue publique.
