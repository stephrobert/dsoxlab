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

Deux classes d'erreur, et un seul critère pour choisir
=====================================================

La question n'est pas de quel fichier vient le champ, mais **qui lit le
message** :

- un champ de ``meta.yml`` remonte jusqu'à ``cli.py``, qui l'affiche. Ces
  erreurs sont des :class:`ContractError` : elles portent une clé i18n et ses
  paramètres, et la CLI compose la phrase traduite ;
- un champ de ``lab.yaml`` est rattrapé par ``discovery/scanner.py``, qui
  écarte le lab et journalise la raison. Rien ne l'affiche : ce sont des
  :class:`LabYamlError`, dont le texte reste technique.

Les coercions partagées (:func:`as_int`, :func:`as_str_list`,
:func:`as_mapping`, :func:`as_mapping_list`) servent les deux fichiers, donc
elles lèvent la première. :func:`as_argv` et :func:`as_argv_list` ne servent
qu'à ``runtime.services`` d'un ``lab.yaml``, donc la seconde.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    """Un champ du contrat mal typé, dont le message **atteint l'utilisateur**.

    Même patron que :class:`~dsoxlab.models.schema_version.UnsupportedSchemaVersion`
    et :class:`~dsoxlab.models.repo.ProviderUnresolved` : l'exception porte des
    **données** (``source``, ``field``, ``key``, ``params``) et jamais une
    phrase. La CLI compose le message traduit ; traduire ici mettrait de la
    langue dans le modèle, c'est-à-dire graver le mauvais patron.

    Le chemin qui l'affiche : ``meta.yml`` → ``discovery/repo.py``, qui laisse
    remonter → ``cli.py: _read_repo()``, qui rend ``_(exc.key, **exc.params)``.

    Le ``str()``, lui, reste en jetons techniques : c'est ce que voit le
    journal, et deux rapports de bug doivent rester comparables quelle que soit
    la locale de qui les produit.
    """

    def __init__(self, source: Path, field: str, key: str, **params: Any) -> None:
        self.source = source
        self.field = field
        self.key = key
        #: ``field`` en fait partie : les messages le nomment presque tous, et
        #: ``str.format`` ignore sans broncher un paramètre qu'un texte n'emploie pas.
        self.params: dict[str, Any] = {"field": field, **params}
        detail = " ".join(f"{nom}={valeur!r}" for nom, valeur in params.items())
        super().__init__(f"{source}: {field}: {key} {detail}".rstrip())


class LabYamlError(ValueError):
    """Un ``lab.yaml`` illisible. Ce message **ne s'affiche jamais**.

    ``discovery/scanner.py`` est le seul appelant de
    ``LabDefinition.from_yaml`` : il rattrape ``(KeyError, ValueError,
    yaml.YAMLError)``, écarte le lab, et range la raison au journal et dans
    ``CatalogScan.illisibles``. Ni l'un ni l'autre n'est de l'interface, d'où
    un texte technique laissé tel quel : le traduire serait du travail perdu et
    du bruit dans les fichiers de traduction.

    La classe existe pour que ce fait soit **vérifiable** plutôt que promis. Le
    garde-fou i18n (``tests/test_i18n_coverage.py``) la connaît par son nom et
    laisse passer les phrases qu'elle porte. Le jour où l'un de ces messages
    devra s'afficher, il changera de classe pour :class:`ContractError`, et le
    garde-fou réclamera sa clé.
    """


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
        raise ContractError(source, field_name, "contract_field_not_int", got=repr(value))
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            raise ContractError(
                source, field_name, "contract_field_not_int", got=repr(value)
            ) from None
    raise ContractError(
        source, field_name, "contract_field_not_int", got=type(value).__name__
    )


def as_str_list(value: object, field_name: str, source: Path) -> list[str]:
    """Valide qu'un champ est une liste, et la normalise en ``list[str]``.

    ``list(42)`` lèverait TypeError. Une str est refusée aussi : ``list("abc")``
    « réussirait » en donnant ``["a", "b", "c"]``, ce qui est pire qu'une erreur.
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ContractError(
            source, field_name, "contract_field_not_list", got=type(value).__name__
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
        raise ContractError(
            source, field_name, "contract_field_not_mapping", got=type(value).__name__
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

    ``runtime.services`` n'existe que dans un ``lab.yaml`` : ces messages ne
    vont qu'au journal, d'où :class:`LabYamlError` et un texte non traduit.
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise LabYamlError(
            f"{source}: '{field_name}' doit être une liste de commandes "
            f"(reçu : {type(value).__name__})."
        )
    commandes: list[list[str]] = []
    for idx, item in enumerate(value):
        if isinstance(item, str):
            try:
                argv = shlex.split(item)
            except ValueError as exc:  # guillemet non fermé
                raise LabYamlError(
                    f"{source}: '{field_name}[{idx}]' n'est pas une commande "
                    f"analysable ({exc})."
                ) from None
        elif isinstance(item, (list, tuple)):
            argv = [str(mot) for mot in item]
        else:
            raise LabYamlError(
                f"{source}: '{field_name}[{idx}]' doit être une chaîne ou une "
                f"liste d'arguments (reçu : {type(item).__name__})."
            )
        if not argv:
            raise LabYamlError(
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
        raise ContractError(
            source, field_name, "contract_field_not_mapping_list",
            got=type(value).__name__,
        )
    items: list[dict[str, Any]] = []
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            # Le champ nommé porte son index : « infra.hosts[1] » désigne la
            # ligne fautive, là où « infra.hosts » enverrait relire toute la liste.
            raise ContractError(
                source, f"{field_name}[{idx}]", "contract_field_not_mapping",
                got=type(item).__name__,
            )
        items.append(item)
    return items
