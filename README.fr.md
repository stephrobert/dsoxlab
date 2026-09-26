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

## Deux façons d'entrer

| | **Installer l'outil** | **Télécharger l'appliance** |
| --- | --- | --- |
| Pour | Linux, et macOS ou Windows si Python est là | Windows et macOS, ou qui préfère une machine jetable |
| Il faut | Python 3.11+ et `uv` ou `pipx` | VirtualBox ou VMware, et 8 Go de RAM disponibles |
| On obtient | une commande, quelques mégaoctets | une VM Debian 13 avec bureau, Ansible et Terraform, ~450 Mo à télécharger |
| À lire | la section juste en dessous | **[L'appliance](docs/appliance.fr.md)** |

Sous Linux, installer l'outil est la bonne réponse : télécharger un
demi-gigaoctet pour s'épargner une commande n'a aucun sens, et ce README le dit
plutôt que de vendre les deux à égalité.

<p align="center">
  <img src="https://raw.githubusercontent.com/stephrobert/dsoxlab/main/docs/assets/appliance-bureau.png" alt="« dsoxlab doctor » dans un terminal du bureau de l'appliance, sous VirtualBox" width="820">
</p>

<p align="center">
  <em>L'appliance quelques minutes après l'import : le bureau, 86 labs
  découverts, et le seul choix restant nommé avec la commande qui le règle.</em>
</p>

---

## Installer et jouer, en cinq minutes

Nécessite **Python 3.11+** et [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
ou `pipx` pour l'installer. Rien à cloner, rien à compiler.

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

## Ou : l'appliance, en quatre étapes

Pour Windows et macOS, où `uv tool install` n'est pas une option. Aucune
connaissance de la virtualisation n'est nécessaire.

1. **Installez VirtualBox** depuis
   <https://www.virtualbox.org/wiki/Downloads>. L'*Extension Pack* proposé
   n'est pas nécessaire.
2. **Téléchargez le fichier `.ova`** de la dernière
   [release](https://github.com/stephrobert/dsoxlab/releases) qui en porte un,
   et vérifiez son empreinte avec le `SHA256SUMS` publié à côté.
3. **Importez et démarrez** : dans VirtualBox, *Fichier → Importer un appareil
   virtuel*, choisissez le `.ova`, *Terminer*, puis *Démarrer*. Le premier
   démarrage installe dsoxlab, les hyperviseurs et le bureau, puis **redémarre
   tout seul** : comptez cinq à quinze minutes, sans rien taper.
4. **Connectez-vous** avec `student` / `dsoxlab` — la machine exige de changer
   ce mot de passe, qui est public — puis, dans le terminal du bureau :

   ```bash
   dsoxlab demo && cd ~/.local/share/dsoxlab/demo
   dsoxlab course premiers-pas
   ```

Les labs `vm` demandent une étape de plus, la **virtualisation imbriquée**, qui
s'active sur votre ordinateur et non dans la machine : *Configuration → Système
→ Processeur → Activer VT-x/AMD-V imbriqué*, appliance éteinte. `dsoxlab
doctor` le dit s'il manque.

Le détail de chaque étape, les prérequis chiffrés et un tableau de dépannage
sont dans **[la page de l'appliance](docs/appliance.fr.md)**.

---

## Documentation

Chaque page nomme son public dès ses premières lignes, et
[l'index](docs/README.fr.md) les répertorie toutes.

| Je veux… | Lire |
| --- | --- |
| Installer dsoxlab, jouer des labs, comprendre ma note | **[Pour l'apprenant](docs/learner.fr.md)** |
| Jouer des labs sous Windows ou macOS, sans rien installer | **[L'appliance](docs/appliance.fr.md)**, une VM prête à jouer |
| Écrire mon propre catalogue de labs | **[Pour l'auteur de catalogue](docs/catalog-author.fr.md)**, puis [le contrat v1](docs/contract-v1.fr.md) champ par champ |
| Monter les machines dont les labs ont besoin | **[Pour le formateur](docs/trainer.fr.md)** |
| Obtenir des VM jetables, sans aucun exercice à écrire | [L'infrastructure sans labs](docs/infra-only.fr.md) |
| Appeler dsoxlab depuis un script ou une CI, et décider sur le résultat | [Les codes de sortie](docs/exit-codes.fr.md), puis [la sortie machine](docs/machine-output.fr.md) pour `--json` |
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

## Remerciements

Plusieurs personnes extérieures au projet ont amélioré dsoxlab en remontant ce
sur quoi elles butaient, avec le diagnostic et souvent le correctif. Nommer ce
que chaque retour a changé paraît plus utile qu'une liste de pseudonymes.

**[@cedric-ribier](https://github.com/cedric-ribier)** est le plus persévérant,
et quatre versions viennent de ses remontées :

- `doctor` ne peint plus en rouge une installation saine à cause de tailles de
  disque nominales (0.1.94). Il a écrit que l'information était *déroutante*,
  ce qui était exactement le défaut : le contrôle comparait un maximum déclaré à
  une mesure ;
- le provisionnement KVM fonctionne de nouveau sur **libvirt 8** (0.1.92). Il a
  reproduit le défaut `os.firmware` du provider libvirt, documenté le
  contournement en amont, et c'est ce qui a rendu un correctif possible sur trois
  versions de libvirt ;
- l'agent Incus est installé sur AlmaLinux, dont le noyau RHEL n'a pas le driver
  9p, et l'attente de disponibilité des hôtes est devenue réglable (0.1.41). Les
  deux depuis un seul rapport, testé sur trois hôtes ;
- `doctor` nomme l'absence de virtualisation imbriquée au lieu de renvoyer au
  BIOS qu'une machine virtuelle n'a pas (0.1.95). Cela vient de son travail sur
  une image prête à l'emploi, discuté dans
  [#91](https://github.com/stephrobert/dsoxlab/issues/91).

**Et l'appliance elle-même est son idée.** Il ne l'a pas demandée : il l'avait
déjà **construite de bout en bout**, puis documentée dans
[#91](https://github.com/stephrobert/dsoxlab/issues/91). Celle que dsoxlab
publie aujourd'hui s'inspire directement de la sienne — l'idée comme la
démarche. C'est la contribution la moins visible dans un journal des
modifications et la plus structurante pour le produit : sans elle, il n'y
aurait rien à proposer à qui travaille sous Windows ou macOS.

**[@Gedd18](https://github.com/Gedd18)** a trouvé que le `conftest.py` du
catalogue de labs ne se chargeait plus dès qu'aucun provider d'infrastructure
n'était résolu, ce qui bloquait en silence **tous les labs `shell`**, c'est-à-dire
les premiers qu'un apprenant joue. Sa traceback est ce qui a transformé une
chasse en correctif de cinq minutes.

**[@VictorVare](https://github.com/VictorVare)** a diagnostiqué deux labs dont
l'état de départ était inutilisable : un port 80 fermé sur un backend, et un port
LDAP fermé. Dans les deux cas, il a distingué `No route to host` de
`Connection refused` et d'une expiration, ce qui a nommé la cause au lieu de nous
laisser hésiter entre HAProxy, SELinux et le pare-feu.

Si vous butez sur quelque chose, le rapport vaut mieux que le contournement :
`dsoxlab support --issue` remplit le diagnostic pour vous.

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
