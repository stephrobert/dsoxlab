"""English translations (default)."""

STRINGS: dict[str, str] = {
    # ── App ───────────────────────────────────────────────────────────────────
    "app_help": "dsoxlab — DevSecOps XL Labs. Control your labs from the terminal.",

    # ── Global options ────────────────────────────────────────────────────────
    "opt_help":     "Show this message and exit.",
    "opt_lab_home": "Root of the linux-training repo (default: auto-detected).",
    "opt_json":           "JSON output, meant for programs (editor extension, dashboard). Nothing else is printed.",
    "opt_level":    "Filter by level (l1, l2, lfcs, rhcsa)",
    "opt_section":  "Filter by section (linux, ansible, terraform, docker…)",
    "opt_type":     "Filter by type: lab, challenge or capstone",
    "opt_bloc":     "Filter by bloc number (1-8)",
    "opt_top":      "Number of displayed results",
    "opt_fix":      "Attempt automatic remediation of missing components.",
    "opt_yes":      "Confirm without asking",
    "opt_filter_lab": "Filter by lab",

    # ── Command help strings ──────────────────────────────────────────────────
    "cmd_use_help":      "Sets the active context (section and/or default level). Use --reset to clear it.",
    "cmd_use_arg":       "Active context: section or section/level (e.g.: linux, linux/l1, ansible/l2)",
    "opt_use_reset":     "Clear the active context.",
    "opt_lang":          "Language for lab content (e.g.: en, fr). Overrides auto-detection.",
    "opt_target":        "Default execution target name (must match runtime.targets[].name in lab.yaml).",
    "opt_run_target":    "Execution target for this run (overrides --target from 'use'). Must match a runtime.targets[].name.",
    "opt_check_target":  "Target to validate against (overrides the session target). Must match a runtime.targets[].name — the tests run on that host.",
    "unknown_target":    "Unknown target '{target}' for this lab. Declared targets: {declared}.",
    "infra_not_provisioned": "This lab needs a VM, and none is running: the lab infrastructure is not provisioned.\nBring it up first:\n  dsoxlab provision",
    "cmd_list_labs_help":"List all available labs (filtered by active context if set).",
    "cmd_progress_help": "Show progression by bloc (labs completed, average score, challenges and capstones).",
    "cmd_next_help":     "Recommend the next lab or challenge to complete in the active context.",
    "cmd_show_help":     "Show details and status of a lab.",
    "cmd_show_arg":      "Lab identifier (e.g.: l1-01-navigation-fichiers)",
    "cmd_guide_help":    "Open the lab's online guide in your web browser.",
    "cmd_guide_arg":     "Lab identifier (optional if a lab is active)",
    "cmd_guide_opt_print": "Print the URL instead of opening a browser.",
    "guide_opening":     "Opening the guide for {lab_id} in your browser…",
    "guide_no_url":      "Lab {lab_id} declares no doc_url: no guide to open.",
    "guide_no_browser":  "No browser could be opened. Copy the URL above.",
    "cmd_run_help":      "Prepare and start the lab environment.",
    "cmd_run_arg":       "Lab identifier",
    "cmd_course_help":    "Display a course section, or the table of contents if no section is given.",
    "cmd_course_arg":    "Lab identifier (optional if a lab is active in session)",
    "cmd_course_opt_section": "Section to display: number (1, 2 …) or id (navigation, permissions …).",
    "cmd_course_list":   "List all labs and show whether a course (scenario.md) is available.",
    "course_toc_title":  "Course — {title}",
    "course_toc_col_n":  "#",
    "course_toc_col_id": "Section ID",
    "course_toc_col_title": "Title",
    "course_toc_tip":    "Read a section: [bold]dsoxlab course {id} --section <n>[/bold]",
    "cmd_course_opt_next": "Go to the next section (increments saved position).",
    "cmd_course_opt_prev": "Go to the previous section (decrements saved position).",
    "course_nav_progress": "Section {pos}/{total}",
    "course_nav_prev":     "← [bold]dsoxlab course --prev[/bold]",
    "course_nav_next":     "→ [bold]dsoxlab course --next[/bold]",
    "course_end_title":    "End of course — {id}",
    "course_end_body":     "You have read all [bold]{total}[/bold] sections.\n\nTime to test your skills: run [bold cyan]dsoxlab challenge {id}[/bold cyan] to tackle the challenge.",
    "course_section_not_found": "Section '{name}' not found. Use [bold]dsoxlab course {id}[/bold] to list available sections.",
    "course_section_file_missing": "Section file not found: {file}",
    "cmd_challenge_help": "Display the challenge mission for this lab (challenge/README.md).",
    "cmd_challenge_arg":  "Lab identifier (optional if a lab is active in session)",
    "cmd_hint_help":     "Show the next challenge hint (deducts points from final score).",
    "cmd_hint_arg":      "Lab identifier (optional if a lab is active in session)",
    "cmd_check_help":    "Run tests, calculate score (hints deducted) and record result.",
    "cmd_check_arg":     "Lab identifier (optional if a lab is active in session)",
    "cmd_submit_help":   "Final submission: run tests, record score, then type 'exit' to leave the session.",
    "cmd_submit_arg":    "Lab identifier (optional if a lab is active in session)",
    "cmd_scores_help":   "Show recorded scores history.",
    "cmd_reset_help":    "Reset the lab to its initial state (clean + restart).",
    "cmd_reset_arg":     "Lab identifier",
    "cmd_clean_help":    "Remove all resources created by the lab.",
    "cmd_clean_arg":     "Lab identifier",
    "cmd_validate_help":  "Check structure and metadata of all labs.",
    "cmd_doctor_help":    "Diagnose the environment (runtimes, tools, detected labs).",
    "opt_version_help":   "Show the dsoxlab version and exit.",
    "cmd_install_help":   "Install the dsoxlab wrapper in ~/.local/bin and shell auto-completion.",
    "cmd_fullhelp_help":  "Show the complete platform guide (concepts, workflow, commands).",
    "cmd_provision_help": "Provision the lab infrastructure (terraform apply on the current provider).",
    "cmd_destroy_help":   "Destroy the lab infrastructure (terraform destroy).",
    "cmd_status_help":    "Check SSH connectivity to all hosts declared in meta.yml.",
    "cmd_ssh_help":       "Open an interactive SSH session on a lab host.",
    "cmd_ssh_arg":        "Host name or short alias (e.g.: alma-rhcsa-1, ubuntu-lfcs-1)",

    # ── provider resolution ───────────────────────────────────────────────────
    "provider_required":      "This command needs an infrastructure provider, and this repository declares several ({candidates}) with none active.\nPick one:\n  dsoxlab use --provider {first}   (persisted)\n  DSOXLAB_PROVIDER={first} dsoxlab <command>   (one-shot)",
    "provider_none_declared": "No infrastructure provider declared in meta.yml (infra.provider). This command needs one.",
    "provider_not_a_section": "'{name}' is an infrastructure provider, not a catalog section.\nTo activate it:\n  dsoxlab use --provider {name}",
    "provider_unknown":       "Unknown provider '{name}' for this repository. Candidates: {candidates}",

    # ── provision / destroy / status / ssh ────────────────────────────────────
    "provision_no_meta":   "No meta.yml found in {root}. Are you in a dsoxlab repository?",
    "provision_starting":  "Provisioning infrastructure (provider: {provider})…",
    "provision_no_ssh_key": "Lab SSH key missing: {path}\nWithout it, cloud keypair would be empty and VMs unreachable.\nRun first: dsoxlab instructor bootstrap",
    "provision_done":      "Provisioning complete — {count} host(s) ready.",
    "provision_failed":    "Provisioning failed: {error}",
    "provision_provider_conflict": "Cannot provision on '{current}': provider '{others}' still has active lab infrastructure.\nincus and KVM share the lab's network name and subnet, so they can't run at the same time.\nFinish or tear down the other one first:\n  DSOXLAB_PROVIDER={other} dsoxlab destroy",
    "provision_waiting_ssh": "Waiting for hosts to become reachable (SSH + cloud-init)…",
    "provision_waiting_ssh_host": "Waiting for {host} (SSH + cloud-init), attempt {attempt}…",
    "provision_ssh_timeout": "Host readiness timed out: {error}\nThe VM may still be booting — retry `dsoxlab run` in a moment.",
    "destroy_starting":    "Destroying infrastructure (provider: {provider})…",
    "destroy_done":        "Infrastructure destroyed.",
    "destroy_failed":      "Destruction failed: {error}",
    "status_no_hosts":     "meta.yml declares no hosts.",
    "status_no_key":       "SSH private key not found: {path}. Run 'dsoxlab instructor bootstrap' first.",
    "status_checking":     "Checking SSH connectivity on {count} host(s)…",
    "status_all_ok":       "All {count} hosts respond on SSH+sudo.",
    "status_partial":      "Only {ok}/{total} hosts respond on the {provider} infrastructure. Cloud-init may still be running (wait 1-2 min) or run 'dsoxlab provision' if VMs were destroyed.",
    "status_via_bastion":  "Going through bastion {bastion} (private subnet)…",
    "ssh_unknown_host":    "Unknown host: {host}. Available: {hosts}",
    "ssh_connecting":      "Connecting to {host} ({ip})…",
    "ssh_via_bastion":     "Connecting to {host} ({ip}) via bastion {bastion}…",

    # ── instructor (commandes formateur) ───────────────────────────────────────
    "cmd_instructor_help":            "Instructor commands (lab key generation, vault, hosts, ssh-config). Not for learners.",
    "cmd_instructor_bootstrap_help":  "Generate the lab SSH key (if missing) and check that terraform/ansible-runner are installed.",
    "bootstrap_key_exists":           "SSH key already present: {path}",
    "bootstrap_generating_key":       "Generating SSH ed25519 key: {path} (no passphrase)…",
    "bootstrap_key_created":          "SSH key created: {path}",
    "bootstrap_keygen_failed":        "ssh-keygen failed: {stderr}",
    "bootstrap_no_terraform":         "terraform not found in PATH. Install: https://developer.hashicorp.com/terraform/install",
    "bootstrap_terraform_ok":         "terraform: OK",
    "bootstrap_no_ansible_runner":    "ansible-runner not installed. Re-run: uv tool install --force --with ansible-runner dsoxlab",
    "bootstrap_ansible_runner_ok":    "ansible-runner: OK",

    # ── fullhelp content ────────────────────────────────────────────────────
    "fullhelp_title":   "dsoxlab — DevSecOps XL Labs",
    "fullhelp_concept": """\
[bold]What is dsoxlab?[/bold]

dsoxlab is the CLI of the [bold cyan]DevSecOps XL Labs[/bold cyan] platform: a self-contained
practice platform built to complement the training content at
[bold]https://blog.stephane-robert.info/docs/[/bold]

Each [cyan]lab[/cyan] is a standalone exercise linked to a site guide, covering a
specific skill: Linux, containers, Kubernetes, IaC, security, CI/CD…

Labs are organised by [bold]section[/bold] (linux, ansible, terraform, kubernetes…)
and [bold]level[/bold] (l1 → beginner, l2 → intermediate, lfcs, rhcsa).

Each lab exposes:
  • an observable [bold]skill[/bold] to acquire,
  • a [bold]runtime[/bold] (shell, incus container or KVM VM),
  • [bold]automated tests[/bold] to validate your solution,
  • [bold]hints[/bold] if you are stuck (with a score penalty),
  • a [bold]direct link[/bold] to the corresponding site guide.""",

    "fullhelp_workflow": """\
[bold]Typical workflow[/bold]

  1. [bold]dsoxlab list-labs[/bold]                   — browse available labs
  2. [bold]dsoxlab use linux/l1[/bold]                — focus on a section/level
  3. [bold]dsoxlab show <id>[/bold]                   — read objectives and details
  4. [bold]dsoxlab run <id>[/bold]                    — launch the lab environment
  5. Work inside the environment…
  6. [bold]dsoxlab hint <id>[/bold]                   — get a hint (costs points)
  7. [bold]dsoxlab check <id>[/bold]                  — run automated tests and get your score
  8. [bold]dsoxlab reset <id>[/bold]                  — reset to initial state and retry
  9. [bold]dsoxlab clean <id>[/bold]                  — destroy the environment when done""",

    "fullhelp_commands": """\
[bold]Command reference[/bold]

  [cyan]use <section>[/cyan][dim]/[/dim][cyan]<level>[/cyan]  Set the active context (filters list-labs and validate-structure).
                       Examples: [bold]linux[/bold]  [bold]linux/l1[/bold]  [bold]ansible/l2[/bold]
    [dim]--lang <code>[/dim]        Also sets the display language (en / fr).
    [dim]--reset / -r[/dim]         Clear the active context (show all labs again).

  [cyan]list-labs[/cyan]            List labs. Options:
    [dim]--section / -s[/dim]       Filter by section.
    [dim]--level   / -l[/dim]       Filter by level.
    [dim]--type    / -t[/dim]       Filter by type: [bold]lab[/bold], [bold]challenge[/bold] or [bold]capstone[/bold].
    [dim]--bloc    / -b[/dim]       Filter by bloc number (1–8).

  [cyan]show <id>[/cyan]            Full details of a lab (skills, runtime, links …).

  [cyan]run <id>[/cyan]             Start the lab environment (shell, incus or KVM).

  [cyan]course[/cyan] [dim][<id>][/dim]        Re-display the guided exercises (scenario.md).
                       [dim]<id>[/dim] is optional if a lab is active in the session.

  [cyan]guide[/cyan] [dim][<id>][/dim]         Open the lab's online guide in your web browser.
                       The course lives on the trainer's site: the page opens in a
                       real tab, so it renders exactly as published.
    [dim]--print[/dim]              Print the URL instead of opening a browser
                       (useful over SSH, where no browser is available).
                       [dim]<id>[/dim] is optional if a lab is active in the session.

  [cyan]challenge[/cyan] [dim][<id>][/dim]     Display the challenge mission (challenge/README.md).
                       [dim]<id>[/dim] is optional if a lab is active in the session.

  [cyan]hint[/cyan] [dim][<id>][/dim]          Display the next hint.
                       Each hint [yellow]deducts points[/yellow] from your final score.
                       [dim]<id>[/dim] is optional if a lab is active in the session.

  [cyan]check[/cyan] [dim][<id>][/dim]         Run tests, compute score, save to history.
                       Score = 100 − (hints used × cost per hint).
                       [dim]<id>[/dim] is optional if a lab is active in the session.

  [cyan]submit[/cyan] [dim][<id>][/dim]        Final submission: run tests, save score, then type [bold]exit[/bold] to end the session.
                       Use this when you are done with the lab.
                       [dim]<id>[/dim] is optional if a lab is active in the session.

  [cyan]progress[/cyan]             Bloc-by-bloc progression summary (labs done, score, challenge, capstone).

  [cyan]next[/cyan]                 Recommend the next lab to complete in the active context.

  [cyan]scores[/cyan]               Show score history.
    [dim]--section / -s[/dim]       Filter by section.
    [dim]--lab     / -l[/dim]       Filter by lab.
    [dim]--top     / -n[/dim]       Limit number of results.

  [cyan]reset <id>[/cyan]           Clean + restart the lab from scratch.

  [cyan]clean <id>[/cyan]           Destroy environment resources (with confirmation).
    [dim]--yes / -y[/dim]           Skip confirmation.

  [cyan]validate-structure[/cyan]   Check all lab.yaml files and directory layout.

  [cyan]doctor[/cyan]               Check required tools (Python, pytest, virsh, incus …).
    [dim]--fix[/dim]                Auto-install missing components.

  [cyan]install[/cyan]              Install dsoxlab in [bold]~/.local/bin[/bold] + shell auto-completion.
                       Supports bash and zsh. Reload your shell after running.

  [cyan]fullhelp[/cyan]             This guide.""",

    "fullhelp_runtimes": """\
[bold]Runtimes[/bold]

  [bold]shell[/bold]   Simple exercises in the current shell — no VM required.
  [bold]incus[/bold]   Container-based labs — lightweight, fast to start.
  [bold]kvm[/bold]     Full virtual machine — required for persistence, services, storage.

Use [bold]dsoxlab doctor[/bold] to check which runtimes are available on your machine.""",

    "fullhelp_language": """\
[bold]Language[/bold]

Lab titles and descriptions can be displayed in different languages.

  [bold]Priority:[/bold] DSOXLAB_LANG env var  >  context file  >  system LANG  >  en

  Set permanently:   [bold]dsoxlab use linux --lang fr[/bold]
  Set for one call:  [bold]DSOXLAB_LANG=fr dsoxlab list-labs[/bold]""",

    "fullhelp_scoring": """\
[bold]Scoring[/bold]

  Score starts at [green]100 pts[/green].
  Each hint used costs points (defined per lab in [dim]hints.yaml[/dim]).
  [bold]dsoxlab check[/bold] calculates the final score and saves it.
  [bold]dsoxlab scores[/bold] shows your history.""",

    # ── install ───────────────────────────────────────────────────────────────────
    "install_wrapper":              "Wrapper installed: {path}  →  {source}",
    "install_completion":           "Completion script: {path}",
    "install_rc":                   "Shell config updated: {path} — reload with: exec $SHELL",
    "install_completion_unsupported": "Auto-completion not supported for shell: {shell} (bash and zsh only).",
    "install_reload":               "Reload your shell to activate changes: [bold]exec $SHELL[/bold]",

    # ── use ───────────────────────────────────────────────────────────────────
    "context_set":      "Active context: [bold]{label}[/bold]",
    "context_set_info": "Commands list-labs and validate-structure now use this filter by default.",
    "context_lang_set": "Language set to [bold]{lang}[/bold] — lab titles and descriptions will be shown in this language.",
    "context_target_set": "Default target set to [bold]{target}[/bold] — 'dsoxlab run' will use it unless --target is given.",
    "context_cleared":  "Context reset — all labs are now visible.",
    "context_active":   "Active context: [bold]{label}[/bold] — use [bold]dsoxlab use --reset[/bold] to see all.",

    # ── show ──────────────────────────────────────────────────────────────────
    "runtime_unavailable": "runtime unavailable",

    # ── run ───────────────────────────────────────────────────────────────────
    "lab_starting":       "Starting lab [bold]{lab_id}[/bold] (runtime: {runtime})…",
    "lab_ready":          "Lab {lab_id} ready. You are now in [bold]{workdir}/[/bold] — your isolated working directory.",
    "lab_ready_local":    "Lab {lab_id} ready. You are on [bold]your own machine[/bold], at the repository root.",
    "lab_ready_target":   "Lab {lab_id} ready. You are connected to [bold]{host}[/bold].",
    "lab_subshell_tip":   "Type [bold]dsoxlab check[/bold] to validate your work, or [bold]exit[/bold] to leave the session.",
    "lab_welcome_title":  "How this lab works",
    "lab_welcome_course": "[bold cyan]dsoxlab course[/bold cyan] [dim][<id>][/dim]   Read the guided exercises ([dim]scenario.md[/dim]).",
    "lab_welcome_challenge": "[bold cyan]dsoxlab challenge[/bold cyan] [dim][<id>][/dim]   Display the challenge mission ([dim]challenge/README.md[/dim]).",
    "lab_welcome_check":  "[bold cyan]dsoxlab check[/bold cyan] [dim][<id>][/dim]   Run tests and show your score — [bold]nothing is saved[/bold].",
    "lab_welcome_submit": "[bold cyan]dsoxlab submit[/bold cyan] [dim][<id>][/dim]  Final submission: run tests, [bold]save result[/bold] to database, then [bold]exit[/bold] the session.",
    "lab_welcome_hint":   "[bold cyan]dsoxlab hint[/bold cyan] [dim][<id>][/dim]   Reveal the next hint — [red]deducts points[/red] from your final score.",
    "lab_welcome_session_local": "You are on [bold]your own machine[/bold], at the repository root: this is where you write your code and run your commands against the lab hosts.",
    "lab_welcome_exit":   "Type [bold]exit[/bold] at any time to leave the session without saving.",
    "lab_welcome_session_target": "You are about to be connected to [bold]{host}[/bold]: work there as on a real machine.",
    "lab_welcome_commands_here": "Your mission is printed just above: dsoxlab does not exist on the lab host, so keep it in sight. The commands below run from [bold]your own machine[/bold] — after [bold]exit[/bold], or in a second terminal.",
    "lab_welcome_labdir":  "The lab lives in [bold]{labdir}/[/bold]: the paths in the mission are relative to that directory.",
    "lab_welcome_start_here": "Start with [bold]dsoxlab challenge[/bold]: the mission states which files to create and what will be checked.",
    "lab_session_ended":  "Session ended for [bold]{lab_id}[/bold]. Back to your original directory.",
    "lab_session_ended_local": "Session ended for [bold]{lab_id}[/bold]. Your work is kept: run [bold]dsoxlab check[/bold] again whenever you want.",
    "no_active_lab":      "No active lab in session. Run [bold]dsoxlab run <id>[/bold] first, or pass the lab identifier explicitly.",
    "course_missing":      "No scenario.md file found for this lab.",
    "course_tip":          "Challenge ready: dsoxlab challenge {id}",
    "course_list_title":   "Available courses",
    "course_list_col_id":  "Lab ID",
    "course_list_col_title": "Title",
    "course_list_col_status": "Course",
    "challenge_missing":   "No challenge/README.md file found for this lab.",
    "challenge_workdir":   "Working directory: {path}",

    # ── hint ──────────────────────────────────────────────────────────────────
    "no_hints":       "No hints available for this lab.",
    "all_hints_used": "All hints used ({count}/{total}).",

    # ── check ─────────────────────────────────────────────────────────────────
    "validating":         "Validating [bold]{lab_id}[/bold]…",
    "check_result_saved": "Result saved to history ({score}/{max_score} pts).",
    "all_tests_passed":    "All tests passed.",
    "tests_failed":        "Some tests failed.",
    "check_tip_submit":    "Score saved. Run [bold]dsoxlab submit[/bold] to record your final attempt and end the session.",
    "submit_success":      "Submission recorded: [green]{score}/{max_score} pts[/green]. All tests passed.",
    "submit_partial":      "Submission recorded: [yellow]{score}/{max_score} pts[/yellow] ({passed}/{total} tests passed). Fix and re-submit if needed.",
    "submit_exit_cta":     "[bold green]\u2714 Attempt saved.[/bold green] Type [bold]exit[/bold] to return to your original directory.",
    "submit_done":         "[bold green]\u2714 Attempt saved.[/bold green] Continue with [bold]dsoxlab run <lab>[/bold] or release the infra with [bold]dsoxlab destroy[/bold].",

    # ── reset ─────────────────────────────────────────────────────────────────
    "resetting": "Resetting [bold]{lab_id}[/bold]…",
    "lab_reset": "Lab reset.",

    # ── clean ─────────────────────────────────────────────────────────────────
    "confirm_clean": "Delete resources for lab {lab_id}?",
    "cleaning":      "Cleaning [bold]{lab_id}[/bold]…",
    "clean_done":    "Clean complete.",

    # ── validate-structure ────────────────────────────────────────────────────
    "all_labs_valid":         "All labs are valid.",
    "labs_have_issues":       "Some labs have structure or metadata issues.",
    "metadata_issues_header": "\n[bold red]Metadata issues:[/bold red]",

    # ── doctor — component labels ─────────────────────────────────────────────
    "check_python":   "Python",
    "check_pytest":   "pytest",
    "check_shell":    "ShellRuntime",
    "check_incus":    "incus",
    "check_kvm":      "virsh/KVM",
    "check_labs":     "Labs detected",
    "check_lab_home": "LAB_HOME",

    "detail_shell_always":   "always available",
    "detail_incus_missing":  "not found (optional)",
    "detail_kvm_daemon_err": "virsh present but error (daemon stopped?)",
    "detail_kvm_missing":    "not found (required for l2+ labs)",
    "detail_pytest_missing": "not found",
    "detail_labs_count":     "{count} lab(s) in {root}",

    # ── doctor — fix ──────────────────────────────────────────────────────────
    "fix_nothing": "No remediation needed.",
    "fix_count":   "{count} component(s) to fix…",
    "fix_success": "{label}: remediation successful.",
    "fix_failure": "{label}: remediation failed (code {code}).",
    "fix_rerun":   "Run [bold]dsoxlab doctor[/bold] again to verify.",

    # ── console — labs table ──────────────────────────────────────────────────
    "no_labs_found":     "No labs found.",
    "table_labs_title":  "Available labs",
    "col_section":       "Section",
    "col_id":            "ID",
    "col_title":         "Title",
    "col_level":         "Level",
    "col_runtime":       "Runtime",
    "col_duration":      "Duration",
    "col_skills":        "Skills",
    "col_score":         "Score",
    "col_type":          "Type",
    "col_bloc":          "Bloc",

    # ── console — progress ────────────────────────────────────────────────────
    "progress_table_title":  "Progression by bloc",
    "col_bloc_num":          "Bloc",
    "col_bloc_done":         "Done",
    "col_bloc_avg":          "Avg score",
    "col_challenge":         "Challenge",
    "col_capstone":          "Capstone",
    "progress_validated":    "[green]✔ validated[/green]",
    "progress_pending":      "[dim]—[/dim]",
    "progress_no_labs":      "No labs found for this context (use [bold]dsoxlab use <section>[/bold] first).",

    # ── console — next ────────────────────────────────────────────────────────
    "next_suggestion":   "Next recommended: [bold cyan]{lab_id}[/bold cyan] — {title}",
    "next_all_done":     "[green]All labs validated in this context![/green] Run [bold]dsoxlab progress[/bold] for a summary.",
    "next_no_context":   "No active context. Run [bold]dsoxlab use <section>[/bold] first.",

    # ── console — lab detail ──────────────────────────────────────────────────
    "field_section":    "[bold]Section:[/bold]",
    "field_title":      "[bold]Title:[/bold]",
    "field_level":      "[bold]Level:[/bold]",
    "field_runtime":    "[bold]Runtime:[/bold]",
    "field_duration":   "[bold]Duration:[/bold]",
    "field_difficulty": "[bold]Difficulty:[/bold]",
    "field_distros":    "[bold]Distros:[/bold]",
    "field_skills":     "[bold]Skills:[/bold]",
    "field_doc":        "[bold]Doc:[/bold]",
    "field_track":      "[bold]Track:[/bold]",
    "field_certifs":    "[bold]Certifs:[/bold]",
    "field_type":       "[bold]Type:[/bold]",
    "field_bloc":       "[bold]Bloc:[/bold]",
    "field_status":     "[bold]Status:[/bold]",
    "field_validation": "[bold]Validation:[/bold]",
    "val_functional":   "functional",
    "val_security":     "security",
    "val_persistence":  "persistence",

    # ── console — structure ───────────────────────────────────────────────────
    "tree_structure_title": "[bold]Structure validation[/bold]",

    # ── console — doctor ──────────────────────────────────────────────────────
    "doctor_table_title": "dsoxlab doctor diagnostic",
    "col_component":      "Component",
    "col_status":         "Status",
    "col_detail":         "Detail",
    "col_remediation":    "Remediation",
    "status_ok":          "[green]✔ OK[/green]",
    "status_ko":          "[red]✘ KO[/red]",
    "doctor_fix_hint":    "ℹ Use [bold]dsoxlab doctor --fix[/bold] to attempt automatic remediation.",

    # ── console — check result ────────────────────────────────────────────────
    "check_result_title":       "Result — {lab_id}",
    "check_result_tests":       "[bold]Tests:[/bold]",
    "check_result_hints_label": "[bold]Hints:[/bold]",
    "check_result_no_hints":    "none",
    "check_result_hints_used":  "{count} used — [yellow]-{cost} pts[/yellow]",
    "check_result_score_label": "[bold]Score:[/bold]",

    # ── console — hint ────────────────────────────────────────────────────────
    "hint_panel_title": "[bold]Hint[/bold]",
    "hint_label":       "💡 Hint {index}/{total}",
    "hint_costs":       "[dim]Cost: [red]-{cost} pts[/red]   Total hint penalty: [red]-{total} pts[/red][/dim]",

    # ── console — scores ──────────────────────────────────────────────────────
    "no_scores":         "No results recorded.",
    "scores_table_title":"Recorded scores",
    "col_lab":           "Lab",
    # "col_score" is already defined in the "columns" section above —
    # redefining it here silently overrode the first value (F601).
    "col_tests":         "Tests",
    "col_hints":         "Hints",
    "col_validated_at":  "Validated on",
}
