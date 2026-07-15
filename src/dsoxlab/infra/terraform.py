"""Routeur Terraform multi-provider.

dsoxlab orchestre Terraform via la CLI ``terraform`` (pas de lib Python
officielle disponible). Le code de provisioning vit **dans le package
dsoxlab** (``dsoxlab/templates/terraform/<provider>/``), pas dans les
dépôts fournisseurs — qui ne contiennent que du déclaratif (meta.yml +
labs).

Cycle d'exécution ``dsoxlab provision`` :

1. Lit ``meta.yml: infra.provider`` du dépôt fournisseur courant.
2. Copie ``templates/terraform/<provider>/*.tf`` vers le **work-dir
   XDG** : ``~/.local/state/dsoxlab/<repo-id>/terraform/<provider>/``.
3. Génère ``<work-dir>/.dsoxlab.auto.tfvars.json`` depuis
   ``meta.yml: infra.hosts[]`` + ``providers.<provider>``.
4. Lance ``terraform -chdir=<work-dir> {init,apply,destroy,output}``.

Le state ``terraform.tfstate``, le dossier ``.terraform/`` et le tfvars
généré vivent dans le work-dir XDG — jamais dans le dépôt training.
Plusieurs apprenants peuvent travailler sur le même repo training en
parallèle, chacun avec son state local isolé.

Contrat invariant des providers (templates/terraform/README.md) :

- Outputs ``hosts`` (map FQDN → IP) et ``bastion`` (objet ou null).
- VMs cloud en réseau privé + bastion public obligatoire (cf.
  REFACTORING-PLAN §11.8).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models.repo import RepoMetadata
from ..templates import terraform_template
from ..utils.shell import CommandError, run_command
from . import credentials as creds_mod

logger = logging.getLogger(__name__)


class TerraformNotInstalled(RuntimeError):
    """Levée si la CLI ``terraform`` n'est pas dans le PATH."""


class ProviderNotImplemented(RuntimeError):
    """Levée si le provider sélectionné n'a pas de template packagé
    dans ``dsoxlab/templates/terraform/<provider>/``.
    """


@dataclass
class ProvisionResult:
    """Résultat d'un ``terraform apply``."""

    outputs: dict[str, dict[str, Any]]
    """Outputs JSON natifs (sortie de ``terraform output -json``).

    Format Terraform : ``{"<output_name>": {"sensitive": bool,
    "type": ..., "value": ...}}``.
    """

    hosts: dict[str, str]
    """Map FQDN → IP extraite de l'output ``hosts``."""


def is_available() -> bool:
    """Retourne True si la CLI ``terraform`` est dans le PATH."""
    try:
        run_command(["terraform", "version"], check=False)
        return True
    except (CommandError, FileNotFoundError):
        return False


