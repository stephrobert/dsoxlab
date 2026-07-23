# Journal des modifications

**Langue :** [English](./CHANGELOG.md) · [Français](./CHANGELOG.fr.md)

Toutes les modifications notables du projet sont documentées dans ce fichier.

Le format s'appuie sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et le projet suit le [versionnage sémantique](https://semver.org/lang/fr/).

## [Non publié]

## [0.1.26] - 2026-07-23

### Corrigé

- **L'icône de runtime décalait l'affichage.** Les emoji de largeur double, et
  leur sélecteur de variante, sont comptés pour une colonne par Rich mais rendus
  sur deux par le terminal : la ligne glissait et la bordure du panneau se
  brisait. L'icône est retirée de `show` et de `list-labs`. Elle affichait de
  toute façon « ? » sur tous les labs `vm` : sa table connaissait `kvm` et
  `incus`, les deux alias rétro-compat, mais pas `vm`, la valeur canonique du
  contrat.
- **La difficulté restait en anglais en français.** `show` affichait
  « Difficulté : intermediate ». Les trois valeurs employées par les dépôts de
  labs sont traduites ; le champ restant libre par contrat, toute autre valeur
  s'affiche telle quelle plutôt que de disparaître.

## [0.1.25] - 2026-07-23

### Ajouté

- **dsoxlab signale qu'une version plus récente existe.** Un apprenant
  installe la CLI une fois et ne revient jamais vérifier : il joue des labs
  avec des défauts corrigés depuis longtemps, et remonte des problèmes déjà
  résolus. La vérification a lieu une fois par jour et l'avis s'affiche en
  dernier, pour être lu.

  Il est construit pour ne jamais gêner. Le message part sur **stderr**, jamais
  sur stdout : un document `--json` reste lisible quoi qu'il arrive. Il est tu
  quand stderr n'est pas un terminal, ce qui laisse les journaux de CI propres.
  Toute défaillance (hors ligne, PyPI en panne, proxy hostile, réponse
  illisible) est avalée en silence : vérifier une version n'est jamais une
  raison de casser un `check`. Le résultat est mis en cache un jour, pour
  qu'une salle de formation ne martèle pas PyPI. Désactivation par
  `DSOXLAB_NO_UPDATE_CHECK=1`.

## [0.1.24] - 2026-07-23

### Ajouté

- **`destroy` demande désormais confirmation.** La commande effaçait un parc
  entier sans un mot : tapée dans le mauvais dépôt, elle détruisait les VM et
  leurs données sans retour possible. Elle demande maintenant confirmation, et
  `--yes` / `-y` préserve l'usage scripté (CI, procédure de récupération
  documentée).

### Corrigé

- **`check` ne plante plus sur un dépôt qui déclare plusieurs providers sans
  qu'aucun soit actif.** La lecture des outputs Terraform lève
  `ProviderUnresolved` et la traceback remontait telle quelle depuis
  `inventory.py`. L'apprenant reçoit maintenant le même message actionnable que
  pour les commandes d'infra : choisir un provider avec
  `dsoxlab use --provider <nom>` ou `DSOXLAB_PROVIDER=<nom>`. Les labs shell,
  qui n'ont besoin d'aucune infrastructure, ne sont concernés dans aucun cas.

### Modifié

- **`destroy --host` ne prétend plus isoler une VM.** Mesuré sur un parc de
  trois hôtes : `terraform destroy -target` détruit aussi tout ce qui dépend de
  la cible, si bien que demander un seul hôte planifiait **7** ressources à
  détruire, et non 4. L'aide de l'option annonçait « détruit une seule VM », ce
  qui est faux et dangereux. Elle décrit maintenant le comportement réel et
  renvoie vers `destroy` + `provision`, seule façon fiable de récupérer une
  machine inaccessible ; un avertissement est affiché à l'exécution.

## [0.1.23] - 2026-07-22

> Le tag `v0.1.22` a été posé sur le mauvais commit, avant la fusion de sa pull
> request : le workflow a republié la 0.1.21 et PyPI n'a jamais reçu de 0.1.22.
> Tout ce que cette version portait est donc livré ici.

### Corrigé

- **`check --json` polluait sa propre sortie.** En cas d'échec, la sortie brute
  de pytest précédait le document JSON, rendant le flux inanalysable. Le garde
  manquait sur cette seule branche, et c'est le cas le plus fréquent en usage
  réel : un lab qui passe ne l'emprunte jamais, ce qui explique précisément que
  le contrôle initial soit passé à côté. Le texte reste disponible pour
  l'appelant dans `check.output`.

- **`status --json` n'émettait aucun document** quand le `meta.yml` ne déclare
  aucun hôte. Un catalogue entièrement `shell` est un cas normal, pas une
  erreur : il rend désormais un document avec `total: 0`, au lieu d'une phrase
  Rich et d'un code de sortie 0.

