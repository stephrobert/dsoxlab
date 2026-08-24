"""Génération dynamique de l'inventory Ansible.

L'inventory est dérivé de deux sources :

1. ``meta.yml: infra.hosts[]`` du dépôt fournisseur (FQDN, distro, role).
2. Les **outputs Terraform** du provider courant — typiquement une map
   ``hosts: { fqdn: ip, ... }`` produite par ``infra/terraform/<provider>/
   outputs.tf``.

En MVP, si Terraform n'a pas encore été appliqué, on tombe en mode
**fallback meta.yml** qui utilise le champ legacy ``ip:`` des hosts
(toujours utilisable pour le provider kvm avec DHCP statique).

L'inventory généré reste un **dict Python** consommé directement par
``ansible-runner`` — pas de fichier .ini écrit sur disque, sauf demande
explicite via ``write_inventory_file()`` (utile pour debug ou pour
``dsoxlab ssh``).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..i18n import _
from ..models.repo import RepoMetadata
from ..utils.fichiers import ecrire_atomiquement
from ..utils.shell import CommandError
from . import libvirt

logger = logging.getLogger(__name__)


class InfraNotProvisioned(RuntimeError):
    """L'infrastructure du lab n'est pas provisionnée (aucun hôte joignable).

    Levée quand le ``meta.yml`` déclare des hôtes mais qu'aucun n'a d'adresse :
    Terraform n'a pas tourné. C'est une situation NORMALE (premier lancement,
    après un ``destroy``), pas un bug — la CLI la rend en une phrase, jamais en
    traceback.
    """


def build_inventory(
    repo_meta: RepoMetadata,
    *,
    ssh_private_key: Path | None = None,
    ssh_user: str = "ansible",
    terraform_outputs: dict[str, Any] | None = None,
    target_fqdn: str | None = None,
    roles: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Construit un inventory Ansible (format dict) depuis meta + outputs.

    Args:
        repo_meta: ``RepoMetadata`` du dépôt fournisseur.
        ssh_private_key: Chemin vers la clé privée du lab. Si None,
            cherche ``<repo>/ssh/id_ed25519``.
        ssh_user: Utilisateur SSH (par défaut ``ansible``, le compte de service).
        terraform_outputs: Outputs JSON de Terraform. Si fourni, l'IP de
            chaque host est lue depuis ``outputs["hosts"][fqdn]``.
            Sinon, fallback sur ``meta.yml: hosts[].ip``.
        target_fqdn: Si fourni, l'inventory contient en plus un groupe
            ``lab_target`` qui ne contient que ce host. C'est ce groupe
            que les playbooks de lab (``setup.yaml``/``cleanup.yaml``/
            ``solution.yaml``) doivent cibler via ``hosts: lab_target``.

    Returns:
        Dict au format inventory Ansible standard. Le groupe ``labenv``
        contient tous les hosts ; si ``target_fqdn`` est fourni, le
        groupe ``lab_target`` contient ce seul host (réutilise les
        host_vars du groupe labenv).
    """
    if ssh_private_key is None:
        ssh_private_key = repo_meta.path / "ssh" / "id_ed25519"

    tf_hosts: dict[str, str] = {}
    if terraform_outputs:
        # Format attendu : {"hosts": {"value": {"fqdn1": "ip1", ...}}}
        # ou directement {"fqdn1": "ip1"} selon que c'est `terraform output -json`.
        raw = terraform_outputs.get("hosts")
        if isinstance(raw, dict):
            # `raw.get("value", raw)` peut rendre autre chose qu'un mapping :
            # un output d'une autre version de Terraform, un provider qui a
            # renommé sa sortie, un state édité à la main. `.items()` levait
            # alors un AttributeError, c'est-à-dire un traceback au moment de
            # jouer un lab, sans dire que la cause est un state périmé.
            # Trouvé par fuzz/fuzz_terraform_outputs.py sur
            # `{"hosts": {"value": "10.99.0.11"}}`.
            valeurs = raw.get("value", raw)
            if isinstance(valeurs, dict):
                tf_hosts = {k: str(v) for k, v in valeurs.items()}

    # Bastion : extrait via bastion_info() pour bénéficier de la
    # priorité meta.yml > output Terraform sur le user (cf.
    # REFACTORING-PLAN §11.8 + commits du test E2E Outscale).
    bastion = bastion_info(terraform_outputs, repo_meta=repo_meta)

    # -F /dev/null : ignore la config SSH perso de l'apprenant
    # (~/.ssh/config) qui peut contenir un ProxyJump appliqué par
    # pattern d'IP (ex: "Host 10.*" → bastion d'un autre projet).
    # Sans ça, ansible-runner va router le SSH lab via ce bastion
    # tiers qui ne répond pas → "Connection to UNKNOWN port 65535".
    base_ssh_args = "-F /dev/null -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
    if bastion:
        proxy_target = bastion["fqdn"] or bastion["public_ip"]
        # On utilise ProxyCommand (et pas ProxyJump) pour pouvoir
        # injecter explicitement -i <ssh_key> sur le hop bastion. En
        # effet, OpenSSH n'applique pas l'option ``-i`` aux hops
        # ProxyJump : il prend la clé par défaut ``~/.ssh/id_ed25519``
        # qui ne matche pas le keypair du lab → "Permission denied".
        base_ssh_args += (
            f" -o ProxyCommand='ssh -F /dev/null -W %h:%p"
            f" -i {ssh_private_key}"
            f" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
            f" {bastion['user']}@{proxy_target}'"
        )

    inventory_hosts: dict[str, dict[str, Any]] = {}
    for host_def in repo_meta.infra.hosts:
        ip = tf_hosts.get(host_def.name) or host_def.ip
        if not ip:
            logger.warning(
                "Host %s sans IP : ni outputs Terraform ni meta.yml ip:. "
                "Lance d'abord 'dsoxlab provision'.",
                host_def.name,
            )
            continue

        inventory_hosts[host_def.name] = {
            "ansible_host": ip,
            "ansible_user": ssh_user,
            "ansible_ssh_private_key_file": str(ssh_private_key),
            "ansible_ssh_common_args": base_ssh_args,
            # Métadonnées propagées comme host_vars (utile pour les
            # conditions Ansible : when distro == "alma10").
            "distro": host_def.distro,
            "role": host_def.role,
        }

    # Le dépôt déclare des hôtes mais AUCUN n'a d'IP : l'infrastructure n'est
    # pas provisionnée. C'est le cas le plus fréquent chez un débutant, et il
    # ne doit surtout pas se manifester par une traceback : on lève une erreur
    # que la CLI sait rendre en une phrase actionnable.
    if repo_meta.infra.hosts and not inventory_hosts:
        raise InfraNotProvisioned(_("err_inventory_not_provisioned"))

    children: dict[str, Any] = {
        "labenv": {"hosts": inventory_hosts},
    }

    # Groupe synthétique ``lab_target`` ciblé par les playbooks de lab.
    # Contient uniquement le host correspondant à la target choisie.
    # Les host_vars sont hérités via ``children`` du groupe labenv (les
    # hosts ne sont pas redéfinis, on liste juste leur nom dans
    # ``hosts:`` — Ansible résout les vars depuis labenv).
    if target_fqdn:
        if target_fqdn not in inventory_hosts:
            raise ValueError(_(
                "err_inventory_target_unknown",
                fqdn=target_fqdn, known=sorted(inventory_hosts),
            ))
        children["lab_target"] = {
            "hosts": {target_fqdn: {}},
        }

    # Labs multi-hôtes : chaque rôle devient un groupe ``lab_<role>`` (ex.
    # ``lab_server``) que le setup/solution/cleanup peut cibler, en plus de
    # ``lab_target``. Les host_vars restent hérités du groupe ``labenv``.
    for role_name, role_fqdn in (roles or {}).items():
        if role_fqdn not in inventory_hosts:
            raise ValueError(_(
                "err_inventory_role_unknown",
                role=role_name, fqdn=role_fqdn, known=sorted(inventory_hosts),
            ))
        children[f"lab_{role_name}"] = {
            "hosts": {role_fqdn: {}},
        }

    return {"all": {"children": children}}


