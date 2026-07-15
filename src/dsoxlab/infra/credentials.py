"""Chargement des credentials cloud depuis les fichiers de config standards.

dsoxlab respecte les **conventions standards** de chaque fournisseur cloud :
l'apprenant a déjà configuré ses credentials avec les outils habituels
(``oapi-cli configure``, ``aws configure``, ``gcloud auth login``, etc.).
dsoxlab lit ces fichiers et passe les variables d'environnement attendues
par Terraform — l'apprenant n'a **rien à exporter manuellement**.

Le profil utilisé est lu depuis ``meta.yml: providers.<name>.profile``
(défaut ``default``), ou surchargé par
``DSOXLAB_<PROVIDER>_PROFILE=<name>``.

Conventions par provider :

| Provider | Fichier de config              | Format    | Profil par défaut |
|----------|--------------------------------|-----------|-------------------|
| outscale | ``~/.osc/config.json``          | JSON      | ``default``       |
| aws      | ``~/.aws/credentials`` + config | INI       | ``default``       |
| gcp      | ``~/.config/gcloud/...``        | JSON      | ADC               |
| azure    | ``~/.azure/azureProfile.json``  | JSON      | active            |
| proxmox  | ``~/.proxmoxer/config``         | INI       | ``default``       |
| kvm      | (aucun — libvirt local)         | —         | —                 |
| vagrant  | (aucun — Vagrantfile local)     | —         | —                 |
"""

from __future__ import annotations

import configparser
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class CredentialsNotFound(RuntimeError):
    """Levée quand le fichier de credentials du provider est introuvable
    ou ne contient pas le profil demandé. Le message contient les
    instructions pour résoudre."""


def load(provider: str, profile: str | None = None) -> dict[str, str]:
    """Charge les credentials du provider et retourne un dict d'env vars.

    Args:
        provider: ``outscale`` | ``aws`` | ``gcp`` | ``azure`` |
                  ``proxmox`` | ``kvm`` | ``vagrant``…
        profile: nom du profil dans le fichier de config. Si None, lit
                 ``DSOXLAB_<PROVIDER>_PROFILE`` ou ``default``.

    Returns:
        Dict ``{ENV_VAR: VALUE}`` à passer à subprocess via ``env=``.
        Vide pour les providers sans credentials (kvm, vagrant).

    Raises:
        CredentialsNotFound: si le fichier ou profil est introuvable.
        NotImplementedError: si le provider n'a pas encore de loader.
    """
    profile_resolved = (
        profile
        or os.environ.get(f"DSOXLAB_{provider.upper()}_PROFILE", "").strip()
        or "default"
    )

    loaders = {
        "outscale": _load_outscale,
        "aws": _load_aws,
        "kvm": _load_none,
        "vagrant": _load_none,
        "incus": _load_none,
        "proxmox": _load_proxmox,
        "gcp": _load_gcp,
        "azure": _load_azure,
    }
    loader = loaders.get(provider)
    if loader is None:
        raise NotImplementedError(
            f"Loader credentials non implémenté pour le provider "
            f"'{provider}'. Voir src/dsoxlab/infra/credentials.py."
        )
    return loader(profile_resolved)


# ── Outscale ────────────────────────────────────────────────────────────

def _load_outscale(profile: str) -> dict[str, str]:
    """Lit ``~/.osc/config.json`` et retourne les env vars Outscale.

    Format attendu (JSON multi-profils) :

        {
          "default": {
            "access_key": "...",
            "secret_key": "...",
            "region": "eu-west-2",
            "host": "outscale.com"
          },
          "student02": { ... }
        }

    Variables d'env produites pour le provider Terraform Outscale :
    ``OSC_ACCESS_KEY``, ``OSC_SECRET_KEY``, ``OSC_REGION``.
    """
    cfg_path = Path.home() / ".osc" / "config.json"
    if not cfg_path.is_file():
        raise CredentialsNotFound(
            f"Fichier {cfg_path} absent. Configure tes credentials "
            f"Outscale via 'oapi-cli configure' (ou crée le JSON manuellement)."
        )

    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CredentialsNotFound(
            f"{cfg_path} : JSON invalide ({exc})."
        ) from exc

    if profile not in data:
        raise CredentialsNotFound(
            f"Profil '{profile}' introuvable dans {cfg_path}. "
            f"Profils disponibles : {sorted(data.keys())}. "
            f"Précise via meta.yml: providers.outscale.profile ou "
            f"DSOXLAB_OUTSCALE_PROFILE=<name>."
        )

    cfg = data[profile]
    access_key = cfg.get("access_key")
    secret_key = cfg.get("secret_key")
    region = cfg.get("region") or "eu-west-2"
    if not access_key or not secret_key:
        raise CredentialsNotFound(
            f"Profil '{profile}' dans {cfg_path} : access_key et "
            f"secret_key requis."
        )

    return {
        "OSC_ACCESS_KEY": str(access_key),
        "OSC_SECRET_KEY": str(secret_key),
        "OSC_REGION": str(region),
    }


