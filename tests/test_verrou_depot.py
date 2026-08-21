"""Le verrou d'écriture par dépôt : ce qu'il refuse, et ce qu'il ne bloque pas.

Le défaut d'origine (issue #81) n'était pas une course rare : deux terminaux
ouverts sur le même dépôt, c'est le cas normal chez un apprenant. Les deux
invocations écrivaient sur le même `.dsoxlab-context.json`, le même state
Terraform, les mêmes conteneurs, et la dernière écriture gagnait sans que la
première le sache.

Ce module prouve quatre choses, et la troisième est celle qui coûte cher à
rater : un verrou qui ne se rend jamais est pire que pas de verrou du tout.

1. Une seconde invocation qui écrit est **refusée**, en nommant la commande
   détentrice et son PID, avec un code de sortie qui lui est propre.
2. Les commandes de **lecture** ne sont pas bloquées.
3. Un verrou laissé par un processus **mort** (tué au ``SIGKILL``, ou perdu
   dans un redémarrage) est repris sans qu'aucun fichier soit à supprimer.
4. ``run`` **rend** le verrou avant d'ouvrir la session interactive, sinon le
   ``dsoxlab check`` que l'apprenant y tape se heurterait à sa propre session.

Tout est réel : de vrais ``flock``, un vrai processus fils tué au ``SIGKILL``,
la vraie CLI. Rien n'est simulé ici.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app
from dsoxlab.locking import EXIT_LOCKED, RepoLock, RepoLocked, lock_identity, lock_path

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(sortie: str) -> str:
    """La sortie telle qu'elle est lue à l'écran, sans les codes de style."""
    return _ANSI.sub("", sortie)


@pytest.fixture(autouse=True)
def _etat_isole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aucun test ne touche au ``~/.local/state`` de la machine."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("LAB_HOME", raising=False)


def _depot(racine: Path, repo_id: str = "verrou-demo") -> Path:
    """Un dépôt de labs minimal mais réel : un meta.yml et un lab shell."""
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "meta.yml").write_text(
        f"repo:\n  id: {repo_id}\n  category: demo\n", encoding="utf-8"
    )
    lab = racine / "labs" / "demo" / "premier"
    lab.mkdir(parents=True)
    (lab / "lab.yaml").write_text(
        "id: premier\n"
        "title: Premier\n"
        "level: l1\n"
        "skills: [rien]\n"
        "distros: [alma10]\n"
        "doc_url: https://example.test/doc\n"
        "runtime:\n"
        "  type: shell\n"
        "  workdir: challenge/work\n",
        encoding="utf-8",
    )
    return racine


# ── Où le verrou se pose ──────────────────────────────────────────────────────


def test_le_verrou_vit_dans_letat_du_depot(tmp_path: Path) -> None:
    """Sous ``<XDG_STATE_HOME>/dsoxlab/<repo.id>/``, là où vit le state Terraform."""
    racine = _depot(tmp_path / "depot")

    chemin = lock_path(racine)

    assert lock_identity(racine) == "verrou-demo"
    assert chemin == tmp_path / "state" / "dsoxlab" / "verrou-demo" / "dsoxlab.lock"


def test_deux_clones_du_meme_catalogue_partagent_le_verrou(tmp_path: Path) -> None:
    """Même ``repo.id``, donc même work-dir Terraform, donc même verrou.

    Les sérialiser inutilement ne coûte rien ; les laisser écrire ensemble sur
    le même state coûte un state corrompu.
    """
    un = _depot(tmp_path / "clone-a", repo_id="meme-catalogue")
    deux = _depot(tmp_path / "clone-b", repo_id="meme-catalogue")

    assert lock_path(un) == lock_path(deux)


def test_sans_meta_yml_lidentite_derive_du_chemin(tmp_path: Path) -> None:
    """Un répertoire sans contrat reste verrouillable, et distinctement."""
    (tmp_path / "sans-contrat-a").mkdir()
    (tmp_path / "sans-contrat-b").mkdir()

    a = lock_identity(tmp_path / "sans-contrat-a")
    b = lock_identity(tmp_path / "sans-contrat-b")

    assert a.startswith("sans-contrat-a-")
    assert a != b
    assert a == lock_identity(tmp_path / "sans-contrat-a"), "l'identité est stable"


# ── Ce que le verrou refuse ───────────────────────────────────────────────────


def test_une_seconde_prise_est_refusee_et_nomme_le_detenteur(tmp_path: Path) -> None:
    racine = _depot(tmp_path / "depot")
    premier = RepoLock(racine, "provision")
    premier.acquire()

    try:
        with pytest.raises(RepoLocked) as capture:
            RepoLock(racine, "destroy").acquire()
    finally:
        premier.release()

    detenteur = capture.value.holder
    assert detenteur is not None, "le refus doit dire QUI tient le verrou"
    assert detenteur.command == "provision"
    assert detenteur.pid == os.getpid()
    assert detenteur.age_seconds >= 0


def test_apres_relachement_le_verrou_se_reprend(tmp_path: Path) -> None:
    racine = _depot(tmp_path / "depot")
    premier = RepoLock(racine, "provision")
    premier.acquire()
    premier.release()

    second = RepoLock(racine, "destroy")
    second.acquire()
    try:
        assert second.held
    finally:
        second.release()


def test_relacher_efface_la_trace_du_detenteur(tmp_path: Path) -> None:
    """Le fichier survit, son contenu non : sinon il accuserait un mort."""
    racine = _depot(tmp_path / "depot")
    verrou = RepoLock(racine, "provision")
    verrou.acquire()
    assert lock_path(racine).read_text(encoding="utf-8").strip()

    verrou.release()

    assert lock_path(racine).is_file(), "le fichier ne se supprime jamais"
    assert lock_path(racine).read_text(encoding="utf-8") == ""


# ── Le verrou périmé, la question qui décide de tout ─────────────────────────


_ENFANT = """\
import os
import sys
import time
from pathlib import Path

