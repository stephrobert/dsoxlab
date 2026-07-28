"""Tests du mécanisme de services conteneurisés (``runtime.services``).

Deux niveaux :

- **contrat + logique pure** : parsing de ``runtime.services`` et nommage des
  conteneurs, sans Docker ;
- **intégration** : démarrage/arrêt réel d'un conteneur, sauté si Docker est
  injoignable. L'image utilisée est ``hello-world`` (universelle, minuscule) ;
  le cas d'usage réel du dépôt (émulateur cloud) reste hors du code de dsoxlab,
  qui est agnostique.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dsoxlab.models.lab import LabDefinition
from dsoxlab.models.runtime import Service
from dsoxlab.runtimes import services as svc
from dsoxlab.utils.shell import run_command

CONTRACT_EXCEPTIONS = (KeyError, ValueError, yaml.YAMLError)

_BASE = """\
id: l1-demo
title: Demo lab
level: beginner
skills: [demo]
distros: [any]
doc_url: https://example.org/docs/demo/
"""


def _lab(tmp_path: Path, runtime_block: str) -> LabDefinition:
    path = tmp_path / "lab.yaml"
    path.write_text(_BASE + runtime_block, encoding="utf-8")
    return LabDefinition.from_yaml(path)


# ── Parsing du contrat ──────────────────────────────────────────────────────

def test_services_absent_donne_liste_vide(tmp_path: Path) -> None:
    lab = _lab(tmp_path, "runtime:\n  type: shell\n  workdir: challenge/work\n")
    assert lab.runtime.services == []


def test_service_complet_est_parse(tmp_path: Path) -> None:
    lab = _lab(tmp_path, """\
runtime:
  type: shell
  workdir: challenge/work
  services:
    - name: cloud
      image: some/image:1.0
      ports: ["4566:4566"]
      run_args: ["-u", "root"]
      env:
        DEBUG: "1"
      ready_tcp: 4566
      ready_timeout: 30
""")
    assert len(lab.runtime.services) == 1
    s = lab.runtime.services[0]
    assert s.name == "cloud"
    assert s.image == "some/image:1.0"
    assert s.ports == ["4566:4566"]
    assert s.run_args == ["-u", "root"]
    assert s.env == {"DEBUG": "1"}
    assert s.ready_tcp == 4566
    assert s.ready_timeout == 30


def test_service_defauts(tmp_path: Path) -> None:
    lab = _lab(tmp_path, """\
runtime:
  type: shell
  services:
    - name: db
      image: postgres:16
""")
    s = lab.runtime.services[0]
    assert s.ports == [] and s.run_args == [] and s.env == {}
    assert s.ready_tcp == 0 and s.ready_timeout == 90


@pytest.mark.parametrize("bad", [
    "runtime:\n  type: shell\n  services:\n    - image: x\n",          # name manquant
    "runtime:\n  type: shell\n  services:\n    - name: x\n",           # image manquante
    "runtime:\n  type: shell\n  services: not-a-list\n",               # services scalaire
    "runtime:\n  type: shell\n  services:\n    - name: x\n      image: y\n      ports: nope\n",  # ports scalaire
    # post_start scalaire : une seule commande écrite sans tiret. `list("vault…")`
    # « réussirait » en découpant caractère par caractère, d'où le refus explicite.
    "runtime:\n  type: shell\n  services:\n    - name: x\n      image: y\n      post_start: vault kv put a b\n",
    # commande vide : docker exec sans argv échouerait plus loin, sans nommer le lab.
    "runtime:\n  type: shell\n  services:\n    - name: x\n      image: y\n      post_start: ['']\n",
    # guillemet non fermé : shlex lève, on veut un ValueError du contrat.
    "runtime:\n  type: shell\n  services:\n    - name: x\n      image: y\n      post_start: ['vault kv put \"oops']\n",
    # entrée d'un type impossible à interpréter comme une commande.
    "runtime:\n  type: shell\n  services:\n    - name: x\n      image: y\n      post_start: [42]\n",
])
def test_service_malforme_reste_dans_le_contrat(tmp_path: Path, bad: str) -> None:
    with pytest.raises(CONTRACT_EXCEPTIONS):
        _lab(tmp_path, bad)


# ── ready_exec : la seule preuve de disponibilité ───────────────────────────

def test_ready_exec_accepte_chaine_ou_argv(tmp_path: Path) -> None:
    lab = _lab(tmp_path, """\
