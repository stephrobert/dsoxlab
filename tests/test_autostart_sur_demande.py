"""Les machines ne démarrent avec l'hôte que si le catalogue le demande (issue #377).

Jusqu'à 0.9.4, les templates kvm et incus posaient le démarrage automatique
sans condition. Au redémarrage d'un poste de formation, le 2026-11-16, sept VM
sont remontées seules, dont cinq arrêtées exprès : 12 Go pris avant toute
demande. Ces tests tiennent le contrat qui le remplace :

- ``infra.autostart`` absent : les machines ne démarrent pas avec l'hôte ;
- seul le booléen YAML ``true`` l'active, une chaîne ``"true"`` ne suffit pas ;
- la variable n'est passée qu'aux providers qui la déclarent (kvm, incus) ;
- les templates lisent la variable au lieu d'une valeur écrite en dur ;
- le lint de contrat connaît la clé.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from dsoxlab.infra import terraform
from dsoxlab.models.repo import RepoMetadata
from dsoxlab.validators.contract import KNOWN_META_KEYS

GABARITS = Path(terraform.__file__).resolve().parent.parent / "templates" / "terraform"


def _meta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, provider: str = "kvm",
          autostart: str | None = None) -> RepoMetadata:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("DSOXLAB_NO_UPDATE_CHECK", "1")
    monkeypatch.delenv("DSOXLAB_PROVIDER", raising=False)
    monkeypatch.setattr(terraform.libvirt, "efi_loader", lambda: "/OVMF.fd")
    repo = tmp_path / "repo"
    (repo / "ssh").mkdir(parents=True, exist_ok=True)
    ligne = f"  autostart: {autostart}\n" if autostart is not None else ""
    (repo / "meta.yml").write_text(
        "repo:\n  id: auto\n  category: demo\n"
        f"infra:\n  provider: {provider}\n  network: lab-auto\n  cidr: 10.10.61.0/24\n{ligne}"
        "  hosts:\n    - name: vm.lab\n",
        encoding="utf-8",
    )
    return RepoMetadata.from_yaml(repo / "meta.yml")


def _tfvars(meta: RepoMetadata) -> dict[str, object]:
    return json.loads(terraform.write_tfvars(meta).read_text(encoding="utf-8"))


def test_sans_la_cle_les_machines_ne_demarrent_pas_avec_l_hote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    meta = _meta(tmp_path, monkeypatch)
    assert meta.infra.autostart is False
    assert _tfvars(meta)["autostart"] is False


def test_le_booleen_true_active_bien_le_demarrage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    meta = _meta(tmp_path, monkeypatch, autostart="true")
    assert meta.infra.autostart is True
    assert _tfvars(meta)["autostart"] is True


@pytest.mark.parametrize("valeur", ['"true"', "1", "false", "oui", "''"])
def test_toute_autre_valeur_laisse_le_demarrage_coupe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, valeur: str
) -> None:
    """Se tromper dans ce sens coûte un `virsh start` ; dans l'autre, de la mémoire."""
    assert _meta(tmp_path, monkeypatch, autostart=valeur).infra.autostart is False


def test_incus_recoit_la_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _tfvars(_meta(tmp_path, monkeypatch, provider="incus", autostart="true"))["autostart"] is True


def test_outscale_ne_recoit_pas_la_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """outscale ne la déclare pas : la lui passer ferait échouer son plan."""
    assert "autostart" not in _tfvars(_meta(tmp_path, monkeypatch, provider="outscale"))


@pytest.mark.parametrize("provider", ["kvm", "incus"])
def test_le_template_declare_la_variable_a_false(provider: str) -> None:
    variables = (GABARITS / provider / "variables.tf").read_text(encoding="utf-8")
    bloc = re.search(r'variable "autostart" \{(.*?)\n\}', variables, re.DOTALL)
    assert bloc, provider
    assert re.search(r"type\s*=\s*bool", bloc.group(1)), provider
    assert re.search(r"default\s*=\s*false", bloc.group(1)), provider


