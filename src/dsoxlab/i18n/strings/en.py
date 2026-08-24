"""English translations (default)."""

STRINGS: dict[str, str] = {
    # ── App ───────────────────────────────────────────────────────────────────
    "app_help": "dsoxlab — DevSecOps XL Labs. Control your labs from the terminal.",

    # ── Global options ────────────────────────────────────────────────────────
    "opt_help":     "Show this message and exit.",
    "opt_lab_home": "Root of the lab catalog (default: auto-detected).",
    "opt_json":           "JSON output, meant for programs (editor extension, dashboard). Nothing else is printed.",
    "opt_level":    "Filter by level (l1, l2, lfcs, rhcsa)",
    "opt_section":  "Filter by section (linux, ansible, terraform, docker…)",
    "opt_type":     "Filter by type: lab, challenge or capstone",
    "opt_bloc":     "Filter by bloc number (1-8)",
    "opt_top":      "Number of displayed results",
    "opt_fix":      "Attempt automatic remediation of missing components.",
    "opt_no_pager": "Print everything at once instead of paging output longer than the screen.",
    "opt_use_provider":
        "Infra provider to activate (e.g. kvm, outscale, incus). "
        "Overridden by DSOXLAB_PROVIDER. Persisted across commands.",
    "opt_provision_host":
        "Target a single VM (fqdn from meta.yml). Repeatable. When omitted, "
        "applies the whole plan. Shared resources (network, base images) are "
        "handled by Terraform in cascade.",
    "opt_destroy_host":
        "Restrict the Terraform target to one fqdn from meta.yml. Repeatable. "
        "WARNING: Terraform also destroys everything that depends on the target, "
        "so this option does NOT isolate one VM from the others. To recover a "
        "single machine, prefer a full destroy + provision.",
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
    "opt_verbose":
        "Say what the engine is doing, on standard error. Repeatable: -v for information, -vv for full detail.",
    "opt_debug":      "Same as -vv. The full log is written to ~/.local/state/dsoxlab/dsoxlab.log either way.",
    "opt_version_help":   "Show the dsoxlab version and exit.",
    "cmd_install_help":   "Deprecated: use `dsoxlab completion install`. Installs shell completion.",
    "cmd_demo_help":
        "Install a demonstration catalog and play a first lab, with nothing to "
        "clone and nothing to provision.",
    "opt_demo_force":
        "Reinstall over the existing one, losing the progress and answers "
        "already there.",
    "demo_installee":  "Demonstration catalog installed in {path}",
    "demo_deja_installee":
        "The demonstration catalog is already installed in {path}.",
    "demo_deja_installee_suite":
        "It may hold your progress and your answers, so nothing was touched.\n"
        "To pick it up: cd {path} && dsoxlab list-labs\n"
        "To start over: dsoxlab demo --force",
    "demo_echec":      "Cannot install: {error}",
    "demo_suite":
        "To get started:\n"
        "  cd {path}\n"
        "  dsoxlab course {lab}\n"
        "  dsoxlab run {lab}\n"
        "Then, once the mission is done: dsoxlab check {lab}",

    # ── catalog: discover, install and locate a catalogue ───────────────────
    "cmd_catalog_help":
        "Discover, install and update lab catalogues.",
    "cmd_catalog_list_help":
        "List known catalogues and the ones installed.",
    "cmd_catalog_add_help":
        "Install a catalogue by name, or by its repository URL.",
    "cmd_catalog_update_help":
        "Update an installed catalogue (all of them if none is named).",
    "cmd_catalog_remove_help":
        "Remove an installed catalogue.",
    "arg_catalog_reference":
        "Id from the manifest (dsoxlab catalog list), or a git repository URL.",
    "arg_catalog_id":
        "Id of an installed catalogue.",
    "cmd_catalog_use_help":
        "Choose the active catalogue, the one used outside its directory.",
    "opt_catalog_force":
        "Reinstall over an existing catalogue (any work in it is lost).",
    "catalog_titre_connus": "Known catalogues",
    "catalog_titre_installes": "Installed catalogues",
    "catalog_col_id": "Id",
    "catalog_col_description": "Description",
    "catalog_col_depot": "Repository",
    "catalog_col_chemin": "Path",
    "catalog_col_actif": "Active",
    "catalog_aucun_installe":
        "No catalogue installed. Install one: dsoxlab catalog add <id>",
    "catalog_installation": "Installing {name} from {url}…",
    "catalog_installe":
        "Catalogue '{name}' installed in {path}, and made active.",
    "catalog_installe_suite":
        "It is usable from any directory:\n"
        "  dsoxlab list-labs\n"
        "  dsoxlab next",
    "catalog_actif_defini": "Active catalogue: '{name}' ({path})",
    "catalog_retire": "Catalogue '{name}' removed ({path}).",
    "catalog_a_jour": "Catalogue '{name}' is up to date.",
    "catalog_mis_a_jour": "Catalogue '{name}' updated: {detail}",
    "catalog_inconnu":
        "Unknown catalogue '{name}'. List them with dsoxlab catalog list, "
        "or pass its repository URL.",
    "catalog_absent":
        "No catalogue '{name}' installed. See: dsoxlab catalog list",
    "catalog_deja_installe":
        "Catalogue '{name}' is already installed in {path}. "
        "Update it (dsoxlab catalog update {name}), or reinstall with --force, "
        "which loses the progress and the work it holds.",
    "catalog_clone_echec":
        "Cloning {url} failed:\n{detail}",
    "catalog_sans_meta":
        "Repository {url} has no meta.yml at its root: it is not a dsoxlab "
        "catalogue.",
    "catalog_id_invalide":
        "'{name}' cannot be used as a catalogue id.",
    "catalog_update_echec":
        "Updating '{name}' failed:\n{detail}",

    "cmd_support_help":
        "Produce an anonymised diagnostic report, ready to paste into an issue.",
    "opt_support_log_lines":
        "How many log lines to include (0 to include none).",
    "support_hint":
        "Paste this report into your issue. It carries no personal path, no "
        "public address and no machine name.",
    "cmd_fullhelp_help":  "Show the complete platform guide (concepts, workflow, commands).",
    "cmd_provision_help": "Provision the lab infrastructure (terraform apply on the current provider).",
    "cmd_destroy_help":   "Destroy the lab infrastructure (terraform destroy), including machines left outside the state.",
    "cmd_status_help":    "Check SSH connectivity to all hosts declared in meta.yml, and name the cause when one stays silent.",
    "cmd_ssh_help":       "Open an interactive SSH session on a lab host.",
    "cmd_ssh_arg":        "Host name or short alias (e.g.: alma-rhcsa-1, ubuntu-lfcs-1)",

    # ── provider resolution ───────────────────────────────────────────────────
    "provider_required":      "This command needs an infrastructure provider, and this repository declares several ({candidates}) with none active.\nPick one:\n  dsoxlab use --provider {first}   (persisted)\n  DSOXLAB_PROVIDER={first} dsoxlab <command>   (one-shot)",
    "provider_none_declared": "No infrastructure provider declared in meta.yml (infra.provider). This command needs one.",
    "section_unknown":
        "Unknown section: \"{name}\". The catalog would come out empty.\n"
        "Sections declared in meta.yml: {sections}.\n"
        "To see everything: dsoxlab use --reset",
    "provider_not_a_section": "'{name}' is an infrastructure provider, not a catalog section.\nTo activate it:\n  dsoxlab use --provider {name}",
    "provider_unknown":       "Unknown provider '{name}' for this repository. Candidates: {candidates}",

    # ── provision / destroy / status / ssh ────────────────────────────────────
    "provision_no_meta":   "No meta.yml found in {root}. Are you in a dsoxlab repository?",
    "host_unknown":        "Unknown host: '{fqdn}'. Known hosts: {known}.",
    "terraform_target":    "Terraform target: {hosts} ({count} resources)",

    # ── progress bars ────────────────────────────────────────────────────────
    "progress_tests_running":  "Tests: {lab_id}",
    "progress_tests_done":     "Tests {lab_id} finished",
    "progress_ansible_task":   "Task: {task}",
    "progress_playbook_done":  "{playbook} complete",
    "progress_tf_init_done":   "Terraform init complete",
    "progress_action_done":    "{action} complete",
    "progress_nothing_to_do":  "Nothing to do",
    "provision_starting":  "Provisioning infrastructure (provider: {provider})…",
    "provision_no_ssh_key": "Lab SSH key missing: {path}\nWithout it, cloud keypair would be empty and VMs unreachable.\nRun first: dsoxlab instructor bootstrap",
    "provision_done":      "Provisioning complete — {count} host(s) ready.",
    "provision_failed":    "Provisioning failed: {error}",
    "provision_provider_conflict": "Cannot provision on '{current}': provider '{others}' still has active lab infrastructure.\nincus and KVM share the lab's network name and subnet, so they can't run at the same time.\nFinish or tear down the other one first:\n  DSOXLAB_PROVIDER={other} dsoxlab destroy",
    "provision_waiting_ssh": "Waiting for hosts to become reachable (SSH + cloud-init)…",
    "provision_waiting_ssh_host": "Waiting for {host} (SSH + cloud-init), attempt {attempt}…",
    "provision_ssh_timeout": "Host readiness timed out: {error}\nThe VM may still be booting — retry `dsoxlab run` in a moment.\nOn a modest machine, booting several VMs at once saturates the CPU and overruns this delay. Raise it:\n  DSOXLAB_HOST_READY_TIMEOUT=360 dsoxlab provision",
    "confirm_destroy":
        "Destroy the whole {provider} infrastructure? "
        "All VM data will be lost",
    "difficulty_beginner":     "beginner",
    "difficulty_intermediate": "intermediate",
    "difficulty_advanced":     "advanced",
    "update_available":
        "\n[dim]A newer version of dsoxlab is available: "
        "{latest} (you have {current}).\n"
        "Upgrade with: uv tool upgrade dsoxlab[/dim]",
    "destroy_host_not_isolated":
        "Warning: Terraform also destroys everything that depends on the target. "
        "Host targeting therefore does not isolate one VM from the others. To "
        "recover an unreachable machine, prefer \"dsoxlab destroy\" then "
        "\"dsoxlab provision\": the whole park is rebuilt from scratch.",
    "destroy_starting":    "Destroying infrastructure (provider: {provider})…",
    "ssh_fragment_failed":  "SSH fragment not written: {error}. Connecting by machine name will not work.",
    "ssh_fragment_written": "Direct connection enabled: [bold]ssh <machine>[/bold] now works (fragment {path}).",
    "ssh_fragment_no_include": "SSH fragment written to {path}, but your ~/.ssh/config has no [bold]Include ~/.ssh/config.d/*.conf[/bold] line: add it at the top of the file, otherwise the fragment is never read.",
    "ssh_fragment_removed": "SSH fragment for [bold]{repo}[/bold] removed: it pointed at destroyed machines.",
    "destroy_done":        "Infrastructure destroyed.",
    "destroy_failed":      "Destruction failed: {error}",
    "snapshot_purge_done":
        "{count} snapshot overlay file(s) removed before destruction: Terraform "
        "does not know about them and would have left them behind.",
    "snapshot_purge_failed":
        "Snapshots could not be purged ({error}). If this infrastructure had "
        "any, their overlay files stay in the storage pool after destruction.",
    "status_no_hosts":     "meta.yml declares no hosts.",
    "status_no_key":       "SSH private key not found: {path}. Run 'dsoxlab instructor bootstrap' first.",
    "status_checking":     "Checking SSH connectivity on {count} host(s)…",
    "status_all_ok":       "All {count} hosts respond on SSH+sudo.",
    "status_partial":      "Only {ok}/{total} hosts respond on the {provider} infrastructure.",
    "status_via_bastion":  "Going through bastion {bastion} (private subnet)…",

    # ── status — machines left behind, and why a host stays silent ────────────
    "orphan_check_skipped":
        "Cannot ask the hypervisor which machines it holds ({error}). "
        "Machines left behind by a failed provisioning, if any, go undetected.",
    "provision_orphan_domains":
        "These machines already exist on the hypervisor but are absent from the "
        "Terraform state: {hosts}. A previous provisioning failed after defining "
        "them, so Terraform neither knows nor destroys them, and creating them "
        "again would fail on 'domain already exists'.",
    "provision_orphan_fix":
        "Remove them, then run dsoxlab provision again: {cmd}",
    "destroy_orphan_domains":
        "Terraform destroyed what it knew about, but these machines are still "
        "defined on the hypervisor: {hosts}. A previous provisioning defined "
        "them without ever recording them in the state.",
    "confirm_destroy_orphans":
        "Remove them from the hypervisor? This cannot be undone",
    "destroy_orphan_removed":
        "Removed from the hypervisor: {hosts}",
    "destroy_orphan_kept":
        "Left in place. Remove them yourself, then run dsoxlab destroy again: {cmd}",
    "destroy_orphan_failed":
        "Could not remove {host}: {error}",
    "status_hypervisor_unavailable":
        "The hypervisor did not answer ({error}), so the diagnosis below only "
        "reflects what SSH says, not the state of the machines.",
    "status_provider_not_inspectable":
        "Provider '{provider}' exposes no machine state that can be queried from "
        "here: the diagnosis below only reflects what SSH says.",
    "status_cause_domain_absent":
        "no domain named '{host}' on the hypervisor: provisioning never created "
        "this machine. Run: dsoxlab provision",
    "status_cause_domain_not_running":
        "domain '{domain}' exists and is '{state}': the template starts it at "
        "boot, so it was stopped afterwards (out-of-memory killer, qemu crash, "
        "manual stop). Run: sudo virsh start {domain}",
    "status_cause_domain_no_lease":
        "domain '{domain}' is running but holds no DHCP lease: it is still "
        "booting, or its network did not come up. Watch it boot: "
        "sudo virsh console {domain}",
    "status_cause_booting":
        "domain '{domain}' is running and holds its address, but SSH is not open "
        "yet: cloud-init has not finished. Wait a minute, then run dsoxlab status "
        "again.",
    "status_cause_ssh_refused":
        "something answers at {ip} and refuses the connection: the machine is up, "
        "sshd is not listening yet. Wait, then run dsoxlab status again.",
    "status_cause_unreachable":
        "nothing answers at {ip}: no machine holds this address on the network.",
    "status_cause_ssh_timeout":
        "{ip} does not answer within the timeout: packets are being dropped "
        "(firewall) or the machine is frozen.",
    "status_cause_ssh_denied":
        "{ip} answers but refuses the key: the machine is up and its SSH account "
        "or key does not match the one this repository holds.",
    "status_cause_unknown":
        "SSH failed for a reason this diagnosis does not recognise: {reason}",
    "ssh_unknown_host":    "Unknown host: {host}. Available: {hosts}",
    "ssh_connecting":      "Connecting to {host} ({ip})…",
    "ssh_via_bastion":     "Connecting to {host} ({ip}) via bastion {bastion}…",

    # ── instructor (commandes formateur) ───────────────────────────────────────
    "cmd_instructor_help":            "Instructor commands (lab key generation, vault, hosts, ssh-config). Not for learners.",
    "cmd_instructor_bootstrap_help":  "Generate the lab SSH key (if missing) and check that terraform/ansible-runner are installed.",
    "bootstrap_key_exists":           "SSH key already present: {path}",
    "bootstrap_not_a_lab_repo":
        "{root} is not a lab repository: no meta.yml at its root.\n"
        "No key was generated: it would land in an arbitrary directory, "
        "outside of any .gitignore.\n"
        "Move into the lab repository, or point at it:\n"
        "  dsoxlab instructor bootstrap --lab-home /path/to/the-repo",
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

dsoxlab turns [bold]declarative exercises[/bold] into reproducible, runnable and
verifiable environments.

A [bold]catalog[/bold] is a repository that states what it offers: a root [cyan]meta.yml[/cyan]
for the topology, one [cyan]lab.yaml[/cyan] per lab for what that lab needs. Nothing
about a domain lives in the tool, so the same engine serves Linux, Ansible,
Terraform or Kubernetes labs, and any other catalog that honors the contract.

Labs are organised by [bold]section[/bold] and [bold]level[/bold], both named by the catalog itself.

Each lab declares:
  • an observable [bold]skill[/bold] to acquire,
  • a [bold]runtime[/bold] ([bold]shell[/bold] on your machine, or a [bold]vm[/bold] provisioned for you),
  • [bold]automated tests[/bold] that read the state of the system, not the commands typed,
  • [bold]hints[/bold] if you are stuck (with a score penalty),
  • a [bold]link[/bold] to the guide that goes with it.""",

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
    [dim]--json[/dim]               The catalog as a machine document.

  [cyan]show <id>[/cyan]            Full details of a lab (skills, runtime, links …).
    [dim]--json[/dim]               The lab and its runtime status, as a document.

  [cyan]run <id>[/cyan]             Start the lab environment (a shell, or a provisioned vm).

  [cyan]course[/cyan] [dim][<id>][/dim]        Display the course: one section at a time when the lab
                       declares them (course.yaml), otherwise scenario + README.
    [dim]--section / -s[/dim]       Section to display: number or id.
    [dim]--next    / -n[/dim]       Next section.  [dim]--prev / -p[/dim]: previous one.
    [dim]--no-pager[/dim]           Print everything at once, without paging.
                       [dim]<id>[/dim] is optional if a lab is active in the session.

  [cyan]guide[/cyan] [dim][<id>][/dim]         Open the lab's online guide in your web browser.
                       The course lives on the trainer's site: the page opens in a
                       real tab, so it renders exactly as published.
    [dim]--print[/dim]              Print the URL instead of opening a browser
                       (useful over SSH, where no browser is available).
                       [dim]<id>[/dim] is optional if a lab is active in the session.

  [cyan]challenge[/cyan] [dim][<id>][/dim]     Display the challenge mission (challenge/README.md).
    [dim]--no-pager[/dim]           Print everything at once, without paging.
                       [dim]<id>[/dim] is optional if a lab is active in the session.

  [cyan]hint[/cyan] [dim][<id>][/dim]          Display the next hint.
                       Each hint [yellow]deducts points[/yellow] from your final score.
                       [dim]<id>[/dim] is optional if a lab is active in the session.

  [cyan]check[/cyan] [dim][<id>][/dim]         Run tests, compute score, save to history.
                       Score = 100 − (hints used × cost per hint).
    [dim]--json[/dim]               The result as a document. Same exit code.
                       [dim]<id>[/dim] is optional if a lab is active in the session.

  [cyan]submit[/cyan] [dim][<id>][/dim]        Final submission: run tests, save score, then type [bold]exit[/bold] to end the session.
                       Use this when you are done with the lab.
                       On a lab declaring [bold]exam_passing_score[/bold], also renders a
                       [yellow]pass / fail verdict[/yellow] against that mark.
                       [dim]<id>[/dim] is optional if a lab is active in the session.

  [cyan]progress[/cyan]             Bloc-by-bloc progression summary (labs done, score, challenge, capstone).
    [dim]--json[/dim]               The same progression, as a document.

  [cyan]next[/cyan]                 Recommend the next lab to complete in the active context.
    [dim]--json[/dim]               The suggestion and what remains, as a document.

  [cyan]scores[/cyan]               Show score history. A [bold]Verdict[/bold] column appears when the
                       catalog holds at least one lab with an exam pass mark.
    [dim]--section / -s[/dim]       Filter by section.
    [dim]--lab     / -l[/dim]       Filter by lab.
    [dim]--top     / -n[/dim]       Limit number of results.
    [dim]--json[/dim]               The history and each exam verdict, as a document.

  [cyan]reset <id>[/cyan]           Clean + restart the lab from scratch.

  [cyan]clean <id>[/cyan]           Destroy environment resources (with confirmation).
    [dim]--yes / -y[/dim]           Skip confirmation.

  [cyan]validate-structure[/cyan]   Check all lab.yaml files and directory layout.
    [dim]--json[/dim]               Every issue with its rule key, as a document.
                       Same exit code: 1 as soon as one lab fails.

  [cyan]doctor[/cyan]               Diagnose the environment. The [bold]Required[/bold] table lists what
                       blocks this very repo; a hypervisor useless here stays
                       [bold]Informational[/bold] and never shows up as an error.
    [dim]--fix[/dim]                Remediate the missing required components.
                       Informational components are left alone.
    [dim]--json[/dim]               The diagnosis as a document, each check carrying a
                       stable key and state. Not with [bold]--fix[/bold].

  [cyan]demo[/cyan]                 Install a demonstration catalog and a first lab you can
                       play right away, with nothing to clone or provision.
    [dim]--force[/dim]              Reinstall over it (loses progress).

  [cyan]catalog list[/cyan]         Known catalogues, and the ones installed.
    [dim]--json[/dim]               Machine document instead of tables.
  [cyan]catalog add <id|url>[/cyan] Installs a catalogue and makes it active. The id comes
                       from the packaged manifest; any git URL is accepted too,
                       the manifest restricts nothing.
    [dim]--force[/dim]              Reinstall over it (loses progress).
  [cyan]catalog use <id>[/cyan]     Chooses the active catalogue, the one used without
                       having to sit in its directory.
  [cyan]catalog update [id][/cyan]  Updates one installed catalogue, or all of them.
  [cyan]catalog remove <id>[/cyan]  Removes an installed catalogue.

  [cyan]provision[/cyan]            Bring up the infrastructure for vm labs (terraform apply).
                       Refuses to start when machines left by a failed
                       provisioning are still defined on the hypervisor, and
                       names the command that removes them.
    [dim]--host <fqdn>[/dim]         Target a single machine. Repeatable.

  [cyan]status[/cyan]               Check SSH connectivity of the declared hosts, and say why
                       one stays silent. On a provider whose machine state can
                       be queried, the hypervisor is [bold]asked[/bold]: a domain that
                       does not exist, one that is stopped and one that is
                       booting call for three different gestures.
    [dim]--json[/dim]               Host reachability, as a document.

  [cyan]ssh <host>[/cyan]           Open an interactive session on a lab host.

  [cyan]destroy[/cyan]              Tear down the infrastructure for vm labs (terraform destroy),
                       then remove — after confirmation — the machines a failed
                       provisioning left defined outside the Terraform state.
                       Exits non-zero if any of them remains.
    [dim]--yes[/dim]                 Do not ask for confirmation, orphan machines included.

  [cyan]completion install[/cyan]   Install shell auto-completion (bash, zsh).
                       Reload your shell afterwards: [bold]exec $SHELL[/bold]
  [cyan]completion show[/cyan]      Print the script on stdout, writing nothing.
    [dim]--shell <name>[/dim]      zsh, bash or fish. Default: the current shell.

  [cyan]install[/cyan]              [bold]Deprecated[/bold] since 0.1.62, removed in 0.3.0.
                       Does what [bold]completion install[/bold] does, and warns.

  [cyan]support[/cyan]              Diagnostic report to paste into an issue:
                       versions, tools, catalog, latest traces. Anonymised by
                       default (no personal path, no public address).
    [dim]--json[/dim]               The same content, as a machine document.
    [dim]--log-lines <n>[/dim]      How many log lines to include (0 for none).

  [cyan]fullhelp[/cyan]             This guide.

[bold]Global options[/bold] [dim](before the command)[/dim]

  [dim]--verbose / -v[/dim]       Say what the engine is doing, on standard error.
                       Repeatable: [bold]-v[/bold] for information,
                       [bold]-vv[/bold] for full detail.
  [dim]--debug[/dim]              Same as [bold]-vv[/bold].
  [dim]--version[/dim]            Print the version and exit.

  The full log is written to [bold]~/.local/state/dsoxlab/dsoxlab.log[/bold]
  either way, so there is no need to replay the command. It never goes to
  standard output: [bold]--json[/bold] stays machine-readable, even in verbose
  mode.""",

    "fullhelp_machine": """\
[bold]Machine output[/bold]

  [bold]--json[/bold] turns a command into one document meant for a program: an editor
  extension, a dashboard, a tracking script. Ten commands take it: [bold]list-labs[/bold],
  [bold]show[/bold], [bold]progress[/bold], [bold]next[/bold], [bold]scores[/bold], [bold]check[/bold], [bold]status[/bold], [bold]doctor[/bold],
  [bold]validate-structure[/bold] and [bold]support[/bold].

  Standard output then carries the document and [bold]nothing else[/bold]. Notices,
  tips and the update warning all go to standard error, so a pipe reads clean.

  Every document carries a [bold]schema[/bold] number. Adding a field keeps that number;
  changing what a field means increments it.

  A verdict is read from a stable [bold]key[/bold] and a [bold]state[/bold] token, never from the
  translated label beside them: no integration should have to parse English or
  French to know whether something is green or red.

  [bold]--json[/bold] changes the shape of the output, never the verdict nor the exit
  code. On a hard error (unknown lab, unreadable meta.yml) standard output stays
  empty, the reason goes to standard error, and the code is unchanged.

  Field by field: [bold]docs/machine-output.md[/bold].""",

    "fullhelp_runtimes": """\
[bold]Runtimes[/bold]

  [bold]shell[/bold]   Simple exercises in the current shell — no VM required.
  [bold]vm[/bold]      Full machine — required for persistence, services, storage.
          Which backend serves it (KVM/libvirt, Incus, Outscale) is declared by
          the catalog in [bold]meta.yml: infra.provider[/bold], not by the lab.

Use [bold]dsoxlab doctor[/bold] to check what is available on your machine.""",

    "fullhelp_language": """\
[bold]Language[/bold]

Lab titles and descriptions can be displayed in different languages.

  [bold]Priority:[/bold] DSOXLAB_LANG env var  >  context file  >  system LANG  >  en

  Set permanently:   [bold]dsoxlab use linux --lang fr[/bold]
  Set for one call:  [bold]DSOXLAB_LANG=fr dsoxlab list-labs[/bold]""",

    "fullhelp_update": """\
[bold]Updates[/bold]

dsoxlab checks once a day whether a newer version exists on PyPI, and says so
at the end of a command. The check never blocks anything: offline, it stays
silent.

  Upgrade:  [bold]uv tool upgrade dsoxlab[/bold]
  Disable:  [bold]DSOXLAB_NO_UPDATE_CHECK=1[/bold]""",

    "fullhelp_scoring": """\
[bold]Scoring[/bold]

  Score starts at [green]100 pts[/green].
  Each hint used costs points (defined per lab in [dim]hints.yaml[/dim]).
  [bold]dsoxlab check[/bold] calculates the final score and saves it.
  [bold]dsoxlab scores[/bold] shows your history.""",

    # ── install ───────────────────────────────────────────────────────────────────
    "install_wrapper":              "Wrapper installed: {path}  →  {source}",
    "install_wrapper_deja":
        "A launcher already points at this binary ({path}): it most likely comes from `uv tool install` or pipx. Leaving it alone, since overwriting it would only undo what their next upgrade restores.",
    "install_completion":           "Completion script: {path}",
    "install_rc":                   "Shell config updated: {path} — reload with: exec $SHELL",
    "install_completion_unsupported": "Auto-completion not supported for shell: {shell} (bash and zsh only).",
    "install_reload":               "Reload your shell to activate changes: [bold]exec $SHELL[/bold]",

    # ── use ───────────────────────────────────────────────────────────────────
    "context_set":      "Active context: [bold]{label}[/bold]",
    "context_set_info": "Commands list-labs and validate-structure now use this filter by default.",
    "context_lang_set": "Language set to [bold]{lang}[/bold] — lab titles and descriptions will be shown in this language.",
    "context_target_set": "Default target set to [bold]{target}[/bold] — 'dsoxlab run' will use it unless --target is given.",
    "context_provider_set": "Active provider: [bold]{provider}[/bold]",
    "meta_read_failed": "Cannot read meta.yml: {error}",
    "context_cleared":  "Context reset — all labs are now visible.",
    "context_active":   "Active context: [bold]{label}[/bold] — use [bold]dsoxlab use --reset[/bold] to see all.",

    # ── show ──────────────────────────────────────────────────────────────────
    "runtime_unavailable": "runtime unavailable",

    # ── run ───────────────────────────────────────────────────────────────────
    "services_docker_absent": "This lab needs a containerised service, but Docker is not reachable. Start Docker, then run the command again.",
    "service_starting":   "Starting service [bold]{name}[/bold] ({image})…",
    "service_ready":      "Service [bold]{name}[/bold] is ready.",
    "service_failed":     "Service [bold]{name}[/bold] could not start: {detail}",
    "service_stopped":    "Service [bold]{name}[/bold] stopped.",
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
    "lab_welcome_local_ssh": "The lab machine is [bold]{host}[/bold]: connect with [bold]dsoxlab ssh {host}[/bold] when the brief asks for it (a plain ssh would fail: the name does not resolve and the key belongs to the repository).",
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
    "opt_check_urls":
        "Also check that every doc_url answers (hits the network).",
    "content_issues_header":
        "\n[bold]Content:[/bold]",
    "doc_url_issues_header":
        "\n[bold]Unreachable guides:[/bold]",
    "checking_doc_urls":
        "Checking doc_url for {count} lab(s)…",
    "metadata_issues_header": "\n[bold red]Metadata issues:[/bold red]",

    # ── validate-structure: what each validator found ────────────────────────
    # Les validators ne composent aucune phrase : ils portent une clé et ses
    # paramètres, et le texte se dit ici, dans la langue de l'auteur.
    "struct_missing_file": "Missing file: {name}",
    "struct_missing_dir":  "Missing directory: {name}/",
    "struct_vm_targets_empty":
        "runtime.type is 'vm' but runtime.targets[] is empty. Declare at least "
        "one target, with its name and its host.",
    "struct_default_unknown":
        "runtime.default='{default}' matches no runtime.targets[].name. "
        "Available: {available}",
    "struct_session_unknown":
        "runtime.session='{session}' is unknown. Accepted values: 'target' (SSH "
        "session on targets[].host, the default) or 'local' (sub-shell on the "
        "learner's machine, for a lab driven from the repository).",
    "struct_shell_workdir_empty":
        "runtime.type is 'shell' but runtime.workdir is empty. Declare the work "
        "directory (e.g. workdir: challenge/work).",
    "struct_forbidden_cleanup_sh_vm":
        "cleanup.sh is not allowed for runtime: vm. Use cleanup.yaml.",
    "struct_forbidden_cleanup_sh_shell":
        "cleanup.sh is not allowed for runtime: shell. Declare fixtures in lab.yaml.",
    "struct_forbidden_kvm_sh":
        "runtime/kvm.sh is not allowed. Use setup.yaml.",
    "struct_forbidden_incus_sh":
        "runtime/incus.sh is not allowed. Use setup.yaml.",
    "struct_forbidden_shell_sh":
        "runtime/shell.sh is not allowed. Preparation is declared through "
        "runtime.workdir and runtime.fixtures.",
    "struct_forbidden_makefile":
        "A Makefile is not allowed in a lab: dsoxlab drives everything.",

    "metadata_field_empty": "the '{field}' field is empty",
    "metadata_list_empty":  "the '{field}' list is empty",
    "metadata_doc_url_scheme": "invalid URL (http/https scheme expected): {url}",
    "metadata_lab_type_invalid":
        "Invalid value '{value}'. Expected one of: {expected}",
    "metadata_exam_score_invalid":
        "Invalid value '{value}'. Expected a percentage of the lab scale, "
        "between 1 and 100 (omit the field for a lab that is not an exam).",

    "content_broken_links": "{count} dead relative link(s): {links}",
    "content_solution_unreadable": "unreadable: {error}",
    "content_solution_plaintext":
        "solution in plain text: encrypt it with 'ansible-vault encrypt', "
        "otherwise git keeps it forever and the lab is spoiled",
    "content_scoring_tasks_vs_tests":
        "{tasks} scored task(s) for {tests} test(s): the score is computed per "
        "test, so the scale on display is not the mark that comes out",
    "content_scoring_points_mismatch":
        "the tasks add up to {total} points, the header announces {announced}",
    "content_scoring_count_mismatch":
        "{count} scored task(s), the header announces {announced}",
    "content_missing_english": "no English counterpart ({name})",
    "content_target_host_unknown":
        "target '{target}' aims at host '{host}', missing from infra.hosts in meta.yml",
    "content_role_host_unknown":
        "role '{role}' aims at '{host}', missing from infra.hosts in meta.yml",
    "content_doc_url_no_scheme": "no URL scheme",
    "content_doc_url_scheme": "unexpected scheme: {scheme}",
    "content_doc_url_unreachable": "unreachable: {error}",
    "content_doc_url_status": "HTTP {code}",

    # ── contract fields the engine cannot read (models/) ─────────────────────
    # Levées par la lecture d'un meta.yml, qui s'affiche. La CLI encadre ces
    # phrases du chemin du fichier ; elles n'ont donc pas à le porter.
    "contract_field_not_int":
        "'{field}' must be an integer (got: {got}).",
    "contract_field_not_list":
        "'{field}' must be a list (got: {got}).",
    "contract_field_not_mapping":
        "'{field}' must be a mapping (got: {got}).",
    "contract_field_not_mapping_list":
        "'{field}' must be a list of mappings (got: {got}).",
    "contract_root_not_mapping":
        "the document must be a YAML mapping (got: {got}).",
    "contract_repo_required":
        "'repo.id' and 'repo.category' are required (dsoxlab contract).",
    "contract_provider_empty_list":
        "'infra.provider' is an empty list. Declare at least one provider "
        "(e.g. 'kvm').",
    "contract_provider_bad_type":
        "'infra.provider' must be a string or a list of strings, not {got}.",
    "contract_provider_not_declared":
        "DSOXLAB_PROVIDER='{provider}' is not among the providers this meta.yml "
        "declares: {candidates}",

    # ── contract version (schema_version) ─────────────────────────────────────
    "contract_issues_header": "\n[bold red]Contract version:[/bold red]",
    "schema_version_invalid":
        "'schema_version' must be a YAML integer of at least 1, and no greater "
        "than {supported}, the latest contract this dsoxlab reads (got: {got}). "
        "Leave the field out and the file is read as version 1.",
    "schema_version_too_new":
        "declares schema_version {found}, beyond version {supported}, which is "
        "the latest contract this dsoxlab reads. Upgrade the tool: "
        "uv tool upgrade dsoxlab",
    "schema_version_meta_too_new":
        "This catalog requires a newer dsoxlab. {path} declares contract "
        "schema_version {found}, and this dsoxlab only reads the contract up to "
        "version {supported}. Upgrade the tool: uv tool upgrade dsoxlab",
    "schema_version_lab_skipped":
        "Lab left out: {path} declares contract schema_version {found}, beyond "
        "version {supported}, which is the latest this dsoxlab reads. The rest "
        "of the catalog is listed as usual. Upgrade the tool to get this lab: "
        "uv tool upgrade dsoxlab",

    # ── doctor — component labels ─────────────────────────────────────────────
    "check_python":   "Python",
    "check_pytest":   "pytest",
    "check_shell":    "ShellRuntime",
    "check_incus":    "incus",
    "check_kvm":      "virsh/KVM",
    "check_provider": "Infra provider",
    "check_terraform":    "Terraform",
    "check_ansible":      "ansible-playbook",
    "check_libvirt_pool": "libvirt pool",
    "check_iso_tool":     "genisoimage",
    "check_labs":     "Labs detected",
    "check_lab_home": "LAB_HOME",

    "detail_shell_always":   "always available",
    "detail_incus_missing":  "not found",
    "detail_incus_ok":       "client {version}, daemon ok",
    "detail_incus_daemon_down": "client {version}, daemon inactive",
    "detail_incus_no_group": "client {version}, user not in the incus group (re-login required)",
    "detail_incus_no_init":  "client {version}, daemon ok but not initialised",
    "detail_kvm_daemon_err": "virsh present but error (daemon stopped?)",
    "detail_kvm_missing":    "not found",
    "detail_pytest_missing": "not found",
    "detail_pytest_bundled": "bundled with dsoxlab (used by 'check')",
    "detail_pytest_via":     "via {cmd}",
    "detail_provider_unresolved": "declared candidates: {candidates} — none selected",
    "detail_terraform_missing":
        "not found: `provision` cannot create the machines",
    "detail_terraform_broken":
        "present but `terraform version` fails: `provision` cannot use it",
    "detail_ansible_missing":
        "not found: `run` cannot play a vm lab's setup.yaml "
        "(ansible-runner does not install it)",
    "detail_ansible_ok":     "present",
    "detail_pool_missing":
        "the `{pool}` pool does not exist: `provision` will fail with "
        "\"Pool Not Found\"",
    "detail_pool_inactive":
        "the `{pool}` pool is defined but never started: `provision` will fail "
        "with \"storage pool is not active\"",
    "detail_pool_unknown":   "cannot be checked without virsh",
    "explain_apparmor_denied":
        "Known cause: AppArmor denies the VM disks. virt-aa-helper cannot "
        "resolve a disk declared by pool reference, so none of them enters the "
        "domain profile. Grant the permission, including the `k` right "
        "(without it: \"Failed to lock byte 100\"):",
    "explain_pool_not_found":
        "Known cause: the libvirt storage pool does not exist. A fresh install "
        "declares none. Create it:",
    "explain_pool_inactive":
        "Known cause: the libvirt storage pool exists but was never started. "
        "Defining a pool is not enough, nothing can be written to it until it "
        "runs. Start it:",
    "explain_domain_exists":
        "Known cause: an earlier provisioning failed AFTER defining this "
        "machine, so it never entered the Terraform state and `destroy` cannot "
        "see it. Remove it by hand:",
    "detail_iso_tool_missing":
        "not found: incus builds the agent:config CD-ROM on the host, "
        "without it no VM starts",
    "detail_unknown_error":  "unknown error",
    "detail_labs_count":     "{count} lab(s) in {root}",

    # ── doctor — why a component is informational here ───────────────────────
    "doctor_note_no_vm":
        "No lab in this repo uses a VM: the hypervisors above are informational.",
    "doctor_note_other_providers":
        "Active provider: {provider}. The other hypervisors are informational.",
    "doctor_note_remote_provider":
        "Provider {provider} runs in the cloud: no local hypervisor needed.",
    "doctor_note_provider_unresolved":
        "This repo has labs that require a VM, and no provider is selected. "
        "Pick one with [bold]dsoxlab use --provider <name>[/bold]: until then, "
        "none of those labs can run.",

    # ── doctor — fix ──────────────────────────────────────────────────────────
    "fix_nothing": "No remediation needed.",
    "doctor_json_sans_fix":
        "--json and --fix cannot be combined: the remediation commands write to "
        "standard output, which would leave the document unreadable. Run "
        "`dsoxlab doctor --json` to read the diagnosis, then `dsoxlab doctor "
        "--fix` to act on it.",
    "fix_count":   "{count} component(s) to fix…",
    "fix_needs_tty":
        "At least one remediation requires sudo, but this shell is not "
        "interactive (no TTY). Run dsoxlab from a terminal, or apply the "
        "commands by hand.",
    "fix_no_sudo": "sudo not found in PATH: remediation is impossible.",
    "fix_sudo_preauth":
        "[bold]{count}[/bold] command(s) require sudo. Pre-authentication "
        "below (a single prompt for the whole run):",
    "fix_sudo_failed": "sudo pre-authentication failed: remediations aborted.",
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
    "doctor_table_title":    "Required for this repo",
    "doctor_optional_title": "Informational — not required here",
    "doctor_choose_title": "Hypervisors: one is required, none selected",
    "doctor_choose_hint":
        "This repo has labs that require a VM. Pick a provider with "
        "[bold]dsoxlab use --provider <name>[/bold], then run doctor again: it "
        "will only diagnose that one. [bold]--fix[/bold] installs nothing until "
        "the choice is made, since one is needed and not both.",
    "doctor_optional_hint":
        "These components block nothing in this repo: [bold]--fix[/bold] "
        "leaves them alone. Install them only if you want that provider.",
    "col_component":      "Component",
    "col_status":         "Status",
    "col_detail":         "Detail",
    "col_remediation":    "Remediation",
    "status_ok":          "[green]✔ OK[/green]",
    "status_ko":          "[red]✘ KO[/red]",
    "status_present":     "[green]installed[/green]",
    "status_absent":      "[dim]— absent[/dim]",
    "status_choose":      "[yellow]to be chosen[/yellow]",
    "doctor_fix_hint":    "ℹ Use [bold]dsoxlab doctor --fix[/bold] to attempt automatic remediation.",
    "doctor_manual_hint":
        "ℹ [bold]--fix[/bold] cannot repair what is missing: apply the "
        "remediation shown above by hand.",

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

    # ── infra — libvirt ───────────────────────────────────────────────────────
    "libvirt_domain_not_found":
        "No libvirt domain matches host '{host}'. Names tried: {tried}. "
        "Existing domains: {domains}.",
    "libvirt_no_domain": "none",

    # ── Errors raised outside cli.py ──────────────────────────────────────────
    # The CLI renders these through `error(str(exc))`, so an exception message
    # IS interface text — as much as a `help=`. They used to live hardcoded in
    # French inside infra/, runtimes/, services/ and templates/, and came out
    # untranslated under DSOXLAB_LANG=en. That is exactly the path a learner
    # walks when something breaks.
    "err_terraform_missing":
        "terraform is not on your PATH: it provisions the machines of vm labs.\n"
        "Install it: https://developer.hashicorp.com/terraform/install",
    "err_terraform_host_unsupported":
        "--host is not implemented for provider '{provider}'.",
    "err_ansible_runner_missing":
        "ansible-runner is not installed. Run: "
        "uv tool install --force --with ansible-runner dsoxlab "
        "or: pipx inject dsoxlab ansible-runner",
    "err_ansible_playbook_missing":
        "ansible-playbook is not on your PATH: a vm lab cannot play its "
        "setup.yaml without it. ansible-runner drives ansible-core but does "
        "not install it. Run: uv tool install ansible-core",
    "err_ansible_playbook_file_missing": "Playbook not found: {path}",
    "err_credentials_loader_unsupported":
        "No credentials loader for provider '{provider}'. "
        "See src/dsoxlab/infra/credentials.py.",
    "err_credentials_outscale_file":
        "File {path} is missing. Configure your Outscale credentials with "
        "'oapi-cli configure' (or write the JSON by hand).",
    "err_credentials_outscale_json": "{path}: invalid JSON ({error}).",
    "err_credentials_profile_unknown":
        "Profile '{profile}' not found in {path}. Available profiles: "
        "{profiles}. Set it through meta.yml: {option}, or {env}=<name>.",
    "err_credentials_profile_unknown_plain":
        "Profile '{profile}' not found in {path}. Profiles: {profiles}.",
    "err_credentials_fields_required":
        "Profile '{profile}' in {path}: {fields} are required.",
    "err_credentials_aws_file":
        "File {path} is missing. Configure it with 'aws configure'.",
    "err_credentials_gcp_file":
        "File {path} is missing. Configure it with "
        "'gcloud auth application-default login'.",
    "err_credentials_azure_file":
        "File {path} is missing. Configure it with 'az login'.",
    "err_credentials_proxmox_file":
        "File {path} is missing. Create it by hand with a Proxmox API token "
        "(api_url, token_id, token_secret).",
    "err_inventory_not_provisioned":
        "No host has an address: the lab infrastructure is not provisioned.",
    "err_inventory_target_unknown":
        "target_fqdn '{fqdn}' is not in the list of known hosts: {known}",
    "err_inventory_role_unknown":
        "role '{role}' → '{fqdn}' is not in the list of known hosts: {known} "
        "(host not declared in meta.yml, or not provisioned).",
    "err_host_ready_timeout":
        "{fqdn} is unreachable over SSH after {timeout}s "
        "(cloud-init too slow, or the VM failed to boot).",
    "err_snapshot_provider_unsupported":
        "Snapshots are not implemented yet for provider '{provider}'. "
        "See src/dsoxlab/infra/snapshot/__init__.py to add a backend.",
    "err_snapshot_no_disk":
        "Snapshot '{snapshot}' of domain {domain} froze no disk: there is "
        "nothing to roll back to. Take it again with dsoxlab run.",
    "err_snapshot_no_base":
        "Snapshot '{snapshot}' of domain {domain}: cannot tell which disk "
        "'{disk}' overlays. Rolling back would throw away the wrong file.",
    "err_snapshot_no_capacity":
        "libvirt does not report the size of {path}: an overlay cannot be "
        "recreated without it.",
    "err_snapshot_not_top_layer":
        "Snapshot '{snapshot}' is no longer the top layer of {domain} disk "
        "'{disk}': it writes to {found}, the snapshot created {expected}. "
        "Rolling back here would drop changes the snapshot never covered.",
    "err_vm_snapshot_required":
        "Lab {lab_id} declares snapshot_required: true and the checkpoint "
        "could not be taken on {host}: {error}\n"
        "The lab is NOT started, because it would run without the safety net "
        "it asks for. Either fix the hypervisor, or declare "
        "snapshot_required: false in its lab.yaml.",
    "err_runtime_unavailable":
        "Runtime '{runtime}' is not available on this machine. Install the "
        "dependencies (`dsoxlab instructor bootstrap`), or pick a lab that "
        "runs on another runtime.",
    "err_runtime_type_unknown": "Unknown RuntimeType: {rt_type}",
    "err_service_network_failed":
        "Cannot create network '{name}':\n{detail}",
    "err_service_port_closed":
        "Service '{name}' did not open port {port} within {timeout}s.",
    "err_service_probe_failed":
        "Service '{name}' never answered « {probe} » within {timeout}s.",
    "err_service_start_failed":
        "Service '{name}' failed to start:\n{detail}",
    "err_service_post_start_failed":
        "Initialising service '{name}' failed on « {command} »:\n{detail}",
    "err_service_container_stopped":
        "Service '{name}' is no longer running, so its initialisation cannot "
        "be played.\nContainer {container}, exited with code {code}.\n"
        "Last lines:\n{logs}",
    "err_vm_setup_missing":
        "Lab {lab_id} must ship setup.yaml at its root (dsoxlab contract for "
        "runtime: vm). Expected file: {path}",
    "err_vm_setup_failed":
        "setup.yaml failed for {lab_id} on target '{target}' "
        "(rc={rc}, status={status}). Stats: {stats}",
    "err_vm_cleanup_missing":
        "Lab {lab_id} must ship cleanup.yaml at its root (dsoxlab contract "
        "for runtime: vm). Expected file: {path}",
    "err_vm_cleanup_failed":
        "cleanup.yaml failed for {lab_id} on target '{target}' "
        "(rc={rc}, status={status}).",
    "err_vm_no_target":
        "Lab {lab_id} (runtime: vm) must declare at least one target under "
        "runtime.targets[] in lab.yaml.",
    "err_vm_target_unknown":
        "Target '{name}' is unknown for lab {lab_id}. "
        "Available targets: {available}",
    "err_vm_no_meta":
        "No meta.yml found walking up from {path}. "
        "dsoxlab cannot derive the inventory.",
    "err_vm_meta_invalid": "Invalid meta.yml: {path}",
    "err_lab_not_found": "Lab not found: {lab_id}",
    "err_template_terraform_missing":
        "No Terraform template for provider '{provider}'. "
        "Providers packaged in dsoxlab: {available}",
    "err_template_cloud_init_missing":
        "No cloud-init template for distribution '{distro}'. "
        "Packaged distros: {available}",

    # ── verrou d'écriture par dépôt (issue #81) ─────────────────────────────
    "lock_busy":
        "Another dsoxlab command is already working on this repository: "
        "« {command} » (PID {pid}, running for {age}). Nothing was changed.",
    "lock_busy_anonymous":
        "Another dsoxlab command is already working on this repository "
        "(lock: {path}). Nothing was changed.",
    "lock_busy_hint":
        "Wait for it to finish, or stop it. A lock left behind by a process "
        "that died is released on its own: there is no file to delete by hand.",

    # ── interruption d'une opération longue (issue #82) ─────────────────────
    "interrupt_notice_first":
        "Interruption requested. Letting the current step finish so nothing "
        "is left half-written. Press Ctrl-C again to stop right now.",
    "interrupt_notice_second":
        "Second interruption: stopping now.",
    "interrupt_resume":
        "Replay to pick up where it stopped: {cmd}",
    "interrupted_hard":
        "You interrupted twice, so the operation was killed rather than "
        "closed: what it left behind may be incomplete.",
    "interrupted_terraform_init":
        "Interrupted while downloading the Terraform provider. "
        "No resource was created.",
    "interrupted_terraform_apply":
        "Interrupted: Terraform stopped and saved its state. What it had "
        "already created is still there, and is known to the state.",
    "interrupted_terraform_destroy":
        "Interrupted: Terraform stopped and saved its state. Part of the "
        "infrastructure is still up.",
    "interrupted_ansible":
        "Interrupted: the playbook stopped mid-run. The machine may be "
        "partially configured; lab playbooks are idempotent.",
    "interrupted_services":
        "Interrupted while starting the lab services. A container may be up "
        "without having been initialised.",
    "interrupted_hosts_wait":
        "Interrupted while waiting for the machines to answer over SSH. "
        "The infrastructure itself is up.",
    "interrupted_tests":
        "Interrupted: the tests were stopped. Nothing was recorded, so this "
        "run costs you no score.",
    "interrupted_session":
        "Interrupted: the lab session was closed. Your work is untouched.",
    "interrupted_unknown":
        "Interrupted by Ctrl-C.",
    # ── exam_passing_score — the verdict of a mock exam ───────────────────────
    "field_exam_score": "[bold]Pass mark:[/bold]",
    "col_verdict":   "Verdict",
    "verdict_pass":  "passed",
    "verdict_fail":  "failed",
    "exam_passed":
        "Exam passed: {pct}% of the scale, for a pass mark of {threshold}%.",
    "exam_failed":
        "Exam failed: {pct}% of the scale, below the {threshold}% pass mark. "
        "Replay the lab: dsoxlab reset, then dsoxlab run.",

    # ── unknown keys in a contract file ───────────────────────────────────────
    "unknown_keys_header": "\n[bold red]Keys nothing reads:[/bold red]",
    "unknown_key":
        "'{field}' is not part of the contract. dsoxlab ignores it, so whatever "
        "you meant by it never happens. Remove it, or check docs/contract-v1.md.",
    "unknown_key_suggest":
        "'{field}' is not part of the contract, and dsoxlab ignores it. "
        "The closest key it does read at that level is '{suggestion}'.",

    # ── #138 : un exécutable absent se nomme, il ne se plante pas ──
    "err_executable_introuvable":
        '"{nom}" is not installed, or not on your PATH. dsoxlab needs it for this command; install it, then try again.',
    "err_fichier_introuvable":
        'File not found: "{nom}".',

    # ── #132 : un « 0 lab » muet oblige à chercher ailleurs ──
    "detail_labs_ecart":
        "{ecart} of the {presents} lab.yaml files on disk could not be loaded. `dsoxlab list-labs` names them and says why.",

    # ── #90 / #134 : la complétion sous un nom qui la nomme ──
    "cmd_completion_help":
        "Install or print the shell completion script.",

    # ── #90 / #134 : la complétion sous un nom qui la nomme ──
    "cmd_completion_install_help":
        "Install completion for the current shell (zsh, bash).",

    # ── #90 / #134 : la complétion sous un nom qui la nomme ──
    "cmd_completion_show_help":
        "Print the completion script on stdout, writing nothing.",

    # ── #90 / #134 : la complétion sous un nom qui la nomme ──
    "opt_completion_shell":
        "Shell to generate for (zsh, bash, fish). Default: the current shell.",

    # ── #90 / #134 : la complétion sous un nom qui la nomme ──
    "install_deprecie":
        "`dsoxlab install` is deprecated since 0.1.62 and will be removed in "
        "0.3.0. Use `dsoxlab completion install`, which does the same thing "
        "under a name that says it. The wrapper in ~/.local/bin is no longer "
        "written: `uv tool install` and `pipx` already put theirs there.",
}