- **Les plans Terraform redeviennent stables, donc `provision` est rejouable.**
  L'`instance-id` du cloud-init était construit avec `timestamp()`, donc il
  changeait à chaque exécution : Terraform planifiait un remplacement du disque
  cloud-init à chaque fois, et le provider libvirt le refuse (« Storage volumes
  cannot be updated »). Rejouer un provision échouait donc sur n'importe quel
  dépôt, ne laissant que `destroy` puis `provision` comme issue. L'identifiant
  dérive désormais d'un hachage du contenu cloud-init, et le nom du volume
  aussi : plan stable quand rien n'a bougé, remplacement propre quand quelque
  chose a bougé.

### Ajouté

- **`dsoxlab course` affiche désormais le README du lab, et non le seul
  scenario.** Les deux fichiers sont complémentaires et étaient traités comme
  concurrents : `scenario` pose la situation en quelques lignes, `README`
  explique les commandes et déroule les exercices. Seul le premier était
  affiché, si bien que la moitié la plus riche n'était atteignable par aucune
  commande (mesuré : 10 465 lignes de code dans les README d'un seul dépôt,
  exposées par rien). L'apprenant en concluait qu'il n'y avait pas de cours et
  allait chercher la réponse dans l'énoncé du challenge. `course` affiche
  maintenant le scenario, puis le README, dans la langue demandée.

- **Un fragment SSH par formation, dans `~/.ssh/config.d/<repo-id>.conf`.**
  Écrit par `provision`, rafraîchi par `status`, retiré par `destroy`. Les
  énoncés demandent de se connecter à une machine par son nom, mais ce nom
  n'est ni dans le DNS ni dans `/etc/hosts` : un `ssh alma-rhcsa-1.lab`
  échouait. Il fonctionne désormais, sans `-F` ni préfixe `dsoxlab`. Un
  avertissement est émis quand `~/.ssh/config` ne contient pas la ligne
  `Include ~/.ssh/config.d/*.conf`, car le fragment serait écrit mais jamais
  lu. Il est retiré au `destroy`, pour ne laisser aucune configuration pointant
  des adresses recyclées.

- **Le panneau d'accueil nomme la machine du lab** pour un lab en
  `session: local` qui se joue malgré tout sur un hôte : l'apprenant sait où se
  connecter sans avoir à deviner le nom.

- **`bloc` et `bloc_order` dans le catalogue JSON.** La CLI trie dessus, mais
  ils n'étaient pas publiés : une intégration ne pouvait regrouper que par
  `section`, laquelle vaut `repo.category` par défaut. Mesuré : 84 labs sous un
  nœud unique dans `linux-dsoxlab-training`.

## [0.1.21] - 2026-07-22

### Ajouté

- **`runtime.session` dans `lab.yaml`** — un lab `vm` déclare désormais où
  s'ouvre sa session interactive : `target` (défaut, session SSH sur
  `targets[].host`, comportement inchangé) ou `local`, un sous-shell sur le
  poste de l'apprenant, à la racine du dépôt.

  Certains catalogues se pilotent **depuis** le poste et non **dans** la
  machine : l'apprenant écrit son code dans le dépôt et lance ses commandes
  vers les hôtes du lab, qui restent provisionnés et ciblés par le
  `setup.yaml`. Pour ceux-là, `dsoxlab run` ouvrait une session SSH sur un
  hôte ne contenant ni le dépôt ni ses outils : la session s'ouvrait, mais il
  n'y avait rien à y faire. Le panneau d'accueil annonce maintenant où l'on
  atterrit, et `validate-structure` refuse toute valeur hors des deux
  acceptées, qui retomberait silencieusement sur le SSH.

### Corrigé

- **`dsoxlab run` annonçait un mauvais emplacement.** Le message de démarrage
  affirmait « Vous êtes dans `challenge/work/` » quel que soit le runtime, y
  compris pour les labs `vm`, où l'apprenant n'atterrit jamais dans ce
  répertoire. Il nomme désormais l'endroit réel : le workdir pour `shell`,
  l'hôte connecté pour une session `target`, la racine du dépôt pour une
  session `local`. Le message `shell` lit en outre le vrai `runtime.workdir`
  au lieu de supposer la valeur par défaut.

- **Le panneau d'accueil listait des commandes intapables.** Pour un lab `vm`,
  il affichait six commandes `dsoxlab …` puis ouvrait une session SSH sur
  l'hôte du lab, où dsoxlab n'est pas installé et ne l'a jamais été : toutes
  répondaient `command not found`. Le panneau nomme désormais l'hôte auquel
  il va connecter et précise que ces commandes vivent sur le poste de
  l'apprenant, derrière `exit`. Pour une session `local`, il nomme le
  répertoire du lab auquel les chemins de la mission se rapportent, et amorce
  par `dsoxlab challenge`.

