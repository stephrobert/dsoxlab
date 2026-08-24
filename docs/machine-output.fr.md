# La sortie machine

**Public :** vous écrivez quelque chose qui *lit* dsoxlab : une extension
d'éditeur, un tableau de bord, une étape de CI, un script de suivi. Cette page
est le contrat sur lequel vous pouvez vous appuyer, et la seule partie de la
sortie faite pour être analysée.

**Langue :** [English](./machine-output.md) · [Français](./machine-output.fr.md)

Tout le reste de ce que dsoxlab affiche est fait pour des yeux : des tableaux
Rich dont la largeur suit le terminal, des couleurs, des barres de progression.
C'est fait pour bouger. `--json` rend un document à la place, et cette page dit
ce qu'il y a dedans.

---

## Trois règles

**1. La sortie standard porte le document, et rien d'autre.** En mode `--json`,
le rappel du contexte actif, les astuces et l'avis de mise à jour partent tous
sur la sortie d'erreur. `json.loads(stdout)` fonctionne donc sans rien retirer,
et c'est exactement ainsi que la suite de tests l'exige : un message glissé
devant le document, ou une barre de progression restée derrière, la fait lever.

**2. Chaque document porte un `schema`.** C'est son premier champ, et il dit à
un consommateur s'il parle la même langue avant qu'il ne lise le reste. La
valeur courante est **1**.

**3. Un verdict se lit dans une clé et un état, jamais dans un libellé.** Les
contrôles et les anomalies portent un identifiant stable (`key`) et, quand il y
a verdict, un état en jeton (`ok`, `failed`, `choice_required`). Le libellé
traduit est posé *à côté*, pour l'affichage. Aucune intégration ne devrait avoir
à analyser du français ou de l'anglais pour savoir si c'est vert ou rouge.

Et une conséquence qui mérite d'être dite à part : **`--json` change la forme de
la sortie, jamais le verdict ni le code de retour.** Un `check` sur un lab en
échec sort en 1 avec ou sans lui ; `validate-structure` sort en 1 dès qu'un lab
échoue ; `doctor` sort en 0 dans les deux modes et met son verdict dans `ok`
(c'est `--strict`, et non `--json`, qui en fait un code de sortie).
Sur une erreur *dure* : identifiant de lab inconnu, `meta.yml` illisible, la
sortie standard reste vide, la cause part sur la sortie d'erreur, et le code ne
bouge pas. Lisez le code de retour d'abord.

---

## Les commandes qui prennent `--json`

| Commande | Document | Codes de retour |
| --- | --- | --- |
| `dsoxlab list-labs` | le catalogue | 0 |
| `dsoxlab show <id>` | un lab et l'état de son runtime | 0, ou 1 si l'identifiant est inconnu (aucun document) |
| `dsoxlab progress` | le catalogue et un résumé de progression | 0 |
| `dsoxlab next` | le lab suggéré et ce qui reste | 0, ou 1 sans contexte actif (aucun document) |
| `dsoxlab scores` | l'historique des notes et les verdicts d'examen | 0 |
| `dsoxlab check <id>` | le résultat des tests et la note | 0, ou 1 si le lab échoue (le document est rendu quand même) |
| `dsoxlab status` | la joignabilité SSH des hôtes déclarés | 0, ou 1 dès qu'un hôte déclaré ne répond pas (le document est rendu quand même) |
| `dsoxlab doctor` | le diagnostic de l'environnement | 0, toujours : le verdict est dans `ok`. Avec `--strict`, 9 (un requis échoue) ou 10 (un requis n'a pas pu être mesuré) |
| `dsoxlab validate-structure` | chaque anomalie de contrat trouvée | 0, ou 1 dès qu'un lab échoue (le document est rendu quand même) |
| `dsoxlab support` | le rapport de diagnostic anonymisé | 0 |

`doctor --json --fix` est refusé, et le dit sur la sortie d'erreur : les
commandes de remédiation écrivent sur la sortie standard, et le document en
deviendrait illisible. On lit le diagnostic d'abord, on agit ensuite.

---

## L'objet lab

