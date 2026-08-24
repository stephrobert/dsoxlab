"""La campagne d'interruption : où un Ctrl-C fait mal, et ce qu'il laisse.

Issue #82. L'enjeu n'est pas d'attraper ``KeyboardInterrupt`` quelque part :
c'est de savoir **où** une interruption fait mal, et de prouver que chacun de
ces points est traité. Un test qui interrompt toujours au même endroit ne
prouve presque rien.

L'inventaire des points de rupture, et ce que chacun laissait derrière lui
=========================================================================

Le point commun : **le silence**. Typer transforme déjà ``KeyboardInterrupt``
en ``Exit(130)``, donc le code de retour était juste ; l'apprenant retrouvait
simplement son invite, sans savoir ce qui avait été interrompu, ce qui restait
debout, ni quoi rejouer. Une seule étape mentait aussi sur le code.

======================  =========================================  ============
Point                   Avant                                      Ici
======================  =========================================  ============
``terraform apply``     Sortie muette. Le fils recevait le Ctrl-C  §1, réel
                        du terminal en même temps que dsoxlab :
                        impossible de savoir s'il l'avait eu,
                        donc impossible de lui en envoyer un.
                        Et un second Ctrl-C sortait du
                        ``finally: proc.wait()``, laissant
                        Terraform continuer, orphelin.
``terraform destroy``   idem                                       §1, réel
playbook ansible        La seule étape où le CODE mentait aussi :  §2, réel
                        ansible-runner posait ses propres
                        handlers, annulait, et l'appelant rendait
                        « rc=254, status=canceled » en
                        « setup.yaml a échoué », code 2. Mesuré.
                        Et après le playbook, `SIGINT`/`SIGTERM`
                        restaient détournés : `kill` sans effet.
services conteneurisés  Sortie muette, conteneur debout mais non   §3, simulé
                        initialisé.
attente SSH             Sortie muette, alors que l'infra est en    §3, simulé
                        place.
pytest (``check``)      Sortie muette, et pytest survivait à la    §4, réel
                        commande qui l'avait lancé, en continuant
                        de piloter la machine du lab.
session interactive     Sortie muette.                             §3, simulé
n'importe où ailleurs   Sortie muette.                             §5, réel
======================  =========================================  ============

Ce qui est réel et ce qui est simulé
====================================

**Réel** : les signaux (``SIGINT``, ``SIGTERM``, ``SIGKILL``), les processus
fils et leur mort, ansible-runner et son annulation, pytest et son arrêt.

**Simulé** : Terraform lui-même est remplacé par un fils qui parle son
protocole ``-json`` et réagit aux signaux comme lui (arrêt gracieux sur
``SIGINT``). Ce qu'on mesure est le comportement **de dsoxlab** face à un fils
qui s'arrête, pas celui de Terraform, et c'est bien le sujet : un vrai
``terraform apply`` mettrait des minutes et exigerait un hyperviseur.
L'instant de l'interruption, lui, est injecté par le callback d'affichage,
qui lève ``KeyboardInterrupt`` au n-ième événement : c'est ce qui rend la
campagne **reproductible** et permet d'en balayer les positions.
"""

from __future__ import annotations

import os
import re
import signal
import sys
import time
from pathlib import Path
from typing import Any

import pytest

import dsoxlab.cli as cli_mod
from dsoxlab.i18n.strings.en import STRINGS as EN
from dsoxlab.i18n.strings.fr import STRINGS as FR
from dsoxlab.infra import ansible as ansible_infra
from dsoxlab.infra.terraform import _stream_terraform
from dsoxlab.interrupt import (
    EVENT_INTERRUPT,
    EXIT_INTERRUPTED,
    Interrupted,
    SignalRelay,
    Stage,
    interruptible,
)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _lisible(sortie: str) -> str:
    """La sortie en une seule ligne, sans style.

    Rich replie à la largeur du terminal : « partially configured » s'écrit sur
    deux lignes et un `in` naïf ne le trouve plus. Chercher dans le texte replié
    ferait dépendre le test d'une largeur de terminal, ce qui n'a rien à voir
    avec ce qu'on veut prouver.
    """
    return " ".join(_ANSI.sub("", sortie).split())