- **Sortie lisible par un programme** : `--json` sur `list-labs`, `progress`,
  `check` et `status`. Chaque document porte une version de `schema`, et la
  sortie standard ne contient rien d'autre que du JSON : les messages
  d'ambiance, la barre de progression pytest et le rappel du contexte actif
  sont tus dans ce mode.

  C'est ce dont toute intégration a besoin : sans cela, une extension
  d'éditeur, un tableau de bord ou un script de suivi devraient analyser la
  sortie Rich, dont les tableaux, les couleurs et les retours à la ligne
  dépendent de la largeur du terminal et ont vocation à changer.

## [0.1.20] - 2026-07-20

### Corrigé

- **`lvm2` est absent de l'image cloud AlmaLinux 9**, et tout lab de stockage
  échouait sur `Failed to find required executable "vgs"` : pas au montage, mais dès
  le premier appel de module LVM. Le commentaire du gabarit affirmait que « lvm2,
  parted et xfsprogs sont dans l'image AlmaLinux Cloud » : vrai en 10, faux en 9. Il
  dit désormais ce qui a été réellement vérifié sur la 9.8, et `lvm2` est installé
  explicitement. Mesuré sur un catalogue de labs : **78 tests en erreur** dus à ce
  seul paquet.

- **`cloud-init status --wait` était lancé sans privilèges**, et sortait donc en
  `PermissionError: /run/cloud-init/cloud.cfg` (rc=1) sur AlmaLinux 9. Le `|| true`
  final avalait cet échec : `wait_for_hosts_ready` rendait la main *avant* la fin de
  cloud-init tout en paraissant l'avoir attendue. C'est désormais `sudo -n`, qui
  rend rc=0. Le `-n` garde la commande non interactive : un hôte où sudo réclamerait
  un mot de passe bloquerait au lieu d'échouer.

## [0.1.19] - 2026-07-20

### Corrigé

- **cloud-init finissait en `status: error` sur chaque nœud KVM, et `dsoxlab
  provision` restait bloqué sur son attente.** Le runcmd lançait `systemctl enable
  --now qemu-guest-agent`, or cette unité déclare
  `BindsTo=dev-virtio\x2dports-org.qemu.guest_agent.0.device` et le provider KVM ne
  déclare **aucun channel virtio**, délibérément (cf. la note dans
  `templates/terraform/kvm/main.tf` : le schéma du provider libvirt le rendait
  impraticable). Le device n'apparaît donc jamais : `--now` attendait **90 secondes
  par nœud**, échouait, et le script runcmd sortait en 1, ce que cloud-init
  rapporte comme un module `scripts_user` en échec.

  Le nœud était pourtant pleinement fonctionnel (comptes créés, paquets installés,
  sshd et firewalld actifs) : le symptôme était uniquement un provisionnement qui
  ne rendait jamais la main. Retirer `--now` conserve l'activation pour le jour où
  un channel existera, et la commande rend désormais la main en **0 s au lieu de
  90**.

## [0.1.18] - 2026-07-20

> **La 0.1.17 n'a jamais été publiée.** Son tag a été posé sur le commit de la
> 0.1.16 : la Release GitHub `v0.1.17` porte donc des artefacts `dsoxlab-0.1.16`,
> et PyPI est resté à la 0.1.16. Le correctif ci-dessous, annoncé pour la 0.1.17,
> est livré par cette version.

### Corrigé

- **`alma9` et `ubuntu22` étaient déclarés mais inutilisables sur le provider
  `kvm`.** Tous deux figurent dans la table Terraform `distro_to_template` : un
  dépôt de labs pouvait donc légitimement écrire `distro: alma9` dans son
  `meta.yml`, alors qu'aucun des deux n'avait d'entrée dans `default_image_urls`.
  Le `coalesce()` qui résout l'image n'avait plus rien à quoi se raccrocher et le
  plan échouait, sauf si le dépôt surchargeait à la main
  `providers.kvm.image_url_<distro>`.

  Les deux embarquent désormais leur image cloud amont, comme les distributions
  déjà listées. Toute distribution que le provider mappe a de nouveau une URL ; le
  provider `incus` gérait déjà `alma9` (`images:almalinux/9/cloud`), et `outscale`
  attend légitimement une OMI pinée par le dépôt.

  Le point compte particulièrement pour la formation RHCE : l'examen EX294 se passe
  sur RHEL 9, donc un catalogue qui le vise a besoin que `alma9` fonctionne sans
  bricolage.

## [0.1.16] - 2026-07-20

### Ajouté

