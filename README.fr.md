<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/dsoxlab-lockup-dark.svg">
  <img src="docs/assets/brand/dsoxlab-lockup-light.svg" alt="dsoxlab" width="240">
</picture>

# dsoxlab — CLI DevSecOps XL Labs

[![CI](https://github.com/stephrobert/dsoxlab/actions/workflows/ci.yml/badge.svg)](https://github.com/stephrobert/dsoxlab/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/stephrobert/dsoxlab?label=OpenSSF%20Scorecard)](https://securityscorecards.dev/viewer/?uri=github.com/stephrobert/dsoxlab)
[![Conformité Plumber](https://score.getplumber.io/github.com/stephrobert/dsoxlab.svg)](https://score.getplumber.io/github.com/stephrobert/dsoxlab)
[![Licence : Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Style : ruff](https://img.shields.io/badge/lint-ruff-orange.svg)](https://github.com/astral-sh/ruff)

**Autre langue :** [English](./README.md)

`dsoxlab` transforme des **exercices déclaratifs en environnements
reproductibles, exécutables et vérifiables**. Un catalogue déclare ce qu'il
propose via un `meta.yml` à la racine et un `lab.yaml` par lab ; le moteur
provisionne ce que le lab demande, l'ouvre, et prouve le résultat par des tests
qui lisent l'**état du système** plutôt que les commandes tapées.

Rien de spécifique à un domaine ne vit dans le moteur : il sert aussi bien des
labs Linux, Ansible, Kubernetes que Terraform, et tout autre catalogue qui
respecte le contrat déclaratif. Il score aussi la progression et conserve
l'historique en local, par catalogue.

> Né pour accompagner les tutoriels de
> [blog.stephane-robert.info](https://blog.stephane-robert.info), et utilisable
> sans eux.

<p align="center">
  <img src="https://raw.githubusercontent.com/stephrobert/dsoxlab/main/docs/demo.gif" alt="dsoxlab en action : list-labs et show" width="820">
</p>

---

## Installer et jouer, en cinq minutes

Nécessite **Python 3.11+**. Rien à cloner, rien à compiler.

```bash
uv tool install dsoxlab      # ou : pipx install dsoxlab
dsoxlab demo                 # installe un catalogue de démonstration d'un lab
cd ~/.local/share/dsoxlab/demo

dsoxlab course premiers-pas     # la leçon
dsoxlab run premiers-pas        # vous dépose dans le répertoire de travail
dsoxlab challenge premiers-pas  # la mission
dsoxlab check premiers-pas      # les tests, et la note
```

Le lab de démonstration a dsoxlab lui-même pour sujet, et ne demande ni VM, ni
conteneur, ni Docker : il tourne partout où dsoxlab tourne.

---

## Documentation

Trois lecteurs, trois portes. Chaque page nomme son public dès ses premières
lignes.

| Je veux… | Lire |
| --- | --- |
| Installer dsoxlab, jouer des labs, comprendre ma note | **[Pour l'apprenant](docs/learner.fr.md)** |
| Écrire mon propre catalogue de labs | **[Pour l'auteur de catalogue](docs/catalog-author.fr.md)**, puis [le contrat v1](docs/contract-v1.fr.md) champ par champ |
| Monter les machines dont les labs ont besoin | **[Pour le formateur](docs/trainer.fr.md)** |
| Savoir où dsoxlab écrit sur mon disque | [Où dsoxlab écrit](docs/files.fr.md) |
| Voir toutes les commandes | [Référence des commandes](docs/commands.fr.md), produite par la CLI |

Dans le terminal, `dsoxlab fullhelp` affiche le guide complet de la plateforme,
en anglais comme en français.

---

## Pourquoi dsoxlab

- **Un moteur, plusieurs catalogues.** Une seule CLI pilote tous les dépôts de
  formation. On ajoute un domaine en écrivant un `meta.yml`, pas en modifiant
  l'outil.
- **La validation prouve, elle ne fait pas confiance.** Les labs sont évalués
  sur l'**état réel du système** (`pytest-testinfra`) et, quand le sujet le
  justifie, sur la **persistance après reboot**, le piège qui fait échouer les
  candidats RHCSA/LFCS.
- **Deux runtimes.** Un lab se joue soit dans un **shell** sur votre machine,
  soit dans une **vm** provisionnée pour vous. Quel backend sert cette VM
  (KVM/libvirt, Incus, Outscale) est la décision du catalogue, pas celle du lab.
- **Une progression qui persiste, par catalogue.** Scores, coûts des indices et
  historique sont conservés dans le catalogue lui-même : deux catalogues ne
  mélangent jamais leurs historiques.
- **Expérience bilingue.** Chaque chaîne affichée existe en anglais et en
  français (`DSOXLAB_LANG=en|fr`).

---

## Contribuer

```bash
git clone https://github.com/stephrobert/dsoxlab.git
cd dsoxlab
uv tool install --editable .
```

Voir [CONTRIBUTING.fr.md](./CONTRIBUTING.fr.md) pour l'installation de
développement, les contrôles de qualité et les règles non négociables (le moteur
reste neutre vis-à-vis du domaine, toute chaîne affichée passe par `_()` dans
les deux langues).

---

## Sécurité

La posture de sécurité est appliquée, pas seulement affichée : chaque workflow
est scanné par son propre outillage à chaque push et pull request.

- **GitHub Actions durcies.** Chaque action est épinglée par SHA de commit
  complet, le token par défaut n'a aucune permission (chaque job demande le
  strict minimum), et `checkout` ne persiste jamais les identifiants.
- **[zizmor](https://github.com/zizmorcore/zizmor)** analyse statiquement les
  workflows à chaque PR (`ci.yml`).
- **[Plumber](https://getplumber.io)** valide la CI/CD contre une politique de
  confiance (`.plumber.yaml`) au seuil de conformité 100%, et publie le badge de
  score (`plumber.yml`).
- **[OpenSSF Scorecard](https://securityscorecards.dev)** suit la posture
  supply-chain (`scorecard.yml`).
- **Publication PyPI de confiance (OIDC).** Les releases ne portent aucun token
  durable et embarquent des attestations
  [PEP 740](https://peps.python.org/pep-0740/) (`release.yml`).
- **Scan de secrets en pre-commit.** TruffleHog et la détection de clés privées
  tournent en local avant chaque commit (voir [CONTRIBUTING.fr.md](./CONTRIBUTING.fr.md)).

Pour signaler une vulnérabilité, suivez [SECURITY.fr.md](./SECURITY.fr.md).

La marque et ses fichiers sont documentés dans
[docs/brand.fr.md](./docs/brand.fr.md) ; **le nom et le logo ne sont pas
couverts par la licence Apache 2.0**.

## Licence et attribution

Distribué sous **licence Apache 2.0**, voir [LICENSE](./LICENSE) et
[NOTICE](./NOTICE).

Vous pouvez utiliser, partager et adapter ce projet, y compris à des fins
commerciales, **à condition de créditer Stéphane Robert et de renvoyer par un
lien vers <https://blog.stephane-robert.info>**, en indiquant si des
modifications ont été apportées. Apache-2.0 conserve ces deux mêmes obligations,
l'attribution et la mention des modifications, et y ajoute une concession de
brevet explicite.

Jusqu'à la version **0.1.12** incluse, dsoxlab était distribué sous Creative
Commons Attribution 4.0 (CC BY 4.0). Cette concession est irrévocable : ces
versions restent disponibles sous CC BY 4.0. À partir de la **0.1.13**, le
projet passe sous Apache-2.0 : les licences Creative Commons ne sont pas conçues
pour du logiciel, et celle-ci laissait la question des brevets ouverte tout en
faisant classer le paquet en `Other/NOASSERTION` sur PyPI.

© 2026 Stéphane Robert.
