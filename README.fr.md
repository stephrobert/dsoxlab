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

Nécessite **Python 3.11+**.

```bash
uv tool install dsoxlab      # ou : pipx install dsoxlab
dsoxlab --version
```

C'est toute l'installation. Rien à cloner, rien à compiler.

---

## Votre premier lab, en cinq minutes

Nul besoin d'un catalogue pour commencer. `dsoxlab demo` installe un catalogue
de démonstration d'un seul lab, dont le sujet est dsoxlab lui-même : la boucle
que vous répéterez sur tous les autres labs.

```bash
dsoxlab demo                    # l'installe et affiche la suite
cd ~/.local/share/dsoxlab/demo

dsoxlab course premiers-pas     # le cours
dsoxlab run premiers-pas        # vous dépose dans le répertoire de travail
dsoxlab challenge premiers-pas  # la mission
dsoxlab check premiers-pas      # les tests, et le score
```

Ni VM, ni conteneur, ni Docker : cela tourne partout où dsoxlab tourne.

---

## Ensuite, un vrai catalogue

Les labs vivent dans leurs propres dépôts, publiés séparément du moteur.
Clonez-en un, puis lancez `dsoxlab` depuis l'intérieur :

```bash
git clone https://github.com/stephrobert/linux-dsoxlab-training.git
cd linux-dsoxlab-training

dsoxlab doctor                  # ce que ce catalogue exige, et ce qui manque
dsoxlab list-labs
dsoxlab run <identifiant>
dsoxlab check <identifiant>
```

`dsoxlab doctor` ne signale que ce dont *ce* catalogue a besoin : un catalogue
entièrement `shell` ne réclame jamais d'hyperviseur. `dsoxlab doctor --fix`
répare ce qui peut l'être sans risque. En cas de problème, `dsoxlab support`
produit un rapport de diagnostic anonymisé, prêt à coller dans une issue.

### Installer depuis les sources (contributeurs)

```bash
git clone https://github.com/stephrobert/dsoxlab.git
cd dsoxlab
uv tool install --editable .
```

### Lire le cours

Le cours n'est pas embarqué dans le dépôt de labs : chaque lab déclare un
`doc_url` qui pointe vers le site du formateur. `dsoxlab guide` ouvre cette page
dans un vrai onglet de navigateur, donc elle s'affiche telle qu'elle est publiée,
avec ses images, ses blocs de code et sa navigation.

```bash
dsoxlab guide                 # le lab actif
dsoxlab guide <id>            # un lab précis
dsoxlab guide <id> --print    # affiche l'URL au lieu de l'ouvrir (utile en SSH)
```

L'URL porte des paramètres de campagne (`utm_source=dsoxlab`, `utm_medium=lab`,
`utm_campaign=<lab_id>`), ce qui permet à un formateur de voir quels labs amènent
réellement des lecteurs vers quels guides. Un lien ouvert depuis une interface
locale ne transmet aucun referrer exploitable : sans ce marquage, ces lectures
seraient indistinguables du trafic direct.

Changer de langue à la volée :

```bash
DSOXLAB_LANG=fr dsoxlab fullhelp
DSOXLAB_LANG=en dsoxlab fullhelp
```

### Lecture des cours longs

`course` et `challenge` passent par le pager dès que leur sortie dépasse la
hauteur du terminal : un cours de plusieurs centaines de lignes reste lisible
sans dépendre du scrollback du terminal. La pagination ne s'applique jamais à
un tube ni à une redirection, qui reçoivent toujours le texte complet.

```bash
DSOXLAB_PAGER='bat --plain' dsoxlab course   # choisir son pager (défaut : less -R)
dsoxlab course --no-pager                    # tout déverser d'un bloc
dsoxlab course > cours.txt                   # jamais paginé : texte brut
```

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

## Le contrat déclaratif

Un dépôt qui héberge des labs décrit son catalogue avec deux niveaux de
fichiers.

Le contrat est **versionné**. Les deux fichiers acceptent un entier
`schema_version` à leur racine ; l'omettre vaut la version 1, aucun catalogue
existant n'a donc rien à changer. Un fichier qui déclare une version que ce
dsoxlab ne lit pas est nommé dans un message, au lieu de disparaître du
catalogue. Champ par champ, avec la règle d'évolution et le chemin de migration
vers une future v2 : **[la référence du contrat v1](docs/contract-v1.fr.md)**.

