"""Incus : le client, le démon, le groupe, et le pool de stockage.

Extrait de ``services/doctor.py`` (issue #199), sans changement de
comportement. Voir ce module pour les principes du diagnostic.
"""

from __future__ import annotations

import getpass
import os
import shutil

from ...i18n import _
from .modele import STATE_UNKNOWN, Check, FixKind, _check, _doctor, _fix, _installer


def _current_user() -> str:
    """L'utilisateur à qui s'adresse un correctif de groupe.

    ``$USER`` d'abord, comme le faisait la chaîne shell d'avant ; à défaut,
    ``getpass.getuser()`` lit la table des comptes. L'ancien repli littéral
    ``$USER`` n'a plus de sens sans shell pour l'expanser.
    """
    return os.environ.get("USER") or getpass.getuser()


def _check_incus() -> Check:
    """Binaire + daemon + permissions user + init storage/network.

    Un simple ``which incus`` ne suffit pas : sans daemon actif ni
    appartenance au groupe ``incus``, le client ne peut rien faire
    (« permissions to talk to the incus daemon »).
    """
    if not shutil.which("incus"):
        return _check(
            "incus", False, _("detail_incus_missing"),
            fix=_fix(_installer(["incus"], ["incus"])),
        )

    # Le numéro de version n'est qu'un ornement du diagnostic. Le verdict vient
    # de la sonde suivante, qui, elle, lit son code retour.
    ver = _doctor()._sonder(["incus", "--version"])
    version = (ver.stdout.strip() if ver else "") or "?"

    probe = _doctor()._sonder(["incus", "list"])
    # Muette, elle ne prouve rien sinon que le daemon ne répond pas : c'est le
    # même geste de réparation que sur un daemon arrêté.
    if probe is None:
        return _check(
            "incus", False, _("detail_incus_daemon_down", version=version),
            fix=_fix(["sudo", "systemctl", "enable", "--now", "incus.service"]),
        )
    if probe.returncode == 0:
        return _check("incus", True, _("detail_incus_ok", version=version))

    err = (probe.stderr or "").lower()
    if "permission" in err or "socket" in err:
        # Soit daemon inactif, soit user hors du groupe : deux causes,
        # deux remédiations, que l'erreur seule ne distingue pas.
        # `is-active` répond par son code retour, c'est sa façon de dire non.
        etat = _doctor()._sonder(["systemctl", "is-active", "--quiet", "incus.service"])
        daemon_active = etat is not None and etat.returncode == 0
        if not daemon_active:
            return _check(
                "incus", False,
                _("detail_incus_daemon_down", version=version),
                fix=_fix(["sudo", "systemctl", "enable", "--now", "incus.service"]),
            )
        # NEEDS_RELOGIN : l'appartenance à un groupe ne prend effet qu'à la
        # session suivante. Sans cette catégorie, l'utilisateur relançait
        # `doctor`, revoyait le rouge, et croyait le correctif en échec.
        return _check(
            "incus", False,
            _("detail_incus_no_group", version=version),
            fix=_fix(
                ["sudo", "usermod", "-aG", "incus,incus-admin", _current_user()],
                kind=FixKind.NEEDS_RELOGIN,
            ),
        )
    if "no storage pools" in err or "init" in err:
        return _check(
            "incus", False,
            _("detail_incus_no_init", version=version),
            fix=_fix(["sudo", "incus", "admin", "init", "--auto"]),
        )

    tail = (probe.stderr or probe.stdout).strip().splitlines()
    return _check("incus", False, tail[-1] if tail else _("detail_unknown_error"))


#: Le pool que le template Incus écrit en dur dans ses volumes. Il n'est
#: **pas** créé par Terraform, contrairement au réseau : `incus admin init` est
#: le seul geste qui le pose.
_POOL_INCUS = "default"


def _check_incus_pool() -> Check:
    """Le pool de stockage d'Incus existe-t-il ?

    `incus list` réussit sur une installation jamais initialisée — elle rend
    simplement une liste vide — si bien que `_check_incus` passait au vert et
    que rien n'annonçait l'échec de `provision`. Le template crée le réseau
    mais **suppose** le pool : il l'écrit en dur dans chaque volume.

    C'est le pendant exact de `_check_libvirt_pool`, qui existait déjà côté
    KVM. Son absence côté Incus est ce qui faisait dire à un utilisateur que
    « seules les résolutions liées à KVM sont proposées ».
    """
    sonde = _doctor()._sonder(["incus", "storage", "list", "--format", "csv"])
    if sonde is None or sonde.returncode != 0:
        # Ne rien pouvoir mesurer n'est ni un pool présent ni un pool absent.
        return _check("incus_pool", False, _("detail_incus_pool_muet"),
                      forced_state=STATE_UNKNOWN)

    pools = [
        ligne.split(",")[0]
        for ligne in sonde.stdout.splitlines() if ligne.strip()
    ]
    if _POOL_INCUS in pools:
        return _check("incus_pool", True, _POOL_INCUS)
    return _check(
        "incus_pool", False,
        _("detail_incus_pool_absent", pool=_POOL_INCUS),
        fix=_fix(["sudo", "incus", "admin", "init", "--auto"]),
    )