Cinq documents (`list-labs`, `show`, `progress`, `next` et `check`) embarquent
le même objet lab. Il est décrit une fois, ici.

| Champ | Type | Sens |
| --- | --- | --- |
| `id` | chaîne | l'identifiant du lab, unique dans le catalogue, et la clé que prennent les commandes |
| `title` | chaîne | titre d'affichage, dans la langue du catalogue |
| `section` | chaîne | la section d'appartenance, `repo.category` par défaut |
| `bloc` | entier ou null | le bloc pédagogique, dérivé de la position dans le `meta.yml` |
| `bloc_order` | entier ou null | le rang dans ce bloc : c'est l'ordre que suit `next` |
| `level` | chaîne | niveau libre (`l1`, `rhcsa`…) |
| `type` | chaîne | `lab`, `challenge` ou `capstone` |
| `exam_passing_score` | entier ou null | seuil de réussite, en pourcentage du barème. `null` sur un lab ordinaire |
| `difficulty` | chaîne ou null | libre, jamais validé |
| `estimated_time` | chaîne ou null | libre, par exemple `"30m"` |
| `skills` | liste de chaînes | jamais vide : le validator l'exige |
| `distros` | liste de chaînes | jamais vide, de même |
| `doc_url` | chaîne | le guide en ligne, en `http` ou `https` |
| `path` | chaîne | chemin **absolu** du répertoire du lab, pour qu'un éditeur puisse ouvrir ses fichiers |
| `runtime.type` | chaîne | `shell` ou `vm` |
| `runtime.session` | chaîne | `target` ou `local` |
| `runtime.target` | chaîne ou null | l'hôte cible résolu, `null` sur un lab `shell` |
| `runtime.workdir` | chaîne | répertoire de travail, relatif à `path` |
| `best_score` | objet ou null | `{"points": entier, "max": entier}`, ou `null` quand le lab n'a **jamais été tenté** |

`best_score: null` n'est pas un zéro. Un lab jamais joué et un lab joué puis raté
sont deux états différents, et une interface qui les confond raconte à
l'apprenant quelque chose de faux.

---

## `list-labs`

```json
{
  "schema": 1,
  "labs": [ { "id": "l1-first-terminal", "…": "…" } ],
  "count": 20
}
```

| Champ | Type | Sens |
| --- | --- | --- |
| `labs` | liste d'objets lab | filtrée par les options et par le contexte actif |
| `count` | entier | la taille de `labs`, pour qu'un consommateur n'ait pas à la calculer |

## `show`

```json
{
  "schema": 1,
  "lab": { "id": "l1-first-terminal", "…": "…" },
  "status": "ready"
}
```

| Champ | Type | Sens |
| --- | --- | --- |
| `lab` | objet lab | avec son `best_score` |
| `status` | chaîne ou null | `ready`, `stopped`, ou `null` quand le runtime ne sait pas répondre |

`status` est un jeton, pas une phrase : il ne suit pas la langue d'affichage.

## `progress`

```json
{
  "schema": 1,
  "labs": [ { "…": "…" } ],
  "summary": { "total": 84, "attempted": 12, "points": 940, "max_points": 1200 }
}
```

| Champ | Type | Sens |
| --- | --- | --- |
| `labs` | liste d'objets lab | triée par `bloc`, puis `bloc_order`, puis `id` |
| `summary.total` | entier | labs dans le périmètre |
| `summary.attempted` | entier | labs qui portent au moins un résultat |
| `summary.points` | entier | points obtenus, sommés sur les seuls labs tentés |
| `summary.max_points` | entier | le barème de ces mêmes labs |

## `next`

```json
{
  "schema": 1,
  "context": { "section": "l1", "level": null },
  "next": { "id": "l1-first-terminal", "…": "…" },
  "all_done": false,
  "remaining": 12
}
```

| Champ | Type | Sens |
| --- | --- | --- |
| `context.section` | chaîne | la section active : `next` en exige une, et sort en 1 sans |
| `context.level` | chaîne ou null | le niveau actif, s'il y en a un |
| `next` | objet lab ou null | le premier lab sans résultat enregistré, dans l'ordre pédagogique |
| `all_done` | booléen | vrai seulement si la section porte des labs et que tous ont un résultat |
| `remaining` | entier | labs sans aucun résultat enregistré |

