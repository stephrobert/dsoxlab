# Où dsoxlab écrit

**Public :** apprenants, auteurs de catalogue et formateurs. C'est la page de
référence commune aux trois, et le seul endroit où ces emplacements sont écrits.

**Langue :** [English](./files.md) · [Français](./files.fr.md)

dsoxlab conserve son état à deux endroits, et nulle part ailleurs : **dans le
catalogue que vous jouez**, et **sous votre répertoire personnel**. La
progression appartient au premier, elle est donc **par catalogue** : deux
catalogues côte à côte gardent des historiques séparés, et supprimer un
catalogue supprime le sien avec lui.

---

## Dans le dépôt du catalogue

| Chemin | Contenu | Écrit par |
| --- | --- | --- |
| `<catalogue>/.dsoxlab.db` | Base SQLite : `results` (les notes) et `hint_requests` | `check`, `submit`, `hint` |
| `<catalogue>/.dsoxlab-context.json` | Section, niveau, langue, lab, cible et provider actifs, plus la position de lecture du cours | `use`, `run`, `course` |

Les deux sont à ignorer dans le `.gitignore` du catalogue. Aucun des deux ne se
déplace : ils **sont** le dépôt, et c'est ce qui fait suivre la progression au
catalogue plutôt qu'à la machine.

Un catalogue qui déclare des labs `vm` porte aussi sa propre paire de clés SSH,
sous `<catalogue>/ssh/id_ed25519` et son `.pub`, produite par
`dsoxlab instructor bootstrap`. La moitié privée ne se commite jamais.

---

## Sous votre répertoire personnel

| Chemin | Contenu | Déplacé par |
| --- | --- | --- |
| `~/.local/state/dsoxlab/dsoxlab.log` | Journal complet de chaque commande, quelle que soit la verbosité | `XDG_STATE_HOME` |
| `~/.local/state/dsoxlab/<catalog-id>/terraform/<provider>/` | Répertoire de travail et state Terraform | `XDG_STATE_HOME` |
| `~/.local/state/dsoxlab/<catalog-id>/cloud-init/` | Templates cloud-init recopiés depuis l'outil pour le provisioning | `XDG_STATE_HOME` |
| `~/.local/state/dsoxlab/<catalog-id>/dsoxlab.lock` | Verrou d'écriture de ce catalogue (`flock`) | `XDG_STATE_HOME` |
| `~/.cache/dsoxlab/<catalog-id>/inventory.json` | Inventaire Ansible généré | `XDG_CACHE_HOME` |
| `~/.cache/dsoxlab/<catalog-id>/ssh_config` | Configuration OpenSSH générée pour les hôtes du lab | `XDG_CACHE_HOME` |
| `~/.cache/dsoxlab/version-check.json` | Dernière version vue sur PyPI, et sa date | `XDG_CACHE_HOME` |
| `~/.local/share/dsoxlab/demo/` | Catalogue de démonstration installé par `dsoxlab demo` | `XDG_DATA_HOME` |
| `~/.local/share/dsoxlab/catalogs/` | Catalogues installés par `dsoxlab catalog add`, un sous-répertoire par identifiant | `XDG_DATA_HOME` |
| `~/.local/state/dsoxlab/<catalog-id>/labs/` | Points de départ du travail, pour distinguer un lab *prêt* d'un lab *en cours* | `XDG_STATE_HOME` |
| `~/.local/state/dsoxlab/catalogue-actif` | Identifiant du catalogue actif, celui qu'on utilise sans se placer dans son répertoire | `XDG_STATE_HOME` |
| `~/.ssh/config.d/<catalog-id>.conf` | Fragment SSH des hôtes du lab, pour que `ssh`, `scp` et votre IDE les atteignent par leur nom | aucune |

`<catalog-id>` est le `repo.id` du `meta.yml` du catalogue. Le verrou retombe
sur le nom du répertoire suffixé d'une empreinte de son chemin absolu quand
aucun `meta.yml` n'est lisible : deux clones du même catalogue partagent ainsi
un seul verrou et un seul state Terraform.

