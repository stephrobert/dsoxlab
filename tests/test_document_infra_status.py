"""La forme du document ``infra status --json``, avant d'y toucher.

Un test couvrait déjà son contenu le plus riche
(``test_status_json_porte_l_etat_de_chaque_domaine`` dans
``test_etat_libvirt.py``) : l'état des domaines, la cause par hôte et le bloc
``hypervisor``. Il ne couvrait ni ``provider``, ni ``summary``, ni les codes de
sortie, ni le cas d'un catalogue sans infrastructure.

Or ce document est lu par des scripts : il dit si une infrastructure est
utilisable, et c'est sur lui qu'un pipeline décide de continuer ou d'attendre.
Ces tests le caractérisent **avant** l'extraction du service, pour que le
refactoring se vérifie au lieu de se supposer.

Rien ici n'a besoin d'une infrastructure : le ``ssh`` et l'hyperviseur sont
simulés, comme dans ``test_etat_libvirt.py`` dont les fixtures sont reprises.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dsoxlab import i18n
from dsoxlab.cli import app
from dsoxlab.infra import inventory, libvirt

runner = CliRunner()

META_AVEC_HOTES = """\
repo:
  id: demo
  category: demo
infra:
  provider: kvm
  network: lab-demo
  cidr: 10.10.30.0/24
  hosts:
    - name: web1.lab
    - name: db1.lab
"""

META_SANS_HOTE = "repo:\n  id: demo\n  category: demo\n"


@pytest.fixture(autouse=True)
def _poste_isole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ces commandes écrivent un fragment SSH et lisent un state.

    Aucun test n'a le droit de toucher au poste qui le joue, d'où le ``HOME``
    et le ``XDG_STATE_HOME`` déviés.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("DSOXLAB_NO_UPDATE_CHECK", "1")
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    monkeypatch.delenv("DSOXLAB_PROVIDER", raising=False)
    monkeypatch.setattr(i18n, "_strings", i18n._load("en"))
    (tmp_path / "home" / ".ssh" / "config.d").mkdir(parents=True)


def _depot(tmp_path: Path, meta: str) -> Path:
    repo = tmp_path / "repo"
    (repo / "ssh").mkdir(parents=True, exist_ok=True)
    (repo / "ssh" / "id_ed25519").write_text("clé factice", encoding="utf-8")
    (repo / "meta.yml").write_text(meta, encoding="utf-8")
    return repo


@pytest.fixture
def depot(tmp_path: Path) -> Path:
    return _depot(tmp_path, META_AVEC_HOTES)


@pytest.fixture
def adresses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les adresses que Terraform aurait publiées, sans lancer Terraform."""
    monkeypatch.setattr(
        inventory,
        "read_terraform_outputs",
        lambda repo_meta: {
            "hosts": {"value": {"web1.lab": "10.10.30.11", "db1.lab": "10.10.30.12"}}
        },
    )


