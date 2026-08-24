"""Réglages communs à toute la suite unitaire.

Un test unitaire ne doit mesurer que le code, jamais la machine qui l'exécute ni
le réseau du moment. `test_doctor.py` porte déjà cette règle pour terraform,
ansible et les prérequis matériels — « sans cela, ces tests mesurent la machine
qui les exécute : ils passaient en local et échouaient sur un runner CI ».

Le contrôle d'accès sortant ajouté en 0.1.81 a rouvert la brèche, et plus
largement : il ouvrait de **vraies connexions**. Six fichiers de tests
appelaient `collect_checks` sans le savoir, chacun payant jusqu'à trois délais
d'attente et rendant un verdict différent selon que le réseau répondait ou non.
Les mêmes tests passaient sur un runner GitHub et échouaient derrière un
pare-feu — c'est-à-dire qu'ils ne mesuraient plus ce qu'ils prétendaient.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _aucun_acces_reseau(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise l'unique sonde réseau de `doctor`, pour toute la suite.

    On neutralise `_joignable`, pas `socket.create_connection` : ce dernier sert
    aussi à `runtimes/services.py` pour attendre qu'un conteneur écoute, et le
    rendre toujours vrai ferait passer des tests de services qui ne prouveraient
    plus rien.

    Un test qui veut éprouver le contrôle lui-même repatche `_joignable` par
    dessus — c'est ce que fait `test_cloud_init_degrade.py`, et le monkeypatch
    le plus récent l'emporte.
    """
    from dsoxlab.services import doctor

    monkeypatch.setattr(doctor, "_joignable", lambda hote: True)