def test_les_machines_lisent_la_variable_au_lieu_d_une_valeur_en_dur() -> None:
    kvm = (GABARITS / "kvm" / "main.tf").read_text(encoding="utf-8")
    domaine = kvm[kvm.index('resource "libvirt_domain" "host"'):]
    domaine = domaine[:domaine.index("\n}\n")]
    assert re.search(r"^\s*autostart\s*=\s*var\.autostart\s*$", domaine, re.MULTILINE)
    incus = (GABARITS / "incus" / "main.tf").read_text(encoding="utf-8")
    assert '"boot.autostart" = tostring(var.autostart)' in incus
    assert '"boot.autostart" = "true"' not in incus


def test_le_lint_de_contrat_connait_la_cle() -> None:
    assert "infra.autostart" in KNOWN_META_KEYS


# ── L'alignement par virsh d'une stack déjà montée ─────────────────────────
#
# Mesuré le 2026-11-16 : passer `autostart` de true à false sur un domaine EN
# MARCHE fait échouer l'apply (dmacvicar/libvirt 0.9.7). Le template le fige,
# et dsoxlab l'aligne après l'apply.


class _Res:
    def __init__(self, ok: bool, stderr: str = "") -> None:
        self.ok, self.stderr, self.stdout = ok, stderr, ""


def test_le_template_fige_autostart_dans_terraform() -> None:
    kvm = (GABARITS / "kvm" / "main.tf").read_text(encoding="utf-8")
    domaine = kvm[kvm.index('resource "libvirt_domain" "host"'):]
    domaine = domaine[:domaine.index("\n}\n")]
    assert re.search(r"lifecycle\s*\{\s*ignore_changes\s*=\s*\[autostart\]\s*\}", domaine)


@pytest.mark.parametrize(("valeur", "attendu"), [
    (None, ["autostart", "--disable", "vm.lab"]),
    ("true", ["autostart", "vm.lab"]),
])
def test_l_alignement_suit_le_meta_yml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, valeur: str | None, attendu: list[str]
) -> None:
    meta = _meta(tmp_path, monkeypatch, autostart=valeur)
    appels: list[list[str]] = []
    monkeypatch.setattr(terraform.libvirt, "list_domains", lambda: ["vm.lab", "autre.lab"])
    monkeypatch.setattr(terraform.libvirt, "run_virsh",
                        lambda args, check=True: appels.append(args) or _Res(True))
    assert terraform._aligner_autostart_kvm(meta) == []
    assert appels == [attendu]


def test_un_domaine_absent_n_est_pas_vise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    meta = _meta(tmp_path, monkeypatch)
    appels: list[list[str]] = []
    monkeypatch.setattr(terraform.libvirt, "list_domains", lambda: ["autre.lab"])
    monkeypatch.setattr(terraform.libvirt, "run_virsh",
                        lambda args, check=True: appels.append(args) or _Res(True))
    assert terraform._aligner_autostart_kvm(meta) == []
    assert appels == []


def test_un_refus_de_virsh_se_dit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _meta(tmp_path, monkeypatch)
    monkeypatch.setattr(terraform.libvirt, "list_domains", lambda: ["vm.lab"])
    monkeypatch.setattr(terraform.libvirt, "run_virsh",
                        lambda args, check=True: _Res(False, "permission denied"))
    avertissements = terraform._aligner_autostart_kvm(meta)
    assert len(avertissements) == 1
    assert "vm.lab" in avertissements[0] and "permission denied" in avertissements[0]


def test_hors_kvm_rien_n_est_aligne(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _meta(tmp_path, monkeypatch, provider="incus")

    def interdit(*_a: object, **_k: object) -> None:
        raise AssertionError("virsh ne doit pas être appelé hors kvm")

    monkeypatch.setattr(terraform.libvirt, "list_domains", interdit)
    assert terraform._aligner_autostart_kvm(meta) == []


def test_virsh_injoignable_se_dit_sans_nommer_de_machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dsoxlab.utils.shell import CommandError, CommandResult

    meta = _meta(tmp_path, monkeypatch)

    def injoignable() -> list[str]:
        raise CommandError(["virsh"], CommandResult(returncode=1, stdout="", stderr="introuvable"))

    monkeypatch.setattr(terraform.libvirt, "list_domains", injoignable)
    avertissements = terraform._aligner_autostart_kvm(meta)
    assert len(avertissements) == 1
    assert "virsh list --autostart" in avertissements[0]
    assert "*" not in avertissements[0]
