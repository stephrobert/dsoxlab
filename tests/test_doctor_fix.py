"""`doctor --fix` de bout en bout, sur un diagnostic injecté.

Ce que ce module prouve :

- rien ne part sans confirmation : sans terminal et sans ``--yes``, aucune
  commande n'est lancée, et le message dit comment faire ;
- une étape sans sudo part en argv, token par token : un argument qui porte
  une espace arrive **entier**, ce qu'un shell aurait redécoupé ;
- un correctif MANUAL n'est **jamais** exécuté ;
- chaque étape est revérifiée par un diagnostic refait, et la **première** qui
  échoue arrête tout, en nommant les étapes restantes ;
- un succès à effet différé (reconnexion, redémarrage) le dit ;
- les étapes root passent par le playbook du poste, jamais par un ``sudo``
  lancé en silence ; sans terminal pour le mot de passe, elles s'affichent en
  bloc à coller.

Et la preuve de fond : plus aucun ``shell=True`` dans ``src/dsoxlab/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from dsoxlab.cli import app, diagnostic
from dsoxlab.services import doctor as service_doctor
from dsoxlab.services.doctor import DoctorReport, Fix, FixKind
from dsoxlab.services.doctor_controles.remedes import Remede
from dsoxlab.utils.shell import CommandResult

runner = CliRunner()


def _texte(resultat: object) -> str:
    """La sortie, espaces normalisés : Rich replie les phrases à la largeur du terminal."""
    return " ".join(resultat.output.split())  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def environnement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un dépôt vide suffit : le rapport est injecté, pas découvert."""
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("DSOXLAB_LANG", "en")
    for variable in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
        monkeypatch.setenv(variable, str(tmp_path / variable.lower()))
    monkeypatch.setattr(diagnostic, "_interactif", lambda: False)


def _check(index: int, ok: bool, correctif: Fix | None = None,
           remede: Remede | None = None) -> service_doctor.Check:
    return service_doctor._check(
        f"composant_{index}", ok, "ok" if ok else "broken", fix=correctif, remede=remede,
    )


class Diagnostics:
    """Le premier diagnostic montre les correctifs ; les suivants, ce qu'ils ont produit.

    ``repares`` liste les indices que les correctifs ont réellement réparés :
    un correctif « réussi » dont le contrôle reste rouge n'est pas une réussite.
    """

    def __init__(self, correctifs: list[Fix | None], remedes: list[Remede | None] | None = None,
                 repares: set[int] | None = None) -> None:
        self.correctifs = correctifs
        self.remedes = remedes or [None] * len(correctifs)
        self.repares = set(range(len(correctifs))) if repares is None else repares
        self.appels = 0

    def __call__(self, root: Path, meta: object) -> DoctorReport:
        self.appels += 1
        report = DoctorReport()
        for i, (correctif, remede) in enumerate(zip(self.correctifs, self.remedes, strict=True)):
            ok = self.appels > 1 and i in self.repares
            report.required.append(_check(i, ok, None if ok else correctif, None if ok else remede))
        return report


def _doctor_fix(
    monkeypatch: pytest.MonkeyPatch, diagnostics: Diagnostics, *options: str,
    code: int = 0,
) -> tuple[list[list[str]], object]:
    """Joue `doctor --fix` en espionnant run_command : rend les argv exacts reçus."""
    appels: list[list[str]] = []

    def faux_run_command(cmd: list[str], **kwargs: object) -> CommandResult:
        appels.append(list(cmd))
        return CommandResult(returncode=code, stdout="", stderr="boom" if code else "")

    monkeypatch.setattr(diagnostic, "run_command", faux_run_command)
    monkeypatch.setattr(diagnostic, "collect_checks", diagnostics)
    resultat = runner.invoke(app, ["doctor", "--fix", *options])
    return appels, resultat