- **`dsoxlab guide [<id>]` ouvre le cours en ligne d'un lab dans le navigateur.**
  Le cours n'est pas embarqué dans le dépôt de labs : chaque lab déclare un
  `doc_url` qui pointe vers le site du formateur. Ouvrir la vraie page, plutôt que
  d'en rapatrier le contenu, la laisse s'afficher telle qu'elle est publiée (images,
  blocs de code, navigation) et évite d'avoir à suivre la structure HTML d'un site
  tiers. `--print` écrit l'URL au lieu d'ouvrir un navigateur : c'est ce qu'on veut
  en SSH, où `webbrowser` n'a rien à ouvrir.

- **`guide_url()` dans le nouveau `services/guide_service.py`**, une fonction pure
  qui compose l'URL et n'ouvre rien. Elle ajoute des paramètres de campagne
  (`utm_source=dsoxlab`, `utm_medium=lab`, `utm_campaign=<lab_id>`) pour qu'un
  formateur puisse voir quels labs amènent réellement des lecteurs vers quels
  guides.

  Ce marquage est nécessaire, pas décoratif : un lien suivi depuis une interface
  locale transmet au mieux `http://localhost:<port>` comme referrer, au pire rien du
  tout, si bien que ces lectures seraient sinon indistinguables du trafic direct.
  Les paramètres de requête déjà présents et les ancres `#section` sont conservés,
  donc un lab peut viser une section précise d'un guide. `source` et `medium` sont
  surchargeables, ce qui permettra à une future interface web de se distinguer de la
  CLI.

## [0.1.15] - 2026-07-20

### Ajouté

- **`services/progress_service.py`** : `build_progress()`, `next_pending_lab()` et
  `pedagogical_sort_key()` exposent la progression de l'apprenant sous forme de
  données typées (`BlocProgress`), et non plus de balisage terminal.
- **`evaluate_lab()` et `compute_score()`** dans `services/lab_service.py` : noter
  une exécution et l'enregistrer devient un seul appel de service, qui rend un
  `ScoreResult`.
- **`SessionSpec` et `Runtime.session_spec()`** : un runtime peut désormais
  *décrire* sa session interactive au lieu de l'ouvrir, et `lab_session_spec()`
  l'expose comme service. `SessionSpec.display()` rend la commande telle qu'un
  apprenant la taperait, quoting compris.

  `open_session()` appelle `subprocess.call`, qui s'empare du terminal courant. Cela
  rendait deux choses impossibles : montrer la commande plutôt que l'exécuter, et
  laisser une interface qui ne peut pas céder son TTY choisir son mode
  d'attachement. L'exécution est maintenant à un seul endroit
  (`BaseRuntime.open_session`), et chaque runtime ne fait plus que décrire.

### Corrigé

- **`dsoxlab ssh`, `dsoxlab status` et la session interactive VM se connectaient
  encore en `student`.** La 0.1.14 a basculé l'inventaire et le `ssh_config` généré
  vers le compte de service `ansible`, mais avait laissé `student@` codé en dur à
  trois endroits : ces commandes et le `ssh_config` généré n'étaient donc pas
  d'accord sur le compte de connexion. Sur un lab qui restreint `AllowUsers` au
  compte de l'automatisation, `dsoxlab ssh` se retrouvait verrouillé hors du nœud
  qu'il venait de provisionner. Le compte est désormais lu depuis l'inventaire
  (`ansible_user`) dans les trois cas, et il ne reste plus aucun compte codé en dur
  dans le paquet.

### Modifié

