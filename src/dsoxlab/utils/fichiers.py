"""Écrire un fichier d'état : d'un seul coup, ou pas du tout.

``Path.write_text`` tronque le fichier **avant** d'écrire. Entre les deux, il
n'existe plus rien de lisible : un Ctrl-C, un ``SIGKILL``, un disque plein ou
une machine qui s'éteint laissent un fichier vide ou coupé au milieu d'une
accolade. Sur les fichiers d'état de dsoxlab, ce moment coûte cher et ne se
signale jamais :

- ``<repo>/.dsoxlab-context.json`` tronqué, et ``read_context`` rend un contexte
  vide, par sécurité et sans un mot : l'apprenant perd sa section, sa target et
  son lab actif sans comprendre pourquoi ;
- un ``ssh_config`` coupé au milieu d'un bloc ``Host``, et ``ssh``, ``scp`` ou
  le ``conftest.py`` d'un dépôt de labs échouent sur une configuration
  incohérente au lieu d'une configuration absente ;
- un ``inventory.json`` tronqué, et c'est le catalogue de machines qui devient
  illisible.

La parade tient en une ligne de POSIX : écrire à côté, puis ``os.replace``, qui
est **atomique** sur le même système de fichiers. Le fichier de destination
n'existe qu'en version complète, ancienne ou nouvelle, jamais entre les deux.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def ecrire_atomiquement(chemin: Path, contenu: str, *, mode: int | None = None) -> None:
    """Écrit ``contenu`` dans ``chemin`` sans jamais laisser d'état intermédiaire.

    Le fichier temporaire est créé **dans le répertoire de destination** : c'est
    la condition pour que le ``os.replace`` reste atomique, puisqu'un
    déplacement entre systèmes de fichiers se dégrade en copie.

    ``mode`` est posé sur le temporaire avant le remplacement, pour qu'un
    fichier sensible ne soit jamais lisible, même une fraction de seconde.
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, brut = tempfile.mkstemp(
        dir=chemin.parent, prefix=f".{chemin.name}.", suffix=".tmp"
    )
    temporaire = Path(brut)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as flux:
            flux.write(contenu)
            flux.flush()
            # Sans ce fsync, le contenu peut n'être encore que dans le cache de
            # pages : le renommage serait atomique, mais une coupure de courant
            # laisserait un fichier renommé et vide.
            os.fsync(flux.fileno())
        if mode is not None:
            temporaire.chmod(mode)
        temporaire.replace(chemin)
    finally:
        # Sans effet après un remplacement réussi : le temporaire n'existe plus
        # sous ce nom. Sur un échec, il ne reste pas derrière.
        temporaire.unlink(missing_ok=True)
