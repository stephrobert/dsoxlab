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

1. Incrémentez la version dans `pyproject.toml`, puis régénérez le lockfile avec
   `uv lock`. Il n'y a **rien à incrémenter** dans `src/dsoxlab/__init__.py` :
   `__version__` est lu depuis les métadonnées du paquet installé, précisément
   pour qu'il ne puisse pas diverger de `pyproject.toml`.
2. Déplacez les entrées `Unreleased` sous un nouveau titre `## [X.Y.Z]` dans
   **les deux** fichiers [CHANGELOG.md](./CHANGELOG.md) et
   [CHANGELOG.fr.md](./CHANGELOG.fr.md), et mettez à jour les liens de
   comparaison en bas de chacun. Le projet est bilingue : une entrée en anglais
   seul est une entrée incomplète.
3. Committez via une pull request et mergez sur `main`.
4. **Attendez que la CI soit verte sur `main`.** Le tag construit depuis ce
   commit, et PyPI est définitif : un numéro de version ne peut jamais être
   republié.
5. Taguez la version et poussez le tag :

   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

Pousser le tag déclenche `release.yml`, qui :

- construit le sdist et la wheel avec `uv build` et les vérifie avec `twine`,
- enregistre la **provenance de build SLSA** des deux artefacts
  (`actions/attest-build-provenance`),
- publie sur PyPI via OIDC, en attachant les attestations de provenance PEP 740,
- crée la **Release GitHub** avec la section du CHANGELOG correspondant au tag,
  les distributions, et `provenance.intoto.jsonl`.

Deux détails de ce pipeline sont délibérés. Le job `publish` n'exécute aucun code
du projet et ne porte que `id-token: write` ; et `github_release` ne tourne
qu'après le succès de PyPI, donc aucune Release n'annonce une version qui aurait
échoué à l'upload.

`provenance.intoto.jsonl` est attaché comme asset de release à dessein : c'est un
artefact *distinct* de l'attestation enregistrée sur l'API GitHub, et c'est celui
que cherche le contrôle Signed-Releases d'OpenSSF Scorecard. Ce contrôle note les
**cinq dernières** releases : il n'atteint donc son maximum qu'une fois cinq
releases consécutives porteuses de l'asset.

## Vérifier une release

N'importe qui peut vérifier qu'un artefact publié provient réellement du workflow
de ce dépôt, et depuis quel commit :

```bash
gh release download vX.Y.Z --repo stephrobert/dsoxlab --pattern '*.whl'
gh attestation verify dsoxlab-X.Y.Z-py3-none-any.whl --repo stephrobert/dsoxlab
```

## Versionnage

`dsoxlab` suit le [versionnage sémantique](https://semver.org/lang/fr/). Un
changement cassant du contrat déclaratif (`meta.yml` / `lab.yaml`) ou de la CLI
incrémentera la version majeure une fois le projet arrivé en 1.0.