Le state Terraform est délibérément **hors** du catalogue : un state posé dans
un dépôt de labs finit commité, et un state commité ment.

Deux de ces fichiers sont des caches, et les perdre ne coûte qu'une
régénération : `inventory.json` et `ssh_config` sont reconstruits à la prochaine
commande qui en a besoin. Tout ce qui pointerait sur le `ssh_config` généré (un
`Include`, un profil d'IDE) doit donc tolérer sa disparition.

`dsoxlab completion install` écrit en dehors de ces deux familles, une fois :
la complétion (`~/.zfunc/_dsoxlab` plus une ligne dans `~/.zshrc`, ou
`~/.bash_completion.d/dsoxlab` plus une ligne dans `~/.bashrc`).

Jusqu'en 0.1.61, `dsoxlab install` écrivait aussi un wrapper dans
`~/.local/bin/dsoxlab`. Ce n'est plus le cas : `uv tool install` et `pipx` y
posent leur lanceur, et écrire par-dessus un lien symbolique écrit dans sa
cible. S'il en reste un d'une ancienne installation, il vous appartient de le
retirer.

---

## Ce qui n'existe pas

Ces chemins ont été documentés par le passé. Ils figurent ici pour que personne
ne les cherche à nouveau :

- **Aucun `~/.config/dsoxlab/config.yaml`, et aucun fichier de configuration
  utilisateur.** Ce qui se règle passe par le contrat (`meta.yml`), par le
  contexte actif (`dsoxlab use`) ou par une variable d'environnement. La
  découverte multi-catalogues par un tel fichier est prévue
  ([#78](https://github.com/stephrobert/dsoxlab/issues/78)) ; tant qu'elle n'est
  pas livrée, aucun code ne lit ce chemin.
- **Aucun `~/.local/share/dsoxlab/progress.db`.** Les notes vivent dans
  `<catalogue>/.dsoxlab.db`, catalogue par catalogue.
- **`XDG_CONFIG_HOME` n'est lue nulle part.** Les trois variables ci-dessus sont
  les seules variables XDG que dsoxlab honore.

---

## Variables d'environnement

| Variable | Effet |
| --- | --- |
| `LAB_HOME` | Racine du catalogue à jouer, au lieu de la détection automatique |
| `DSOXLAB_LANG` | Langue d'affichage (`en` / `fr`), prioritaire sur le fichier de contexte |
| `DSOXLAB_PROVIDER` | Provider d'infrastructure, prioritaire sur `dsoxlab use --provider` |
| `DSOXLAB_TARGET` | Cible par défaut d'un lab `vm`, quand la session n'en fixe aucune |
| `DSOXLAB_PAGER` | Pagineur de `course` et `challenge` (puis `PAGER`, défaut `less -R`) |
| `DSOXLAB_LOG` | `DSOXLAB_LOG=debug` équivaut à `-vv` |
| `DSOXLAB_HOST_READY_TIMEOUT` | Secondes d'attente d'un hôte fraîchement provisionné (défaut 180) |
| `DSOXLAB_NO_UPDATE_CHECK` | À `1`, coupe l'avis quotidien de nouvelle version |
| `DSOXLAB_OUTSCALE_PROFILE`, `DSOXLAB_AWS_PROFILE` | Profil d'identifiants de ces providers |

Deux autres sont **posées par dsoxlab** pour que les tests d'un lab les lisent,
et ne se règlent pas à la main : `DSOXLAB_TARGET_HOST` (l'hôte que les tests
doivent inspecter, ce qui permet à un lab multi-distributions de valider la
cible choisie) et `DSOXLAB_LAB_SESSION` (l'identifiant du lab, dans la session
ouverte par `run`).

---

## Cette page ne peut plus dériver

`tests/test_documentation_synchrone.py` dérive les emplacements réels **en
appelant le code**, les mêmes fonctions que la CLI appelle, et échoue dès qu'un
chemin cité dans une page de documentation ne correspond à aucun d'eux. Les faux
`progress.db` et `config.yaml` ci-dessus sont ce qui l'a motivé : ils sont
restés documentés des mois durant, faute de quelqu'un pour lire la documentation
et le code en même temps.