# ─────────────────────────────────────────────────────────────────────────────
# §0. Le vocabulaire : une étape sans message serait une interruption muette
# ─────────────────────────────────────────────────────────────────────────────


def test_chaque_etape_a_son_message_dans_les_deux_langues() -> None:
    """Une étape ajoutée sans sa clé afficherait la clé elle-même à l'écran."""
    manquantes = [
        (stage.value, langue)
        for stage in Stage
        for langue, table in (("en", EN), ("fr", FR))
        if f"interrupted_{stage.value}" not in table
    ]
    assert not manquantes, f"clés absentes : {manquantes}"


def test_le_code_de_sortie_dit_la_verite() -> None:
    """130 = 128 + SIGINT, ce que le shell rend lui-même. Jamais 1."""
    assert 128 + int(signal.SIGINT) == EXIT_INTERRUPTED


# ─────────────────────────────────────────────────────────────────────────────
# §1. terraform apply / destroy : un vrai fils, une vraie escalade
# ─────────────────────────────────────────────────────────────────────────────

#: Un faux Terraform : il parle le protocole ``-json``, et il réagit aux
#: signaux comme le vrai. Sur ``SIGINT`` il ne meurt pas : il termine ce qu'il
#: a commencé, continue d'écrire quelques lignes, puis sort en 0 après avoir
#: « enregistré son state ». Sur ``SIGTERM`` il meurt sans rien enregistrer.
_FAUX_TERRAFORM = """\
import json
import os
import signal
import sys
import time
from pathlib import Path

temoin = Path(sys.argv[1])
total = int(sys.argv[2])
Path(sys.argv[3]).write_text(str(os.getpgrp()), encoding="utf-8")
arret = {"demande": False, "restant": 6}


def _sur_sigint(signum, frame):
    arret["demande"] = True
    temoin.write_text("sigint-recu", encoding="utf-8")


def _sur_sigterm(signum, frame):
    temoin.write_text("sigterm-tue", encoding="utf-8")
    sys.exit(1)


signal.signal(signal.SIGINT, _sur_sigint)
signal.signal(signal.SIGTERM, _sur_sigterm)
temoin.write_text("vivant", encoding="utf-8")

# `total < 0` : mode campagne. Le fils n'a AUCUNE raison de s'arrêter de
# lui-même, ce qui retire du test la seule course qu'il pouvait porter : celle
# où le fils finit avant que le parent ait lu l'événement où il devait
# interrompre. Le plafond de 2000 est un garde-fou de harnais : un test qui
# oublierait d'interrompre doit échouer, pas pendre.
i = 0
while True:
    print(json.dumps({
        "type": "apply_complete",
        "hook": {"resource": {"addr": f"module.lab.machine[{i}]"},
                 "elapsed_seconds": 1},
    }), flush=True)
    i += 1
    if arret["demande"]:
        arret["restant"] -= 1
        if arret["restant"] <= 0:
            temoin.write_text("sigint-state-ecrit", encoding="utf-8")
            sys.exit(0)
    elif i >= total >= 0 or i >= 2000:
        temoin.write_text("fini-sans-interruption", encoding="utf-8")
        sys.exit(0)
    time.sleep(0.005)
"""


def _faux_terraform(tmp_path: Path, total: int = -1) -> tuple[list[str], Path]:
    """La commande du faux Terraform, et le témoin qu'il tient à jour."""
    script = tmp_path / "faux_terraform.py"
    script.write_text(_FAUX_TERRAFORM, encoding="utf-8")
    temoin = tmp_path / "temoin.txt"
    groupe = tmp_path / "groupe.txt"
    return (
        [sys.executable, str(script), str(temoin), str(total), str(groupe)],
        temoin,
    )