def bastion_info(
    terraform_outputs: dict[str, Any] | None,
    repo_meta: RepoMetadata | None = None,
) -> dict[str, str] | None:
    """Extrait les infos du bastion depuis les outputs Terraform.

    Retourne ``{user, fqdn, public_ip}`` ou ``None`` si aucun bastion
    n'est configuré (cas KVM/Vagrant — accès direct).

    Le ``user`` est lu en priorité depuis ``meta.yml: providers.<name>
    .bastion_user`` si fourni (via ``repo_meta``). Cela permet de
    changer l'utilisateur SSH du bastion sans avoir à re-applier
    Terraform pour rafraîchir l'output.
    """
    if not terraform_outputs:
        return None
    raw = terraform_outputs.get("bastion")
    if not isinstance(raw, dict):
        return None
    value = raw.get("value", raw)
    if not isinstance(value, dict) or not value.get("public_ip"):
        return None
    # User : priorité meta.yml > output Terraform > défaut "ec2-user"
    user = ""
    if repo_meta is not None:
        user = repo_meta.infra.provider_config().get("bastion_user", "")
    if not user:
        user = str(value.get("user", "ec2-user"))
    return {
        "user": user,
        "fqdn": str(value.get("fqdn", "")),
        "public_ip": str(value["public_ip"]),
    }


