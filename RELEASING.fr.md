# Publier une version de dsoxlab

**Langue :** [English](./RELEASING.md) · [Français](./RELEASING.fr.md)

Les versions sont publiées sur [PyPI](https://pypi.org/project/dsoxlab/) par le
workflow `release.yml` via la **publication de confiance** (Trusted Publishing,
OIDC) : aucun token d'API n'est jamais stocké dans le dépôt.

## Configuration unique

1. **Publisher de confiance PyPI.** Sur PyPI, ajoutez un publisher de confiance
   *en attente* pour le projet `dsoxlab` (Account puis Publishing, ou les
   réglages *Publishing* du projet) :
   - Owner : `stephrobert`
   - Repository : `dsoxlab`
   - Workflow : `release.yml`
   - Environment : `pypi`

2. **Environnement GitHub.** Créez un environnement nommé `pypi` dans les
   réglages du dépôt (Settings puis Environments). Ajoutez au besoin des
   relecteurs requis et une restriction aux tags `v*` pour qu'une approbation
   manuelle protège chaque publication.

## Publier une version

1. Incrémentez la version dans `pyproject.toml` et `src/dsoxlab/__init__.py`.
2. Déplacez les entrées `Unreleased` de [CHANGELOG.md](./CHANGELOG.md) sous un
   nouveau titre `## [X.Y.Z]` et mettez à jour les liens de comparaison.
3. Committez via une pull request et mergez sur `main`.
4. Taguez la version et poussez le tag :

   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

Pousser le tag déclenche `release.yml`, qui :

- construit le sdist et la wheel avec `uv build` et les vérifie avec `twine`,
- publie sur PyPI via OIDC, en attachant les attestations de provenance PEP 740.

## Versionnage

`dsoxlab` suit le [versionnage sémantique](https://semver.org/lang/fr/). Un
changement cassant du contrat déclaratif (`meta.yml` / `lab.yaml`) ou de la CLI
incrémentera la version majeure une fois le projet arrivé en 1.0.