`all_done` et `next: null` ne disent pas la même chose : une section vide rend
elle aussi `next: null`, et un consommateur qui féliciterait l'apprenant
fêterait un parcours qui n'a jamais commencé.

## `scores`

```json
{
  "schema": 1,
  "results": [
    {
      "lab_id": "aws-provider-aws-first-ec2",
      "section": "aws",
      "score": 100,
      "max_score": 100,
      "passed_tests": 11,
      "total_tests": 11,
      "hints_used": 0,
      "validated_at": "2026-08-13T13:30:12.831759+00:00",
      "exam": null
    }
  ],
  "count": 1
}
```

| Champ | Type | Sens |
| --- | --- | --- |
| `results` | liste | les plus récents d'abord, bornée par `--top` |
| `results[].score` / `max_score` | entier | la note enregistrée et son barème |
| `results[].passed_tests` / `total_tests` | entier | ce que pytest a rapporté |
| `results[].hints_used` | entier | indices pris, c'est-à-dire ce qui a fait baisser la note |
| `results[].validated_at` | chaîne | ISO 8601, en UTC |
| `results[].exam` | objet ou null | `null` sur un lab ordinaire ; sinon `{"passing_score", "percentage", "passed"}` |

`exam: null` veut dire *ce n'est pas un examen*, et ce n'est délibérément pas
`false` : un lab ordinaire n'est pas un examen recalé. La comparaison derrière
`passed` se fait en entiers, jamais sur un pourcentage arrondi : un seuil
d'examen ne s'arrondit pas en faveur du candidat.

## `check`

```json
{
  "schema": 1,
  "lab": { "id": "premiers-pas", "…": "…" },
  "check": {
    "ok": true,
    "passed": 3,
    "total": 3,
    "score": 100,
    "max_score": 100,
    "output": "=== test session starts ===\n…"
  }
}
```

| Champ | Type | Sens |
| --- | --- | --- |
| `check.ok` | booléen | tous les tests passent |
| `check.passed` / `total` | entier | tests réussis, tests joués |
| `check.score` / `max_score` | entier | la note enregistrée dans la base du catalogue |
| `check.output` | chaîne | la sortie brute de pytest, où vit le détail d'un échec |

La commande sort en 1 quand `ok` vaut faux, et rend le document quand même.

## `status`

L'état du lab actif, ou de celui qu'on nomme.

```json
{
  "schema": 1,
  "lab": "l2-swap-management",
  "state": "in_progress",
  "label": "en cours",
  "detail": "Le travail a commencé dans /chemin/challenge/work",
  "best_score": null,
  "max_score": null
}
```

| Champ | Type | Sens |
| --- | --- | --- |
| `lab` | chaîne ou null | l'identifiant du lab ; `null` quand aucun n'est actif |
| `state` | chaîne ou null | un **jeton stable**, voir la table ci-dessous |
| `label` | chaîne | le même état, traduit, pour les yeux |
| `detail` | chaîne | ce qui a été observé, et le geste qui suit |
| `best_score` / `max_score` | entier ou null | la meilleure note obtenue, s'il y en a une |

| `state` | Ce qu'il veut dire |
| --- | --- |
| `not_started` | rien n'est préparé pour ce lab |
| `ready` | l'environnement est prêt, et rien n'y a été touché |
| `in_progress` | le travail a commencé |
| `validated` | une note a été obtenue |
| `degraded` | un service déclaré ne tourne plus : le lab est injouable en l'état |

`state` et `label` sont séparés à dessein. Une intégration qui filtre sur
« validé » ne doit pas dépendre de la langue de qui a lancé la commande : le
jeton ne bouge pas, le libellé suit `DSOXLAB_LANG`.