@pytest.fixture
def ssh(monkeypatch: pytest.MonkeyPatch) -> Callable[[bool, str], None]:
    """Le ``ssh`` de la commande, rendu prévisible.

    L'échec de ce ``ssh`` **est** la mesure : un hôte injoignable est un
    résultat à rapporter, donc on le simule plutôt que de l'éviter.
    """

    def regler(joignable: bool, raison: str = "No route to host") -> None:
        def faux(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[bytes]:
            if joignable:
                return subprocess.CompletedProcess(["ssh"], 0, b"", b"")
            return subprocess.CompletedProcess(
                ["ssh"], 255, b"", f"ssh: connect to host: {raison}\n".encode()
            )

        monkeypatch.setattr(subprocess, "run", faux)

    return regler


@pytest.fixture(autouse=True)
def _hyperviseur_muet(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Par défaut, l'hyperviseur ne répond pas.

    C'est le cas le plus fréquent sur un poste qui n'a pas provisionné, et
    « je n'ai pas pu regarder » ne doit jamais devenir « rien n'existe ».
    """
    monkeypatch.setattr(libvirt, "supports_domain_state", lambda _p: False)
    yield


def _document(depot: Path) -> tuple[dict[str, Any], int]:
    resultat = runner.invoke(
        app, ["infra", "status", "--json", "--lab-home", str(depot)]
    )
    return json.loads(resultat.stdout), resultat.exit_code


class TestUnCatalogueSansInfrastructure:
    """Un catalogue 100 % shell est un cas normal, pas une erreur."""

    def test_le_document_existe_quand_meme(self, tmp_path: Path) -> None:
        """Une phrase Rich et un code 0 laissaient l'appelant sans rien à lire."""
        document, code = _document(_depot(tmp_path, META_SANS_HOTE))

        assert code == 0
        assert document["provider"] is None
        assert document["hosts"] == []
        assert document["summary"] == {"reachable": 0, "total": 0}


class TestUnCatalogueProvisionne:
    def test_tous_les_hotes_joignables_rendent_zero(
        self, depot: Path, adresses: None, ssh: Callable[..., None]
    ) -> None:
        ssh(True)
        document, code = _document(depot)

        assert code == 0
        assert document["provider"] == "kvm"
        assert document["summary"] == {"reachable": 2, "total": 2}
        assert {h["fqdn"] for h in document["hosts"]} == {"web1.lab", "db1.lab"}
        assert all(h["reachable"] for h in document["hosts"])

    def test_un_hote_injoignable_rend_un(
        self, depot: Path, adresses: None, ssh: Callable[..., None]
    ) -> None:
        """Le code de retour est ce sur quoi un pipeline décide d'attendre."""
        ssh(False)
        document, code = _document(depot)

        assert code == 1
        assert document["summary"] == {"reachable": 0, "total": 2}
        assert all(not h["reachable"] for h in document["hosts"])

    def test_chaque_hote_porte_les_memes_champs(
        self, depot: Path, adresses: None, ssh: Callable[..., None]
    ) -> None:
        """Un champ qui disparaît casse un appelant sans un mot."""
        ssh(False)
        document, _code = _document(depot)

        attendus = {
            "fqdn",
            "ip",
            "reachable",
            "reason",
            "domain",
            "domain_state",
            "cause",
        }
        for hote in document["hosts"]:
            assert set(hote) == attendus

    def test_la_raison_de_lechec_est_reprise_de_ssh(
        self, depot: Path, adresses: None, ssh: Callable[..., None]
    ) -> None:
        ssh(False, "Connection refused")
        document, _code = _document(depot)

        assert all("Connection refused" in h["reason"] for h in document["hosts"])

    def test_un_hote_joignable_na_pas_de_raison(
        self, depot: Path, adresses: None, ssh: Callable[..., None]
    ) -> None:
        ssh(True)
        document, _code = _document(depot)

        assert all(h["reason"] is None for h in document["hosts"])

    def test_les_hotes_sont_rendus_dans_un_ordre_stable(
        self, depot: Path, adresses: None, ssh: Callable[..., None]
    ) -> None:
        """Un ordre qui change d'un appel à l'autre rend tout diff illisible."""
        ssh(True)
        premier, _ = _document(depot)
        second, _ = _document(depot)

        assert [h["fqdn"] for h in premier["hosts"]] == [
            h["fqdn"] for h in second["hosts"]
        ]
        assert [h["fqdn"] for h in premier["hosts"]] == sorted(
            h["fqdn"] for h in premier["hosts"]
        )


class TestLHyperviseurQuiNeRepondPas:
    def test_le_bloc_hypervisor_distingue_labsence_de_lignorance(
        self, depot: Path, adresses: None, ssh: Callable[..., None]
    ) -> None:
        """Sans ce bloc, « aucun domaine » et « rien n'a répondu » se
        ressembleraient tous deux à des ``domain_state: null``."""
        ssh(False)
        document, _code = _document(depot)

        assert document["hypervisor"]["queryable"] is False
        assert all(h["domain_state"] is None for h in document["hosts"])
