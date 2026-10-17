"""Les collections Ansible : le défaut que le mainteneur ne pouvait pas voir.

Rapporté par deux utilisateurs (kubernetes-dsoxlab-training#94) : sur une
machine fraîche, **tous** les labs du catalogue kubernetes échouaient au `run`,
sur un `couldn't resolve module/action 'community.general.modprobe'`.
`ansible-core` ne fournit que `ansible.builtin` ; les collections ne sont pas
des paquets Python, et aucune installation ne les apporte.

Le mainteneur ne reproduisait pas : sa machine portait douze collections
accumulées au fil des années. C'est le cas d'école du défaut invisible chez
soi, et c'est précisément ce qu'un diagnostic doit dire à sa place.

Ces tests tiennent quatre promesses :

- ce qui est exigé se lit dans les playbooks que **dsoxlab joue lui-même**,
  jamais dans une liste écrite dans le code (l'agnosticisme) ;
- une collection manquante est nommée **avec le fichier qui l'appelle** ;
- `ansible-galaxy` muet ne conclut **ni** au vert **ni** au rouge ;
- un catalogue qui n'exige rien n'interroge pas `ansible-galaxy` du tout.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from dsoxlab.services import collections_ansible, doctor
from dsoxlab.utils.shell import CommandResult


def _ecrire(chemin: Path, contenu: str) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")


def _catalogue_kubernetes(racine: Path) -> None:
    """La forme réelle du catalogue kubernetes : un `shared/` joué par tous."""
    _ecrire(
        racine / "labs/cka/l1/setup.yaml",
        "- hosts: lab_target\n"
        "  tasks:\n"
        "    - name: Prepare the node\n"
        "      ansible.builtin.import_tasks: ../../../shared/noeud-kubernetes.yml\n",
    )
    _ecrire(
        racine / "shared/noeud-kubernetes.yml",
        "- name: Load the br_netfilter module\n"
        "  community.general.modprobe:\n"
        "    name: br_netfilter\n"
        "    state: present\n",
    )


def _galaxy(monkeypatch: pytest.MonkeyPatch, *, installees: list[str] | None) -> None:
    """Fait répondre `ansible-galaxy`, ou le fait taire si ``installees`` est None."""

    def faux_run(cmd: list[str], **kwargs: object) -> CommandResult:
        assert cmd[:2] == ["ansible-galaxy", "collection"]
        if installees is None:
            return CommandResult(returncode=127, stdout="", stderr="", failure="not_found")
        document = {
            "/home/x/.ansible/collections/ansible_collections": {
                nom: {"version": "1.0.0"} for nom in installees
            }
        }
        return CommandResult(returncode=0, stdout=json.dumps(document), stderr="")

    monkeypatch.setattr(collections_ansible, "run_command", faux_run)


def test_une_collection_manquante_est_nommee_avec_son_fichier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le défaut de l'issue #94, reproduit : exigée par `shared/`, absente."""
    _catalogue_kubernetes(tmp_path)
    _galaxy(monkeypatch, installees=["ansible.posix"])

    besoins = collections_ansible.mesurer(tmp_path)

    assert besoins.manquantes == ["community.general"]
    # Nommer le fichier est ce qui transforme « il manque quelque chose » en
    # « voilà où c'est appelé » : sans lui, l'utilisateur cherche à l'aveugle.
    assert besoins.exigees["community.general"] == "shared/noeud-kubernetes.yml"


def test_la_collection_installee_ne_manque_pas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le cas du mainteneur : la même mesure, et rien à signaler."""
    _catalogue_kubernetes(tmp_path)
    _galaxy(monkeypatch, installees=["community.general", "ansible.posix"])

    besoins = collections_ansible.mesurer(tmp_path)

    assert besoins.exigees == {"community.general": "shared/noeud-kubernetes.yml"}
    assert besoins.manquantes == []


def test_ansible_builtin_ne_s_exige_jamais(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Elle vient avec ansible-core et ne s'installe pas : l'exiger serait faux."""
    _ecrire(
        tmp_path / "labs/l1/setup.yaml",
        "- hosts: lab_target\n"
        "  tasks:\n"
        "    - name: Install a package\n"
        "      ansible.builtin.package:\n"
        "        name: vim\n",
    )
    appels: list[list[str]] = []
    monkeypatch.setattr(
        collections_ansible,
        "run_command",
        lambda cmd, **kw: appels.append(cmd)  # type: ignore[arg-type,return-value]
        or CommandResult(returncode=0, stdout="{}", stderr=""),
    )

    besoins = collections_ansible.mesurer(tmp_path)

    assert besoins.exigees == {}
    # Rien à vérifier, donc rien à demander : un diagnostic ne paie pas une
    # commande externe pour conclure ce qu'il sait déjà.
    assert appels == []


