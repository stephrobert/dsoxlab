"""L'accès sortant vers les miroirs d'images que les templates citent.

Extrait de ``services/doctor.py`` (issue #199), sans changement de
comportement. Voir ce module pour les principes du diagnostic.
"""

from __future__ import annotations

import re
import socket
from pathlib import Path

from ...i18n import _
from .modele import STATE_UNKNOWN, Check, _check, _doctor

#: Les URL d'images des templates packagés. Le moteur ne **connaît** aucun
#: domaine : il les lit dans les templates, comme il lit le reste du contrat.
_URL_IMAGE = re.compile(r'https://([A-Za-z0-9.-]+)/[^"\s]*\.(?:qcow2|img)')

#: Une sonde d'accès sortant doit être brève : `doctor` en enchaîne déjà
#: plusieurs, et un réseau coupé se constate en deux secondes.
_DELAI_EGRESS = 2.0


def _hotes_images() -> list[str]:
    """Les hôtes que le provisionnement ira chercher, lus dans les templates."""
    racine = Path(__file__).resolve().parents[2] / "templates" / "terraform"
    hotes: list[str] = []
    for chemin in sorted(racine.rglob("*.tf")):
        try:
            contenu = chemin.read_text(encoding="utf-8")
        except OSError:
            continue
        for hote in _URL_IMAGE.findall(contenu):
            if hote not in hotes:
                hotes.append(hote)
    return hotes


def _joignable(hote: str) -> bool:
    """Une connexion sortante vers cet hôte aboutit-elle ?

    Isolée en fonction parce que c'est le seul appel **réseau** de tout
    `collect_checks`. Les tests la neutralisent d'un coup (`tests/conftest.py`),
    faute de quoi chaque test de classement ouvrirait de vraies connexions :
    lentes, dépendantes du réseau du moment, et fausses dès qu'une CI est
    fermée. C'est le défaut que la fixture voisine corrigeait déjà pour
    terraform et ansible — « ces tests mesurent la machine qui les exécute ».

    Patcher ``socket`` globalement ne convenait pas : ``runtimes/services.py``
    s'en sert pour attendre un conteneur, et le neutraliser rendrait cette
    attente-là toujours vraie.
    """
    try:
        with socket.create_connection((hote, 443), timeout=_DELAI_EGRESS):
            return True
    except OSError:
        return False


def _check_egress() -> Check:
    """Le provisionnement télécharge une image, puis cloud-init des paquets.

    Sans accès sortant — salle de formation fermée, proxy d'entreprise — le
    téléchargement échoue ou cloud-init finit en `degraded`, et les labs
    échouent plus tard sur des commandes absentes. Le dire **avant** de
    provisionner coûte deux secondes et évite de chercher la panne au mauvais
    endroit.

    Un seul hôte joignable suffit à conclure : ce qui est en cause est l'accès
    sortant lui-même, pas la disponibilité d'un miroir en particulier.
    """
    hotes = _hotes_images()
    if not hotes:
        # Aucun template ne déclare d'image : rien à joindre, rien à conclure.
        return _check("egress", False, _("detail_egress_indetermine"),
                      forced_state=STATE_UNKNOWN)
    for hote in hotes:
        if _doctor()._joignable(hote):
            return _check("egress", True, hote)
    return _check("egress", False,
                  _("detail_egress_absent", hosts=", ".join(hotes)),
                  hint="https://docs.docker.com/network/proxy/")