os.environ["XDG_STATE_HOME"] = sys.argv[1]

from dsoxlab.locking import RepoLock

verrou = RepoLock(Path(sys.argv[2]), "provision")
verrou.acquire()
Path(sys.argv[3]).write_text(str(os.getpid()), encoding="utf-8")
time.sleep(300)
"""


def test_un_verrou_tenu_par_un_processus_tue_est_repris(tmp_path: Path) -> None:
    """SIGKILL sur le détenteur : le noyau rend le verrou, personne n'efface rien.

    C'est le cas qui rend un verrou par fichier-sentinelle dangereux, et celui
    que ``flock`` règle sans code : le verrou est attaché au descripteur, que
    le noyau referme quoi qu'il arrive au processus.
    """
    racine = _depot(tmp_path / "depot")
    script = tmp_path / "detenteur.py"
    script.write_text(_ENFANT, encoding="utf-8")
    temoin = tmp_path / "pid.txt"

    enfant = subprocess.Popen(
        [sys.executable, str(script), str(tmp_path / "state"), str(racine), str(temoin)],
    )
    try:
        limite = time.monotonic() + 30
        while not temoin.is_file() and time.monotonic() < limite:
            time.sleep(0.05)
        assert temoin.is_file(), "l'enfant n'a jamais pris le verrou"

        # Tant qu'il vit, il tient : c'est ce qui prouve que le test qui suit
        # mesure bien la mort de l'enfant, et pas un verrou qui n'a jamais pris.
        with pytest.raises(RepoLocked):
            RepoLock(racine, "run").acquire()

        enfant.send_signal(signal.SIGKILL)
        enfant.wait(timeout=30)
    finally:
        if enfant.poll() is None:  # pragma: no cover : filet du harnais
            enfant.kill()
            enfant.wait(timeout=10)

    repris = RepoLock(racine, "run")
    repris.acquire()  # ne doit pas lever
    try:
        assert repris.held
    finally:
        repris.release()


def test_un_verrou_survivant_a_un_redemarrage_ne_bloque_rien(tmp_path: Path) -> None:
    """Le fichier survit au redémarrage, le ``flock`` non.

    On rejoue exactement ce que la machine laisse au réveil : le fichier est là,
    il nomme un PID d'un autre temps, et rien ne le tient. Le verrou doit se
    prendre sans un mot, et surtout sans demander de supprimer un fichier.
    """
    racine = _depot(tmp_path / "depot")
    chemin = lock_path(racine)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        '{"command": "provision", "pid": 424242, '
        '"since": 1000000000.0, "host": "avant-le-reboot"}',
        encoding="utf-8",
    )

    verrou = RepoLock(racine, "run")
    verrou.acquire()
    try:
        assert verrou.held
        # Le détenteur périmé a été remplacé, pas conservé.
        assert '"command": "run"' in chemin.read_text(encoding="utf-8")
    finally:
        verrou.release()


def test_un_systeme_de_fichiers_sans_verrou_ne_bloque_pas_loutil(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dégradé assumé : sur un FS sans ``flock``, on travaille sans filet.

    Simulé (``fcntl.flock`` remplacé) : provoquer un vrai ``ENOLCK`` demanderait
    un montage NFS sans lockd, hors de portée d'une suite unitaire. Ce qui est
    prouvé ici est le comportement de dsoxlab face à cet errno, pas l'errno.
    """
    import errno
    import fcntl

    def _refus(fd: int, operation: int) -> None:
        del fd, operation
        raise OSError(errno.ENOLCK, "no locks available")

    monkeypatch.setattr(fcntl, "flock", _refus)
    racine = _depot(tmp_path / "depot")

    verrou = RepoLock(racine, "provision")
    verrou.acquire()  # ne doit pas lever
    try:
        assert not verrou.held, "l'outil ne doit pas prétendre tenir un verrou"
    finally:
        verrou.release()