def _attendre(temoin: Path, valeur: str, delai: float = 30.0) -> str:
    """Attend que le témoin porte la valeur voulue, et rend ce qu'il porte."""
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        contenu = temoin.read_text(encoding="utf-8") if temoin.is_file() else ""
        if contenu == valeur:
            return contenu
        time.sleep(0.02)
    return temoin.read_text(encoding="utf-8") if temoin.is_file() else ""


@pytest.mark.parametrize("rang", [0, 1, 6, 25, 60])
def test_un_ctrl_c_laisse_terraform_finir_et_ecrire_son_state(
    tmp_path: Path, rang: int
) -> None:
    """La campagne : le même Ctrl-C, joué à quatre instants du flux.

    ``rang`` est le numéro de l'événement pendant lequel l'utilisateur appuie :
    sur la toute première ressource, juste après, puis de plus en plus loin
    dans le flux. Le verdict doit être le même partout, et c'est précisément ce
    qu'un test qui n'interromprait qu'à un seul endroit ne dirait pas.
    """
    cmd, temoin = _faux_terraform(tmp_path)
    vus: list[dict[str, Any]] = []
    interruptions: list[int] = []

    def _on_event(event: dict[str, Any]) -> None:
        if event.get("type") == EVENT_INTERRUPT:
            interruptions.append(int(event["count"]))
            return
        vus.append(event)
        if len(vus) - 1 == rang and not interruptions:
            raise KeyboardInterrupt  # ← le Ctrl-C de l'apprenant

    with pytest.raises(Interrupted) as capture:
        _stream_terraform(
            cmd, env=dict(os.environ), on_event=_on_event,
            stage=Stage.TERRAFORM_APPLY,
        )

    assert capture.value.stage is Stage.TERRAFORM_APPLY
    assert capture.value.hard is False, "un seul Ctrl-C n'est pas un arrêt brutal"
    assert interruptions == [1], "l'utilisateur doit être prévenu, une fois"
    assert _attendre(temoin, "sigint-state-ecrit") == "sigint-state-ecrit", (
        "Terraform doit avoir reçu SIGINT et fini d'écrire son état : c'est ce "
        "qui rend « rejouer la commande » suffisant"
    )


def test_un_second_ctrl_c_termine_le_fils_sans_attendre(tmp_path: Path) -> None:
    """L'outil ne doit jamais laisser croire qu'il est bloqué.

    Avant, un second Ctrl-C sortait du ``proc.wait()`` du ``finally`` : dsoxlab
    rendait la main pendant que Terraform continuait, orphelin, à créer des
    machines que plus personne ne suivait.
    """
    cmd, temoin = _faux_terraform(tmp_path)
    interruptions: list[int] = []

    def _on_event(event: dict[str, Any]) -> None:
        if event.get("type") == EVENT_INTERRUPT:
            interruptions.append(int(event["count"]))
            return
        raise KeyboardInterrupt  # l'utilisateur insiste à chaque ligne

    with pytest.raises(Interrupted) as capture:
        _stream_terraform(
            cmd, env=dict(os.environ), on_event=_on_event,
            stage=Stage.TERRAFORM_DESTROY,
        )

    assert capture.value.hard is True, "l'arrêt dur doit se dire"
    assert interruptions == [1, 2]
    assert _attendre(temoin, "sigterm-tue") == "sigterm-tue", (
        "le fils doit avoir été terminé, pas abandonné derrière soi"
    )


def test_sans_interruption_rien_ne_change(tmp_path: Path) -> None:
    """Le garde-fou du garde-fou : le chemin nominal reste intact."""
    cmd, temoin = _faux_terraform(tmp_path, total=3)
    vus: list[dict[str, Any]] = []

    _stream_terraform(
        cmd, env=dict(os.environ), on_event=vus.append,
        stage=Stage.TERRAFORM_APPLY,
    )

    assert len(vus) == 3
    assert temoin.read_text(encoding="utf-8") == "fini-sans-interruption"