def _xdg_state_home() -> Path:
    env = os.environ.get("XDG_STATE_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".local" / "state"


def workdir(repo_meta: RepoMetadata) -> Path:
    """Retourne le work-dir XDG du provider courant pour ce dépôt.

    Arborescence du work-dir :

        ~/.local/state/dsoxlab/<repo-id>/
        ├── cloud-init/                    ← templates partagés
        │   ├── almalinux.yaml.tmpl
        │   └── ubuntu.yaml.tmpl
        └── terraform/<provider>/
            ├── main.tf, variables.tf, …    ← copiés depuis le package
            ├── .dsoxlab.auto.tfvars.json   ← généré par write_tfvars()
            └── terraform.tfstate            ← state local

    Le path relatif ``${path.module}/../../cloud-init/<distro>.yaml.tmpl``
    dans les templates Terraform pointe ainsi vers les bons fichiers
    cloud-init.

    Raises:
        ProviderNotImplemented: si aucun template n'est packagé pour
            ce provider dans dsoxlab/templates/terraform/<provider>/.
    """
    provider = repo_meta.infra.require_provider()
    try:
        template_dir = terraform_template(provider)
    except FileNotFoundError as exc:
        raise ProviderNotImplemented(str(exc)) from exc

    repo_root = _xdg_state_home() / "dsoxlab" / repo_meta.id
    work = repo_root / "terraform" / provider
    work.mkdir(parents=True, exist_ok=True)

    # Synchronise les fichiers .tf et tout asset auxiliaire (sauf state).
    for src in template_dir.iterdir():
        if src.is_file():
            dst = work / src.name
            if not dst.exists() or src.read_bytes() != dst.read_bytes():
                shutil.copy2(src, dst)

    # Synchronise aussi les templates cloud-init partagés vers
    # <repo-root>/cloud-init/ (path relatif ../../cloud-init/ depuis
    # le terraform module).
    from ..templates import template_root

    cloud_init_src = template_root() / "cloud-init"
    cloud_init_dst = repo_root / "cloud-init"
    cloud_init_dst.mkdir(parents=True, exist_ok=True)
    for src in cloud_init_src.iterdir():
        if src.is_file():
            dst = cloud_init_dst / src.name
            if not dst.exists() or src.read_bytes() != dst.read_bytes():
                shutil.copy2(src, dst)

    return work


# Alias rétro-compat — déprécié, à supprimer
def provider_dir(repo_meta: RepoMetadata) -> Path:
    """DEPRECATED : utilise ``workdir(repo_meta)`` à la place."""
    return workdir(repo_meta)


def write_tfvars(repo_meta: RepoMetadata) -> Path:
    """Génère ``<work-dir>/.dsoxlab.auto.tfvars.json``.

    Variables exposées à Terraform :

    - ``network_name``   : nom du réseau (libvirt, VPC, Net Outscale...)
    - ``network_cidr``   : CIDR
    - ``hosts``          : liste des VMs (name, distro, role, ram_mb,
      vcpu, disk_gb)
    - ``provider_config``: dict d'overrides du provider, enrichi
      automatiquement avec :
      - ``ssh_pubkey`` (lue depuis ``<repo>/ssh/id_ed25519.pub``)
      - ``region`` (lue depuis le profil cloud du provider —
        ``~/.osc/config.json`` pour outscale, ``~/.aws/config`` pour
        aws, etc.) si non déjà déclarée dans meta.yml
    """
    work = workdir(repo_meta)
    tfvars_path = work / ".dsoxlab.auto.tfvars.json"

    # Charge la clé SSH publique du repo training pour la propager aux
    # templates cloud-init via provider_config.ssh_pubkey.
    pub_key = repo_meta.path / "ssh" / "id_ed25519.pub"
    provider_cfg = dict(repo_meta.infra.provider_config())
    if pub_key.is_file():
        provider_cfg.setdefault(
            "ssh_pubkey", pub_key.read_text(encoding="utf-8").strip()
        )

    # Enrichit provider_config avec la région du profil cloud (cas
    # outscale/aws/gcp/azure). Pour kvm/vagrant, region reste vide.
    profile_name = provider_cfg.get("profile") or None
    try:
        env_creds = creds_mod.load(repo_meta.infra.provider, profile_name)
    except (creds_mod.CredentialsNotFound, NotImplementedError):
        env_creds = {}
    region_from_profile = (
        env_creds.get("OSC_REGION")
        or env_creds.get("AWS_REGION")
        or env_creds.get("AWS_DEFAULT_REGION")
        or ""
    )
    if region_from_profile:
        provider_cfg.setdefault("region", region_from_profile)

    # Le CIDR du Net peut etre surcharge par provider — utile quand un
    # provider exige une plage plus large (Outscale: /22 pour 2 subnets
    # /24 dans son Net) que celle utilisee par defaut en KVM (/24).
    network_cidr = (
        provider_cfg.get("cidr") or repo_meta.infra.cidr
    )

    payload = {
        "network_name": repo_meta.infra.network,
        "network_cidr": network_cidr,
        "hosts": [
            {
                "name": h.name,
                "distro": h.distro,
                "role": h.role,
                "ram_mb": h.ram_mb,
                "vcpu": h.vcpu,
                "disk_gb": h.disk_gb,
                "extra_disk_gb": h.extra_disk_gb,
            }
            for h in repo_meta.infra.hosts
        ],
        "provider_config": provider_cfg,
    }
    tfvars_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return tfvars_path


def _provider_env(repo_meta: RepoMetadata) -> dict[str, str]:
    """Construit l'environnement à passer aux invocations terraform.

    Charge les credentials du provider courant via
    ``infra/credentials.py`` et les superpose à ``os.environ`` (sans
    écraser les variables explicitement posées par l'utilisateur).
    """
    profile_name = repo_meta.infra.provider_config().get("profile") or None
    try:
        creds = creds_mod.load(repo_meta.infra.provider, profile_name)
    except (creds_mod.CredentialsNotFound, NotImplementedError) as exc:
        # Pour kvm/vagrant : pas de creds, c'est normal.
        # Pour outscale/aws : remonter l'erreur si on tente provision.
        if isinstance(exc, NotImplementedError):
            return dict(os.environ)
        # CredentialsNotFound : message explicite mais on laisse remonter
        raise

    env = dict(os.environ)
    for key, value in creds.items():
        # On n'écrase pas si l'utilisateur a explicitement exporté.
        env.setdefault(key, value)
    return env


def init(
    repo_meta: RepoMetadata,
    *,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Lance ``terraform init`` dans le dossier provider courant.

    Idempotent (Terraform skippe l'init si .terraform/ est à jour).
    Si ``on_event`` est fourni, utilise ``-json`` pour streamer les
    événements (téléchargement provider, etc.).
    """
    tf_dir = workdir(repo_meta)
    if not is_available():
        raise TerraformNotInstalled(
            "terraform absent du PATH. Lance : dsoxlab instructor bootstrap"
        )

    cmd = ["terraform", f"-chdir={tf_dir}", "init", "-input=false"]
    if on_event is not None:
        cmd.append("-json")
        _stream_terraform(cmd, env=_provider_env(repo_meta), on_event=on_event)
    else:
        run_command(cmd, timeout=600, env=_provider_env(repo_meta))


def apply(
    repo_meta: RepoMetadata,
    *,
    auto_approve: bool = True,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    targets: list[str] | None = None,
    target_hosts: list[str] | None = None,
) -> ProvisionResult:
    """Lance ``terraform apply`` et retourne les outputs.

    Args:
        repo_meta: contrat dsoxlab du dépôt fournisseur.
        auto_approve: ``-auto-approve`` (par défaut, on est en lab).
        on_event: callback optionnel appelé pour chaque événement JSON
            émis par ``terraform apply -json`` (mode machine-readable
            depuis Terraform 0.15+). Permet à la CLI d'alimenter une
            progress bar. Si None, mode silencieux/standard.
        targets: liste de ressources Terraform à cibler via ``-target=…``.
            Terraform résout automatiquement les dépendances en amont
            (réseau partagé, image de base) — pas besoin de les lister.
            Si None, applique tout le plan.

    Returns:
        ``ProvisionResult`` avec outputs JSON et map FQDN→IP.
    """
    if not is_available():
        raise TerraformNotInstalled(
            "terraform absent du PATH. Lance : dsoxlab instructor bootstrap"
        )

    tf_dir = workdir(repo_meta)
    write_tfvars(repo_meta)

    # Note : ``init`` n'est PAS appelé automatiquement ici. La CLI
    # ``dsoxlab provision`` l'appelle séparément (avec spinner) pour
    # que le téléchargement du provider soit visible. Si tu utilises
    # ``apply()`` programmatiquement, pense à appeler ``init()`` avant.

    cmd = ["terraform", f"-chdir={tf_dir}", "apply", "-input=false"]
    if auto_approve:
        cmd.append("-auto-approve")
    for t in targets or []:
        cmd.append(f"-target={t}")
    # Scope les ressources dédiées (disques additionnels) aux hôtes ciblés,
    # complément indispensable de -target : sans lui, le for_each extra
    # créerait le disque d'autres hôtes (issue #1). Templates ignorant la
    # variable la déclarent quand même (default []), donc -var est sûr.
    if target_hosts:
        cmd += ["-var", f"target_hosts={json.dumps(target_hosts)}"]
    if on_event is not None:
        cmd.append("-json")
        _stream_terraform(cmd, env=_provider_env(repo_meta), on_event=on_event)
    else:
        run_command(cmd, timeout=1800, env=_provider_env(repo_meta))

    return _read_outputs(tf_dir, env=_provider_env(repo_meta))


def _stream_terraform(
    cmd: list[str],
    *,
    env: dict[str, str],
    on_event: Callable[[dict[str, Any]], None],
) -> None:
    """Lance terraform en mode -json et streame chaque event vers on_event.

    Stratégie anti-deadlock : stderr est mergé sur stdout
    (``stderr=subprocess.STDOUT``). Cela évite que le buffer pipe
    stderr se sature pendant qu'on lit stdout — un blocage classique
    de ``subprocess.Popen`` qui empêche le process de se terminer.

    Les lignes non-JSON (warnings hors mode -json, messages legacy
    Terraform) sont ignorées par le parseur JSON mais conservées dans
    ``raw_log`` pour reporting d'erreur lisible.

    Lève RuntimeError si rc != 0 (avec diagnostic + stderr brut).
    """
    proc = subprocess.Popen(  # noqa: S603 — commande maîtrisée
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # merge pour éviter le deadlock pipe
        text=True,
        bufsize=1,                  # line-buffered
        env=env,
    )
    assert proc.stdout is not None  # nosec : Popen avec PIPE garantit non-None

    last_diagnostic = ""
    raw_log_tail: list[str] = []
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            # Conserve les 50 dernières lignes brutes pour reporting
            raw_log_tail.append(line)
            if len(raw_log_tail) > 50:
                raw_log_tail.pop(0)

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # Ligne non-JSON (warnings hors mode -json) — on l'ignore
                # pour les events mais on l'a gardée dans raw_log_tail.
                continue

            # Capture le dernier diagnostic en erreur
            if event.get("@level") == "error" and event.get("type") == "diagnostic":
                diag = event.get("diagnostic", {})
                last_diagnostic = (
                    f"{diag.get('summary', '')}\n{diag.get('detail', '')}".strip()
                )
            try:
                on_event(event)
            except Exception:  # noqa: BLE001 — callback ne doit pas tuer Terraform
                logger.exception("on_event callback failed")
    finally:
        # Laisse Terraform se terminer proprement même si la boucle a été
        # interrompue (KeyboardInterrupt, etc.).
        rc = proc.wait()

    if rc != 0:
        msg = last_diagnostic
        if not msg:
            tail = "\n".join(raw_log_tail[-20:])
            msg = tail or f"terraform exit code {rc}"
        raise RuntimeError(msg)


def destroy(
    repo_meta: RepoMetadata,
    *,
    auto_approve: bool = True,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    targets: list[str] | None = None,
    target_hosts: list[str] | None = None,
) -> None:
    """Lance ``terraform destroy``.

    Si ``on_event`` est fourni, utilise le mode ``-json`` pour streamer
    les événements (cf. apply()). Si ``targets`` est fourni, ne détruit
    que ces ressources (et leurs dépendantes en aval) — utile pour
    rejouer une seule VM sans toucher au réseau ni aux images de base.
    """
    if not is_available():
        raise TerraformNotInstalled(
            "terraform absent du PATH. Lance : dsoxlab instructor bootstrap"
        )

    tf_dir = workdir(repo_meta)
    # Re-génère le tfvars : Terraform exige les variables même pour
    # destroy (l'état ne contient pas la définition des inputs). Sans
    # ça : "Error: No value for required variable: hosts".
    write_tfvars(repo_meta)

    cmd = ["terraform", f"-chdir={tf_dir}", "destroy", "-input=false"]
    if auto_approve:
        cmd.append("-auto-approve")
    for t in targets or []:
        cmd.append(f"-target={t}")
    # Même scoping qu'à l'apply : sur un destroy --host, ne détruire que le
    # disque additionnel de l'hôte ciblé (le for_each extra est filtré par
    # target_hosts). Vide = tous les hôtes.
    if target_hosts:
        cmd += ["-var", f"target_hosts={json.dumps(target_hosts)}"]
    if on_event is not None:
        cmd.append("-json")
        _stream_terraform(cmd, env=_provider_env(repo_meta), on_event=on_event)
    else:
        run_command(cmd, timeout=1800, env=_provider_env(repo_meta))

    # Nettoyage du tfvars généré : seulement si on a tout détruit
    # (sinon on garde le tfvars pour les prochains apply ciblés).
    if targets is None:
        tfvars = tf_dir / ".dsoxlab.auto.tfvars.json"
        if tfvars.is_file():
            tfvars.unlink()


def host_targets(provider: str, fqdn: str) -> list[str]:
    """Retourne la liste de ressources Terraform à cibler pour un host.

    Permet à ``dsoxlab provision --host <fqdn>`` ou ``destroy --host <fqdn>``
    de ne toucher qu'à une VM (et ses ressources dédiées : disque OS,
    seed cloud-init, ISO cloudinit). Les ressources partagées (réseau,
    images de base, bastion) sont automatiquement gérées par Terraform
    via la résolution de dépendances et restent intactes.

    Args:
        provider: nom du provider (kvm, outscale, ...).
        fqdn: nom du host tel que déclaré dans meta.yml.

    Raises:
        NotImplementedError: si le provider n'expose pas de mapping.
    """
    if provider == "kvm":
        return [
            f'libvirt_domain.host["{fqdn}"]',
            f'libvirt_volume.host["{fqdn}"]',
            f'libvirt_volume.cloudinit["{fqdn}"]',
            f'libvirt_cloudinit_disk.host["{fqdn}"]',
        ]
    if provider == "outscale":
        return [
            f'outscale_vm.host["{fqdn}"]',
        ]
    if provider == "incus":
        # Instance + son volume extra dédié. À l'apply, -target de
        # l'instance suffit à créer le volume (dépendance amont) ; mais au
        # destroy, le volume amont N'EST PAS détruit par -target de la seule
        # instance → on le cible explicitement pour que `destroy --host X`
        # le nettoie. Le for_each extra étant filtré par target_hosts
        # (issue #1), cibler extra["<host sans disque>"] est un no-op bénin.
        return [
            f'incus_instance.host["{fqdn}"]',
            f'incus_storage_volume.extra["{fqdn}"]',
        ]
    raise NotImplementedError(
        f"--host non implémenté pour le provider '{provider}'"
    )


def get_outputs(repo_meta: RepoMetadata) -> ProvisionResult | None:
    """Retourne les outputs Terraform actuels (sans relancer apply).

    Retourne None si l'état n'existe pas encore.
    """
    try:
        tf_dir = workdir(repo_meta)
    except ProviderNotImplemented:
        return None

    state = tf_dir / "terraform.tfstate"
    if not state.is_file():
        return None

    try:
        env = _provider_env(repo_meta)
    except creds_mod.CredentialsNotFound:
        env = None  # best-effort lecture sans credentials
    return _read_outputs(tf_dir, env=env)


def _read_outputs(tf_dir: Path, *, env: dict[str, str] | None = None) -> ProvisionResult:
    """Lit ``terraform output -json`` et extrait la map hosts."""
    result = run_command(
        ["terraform", "-chdir=" + str(tf_dir), "output", "-json"],
        check=False,
        env=env,
    )

    outputs: dict[str, dict[str, Any]] = {}
    if result.ok and result.stdout.strip():
        try:
            outputs = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning("Sortie 'terraform output -json' non parsable.")

    hosts_output = outputs.get("hosts", {}).get("value", {})
    hosts: dict[str, str] = {
        str(name): str(ip) for name, ip in (hosts_output or {}).items()
    }

    return ProvisionResult(outputs=outputs, hosts=hosts)