def inventory_path(repo_meta: RepoMetadata) -> Path:
    """Retourne le chemin du fichier inventory cache (XDG)."""
    cache_root = _xdg_cache_home() / "dsoxlab" / repo_meta.id
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root / "inventory.json"


def ssh_config_path(repo_meta: RepoMetadata) -> Path:
    """Retourne le chemin du ssh_config OpenSSH généré pour ce repo."""
    cache_root = _xdg_cache_home() / "dsoxlab" / repo_meta.id
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root / "ssh_config"


def write_ssh_config(
    inventory: dict[str, Any], repo_meta: RepoMetadata
) -> Path:
    """Génère un ``ssh_config`` OpenSSH depuis l'inventory et l'écrit (XDG).

    Utile pour les outils tiers (testinfra, scp, rsync, IDE) qui ne savent
    pas parser des ``ansible_ssh_common_args`` complexes contenant un
    ProxyCommand entre quotes. Avec un fichier ssh_config par-Host,
    OpenSSH applique automatiquement le ProxyCommand bastion.

    Returns:
        Path du fichier ``ssh_config`` généré.
    """
    hosts = (
        inventory.get("all", {})
        .get("children", {})
        .get("labenv", {})
        .get("hosts", {})
    )

    lines: list[str] = [
        "# Auto-généré par dsoxlab — ne pas éditer.",
        "# Source : inventory dynamique (Terraform outputs + meta.yml).",
        "",
    ]
    for name, vars_ in hosts.items():
        ip = vars_.get("ansible_host", "")
        user = vars_.get("ansible_user", "ansible")
        identity = vars_.get("ansible_ssh_private_key_file", "")
        extra = vars_.get("ansible_ssh_common_args", "") or ""

        lines.append(f"Host {name}")
        if ip:
            lines.append(f"  HostName {ip}")
        lines.append(f"  User {user}")
        if identity:
            lines.append(f"  IdentityFile {identity}")
            lines.append("  IdentitiesOnly yes")
        lines.append("  StrictHostKeyChecking no")
        lines.append("  UserKnownHostsFile /dev/null")
        # Extrait le ProxyCommand des ansible_ssh_common_args.
        m = re.search(r"-o ProxyCommand=(?:'([^']*)'|\"([^\"]*)\")", extra)
        if m:
            proxy_cmd = m.group(1) or m.group(2)
            lines.append(f"  ProxyCommand {proxy_cmd}")
        lines.append("")

    path = ssh_config_path(repo_meta)
    # Atomique, et le mode posé AVANT le remplacement : un ssh_config coupé
    # au milieu d'un bloc « Host » fait échouer ssh, scp et le conftest d'un
    # dépôt de labs sur une configuration incohérente, ce qui est plus dur à
    # diagnostiquer qu'une configuration absente.
    ecrire_atomiquement(path, "\n".join(lines), mode=0o600)
    return path