Deux schémas JSON décrivent le même contrat pour ton éditeur et pour ta CI :
[`schemas/lab.schema.json`](schemas/lab.schema.json) et
[`schemas/meta.schema.json`](schemas/meta.schema.json). Pose cette ligne en tête
d'un fichier, et tout éditeur qui fait tourner `yaml-language-server`
(l'extension YAML de VS Code, entre autres) complète les champs et souligne les
fautes à la frappe :

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/stephrobert/dsoxlab/main/schemas/lab.schema.json
id: mon-lab
title: Mon lab
```

Remplace `main` par un tag de release (`v0.1.46`) pour épingler le schéma en CI.
Un test confronte les deux schémas au parseur, dans les deux sens : ils ne
peuvent pas dériver du code en silence.

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
français uniquement. La même convention vaut un cran au-dessus : un
`meta.fr.yml` posé à côté du `meta.yml` traduit `repo.title`,
`repo.description` et les titres et descriptions des `sections[]`, appariées
par `id`.

`dsoxlab validate-structure` vérifie que tout le contrat tient : le `meta.yml`
racine est conforme, chaque lab référencé existe avec un `lab.yaml` valide,
chaque `runtime.host` pointe un hôte déclaré, et tous les scripts et fichiers de
test référencés sont présents.

---

## Référence des commandes

<!-- BEGIN COMMANDES : généré par scripts/generer-doc.py, ne pas éditer -->

| Commande | Rôle |
| --- | --- |
| `dsoxlab challenge` | Affiche la mission du challenge (challenge/README.md). |
| `dsoxlab check` | Exécute les tests, calcule le score (hints déduits) et enregistre le résultat. |
| `dsoxlab clean` | Supprime toutes les ressources créées par le lab. |
| `dsoxlab completion install` | Installe l'auto-complétion pour le shell courant (zsh, bash). |
| `dsoxlab completion show` | Imprime le script de complétion sur la sortie standard, sans rien écrire. |
| `dsoxlab course` | Affiche une section du cours, ou le sommaire si aucune section n'est précisée. |
| `dsoxlab demo` | Installe un catalogue de démonstration et joue un premier lab, sans rien cloner ni provisionner. |
| `dsoxlab destroy` | Détruit l'infrastructure du lab (terraform destroy), machines restées hors du state comprises. |
| `dsoxlab doctor` | Diagnostique l'environnement (runtimes, outils, labs détectés). |
| `dsoxlab fullhelp` | Affiche le guide complet de la plateforme (concepts, workflow, commandes). |
| `dsoxlab guide` | Ouvre le guide en ligne du lab dans le navigateur. |
| `dsoxlab hint` | Affiche le prochain indice du challenge (déduit des points au score final). |
| `dsoxlab install` | Déprécié : utilise « dsoxlab completion install ». Installe l'auto-complétion. |
| `dsoxlab instructor bootstrap` | Génère la clé SSH du lab (si absente) et vérifie que terraform/ansible-runner sont installés. |
| `dsoxlab list-labs` | Liste tous les labs disponibles (filtrés par contexte actif si défini). |
| `dsoxlab next` | Recommande le prochain lab ou challenge à compléter dans le contexte actif. |
| `dsoxlab progress` | Affiche la progression par bloc (labs complétés, score moyen, challenges et capstones). |
| `dsoxlab provision` | Provisionne l'infrastructure du lab (terraform apply sur le provider courant). |
| `dsoxlab reset` | Remet le lab à l'état initial (clean + redémarrage). |
| `dsoxlab run` | Prépare et démarre l'environnement du lab. |
| `dsoxlab scores` | Affiche l'historique des scores enregistrés. |
| `dsoxlab show` | Affiche le détail et le statut d'un lab. |
| `dsoxlab ssh` | Ouvre une session SSH interactive sur un hôte du lab. |
| `dsoxlab status` | Vérifie la connectivité SSH des hôtes déclarés dans meta.yml, et nomme la cause quand l'un reste muet. |
| `dsoxlab submit` | Soumission finale : lance les tests, enregistre le score, puis tapez 'exit' pour quitter la session. |
| `dsoxlab support` | Produit un rapport de diagnostic anonymisé, à coller dans une issue. |
| `dsoxlab use` | Définit le contexte actif (section et/ou niveau par défaut). Utilisez --reset pour l'effacer. |
| `dsoxlab validate-structure` | Vérifie la structure et les métadonnées de tous les labs. |

<!-- END COMMANDES -->

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

Tout ce que dsoxlab conserve tient dans quatre emplacements, et **la
progression est par catalogue**, jamais globale : deux catalogues côte à côte
ont chacun leur historique.

| Quoi | Où | Surcharge |
| --- | --- | --- |
| Scores et indices | `<catalogue>/.dsoxlab.db` (SQLite) | aucune, c'est le dépôt |
| Contexte de session | `<catalogue>/.dsoxlab-context.json` | aucune, c'est le dépôt |
| Journal, état Terraform | `~/.local/state/dsoxlab/` | `XDG_STATE_HOME` |
| Catalogue de démonstration | `~/.local/share/dsoxlab/demo/` | `XDG_DATA_HOME` |

Les deux premiers sont à ignorer dans le `.gitignore` de chaque catalogue.

Il n'existe **aucun fichier de configuration utilisateur** : rien n'est lu dans
`~/.config/dsoxlab/`. Ce que l'on règle passe par le contrat (`meta.yml`), par
le contexte actif (`dsoxlab use`) ou par une variable d'environnement
(`DSOXLAB_PROVIDER`, `DSOXLAB_LANG`, `DSOXLAB_LOG`,
`DSOXLAB_HOST_READY_TIMEOUT`).

---

## Développement

```bash
uv sync                                     # installe les dépendances de dev
uv run pre-commit install --install-hooks   # active les hooks git
uv run ruff check src/dsoxlab               # lint + sécurité
uv run mypy src/dsoxlab                     # typage (strict)
uv run pytest                               # tests unitaires
uv run pytest tests_e2e                     # bout en bout, sur la roue construite
```

`tests_e2e/` est une suite boîte noire : elle n'importe jamais `dsoxlab`. Elle
construit la roue, l'installe dans un environnement virtuel jetable et pilote le
binaire par sous-processus, de `dsoxlab demo` jusqu'au 100/100. C'est le seul
contrôle qui voie un défaut d'empaquetage.

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