def test_galaxy_muet_ne_conclut_ni_au_vert_ni_au_rouge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La règle de fond du module : un contrôle qui n'a pas pu regarder se tait."""
    _catalogue_kubernetes(tmp_path)
    _galaxy(monkeypatch, installees=None)

    besoins = collections_ansible.mesurer(tmp_path)

    assert besoins.mesurable is False
    assert besoins.exigees  # ce qu'exige le catalogue reste su
    assert besoins.manquantes == []  # mais rien n'est accusé


def test_la_solution_d_un_lab_n_exige_rien(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ce que l'apprenant écrit est son travail, souvent le sujet même du lab."""
    _ecrire(
        tmp_path / "labs/l1/setup.yaml",
        "- hosts: lab_target\n  tasks: []\n",
    )
    _ecrire(
        tmp_path / "labs/l1/solution/playbook.yml",
        "- hosts: all\n"
        "  tasks:\n"
        "    - name: Mount the volume\n"
        "      ansible.posix.mount:\n"
        "        path: /data\n",
    )
    _galaxy(monkeypatch, installees=[])

    assert collections_ansible.mesurer(tmp_path).exigees == {}


def test_le_catalogue_sans_playbook_reste_vert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`terraform-training` : tous ses labs sont `shell`, aucun playbook joué."""
    _ecrire(tmp_path / "labs/l1/lab.yaml", "id: l1\n")
    _galaxy(monkeypatch, installees=[])

    besoins = collections_ansible.mesurer(tmp_path)

    assert besoins.exigees == {}
    assert besoins.manquantes == []


def test_le_plafond_borne_la_lecture(tmp_path: Path) -> None:
    """Un diagnostic ne doit pas s'allonger avec la taille du catalogue."""
    for i in range(5):
        _ecrire(tmp_path / f"labs/l{i}/setup.yaml", "- hosts: all\n")
    monkeypatche = pytest.MonkeyPatch()
    monkeypatche.setattr(collections_ansible, "_PLAFOND_DE_FICHIERS", 3)
    try:
        assert len(collections_ansible.playbooks_joues(tmp_path)) == 3
    finally:
        monkeypatche.undo()


def test_le_check_doctor_propose_la_commande_qui_repare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le rouge doit porter le geste, sinon il laisse l'utilisateur en plan."""
    _catalogue_kubernetes(tmp_path)
    _galaxy(monkeypatch, installees=[])

    check = doctor._check_collections(tmp_path)

    assert check.ok is False
    assert check.fix is not None
    assert check.fix.commands == (
        ("ansible-galaxy", "collection", "install", "community.general"),
    )
    assert "community.general" in check.detail
    assert "shared/noeud-kubernetes.yml" in check.detail


def test_le_requirements_du_catalogue_fait_autorite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La frontière entre les deux dépôts, tenue par un test.

    Le catalogue déclare ce qu'il exige, et il borne les versions ; dsoxlab
    mesure et répare. Réparer en installant le nom seul prendrait la dernière
    publiée : le catalogue kubernetes a validé ses labs en `community.general`
    11.4.7, deux majeures avant elle. Quand la déclaration existe, c'est elle
    qu'on joue.
    """
    _catalogue_kubernetes(tmp_path)
    _ecrire(
        tmp_path / "requirements.yml",
        "collections:\n"
        "  - name: community.general\n"
        '    version: ">=11.4.7,<12.0.0"\n',
    )
    _galaxy(monkeypatch, installees=[])

    check = doctor._check_collections(tmp_path)

    assert check.fix is not None
    assert check.fix.commands == (
        (
            "ansible-galaxy",
            "collection",
            "install",
            "-r",
            str(tmp_path / "requirements.yml"),
        ),
    )


def test_une_collection_declaree_mais_jamais_appelee_compte_aussi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le catalogue sait ce dont il a besoin mieux qu'un motif ne le devine.

    `ansible-training` déclare `community.hashi_vault` pour des lookups, que
    nul `module:` en tête de tâche ne révèle : la déclaration rattrape ce que
    la lecture des appels ne peut pas voir.
    """
    _ecrire(tmp_path / "labs/l1/setup.yaml", "- hosts: all\n  tasks: []\n")
    _ecrire(
        tmp_path / "requirements.yml",
        "collections:\n  - name: community.hashi_vault\n",
    )
    _galaxy(monkeypatch, installees=[])

    besoins = collections_ansible.mesurer(tmp_path)

    assert besoins.manquantes == ["community.hashi_vault"]
    assert besoins.exigees["community.hashi_vault"] == "requirements.yml"


def test_la_forme_courte_du_requirements_est_lue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`- community.general` sans `name:` est du Galaxy valide, et ça se voit
    dans `linux-dsoxlab-training`, qui écrit les deux formes."""
    _ecrire(tmp_path / "labs/l1/setup.yaml", "- hosts: all\n")
    _ecrire(
        tmp_path / "requirements.yml",
        "collections:\n  - ansible.posix\n  - name: community.crypto\n",
    )
    _galaxy(monkeypatch, installees=["ansible.posix"])

    assert collections_ansible.mesurer(tmp_path).manquantes == ["community.crypto"]


def test_un_requirements_illisible_ne_fait_pas_tomber_le_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un diagnostic qui lève sur un fichier mal formé ne diagnostique plus rien."""
    _catalogue_kubernetes(tmp_path)
    _ecrire(tmp_path / "requirements.yml", "collections: [oui\n  - non\n")
    _galaxy(monkeypatch, installees=[])

    besoins = collections_ansible.mesurer(tmp_path)

    # On retombe sur ce que les playbooks appellent, sans déclaration à jouer.
    assert besoins.manquantes == ["community.general"]
    assert besoins.declaration is None


def test_le_check_doctor_sort_en_unknown_quand_galaxy_se_tait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ni vert ni rouge : `--strict` a son propre code (10) pour ce cas."""
    _catalogue_kubernetes(tmp_path)
    _galaxy(monkeypatch, installees=None)

    check = doctor._check_collections(tmp_path)

    assert check.state == doctor.STATE_UNKNOWN
    assert check.fix is None


def test_le_check_doctor_est_vert_sans_rien_exiger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ecrire(tmp_path / "labs/l1/setup.yaml", "- hosts: all\n")
    _galaxy(monkeypatch, installees=[])

    check = doctor._check_collections(tmp_path)

    assert check.ok is True


def test_aucun_nom_de_collection_n_est_ecrit_dans_le_code() -> None:
    """L'invariant d'agnosticisme, tenu sur le fichier lui-même.

    Une liste de collections connues serait de la logique de domaine : c'est le
    catalogue qui dit ce qu'il exige, et lui seul. `ansible.builtin` est la
    seule exception, et elle est structurelle : elle vient avec ansible-core.

    Un commentaire ou une docstring peuvent nommer `community.general` : ils
    racontent le défaut rapporté, et un code sans son pourquoi se fait défaire
    au prochain passage. Ce qui est interdit, c'est qu'une **valeur** du
    programme porte un nom de collection : elle en ferait une connaissance de
    domaine, et le prochain catalogue en manquerait une.
    """
    source = Path(collections_ansible.__file__).read_text(encoding="utf-8")
    arbre = ast.parse(source)
    docstrings = {
        id(noeud.body[0].value)
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Module | ast.FunctionDef | ast.ClassDef)
        and noeud.body
        and isinstance(noeud.body[0], ast.Expr)
        and isinstance(noeud.body[0].value, ast.Constant)
    }
    valeurs = [
        noeud.value
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Constant)
        and isinstance(noeud.value, str)
        and id(noeud) not in docstrings
    ]
    for valeur in valeurs:
        ressemble = re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", valeur)
        # `requirements.yml` est un nom de fichier, pas une collection : c'est
        # la convention Ansible, et elle vaut pour tout catalogue.
        assert not ressemble or valeur == "requirements.yml", valeur
