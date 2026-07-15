# dsoxlab — CLI DevSecOps XL Labs

[![CI](https://github.com/stephrobert/dsoxlab/actions/workflows/ci.yml/badge.svg)](https://github.com/stephrobert/dsoxlab/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/stephrobert/dsoxlab?label=OpenSSF%20Scorecard)](https://securityscorecards.dev/viewer/?uri=github.com/stephrobert/dsoxlab)
[![Conformité Plumber](https://score.getplumber.io/github.com/stephrobert/dsoxlab.svg)](https://score.getplumber.io/github.com/stephrobert/dsoxlab)
[![Licence : CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Style : ruff](https://img.shields.io/badge/lint-ruff-orange.svg)](https://github.com/astral-sh/ruff)

**Autre langue :** [English](./README.md)

`dsoxlab` est un **framework CLI neutre vis-à-vis du domaine** qui pilote des
labs pédagogiques répartis dans **plusieurs dépôts**. Chaque dépôt déclare son
catalogue via un fichier `meta.yml` à la racine et un `lab.yaml` par lab.

Le framework sert aussi bien des labs Linux, Ansible, Kubernetes que Terraform,
tout ce qui respecte le contrat déclaratif. Il provisionne l'environnement,
exécute une validation au niveau du système (`pytest` + `pytest-testinfra`),
score la progression et conserve l'historique en local. Rien de spécifique à un
domaine ne vit dans le moteur.

> Compagnon des tutoriels de
> [blog.stephane-robert.info](https://blog.stephane-robert.info).

---

## Pourquoi dsoxlab

- **Un moteur, plusieurs catalogues.** Une seule CLI pilote tous les dépôts de
  formation. On ajoute un domaine en écrivant un `meta.yml`, pas en modifiant
  l'outil.
- **La validation prouve, elle ne fait pas confiance.** Les labs sont évalués
  sur l'**état réel du système** (`pytest-testinfra`) et, quand le sujet le
  justifie, sur la **persistance après reboot**, le piège qui fait échouer les
  candidats RHCSA/LFCS.
- **Plusieurs runtimes.** Jouer un lab dans un simple **shell**, un conteneur
  **Incus** ou une VM **KVM/libvirt** complète, au choix par lab.
- **Une progression qui persiste.** Scores, coûts des indices et historique sont
  conservés dans une base SQLite locale conforme à la spécification XDG.
- **Expérience bilingue.** Chaque chaîne affichée existe en anglais et en
  français (`DSOXLAB_LANG=en|fr`).

---

## Installation

Nécessite **Python 3.11+** et [uv](https://docs.astral.sh/uv/).

```bash
# Depuis le dépôt Git (mode développement / editable)
git clone https://github.com/stephrobert/dsoxlab.git
cd dsoxlab
uv tool install --editable .

# Vérifier
dsoxlab --version
dsoxlab doctor
```

`dsoxlab doctor --fix` diagnostique (et répare si possible) la boîte à outils
locale attendue par les runtimes : SSH, Terraform, libvirt/Incus et la pile
`pytest` embarquée.

---

## Prise en main

```bash
# Se placer dans un dépôt qui héberge des labs (linux-training, ansible-training…)
cd ~/Projets/linux-training

# Le contexte actif est détecté automatiquement via le meta.yml du dépôt
dsoxlab list-labs
dsoxlab show linux.depanner.service-crash-loop
dsoxlab run linux.depanner.service-crash-loop
dsoxlab check linux.depanner.service-crash-loop
```

Changer de langue à la volée :

```bash
DSOXLAB_LANG=fr dsoxlab fullhelp
DSOXLAB_LANG=en dsoxlab fullhelp
```

---

## Le contrat déclaratif

Un dépôt qui héberge des labs décrit son catalogue avec deux niveaux de
fichiers.

### 1. `meta.yml` à la racine du dépôt

Métadonnées du dépôt, topologie d'infrastructure (KVM/Incus), ordre des
sections.

```yaml
repo:
  id: linux-training
  category: linux
  title: "Linux Training — RHCSA + LFCS 2026"
  blog_url: "https://blog.stephane-robert.info/docs/admin-serveurs/linux/"

infra:
  network: lab-linux
  hosts:
    - { name: alma-rhcsa-1.lab, ip: 10.10.30.11, distro: alma10 }
    - { name: alma-rhcsa-2.lab, ip: 10.10.30.12, distro: alma10 }
    - { name: ubuntu-lfcs-1.lab, ip: 10.10.30.21, distro: ubuntu24 }

sections:
  - id: depanner
    title: "Dépanner"
    labs:
      - depanner/services-processus/service-crash-loop
      - depanner/stockage-fs/disque-plein-mais-pas-de-fichiers
```

### 2. `lab.yaml` par lab (sous `labs/<category>/<section>/<lab>/`)

Métadonnées spécifiques à un lab (skills, runtime, distros, validation).

```yaml
id: depanner-service-crash-loop
title: "Identifier et corriger un service systemd en crash loop"
section: linux
level: l2
track: [depanner, rhcsa]
skills: [systemd, journalctl, debug]
difficulty: intermediate
estimated_time: 30m
runtime:
  type: kvm
  host: alma-rhcsa-1.lab
distros: [rhel10, ubuntu24.04]
doc_url: https://blog.stephane-robert.info/docs/admin-serveurs/linux/depanner/services-processus/service-crash-loop/
validation:
  functional: true
  security: false
  persistence_after_reboot: true
```

Un `lab.fr.yaml` optionnel peut surcharger `title` et `description` pour le
français uniquement.

`dsoxlab validate-structure` vérifie que tout le contrat tient : le `meta.yml`
racine est conforme, chaque lab référencé existe avec un `lab.yaml` valide,
chaque `runtime.host` pointe un hôte déclaré, et tous les scripts et fichiers de
test référencés sont présents.

---

## Référence des commandes

| Commande | Effet |
| --- | --- |
| `dsoxlab use [section[/level]]` | Définit le contexte actif ; `--reset` l'efface, `--provider` choisit le provider d'infra |
| `dsoxlab list-labs` | Liste les labs du dépôt courant (filtre `--section`/`--level`/`--type`/`--bloc`) |
| `dsoxlab show <id>` | Détail d'un lab |
| `dsoxlab course [section]` | Affiche une section de cours ou la table des matières |
| `dsoxlab run <id>` | Prépare et démarre l'environnement du lab |
| `dsoxlab challenge <id>` | Affiche la mission de challenge d'un lab |
| `dsoxlab hint <id>` | Révèle un indice (déduit du score) |
| `dsoxlab check <id>` | Lance la validation `pytest` et enregistre le score |
| `dsoxlab submit <id>` | Soumission finale : tests, score, fermeture de session |
| `dsoxlab scores` | Historique des runs (SQLite local) |
| `dsoxlab progress` | Progression par bloc (labs faits, score moyen, challenges) |
| `dsoxlab next` | Recommande le prochain lab ou challenge à traiter |
| `dsoxlab reset <id>` | Remet le lab à son état initial |
| `dsoxlab clean <id>` | Exécute le `cleanup.sh` du lab |
| `dsoxlab provision` | Provisionne l'infrastructure (`terraform apply`) |
| `dsoxlab destroy` | Détruit l'infrastructure (`terraform destroy`) |
| `dsoxlab status` | Vérifie la connectivité SSH de tous les hôtes du `meta.yml` |
| `dsoxlab ssh <host>` | Ouvre une session SSH interactive sur un hôte |
| `dsoxlab validate-structure` | Valide le contrat (`meta.yml` + chaque `lab.yaml`) |
| `dsoxlab doctor [--fix]` | Diagnostique (et répare) l'environnement local |
| `dsoxlab install` | Installe le wrapper shell et l'auto-complétion |
| `dsoxlab instructor bootstrap` | Outillage formateur (génération de la clé SSH du lab) |
| `dsoxlab fullhelp` | Guide complet multilingue (EN/FR) |

Lancer `dsoxlab <commande> --help` pour les options de chaque commande.

---

## Runtimes

| Runtime | Backend | Usage typique |
| --- | --- | --- |
| `shell` | Shell local | Exercices rapides mono-hôte, sans surcoût de VM |
| `incus` | Conteneurs Incus | Environnements Linux isolés, à démarrage rapide |
| `kvm` | Terraform + libvirt | VM complètes avec test de reboot/persistance |

Chaque runtime est opt-in et auto-descriptif (`is_available()`), le moteur ne
dépend jamais en dur d'un backend non installé. Les templates de provisioning
(HCL Terraform, cloud-init) vivent sous `dsoxlab.templates` et couvrent Incus,
KVM/libvirt et Outscale.

---

## Architecture

```text
src/dsoxlab/
├── cli.py            ← point d'entrée Typer (+ groupe de commandes i18n)
├── config.py         ← LAB_HOME, contexte actif, .dsoxlab-context.json
├── i18n/             ← get_lang(), _(), en.py + fr.py
├── models/           ← schémas typés du contrat déclaratif
├── discovery/        ← scan meta.yml + tous les lab.yaml du dépôt courant
├── services/         ← orchestration métier (get_lab, run_lab, check_lab…)
├── sessions/         ← persistance SQLite (results + hint_requests)
├── runtimes/         ← BaseRuntime, ShellRuntime, IncusRuntime, KvmRuntime
├── infra/            ← Terraform, Ansible, inventaire, snapshots
├── validators/       ← validation du contrat (meta.yml + lab.yaml)
├── reporting/        ← sorties terminal Rich
├── utils/            ← wrapper subprocess centralisé
└── templates/        ← templates de provisioning (HCL, cloud-init)
```

Le moteur reste indépendant de l'arborescence d'un dépôt : `discovery/`
fonctionne sur n'importe quel arbre déclaré par le `meta.yml`.

---

## Persistance

- **Sessions locales :** `.dsoxlab-context.json` dans le dépôt courant
  (gitignored par chaque dépôt de labs).
- **Scores et indices :** `~/.local/share/dsoxlab/progress.db` (XDG). L'id
  global d'un lab est `<category>.<section>.<lab>`, le schéma reste universel.
- **Config utilisateur :** `~/.config/dsoxlab/config.yaml` (optionnelle).

On surcharge ces emplacements avec les variables standard `XDG_DATA_HOME` /
`XDG_CONFIG_HOME`.

---

## Développement

```bash
uv sync                                     # installe les dépendances de dev
uv run pre-commit install --install-hooks   # active les hooks git
uv run ruff check src/dsoxlab               # lint + sécurité
uv run mypy src/dsoxlab                     # typage (strict)
uv run pytest                               # tests
```

Voir [CONTRIBUTING.fr.md](./CONTRIBUTING.fr.md) pour le workflow, les conventions de
commit et les règles non négociables (le moteur reste neutre vis-à-vis du
domaine, toute chaîne affichée passe par `_()` dans les deux langues).

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

## Licence et attribution

Distribué sous licence **Creative Commons Attribution 4.0 International**
(CC BY 4.0), voir [LICENSE](./LICENSE).

Vous pouvez utiliser, partager et adapter ce projet, y compris à des fins
commerciales, **à condition de créditer Stéphane Robert et de renvoyer par un
lien vers <https://blog.stephane-robert.info>**, en indiquant si des
modifications ont été apportées.

© 2026 Stéphane Robert.