def test_terraform_tourne_dans_sa_propre_session(tmp_path: Path) -> None:
    """La condition de toute la politique d'arrêt, et elle se vérifie.

    Dans le même groupe de processus, le Ctrl-C du terminal frappe le fils en
    même temps que dsoxlab : on ne peut plus lui envoyer de signal sans risquer
    de compter pour le second, celui qui fait sortir Terraform sans finir la
    ressource en cours. Isolé, il ne reçoit que ce que dsoxlab lui envoie.
    """
    cmd, _temoin = _faux_terraform(tmp_path, total=2)
    groupe = tmp_path / "groupe.txt"

    _stream_terraform(
        cmd, env=dict(os.environ), on_event=lambda _e: None,
        stage=Stage.TERRAFORM_APPLY,
    )

    assert groupe.read_text(encoding="utf-8") != str(os.getpgrp()), (
        "le fils partage le groupe de processus de dsoxlab : le Ctrl-C du "
        "terminal l'atteindrait directement, et l'arrêt gracieux deviendrait "
        "indéterministe"
    )


def test_un_echec_reste_un_echec(tmp_path: Path) -> None:
    """Interrompre et échouer ne doivent pas se confondre : deux exceptions."""
    script = tmp_path / "terraform_qui_echoue.py"
    script.write_text(
        "import json, sys\n"
        "print(json.dumps({'@level': 'error', 'type': 'diagnostic',\n"
        "                  'diagnostic': {'summary': 'network is already in use',\n"
        "                                 'detail': ''}}))\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError) as capture:
        _stream_terraform(
            [sys.executable, str(script)], env=dict(os.environ),
            on_event=lambda _e: None, stage=Stage.TERRAFORM_APPLY,
        )

    assert not isinstance(capture.value, Interrupted)
    assert "network is already in use" in str(capture.value)


# ─────────────────────────────────────────────────────────────────────────────
# §2. ansible-runner : le relais de signal, et l'annulation qui n'est pas un échec
# ─────────────────────────────────────────────────────────────────────────────


def test_le_relais_compte_les_signaux_et_finit_par_rendre_la_main() -> None:
    """Vrais signaux, envoyés à ce processus. Rien n'est simulé ici."""
    vus: list[int] = []
    with SignalRelay(on_notice=vus.append) as relais:
        assert not relais.is_requested()
        os.kill(os.getpid(), signal.SIGINT)
        assert relais.is_requested(), "le premier signal arme l'annulation"
        assert vus == [1]

        # Le second ne se contente plus d'armer : il relance l'interruption
        # par le chemin normal de Python, pour que les `finally` jouent.
        with pytest.raises(KeyboardInterrupt):
            os.kill(os.getpid(), signal.SIGINT)
        assert vus == [1, 2]


def test_le_relais_rend_les_handlers_quil_a_trouves() -> None:
    """Le défaut latent d'ansible-runner : détourner SIGTERM et ne jamais le rendre.

    Un ``kill`` sur dsoxlab restait alors sans effet pour le reste du processus.
    """
    avant_int = signal.getsignal(signal.SIGINT)
    avant_term = signal.getsignal(signal.SIGTERM)

    with SignalRelay():
        assert signal.getsignal(signal.SIGINT) is not avant_int

    assert signal.getsignal(signal.SIGINT) is avant_int
    assert signal.getsignal(signal.SIGTERM) is avant_term


_PLAYBOOK_LENT = """\
- hosts: localhost
  gather_facts: false
  tasks:
    - name: attendre assez longtemps pour etre interrompu
      ansible.builtin.wait_for:
        timeout: 30
"""

_PLAYBOOK_COURT = """\
- hosts: localhost
  gather_facts: false
  tasks:
    - name: ne rien faire
      ansible.builtin.debug:
        msg: ok
"""

_INVENTAIRE = {
    "all": {"hosts": {"localhost": {"ansible_connection": "local"}}}
}

_sans_ansible = pytest.mark.skipif(
    not ansible_infra.is_available(),
    reason="ansible-runner ou ansible-playbook absent de cet environnement",
)


@_sans_ansible
def test_un_playbook_normal_rend_les_handlers(tmp_path: Path) -> None:
    """Vrai ansible-runner, vrai playbook : après lui, les signaux nous reviennent."""
    playbook = tmp_path / "court.yaml"
    playbook.write_text(_PLAYBOOK_COURT, encoding="utf-8")
    avant = signal.getsignal(signal.SIGINT)

    resultat = ansible_infra.run_playbook(playbook, _INVENTAIRE)

    assert resultat.ok, resultat.stdout
    assert signal.getsignal(signal.SIGINT) is avant, (
        "ansible-runner posait ses handlers et ne les rendait jamais : "
        "tout Ctrl-C ultérieur devenait muet"
    )


@_sans_ansible
def test_un_playbook_interrompu_nest_pas_un_playbook_en_echec(tmp_path: Path) -> None:
    """Vrai ansible-runner, vrai SIGINT, vraie annulation.

    Le signal part **quand la tâche démarre**, pas après un délai choisi au
    doigt mouillé : l'instant de l'interruption est ainsi le même à chaque
    exécution, sur une machine chargée comme sur un runner de CI. C'est le
    ``os.kill`` sur soi-même, exactement ce que fait le terminal au Ctrl-C.

    Avant, l'appelant recevait un ``PlaybookResult(rc=254, status='canceled')``
    qu'il rendait à l'apprenant en « setup.yaml a échoué », avec le code de
    sortie d'un échec.
    """
    playbook = tmp_path / "lent.yaml"
    playbook.write_text(_PLAYBOOK_LENT, encoding="utf-8")
    envoye: list[str] = []

    def _au_demarrage_de_la_tache(event: dict[str, Any]) -> None:
        # Appelé depuis le fil d'events d'ansible-runner : le signal se délivre
        # au processus, et Python exécute toujours le handler dans le fil
        # principal, celui qui attend le playbook.
        if event.get("event") == "playbook_on_task_start" and not envoye:
            envoye.append("sigint")
            os.kill(os.getpid(), signal.SIGINT)

    try:
        with pytest.raises(Interrupted) as capture:
            ansible_infra.run_playbook(
                playbook, _INVENTAIRE, on_event=_au_demarrage_de_la_tache
            )
    except KeyboardInterrupt:  # pragma: no cover : le relais n'a pas pris
        pytest.fail("le SIGINT n'a pas été capté par le relais de dsoxlab")

    assert envoye == ["sigint"], "le signal n'est jamais parti, le test ne mesure rien"
    assert capture.value.stage is Stage.ANSIBLE
    assert capture.value.hard is False


# ─────────────────────────────────────────────────────────────────────────────
# §3. Les attentes sans processus fils à nous : services, SSH, session
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "stage", [Stage.SERVICES, Stage.HOSTS_WAIT, Stage.SESSION, Stage.TESTS]
)
def test_une_attente_interrompue_devient_une_interruption_nommee(stage: Stage) -> None:
    """``interruptible`` ne fait qu'une chose, mais elle doit être vraie.

    Simulé : le ``KeyboardInterrupt`` est levé directement plutôt que par une
    sonde Docker ou une boucle SSH réelles. Ce qui est prouvé est la conversion,
    seule chose que dsoxlab décide à ces endroits-là.
    """
    with pytest.raises(Interrupted) as capture, interruptible(stage):
        raise KeyboardInterrupt

    assert capture.value.stage is stage
    assert capture.value.hard is False