runtime:
  type: shell
  services:
    - name: vault
      image: some/vault:1.0
      ready_exec: vault status
    - name: db
      image: postgres:16
      ready_exec: ["pg_isready", "-q"]
""")
    assert lab.runtime.services[0].ready_exec == ["vault", "status"]
    assert lab.runtime.services[1].ready_exec == ["pg_isready", "-q"]


def test_ready_exec_absent_donne_liste_vide(tmp_path: Path) -> None:
    lab = _lab(tmp_path, "runtime:\n  type: shell\n  services:\n    - name: db\n      image: postgres:16\n")
    assert lab.runtime.services[0].ready_exec == []


def test_ready_exec_est_rejoue_jusqu_au_succes(monkeypatch: pytest.MonkeyPatch) -> None:
    """La sonde patiente : un service met du temps à répondre après le boot."""
    tentatives = {"n": 0}

    class _Res:
        def __init__(self, ok: bool) -> None:
            self.ok = ok
            self.stdout = ""
            self.stderr = ""

    def _fake(cmd: list[str], **kw: object) -> _Res:
        if cmd[:2] == ["docker", "exec"] and cmd[3:] == ["vault", "status"]:
            tentatives["n"] += 1
            return _Res(tentatives["n"] >= 3)  # prêt à la 3e sonde
        return _Res(True)

    monkeypatch.setattr(svc, "_is_running", lambda name: True)
    monkeypatch.setattr(svc, "run_command", _fake)
    monkeypatch.setattr(svc.time, "sleep", lambda s: None)

    service = Service(name="vault", image="x", ready_exec=["vault", "status"], ready_timeout=30)
    svc.start(service, "repo")

    assert tentatives["n"] == 3


def test_ready_exec_jamais_satisfaite_leve(monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout de la sonde : on lève, on ne lance pas post_start dans le vide."""
    class _Res:
        ok = False
        stdout = ""
        stderr = ""

    monkeypatch.setattr(svc, "_is_running", lambda name: True)
    monkeypatch.setattr(svc, "run_command", lambda cmd, **kw: _Res())
    monkeypatch.setattr(svc.time, "sleep", lambda s: None)

    # ready_timeout=0 : la deadline est atteinte dès le premier échec. Figer
    # `monotonic` à une constante rendrait au contraire la sortie de boucle
    # inatteignable, et le test tournerait indéfiniment — vécu à l'écriture.
    service = Service(name="vault", image="x", ready_exec=["vault", "status"], ready_timeout=0)
    with pytest.raises(svc.ServiceError) as exc:
        svc.start(service, "repo")
    assert "vault status" in str(exc.value)


def test_post_start_attend_ready_exec(monkeypatch: pytest.MonkeyPatch) -> None:
    """L'initialisation ne part qu'une fois la sonde satisfaite.

    C'est tout l'intérêt de ready_exec : sur un port publié, ready_tcp répond
    « prêt » immédiatement (le proxy Docker accepte avant que le service
    écoute), et post_start échouait alors sur un « connection refused » venu de
    l'intérieur du conteneur.
    """
    ordre: list[str] = []

    class _Res:
        def __init__(self, ok: bool = True) -> None:
            self.ok = ok
            self.stdout = ""
            self.stderr = ""

    sondes = {"n": 0}

    def _fake(cmd: list[str], **kw: object) -> _Res:
        if cmd[3:] == ["vault", "status"]:
            sondes["n"] += 1
            pret = sondes["n"] >= 2
            ordre.append(f"sonde{'-ok' if pret else '-ko'}")
            return _Res(pret)
        if cmd[:2] == ["docker", "exec"]:
            ordre.append("init")
        return _Res(True)

    monkeypatch.setattr(svc, "_is_running", lambda name: True)
    monkeypatch.setattr(svc, "run_command", _fake)
    monkeypatch.setattr(svc.time, "sleep", lambda s: None)

    service = Service(
        name="vault", image="x",
        ready_exec=["vault", "status"],
        post_start=[["vault", "kv", "put", "secret/lab", "k=v"]],
    )
    svc.start(service, "repo")

    assert ordre == ["sonde-ko", "sonde-ok", "init"]


# ── post_start : initialisation du service ──────────────────────────────────