def user_ssh_config_path(repo_meta: RepoMetadata) -> Path:
    """Le fragment déposé dans le ``~/.ssh/config.d`` de l'apprenant."""
    return Path.home() / ".ssh" / "config.d" / f"{repo_meta.id}.conf"


def ssh_config_include_present() -> bool:
    """``~/.ssh/config`` charge-t-il bien le répertoire de fragments ?

    Sans cette ligne, le fragment est écrit mais jamais lu, et ``ssh web1.lab``
    continue d'échouer : mieux vaut le dire que laisser croire.
    """
    principal = Path.home() / ".ssh" / "config"
    if not principal.is_file():
        return False
    try:
        contenu = principal.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(
        ligne.strip().lower().startswith("include")
        and "config.d" in ligne
        for ligne in contenu.splitlines()
    )


def write_user_ssh_config(
    inventory: dict[str, Any], repo_meta: RepoMetadata
) -> Path:
    """Écrit le fragment SSH de la formation dans ``~/.ssh/config.d``.

    Le ``ssh_config`` du cache sert dsoxlab et les tests, mais il impose un
    ``-F`` que personne ne tape. Or les énoncés demandent de se connecter à une
    machine par son nom, et ce nom n'est ni dans le DNS ni dans ``/etc/hosts`` :
    sans ce fragment, un ``ssh alma-rhcsa-1.lab`` échoue.

    Le fichier porte le ``repo.id``, donc une formation par fichier : deux
    catalogues provisionnés en parallèle ne s'écrasent pas. Il est réécrit à
    chaque provision, les adresses changeant à chaque cycle.
    """
    contenu = ssh_config_path(repo_meta).read_text(encoding="utf-8")
    entete = (
        f"# Généré par dsoxlab pour la formation « {repo_meta.id} ».\n"
        f"# Réécrit à chaque provision, retiré au destroy : ne pas éditer.\n"
    )
    cible = user_ssh_config_path(repo_meta)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.parent.chmod(0o700)
    ecrire_atomiquement(cible, entete + contenu, mode=0o600)
    return cible


def remove_user_ssh_config(repo_meta: RepoMetadata) -> bool:
    """Retire le fragment. Rend True s'il existait.

    Laisser derrière soi un fichier pointant des adresses mortes est le
    scénario que ce projet a déjà connu : une configuration figée qui envoie
    vers des IP recyclées est pire que pas de configuration du tout.
    """
    cible = user_ssh_config_path(repo_meta)
    if not cible.exists():
        return False
    cible.unlink()
    return True


class HostReadyTimeout(RuntimeError):
    """Levée quand un host ne devient pas joignable en SSH dans le délai imparti."""


#: Variable d'environnement qui règle l'attente de disponibilité des hosts.
HOST_READY_TIMEOUT_ENV = "DSOXLAB_HOST_READY_TIMEOUT"

#: Des hôtes n'ont pas répondu dans le délai imparti.
#:
#: `provision` se contentait d'un avertissement, puis annonçait « ✔ N hôtes
#: provisionnés » et sortait en 0. L'échec était donc invisible à tout script,
#: et le `run` suivant échouait en « unreachable » sans lien visible avec la
#: cause. Un code dédié le dit, comme 5 et 6 le font pour les orphelins.
EXIT_HOTES_INJOIGNABLES = 8


#: Défaut, en secondes. Confortable sur un poste dédié, juste sur un hôte
#: modeste : le boot parallèle de plusieurs VMs y sature le CPU, et un rapport
#: d'usage a mesuré un host prêt à 181 s, soit une seconde après l'abandon.
HOST_READY_TIMEOUT_DEFAULT = 180.0