def test_une_attente_qui_reussit_ne_change_rien() -> None:
    with interruptible(Stage.SERVICES):
        resultat = 1 + 1
    assert resultat == 2


# ─────────────────────────────────────────────────────────────────────────────
# §4. pytest : un `check` interrompu ne doit pas survivre à sa commande
# ─────────────────────────────────────────────────────────────────────────────


def _lab_de_test(tmp_path: Path, marqueur: Path) -> Any:
    """Un lab réel, avec deux tests dont le second laisse une trace en finissant."""
    from dsoxlab.models.lab import LabDefinition, ValidationConfig
    from dsoxlab.models.runtime import RuntimeConfig, RuntimeType

    (tmp_path / "meta.yml").write_text(
        "repo:\n  id: interruption-demo\n  category: demo\n", encoding="utf-8"
    )
    lab_dir = tmp_path / "labs" / "demo"
    tests = lab_dir / "challenge" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_functional.py").write_text(
        "import time\n"
        "from pathlib import Path\n"
        "\n"
        "\n"
        "def test_premier():\n"
        "    assert True\n"
        "\n"
        "\n"
        "def test_second():\n"
        "    time.sleep(0.6)\n"
        f"    Path({str(marqueur)!r}).write_text('pytest a survecu')\n"
        "    assert True\n",
        encoding="utf-8",
    )
    return LabDefinition(
        id="demo",
        title="Demo",
        level="l1",
        skills=["s"],
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="challenge/work"),
        distros=["alma10"],
        doc_url="https://example.test/doc",
        validation=ValidationConfig(),
        path=lab_dir,
    )


