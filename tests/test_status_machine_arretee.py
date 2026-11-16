"""Une machine arrêtée ne veut pas dire la même chose selon ``infra.autostart``.

Le défaut corrigé
=================

``infra status`` disait de toute machine arrêtée : « le template la démarre au
boot, elle a donc été arrêtée après coup (tueur de mémoire, crash qemu, arrêt
manuel) ». C'était vrai avant la 0.9.5, où chaque machine démarrait avec
l'hôte. Depuis, elle ne le fait que si le catalogue déclare
``infra.autostart: true`` ; sans ce réglage, une machine arrêtée après un
redémarrage de l'hôte est dans son état normal, et le message faisait chercher
un crash qui n'avait pas eu lieu. Relevé le 2026-11-16 sur k8s-kind.lab, arrêtée
à dessein.

Ces tests interrogent le modèle et la phrase choisie, jamais un rendu Rich.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab import i18n
from dsoxlab.i18n import _
from dsoxlab.models.repo import RepoMetadata
from dsoxlab.reporting.console import _cause_de
from dsoxlab.services import host_diagnosis as diag
from dsoxlab.services import infra_state_service
from dsoxlab.services.infra_state_service import EtatHote


@pytest.fixture(autouse=True)
def _anglais() -> None:
    i18n.set_lang("en")


def _meta(tmp_path: Path, autostart: str | None) -> RepoMetadata:
    ligne = f"  autostart: {autostart}\n" if autostart is not None else ""
    chemin = tmp_path / "meta.yml"
    chemin.write_text(
        "repo:\n  id: demo\ninfra:\n  provider: kvm\n  network: lab-demo\n"
        "  cidr: 10.10.30.0/24\n" + ligne + "  hosts:\n    - name: web1.lab\n",
        encoding="utf-8",
    )
    return RepoMetadata.from_yaml(chemin)


@pytest.mark.parametrize(
    ("declare", "attendu"),
    [(None, False), ("false", False), ("true", True), ('"true"', False)],
)
def test_l_etat_porte_l_autostart_du_catalogue(
    tmp_path: Path, declare: str | None, attendu: bool
) -> None:
    """``mesurer`` recopie ``infra.autostart`` ; la chaîne "true" ne suffit pas."""
    etat = infra_state_service.mesurer(
        _meta(tmp_path, declare),
        {"web1.lab": {"ansible_host": "10.10.30.11"}},
        tmp_path / "cle",
        provider=None,
        sonde=lambda commande: (True, None),
    )

    assert etat.autostart is attendu


def _arretee() -> EtatHote:
    return EtatHote(
        fqdn="web1.lab",
        ip="10.10.30.11",
        joignable=False,
        raison="Connection timed out",
        domaine="web1.lab",
        etat_domaine="shut off",
        cause=diag.CAUSE_DOMAIN_NOT_RUNNING,
    )


def test_sans_autostart_une_machine_arretee_n_est_pas_un_crash() -> None:
    phrase = _cause_de(_arretee(), autostart=False)

    assert phrase == _("status_cause_domain_stopped", domain="web1.lab", state="shut off")
    assert phrase != _("status_cause_domain_not_running", domain="web1.lab", state="shut off")


def test_avec_autostart_une_machine_arretee_reste_suspecte() -> None:
    phrase = _cause_de(_arretee(), autostart=True)

    assert phrase == _("status_cause_domain_not_running", domain="web1.lab", state="shut off")


def test_par_defaut_la_phrase_ne_suppose_pas_l_autostart() -> None:
    """Un appelant qui n'a pas l'information ne retombe pas sur la piste du crash."""
    assert _cause_de(_arretee()) == _(
        "status_cause_domain_stopped", domain="web1.lab", state="shut off"
    )


@pytest.mark.parametrize("langue", ["en", "fr"])
def test_la_nouvelle_phrase_existe_dans_les_deux_langues(langue: str) -> None:
    i18n.set_lang(langue)

    phrase = _("status_cause_domain_stopped", domain="web1.lab", state="shut off")

    assert "status_cause_domain_stopped" not in phrase
    assert "virsh start web1.lab" in phrase
    assert "infra.autostart" in phrase
