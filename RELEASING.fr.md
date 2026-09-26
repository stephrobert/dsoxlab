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
5. **Lancez le contrôle local** avant de taguer :

   ```bash
   python3 scripts/check-release.py
   ```

   Il rejoue à froid les étapes ci-dessus : arbre propre, `main` à jour, tag
   cohérent avec `pyproject.toml`, section de CHANGELOG présente dans les deux
   langues, `uv.lock` aligné, version encore libre sur PyPI, CI verte. Il
   affiche la commande exacte à lancer quand tout est bon. Le garde-fou du
   workflow, lui, ne parle qu'une fois le tag poussé : il faut alors le
   supprimer des deux côtés.

6. Taguez la version et poussez le tag :

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

7. **Confirmez que la version a réellement atterri**, une fois le workflow
   terminé :

   ```bash
   python3 scripts/check-release.py --publiee
   ```

   Un workflow vert ne prouve pas que la version est installable. Lors de la
   publication de la 0.1.42, l'upload avait reçu deux `200 OK` de PyPI et la
   page du projet répondait, mais `https://pypi.org/simple/dsoxlab/` — le seul
   index que lisent pip et uv pour résoudre une version — ne la listait pas
   encore. Pendant ces minutes-là, `uv tool install dsoxlab` installait
   silencieusement la version *précédente*.

   Ce contrôle regarde le tag sur `origin`, les assets de la Release (wheel,
   sdist, provenance) et l'index simple. Il distingue « publiée mais pas encore
   servie », qui est une affaire de patience, de « absente de PyPI », qui
   signifie que l'upload n'a jamais eu lieu malgré un job vert.

   Un dernier piège, qu'il rappelle à l'affichage : uv met l'index en cache,
   donc vérifier en installant demande
   `uv tool install --force --refresh dsoxlab`. Sans `--refresh`, uv réinstalle
   tranquillement la version qu'il connaît déjà.

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
