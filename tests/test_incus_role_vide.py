"""Le template Incus ne pose `user.lab.role` que si le rôle a une valeur.

Incus efface une clé de config vide. Le provider relit alors l'instance, ne
retrouve pas la clé qu'il vient d'envoyer, et échoue sur « Provider produced
inconsistent result after apply: element "user.lab.role" has vanished ».
L'instance reste marquée à recréer : chaque `provision` suivant la détruit et
la refait. Mesuré sur Incus 7.2 le 2026-11-14, avec un hôte sans `role` (le
champ est optionnel dans le contrat).
"""

from __future__ import annotations

import re
from pathlib import Path

import dsoxlab

TEMPLATE = Path(dsoxlab.__file__).parent / "templates" / "terraform" / "incus" / "main.tf"


def test_le_role_n_est_pose_que_s_il_a_une_valeur() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")
    poses = [ligne.strip() for ligne in source.splitlines()
             if '"user.lab.role"' in ligne and not ligne.strip().startswith("#")]
    assert poses, "le template Incus ne pose plus du tout user.lab.role"
    for ligne in poses:
        assert re.search(r'each\.value\.role\s*!=\s*""\s*\?', ligne), (
            f"user.lab.role est posé sans condition : {ligne!r}. Un rôle vide fait échouer l'apply."
        )
