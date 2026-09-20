# L'infrastructure sans labs

**Public :** qui a besoin de machines jetables et n'a aucun exercice à écrire.
Ni l'apprenant, qui n'ouvre jamais un `meta.yml`, ni l'auteur de catalogue, dont
la page est [catalog-author.fr.md](./catalog-author.fr.md).

**Langue :** [English](./infra-only.md) · [Français](./infra-only.fr.md)

dsoxlab pilote des labs pédagogiques, mais sa couche d'infrastructure, elle, n'en
sait rien. `provision`, `destroy`, `ssh` et `infra status` lisent le `meta.yml`
et rien d'autre : ni base de progression, ni score, ni indices, ni découverte de
labs. On peut donc se servir de dsoxlab comme d'un **fournisseur de VM
jetables**, sans écrire le moindre exercice.

Usages typiques : rejouer un tutoriel sur une machine propre avant de le publier,
reproduire un bogue sur trois distributions, obtenir un cluster qu'un conteneur
ne peut pas remplacer parce que le test exige un vrai noyau, systemd ou un
pare-feu.

## Le fichier, en entier

Un `meta.yml` à la racine d'un répertoire, et c'est tout :

```yaml
repo:
  id: ma-stack
  title: "VM jetables"

infra:
  provider: kvm
  network: lab-stack
  cidr: 10.10.90.0/24
  hosts:
    - name: db.lab
      distro: debian13
      ram_mb: 2048
    - name: app.lab
      distro: ubuntu24
```

Aucun répertoire `labs/`, aucun `repo.category`, aucun Terraform, aucun
cloud-init : les modèles des trois providers (kvm, incus, outscale) sont
empaquetés dans l'outil. `repo.id` est le seul champ requis ; il sert d'espace de
noms au state Terraform et à l'inventaire généré.

Ensuite :

```bash
dsoxlab provision        # terraform apply, puis attente du SSH sur chaque hôte
dsoxlab infra status     # qui répond, et pourquoi les muets se taisent
dsoxlab ssh db.lab       # un shell sur un nœud
dsoxlab destroy          # machines restées hors du state comprises
```

## Ce qui s'applique, et ce qui n'a pas d'objet

| Commande | Sur une stack sans lab |
| --- | --- |
| `provision`, `destroy`, `ssh`, `infra status` | fonctionnent pleinement |
| `doctor` | fonctionne, et classe terraform, l'hyperviseur et l'accès sortant en **requis** dès que `infra.hosts` n'est pas vide |
| `validate-structure` | passe, et ne dit rien de `repo.category` tant qu'aucun lab n'existe |
| `list-labs`, `show` | affichent « aucun lab trouvé », ce qui n'est pas une erreur |
| `run`, `check`, `submit`, `scores`, `progress`, `next`, `hint`, `course`, `challenge`, `guide` | sans objet : toutes réclament un lab |

Aucun `.dsoxlab.db` n'est créé tant qu'aucune commande n'écrit de progression.

## Où vit l'état

Rien n'est écrit dans votre répertoire, hormis `.dsoxlab-context.json`, qui porte
le provider actif. Tout le reste est à l'écart :

- State Terraform : `~/.local/state/dsoxlab/<repo-id>/terraform/<provider>/`
- Inventaire et `ssh_config` générés : `~/.cache/dsoxlab/<repo-id>/`
- Verrou d'écriture : `~/.local/state/dsoxlab/<repo-id>/dsoxlab.lock`
- Journal : `~/.local/state/dsoxlab/dsoxlab.log`

Deux comptes sont posés sur chaque nœud par le cloud-init, tous deux par clé
seule et sans mot de passe pour sudo : `ansible`, le compte de service
d'automatisation, celui avec lequel dsoxlab se connecte, et `student`, le compte
humain. Tout ce qui restreint la connexion doit viser `ansible`.

La clé publique `ssh/id_ed25519.pub` du répertoire est celle qui est déployée.
Créez la paire avec `dsoxlab instructor bootstrap` si vous n'en avez pas.

## Ses limites

**Les conteneurs ne passent pas par là.** `runtime.services` se déclare *par
lab*, dans `lab.yaml`, et son cycle de vie est porté par `run`, `check` et
`clean`. Il n'existe pas de stack de conteneurs au niveau du `meta.yml`. Pour du
conteneur, il faut un lab.

**Les adresses dérivent de la position.** L'IP et la MAC d'un hôte viennent de
son index dans `infra.hosts`. Insérer un hôte au milieu réassigne les suivants,
et libvirt refuse de mettre à jour un réseau existant. Ajoutez en fin de liste.

**Deux stacks KVM ne doivent pas tourner en même temps.** Les adresses MAC ne
portent pas de préfixe de dépôt : deux répertoires donnent la même adresse à
leurs VM de même index, et l'une des deux reste injoignable.

## Mélanger les deux

Rien n'interdit à une stack de porter aussi des labs : ce sont alors des labs
ordinaires, avec score, progression et indices. Si vous ne voulez y porter que
des suites de tests sans en faire des exercices, sachez que dsoxlab les traitera
malgré tout comme des labs.

## Pour aller plus loin

- [Le contrat v1](./contract-v1.fr.md), champ par champ
- [Où dsoxlab écrit](./files.fr.md)
- [Référence des commandes](./commands.fr.md)
