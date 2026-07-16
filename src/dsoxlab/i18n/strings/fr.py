"""Traductions françaises."""

STRINGS: dict[str, str] = {
    # ── App ───────────────────────────────────────────────────────────────────
    "app_help": "dsoxlab — DevSecOps XL Labs. Pilotez vos labs depuis le terminal.",

    # ── Options globales ──────────────────────────────────────────────────────
    "opt_help":       "Affiche ce message et quitte.",
    "opt_lab_home":   "Racine du dépôt linux-training (défaut : auto-détecté).",
    "opt_level":      "Filtre par niveau (l1, l2, lfcs, rhcsa)",
    "opt_section":    "Filtre par section (linux, ansible, terraform, docker…)",
    "opt_type":       "Filtre par type : lab, challenge ou capstone",
    "opt_bloc":       "Filtre par numéro de bloc (1-8)",
    "opt_top":        "Nombre de résultats affichés",
    "opt_fix":        "Tenter la remédiation automatique des composants manquants.",
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
    "opt_version_help":   "Affiche la version de dsoxlab et quitte.",
    "cmd_install_help":   "Installe le wrapper dsoxlab dans ~/.local/bin et l'auto-complétion shell.",
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
    "provider_not_a_section": "'{name}' est un provider d'infrastructure, pas une section du catalogue.\nPour l'activer :\n  dsoxlab use --provider {name}",
    "provider_unknown":       "Provider '{name}' inconnu pour ce dépôt. Candidats : {candidates}",

    "provision_no_meta":   "Pas de meta.yml trouvé dans {root}. Es-tu dans un dépôt dsoxlab ?",
    "provision_starting":  "Provisionnement de l'infrastructure (provider : {provider})…",
    "provision_no_ssh_key": "Clé SSH du lab manquante : {path}\nSans elle, le keypair cloud serait vide et les VMs inaccessibles.\nLance d'abord : dsoxlab instructor bootstrap",
    "provision_done":      "Provisionnement terminé — {count} hôte(s) prêt(s).",
    "provision_failed":    "Provisionnement échoué : {error}",
    "provision_provider_conflict": "Impossible de provisionner sur « {current} » : le provider « {others} » a encore une infra de lab active.\nincus et KVM partagent le nom de réseau et le subnet du lab, ils ne peuvent pas tourner en même temps.\nTermine ou détruis l'autre d'abord :\n  DSOXLAB_PROVIDER={other} dsoxlab destroy",
    "provision_waiting_ssh": "Attente que les hôtes soient joignables (SSH + cloud-init)…",
    "provision_waiting_ssh_host": "Attente de {host} (SSH + cloud-init), tentative {attempt}…",
    "provision_ssh_timeout": "Délai d'attente dépassé : {error}\nLa VM démarre peut-être encore — relance `dsoxlab run` dans un instant.",
    "destroy_starting":    "Destruction de l'infrastructure (provider : {provider})…",
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

  [cyan]course[/cyan] [dim][<id>][/dim]        Réaffiche les exercices guidés (scenario.md).
                       [dim]<id>[/dim] est optionnel si un lab est actif en session.

  [cyan]challenge[/cyan] [dim][<id>][/dim]     Affiche la mission du challenge (challenge/README.md).
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

  [cyan]doctor[/cyan]               Vérifie les outils requis (Python, pytest, virsh, incus…).
    [dim]--fix[/dim]                Installe automatiquement les composants manquants.

  [cyan]install[/cyan]              Installe dsoxlab dans [bold]~/.local/bin[/bold] + auto-complétion shell.
                       Supporte bash et zsh. Rechargez le shell après exécution.

  [cyan]fullhelp[/cyan]             Ce guide.""",

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

    "fullhelp_scoring": """\
[bold]Scoring[/bold]

  Le score démarre à [green]100 pts[/green].
  Chaque indice utilisé coûte des points (défini par lab dans [dim]hints.yaml[/dim]).
  [bold]dsoxlab check[/bold] calcule le score final et le sauvegarde.
  [bold]dsoxlab scores[/bold] affiche votre historique.""",

    # ── install ───────────────────────────────────────────────────────────────────
    "install_wrapper":              "Wrapper installé : {path}  →  {source}",
    "install_completion":           "Script de complétion : {path}",
    "install_rc":                   "Config shell mise à jour : {path} — rechargez avec : exec $SHELL",
    "install_completion_unsupported": "Auto-complétion non supportée pour le shell : {shell} (bash et zsh uniquement).",
    "install_reload":               "Rechargez votre shell pour activer les changements : [bold]exec $SHELL[/bold]",

    # ── use ───────────────────────────────────────────────────────────────────
    "context_set":      "Contexte actif : [bold]{label}[/bold]",
    "context_set_info": "Les commandes list-labs et validate-structure utilisent maintenant ce filtre par défaut.",
    "context_lang_set": "Langue définie : [bold]{lang}[/bold] — les titres et descriptions des labs seront affichés dans cette langue.",
    "context_target_set": "Cible par défaut : [bold]{target}[/bold] — 'dsoxlab run' l'utilisera sauf si --target est spécifié.",
    "context_cleared":  "Contexte réinitialisé — tous les labs sont maintenant visibles.",
    "context_active":   "Contexte actif : [bold]{label}[/bold] — utilisez [bold]dsoxlab use --reset[/bold] pour tout voir.",

    # ── show ──────────────────────────────────────────────────────────────────
    "runtime_unavailable": "runtime indisponible",

    # ── run ───────────────────────────────────────────────────────────────────
    "lab_starting":       "Démarrage du lab [bold]{lab_id}[/bold] (runtime: {runtime})…",
    "lab_ready":          "Lab {lab_id} prêt. Vous êtes dans [bold]challenge/work/[/bold] — votre répertoire de travail isolé.",
    "lab_subshell_tip":   "Tapez [bold]dsoxlab check[/bold] pour valider votre travail, ou [bold]exit[/bold] pour quitter la session.",
    "lab_welcome_title":  "Comment fonctionne ce lab",
    "lab_welcome_course": "[bold cyan]dsoxlab course[/bold cyan] [dim][<id>][/dim]   Affiche les exercices guidés ([dim]scenario.md[/dim]).",
    "lab_welcome_challenge": "[bold cyan]dsoxlab challenge[/bold cyan] [dim][<id>][/dim]   Affiche la mission challenge ([dim]challenge/README.md[/dim]).",
    "lab_welcome_check":  "[bold cyan]dsoxlab check[/bold cyan] [dim][<id>][/dim]   Lance les tests et affiche votre score — [bold]rien n'est enregistré[/bold].",
    "lab_welcome_submit": "[bold cyan]dsoxlab submit[/bold cyan] [dim][<id>][/dim]  Soumission finale : lance les tests, [bold]enregistre le résultat[/bold] en base, puis [bold]quitte[/bold] la session.",
    "lab_welcome_hint":   "[bold cyan]dsoxlab hint[/bold cyan] [dim][<id>][/dim]   Révèle l'indice suivant — [red]déduit des points[/red] de votre score final.",
    "lab_welcome_exit":   "Tapez [bold]exit[/bold] à tout moment pour quitter la session sans enregistrer.",
    "lab_session_ended":  "Session terminée pour [bold]{lab_id}[/bold]. Retour à votre répertoire d'origine.",
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
    "metadata_issues_header": "\n[bold red]Problèmes de métadonnées :[/bold red]",

    # ── doctor — libellés composants ─────────────────────────────────────────
    "check_python":   "Python",
    "check_pytest":   "pytest",
    "check_shell":    "ShellRuntime",
    "check_incus":    "incus",
    "check_kvm":      "virsh/KVM",
    "check_labs":     "Labs détectés",
    "check_lab_home": "LAB_HOME",

    "detail_shell_always":   "toujours disponible",
    "detail_incus_missing":  "introuvable (optionnel)",
    "detail_kvm_daemon_err": "virsh présent mais erreur (daemon arrêté ?)",
    "detail_kvm_missing":    "introuvable (requis pour labs l2+)",
    "detail_pytest_missing": "introuvable",
    "detail_labs_count":     "{count} lab(s) dans {root}",

    # ── doctor — remédiation ──────────────────────────────────────────────────
    "fix_nothing": "Aucune remédiation nécessaire.",
    "fix_count":   "{count} composant(s) à corriger…",
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
    "doctor_table_title": "Diagnostic dsoxlab doctor",
    "col_component":      "Composant",
    "col_status":         "Statut",
    "col_detail":         "Détail",
    "col_remediation":    "Remédiation",
    "status_ok":          "[green]✔ OK[/green]",
    "status_ko":          "[red]✘ KO[/red]",
    "doctor_fix_hint":    "ℹ Utilisez [bold]dsoxlab doctor --fix[/bold] pour tenter la remédiation automatique.",

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