`ready` et `in_progress` ne diffèrent que par le contenu du répertoire de
travail, comparé à l'empreinte que `run` a retenue au moment de le préparer.
Sur un lab `vm`, ce travail se fait sur la machine et aucune empreinte locale ne
le verrait : l'état y vaut `in_progress` dès la préparation, et le `detail` le
dit plutôt que de laisser croire à une mesure qui n'a pas eu lieu.

## `infra status`

Portait le nom `status` jusqu'en 0.1.67.


```json
{
  "schema": 1,
  "provider": "kvm",
  "hypervisor": { "queryable": true, "error": null },
  "hosts": [
    {
      "fqdn": "alma-rhcsa-1.lab",
      "ip": "10.10.10.11",
      "reachable": false,
      "reason": "Connection timed out",
      "domain": "alma-rhcsa-1",
      "domain_state": "shut off",
      "cause": "domain_not_running"
    }
  ],
  "summary": { "reachable": 0, "total": 1 }
}
```

| Champ | Type | Sens |
| --- | --- | --- |
| `provider` | chaîne ou null | le provider d'infra actif ; `null` sur un catalogue sans hôte |
| `hypervisor.queryable` | booléen | l'état des machines a-t-il pu être demandé au backend |
| `hypervisor.error` | chaîne ou null | pourquoi il ne l'a pas pu, le cas échéant |
| `hosts[].reachable` | booléen | SSH a répondu |
| `hosts[].reason` | chaîne ou null | la dernière ligne de l'échec SSH, quand il y en a eu un |
| `hosts[].domain` / `domain_state` | chaîne ou null | ce que dit l'hyperviseur, quand on peut le lui demander |
| `hosts[].cause` | chaîne | un **jeton stable** qui nomme le diagnostic, pas une phrase |
| `summary.reachable` / `total` | entier | hôtes qui ont répondu, hôtes déclarés |

La commande sort en 1 dès qu'un hôte déclaré ne répond pas, et rend le document
quand même : c'est justement lui qui dit lequel, et pourquoi.

Un catalogue sans bloc `infra:` est un cas normal, pas une erreur : il rend
`provider: null`, `hosts: []` et un résumé à zéro, et sort en 0.

## `doctor`

```json
{
  "schema": 1,
  "ok": true,
  "required": [
    {
      "key": "pytest",
      "state": "ok",
      "ok": true,
      "label": "pytest",
      "detail": "embarqué avec dsoxlab (celui qu'utilise « check »)",
      "fix": null,
      "fix_kind": null,
      "hint": null
    }
  ],
  "informational": [
    {
      "key": "kvm",
      "state": "failed",
      "ok": false,
      "label": "virsh/KVM",
      "detail": "virsh introuvable",
      "fix": "sudo apt install libvirt-clients libvirt-daemon-system qemu-kvm",
      "fix_kind": "automatic",
      "hint": null
    }
  ],
  "notes": ["Aucun lab de ce dépôt n'utilise de VM : les hyperviseurs ci-dessus sont informatifs."]
}
```

| Champ | Type | Sens |
| --- | --- | --- |
| `ok` | booléen | **le verdict**, et il ne porte que sur `required` |
| `required` | liste de contrôles | ce qui bloque *ce* catalogue |
| `informational` | liste de contrôles | composants dont ce catalogue n'a pas besoin, jamais une erreur |
| `notes` | liste de chaînes | phrases traduites qui expliquent *pourquoi* un composant est informatif ici |

Chaque contrôle :