def _host_ready_timeout(explicite: float | None) -> float:
    """Résout le délai d'attente : argument, puis variable d'env, puis défaut.

    Un délai en dur ne convient pas à tous les postes. Le matériel de l'apprenant
    n'est pas un paramètre du dépôt de labs : c'est une propriété de SA machine,
    donc une variable d'environnement, pas une clé du ``meta.yml``.

    Une valeur non numérique ou négative est ignorée au profit du défaut : sur
    ce chemin, un provision qui échoue parce qu'une variable est mal écrite
    serait bien pire que le délai qu'elle voulait corriger.
    """
    if explicite is not None:
        return explicite
    brut = os.environ.get(HOST_READY_TIMEOUT_ENV, "").strip()
    if not brut:
        return HOST_READY_TIMEOUT_DEFAULT
    try:
        valeur = float(brut)
    except ValueError:
        logger.warning(
            "%s=%r n'est pas un nombre : on garde %.0f s.",
            HOST_READY_TIMEOUT_ENV,
            brut,
            HOST_READY_TIMEOUT_DEFAULT,
        )
        return HOST_READY_TIMEOUT_DEFAULT
    if valeur <= 0:
        logger.warning(
            "%s=%r doit être positif : on garde %.0f s.",
            HOST_READY_TIMEOUT_ENV,
            brut,
            HOST_READY_TIMEOUT_DEFAULT,
        )
        return HOST_READY_TIMEOUT_DEFAULT
    return valeur


def _reset_kvm_domain(repo_meta: RepoMetadata, fqdn: str) -> bool:
    """Envoie un ``virsh reset`` à un domaine KVM. Retourne True si tenté.

    Débloque une VM coincée au premier boot. Cas connu : Debian cloud (generic
    comme genericcloud) sous firmware OVMF/EFI avec resize du disque au premier
    démarrage kernel-panique (« Attempted to kill init »), bug documenté côté
    Proxmox et XCP-ng. Un simple reset passe le panic : la VM redémarre et boote
    normalement. alma/ubuntu ne déclenchent pas ce cas, mais le reset répare
    aussi n'importe quelle VM bloquée au boot. No-op hors provider kvm.
    """
    infra = repo_meta.infra
    if infra is None or getattr(infra, "provider", None) != "kvm":
        return False
    # check=False : la fonction rend un booléen « tenté ou non » et son
    # appelant enchaîne. Un reset refusé (droits absents, domaine déjà éteint)
    # ne doit pas casser l'attente : c'est un dépannage opportuniste, pas une
    # étape. `run_virsh` porte la détection du préfixe `sudo -n` : un `sudo`
    # brut pendait sur un prompt sans terminal, et échouait toujours chez qui
    # joint libvirt par le groupe, sans droits sudo.
    try:
        res = libvirt.run_virsh(["reset", fqdn], check=False)
    except CommandError:
        return False
    if res.ok:
        logger.info("reset envoyé à %s (déblocage du premier boot)", fqdn)
        return True
    return False


#: Préfixe de la ligne par laquelle l'hôte distant remonte le code de retour de
#: ``cloud-init status --wait``. Un marqueur explicite plutôt qu'une position :
#: la sortie de ``status --long`` change d'une version à l'autre.
_MARQUEUR_RC = "__dsoxlab_cloudinit_rc="


def _etat_cloud_init(sortie: str) -> tuple[int | None, str]:
    """Le code de retour de cloud-init et ce qu'il a dit, lus dans la sortie SSH.

    Rend ``(None, "")`` quand l'hôte n'a pas de cloud-init : ce n'est pas un
    défaut, seulement une image qui n'en embarque pas.
    """
    code: int | None = None
    detail: list[str] = []
    for ligne in sortie.splitlines():
        if ligne.startswith(_MARQUEUR_RC):
            valeur = ligne[len(_MARQUEUR_RC):].strip()
            code = int(valeur) if valeur.isdigit() else None
            continue
        if code is not None and ligne.strip():
            detail.append(ligne.strip())
    return code, "\n".join(detail[:12])


def _commande_cloud_init() -> str:
    """La commande jouée sur l'hôte pour attendre cloud-init ET lire son état.

    Extraite plutôt qu'inline : ce qu'elle envoie est un contrat — un marqueur
    de code de retour, et la sortie de ``status --long`` — que les tests
    éprouvent en l'appelant, sans relire le fichier source.
    """
    return (
        "command -v cloud-init >/dev/null 2>&1 || exit 0\n"
        "sudo -n cloud-init status --wait >/dev/null 2>&1\n"
        f"echo \"{_MARQUEUR_RC}$?\"\n"
        "sudo -n cloud-init status --long 2>&1 || true\n"
        "exit 0\n"
    )


