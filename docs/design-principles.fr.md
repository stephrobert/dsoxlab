# Les invariants du projet

**Public :** quiconque ajoute un contrôle, une commande ou un chemin d'échec à
dsoxlab — humain ou agent. C'est aussi ce qui permet à une relecture de dire
*non* en une phrase : « ce contrôle rend `ok` quand sa sonde échoue » est un motif
complet.

**Langue :** [English](./design-principles.md) · [Français](./design-principles.fr.md)

Chaque règle ci-dessous était déjà appliquée sans avoir été écrite, et chacune a
été découverte **le jour où elle a été violée**. D'où l'incident qui accompagne
chacune : un principe sans son bug se discute, un principe avec son bug se
respecte.

La troisième colonne est celle qu'il faut lire deux fois. Elle nomme le test qui
tient la règle — et là où elle dit *pas encore gardé*, c'est un manque assumé, pas
un oubli qu'on cache.

---

## Mesurer

**Un contrôle qui n'a pas pu regarder ne conclut jamais au vert.**

| Invariant | Ce qui l'a révélé | Tenu par |
| --- | --- | --- |
| Une sonde qui n'a pas pu regarder ne conclut pas au vert. Un contrôle a **trois** issues — `ok`, `failed`, `unknown` — et `unknown` a son propre code de sortie (`10`), parce qu'un script ne peut rien conclure d'une mesure qui n'a pas eu lieu | issue #172 : un pool libvirt illisible était rendu comme allant bien. Tout le lot #172 → #179 avait cette seule forme | `tests/test_doctor_strict.py`, `tests/test_note_sans_mesure.py` |
| Zéro test exécuté n'est pas une note de zéro. Un `conftest.py` qui lève à l'import, une machine injoignable, une dépendance absente donnent tous `total == 0`, c'est-à-dire une absence de mesure et non un échec | issue #168 : le 0 était inscrit en base comme une note | `tests/test_note_sans_mesure.py` |
| **Une adresse n'est pas une machine.** Un hôte présent dans le state Terraform n'est pas un hôte qui répond | `dsoxlab start` annonçait « déjà provisionné, rien à reconstruire » juste après un `provision` sorti en 8 sur « l'infrastructure existe, mais elle n'est pas utilisable en l'état ». Il tranchait sur le state seul. Corrigé en 0.2.2 : il sonde le port 22 | `tests/test_start_sequence.py` |
| **Provisionné n'est pas utilisable.** Un Terraform qui rend 0 dit que les ressources existent, pas que le lab peut tourner | issues #170, #178 — d'où le code de sortie `8`, et `dsoxlab infra status` qui nomme l'hôte resté muet | `tests/test_host_ready_timeout.py`, `tests/test_codes_de_sortie.py` |
| **Une commande exécutée n'est pas un état atteint.** On ne vérifie jamais qu'une commande a été tapée, on vérifie l'état du système | la machine d'état des labs, et `pytest-testinfra` comme outil de validation | les suites de tests des catalogues |
| **Vérifier n'est pas parser.** `ast.parse` accepte un module Python dont une substitution malheureuse a supprimé une variable : le fichier est valide et lève un `NameError` au premier appel. Même écart entre `terraform validate` et `terraform apply` | écrit dans les règles de travail du projet avant d'avoir un nom | `tests/test_contrat_honore.py` (le comportement, pas la forme) |
| **Un workflow qui n'a jamais tourné est un workflow qui ne marche pas**, quelle que soit l'analyse statique qui l'approuve | `actionlint`, `zizmor` et `poutine` passaient tous sur le workflow de l'appliance. Il a fallu trois versions pour qu'il aboutisse : `/mnt` appartient à root, Packer refuse un répertoire de sortie préexistant, `/dev/kvm` n'est pas ouvrable par le compte `runner`. Le job KVM l'a redit en cinq exécutions et quatre défauts — un nom de pont trop long d'un caractère, `ovmf` absent, un pool de stockage jamais défini, `qemu-utils` écarté par `--no-install-recommends` — chacun nommé par le message de dsoxlab lui-même | `.github/workflows/kvm.yml` (issue #243) : quand le runner expose `/dev/kvm`, le template `kvm` est appliqué pour de vrai, un hôte doit répondre, et `destroy` ne doit rien laisser derrière lui. Sans `/dev/kvm`, le job le dit et ne conclut rien |
| **Un contrôle qui n'emploie pas le lecteur du destinataire ne contrôle rien** | issue #279 : l'OVA de l'appliance était vérifiée par `tar`, `xmllint` et `sha256sum` — trois outils qui lisent un *fichier* — et importée sous VirtualBox, qui ne vérifie pas le manifeste. VMware lit un *flux*, s'arrête à son marqueur de fin, et empreignait 64 512 octets de moins que ce que notre manifeste déclarait. Le disque était intact : seules les deux lectures divergeaient | `tests/test_ova_flux_vmdk.py`, et la fabrique refuse désormais de livrer une image dont l'empreinte du fichier n'est pas aussi celle de son flux |

---

## Le dire

**Un échec qui ne se dit pas est pire qu'un échec.**

| Invariant | Ce qui l'a révélé | Tenu par |
| --- | --- | --- |
| Un échec qui ne se dit pas est pire qu'un échec. Tout chemin d'échec reçoit un code **et** un message | issues #170, #173, #179 : `destroy` sortait en succès en laissant des machines debout, `doctor` affichait « ok » sur un terraform inutilisable, un snapshot en échec était avalé dans un `logger.warning` | `tests/test_codes_de_sortie.py`, `docs/exit-codes.fr.md` |
| **Un marqueur de travail accompli ne s'écrit qu'après le succès.** Sinon il condamne la machine en silence | le premier démarrage de l'appliance se marquait fait même quand le réseau était absent et que rien n'avait été installé — sans plus aucun moyen de se rattraper | `packer/scripts/30-premier-demarrage.sh` accumule les échecs et sort en 1 sans poser le marqueur ; *pas gardé par un test* |
| **La sortie humaine n'est pas l'interface machine.** `--json` porte une `key` stable et un `state` en jeton, et seulement ensuite un libellé traduit. Recopier le texte affiché dans un champ rend une intégration inutilisable tout en paraissant complète | le chantier `--json` : personne ne peut savoir si c'est vert ou rouge sans analyser du français ou de l'anglais | `tests/test_json_output.py`, `tests/test_json_schemas.py` |
| **Le journal s'écrit en anglais**, et il n'est pas de l'interface | le journal mélangeait le français et l'anglais ; c'est le fichier que `dsoxlab support` collecte, qui se cherche mot pour mot et se compare entre machines aux locales différentes | `tests/test_journal_en_anglais.py` |
| **Tout texte affiché passe par `_()`**, dans les deux langues à la fois | la dette soldée en 0.1.34 valait dans les deux sens : des messages français s'affichaient sous `DSOXLAB_LANG=en`, et tous les libellés de barres de progression restaient anglais sous `DSOXLAB_LANG=fr` | `tests/test_i18n_coverage.py`, `tests/test_cles_i18n_existantes.py` |

---

## Le contrat

| Invariant | Ce qui l'a révélé | Tenu par |
| --- | --- | --- |
| **Une fixture déclarée et absente n'est pas un workdir partiel.** Tout ou rien : la validation précède toute copie, et nomme toutes les fautives d'un coup | issue #177 — un `challenge/work` à moitié rempli a l'air de marcher, et l'apprenant cherche alors l'erreur dans son propre travail. Sept labs de `terraform-training` étaient injouables le 2026-07-28, tous marqués faits | `tests/test_fixtures_declarees.py`, `tests/test_shell_fixtures.py` |
| **Un catalogue est une entrée non fiable. Une valeur du contrat est une donnée, jamais une instruction.** Le modèle entier est écrit une seule fois, dans [le modèle de menace](./security.fr.md) | un `doc_url` en `javascript:` atteignait `webbrowser.open()` ; un `title` portant un balisage Rich non apparié faisait sortir `list-labs` et `show` en trace Python | `tests/test_securite_urls.py`, `tests/test_securite_terminal.py`, `tests/test_securite_identifiants.py` |
| **Le parseur est tolérant, le validator est strict.** Un `lab.yaml` continue de charger ; `validate-structure` est le lint qui le dit à l'auteur. Un lint n'est pas une barrière de sécurité — il n'est ni automatique, ni exigé avant d'utiliser un catalogue | la v1 garantit qu'un lab ne disparaît pas parce qu'un champ est nouveau ; et les contrôles de sécurité sont rejoués au point d'usage pour exactement cette raison | `tests/test_yaml_contract.py`, `tests/test_validator_voit_tout.py` |
| **Une documentation qui dérive est pire qu'absente** : elle fait écrire du faux avec assurance | la table des commandes décrivait un `cleanup.sh` que le contrat interdit ; la section persistance annonçait une base qui n'a jamais existé (issue #86) | `tests/test_documentation_synchrone.py`, `tests/test_doc_auteur_couvre_les_controles.py` |

---

## Ce que le projet promet

Ce sont des engagements envers qui intègre dsoxlab. Ils étaient tranchés dans les
faits bien avant d'être écrits ici, ce qui est tout l'intérêt de les écrire.

### Le contrat d'entrée (`meta.yml` / `lab.yaml`), version 1

- **Ajouter un champ optionnel est toujours permis**, et n'exige rien des
  catalogues existants.
- **Retirer un champ, ou changer le sens de l'un d'eux, ne l'est pas.** Cela
  imposerait un `schema_version: 2`, et un moteur qui lit une version qu'il ne
  connaît pas le dit et nomme le fichier — il ne fait pas disparaître le lab.
- **Le parseur reste tolérant** sur les valeurs : un champ malformé lève dans le
  contrat du parseur (`KeyError`, `ValueError`, `yaml.YAMLError`), donc un lab
  fautif est écarté avec un avertissement au lieu de faire tomber la CLI.
- **Les alias `kvm` et `incus` de `runtime.type` sont maintenus** par
  rétro-compatibilité, et traités exactement comme `vm`. Aucun retrait n'est
  prévu ; un nouveau lab écrit `vm`.

### La sortie machine

- `reporting/machine.py` porte `SCHEMA = 1`, qui évolue **indépendamment de la
  version du paquet**. Un ajout de champ garde la compatibilité ; un champ qui
  change de sens ou disparaît l'incrémente.
- Le document de preuve se nomme autrement, à dessein :
  `"schema": "dsoxlab-evidence-v1"`, une **chaîne**, parce que ce document quitte
  dsoxlab et que `{"schema": 1}` ne dit pas de quoi il est le schéma 1.
- Ses champs sont construits par **liste blanche**. Voir [la sortie
  machine](./machine-output.fr.md) pour ce qui ne doit jamais y figurer.

### Les codes de sortie

Les codes listés dans [les codes de sortie](./exit-codes.fr.md) **ne changent
plus de sens**. Un code n'a ni schéma, ni version, ni message : un script qui lit
`7` aujourd'hui doit lire `7` demain. Les nouveaux chemins d'échec reçoivent de
nouveaux codes.

---

## Ajouter à ce document

Deux règles, et c'est la seconde qui le garde honnête.

**Un invariant, un incident.** Si vous ne pouvez pas nommer ce qui est allé de
travers, c'est une préférence, et une préférence appartient à un commentaire de
relecture plutôt qu'à cette page.

**Nommez le test, ou dites qu'il n'y en a pas.** La troisième colonne est ce qui
transforme une liste de bonnes intentions en carte de ce qui est réellement
gardé — et de ce qui ne l'est pas. Une règle sans test est une règle qui attend
sa régression.