def test_post_start_absent_donne_liste_vide(tmp_path: Path) -> None:
    lab = _lab(tmp_path, "runtime:\n  type: shell\n  services:\n    - name: db\n      image: postgres:16\n")
    assert lab.runtime.services[0].post_start == []


def test_post_start_accepte_les_deux_ecritures(tmp_path: Path) -> None:
    """Chaîne façon shell ou argv explicite : même résultat normalisé."""
    lab = _lab(tmp_path, """\
runtime:
  type: shell
  services:
    - name: vault
      image: some/vault:1.0
      post_start:
        - vault kv put secret/lab db_password=Pass api_key=xyz
        - ["vault", "policy", "write", "lab", "policies/lab.hcl"]
""")
    assert lab.runtime.services[0].post_start == [
        ["vault", "kv", "put", "secret/lab", "db_password=Pass", "api_key=xyz"],
        ["vault", "policy", "write", "lab", "policies/lab.hcl"],
    ]


def test_post_start_respecte_les_guillemets(tmp_path: Path) -> None:
    """Un argument à espaces reste UN argument : c'est shlex, pas un split()."""
    lab = _lab(tmp_path, """\
runtime:
  type: shell
  services:
    - name: db
      image: postgres:16
      post_start:
        - psql -c "CREATE DATABASE lab"
""")
    assert lab.runtime.services[0].post_start == [
        ["psql", "-c", "CREATE DATABASE lab"],
    ]


def test_post_start_joue_apres_le_demarrage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les commandes partent en `docker exec`, dans l'ordre, après le run."""
    appels: list[list[str]] = []

    class _Res:
        ok = True
        stdout = ""
        stderr = ""

    monkeypatch.setattr(svc, "_is_running", lambda name: False)
    monkeypatch.setattr(svc, "_exists", lambda name: False)
    monkeypatch.setattr(svc, "run_command",
                        lambda cmd, **kw: (appels.append(list(cmd)), _Res())[1])

    service = Service(
        name="vault", image="some/vault:1.0",
        post_start=[["vault", "kv", "put", "secret/lab", "k=v"], ["vault", "status"]],
    )
    svc.start(service, "ansible-training")

    execs = [c for c in appels if c[:2] == ["docker", "exec"]]
    assert execs == [
        ["docker", "exec", "dsoxlab-ansible-training-vault", "vault", "kv", "put", "secret/lab", "k=v"],
        ["docker", "exec", "dsoxlab-ansible-training-vault", "vault", "status"],
    ]
    # …et après le `docker run`, jamais avant : un service pas encore prêt
    # ferait échouer l'initialisation par intermittence.
    assert appels.index(["docker", "run", "-d", "--name", "dsoxlab-ansible-training-vault",
                         "some/vault:1.0"]) < appels.index(execs[0])


