"""Le pool Incus est diagnostiqué comme celui de libvirt (linux-dsoxlab-training#54).

Un utilisateur a signalé que sur un provisionnement Incus raté faute d'avoir
joué `incus admin init --auto`, « seules les résolutions liées à KVM sont
proposées ». La vérification a donné raison au symptôme et tort à l'hypothèse
la plus évidente : `_check_incus` **propose bien** `incus admin init` — mais
seulement quand `incus list` échoue en le disant.

Or `incus list` **réussit** sur une installation jamais initialisée : elle rend
simplement une liste vide. Le contrôle passait donc au vert, et le seul contrôle
supplémentaire de la branche Incus était l'outil ISO — là où la branche KVM
contrôle son pool de stockage depuis longtemps.

Le template le suppose sans le créer : il crée bien le réseau
(`resource "incus_network" "lab"`) mais écrit `pool = "default"` en dur dans
chaque volume. Sans ce pool, `provision` échoue.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dsoxlab.services import doctor


class _Sortie:
    """Ce que `_sonder` rend : un CompletedProcess, ou None s'il n'a pas répondu."""

    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def _sonde(monkeypatch: pytest.MonkeyPatch, resultat: Any) -> None:
    monkeypatch.setattr(doctor, "_sonder", lambda *a, **k: resultat)


# ── Les trois états, comme pour le pool libvirt ─────────────────────────────

def test_un_pool_present_passe_au_vert(monkeypatch: pytest.MonkeyPatch) -> None:
    _sonde(monkeypatch, _Sortie("default,zfs,,14,CREATED\n"))

    controle = doctor._check_incus_pool()

    assert controle.ok is True
    assert "default" in controle.detail


def test_un_pool_absent_propose_l_initialisation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le cas de l'issue : incus répond, mais n'a aucun pool."""
    _sonde(monkeypatch, _Sortie(""))

    controle = doctor._check_incus_pool()

    assert controle.ok is False
    assert controle.fix is not None
    assert ("sudo", "incus", "admin", "init", "--auto") in controle.fix.commands


def test_une_sonde_muette_ne_tranche_pas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ne pas pouvoir lister n'est ni un pool présent ni un pool absent.

    Proposer `incus admin init` sur une machine dont on ignore l'état
    réinitialiserait peut-être une installation qui fonctionne.
    """
    _sonde(monkeypatch, None)

    controle = doctor._check_incus_pool()

    assert controle.state == doctor.STATE_UNKNOWN
    assert controle.fix is None


def test_un_autre_pool_ne_suffit_pas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le template écrit `default` en dur : c'est celui-là qu'il faut.

    Un pool nommé autrement existe sans que le provisionnement fonctionne.
    """
    _sonde(monkeypatch, _Sortie("autre-pool,dir,,3,CREATED\n"))

    assert doctor._check_incus_pool().ok is False


# ── Le classement : Incus rattrape la symétrie qui lui manquait ─────────────

def test_le_pool_incus_est_requis_quand_incus_est_actif(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C'est l'absence de ce contrôle qui a produit l'issue."""
    monkeypatch.setattr(doctor, "_check_incus",
                        lambda: doctor._check("incus", True, "7.2"))
    monkeypatch.setattr(doctor, "_check_kvm",
                        lambda: doctor._check("kvm", False, "absent"))
    _sonde(monkeypatch, _Sortie("default,zfs,,14,CREATED\n"))

    (tmp_path / "meta.yml").write_text(
        "repo:\n  id: essai\n  category: essai\n"
        "infra:\n  provider: incus\n  hosts:\n    - name: h.lab\n",
        encoding="utf-8")
    base = tmp_path / "labs" / "l1"
    base.mkdir(parents=True)
    (base / "lab.yaml").write_text(
        "id: l1\ntitle: T\nlevel: l1\nskills: [s]\ndistros: [any]\n"
        "doc_url: https://example.org/\n"
        "runtime:\n  type: vm\n  targets:\n    - name: c\n      host: h.lab\n",
        encoding="utf-8")

    from dsoxlab.discovery.scanner import read_repo_metadata

    rapport = doctor.collect_checks(tmp_path, read_repo_metadata(tmp_path))

    assert "incus_pool" in [c.key for c in rapport.required]


def test_le_pool_incus_ne_gene_pas_un_depot_kvm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un dépôt qui provisionne en KVM n'a pas à voir de contrôle Incus.

    C'est la règle du dépôt appliquée aux providers : jamais de rouge pour un
    composant que ce catalogue n'utilise pas.
    """
    monkeypatch.setattr(doctor, "_check_kvm",
                        lambda: doctor._check("kvm", True, "ok"))
    monkeypatch.setattr(doctor, "_check_libvirt_pool",
                        lambda pool: doctor._check("libvirt_pool", True, pool))

    (tmp_path / "meta.yml").write_text(
        "repo:\n  id: essai\n  category: essai\n"
        "infra:\n  provider: kvm\n  hosts:\n    - name: h.lab\n",
        encoding="utf-8")
    base = tmp_path / "labs" / "l1"
    base.mkdir(parents=True)
    (base / "lab.yaml").write_text(
        "id: l1\ntitle: T\nlevel: l1\nskills: [s]\ndistros: [any]\n"
        "doc_url: https://example.org/\n"
        "runtime:\n  type: vm\n  targets:\n    - name: c\n      host: h.lab\n",
        encoding="utf-8")

    from dsoxlab.discovery.scanner import read_repo_metadata

    rapport = doctor.collect_checks(tmp_path, read_repo_metadata(tmp_path))

    assert "incus_pool" not in [c.key for c in rapport.required]


# ── Ce que le template suppose, et qui justifie le contrôle ────────────────

def test_le_template_suppose_le_pool_sans_le_creer() -> None:
    """Si un jour Terraform crée le pool, ce contrôle n'a plus lieu d'être.

    Le test le dira : il échouera quand la ressource apparaîtra, et personne
    n'aura à se souvenir que ce diagnostic existait pour cette raison.
    """
    import dsoxlab

    main = (Path(dsoxlab.__file__).resolve().parent / "templates" / "terraform"
            / "incus" / "main.tf").read_text(encoding="utf-8")

    assert 'pool         = "default"' in main or '"pool" = "default"' in main, (
        "le template ne référence plus le pool en dur"
    )
    assert 'resource "incus_storage_pool"' not in main, (
        "le template crée désormais le pool : le contrôle doctor est caduc"
    )
