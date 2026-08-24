"""`doctor --fix` : un correctif typé, joué sans shell, catégorisé.

Ce que ce module prouve, catégorie par catégorie :

- AUTOMATIC s'exécute par le wrapper centralisé, token par token : un argument
  qui porte une espace arrive **entier** à la commande, ce qu'une chaîne
  passée à un shell aurait redécoupé en deux mots ;
- MANUAL n'est **jamais** exécuté : il est affiché, le geste appartient à
  l'humain ;
- NEEDS_RELOGIN et NEEDS_REBOOT s'exécutent, puis disent que la ligne restera
  rouge jusqu'à la reconnexion ou au redémarrage : sans ce message,
  l'utilisateur relançait `doctor`, revoyait le rouge, et croyait le correctif
  en échec ;
- une séquence de commandes s'arrête au premier échec, et le dit.

Et la preuve de fond : plus aucun ``shell=True`` dans ``src/dsoxlab/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from dsoxlab.cli import app, diagnostic
from dsoxlab.services import doctor as service_doctor
from dsoxlab.services.doctor import DoctorReport, Fix, FixKind
from dsoxlab.utils.shell import CommandResult

runner = CliRunner()


@pytest.fixture(autouse=True)
def environnement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un dépôt vide suffit : le rapport est injecté, pas découvert."""
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    for variable in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
        monkeypatch.setenv(variable, str(tmp_path / variable.lower()))


def _rapport(*correctifs: Fix) -> DoctorReport:
    """Un diagnostic où chaque correctif porte un contrôle en échec."""
    report = DoctorReport()
    for index, correctif in enumerate(correctifs):
        report.required.append(
            service_doctor.Check(
                key=f"composant_{index}",
                label=f"Component {index}",
                ok=False,
                detail="broken",
                fix=correctif,
            )
        )
    return report


def _doctor_fix(
    monkeypatch: pytest.MonkeyPatch, *correctifs: Fix
) -> tuple[list[list[str]], object]:
    """Joue `doctor --fix` sur un rapport injecté, en espionnant run_command.

    Rend les argv **exacts** reçus par le wrapper, et le résultat CLI. Aucun
    shell ne tourne : ce que l'espion enregistre est ce que la commande
    recevrait.
    """
    appels: list[list[str]] = []

    def faux_run_command(cmd: list[str], **kwargs: object) -> CommandResult:
        appels.append(list(cmd))
        return CommandResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(diagnostic, "run_command", faux_run_command)
    monkeypatch.setattr(
        diagnostic, "collect_checks", lambda root, meta: _rapport(*correctifs)
    )
    resultat = runner.invoke(app, ["doctor", "--fix"])
    return appels, resultat


def test_un_argument_avec_espace_reste_un_seul_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUTOMATIC : la commande part en argv, jamais dans un shell.

    C'est LE test qui prouve le gain : « two words » passé à
    ``subprocess.run(..., shell=True)`` aurait été redécoupé en deux
    arguments par le shell. En tokens, il arrive entier.
    """
    correctif = Fix((("install-tool", "--label", "two words"),))

    appels, resultat = _doctor_fix(monkeypatch, correctif)

    assert resultat.exit_code == 0
    assert appels == [["install-tool", "--label", "two words"]]
    assert "remediation successful" in resultat.stdout


def test_manuel_affiche_et_jamais_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MANUAL : `--fix` nomme le geste, et ne lance rien du tout."""
    correctif = Fix((("rm", "-rf", "/something"),), kind=FixKind.MANUAL)

    appels, resultat = _doctor_fix(monkeypatch, correctif)

    assert resultat.exit_code == 0
    assert appels == [], "un correctif manuel ne doit jamais être exécuté"
    assert "never run automatically" in resultat.stdout
    assert "rm -rf /something" in resultat.stdout


def test_reconnexion_le_rouge_persistant_est_annonce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NEEDS_RELOGIN : exécuté, puis le message dit que le rouge va rester.

    Un `usermod -aG` réussi laisse la ligne rouge jusqu'à la session
    suivante : sans cette phrase, le prochain `doctor` ressemble à un échec.
    """
    correctif = Fix(
        (("usermod", "-aG", "incus", "student"),), kind=FixKind.NEEDS_RELOGIN
    )

    appels, resultat = _doctor_fix(monkeypatch, correctif)

    assert appels == [["usermod", "-aG", "incus", "student"]]
    assert "remediation successful" in resultat.stdout
    assert "log out" in resultat.stdout
    assert "stay red" in resultat.stdout


def test_redemarrage_le_rouge_persistant_est_annonce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NEEDS_REBOOT : exécuté, puis le message annonce l'effet différé."""
    correctif = Fix((("modprobe", "kvm"),), kind=FixKind.NEEDS_REBOOT)

    appels, resultat = _doctor_fix(monkeypatch, correctif)

    assert appels == [["modprobe", "kvm"]]
    assert "remediation successful" in resultat.stdout
    assert "after a reboot" in resultat.stdout
    assert "stay red" in resultat.stdout


def test_une_sequence_s_arrete_au_premier_echec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un correctif en plusieurs commandes ne poursuit pas après un échec.

    C'est l'équivalent typé du ``&&`` d'hier : `pool-build` sur un
    `pool-define-as` raté n'a aucun sens, et le code d'échec doit remonter.
    """
    appels: list[list[str]] = []

    def run_qui_echoue(cmd: list[str], **kwargs: object) -> CommandResult:
        appels.append(list(cmd))
        return CommandResult(returncode=3, stdout="", stderr="boom")

    correctif = Fix((("premiere", "etape"), ("seconde", "etape")))
    monkeypatch.setattr(diagnostic, "run_command", run_qui_echoue)
    monkeypatch.setattr(
        diagnostic, "collect_checks", lambda root, meta: _rapport(correctif)
    )

    resultat = runner.invoke(app, ["doctor", "--fix"])

    assert appels == [["premiere", "etape"]], "la seconde étape ne doit pas partir"
    assert "remediation failed (code 3)" in resultat.stderr


def test_le_display_requote_ce_qui_doit_l_etre() -> None:
    """La forme affichée se relit telle qu'elle s'exécute, espaces comprises."""
    correctif = Fix((("echo", "deux mots"), ("touch", "fichier")))

    assert correctif.display == "echo 'deux mots' && touch fichier"
    assert not correctif.requires_sudo
    assert Fix((("sudo", "apt", "install", "x"),)).requires_sudo


def test_plus_aucun_shell_true_dans_les_sources() -> None:
    """Le contrat de l'issue #89 : zéro ``shell=True`` dans ``src/dsoxlab/``."""
    racine = Path(__file__).resolve().parent.parent / "src" / "dsoxlab"
    coupables = [
        chemin
        for chemin in racine.rglob("*.py")
        if "shell=True" in chemin.read_text(encoding="utf-8")
    ]
    assert coupables == []