def wait_for_hosts_ready(
    repo_meta: RepoMetadata,
    hosts: list[str],
    *,
    timeout: float | None = None,
    poll_interval: float = 3.0,
    connect_timeout: int = 8,
    reset_after: float = 60.0,
    on_attempt: Callable[[str, int], None] | None = None,
) -> list[str]:
    """Attend que chaque host soit réellement utilisable après ``terraform apply``.

    Juste après le provisioning, la VM boote encore : ``sshd`` démarre, puis
    cloud-init crée le compte de service ``ansible`` et configure sudo. Tant que
    ce n'est pas terminé, la première commande ``dsoxlab run`` échoue en
    *unreachable* (« dark ») côté Ansible. On sonde donc une connexion SSH
    réelle sous le compte ``ansible`` (le compte de connexion de l'automatisation),
    ce qui prouve à la fois que ``sshd`` répond et que le compte existe, puis on
    laisse ``cloud-init status --wait`` bloquer jusqu'à la fin de la configuration.

    Args:
        repo_meta: métadonnées du dépôt (pour construire le ssh_config).
        hosts: FQDN à attendre (typiquement ``result.hosts`` du provision).
        timeout: délai global maximum, en secondes, par host. ``None`` (défaut)
            résout par ``DSOXLAB_HOST_READY_TIMEOUT``, sinon 180 s.
        poll_interval: pause entre deux tentatives, en secondes.
        connect_timeout: ``ConnectTimeout`` SSH de chaque tentative, en secondes.
        on_attempt: callback ``(fqdn, numéro_tentative)`` pour l'affichage.

    Returns:
        Les avertissements constatés pendant l'attente — un cloud-init qui a
        terminé en erreur, notamment. La liste est vide quand tout s'est bien
        passé ; l'appelant les affiche, il n'a pas à les déduire.

    Raises:
        HostReadyTimeout: si un host reste injoignable au-delà de ``timeout``.
    """
    if not hosts:
        return []

    timeout = _host_ready_timeout(timeout)

    inventory = build_inventory(
        repo_meta, terraform_outputs=read_terraform_outputs(repo_meta)
    )
    ssh_cfg = write_ssh_config(inventory, repo_meta)
    avertissements: list[str] = []

    # SSH réussit dès que sshd répond ET que le compte ansible existe ; on enchaîne sur
    # `cloud-init status --wait` (best-effort) pour ne rendre la main qu'une fois
    # la VM entièrement configurée. Le `|| true` évite d'échouer sur un état
    # cloud-init « degraded » : ce qui compte, c'est qu'il ait terminé.
    #
    # `sudo -n` est indispensable : sans privilèges, la commande sort en
    # `PermissionError: /run/cloud-init/cloud.cfg` (mesuré sur AlmaLinux 9), donc
    # rc=1. Le `|| true` avalait cet échec et l'attente ne garantissait plus rien :
    # on rendait la main avant la fin de cloud-init, en croyant l'avoir attendue.
    # `-n` (non interactif) évite de bloquer si sudo réclamait un mot de passe.
    # `--wait` bloque jusqu'à la FIN de cloud-init, et son code de retour dit
    # comment il a fini. L'ancienne forme jetait les deux (`>/dev/null` et
    # `|| true`) : un cloud-init `degraded` — une quinzaine de paquets qui
    # n'ont pas pu s'installer parce qu'il n'y avait pas d'accès sortant —
    # devenait indistinguable d'un succès. L'hôte était déclaré prêt, puis les
    # labs échouaient sur des commandes absentes, sans que rien ne relie les
    # deux.
    #
    # Ne pas bloquer reste la bonne décision : ce qui compte pour rendre la
    # main, c'est que cloud-init ait TERMINÉ. Mais terminer mal doit se dire.
    #
    # `sudo -n` est indispensable : sans privilèges, la commande sort en
    # `PermissionError: /run/cloud-init/cloud.cfg` (mesuré sur AlmaLinux 9).
    # `-n` évite de bloquer si sudo réclamait un mot de passe.
    remote_cmd = _commande_cloud_init()

    for fqdn in hosts:
        start = time.monotonic()
        deadline = start + timeout
        reset_deadline = start + reset_after
        reset_done = False
        attempt = 0
        while True:
            attempt += 1
            if on_attempt is not None:
                on_attempt(fqdn, attempt)
            # check=False : c'est une boucle d'attente. Un échec signifie
            # « pas encore prêt » et doit être réessayé jusqu'au deadline ;
            # lever au premier essai rendrait l'attente inutile.
            proc = subprocess.run(
                [
                    "ssh",
                    "-F",
                    str(ssh_cfg),
                    "-o",
                    f"ConnectTimeout={connect_timeout}",
                    "-o",
                    "BatchMode=yes",
                    fqdn,
                    remote_cmd,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0:
                logger.info("Host %s prêt (tentative %d).", fqdn, attempt)
                code, detail = _etat_cloud_init(proc.stdout)
                if code is not None and code != 0:
                    avertissements.append(_(
                        "cloud_init_degrade", host=fqdn, code=code,
                        detail=detail or _("cloud_init_sans_detail"),
                    ))
                break
            if time.monotonic() >= deadline:
                raise HostReadyTimeout(_(
                    "err_host_ready_timeout", fqdn=fqdn, timeout=f"{timeout:.0f}",
                ))
            # Un host dont sshd n'a JAMAIS répondu après `reset_after` est
            # probablement coincé au boot (kernel panic Debian cloud + OVMF +
            # resize, cf. _reset_kvm_domain). Un reset unique le débloque. Sans
            # risque pour une VM saine : dès que sshd répond, la tentative se
            # connecte et bloque sur `cloud-init status --wait`, donc ce seuil
            # n'est plus évalué (le boot normal sshd est bien en deçà de 60 s).
            if not reset_done and time.monotonic() >= reset_deadline:
                reset_done = _reset_kvm_domain(repo_meta, fqdn) or True
            time.sleep(poll_interval)

    return avertissements


def write_inventory_file(
    inventory: dict[str, Any], repo_meta: RepoMetadata
) -> Path:
    """Écrit l'inventory en JSON dans le cache XDG. Retourne le chemin.

    Le format JSON est natif pour Ansible (``ANSIBLE_INVENTORY_ENABLED``
    inclut le plugin ``constructed`` qui lit JSON). Plus simple que
    ``ini`` à générer programmatiquement.
    """
    path = inventory_path(repo_meta)
    ecrire_atomiquement(path, json.dumps(inventory, indent=2))
    return path


def read_terraform_outputs(repo_meta: RepoMetadata) -> dict[str, Any] | None:
    """Lit les outputs Terraform du provider courant si disponibles.

    Retourne None si le state Terraform n'existe pas encore ou si
    ``terraform`` n'est pas installé. Les outputs sont au format JSON
    natif (``terraform output -json``).

    Note : le work-dir Terraform vit dans XDG state
    (``~/.local/state/dsoxlab/<repo>/terraform/<provider>/``), pas dans
    le dépôt training. Voir ``infra/terraform.py:workdir()``.
    """
    # Délégation à infra/terraform.py — single source of truth pour le path.
    try:
        from .terraform import ProviderNotImplemented, workdir

        try:
            tf_dir = workdir(repo_meta)
        except ProviderNotImplemented:
            return None
    except ImportError:
        return None

    state_file = tf_dir / "terraform.tfstate"
    if not state_file.is_file():
        return None

    try:
        from ..utils.shell import run_command

        result = run_command(
            ["terraform", "-chdir=" + str(tf_dir), "output", "-json"],
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.debug("Lecture outputs Terraform impossible : %s", exc)
        return None

    if not result.ok or not result.stdout.strip():
        return None

    try:
        outputs: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return outputs


def _xdg_cache_home() -> Path:
    """Retourne ``$XDG_CACHE_HOME`` ou ``~/.cache``."""
    import os

    env = os.environ.get("XDG_CACHE_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".cache"