- **La logique métier ne vit plus dans la couche de présentation.** La formule de
  score était dans `cli.py` (`_run_check`), entrelacée avec des `typer.Exit` et des
  appels d'affichage, et l'agrégation de progression était dans
  `reporting/console.py`, qui produisait du balisage Rich au fil du calcul. Les deux
  étaient donc inatteignables depuis ailleurs et intestables sans capturer une
  sortie terminal : toute seconde interface aurait dû réimplémenter la formule de
  score et la règle « quelle est la prochaine étape ».

  Ce sont désormais des fonctions pures sur des données simples.
  `print_progress_table()` ne fait plus que du rendu, la commande `next` ne fait
  plus que présenter, et les règles qu'elles portent sont couvertes par des tests
  unitaires (14 nouveaux tests, dont celui qui compte le plus : un indice abaisse le
  plafond, il n'est pas soustrait du score final).

  Aucun changement de comportement : mêmes scores, même ordre, même rendu, vérifié
  sur `ansible-training` et sur `linux-dsoxlab-training`.

## [0.1.14] - 2026-07-20

### Ajouté

- **Un compte de service `ansible` dédié sur chaque nœud provisionné.** Les
  gabarits cloud-init (AlmaLinux et Ubuntu) créent désormais un compte `ansible`
  à côté du compte humain `student`, avec le même durcissement : clé SSH
  uniquement, aucun mot de passe de connexion, appartenance à `wheel`/`sudo` et
  `sudo NOPASSWD:ALL`.

  Séparer le compte de *service* utilisé par l'automatisation du compte *humain*
  est la bonne pratique : la traçabilité garde du sens et chaque compte peut être
  révoqué sans verrouiller l'autre. `student` reste le compte humain sur le
  control node ; `ansible` est le compte par lequel dsoxlab et les playbooks des
  labs se connectent. Le `NOPASSWD:ALL` global est assumé, car ce compte pilote
  une automatisation généraliste (dnf, systemd, LVM, SELinux, firewalld) : la
  sécurité vient de la dédicace du compte, pas d'un bridage de ses règles sudo.

- **Les paquets absents de l'image cloud minimale AlmaLinux.** `firewalld` n'est
  pas fourni dans l'image cloud AlmaLinux 10 : `systemctl enable --now firewalld`
  visait donc une unité inexistante et tous les labs de pare-feu échouaient.
  Ajoutés avec lui :

  - `python3-firewall`, requis par le module `ansible.posix.firewalld`, qui sinon
    échoue sur *Failed to import the required Python library (firewall)*.
  - `policycoreutils-python-utils`, qui fournit `semanage`, l'outil RHCSA de
    référence pour la gestion des ports et des contextes SELinux.

  Ce sont des *prérequis d'exécution* Ansible : leur place est dans l'image de
  base, pour que chaque nœud managé soit prêt pour Ansible sans amorçage par lab.

### Modifié

- **CASSANT : le compte SSH par défaut devient `ansible`, et non plus
  `student`.** `build_inventory()` et `write_ssh_config()` utilisent désormais
  `ansible` comme valeur par défaut de `ssh_user` : l'inventaire et le
  `ssh_config` générés se connectent avec le compte de service.

### Migration

Les nœuds provisionnés avant la 0.1.14 n'ont pas de compte `ansible` et
deviennent injoignables avec ce nouveau défaut. Il faut les reprovisionner :

```console
dsoxlab destroy && dsoxlab provision
```

Dans les dépôts de labs, tout ce qui restreint la connexion (`AllowUsers`,
`remote_user`, `ansible_user`) doit désormais viser `ansible`, jamais `student`.
Le pointer sur `student` verrouille l'automatisation hors du nœud.

## [0.1.13] - 2026-07-17

### Modifié

- **Licence : CC BY 4.0 → Apache-2.0.** Creative Commons
  [déconseille ses licences pour du logiciel](https://creativecommons.org/faq/#can-i-apply-a-creative-commons-license-to-software) :
  elles n'accordent aucun brevet, leurs termes sont écrits pour des œuvres de
  création et non pour du code, et PyPI ne pouvait classer le paquet qu'en
  `Other/NOASSERTION`. Pour une CLI publiée sur PyPI et importée par des dépôts
  de labs tiers, cela laissait une réelle ambiguïté juridique aux utilisateurs.

  **Apache-2.0 est la licence logicielle la plus proche des termes précédents.**
  Elle conserve les deux obligations qu'imposait CC BY 4.0 — créditer l'auteur,
  et indiquer si les fichiers ont été modifiés (§4.b) — et y ajoute la concession
  de brevet explicite qui manquait à CC BY 4.0. L'attribution vit désormais dans
  le fichier [NOTICE](./NOTICE), que le §4.d impose de transmettre avec toute
  œuvre dérivée.

  **Les versions jusqu'à la 0.1.12 incluse restent sous CC BY 4.0** : cette
  concession est irrévocable pour quiconque les a reçues. Seules les versions à
  partir de la 0.1.13 sont sous Apache-2.0.

## [0.1.12] - 2026-07-17

### Corrigé

- **La provenance de build n'atteste plus un fichier qui n'est pas publié.**
  `uv build` dépose un `dist/.gitignore` d'un octet, et
  `attest-build-provenance` inclut les fichiers cachés dans son glob (au
  contraire du glob shell qui alimente `gh release create`) : l'attestation de
  la v0.1.11 listait donc `.gitignore` à côté de la wheel et du sdist. Les
  artefacts sont désormais nommés explicitement. Anodin en soi, mais une
  attestation doit nommer exactement ce qui est publié, rien de plus.

## [0.1.11] - 2026-07-17

### Corrigé

- **Un `lab.yaml` ou un `meta.yml` malformé pouvait faire planter la CLI au lieu
  d'être ignoré.** `discovery/scanner.py` rattrape `(KeyError, ValueError,
  yaml.YAMLError)` et ignore le lab fautif avec un warning — mais les parsers
  pouvaient lever hors de ce contrat, et l'exception remontait alors en
  traceback brut sur une commande sans rapport (`list-labs`, `progress`…).
  Comme un `lab.yaml` provient d'un *dépôt fournisseur de labs*, c'est l'entrée
  non fiable du moteur. Cinq cas, tous trouvés par les nouveaux harnais de
  fuzzing :
  - un `lab.yaml` **vide** (ou réduit à des commentaires) → `AttributeError`,
    `yaml.safe_load` rendant `None` ;
  - un document dont la **racine est une liste ou un scalaire**, dans les deux
    fichiers ;
  - **`runtime: vm`** écrit à la place du bloc `runtime:`, et
    `runtime.targets: true` → `AttributeError` / `TypeError` ;
  - **`infra.hosts:` écrit en mapping** au lieu d'une liste → `TypeError` sur
    `h["name"]`, l'itération portant sur les clés ;
  - une **clé présente mais vide** comme `vcpu:` ou `bloc:` → `int(None)` lève
    `TypeError`, `.get("vcpu", 1)` rendant `None` et non le défaut quand la clé
    existe.

  Chacun de ces cas lève désormais un `ValueError` portant le chemin du fichier
  et le champ fautif : le lab est ignoré et le reste du catalogue se charge. Un
  `ip:` vide ne donne plus non plus la chaîne littérale « None ».

### Ajouté

- **Des harnais de fuzzing sur le contrat YAML non fiable** (`fuzz/`), rejoués
  en régression courte dans la CI. Ils vérifient le *contrat* — toute exception
  hors de `(KeyError, ValueError, yaml.YAMLError)` fait échouer le run — plutôt
  que de simplement exécuter les parsers. Livrés avec un corpus de graines et un
  dictionnaire libFuzzer des mots-clés du contrat ; `uv sync --group fuzz`
  installe atheris (tenu hors du groupe `dev`).
- **`actionlint` et `poutine` en gates CI**, aux côtés du job zizmor existant,
  tous deux installés depuis un binaire de release dont le SHA-256 est vérifié
  contre les checksums publiés. `poutine --fail-on-violation` en fait une gate,
  pas un rapport. Les jobs lourds attendent désormais les trois scanners.
- **`step-security/harden-runner`** en premier step de chaque job
  (`egress-policy: audit`), et un `.poutine.yml` qui acquitte trois actions
  vérifiées à la main par leur purl, sans désactiver la règle.
- **La provenance de build attachée à la Release GitHub** sous le nom
  `provenance.intoto.jsonl`. L'attestation existante est enregistrée sur l'API
  d'attestation de GitHub, qui est un artefact *distinct* de l'asset de release
  qu'attend le contrôle Signed-Releases d'OpenSSF Scorecard.

## [0.1.10] - 2026-07-16

### Corrigé

- **Les scores étaient faux sur les labs dont les données contiennent
  « ERROR », « PASSED » ou « FAILED »** : `_parse_counts()` comptait les
  occurrences de ces mots dans la sortie brute de pytest, messages d'assertion
  compris. Un lab qui filtre des lignes `ERROR` (`l1-get-help`,
  `l1-grep-regex`, `l1-redirections-pipes`, `l3-service-diagnose`…) gonflait son
  propre total — `dsoxlab check` annonçait `1/5` pour un lab de 4 tests, et le
  score de l'apprenant s'en trouvait sous-évalué (20 pts au lieu de 25). La
  ligne de résumé que pytest produit lui-même fait désormais foi, avec un repli
  ancré sur les node-ids.

## [0.1.9] - 2026-07-16

### Corrigé

- **KVM : deux dépôts de labs ne se disputent plus le même volume de base.**
  L'image de base libvirt s'appelait `dsoxlab-base-<distro>.qcow2`, sans
  l'identifiant du dépôt. Or le pool libvirt est *partagé* entre tous les
  dépôts, alors que chacun garde son **propre** state Terraform. Le second
  dépôt à provisionner sur une distro déjà utilisée par un autre échouait donc
  sur `storage volume 'dsoxlab-base-alma10.qcow2' exists already` : son state
  ignorait simplement le volume créé par le premier. Concrètement,
  `linux-dsoxlab-training` (alma10) bloquait `ansible-training` (alma10) sur la
  même machine. Le volume devient `dsoxlab-base-<repo-id>-<distro>.qcow2` : les
  catalogues cohabitent vraiment, comme le contrat le promet déjà avec leurs
  réseaux libvirt séparés. L'image cloud est dupliquée par dépôt (sparse, ~600 Mo
  à 2 Go) : c'est le prix de l'isolation.

  Terraform reçoit une variable `repo_id`, déclarée par les trois providers
  (`kvm`, `incus`, `outscale`) puisque les tfvars sont communs ; seul `kvm` crée
  un volume local, lui seul était touché. Incus tire des alias d'images publiques
  et Outscale utilise des AMI : aucune collision possible.

  **Impact à la mise à jour.** Sur un dépôt provisionné en ≤ 0.1.8, le prochain
  `dsoxlab provision` renomme le volume de base, ce que Terraform traite comme un
  *remplacement* : les VMs sont recréées. Rien n'est perdu (les VMs de labs sont
  jetables par conception, et le travail de l'apprenant vit dans le dépôt,
  `challenge/`, jamais sur la VM), mais l'état des labs en cours sur les VMs
  disparaît. Enchaîner `dsoxlab destroy` puis `dsoxlab provision` pour un cycle
  propre.

## [0.1.8] - 2026-07-16

### Corrigé

- **Plus de traceback Python quand l'infrastructure n'est pas provisionnée** :
  un apprenant qui lançait un lab VM avant `dsoxlab provision` (premier
  lancement, ou après un `destroy`) recevait un `ValueError: target_fqdn '...'
  n'est pas dans la liste des hôtes connus : []` brut. C'est une situation
  normale, pas un bug — `build_inventory()` lève désormais
  `InfraNotProvisioned`, que la CLI rend en une phrase actionnable (EN+FR)
  indiquant de lancer `dsoxlab provision`. Un point d'entrée `main()` l'attrape
  pour toutes les commandes : aucune ne peut plus afficher de traceback pour ça.
- **`check` n'enregistre plus un 0/100 en l'absence d'infrastructure** : pytest
  tourne en sous-processus, donc l'erreur d'hôte manquant ne pouvait pas
  remonter jusqu'à la CLI — l'exécution était notée comme un échec de
  l'apprenant et sauvegardée dans son historique. `check`/`submit` vérifient
  maintenant l'inventory avant de noter, et sortent sans rien enregistrer.

## [0.1.7] - 2026-07-16

### Ajouté

- **Les labs multi-distrib deviennent réels** : `check`/`submit` acceptent
  `--target/-t` et exportent le FQDN de la cible résolue aux tests via
  `DSOXLAB_TARGET_HOST`. Jusqu'ici `runtime.targets[]` n'était que déclaratif —
  un lab pouvait déclarer une cible Ubuntu pendant que ses tests codaient
  l'hôte RHEL en dur : choisir Ubuntu ne changeait rien et le contrat mentait.
  Les tests demandent désormais l'hôte choisi (helper `lab_target_host()` dans
  le `conftest.py` du dépôt), donc un même lab peut être réellement validé sur
  plusieurs distributions.

