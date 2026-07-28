"""Garde-fous de typage du contrat déclaratif (lab.yaml, meta.yml).

Ces fichiers viennent d'un **dépôt fournisseur de labs** : ce sont les entrées
non fiables du moteur. ``discovery/scanner.py`` rattrape exactement
``(KeyError, ValueError, yaml.YAMLError)`` et ignore le lab fautif avec un
warning ; la CLI, elle, compose son message d'erreur depuis le ``ValueError``.

Toute autre exception (``AttributeError`` sur un ``.get`` appliqué à autre
chose qu'un mapping, ``TypeError`` sur ``int(None)`` ou ``list(42)``) échappe à
ce filet et remonte en traceback brut sur une commande sans rapport.

Ces helpers ramènent donc chaque champ mal typé dans le contrat. Ils sont
partagés par ``models/lab.py`` et ``models/repo.py`` : mêmes pièges, mêmes
garde-fous, une seule implémentation. Les cas couverts ont été trouvés par les
harnais de ``fuzz/``.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any


def as_int(value: object, default: int, field_name: str, source: Path) -> int:
    """Convertit un champ entier du contrat, défaut compris.

    ``data.get("vcpu", 1)`` rend ``None`` — et non ``1`` — quand la clé est
    présente mais vide (``vcpu:`` en blanc) : ``int(None)`` lèverait TypeError.
    C'est le cas le plus courant du contrat.

    ``bool`` est refusé explicitement : ``True`` est un ``int`` en Python, donc
    ``vcpu: true`` donnerait silencieusement 1 plutôt qu'une erreur.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(
            f"{source}: '{field_name}' doit être un entier (reçu un booléen : {value!r})."
        )
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            raise ValueError(
                f"{source}: '{field_name}' doit être un entier (reçu : {value!r})."
            ) from None
    raise ValueError(
        f"{source}: '{field_name}' doit être un entier (reçu : {type(value).__name__})."
    )


def as_str_list(value: object, field_name: str, source: Path) -> list[str]:
    """Valide qu'un champ est une liste, et la normalise en ``list[str]``.

    ``list(42)`` lèverait TypeError. Une str est refusée aussi : ``list("abc")``
    « réussirait » en donnant ``["a", "b", "c"]``, ce qui est pire qu'une erreur.
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ValueError(
            f"{source}: '{field_name}' doit être une liste "
            f"(reçu : {type(value).__name__})."
        )
    return [str(item) for item in value]


def as_mapping(value: object, field_name: str, source: Path, *, default_empty: bool = True) -> dict[str, Any]:
    """Valide qu'un champ est un mapping.

    Couvre ``runtime: vm`` écrit à la place du bloc ``runtime:``, la faute la
    plus naturelle du contrat.
    """
    if value is None and default_empty:
        return {}
    if not isinstance(value, dict):
        raise ValueError(
            f"{source}: '{field_name}' doit être un mapping "
            f"(reçu : {type(value).__name__})."
        )
    return value


def as_argv(value: object, field_name: str, source: Path) -> list[str]:
    """Valide UNE commande et la normalise en ``argv``.

    Mêmes écritures que :func:`as_argv_list`, au singulier : une chaîne
    découpée façon shell, ou une liste d'arguments.
    """
    if value is None:
        return []
    commandes = as_argv_list([value], field_name, source)
    return commandes[0] if commandes else []


def as_argv_list(value: object, field_name: str, source: Path) -> list[list[str]]:
    """Valide une liste de commandes et la normalise en liste d'``argv``.

    Deux écritures sont acceptées pour la même commande, parce que les deux se
    défendent dans un ``lab.yaml`` :

    - ``- vault kv put secret/x k=v`` — lisible, découpée à la manière du shell
      (``shlex``), donc les guillemets d'un argument à espaces sont respectés ;
    - ``- ["vault", "kv", "put", "secret/x", "k=v"]`` — explicite, sans découpage.

    Le résultat est toujours un ``argv``, exécuté sans shell : ni pipe, ni
    redirection, ni expansion. Une chaîne vide (ou qui ne contient que des
    espaces) est refusée plutôt qu'ignorée : ``docker exec`` sans commande
    échouerait plus loin, avec un message qui ne désignerait pas le lab fautif.
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ValueError(
            f"{source}: '{field_name}' doit être une liste de commandes "
            f"(reçu : {type(value).__name__})."
        )
    commandes: list[list[str]] = []
    for idx, item in enumerate(value):
        if isinstance(item, str):
            try:
                argv = shlex.split(item)
            except ValueError as exc:  # guillemet non fermé
                raise ValueError(
                    f"{source}: '{field_name}[{idx}]' n'est pas une commande "
                    f"analysable ({exc})."
                ) from None
        elif isinstance(item, (list, tuple)):
            argv = [str(mot) for mot in item]
        else:
            raise ValueError(
                f"{source}: '{field_name}[{idx}]' doit être une chaîne ou une "
                f"liste d'arguments (reçu : {type(item).__name__})."
            )
        if not argv:
            raise ValueError(
                f"{source}: '{field_name}[{idx}]' est une commande vide."
            )
        commandes.append(argv)
    return commandes


def as_mapping_list(value: object, field_name: str, source: Path) -> list[dict[str, Any]]:
    """Valide qu'un champ est une liste de mappings.

    ``hosts:`` écrit en mapping plutôt qu'en liste ferait porter l'itération sur
    les clés (des str), et ``h["name"]`` lèverait TypeError.
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ValueError(
            f"{source}: '{field_name}' doit être une liste de mappings "
            f"(reçu : {type(value).__name__})."
        )
    items: list[dict[str, Any]] = []
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(
                f"{source}: '{field_name}[{idx}]' doit être un mapping "
                f"(reçu : {type(item).__name__})."
            )
        items.append(item)
    return items