| Champ | Type | Sens |
| --- | --- | --- |
| `key` | chaîne | **l'identité stable** : `python`, `pytest`, `shell`, `provider`, `kvm`, `incus`, `terraform`, `ansible`, `libvirt_pool`, `iso_tool`, `hw_virt`, `cpu_arch`, `resources`, `labs`, `lab_home` |
| `state` | chaîne | `ok`, `failed`, `choice_required` ou `unknown` |
| `ok` | booléen | la même chose que `state == "ok"`, gardé pour une lecture vert/rouge immédiate |
| `label` | chaîne | le nom du composant, traduit : pour l'affichage seulement |
| `detail` | chaîne | ce qui a été mesuré : une version, une ligne d'erreur, un compte |
| `fix` | chaîne ou null | la remédiation sous sa forme lisible ; `dsoxlab doctor --fix` joue les mêmes commandes token par token, sans shell |
| `fix_kind` | chaîne ou null | la catégorie de la remédiation : `automatic`, `manual` (affichée, jamais exécutée), `needs_relogin` ou `needs_reboot` (exécutée, mais le contrôle reste rouge jusqu'à la reconnexion ou au redémarrage) |
| `hint` | chaîne ou null | un geste que seul un humain doit poser : une page d'installation, une décision |

`state: choice_required` existe parce qu'une décision n'est pas une panne : un
catalogue qui déclare plusieurs providers sans qu'aucun soit choisi bloque bien
le provisionnement, mais rien n'est cassé, et l'afficher en rouge reviendrait à
traiter un choix comme une avarie.

`state: unknown` existe parce qu'une sonde impossible ne prouve rien, dans
aucun sens : un contrôle dont la mesure a échoué (un `/proc/meminfo` illisible,
un pool libvirt qui ne répond pas) n'est ni le vert rassurant d'un `ok` non
mérité, ni le rouge accusateur d'une panne non prouvée. Son champ `ok` vaut
`false`, puisque rien n'a été vérifié, mais il ne compte pas dans le verdict
global.

`ok` ne porte que sur `required`, délibérément. Un hyperviseur que ce catalogue
n'utilisera jamais n'a pas à peindre en rouge une machine qui va très bien.

`fix` et `hint` restent séparés à dessein : l'un est une commande, l'autre une
phrase. Les fondre ferait exécuter une URL de documentation par une
automatisation.

`fix_kind` est ce qu'une automatisation doit lire avant d'agir sur `fix` :
une remédiation `manual` n'est jamais exécutée par `--fix`, et une
`needs_relogin` ou `needs_reboot` réussit alors que son contrôle continue de
rapporter `failed` jusqu'à la reconnexion ou au redémarrage. C'est un effet
différé, pas un échec.

### Le code de sortie, et les deux modes

Par défaut, `doctor` sort en **0 quoi qu'il arrive** : le verdict est dans `ok`.
C'est le bon choix pour un humain — un diagnostic n'est pas un échec — mais il
rend la commande inutilisable comme portail, un script devant lire le document
pour savoir si quelque chose manque.

`--strict` traduit le diagnostic en code de sortie. Il ne change **rien**
d'autre : le tableau et le document restent rendus à l'identique, avant que le
code ne tombe.

| Mode | Code | Quand |
| --- | --- | --- |
| `doctor` | `0` | toujours, y compris quand un requis échoue |
| `doctor --strict` | `0` | tous les contrôles requis sont `ok` |
| `doctor --strict` | `9` | au moins un requis est `failed` ou `choice_required` |
| `doctor --strict` | `10` | aucun échec, mais au moins un requis est `unknown` |

Deux codes plutôt qu'un, parce que les deux situations appellent des gestes
différents : `9` se répare, `10` se remesure. Un environnement dont une sonde
n'a pas abouti n'est pas validé pour autant — c'est précisément ce qu'un script
de construction d'image ne doit pas confondre avec un succès.

`9` l'emporte quand les deux coexistent : une certitude est plus forte qu'une
ignorance.

`--strict` se combine à `--json`, et l'ordre compte : le document part sur la
sortie standard **avant** que le code ne soit rendu, exactement comme
`validate-structure`. Un appelant qui reçoit un code non nul peut donc encore
lire ce qui n'allait pas.

## `validate-structure`

```json
{
  "schema": 1,
  "ok": false,
  "labs_checked": 87,
  "doc_urls_checked": false,
  "issues": [
    {
      "kind": "structure",
      "key": "struct_missing_file",
      "params": { "name": "test_functional.py" },
      "message": "Fichier manquant : test_functional.py",
      "lab": "labo-tordu",
      "path": "/home/…/labs/domaine/labo-tordu/challenge/tests/test_functional.py",
      "field": null
    }
  ],
  "counts": {
    "contract": 0, "unknown_key": 1, "structure": 1,
    "content": 1, "doc_url": 0, "metadata": 3
  }
}
```

| Champ | Type | Sens |
| --- | --- | --- |
| `ok` | booléen | le verdict, aligné sur le code de retour : `false` veut dire code 1 |
| `labs_checked` | entier | labs réellement découverts et validés |
| `doc_urls_checked` | booléen | `--check-urls` a-t-il été passé ; sans lui, `doc_url: 0` veut dire *non regardé*, pas *toutes vivantes* |
| `issues` | liste | chaque anomalie, dans l'ordre où les contrôles sont joués |
| `counts` | objet | une entrée par famille, **toujours toutes**, y compris à zéro |

Chaque anomalie :

| Champ | Type | Sens |
| --- | --- | --- |
| `kind` | chaîne | la famille : `contract`, `unknown_key`, `structure`, `content`, `doc_url`, `metadata` |
| `key` | chaîne | **l'identité stable de la règle qui a parlé** : c'est là-dessus qu'on filtre, compte et compare |
| `params` | objet | les faits de cette règle, valeurs ramenées à des chaînes et des nombres |
| `message` | chaîne | la même chose dite à un humain, traduite |
| `lab` | chaîne ou null | l'identifiant du lab ; `null` pour les anomalies trouvées avant la découverte (`contract`, `unknown_key`) |
| `path` | chaîne ou null | chemin absolu du fichier en cause |
| `field` | chaîne ou null | le champ de métadonnée en cause, sur les anomalies `metadata` seulement |

`counts` porte toujours les six familles. En omettre les vides laisserait un
tableau de bord incapable de distinguer une famille saine d'une famille que
cette version de l'outil ne connaît pas.

Quand le `meta.yml` lui-même est illisible, la validation s'arrête là : le
document garde la même forme, `labs_checked` vaut 0, et le code de retour est 1.
Ce fichier décrit tout le catalogue, donc chaque contrôle suivant ne serait plus
qu'une supposition.

## `support`

Le rapport anonymisé que `dsoxlab support` rend en Markdown, sous forme de
document. Ses clés de premier niveau sont `dsoxlab`, `python`, `systeme`,
`distribution`, `architecture`, `shell`, `outils`, `catalogue`, `etat` et
`journal`. C'est un dossier de diagnostic destiné à une issue, pas un état sur
lequel bâtir un tableau de bord : les chemins personnels et les adresses
publiques y sont remplacés avant l'affichage.

---

## La règle d'évolution

**Un champ ajouté laisse `schema` où il est.** Un consommateur qui ignore les
champs qu'il ne connaît pas continue de fonctionner, et c'est pourquoi il faut
qu'il le fasse. Les données facultatives arrivent par ce chemin.

**Un champ qui change de sens, qui est renommé ou qui disparaît incrémente
`schema`.** De même pour le sens d'un jeton `state` ou `kind`, et pour la forme
d'un objet imbriqué. Un consommateur qui lit `schema` en premier peut alors
refuser de deviner.

Deux choses ne font explicitement **pas** partie du contrat, et ne doivent pas
être analysées :

- **le texte traduit** : `label`, `message`, `detail`, `notes`. Il suit
  `DSOXLAB_LANG` et est réécrit dès que la formulation s'améliore ;
- **la sortie brute d'un autre outil** : `check.output` est celle de pytest,
  telle quelle.

Deux choses en font partie, et s'oublient facilement :

- les **jetons stables** : `key`, `state`, `kind`, `status`, `cause`, ainsi que
  le `type` et la `session` du runtime. De nouvelles valeurs peuvent apparaître :
  traitez une valeur inconnue comme inconnue, pas comme une erreur ;
- les **codes de retour**, que `--json` ne change jamais.

Les règles vivent à côté du code, dans `src/dsoxlab/reporting/machine.py`, et
les tests qui les tiennent dans `tests/test_json_output.py` et
`tests_e2e/test_parcours.py`. Ces derniers lancent le binaire installé dans un
sous-processus et analysent sa sortie standard sans rien en retirer : c'est la
seule façon d'attraper un message qu'aurait imprimé autre chose que la CLI.
