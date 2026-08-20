"""Traductions françaises."""

STRINGS: dict[str, str] = {
    # ── App ───────────────────────────────────────────────────────────────────
    "app_help": "dsoxlab — DevSecOps XL Labs. Pilotez vos labs depuis le terminal.",

    # ── Options globales ──────────────────────────────────────────────────────
    "opt_help":       "Affiche ce message et quitte.",
    "opt_lab_home":   "Racine du dépôt linux-training (défaut : auto-détecté).",
    "opt_json":           "Sortie JSON, destinée aux programmes (extension d'éditeur, tableau de bord). Aucun autre affichage.",
    "opt_level":      "Filtre par niveau (l1, l2, lfcs, rhcsa)",
    "opt_section":    "Filtre par section (linux, ansible, terraform, docker…)",
    "opt_type":       "Filtre par type : lab, challenge ou capstone",
    "opt_bloc":       "Filtre par numéro de bloc (1-8)",
    "opt_top":        "Nombre de résultats affichés",
    "opt_fix":        "Tenter la remédiation automatique des composants manquants.",
    "opt_no_pager":   "Tout afficher d'un bloc au lieu de paginer ce qui dépasse l'écran.",
    "opt_use_provider":
        "Provider d'infra à activer (ex. kvm, outscale, incus). "
        "Surchargé par DSOXLAB_PROVIDER. Persisté entre commandes.",
    "opt_provision_host":
        "Cible une seule VM (fqdn du meta.yml). Répétable. Si absent, applique "
        "tout le plan. Les ressources partagées (réseau, images de base) sont "
        "gérées par Terraform en cascade.",
    "opt_destroy_host":
        "Restreint la cible Terraform à un fqdn du meta.yml. Répétable. "
        "ATTENTION : Terraform détruit aussi tout ce qui dépend de la cible, "
        "donc cette option n'isole PAS une VM des autres. Pour récupérer une "
        "machine, préférer destroy complet + provision.",
    "opt_yes":        "Confirme sans demander",
    "opt_filter_lab": "Filtre par lab",

    # ── Aides des commandes ───────────────────────────────────────────────────
    "cmd_use_help":       "Définit le contexte actif (section et/ou niveau par défaut). Utilisez --reset pour l'effacer.",
    "cmd_use_arg":        "Contexte actif : section ou section/niveau (ex: linux, linux/l1, ansible/l2)",
    "opt_use_reset":      "Efface le contexte actif.",
    "opt_target":         "Nom de la cible d'exécution par défaut (doit matcher runtime.targets[].name dans lab.yaml).",
    "opt_run_target":     "Cible pour cette exécution (override le défaut de 'use'). Doit matcher un runtime.targets[].name.",
    "opt_check_target":   "Cible sur laquelle valider (override la cible de session). Doit matcher un runtime.targets[].name — les tests tournent sur cet hôte.",
    "unknown_target":     "Cible '{target}' inconnue pour ce lab. Cibles déclarées : {declared}.",
    "infra_not_provisioned": "Ce lab a besoin d'une VM, et aucune ne tourne : l'infrastructure du lab n'est pas provisionnée.\nMonte-la d'abord :\n  dsoxlab provision",
    "opt_lang":           "Langue pour le contenu des labs (ex: en, fr). Remplace l'auto-détection.",
    "cmd_list_labs_help": "Liste tous les labs disponibles (filtrés par contexte actif si défini).",
    "cmd_progress_help": "Affiche la progression par bloc (labs complétés, score moyen, challenges et capstones).",
    "cmd_next_help":     "Recommande le prochain lab ou challenge à compléter dans le contexte actif.",
    "cmd_show_help":      "Affiche le détail et le statut d'un lab.",
    "cmd_show_arg":       "Identifiant du lab (ex: l1-01-navigation-fichiers)",
    "cmd_guide_help":     "Ouvre le guide en ligne du lab dans le navigateur.",
    "cmd_guide_arg":      "Identifiant du lab (optionnel si un lab est actif)",
    "cmd_guide_opt_print": "Affiche l'URL au lieu d'ouvrir un navigateur.",
    "guide_opening":      "Ouverture du guide de {lab_id} dans le navigateur…",
    "guide_no_url":       "Le lab {lab_id} ne déclare pas de doc_url : aucun guide à ouvrir.",
    "guide_no_browser":   "Aucun navigateur n'a pu être ouvert. Copiez l'URL ci-dessus.",
    "cmd_run_help":       "Prépare et démarre l'environnement du lab.",
    "cmd_run_arg":        "Identifiant du lab",
    "cmd_course_help":    "Affiche une section du cours, ou le sommaire si aucune section n'est précisée.",
    "cmd_course_arg":    "Identifiant du lab (optionnel si un lab est actif en session)",
    "cmd_course_opt_section": "Section à afficher : numéro (1, 2 …) ou identifiant (navigation, permissions …).",
    "cmd_course_list":   "Liste tous les labs et indique si un cours (scenario.md) est disponible.",
    "course_toc_title":  "Cours — {title}",
    "course_toc_col_n":  "#",
    "course_toc_col_id": "ID section",
    "course_toc_col_title": "Titre",
    "course_toc_tip":    "Lire une section : [bold]dsoxlab course {id} --section <n>[/bold]",
    "cmd_course_opt_next": "Passer à la section suivante (incrémente la position sauvegardée).",
    "cmd_course_opt_prev": "Revenir à la section précédente (décrémente la position sauvegardée).",
    "course_nav_progress": "Section {pos}/{total}",
    "course_nav_prev":     "← [bold]dsoxlab course --prev[/bold]",
    "course_nav_next":     "→ [bold]dsoxlab course --next[/bold]",
    "course_end_title":    "Fin du cours — {id}",
    "course_end_body":     "Vous avez lu les [bold]{total}[/bold] sections du cours.\n\nPassez au challenge : [bold cyan]dsoxlab challenge {id}[/bold cyan]",
    "course_section_not_found": "Section '{name}' introuvable. Utilisez [bold]dsoxlab course {id}[/bold] pour lister les sections.",
    "course_section_file_missing": "Fichier de section introuvable : {file}",
    "cmd_challenge_help": "Affiche la mission du challenge (challenge/README.md).",
    "cmd_challenge_arg":  "Identifiant du lab (optionnel si un lab est actif en session)",
    "cmd_hint_help":      "Affiche le prochain indice du challenge (déduit des points au score final).",
    "cmd_hint_arg":       "Identifiant du lab (optionnel si un lab est actif en session)",
    "cmd_check_help":     "Exécute les tests, calcule le score (hints déduits) et enregistre le résultat.",
    "cmd_check_arg":      "Identifiant du lab (optionnel si un lab est actif en session)",
    "cmd_submit_help":    "Soumission finale : lance les tests, enregistre le score, puis tapez 'exit' pour quitter la session.",
    "cmd_submit_arg":     "Identifiant du lab (optionnel si un lab est actif en session)",
    "cmd_scores_help":    "Affiche l'historique des scores enregistrés.",
    "cmd_reset_help":     "Remet le lab à l'état initial (clean + redémarrage).",
    "cmd_reset_arg":      "Identifiant du lab",
    "cmd_clean_help":     "Supprime toutes les ressources créées par le lab.",
    "cmd_clean_arg":      "Identifiant du lab",
    "cmd_validate_help":  "Vérifie la structure et les métadonnées de tous les labs.",
    "cmd_doctor_help":    "Diagnostique l'environnement (runtimes, outils, labs détectés).",
    "opt_verbose":
        "Détaille ce que fait le moteur, sur la sortie d'erreur. Répétable : -v pour les informations, -vv pour le détail complet.",
    "opt_debug":      "Équivaut à -vv. Le journal complet est de toute façon écrit dans ~/.local/state/dsoxlab/dsoxlab.log.",
    "opt_version_help":   "Affiche la version de dsoxlab et quitte.",
    "cmd_install_help":   "Installe le wrapper dsoxlab dans ~/.local/bin et l'auto-complétion shell.",
    "cmd_demo_help":
        "Installe un catalogue de démonstration et joue un premier lab, sans "
        "rien cloner ni provisionner.",
    "opt_demo_force":
        "Réinstalle par-dessus, en perdant la progression et les réponses déjà "
        "présentes.",
    "demo_installee":  "Catalogue de démonstration installé dans {path}",
    "demo_deja_installee":
        "Le catalogue de démonstration est déjà installé dans {path}.",
    "demo_deja_installee_suite":
        "Il contient peut-être votre progression et vos réponses, donc rien "
        "n'a été touché.\n"
        "Pour le reprendre : cd {path} && dsoxlab list-labs\n"
        "Pour repartir de zéro : dsoxlab demo --force",
    "demo_echec":      "Installation impossible : {error}",
    "demo_suite":
        "Pour commencer :\n"
        "  cd {path}\n"
        "  dsoxlab course {lab}\n"
        "  dsoxlab run {lab}\n"
        "Puis, une fois la mission remplie : dsoxlab check {lab}",
    "cmd_support_help":
        "Produit un rapport de diagnostic anonymisé, à coller dans une issue.",
    "opt_support_log_lines":
        "Nombre de lignes de journal à joindre (0 pour n'en joindre aucune).",
    "support_hint":
        "Collez ce rapport dans votre issue. Il ne contient ni chemin personnel, "
        "ni adresse publique, ni nom de machine.",
    "cmd_fullhelp_help":  "Affiche le guide complet de la plateforme (concepts, workflow, commandes).",
    "cmd_provision_help": "Provisionne l'infrastructure du lab (terraform apply sur le provider courant).",
    "cmd_destroy_help":   "Détruit l'infrastructure du lab (terraform destroy).",
    "cmd_status_help":    "Vérifie la connectivité SSH des hôtes déclarés dans meta.yml.",
    "cmd_ssh_help":       "Ouvre une session SSH interactive sur un hôte du lab.",
    "cmd_ssh_arg":        "Nom de l'hôte ou alias court (ex. : alma-rhcsa-1, ubuntu-lfcs-1)",

    # ── provision / destroy / status / ssh ────────────────────────────────────
    # ── résolution du provider ────────────────────────────────────────────────
    "provider_required":      "Cette commande a besoin d'un provider d'infrastructure, et ce dépôt en déclare plusieurs ({candidates}) sans qu'aucun ne soit actif.\nChoisis-en un :\n  dsoxlab use --provider {first}   (persisté)\n  DSOXLAB_PROVIDER={first} dsoxlab <commande>   (one-shot)",
    "provider_none_declared": "Aucun provider d'infrastructure déclaré dans meta.yml (infra.provider). Cette commande en exige un.",
    "section_unknown":
        "Section inconnue : « {name} ». Le catalogue serait vide.\n"
        "Sections déclarées dans meta.yml : {sections}.\n"
        "Pour tout voir : dsoxlab use --reset",
    "provider_not_a_section": "'{name}' est un provider d'infrastructure, pas une section du catalogue.\nPour l'activer :\n  dsoxlab use --provider {name}",
    "provider_unknown":       "Provider '{name}' inconnu pour ce dépôt. Candidats : {candidates}",

    "provision_no_meta":   "Pas de meta.yml trouvé dans {root}. Es-tu dans un dépôt dsoxlab ?",
    "host_unknown":        "Host inconnu : '{fqdn}'. Connus : {known}.",
    "terraform_target":    "Cible Terraform : {hosts} ({count} ressources)",

    # ── barres de progression ────────────────────────────────────────────────
    "progress_tests_running":  "Tests : {lab_id}",
    "progress_tests_done":     "Tests {lab_id} terminés",
    "progress_ansible_task":   "Tâche : {task}",
    "progress_playbook_done":  "{playbook} terminé",
    "progress_tf_init_done":   "terraform init terminé",
    "progress_action_done":    "{action} terminé",
    "progress_nothing_to_do":  "Rien à faire",
    "provision_starting":  "Provisionnement de l'infrastructure (provider : {provider})…",
    "provision_no_ssh_key": "Clé SSH du lab manquante : {path}\nSans elle, le keypair cloud serait vide et les VMs inaccessibles.\nLance d'abord : dsoxlab instructor bootstrap",
    "provision_done":      "Provisionnement terminé — {count} hôte(s) prêt(s).",
    "provision_failed":    "Provisionnement échoué : {error}",
    "provision_provider_conflict": "Impossible de provisionner sur « {current} » : le provider « {others} » a encore une infra de lab active.\nincus et KVM partagent le nom de réseau et le subnet du lab, ils ne peuvent pas tourner en même temps.\nTermine ou détruis l'autre d'abord :\n  DSOXLAB_PROVIDER={other} dsoxlab destroy",
    "provision_waiting_ssh": "Attente que les hôtes soient joignables (SSH + cloud-init)…",
    "provision_waiting_ssh_host": "Attente de {host} (SSH + cloud-init), tentative {attempt}…",
    "provision_ssh_timeout": "Délai d'attente dépassé : {error}\nLa VM démarre peut-être encore : relance `dsoxlab run` dans un instant.\nSur une machine modeste, le démarrage simultané de plusieurs VMs sature le CPU et dépasse ce délai. Allonge-le :\n  DSOXLAB_HOST_READY_TIMEOUT=360 dsoxlab provision",
    "confirm_destroy":
        "Détruire toute l'infrastructure du provider {provider} ? "
        "Les données des VM seront perdues",
    "difficulty_beginner":     "débutant",
    "difficulty_intermediate": "intermédiaire",
    "difficulty_advanced":     "avancé",
    "update_available":
        "\n[dim]Une version plus récente de dsoxlab est disponible : "
        "{latest} (vous avez {current}).\n"
        "Mettez à jour avec : uv tool upgrade dsoxlab[/dim]",
    "destroy_host_not_isolated":
        "Attention : Terraform détruit aussi tout ce qui dépend de la cible. "
        "Le ciblage par hôte n'isole donc pas une VM des autres. Pour "
        "récupérer une machine inaccessible, préfère « dsoxlab destroy » "
        "puis « dsoxlab provision » : le parc entier est reconstruit à neuf.",
    "destroy_starting":    "Destruction de l'infrastructure (provider : {provider})…",
    "ssh_fragment_failed":  "Fragment SSH non écrit : {error}. La connexion par nom de machine ne fonctionnera pas.",
    "ssh_fragment_written": "Connexion directe activée : [bold]ssh <machine>[/bold] fonctionne désormais (fragment {path}).",
    "ssh_fragment_no_include": "Fragment SSH écrit dans {path}, mais votre ~/.ssh/config ne contient pas [bold]Include ~/.ssh/config.d/*.conf[/bold] : ajoutez cette ligne en tête de fichier, sinon il ne sera jamais lu.",
    "ssh_fragment_removed": "Fragment SSH de [bold]{repo}[/bold] retiré : il pointait des machines détruites.",
    "destroy_done":        "Infrastructure détruite.",
    "destroy_failed":      "Destruction échouée : {error}",
    "status_no_hosts":     "Aucun hôte déclaré dans meta.yml.",
    "status_no_key":       "Clé SSH privée introuvable : {path}. Lance 'dsoxlab instructor bootstrap' d'abord.",
    "status_checking":     "Vérification de la connectivité SSH sur {count} hôte(s)…",
    "status_all_ok":       "Les {count} hôtes répondent en SSH+sudo.",
    "status_partial":      "Seulement {ok}/{total} hôtes répondent sur l'infrastructure {provider}. Cloud-init peut être encore en cours (attends 1-2 min) ou relance 'dsoxlab provision' si les VMs ont été détruites.",
    "status_via_bastion":  "Connexion via bastion {bastion} (subnet privé)…",
    "ssh_unknown_host":    "Hôte inconnu : {host}. Disponibles : {hosts}",
    "ssh_connecting":      "Connexion à {host} ({ip})…",
    "ssh_via_bastion":     "Connexion à {host} ({ip}) via bastion {bastion}…",

    # ── instructor (commandes formateur) ───────────────────────────────────────
    "cmd_instructor_help":            "Commandes formateur (clé SSH, vault, hosts, ssh-config). Pas pour les apprenants.",
    "cmd_instructor_bootstrap_help":  "Génère la clé SSH du lab (si absente) et vérifie que terraform/ansible-runner sont installés.",
    "bootstrap_key_exists":           "Clé SSH déjà présente : {path}",
    "bootstrap_not_a_lab_repo":
        "{root} n'est pas un dépôt de labs : aucun meta.yml à sa racine.\n"
        "Aucune clé n'a été générée : elle atterrirait dans un répertoire "
        "quelconque, hors de tout .gitignore.\n"
        "Place-toi dans le dépôt de labs, ou indique-le :\n"
        "  dsoxlab instructor bootstrap --lab-home /chemin/vers/le-depot",
    "bootstrap_generating_key":       "Génération clé SSH ed25519 : {path} (sans passphrase)…",
    "bootstrap_key_created":          "Clé SSH créée : {path}",
    "bootstrap_keygen_failed":        "ssh-keygen a échoué : {stderr}",
    "bootstrap_no_terraform":         "terraform absent du PATH. Installation : https://developer.hashicorp.com/terraform/install",
    "bootstrap_terraform_ok":         "terraform : OK",
    "bootstrap_no_ansible_runner":    "ansible-runner non installé. Relance : uv tool install --force --with ansible-runner dsoxlab",
    "bootstrap_ansible_runner_ok":    "ansible-runner : OK",

    # ── fullhelp contenu ──────────────────────────────────────────────────────
    "fullhelp_title":   "dsoxlab — DevSecOps XL Labs",
    "fullhelp_concept": """\
[bold]Qu'est-ce que dsoxlab ?[/bold]

dsoxlab est la CLI de la plateforme [bold cyan]DevSecOps XL Labs[/bold cyan] : une plateforme de
formation pratique auto-portée, conçue pour accompagner les formations du site
[bold]https://blog.stephane-robert.info/docs/[/bold]

Chaque [cyan]lab[/cyan] est un exercice autonome lié à un guide du site, portant sur une
compétence précise : Linux, conteneurs, Kubernetes, IaC, sécurité, CI/CD…

Les labs sont organisés par [bold]section[/bold] (linux, ansible, terraform, kubernetes…)
et par [bold]niveau[/bold] (l1 → débutant, l2 → intermédiaire, lfcs, rhcsa).

Chaque lab expose :
  • une [bold]compétence observable[/bold] à acquérir,
  • un [bold]runtime[/bold] (shell, conteneur incus ou VM KVM),
  • des [bold]tests automatiques[/bold] pour valider votre réponse,
  • des [bold]indices[/bold] en cas de blocage (avec pénalité sur le score),
  • un [bold]lien direct[/bold] vers le guide du site correspondant.""",

    "fullhelp_workflow": """\
[bold]Workflow typique[/bold]

  1. [bold]dsoxlab list-labs[/bold]                   — parcourir les labs disponibles
  2. [bold]dsoxlab use linux/l1[/bold]                — se concentrer sur une section/un niveau
  3. [bold]dsoxlab show <id>[/bold]                   — lire les objectifs et le détail du lab
  4. [bold]dsoxlab run <id>[/bold]                    — démarrer l'environnement du lab
  5. Travailler dans l'environnement…
  6. [bold]dsoxlab hint <id>[/bold]                   — obtenir un indice (coûte des points)
  7. [bold]dsoxlab check <id>[/bold]                  — lancer les tests auto et obtenir son score
  8. [bold]dsoxlab reset <id>[/bold]                  — remettre à zéro et recommencer
  9. [bold]dsoxlab clean <id>[/bold]                  — détruire l'environnement une fois terminé""",

    "fullhelp_commands": """\
[bold]Référence des commandes[/bold]

  [cyan]use <section>[/cyan][dim]/[/dim][cyan]<niveau>[/cyan]  Définit le contexte actif (filtre list-labs et validate-structure).
                       Exemples : [bold]linux[/bold]  [bold]linux/l1[/bold]  [bold]ansible/l2[/bold]
    [dim]--lang <code>[/dim]        Définit aussi la langue d'affichage (en / fr).
    [dim]--reset / -r[/dim]         Efface le contexte actif (affiche de nouveau tous les labs).

  [cyan]list-labs[/cyan]            Liste les labs. Options :
    [dim]--section / -s[/dim]       Filtre par section.
    [dim]--level   / -l[/dim]       Filtre par niveau.
    [dim]--type    / -t[/dim]       Filtre par type : [bold]lab[/bold], [bold]challenge[/bold] ou [bold]capstone[/bold].
    [dim]--bloc    / -b[/dim]       Filtre par numéro de bloc (1–8).

  [cyan]show <id>[/cyan]            Détail complet d'un lab (compétences, runtime, liens…).

  [cyan]run <id>[/cyan]             Démarre l'environnement du lab (shell, incus ou KVM).

  [cyan]course[/cyan] [dim][<id>][/dim]        Affiche le cours : une section à la fois si le lab en
                       déclare (course.yaml), sinon le scenario et le README.
    [dim]--section / -s[/dim]       Section à afficher : numéro ou identifiant.
    [dim]--next    / -n[/dim]       Section suivante.  [dim]--prev / -p[/dim] : précédente.
    [dim]--no-pager[/dim]           Tout afficher d'un bloc, sans pagination.
                       [dim]<id>[/dim] est optionnel si un lab est actif en session.

  [cyan]guide[/cyan] [dim][<id>][/dim]         Ouvre le guide en ligne du lab dans le navigateur.
                       Le cours vit sur le site du formateur : la page s'ouvre dans
                       un vrai onglet, donc elle s'affiche telle qu'elle est publiée.
    [dim]--print[/dim]              Affiche l'URL au lieu d'ouvrir un navigateur
                       (utile en SSH, où aucun navigateur n'est disponible).
                       [dim]<id>[/dim] est optionnel si un lab est actif en session.

  [cyan]challenge[/cyan] [dim][<id>][/dim]     Affiche la mission du challenge (challenge/README.md).
    [dim]--no-pager[/dim]           Tout afficher d'un bloc, sans pagination.
                       [dim]<id>[/dim] est optionnel si un lab est actif en session.

  [cyan]hint[/cyan] [dim][<id>][/dim]          Affiche le prochain indice.
                       Chaque indice [yellow]déduit des points[/yellow] du score final.
                       [dim]<id>[/dim] est optionnel si un lab est actif en session.

  [cyan]check[/cyan] [dim][<id>][/dim]         Joue les tests, calcule le score, sauvegarde dans l'historique.
                       Score = 100 − (indices utilisés × coût par indice).
                       [dim]<id>[/dim] est optionnel si un lab est actif en session.

  [cyan]submit[/cyan] [dim][<id>][/dim]        Soumission finale : joue les tests, sauvegarde le score, puis tapez [bold]exit[/bold] pour terminer la session.
                       À utiliser quand vous avez fini le lab.
                       [dim]<id>[/dim] est optionnel si un lab est actif en session.
  [cyan]progress[/cyan]             Résumé de progression par bloc (labs faits, score, challenge, capstone).

  [cyan]next[/cyan]                 Recommande le prochain lab à compléter dans le contexte actif.
  [cyan]scores[/cyan]               Affiche l'historique des scores.
    [dim]--section / -s[/dim]       Filtre par section.
    [dim]--lab     / -l[/dim]       Filtre par lab.
    [dim]--top     / -n[/dim]       Limite le nombre de résultats.

  [cyan]reset <id>[/cyan]           Nettoie et redémarre le lab depuis zéro.

  [cyan]clean <id>[/cyan]           Détruit les ressources de l'environnement (avec confirmation).
    [dim]--yes / -y[/dim]           Passe la confirmation.

  [cyan]validate-structure[/cyan]   Vérifie tous les fichiers lab.yaml et l'arborescence.

  [cyan]doctor[/cyan]               Diagnostique l'environnement. Le tableau [bold]Requis[/bold] liste ce qui
                       bloque ce dépôt-ci ; un hyperviseur inutile ici reste
                       [bold]Informatif[/bold] et ne s'affiche jamais en erreur.
    [dim]--fix[/dim]                Applique la remédiation des composants requis manquants.
                       Les composants informatifs ne sont pas touchés.

  [cyan]demo[/cyan]                 Installe un catalogue de démonstration et un premier lab
                       jouable immédiatement, sans rien cloner ni provisionner.
    [dim]--force[/dim]              Réinstalle par-dessus (perd la progression).

  [cyan]provision[/cyan]            Monte l'infrastructure des labs vm (terraform apply).
    [dim]--host <fqdn>[/dim]         Ne cible qu'une machine. Répétable.

  [cyan]status[/cyan]               Vérifie la connectivité SSH des hôtes déclarés.

  [cyan]ssh <hote>[/cyan]           Ouvre une session interactive sur un hôte du lab.

  [cyan]destroy[/cyan]              Détruit l'infrastructure des labs vm (terraform destroy).
    [dim]--yes[/dim]                 Ne demande pas confirmation.

  [cyan]install[/cyan]              Installe dsoxlab dans [bold]~/.local/bin[/bold] + auto-complétion shell.
                       Supporte bash et zsh. Rechargez le shell après exécution.

  [cyan]support[/cyan]              Rapport de diagnostic à coller dans une issue :
                       versions, outils, catalogue, dernières traces. Anonymisé
                       par défaut (ni chemin personnel, ni adresse publique).
    [dim]--json[/dim]               Le même contenu, en document machine.
    [dim]--log-lines <n>[/dim]      Nombre de lignes de journal jointes (0 pour aucune).

  [cyan]fullhelp[/cyan]             Ce guide.

[bold]Options globales[/bold] [dim](avant la commande)[/dim]

  [dim]--verbose / -v[/dim]       Dit ce que fait le moteur, sur la sortie d'erreur.
                       Répétable : [bold]-v[/bold] pour les informations,
                       [bold]-vv[/bold] pour le détail complet.
  [dim]--debug[/dim]              Équivaut à [bold]-vv[/bold].
  [dim]--version[/dim]            Affiche la version et quitte.

  Le journal complet est de toute façon écrit dans
  [bold]~/.local/state/dsoxlab/dsoxlab.log[/bold], sans avoir à repasser la commande.
  Il ne va jamais sur la sortie standard : [bold]--json[/bold] reste lisible par
  un programme, même en mode verbeux.""",

    "fullhelp_runtimes": """\
[bold]Runtimes[/bold]

  [bold]shell[/bold]    Exercices simples dans le shell courant — aucune VM nécessaire.
  [bold]incus[/bold]    Labs en conteneurs — léger, démarrage rapide.
  [bold]kvm[/bold]      Machine virtuelle complète — requis pour la persistance, les services, le stockage.

Utilisez [bold]dsoxlab doctor[/bold] pour vérifier quels runtimes sont disponibles sur votre machine.""",

    "fullhelp_language": """\
[bold]Langue[/bold]

Les titres et descriptions des labs peuvent s'afficher dans plusieurs langues.

  [bold]Priorité :[/bold] variable DSOXLAB_LANG  >  fichier de contexte  >  LANG système  >  en

  Fixer de façon permanente :  [bold]dsoxlab use linux --lang fr[/bold]
  Fixer pour un appel :        [bold]DSOXLAB_LANG=fr dsoxlab list-labs[/bold]""",

    "fullhelp_update": """\
[bold]Mises à jour[/bold]

dsoxlab regarde une fois par jour si une version plus récente existe sur
PyPI, et le signale en fin de commande. La vérification ne bloque rien :
hors ligne, elle se tait.

  Mettre à jour :   [bold]uv tool upgrade dsoxlab[/bold]
  Désactiver :      [bold]DSOXLAB_NO_UPDATE_CHECK=1[/bold]""",

    "fullhelp_scoring": """\
[bold]Scoring[/bold]

  Le score démarre à [green]100 pts[/green].
  Chaque indice utilisé coûte des points (défini par lab dans [dim]hints.yaml[/dim]).
  [bold]dsoxlab check[/bold] calcule le score final et le sauvegarde.
  [bold]dsoxlab scores[/bold] affiche votre historique.""",

    # ── install ───────────────────────────────────────────────────────────────────
    "install_wrapper":              "Wrapper installé : {path}  →  {source}",
    "install_wrapper_deja":
        "Un lanceur mène déjà à ce binaire ({path}) : il vient probablement de « uv tool install » ou de pipx. On n'y touche pas, l'écraser ne ferait que défaire ce que leur prochaine mise à jour remettra.",
    "install_completion":           "Script de complétion : {path}",
    "install_rc":                   "Config shell mise à jour : {path} — rechargez avec : exec $SHELL",
    "install_completion_unsupported": "Auto-complétion non supportée pour le shell : {shell} (bash et zsh uniquement).",
    "install_reload":               "Rechargez votre shell pour activer les changements : [bold]exec $SHELL[/bold]",

    # ── use ───────────────────────────────────────────────────────────────────
    "context_set":      "Contexte actif : [bold]{label}[/bold]",
    "context_set_info": "Les commandes list-labs et validate-structure utilisent maintenant ce filtre par défaut.",
    "context_lang_set": "Langue définie : [bold]{lang}[/bold] — les titres et descriptions des labs seront affichés dans cette langue.",
    "context_target_set": "Cible par défaut : [bold]{target}[/bold] — 'dsoxlab run' l'utilisera sauf si --target est spécifié.",
    "context_provider_set": "Provider actif : [bold]{provider}[/bold]",
    "meta_read_failed": "Lecture du meta.yml impossible : {error}",
    "context_cleared":  "Contexte réinitialisé — tous les labs sont maintenant visibles.",
    "context_active":   "Contexte actif : [bold]{label}[/bold] — utilisez [bold]dsoxlab use --reset[/bold] pour tout voir.",

    # ── show ──────────────────────────────────────────────────────────────────
    "runtime_unavailable": "runtime indisponible",

    # ── run ───────────────────────────────────────────────────────────────────
    "services_docker_absent": "Ce lab a besoin d'un service conteneurisé, mais Docker est injoignable. Démarrez Docker, puis relancez la commande.",
    "service_starting":   "Démarrage du service [bold]{name}[/bold] ({image})…",
    "service_ready":      "Service [bold]{name}[/bold] prêt.",
    "service_failed":     "Le service [bold]{name}[/bold] n'a pas pu démarrer : {detail}",
    "service_stopped":    "Service [bold]{name}[/bold] arrêté.",
    "lab_starting":       "Démarrage du lab [bold]{lab_id}[/bold] (runtime: {runtime})…",
    "lab_ready":          "Lab {lab_id} prêt. Vous êtes dans [bold]{workdir}/[/bold], votre répertoire de travail isolé.",
    "lab_ready_local":    "Lab {lab_id} prêt. Vous êtes sur [bold]votre poste[/bold], à la racine du dépôt.",
    "lab_ready_target":   "Lab {lab_id} prêt. Vous êtes connecté à [bold]{host}[/bold].",
    "lab_subshell_tip":   "Tapez [bold]dsoxlab check[/bold] pour valider votre travail, ou [bold]exit[/bold] pour quitter la session.",
    "lab_welcome_title":  "Comment fonctionne ce lab",
    "lab_welcome_course": "[bold cyan]dsoxlab course[/bold cyan] [dim][<id>][/dim]   Affiche les exercices guidés ([dim]scenario.md[/dim]).",
    "lab_welcome_challenge": "[bold cyan]dsoxlab challenge[/bold cyan] [dim][<id>][/dim]   Affiche la mission challenge ([dim]challenge/README.md[/dim]).",
    "lab_welcome_check":  "[bold cyan]dsoxlab check[/bold cyan] [dim][<id>][/dim]   Lance les tests et affiche votre score — [bold]rien n'est enregistré[/bold].",
    "lab_welcome_submit": "[bold cyan]dsoxlab submit[/bold cyan] [dim][<id>][/dim]  Soumission finale : lance les tests, [bold]enregistre le résultat[/bold] en base, puis [bold]quitte[/bold] la session.",
    "lab_welcome_hint":   "[bold cyan]dsoxlab hint[/bold cyan] [dim][<id>][/dim]   Révèle l'indice suivant — [red]déduit des points[/red] de votre score final.",
    "lab_welcome_session_local": "Vous êtes sur [bold]votre poste[/bold], à la racine du dépôt : c'est d'ici que vous écrivez votre code et lancez vos commandes vers les hôtes du lab.",
    "lab_welcome_exit":   "Tapez [bold]exit[/bold] à tout moment pour quitter la session sans enregistrer.",
    "lab_welcome_session_target": "Vous allez être connecté à [bold]{host}[/bold] : travaillez-y comme sur une machine réelle.",
    "lab_welcome_commands_here": "Votre mission est affichée juste au-dessus : dsoxlab n'existe pas sur la machine, gardez-la sous les yeux. Les commandes ci-dessous se lancent depuis [bold]votre poste[/bold] — après [bold]exit[/bold], ou dans un second terminal.",
    "lab_welcome_labdir":  "Le lab vit dans [bold]{labdir}/[/bold] : les chemins de la mission sont relatifs à ce répertoire.",
    "lab_welcome_local_ssh": "La machine du lab est [bold]{host}[/bold] : connectez-vous avec [bold]dsoxlab ssh {host}[/bold] quand le sujet le demande (un ssh direct échouerait, le nom n'est pas résolvable et la clé est propre au dépôt).",
    "lab_welcome_start_here": "Commencez par [bold]dsoxlab challenge[/bold] : la mission dit quels fichiers créer et ce qui sera vérifié.",
    "lab_session_ended":  "Session terminée pour [bold]{lab_id}[/bold]. Retour à votre répertoire d'origine.",
    "lab_session_ended_local": "Session terminée pour [bold]{lab_id}[/bold]. Votre travail est conservé : relancez [bold]dsoxlab check[/bold] quand vous voulez.",
    "no_active_lab":      "Aucun lab actif en session. Exécutez [bold]dsoxlab run <id>[/bold] d'abord, ou passez l'identifiant explicitement.",
    "course_missing":      "Aucun fichier scenario.md trouvé pour ce lab.",
    "course_tip":          "Challenge prêt : dsoxlab challenge {id}",
    "course_list_title":   "Cours disponibles",
    "course_list_col_id":  "Lab ID",
    "course_list_col_title": "Titre",
    "course_list_col_status": "Cours",
    "challenge_missing":   "Aucun fichier challenge/README.md trouvé pour ce lab.",
    "challenge_workdir":   "Répertoire de travail : {path}",

    # ── hint ──────────────────────────────────────────────────────────────────
    "no_hints":       "Aucun indice disponible pour ce lab.",
    "all_hints_used": "Tous les indices ont été utilisés ({count}/{total}).",

    # ── check ─────────────────────────────────────────────────────────────────
    "validating":         "Validation de [bold]{lab_id}[/bold]…",
    "check_result_saved": "Résultat enregistré dans l'historique ({score}/{max_score} pts).",
    "all_tests_passed":   "Tous les tests sont passés.",
    "tests_failed":       "Des tests ont échoué.",
    "check_tip_submit":   "Score sauvegardé. Lancez [bold]dsoxlab submit[/bold] pour valider définitivement et terminer la session.",
    "submit_success":     "Soumission enregistrée : [green]{score}/{max_score} pts[/green]. Tous les tests sont passés.",
    "submit_partial":     "Soumission enregistrée : [yellow]{score}/{max_score} pts[/yellow] ({passed}/{total} tests réussis). Corrigez et soumettez à nouveau si besoin.",
    "submit_exit_cta":    "[bold green]\u2714 Tentative sauvegardée.[/bold green] Tapez [bold]exit[/bold] pour revenir à votre répertoire d'origine.",
    "submit_done":        "[bold green]\u2714 Tentative sauvegardée.[/bold green] Vous pouvez enchaîner avec [bold]dsoxlab run <lab>[/bold] ou libérer l'infra avec [bold]dsoxlab destroy[/bold].",

    # ── reset ─────────────────────────────────────────────────────────────────
    "resetting": "Réinitialisation de [bold]{lab_id}[/bold]…",
    "lab_reset": "Lab réinitialisé.",

    # ── clean ─────────────────────────────────────────────────────────────────
    "confirm_clean": "Supprimer les ressources du lab {lab_id} ?",
    "cleaning":      "Nettoyage de [bold]{lab_id}[/bold]…",
    "clean_done":    "Nettoyage terminé.",

    # ── validate-structure ────────────────────────────────────────────────────
    "all_labs_valid":         "Tous les labs sont valides.",
    "labs_have_issues":       "Des labs ont des problèmes de structure ou de métadonnées.",
    "opt_check_urls":
        "Vérifier aussi que chaque doc_url répond (sort sur le réseau).",
    "content_issues_header":
        "\n[bold]Contenu :[/bold]",
    "doc_url_issues_header":
        "\n[bold]Guides injoignables :[/bold]",
    "checking_doc_urls":
        "Vérification des doc_url de {count} lab(s)…",
    "metadata_issues_header": "\n[bold red]Problèmes de métadonnées :[/bold red]",

    # ── version du contrat (schema_version) ───────────────────────────────────
    "contract_issues_header": "\n[bold red]Version du contrat :[/bold red]",
    "schema_version_invalid":
        "'schema_version' doit être un entier YAML supérieur ou égal à 1, et au "
        "plus {supported}, la dernière version du contrat que ce dsoxlab lit "
        "(reçu : {got}). Sans ce champ, le fichier est lu en version 1.",
    "schema_version_too_new":
        "déclare schema_version {found}, au-delà de la version {supported}, la "
        "dernière que ce dsoxlab sait lire. Mets l'outil à jour : "
        "uv tool upgrade dsoxlab",
    "schema_version_meta_too_new":
        "Ce catalogue exige une version plus récente de dsoxlab. {path} déclare "
        "un contrat en schema_version {found}, alors que ce dsoxlab ne lit le "
        "contrat que jusqu'à la version {supported}. Mets l'outil à jour : "
        "uv tool upgrade dsoxlab",
    "schema_version_lab_skipped":
        "Lab écarté : {path} déclare un contrat en schema_version {found}, "
        "au-delà de la version {supported}, la dernière que ce dsoxlab sait "
        "lire. Le reste du catalogue est listé normalement. Mets l'outil à jour "
        "pour récupérer ce lab : uv tool upgrade dsoxlab",

    # ── doctor — libellés composants ─────────────────────────────────────────
    "check_python":   "Python",
    "check_pytest":   "pytest",
    "check_shell":    "ShellRuntime",
    "check_incus":    "incus",
    "check_kvm":      "virsh/KVM",
    "check_provider": "Provider d'infra",
    "check_terraform":    "Terraform",
    "check_ansible":      "ansible-playbook",
    "check_libvirt_pool": "Pool libvirt",
    "check_iso_tool":     "genisoimage",
    "check_labs":     "Labs détectés",
    "check_lab_home": "LAB_HOME",

    "detail_shell_always":   "toujours disponible",
    "detail_incus_missing":  "introuvable",
    "detail_incus_ok":       "client {version}, daemon ok",
    "detail_incus_daemon_down": "client {version}, daemon inactif",
    "detail_incus_no_group": "client {version}, user hors groupe incus (re-login requis)",
    "detail_incus_no_init":  "client {version}, daemon ok mais non initialisé",
    "detail_kvm_daemon_err": "virsh présent mais erreur (daemon arrêté ?)",
    "detail_kvm_missing":    "introuvable",
    "detail_pytest_missing": "introuvable",
    "detail_pytest_bundled": "embarqué avec dsoxlab (celui qu'utilise « check »)",
    "detail_pytest_via":     "via {cmd}",
    "detail_provider_unresolved": "candidats déclarés : {candidates} — aucun choisi",
    "detail_terraform_missing":
        "introuvable : « provision » ne peut pas créer les machines",
    "detail_ansible_missing":
        "introuvable : « run » ne peut pas jouer le setup.yaml d'un lab vm "
        "(ansible-runner ne l'installe pas)",
    "detail_ansible_ok":     "présent",
    "detail_pool_missing":
        "le pool « {pool} » n'existe pas : « provision » échouera sur "
        "« Pool Not Found »",
    "detail_pool_unknown":   "non vérifiable sans virsh",
    "explain_apparmor_denied":
        "Cause connue : AppArmor refuse les disques des VM. virt-aa-helper ne "
        "sait pas résoudre un disque déclaré par référence de pool, donc aucun "
        "n'entre dans le profil du domaine. Pose l'autorisation, le droit « k » "
        "compris (sans lui : « Failed to lock byte 100 ») :",
    "explain_pool_not_found":
        "Cause connue : le pool de stockage libvirt n'existe pas. Une "
        "installation fraîche n'en déclare aucun. Crée-le :",
    "explain_domain_exists":
        "Cause connue : un provisionnement précédent a échoué APRÈS avoir "
        "défini cette machine, qui n'est donc pas dans le state Terraform. "
        "« destroy » ne peut pas la voir. Retire-la à la main :",
    "detail_iso_tool_missing":
        "introuvable : incus fabrique le CD-ROM agent:config sur l'hôte, "
        "sans lui aucune VM ne démarre",
    "detail_unknown_error":  "erreur inconnue",
    "detail_labs_count":     "{count} lab(s) dans {root}",

    # ── doctor — pourquoi un composant est informatif ici ────────────────────
    "doctor_note_no_vm":
        "Aucun lab de ce dépôt n'utilise de VM : les hyperviseurs ci-dessus "
        "sont informatifs.",
    "doctor_note_other_providers":
        "Provider actif : {provider}. Les autres hyperviseurs sont informatifs.",
    "doctor_note_remote_provider":
        "Le provider {provider} tourne dans le cloud : aucun hyperviseur "
        "local n'est nécessaire.",
    "doctor_note_provider_unresolved":
        "Ce dépôt a des labs qui exigent une VM, et aucun provider n'est "
        "choisi. Choisissez-en un avec [bold]dsoxlab use --provider <nom>"
        "[/bold] : tant que ce n'est pas fait, aucun de ces labs ne tourne.",

    # ── doctor — remédiation ──────────────────────────────────────────────────
    "fix_nothing": "Aucune remédiation nécessaire.",
    "fix_count":   "{count} composant(s) à corriger…",
    "fix_needs_tty":
        "Au moins une remédiation exige sudo, mais ce shell n'est pas "
        "interactif (pas de TTY). Lancez dsoxlab depuis un terminal, ou "
        "appliquez les commandes à la main.",
    "fix_no_sudo": "sudo introuvable dans le PATH : remédiation impossible.",
    "fix_sudo_preauth":
        "[bold]{count}[/bold] commande(s) nécessitent sudo. "
        "Pré-authentification ci-dessous (un seul prompt pour toute la cascade) :",
    "fix_sudo_failed": "Pré-authentification sudo échouée : remédiations abandonnées.",
    "fix_success": "{label} : remédiation réussie.",
    "fix_failure": "{label} : échec de la remédiation (code {code}).",
    "fix_rerun":   "Relancez [bold]dsoxlab doctor[/bold] pour vérifier.",

    # ── console — tableau des labs ────────────────────────────────────────────
    "no_labs_found":    "Aucun lab trouvé.",
    "table_labs_title": "Labs disponibles",
    "col_section":      "Section",
    "col_id":           "ID",
    "col_title":        "Titre",
    "col_level":        "Niveau",
    "col_runtime":      "Runtime",
    "col_duration":     "Durée",
    "col_skills":       "Compétences",
    "col_score":        "Score",
    "col_type":         "Type",
    "col_bloc":         "Bloc",

    # ── console — progress ──────────────────────────────────────────────────
    "progress_table_title":  "Progression par bloc",
    "col_bloc_num":          "Bloc",
    "col_bloc_done":         "Complétés",
    "col_bloc_avg":          "Score moyen",
    "col_challenge":         "Challenge",
    "col_capstone":          "Capstone",
    "progress_validated":    "[green]✔ validé[/green]",
    "progress_pending":      "[dim]—[/dim]",
    "progress_no_labs":      "Aucun lab trouvé pour ce contexte (utilisez [bold]dsoxlab use <section>[/bold] d’abord).",

    # ── console — next ─────────────────────────────────────────────────────
    "next_suggestion":   "Prochain recommandé : [bold cyan]{lab_id}[/bold cyan] — {title}",
    "next_all_done":     "[green]Tous les labs validés dans ce contexte ![/green] Lancez [bold]dsoxlab progress[/bold] pour un résumé.",
    "next_no_context":   "Aucun contexte actif. Lancez [bold]dsoxlab use <section>[/bold] d’abord.",
    # ── console — détail lab ──────────────────────────────────────────────────
    "field_section":    "[bold]Section :[/bold]",
    "field_title":      "[bold]Titre :[/bold]",
    "field_level":      "[bold]Niveau :[/bold]",
    "field_runtime":    "[bold]Runtime :[/bold]",
    "field_duration":   "[bold]Durée :[/bold]",
    "field_difficulty": "[bold]Difficulté :[/bold]",
    "field_distros":    "[bold]Distros :[/bold]",
    "field_skills":     "[bold]Skills :[/bold]",
    "field_doc":        "[bold]Doc :[/bold]",
    "field_track":      "[bold]Parcours :[/bold]",
    "field_certifs":    "[bold]Certifs :[/bold]",
    "field_type":       "[bold]Type :[/bold]",
    "field_bloc":       "[bold]Bloc :[/bold]",
    "field_status":     "[bold]Statut :[/bold]",
    "field_validation": "[bold]Validation :[/bold]",
    "val_functional":   "fonctionnel",
    "val_security":     "sécurité",
    "val_persistence":  "persistance",

    # ── console — structure ───────────────────────────────────────────────────
    "tree_structure_title": "[bold]Validation de structure[/bold]",

    # ── console — doctor ──────────────────────────────────────────────────────
    "doctor_table_title":    "Requis pour ce dépôt",
    "doctor_optional_title": "Informatif — non requis ici",
    "doctor_choose_title": "Hyperviseurs : il en faut un, aucun n'est choisi",
    "doctor_choose_hint":
        "Ce dépôt a des labs qui exigent une VM. Choisissez un provider avec "
        "[bold]dsoxlab use --provider <nom>[/bold], puis relancez doctor : il "
        "ne diagnostiquera plus que celui-là. [bold]--fix[/bold] n'installe "
        "rien tant que le choix n'est pas fait, il en faut un et non les deux.",
    "doctor_optional_hint":
        "Ces composants ne bloquent rien dans ce dépôt : [bold]--fix[/bold] "
        "ne les traite pas. Installez-les seulement si vous voulez ce provider.",
    "col_component":      "Composant",
    "col_status":         "Statut",
    "col_detail":         "Détail",
    "col_remediation":    "Remédiation",
    "status_ok":          "[green]✔ OK[/green]",
    "status_ko":          "[red]✘ KO[/red]",
    "status_present":     "[green]installé[/green]",
    "status_absent":      "[dim]— absent[/dim]",
    "status_choose":      "[yellow]à choisir[/yellow]",
    "doctor_fix_hint":    "ℹ Utilisez [bold]dsoxlab doctor --fix[/bold] pour tenter la remédiation automatique.",
    "doctor_manual_hint":
        "ℹ [bold]--fix[/bold] ne sait pas corriger ce qui manque : appliquez "
        "la remédiation indiquée à la main.",

    # ── console — résultat check ──────────────────────────────────────────────
    "check_result_title":       "Résultat — {lab_id}",
    "check_result_tests":       "[bold]Tests :[/bold]",
    "check_result_hints_label": "[bold]Hints :[/bold]",
    "check_result_no_hints":    "aucun",
    "check_result_hints_used":  "{count} utilisé(s) — [yellow]-{cost} pts[/yellow]",
    "check_result_score_label": "[bold]Score :[/bold]",

    # ── console — indice ──────────────────────────────────────────────────────
    "hint_panel_title": "[bold]Indice[/bold]",
    "hint_label":       "💡 Hint {index}/{total}",
    "hint_costs":       "[dim]Coût : [red]-{cost} pts[/red]   Pénalité totale hints : [red]-{total} pts[/red][/dim]",

    # ── console — scores ──────────────────────────────────────────────────────
    "no_scores":          "Aucun résultat enregistré.",
    "scores_table_title": "Scores enregistrés",
    "col_lab":            "Lab",
    # "col_score" est déjà défini dans la section « colonnes » ci-dessus —
    # le redéfinir ici écrasait silencieusement la première valeur (F601).
    "col_tests":          "Tests",
    "col_hints":          "Hints",
    "col_validated_at":   "Validé le",
}