# ── AWS ─────────────────────────────────────────────────────────────────

def _load_aws(profile: str) -> dict[str, str]:
    """Lit ``~/.aws/credentials`` + ``~/.aws/config`` (format INI)."""
    creds_path = Path.home() / ".aws" / "credentials"
    config_path = Path.home() / ".aws" / "config"
    if not creds_path.is_file():
        raise CredentialsNotFound(
            f"Fichier {creds_path} absent. Configure via 'aws configure'."
        )

    creds = configparser.ConfigParser()
    creds.read(creds_path)
    if profile not in creds:
        raise CredentialsNotFound(
            f"Profil '{profile}' introuvable dans {creds_path}. "
            f"Profils : {sorted(creds.sections())}. "
            f"Précise via meta.yml: providers.aws.profile ou "
            f"DSOXLAB_AWS_PROFILE=<name>."
        )
    section = creds[profile]
    access_key = section.get("aws_access_key_id")
    secret_key = section.get("aws_secret_access_key")
    if not access_key or not secret_key:
        raise CredentialsNotFound(
            f"Profil '{profile}' dans {creds_path} : aws_access_key_id "
            f"et aws_secret_access_key requis."
        )

    # La région est dans ~/.aws/config (parfois avec le préfixe "profile")
    region = ""
    if config_path.is_file():
        cfg = configparser.ConfigParser()
        cfg.read(config_path)
        candidate = profile if profile in cfg else f"profile {profile}"
        if candidate in cfg:
            region = cfg[candidate].get("region", "")

    env = {
        "AWS_ACCESS_KEY_ID": access_key,
        "AWS_SECRET_ACCESS_KEY": secret_key,
    }
    if region:
        env["AWS_REGION"] = region
        env["AWS_DEFAULT_REGION"] = region
    # Token de session si MFA / SSO actif
    session_token = section.get("aws_session_token")
    if session_token:
        env["AWS_SESSION_TOKEN"] = session_token
    return env


# ── GCP ─────────────────────────────────────────────────────────────────

def _load_gcp(profile: str) -> dict[str, str]:
    """Lit les credentials gcloud (Application Default Credentials)."""
    del profile  # GCP ne distingue pas par profil au niveau ADC
    adc_path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    if not adc_path.is_file():
        raise CredentialsNotFound(
            f"Fichier {adc_path} absent. Configure via "
            f"'gcloud auth application-default login'."
        )
    return {
        "GOOGLE_APPLICATION_CREDENTIALS": str(adc_path),
    }


# ── Azure ───────────────────────────────────────────────────────────────

def _load_azure(profile: str) -> dict[str, str]:
    """Lit ``~/.azure/azureProfile.json`` (subscription active)."""
    del profile
    cfg_path = Path.home() / ".azure" / "azureProfile.json"
    if not cfg_path.is_file():
        raise CredentialsNotFound(
            f"Fichier {cfg_path} absent. Configure via 'az login'."
        )
    # Le provider azurerm Terraform lit directement la session az CLI.
    # Il suffit que `az login` ait été fait — pas besoin de variables.
    return {}


# ── Proxmox ─────────────────────────────────────────────────────────────

def _load_proxmox(profile: str) -> dict[str, str]:
    """Lit ``~/.proxmoxer/config`` (format INI multi-profils).

    Note : Proxmox Terraform provider attend un token API. Le format
    privilégié est :

        [default]
        api_url = https://proxmox.lan:8006/api2/json
        token_id = root@pam!terraform
        token_secret = <uuid>
    """
    cfg_path = Path.home() / ".proxmoxer" / "config"
    if not cfg_path.is_file():
        raise CredentialsNotFound(
            f"Fichier {cfg_path} absent. Crée-le manuellement avec "
            f"un token API Proxmox (api_url, token_id, token_secret)."
        )
    cfg = configparser.ConfigParser()
    cfg.read(cfg_path)
    if profile not in cfg:
        raise CredentialsNotFound(
            f"Profil '{profile}' introuvable dans {cfg_path}. "
            f"Profils : {sorted(cfg.sections())}."
        )
    section = cfg[profile]
    api_url = section.get("api_url")
    token_id = section.get("token_id")
    token_secret = section.get("token_secret")
    if not (api_url and token_id and token_secret):
        raise CredentialsNotFound(
            f"Profil '{profile}' dans {cfg_path} : api_url, token_id "
            f"et token_secret requis."
        )
    return {
        "PROXMOX_VE_ENDPOINT": api_url,
        "PROXMOX_VE_API_TOKEN": f"{token_id}={token_secret}",
        "PROXMOX_VE_INSECURE": "true",  # par défaut en homelab
    }


# ── No-op (kvm, vagrant, incus) ─────────────────────────────────────────

def _load_none(profile: str) -> dict[str, str]:
    """Pas de credentials externes (libvirt local, Vagrant, Incus)."""
    del profile
    return {}