# ── La CLI : ce qui est refusé, ce qui passe ─────────────────────────────────


def test_la_cli_refuse_une_seconde_ecriture_et_dit_laquelle(tmp_path: Path) -> None:
    racine = _depot(tmp_path / "depot")
    tenu = RepoLock(racine, "provision")
    tenu.acquire()

    try:
        resultat = runner.invoke(
            app, ["use", "--lang", "fr", "--lab-home", str(racine)]
        )
    finally:
        tenu.release()

    assert resultat.exit_code == EXIT_LOCKED, "un conflit a son propre code"
    lisible = _plain(resultat.output)
    assert "provision" in lisible, "la commande détentrice doit être nommée"
    assert str(os.getpid()) in lisible, "son PID aussi"


@pytest.mark.parametrize(
    "commande",
    [
        ["list-labs"],
        ["show", "premier"],
        ["scores"],
        ["progress"],
        ["validate-structure"],
    ],
)
def test_les_commandes_de_lecture_ne_prennent_pas_le_verrou(
    tmp_path: Path, commande: list[str]
) -> None:
    """Consulter son catalogue pendant un provision n'est pas un conflit."""
    racine = _depot(tmp_path / "depot")
    tenu = RepoLock(racine, "provision")
    tenu.acquire()

    try:
        resultat = runner.invoke(app, [*commande, "--lab-home", str(racine)])
    finally:
        tenu.release()

    assert resultat.exit_code != EXIT_LOCKED, _plain(resultat.output)


def test_le_verrou_est_rendu_meme_quand_la_commande_sort_en_erreur(
    tmp_path: Path,
) -> None:
    """Une commande qui échoue ne doit pas condamner le dépôt."""
    racine = _depot(tmp_path / "depot")
    (racine / "meta.yml").write_text(
        "repo:\n  id: verrou-demo\n  category: demo\n"
        "sections:\n  - id: demo\n    labs:\n      - demo/premier\n",
        encoding="utf-8",
    )

    echec = runner.invoke(app, ["use", "inconnue", "--lab-home", str(racine)])
    assert echec.exit_code == 1, _plain(echec.output)

    apres = RepoLock(racine, "provision")
    apres.acquire()  # ne doit pas lever
    try:
        assert apres.held
    finally:
        apres.release()


def test_run_rend_le_verrou_avant_douvrir_la_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sinon le ``dsoxlab check`` tapé dans le sous-shell serait refusé.

    C'est le piège de tout verrou pris « pour toute la commande » : ``run``
    ouvre une session interactive qui dure des minutes, et c'est DEPUIS cette
    session que l'apprenant relance dsoxlab.
    """
    racine = _depot(tmp_path / "depot")
    observe: dict[str, bool] = {}

    def _session(lab: object) -> None:
        del lab
        sonde = RepoLock(racine, "check")
        try:
            sonde.acquire()
        except RepoLocked:
            observe["libre"] = False
            return
        observe["libre"] = True
        sonde.release()

    monkeypatch.setattr("dsoxlab.cli.open_lab_session", _session)

    resultat = runner.invoke(app, ["run", "premier", "--lab-home", str(racine)])

    assert resultat.exit_code == 0, _plain(resultat.output)
    assert observe.get("libre") is True, (
        "le verrou est encore tenu pendant la session : « dsoxlab check » y "
        "serait refusé par sa propre session"
    )