### Corrigé

- **Une faute de frappe dans `--target` n'enregistre plus un 0/100** : une
  cible explicite inconnue est désormais une erreur (`unknown_target`, EN+FR)
  levée avant le lancement des tests, au lieu d'un check échoué sauvegardé dans
  l'historique de l'apprenant.
- **Une cible de session ne casse plus les labs qui ne la déclarent pas** :
  l'`active_target` persistée par `use --target` n'est appliquée qu'aux labs
  qui la déclarent ; les labs shell et mono-cible l'ignorent silencieusement.

## [0.1.6] - 2026-07-16

### Corrigé

- **Inventory KVM après un provision ciblé** : `terraform apply -target`
  n'évalue pas les outputs racine, donc les IP des hôtes KVM (DHCP libvirt)
  manquaient et `dsoxlab check` échouait « Aucun host dans l'inventory » pour
  tout lab KVM. `apply()` lance désormais un `terraform apply -refresh-only`
  après un apply ciblé pour recalculer le map d'outputs `hosts` sans recréer de
  ressource.

### Ajouté

- **Détection de conflit de provider** : `dsoxlab provision` s'arrête avec un
  message d'aide (EN + FR) si un autre provider (incus/KVM) a encore de l'infra
  active — ils partagent le nom de réseau et le subnet du lab et ne peuvent pas
  tourner en même temps.