def test_sans_terminal_ni_yes_rien_ne_part(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le plan s'affiche, et rien n'est lancé : un script doit le demander par --yes."""
    correctif = Fix((("install-tool",),))

    appels, resultat = _doctor_fix(monkeypatch, Diagnostics([correctif]))

    assert appels == []
    assert resultat.exit_code == 1
    assert "Add --yes" in _texte(resultat)
    assert "install-tool" in _texte(resultat), "le plan est affiché avant le refus"


def test_un_argument_avec_espace_reste_un_seul_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une étape sans sudo part en argv, jamais dans un shell."""
    correctif = Fix((("install-tool", "--label", "two words"),))

    appels, resultat = _doctor_fix(monkeypatch, Diagnostics([correctif]), "--yes")

    assert resultat.exit_code == 0
    assert appels == [["install-tool", "--label", "two words"]]
    assert "done, checked again" in _texte(resultat)


def test_manuel_affiche_et_jamais_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    """MANUAL : `--fix` nomme le geste, et ne lance rien du tout."""
    correctif = Fix((("rm", "-rf", "/something"),), kind=FixKind.MANUAL)

    appels, resultat = _doctor_fix(monkeypatch, Diagnostics([correctif]), "--yes")

    assert resultat.exit_code == 0
    assert appels == [], "un correctif manuel ne doit jamais être exécuté"
    assert "rm -rf /something" in _texte(resultat)
    assert "yours to do" in _texte(resultat)


def test_un_succes_dont_le_controle_reste_rouge_est_un_echec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un code nul ne suffit pas : `apt install` sort en 0 sur ce qui ne règle rien."""
    correctif = Fix((("install-tool",),))

    appels, resultat = _doctor_fix(
        monkeypatch, Diagnostics([correctif], repares=set()), "--yes",
    )

    assert appels == [["install-tool"]]
    assert "the check is still not green" in _texte(resultat)
    assert "Remaining steps: 1" in _texte(resultat)


def test_le_premier_echec_arrete_les_suivants(monkeypatch: pytest.MonkeyPatch) -> None:
    """L'ancienne cascade continuait : un pool créé sans libvirt, des collections
    sans Ansible. Désormais la première étape qui échoue arrête tout."""
    premier = Fix((("premiere", "etape"),))
    second = Fix((("seconde", "etape"),))

    appels, resultat = _doctor_fix(
        monkeypatch, Diagnostics([premier, second]), "--yes", code=3,
    )

    assert appels == [["premiere", "etape"]], "la seconde étape ne doit pas partir"
    assert "failed (code 3)" in _texte(resultat)
    assert "Remaining steps: 1, 2" in _texte(resultat)


def test_une_sequence_s_arrete_au_premier_echec(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dans une même étape, la seconde commande ne part pas après un échec."""
    correctif = Fix((("premiere", "etape"), ("seconde", "etape")))

    appels, resultat = _doctor_fix(monkeypatch, Diagnostics([correctif]), "--yes", code=3)

    assert appels == [["premiere", "etape"]]
    assert "failed (code 3)" in _texte(resultat)


def test_reconnexion_le_rouge_persistant_est_annonce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    correctif = Fix((("usermod", "-aG", "incus", "student"),), kind=FixKind.NEEDS_RELOGIN)

    appels, resultat = _doctor_fix(monkeypatch, Diagnostics([correctif]), "--yes")

    assert appels == [["usermod", "-aG", "incus", "student"]]
    assert "log out" in _texte(resultat)
    assert "stay red" in _texte(resultat)


def test_redemarrage_le_rouge_persistant_est_annonce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    correctif = Fix((("modprobe", "kvm"),), kind=FixKind.NEEDS_REBOOT)

    appels, resultat = _doctor_fix(monkeypatch, Diagnostics([correctif]), "--yes")

    assert appels == [["modprobe", "kvm"]]
    assert "after a reboot" in _texte(resultat)


_ROOT = Remede("composant_0", ("sudo apt install libvirt-clients",), root=True, tag="libvirt")


def test_sans_terminal_les_etapes_root_s_affichent_a_coller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Personne ne peut taper le mot de passe : rien n'est lancé, le bloc s'affiche.

    ansible-playbook est bien là : c'est l'absence de terminal, et elle seule,
    qui doit empêcher le lancement.
    """
    binaire = tmp_path / "ansible-playbook"
    binaire.write_text("#!/bin/sh\n", encoding="utf-8")
    binaire.chmod(0o755)
    lancements: list[list[str]] = []
    monkeypatch.setattr(diagnostic, "_commande_playbook",
                        lambda chemin: [str(binaire), "--ask-become-pass", str(chemin)])
    monkeypatch.setattr(diagnostic.subprocess, "run",
                        lambda cmd, **kw: lancements.append(cmd))

    appels, resultat = _doctor_fix(monkeypatch, Diagnostics([None], [_ROOT]), "--yes")

    assert appels == [] and lancements == []
    assert "Paste these sudo steps" in _texte(resultat)
    assert "sudo apt install libvirt-clients" in _texte(resultat)


def test_les_etapes_root_passent_par_le_playbook_du_poste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un seul ansible-playbook, aucun sudo lancé par dsoxlab, et un playbook qui
    joue la ligne affichée, sans sudo et sans question."""
    binaire = tmp_path / "ansible-playbook"
    binaire.write_text("#!/bin/sh\n", encoding="utf-8")
    binaire.chmod(0o755)
    lancements: list[list[str]] = []

    class Fini:
        returncode = 0

    monkeypatch.setattr(diagnostic, "_interactif", lambda: True)
    monkeypatch.setattr(diagnostic, "_current_user", lambda: "student")
    monkeypatch.setattr(diagnostic, "_commande_playbook",
                        lambda chemin: [str(binaire), "--ask-become-pass", str(chemin)])
    monkeypatch.setattr(diagnostic.subprocess, "run",
                        lambda cmd, **kw: (lancements.append(cmd), Fini())[1])

    appels, resultat = _doctor_fix(monkeypatch, Diagnostics([None], [_ROOT]), "--yes")

    assert appels == [], "aucune commande root ne part par run_command"
    assert len(lancements) == 1 and lancements[0][0] == str(binaire)
    jeu = yaml.safe_load(Path(lancements[0][-1]).read_text(encoding="utf-8"))
    script = jeu[0]["tasks"][0]["ansible.builtin.shell"]
    assert "apt install -y libvirt-clients" in script
    assert "sudo" not in script
    assert "done, checked again" in _texte(resultat)


def test_sans_ansible_fix_l_installe_avant_le_playbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Décision 3 : le playbook du poste a besoin d'Ansible, installé sans sudo.

    Le cas réel : une AlmaLinux 10 sans git ni catalogue, où la seule étape est
    root et où aucune étape « installer Ansible » n'est au plan.
    """
    binaire = tmp_path / "bin" / "ansible-playbook"
    lancements: list[list[str]] = []

    class Fini:
        returncode = 0

    def faux_run_command(cmd: list[str], **kwargs: object) -> CommandResult:
        appels.append(list(cmd))
        binaire.parent.mkdir(exist_ok=True)
        binaire.write_text("#!/bin/sh\n", encoding="utf-8")
        binaire.chmod(0o755)
        return CommandResult(returncode=0, stdout="", stderr="")

    appels: list[list[str]] = []
    monkeypatch.setattr(diagnostic, "_interactif", lambda: True)
    monkeypatch.setattr(diagnostic, "_current_user", lambda: "student")
    monkeypatch.setattr(diagnostic, "_commande_playbook",
                        lambda chemin: [str(binaire), "--ask-become-pass", str(chemin)])
    monkeypatch.setattr(diagnostic.shutil, "which",
                        lambda nom: "/usr/bin/uv" if nom == "uv" else (
                            str(binaire) if nom == "ansible-playbook" and binaire.exists() else None))
    monkeypatch.setattr(diagnostic.subprocess, "run",
                        lambda cmd, **kw: (lancements.append(cmd), Fini())[1])
    monkeypatch.setattr(diagnostic, "run_command", faux_run_command)
    monkeypatch.setattr(diagnostic, "collect_checks", Diagnostics([None], [_ROOT]))

    resultat = runner.invoke(app, ["doctor", "--fix", "--yes"])

    assert appels == [["uv", "tool", "install", "ansible-core"]]
    assert len(lancements) == 1 and lancements[0][0] == str(binaire)
    assert "done, checked again" in _texte(resultat)


def test_un_controle_qui_attendait_le_playbook_est_reverifie_apres(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le firmware EFI attend libvirt : ni « à faire vous-même », ni oublié."""
    binaire = tmp_path / "ansible-playbook"
    binaire.write_text("#!/bin/sh\n", encoding="utf-8")
    binaire.chmod(0o755)
    appels = {"n": 0}

    def diagnostics(root: Path, meta: object) -> DoctorReport:
        appels["n"] += 1
        report = DoctorReport()
        fait = appels["n"] > 1
        report.required.append(service_doctor._check(
            "composant_0", fait, "x", remede=None if fait else _ROOT))
        report.required.append(service_doctor._check(
            "efi", fait, "OVMF" if fait else "attend libvirt",
            forced_state=None if fait else service_doctor.STATE_UNKNOWN,
            apres=None if fait else "composant_0"))
        return report

    class Fini:
        returncode = 0

    monkeypatch.setattr(diagnostic, "_interactif", lambda: True)
    monkeypatch.setattr(diagnostic, "_current_user", lambda: "student")
    monkeypatch.setattr(diagnostic, "_commande_playbook",
                        lambda chemin: [str(binaire), "--ask-become-pass", str(chemin)])
    monkeypatch.setattr(diagnostic.subprocess, "run", lambda cmd, **kw: Fini())
    monkeypatch.setattr(diagnostic, "collect_checks", diagnostics)

    sortie = _texte(runner.invoke(app, ["doctor", "--fix", "--yes"]))

    assert "Checked again after the playbook" in sortie
    assert "To do yourself" not in sortie
    assert "checked after the playbook, ready" in sortie


def test_plus_aucun_shell_true_dans_les_sources() -> None:
    """Le contrat de l'issue #89 : zéro ``shell=True`` dans ``src/dsoxlab/``."""
    racine = Path(__file__).resolve().parent.parent / "src" / "dsoxlab"
    coupables = [
        chemin
        for chemin in racine.rglob("*.py")
        if "shell=True" in chemin.read_text(encoding="utf-8")
    ]
    assert coupables == []


def test_le_display_requote_ce_qui_doit_l_etre() -> None:
    """La forme affichée se relit telle qu'elle s'exécute, espaces comprises."""
    correctif = Fix((("echo", "deux mots"), ("touch", "fichier")))

    assert correctif.display == "echo 'deux mots' && touch fichier"
    assert not correctif.requires_sudo
    assert Fix((("sudo", "apt", "install", "x"),)).requires_sudo


@pytest.mark.parametrize(("code_sudo", "demande"), [(0, False), (1, True)])
def test_le_mot_de_passe_se_demande_sauf_vrai_nopasswd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code_sudo: int, demande: bool,
) -> None:
    """La sonde ignore le mot de passe gardé en mémoire (`sudo -k`).

    Sans `-k`, `sudo -n true` réussissait grâce au cache du terminal : dsoxlab
    omettait `--ask-become-pass`, et le sudo d'Ansible échouait sur « il est
    nécessaire de saisir un mot de passe » (Pop!_OS 24.04, 2026-11-16).
    """
    sondes: list[list[str]] = []

    class Resultat:
        returncode = code_sudo

    monkeypatch.setattr(diagnostic.shutil, "which", lambda nom: f"/usr/bin/{nom}")
    monkeypatch.setattr(diagnostic.subprocess, "run",
                        lambda cmd, **kw: (sondes.append(cmd), Resultat())[1])

    commande = diagnostic._commande_playbook(tmp_path / "poste.yml")

    assert sondes == [["sudo", "-n", "-k", "true"]]
    assert ("--ask-become-pass" in commande) is demande