def test_ready_tcp_sonde_le_port_hote_pas_celui_du_conteneur(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un service remappé attend son port PUBLIÉ.

    Avec ``ports: ["8201:8200"]``, sonder 8200 reviendrait à interroger le 8200
    de l'hôte, c'est-à-dire un service étranger — qui répondrait « prêt » pour
    le mauvais serveur. Le cas n'est pas théorique : c'est exactement comme ça
    qu'un lab a dialogué avec le Vault d'une autre formation.
    """
    sondes: list[int] = []

    class _Res:
        ok = True
        stdout = ""
        stderr = ""

    monkeypatch.setattr(svc, "_is_running", lambda name: False)
    monkeypatch.setattr(svc, "_exists", lambda name: False)
    monkeypatch.setattr(svc, "run_command", lambda cmd, **kw: _Res())
    monkeypatch.setattr(svc, "_wait_tcp",
                        lambda port, timeout: (sondes.append(port), True)[1])

    service = Service(name="vault", image="x", ports=["8201:8200"], ready_tcp=8201)
    svc.start(service, "repo")

    assert sondes == [8201]


def test_post_start_rejoue_sur_conteneur_deja_debout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Conteneur réutilisé : l'initialisation repasse, pour un état de départ identique."""
    appels: list[list[str]] = []

    class _Res:
        ok = True
        stdout = ""
        stderr = ""

    monkeypatch.setattr(svc, "_is_running", lambda name: True)
    monkeypatch.setattr(svc, "run_command",
                        lambda cmd, **kw: (appels.append(list(cmd)), _Res())[1])

    service = Service(name="vault", image="x", post_start=[["init"]])
    svc.start(service, "repo")

    assert ["docker", "exec", "dsoxlab-repo-vault", "init"] in appels
    assert not [c for c in appels if c[:2] == ["docker", "run"]]  # pas de recréation


def test_post_start_en_echec_leve_service_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une initialisation ratée doit arrêter le lab, pas le laisser noter un 0."""
    class _Res:
        ok = False
        stdout = ""
        stderr = "permission denied on secret/lab"

    monkeypatch.setattr(svc, "_is_running", lambda name: True)
    monkeypatch.setattr(svc, "run_command", lambda cmd, **kw: _Res())

    service = Service(name="vault", image="x", post_start=[["vault", "kv", "put", "secret/lab"]])
    with pytest.raises(svc.ServiceError) as exc:
        svc.start(service, "repo")
    # Le message doit nommer la commande fautive ET la sortie du service : sans
    # elle, « l'initialisation a échoué » n'aide personne.
    assert "vault kv put secret/lab" in str(exc.value)
    assert "permission denied" in str(exc.value)


# ── Nommage des conteneurs ──────────────────────────────────────────────────

def test_container_name_namespace_par_repo(tmp_path: Path) -> None:
    s = Service(name="cloud", image="x")
    assert svc.container_name("terraform-training", s) == "dsoxlab-terraform-training-cloud"


def test_container_name_sanitize(tmp_path: Path) -> None:
    s = Service(name="my cloud!", image="x")
    # espaces et caractères interdits Docker remplacés par des tirets.
    assert svc.container_name("repo/id", s) == "dsoxlab-repo-id-my-cloud-"


# ── Intégration Docker (sautée si Docker injoignable) ───────────────────────

@pytest.mark.skipif(not svc.docker_available(), reason="Docker injoignable")
def test_start_status_stop_cycle() -> None:
    """Cycle réel start → status → stop sur une image universelle.

    hello-world sort immédiatement : on ne teste pas ``ready_tcp`` ici (pas de
    port), seulement que start crée le conteneur et que stop le retire.
    """
    s = Service(name="pytest-svc", image="hello-world")
    repo = "dsoxlab-test"
    try:
        svc.start(s, repo)
        st = svc.status(s, repo)
        assert st.container == svc.container_name(repo, s)
        assert st.detail in ("running", "stopped")  # hello-world s'arrête vite
    finally:
        assert svc.stop(s, repo) in (True, False)
        assert svc.status(s, repo).running is False


@pytest.mark.skipif(not svc.docker_available(), reason="Docker injoignable")
def test_post_start_execute_vraiment_dans_le_conteneur() -> None:
    """post_start contre un vrai Docker : la commande touche l'état du service.

    Les tests ci-dessus mockent ``run_command`` : ils prouvent l'orchestration
    (bon argv, bon ordre), pas que ``docker exec`` fasse quoi que ce soit. Ici
    l'initialisation écrit un fichier dans le conteneur, et on va le relire —
    vérifier la forme de la commande ne prouve pas son effet.

    nginx:alpine parce qu'elle reste debout sans qu'on lui passe de commande :
    le contrat ``services:`` déclare une image, pas un argv de conteneur.
    """
    s = Service(
        name="pytest-poststart",
        image="nginx:alpine",
        post_start=[["sh", "-c", "echo initialise > /preuve-post-start"]],
    )
    repo = "dsoxlab-test"
    try:
        name = svc.start(s, repo)
        lu = run_command(["docker", "exec", name, "cat", "/preuve-post-start"],
                         check=False, timeout=30)
        assert lu.ok, f"le fichier posé par post_start est illisible : {lu.stderr}"
        assert lu.stdout.strip() == "initialise"
    finally:
        svc.stop(s, repo)


@pytest.mark.skipif(not svc.docker_available(), reason="Docker injoignable")
def test_post_start_en_echec_reel_leve_service_error() -> None:
    """Une commande qui échoue dans le conteneur remonte en ServiceError."""
    s = Service(
        name="pytest-poststart-ko",
        image="nginx:alpine",
        post_start=[["sh", "-c", "exit 3"]],
    )
    repo = "dsoxlab-test"
    try:
        with pytest.raises(svc.ServiceError):
            svc.start(s, repo)
    finally:
        svc.stop(s, repo)