def test_un_check_interrompu_tue_pytest_et_nenregistre_rien(tmp_path: Path) -> None:
    """Vrai pytest, vraiment arrêté.

    Le marqueur est écrit par le second test **après** l'instant de
    l'interruption : s'il apparaît, c'est que pytest a continué de tourner sans
    personne pour l'attendre, en continuant, dans un vrai lab, de piloter la
    machine que l'apprenant croyait avoir laissée tranquille.
    """
    from dsoxlab.services.lab_service import check_lab

    marqueur = tmp_path / "survivant.txt"
    lab = _lab_de_test(tmp_path, marqueur)

    def _on_event(event: dict[str, Any]) -> None:
        if event.get("type") == "verdict":
            raise KeyboardInterrupt  # ← Ctrl-C au premier verdict

    with pytest.raises(Interrupted) as capture:
        check_lab(lab, on_event=_on_event)

    assert capture.value.stage is Stage.TESTS
    time.sleep(1.5)
    assert not marqueur.exists(), "pytest a survécu à la commande qui l'a lancé"


# ─────────────────────────────────────────────────────────────────────────────
# §5. La CLI : ce que l'apprenant lit, et le code que le shell reçoit
# ─────────────────────────────────────────────────────────────────────────────


def _depot(racine: Path) -> Path:
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "meta.yml").write_text(
        "repo:\n  id: interruption-cli\n  category: demo\n", encoding="utf-8"
    )
    lab = racine / "labs" / "demo" / "premier"
    (lab / "challenge" / "tests").mkdir(parents=True)
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


@pytest.fixture(autouse=True)
def _etat_isole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("LAB_HOME", raising=False)