## [0.1.5] - 2026-07-15

### Ajouté

- **hints i18n** : le format moderne d'indice (`text_en` / `text_fr`) accepte
  désormais aussi des valeurs encodées en base64, pour que les indices soient à
  la fois bilingues et obfusqués dans le fichier. Le loader tente le base64
  d'abord, avec repli sur le texte brut.

### Modifié

- **challenge i18n** : le brief de challenge localisé est résolu en
  `challenge/README.<lang>.md` (ex. `README.fr.md`), cohérent avec
  `scenario.<lang>.md` et le `README.<lang>.md` racine — au lieu de l'ancien
  nommage `README_FR.md`.

## [0.1.4] - 2026-07-15

### Corrigé

- **progress** : `dsoxlab progress` affiche désormais un nom de bloc clair (le
  titre de la section meta.yml, ex. « Fondamentaux (l1) ») au lieu de `?`, et la
  colonne Bloc est alignée à gauche. Chaque lab est rattaché à sa section
  meta.yml à la découverte (`bloc` + nouveau `bloc_name`), donc le récapitulatif
  regroupe par vraie section plutôt que par un `bloc=0` non affecté.

## [0.1.3] - 2026-07-15

### Ajouté

- **labs multi-hôtes** : un mapping `runtime.targets[].roles` (ex.
  `roles: {server: alma-rhcsa-2.lab}`) permet à un lab `vm` d'utiliser plusieurs
  hôtes à la fois. Chaque rôle devient un groupe Ansible `lab_<role>` (en plus de
  `lab_target`, l'hôte primaire où tournent les tests), pour que `setup.yaml` /
  `solution.yaml` / `cleanup.yaml` configurent un serveur et un client sans coder
  de FQDN en dur. Les hôtes de rôle sont validés contre l'inventory provisionné
  au runtime. Rétro-compatible : sans `roles`, lab mono-hôte comme avant.

## [0.1.2] - 2026-07-15

### Ajouté

- **provision** : après `terraform apply`, `dsoxlab provision` attend désormais
  que chaque hôte soit réellement joignable — `sshd` démarré, compte `student`
  créé et cloud-init terminé (`cloud-init status --wait`) — avant de rendre la
  main. Cela supprime l'échec « unreachable » (dark) qui frappait le tout premier
  `dsoxlab run` juste après le provisioning : plus besoin de relancer à la main.
  Un `HostReadyTimeout` retombe sur un avertissement (la VM démarre peut-être
  encore).

### Corrigé

- **version** : `__version__` est désormais lu depuis les métadonnées du paquet
  installé au lieu d'une chaîne codée en dur, pour que `dsoxlab --version` reste
  aligné sur `pyproject.toml` (il était figé à `0.1.0`).

## [0.1.1] - 2026-07-15

### Corrigé

- **incus** : `provision --host X` ne crée plus le disque additionnel des
  *autres* hôtes, et `destroy --host X` supprime désormais le disque additionnel
  de cet hôte. Une variable Terraform `target_hosts` restreint le `for_each` du
  volume extra, et `host_targets` cible le volume propre à l'hôte pour que
  `-target` le nettoie.
  ([#1](https://github.com/stephrobert/dsoxlab/issues/1))

## [0.1.0] - 2026-07-15

Première version publique.

### Ajouté

- CLI basée sur Typer (`dsoxlab`) pilotant des labs pratiques répartis dans
  plusieurs dépôts, via un contrat déclaratif (`meta.yml` + `lab.yaml`).
- Découverte du catalogue qui scanne le `meta.yml` du dépôt courant et chaque
  `lab.yaml`.
- Trois runtimes : `shell`, `incus` (conteneurs) et `kvm` (Terraform +
  libvirt), chacun opt-in et auto-descriptif.
- Templates de provisioning pour Incus, KVM/libvirt et Outscale (HCL Terraform
  et cloud-init).
- Validation au niveau du système via `pytest` + `pytest-testinfra`, incluant
  les tests de persistance après reboot.
- Scoring et suivi de progression persistés dans une base SQLite XDG locale,
  avec des indices à coût variable.
- Validateurs de structure et de métadonnées (`dsoxlab validate-structure`).
- Diagnostics de l'environnement (`dsoxlab doctor [--fix]`).
- Interface utilisateur bilingue (anglais/français) pilotée par `DSOXLAB_LANG`.

[Unreleased]: https://github.com/stephrobert/dsoxlab/compare/v0.1.20...HEAD
[0.1.20]: https://github.com/stephrobert/dsoxlab/compare/v0.1.19...v0.1.20
[0.1.19]: https://github.com/stephrobert/dsoxlab/compare/v0.1.18...v0.1.19
[0.1.18]: https://github.com/stephrobert/dsoxlab/compare/v0.1.16...v0.1.18
[0.1.16]: https://github.com/stephrobert/dsoxlab/compare/v0.1.15...v0.1.16
[0.1.15]: https://github.com/stephrobert/dsoxlab/compare/v0.1.14...v0.1.15
[0.1.14]: https://github.com/stephrobert/dsoxlab/compare/v0.1.13...v0.1.14
[0.1.13]: https://github.com/stephrobert/dsoxlab/compare/v0.1.12...v0.1.13
[0.1.12]: https://github.com/stephrobert/dsoxlab/compare/v0.1.11...v0.1.12
[0.1.11]: https://github.com/stephrobert/dsoxlab/compare/v0.1.10...v0.1.11
[0.1.10]: https://github.com/stephrobert/dsoxlab/compare/v0.1.9...v0.1.10
[0.1.9]: https://github.com/stephrobert/dsoxlab/compare/v0.1.8...v0.1.9
[0.1.8]: https://github.com/stephrobert/dsoxlab/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/stephrobert/dsoxlab/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/stephrobert/dsoxlab/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/stephrobert/dsoxlab/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/stephrobert/dsoxlab/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/stephrobert/dsoxlab/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/stephrobert/dsoxlab/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/stephrobert/dsoxlab/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/stephrobert/dsoxlab/releases/tag/v0.1.0
