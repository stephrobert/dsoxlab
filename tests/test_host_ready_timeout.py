"""Résolution du délai d'attente des hôtes après un provision.

Le délai était figé à 180 s. Sur un poste modeste, le démarrage simultané de
plusieurs VMs sature le CPU : un rapport d'usage a mesuré un hôte prêt à 181 s,
soit une seconde après l'abandon. Le matériel de l'apprenant n'est pas une
propriété du dépôt de labs, donc le réglage est une variable d'environnement et
non une clé du ``meta.yml``.

Ce qui est prouvé ici : la précédence (argument > variable > défaut), et le fait
qu'une variable mal écrite ne fasse **jamais** échouer un provision.
"""

from __future__ import annotations

import pytest

from dsoxlab.infra.inventory import (
    HOST_READY_TIMEOUT_DEFAULT,
    HOST_READY_TIMEOUT_ENV,
    _host_ready_timeout,
)


def test_defaut_sans_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(HOST_READY_TIMEOUT_ENV, raising=False)
    assert _host_ready_timeout(None) == HOST_READY_TIMEOUT_DEFAULT


def test_la_variable_est_lue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HOST_READY_TIMEOUT_ENV, "360")
    assert _host_ready_timeout(None) == 360.0


def test_la_variable_accepte_un_flottant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HOST_READY_TIMEOUT_ENV, "90.5")
    assert _host_ready_timeout(None) == 90.5


def test_les_espaces_sont_tolerees(monkeypatch: pytest.MonkeyPatch) -> None:
    """`export VAR=" 300 "` ne doit pas retomber silencieusement sur le défaut."""
    monkeypatch.setenv(HOST_READY_TIMEOUT_ENV, "  300  ")
    assert _host_ready_timeout(None) == 300.0


def test_l_argument_explicite_prime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un appelant qui impose un délai garde la main sur l'environnement."""
    monkeypatch.setenv(HOST_READY_TIMEOUT_ENV, "360")
    assert _host_ready_timeout(42.0) == 42.0


@pytest.mark.parametrize("valeur", ["", "   ", "abc", "5m", "0", "-30", "nan-ish"])
def test_une_valeur_invalide_retombe_sur_le_defaut(
    monkeypatch: pytest.MonkeyPatch, valeur: str
) -> None:
    """Une variable mal écrite ne doit pas casser le provision.

    Lever ici serait pire que le mal : l'apprenant qui tape ``=5m`` verrait son
    provisionnement échouer à cause du réglage censé le sauver.
    """
    monkeypatch.setenv(HOST_READY_TIMEOUT_ENV, valeur)
    assert _host_ready_timeout(None) == HOST_READY_TIMEOUT_DEFAULT