def _sortie(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    """Joue la CLI par son VRAI point d'entrée et rend le code de sortie.

    Passer par ``main()`` et non par ``CliRunner`` n'est pas un détail : c'est
    ``main()`` qui porte le filet de dernier recours, et le code de sortie est
    ici le livrable.
    """
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as capture:
        cli_mod.main()
    code = capture.value.code
    return int(code) if code is not None else 0


def test_run_interrompu_sort_en_130_et_dit_comment_reprendre(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    racine = _depot(tmp_path / "depot")

    def _setup_interrompu(*args: Any, **kwargs: Any) -> None:
        raise Interrupted(Stage.ANSIBLE)

    monkeypatch.setattr(cli_mod.parcours, "run_lab", _setup_interrompu)
    monkeypatch.setenv("DSOXLAB_LANG", "en")

    code = _sortie(
        ["dsoxlab", "run", "premier", "--lab-home", str(racine)], monkeypatch
    )

    assert code == EXIT_INTERRUPTED
    lu = capsys.readouterr()
    ecran = _lisible(lu.out + lu.err)
    assert "partially configured" in ecran, "il faut dire ce qui reste en place"
    assert "dsoxlab run premier" in ecran, "et la commande qui reprend"


def test_un_ctrl_c_sans_proprietaire_se_dit_quand_meme(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le filet : ailleurs, l'interruption sortait en 130 mais sans un mot.

    Le code de retour n'est donc pas ce que ce test garde (typer le rendait
    déjà) : c'est la PHRASE. Sans le filet posé sur le groupe Click,
    l'apprenant récupère son invite sans savoir ce qui vient d'être interrompu.
    """
    racine = _depot(tmp_path / "depot")

    def _liste_interrompue(*args: Any, **kwargs: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_mod.contexte, "get_best_scores", _liste_interrompue)
    monkeypatch.setenv("DSOXLAB_LANG", "en")

    code = _sortie(
        ["dsoxlab", "list-labs", "--lab-home", str(racine)], monkeypatch
    )

    assert code == EXIT_INTERRUPTED
    lu = capsys.readouterr()
    ecran = _lisible(lu.out + lu.err)
    assert "Interrupted by Ctrl-C" in ecran, (
        "sans un mot, l'apprenant ne peut pas distinguer une interruption "
        "d'une commande qui n'a rien trouvé à faire"
    )


def test_un_echec_ordinaire_garde_son_propre_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le pendant du test précédent : 130 ne doit pas manger les autres codes."""
    racine = _depot(tmp_path / "depot")

    code = _sortie(
        ["dsoxlab", "show", "inexistant", "--lab-home", str(racine)], monkeypatch
    )

    assert code == 1


# ─────────────────────────────────────────────────────────────────────────────
# §6. L'état à moitié écrit : le fichier n'existe qu'entier, ou pas du tout
# ─────────────────────────────────────────────────────────────────────────────


def test_un_fichier_detat_ne_perd_jamais_sa_version_precedente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`write_text` tronque AVANT d'écrire : entre les deux, il n'y a plus rien.

    Le contexte de session était réécrit ainsi. Une coupure au mauvais instant
    le laissait vide, `read_context` rendait alors un contexte neuf sans un mot,
    et l'apprenant perdait sa section, sa target et son lab actif.

    La panne est simulée (un `fsync` qui lève), parce qu'un vrai arrêt machine
    au bon microseconde ne se scripte pas. Ce qui est prouvé est ce que dsoxlab
    garantit : la destination n'est remplacée qu'une fois le contenu complet
    écrit, et rien ne traîne derrière.
    """
    from dsoxlab.config import read_context, set_active_lab, write_context
    from dsoxlab.utils import fichiers

    write_context(tmp_path, "demo", "l1")
    set_active_lab(tmp_path, "avant-la-panne")

    def _fsync_en_panne(fd: int) -> None:
        del fd
        raise OSError("disque plein")

    monkeypatch.setattr(fichiers.os, "fsync", _fsync_en_panne)
    with pytest.raises(OSError, match="disque plein"):
        set_active_lab(tmp_path, "pendant-la-panne")

    monkeypatch.undo()
    survivant = read_context(tmp_path)
    assert survivant.active_lab == "avant-la-panne", (
        "la version précédente doit survivre entière à une écriture en échec"
    )
    assert survivant.section == "demo"
    restes = list(tmp_path.glob(".dsoxlab-context.json.*"))
    assert not restes, f"un temporaire est resté derrière : {restes}"
