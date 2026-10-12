"""Pilotage d'Ansible depuis Python via ``ansible-runner``.

dsoxlab n'invoque **jamais** ``ansible-playbook`` en sous-processus.
La bibliothèque ``ansible-runner`` (officielle Red Hat, utilisée par
AAP et ansible-navigator) fournit une API Python typée avec retours
structurés (events JSON par tâche, stats agrégées).

Cette couche est strictement **agnostique du domaine** : elle reçoit
un chemin de playbook + un inventory dict, exécute, retourne un
``PlaybookResult`` enrichi. Ce sont les modules métier (runtimes/vm.py,
services/lab_service.py) qui appellent cette couche.

Le hook ``logging.captureWarnings(True)`` côté ansible-runner produit
beaucoup de bruit ; on filtre par défaut sauf en mode verbeux.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..i18n import _
from ..interrupt import EVENT_INTERRUPT, Interrupted, SignalRelay, Stage

logger = logging.getLogger(__name__)



@dataclass(frozen=True)
class TacheEnEchec:
    """Ce qu'ansible a dit d'une tâche qui n'est pas passée.

    Reconstitué depuis l'événement ``runner_on_failed`` ou
    ``runner_on_unreachable``, qui porte déjà tout : dsoxlab le recevait et le
    laissait filer.
    """

    tache: str
    """Le nom de la tâche, tel que le playbook l'écrit."""

    hote: str
    """L'hôte sur lequel elle a échoué."""

    message: str
    """Le message d'ansible — souvent la seule ligne qui explique."""

    injoignable: bool = False
    """``True`` pour un ``unreachable`` : la cause est le lien, pas la tâche."""

    def resume(self, largeur: int = 400) -> str:
        """Une ligne par fait, prête à être affichée.

        Le repli sur « (aucun message) » est ici et pas seulement chez
        l'appelant : un `TacheEnEchec` construit à la main — par un test, ou
        par un futur appelant — produisait sinon une ligne qui s'arrête sur
        deux-points, ce qui se lit comme un bug d'affichage plutôt que comme
        un module muet.
        """
        quoi = "injoignable" if self.injoignable else "échec"
        message = " ".join(self.message.split())[:largeur] or _("ansible_sans_message")
        return f"{self.tache} — {self.hote} ({quoi}) : {message}"


@dataclass
class PlaybookResult:
    """Résultat structuré d'une exécution de playbook."""

    rc: int
    """Code de retour (0 = succès)."""

    status: str
    """``successful`` | ``failed`` | ``timeout`` | ``unknown``.

    ``canceled`` n'arrive jamais jusqu'ici : une annulation est une
    interruption utilisateur, pas un résultat, et ``run_playbook`` lève
    ``Interrupted`` plutôt que de la faire passer pour un échec.
    """

    stats: dict[str, dict[str, int]] = field(default_factory=dict)
    """Stats agrégées par hôte : ``{ "ok": {host: n}, "changed": {...},
    "failed": {...}, "skipped": {...}, "unreachable": {...} }``."""

    stdout: str = ""
    """Sortie agrégée (utile pour debug)."""

    echecs: list[TacheEnEchec] = field(default_factory=list)
    """Les tâches qui ont échoué, dans l'ordre où ansible les a signalées.

    Vide ne veut pas dire « tout va bien » : un playbook interrompu avant la
    première tâche n'en produit aucune, et c'est précisément le cas qui
    laissait l'utilisateur sans rien (``Stats: {}``). L'appelant doit donc
    retomber sur ``stdout``, jamais conclure du vide."""

    trace: Path | None = None
    """Où la sortie complète a été conservée, quand elle l'a été."""

    @property
    def ok(self) -> bool:
        return self.rc == 0 and self.status == "successful"

    @property
    def total_changed(self) -> int:
        return sum(self.stats.get("changed", {}).values())

    @property
    def total_failed(self) -> int:
        return sum(self.stats.get("failed", {}).values()) + sum(
            self.stats.get("unreachable", {}).values()
        )


class AnsibleNotInstalled(RuntimeError):
    """Levée si ansible-runner n'est pas disponible."""


def is_available() -> bool:
    """True si un playbook peut réellement être joué.

    Tester le seul import d'``ansible_runner`` ne suffit pas, et c'est un faux
    positif coûteux : ``ansible-runner`` **ne tire pas** ``ansible-core``, et le
    binaire qu'il finit par exécuter est ``ansible-playbook``. Sur une machine
    où il manque, ce diagnostic répondait « OK » pendant que tout ``dsoxlab
    run`` sur un lab ``vm`` sortait en ``rc=127``, sans que rien ne relie les
    deux.

    On vérifie donc les deux moitiés : la bibliothèque, et l'exécutable.
    """
    try:
        import ansible_runner  # noqa: F401
    except ImportError:
        return False
    return has_ansible_playbook()


def has_ansible_playbook() -> bool:
    """``ansible-playbook`` est-il dans le PATH ?

    Séparé d'``is_available()`` pour que le diagnostic puisse distinguer les
    deux causes : la bibliothèque absente et l'exécutable absent ne se
    réparent pas de la même façon.
    """
    return shutil.which("ansible-playbook") is not None


def run_playbook(
    playbook_path: Path,
    inventory: dict[str, Any] | Path,
    *,
    extra_vars: dict[str, Any] | None = None,
    vault_password_file: Path | None = None,
    quiet: bool = True,
    timeout_s: int | None = None,
    private_data_dir: Path | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> PlaybookResult:
    """Exécute un playbook via ansible-runner et retourne le résultat.

    Args:
        playbook_path: Chemin absolu vers le ``.yaml`` du playbook.
        inventory: Soit un dict (format standard Ansible :
            ``{"all": {"hosts": {fqdn: {ansible_host, ansible_user,
            ansible_ssh_private_key_file, ...}}}}``) ; soit un chemin
            vers un fichier inventory.
        extra_vars: ``-e`` Ansible.
        vault_password_file: Chemin vers ``.vault-pass`` (pour les
            playbooks chiffrés ansible-vault).
        quiet: Si True, supprime stdout d'ansible-runner.
        timeout_s: Timeout total en secondes (None = pas de limite).
        private_data_dir: Répertoire de travail d'ansible-runner (logs,
            artifacts). Si None, un tmpdir est créé et nettoyé.

    Returns:
        ``PlaybookResult`` (rc, status, stats, stdout).

    Raises:
        AnsibleNotInstalled: Si ``ansible-runner`` n'est pas importable.
        FileNotFoundError: Si le playbook n'existe pas.
        Interrupted: Si l'utilisateur a interrompu le playbook (Ctrl-C).
            L'hôte peut alors être partiellement configuré : les playbooks
            des labs sont idempotents, rejouer la commande suffit.
    """
    # Les deux moitiés manquent pour des raisons différentes et se réparent
    # différemment : les confondre dans un seul message envoyait l'utilisateur
    # réinstaller une bibliothèque qu'il avait déjà.
    try:
        import ansible_runner  # sonde d'import : la valeur ne sert pas
    except ImportError:
        raise AnsibleNotInstalled(_("err_ansible_runner_missing")) from None

    if not has_ansible_playbook():
        raise AnsibleNotInstalled(_("err_ansible_playbook_missing"))

    if not playbook_path.is_file():
        raise FileNotFoundError(
            _("err_ansible_playbook_file_missing", path=playbook_path)
        )

    import ansible_runner

    cmdline_parts: list[str] = []
    if vault_password_file is not None:
        cmdline_parts.append(f"--vault-password-file={vault_password_file}")
    cmdline = " ".join(cmdline_parts) if cmdline_parts else None

    # ansible-runner attend playbook == nom du fichier dans
    # private_data_dir/project/. On utilise le pattern roles_path absolu
    # pour rester portable depuis le dépôt fournisseur.
    project_dir = playbook_path.parent

    # Narrowing direct sur `private_data_dir` (et non via un booléen
    # intermédiaire) : c'est ce qui permet de prouver que le chemin n'est
    # plus None au moment du `private_data_dir / "project"` ci-dessous.
    tmpdir_obj: tempfile.TemporaryDirectory[str] | None = None
    if private_data_dir is None:
        tmpdir_obj = tempfile.TemporaryDirectory(prefix="dsoxlab-runner-")
        private_data_dir = Path(tmpdir_obj.name)

    try:
        # ansible-runner cherche le playbook dans private_data_dir/project.
        # On crée un lien symbolique vers le project_dir réel.
        project_link = private_data_dir / "project"
        if not project_link.exists():
            project_link.symlink_to(project_dir, target_is_directory=True)

        # Les échecs, captés au vol. L'événement porte déjà le nom de la
        # tâche, l'hôte et le message : il suffisait de les garder.
        echecs: list[TacheEnEchec] = []

        def _collecter(event: dict[str, Any]) -> None:
            nom = event.get("event")
            if nom not in {"runner_on_failed", "runner_on_unreachable"}:
                return
            donnees = event.get("event_data") or {}
            resultat = donnees.get("res") or {}
            # `msg` est le plus courant ; `stderr` et `reason` couvrent les
            # modules qui n'en posent pas. `module_stderr` sert aux échecs de
            # connexion, où `msg` est souvent laconique.
            message = ""
            for cle in ("msg", "reason", "stderr", "module_stderr", "stdout"):
                valeur = resultat.get(cle)
                if isinstance(valeur, str) and valeur.strip():
                    message = valeur.strip()
                    break
            if not message:
                message = str(resultat) if resultat else "(aucun message)"
            echecs.append(TacheEnEchec(
                tache=str(donnees.get("task") or "(tâche sans nom)"),
                hote=str(donnees.get("host") or "?"),
                message=message,
                injoignable=nom == "runner_on_unreachable",
            ))

        kwargs: dict[str, Any] = {}
        if True:
            def _safe_handler(event: dict[str, Any]) -> bool:
                """ansible-runner event_handler : doit retourner True
                pour continuer (False arrête le run). On wrap le
                callback utilisateur pour ne pas tuer le playbook si
                la CLI plante."""
                # La collecte d'abord, et hors du try de l'appelant : perdre
                # le diagnostic parce que la barre de progression a planté
                # serait exactement le défaut qu'on corrige.
                try:
                    _collecter(event)
                except Exception:
                    logger.exception("could not collect the ansible failure event")
                if on_event is not None:
                    try:
                        on_event(event)
                    except Exception:  # le callback ne doit pas tuer le playbook
                        logger.exception("on_event callback failed")
                return True

            kwargs["event_handler"] = _safe_handler

        def _prevenir(rang: int) -> None:
            """Fait remonter le Ctrl-C dans le flux d'events du playbook.

            Passer par ``on_event`` plutôt qu'imprimer ici garde le texte
            affiché dans ``cli.py``, traduit, et compatible avec la barre de
            progression Rich qui possède le terminal à cet instant.
            """
            if on_event is None:
                return
            try:
                on_event({"event": EVENT_INTERRUPT, "count": rang})
            except Exception:  # un affichage ne casse pas un arrêt
                logger.exception("on_event callback failed")

        # Le relais **doit** fournir le cancel_callback : sans lui,
        # ansible-runner installe ses propres handlers SIGINT/SIGTERM et ne les
        # restaure jamais (cf. SignalRelay). Le Ctrl-C devenait alors invisible
        # pour dsoxlab, et le playbook annulé ressortait en « échec ».
        with SignalRelay(on_notice=_prevenir) as relais:
            try:
                runner = ansible_runner.run(
                    playbook=playbook_path.name,
                    private_data_dir=str(private_data_dir),
                    inventory=inventory if isinstance(inventory, dict) else str(inventory),
                    extravars=extra_vars or {},
                    cmdline=cmdline,
                    quiet=quiet,
                    timeout=timeout_s,
                    envvars=_env_overrides(),
                    cancel_callback=relais.is_requested,
                    **kwargs,
                )
            except KeyboardInterrupt:
                # Second Ctrl-C : le relais l'a relancé pour que les `finally`
                # jouent (verrou rendu, terminal restauré) plutôt que de mourir
                # sur le signal.
                raise Interrupted(Stage.ANSIBLE, hard=True) from None

        # Un playbook annulé n'est pas un playbook en échec. Sans cette
        # distinction, l'apprenant lisait « setup.yaml a échoué (rc=254,
        # status=canceled) » là où il venait lui-même d'appuyer sur Ctrl-C, et
        # la commande sortait avec le code d'un échec.
        if relais.is_requested() or (runner.status or "") == "canceled":
            raise Interrupted(Stage.ANSIBLE, hard=relais.count >= 2)

        sortie = _read_stdout(runner)
        statut = runner.status or "unknown"
        code = runner.rc if runner.rc is not None else -1

        # La trace n'est écrite QUE sur échec, et elle survit au tmpdir : sans
        # elle, la seule copie de ce qu'ansible a dit disparaît au `cleanup()`
        # ci-dessous. C'est ce qui a laissé l'issue kubernetes#94 sans
        # diagnostic pendant deux jours.
        trace: Path | None = None
        if (code != 0 or statut != "successful") and sortie:
            trace = _conserver_la_trace(playbook_path, sortie)

        return PlaybookResult(
            rc=code,
            status=statut,
            stats=runner.stats or {},
            stdout=sortie,
            echecs=echecs,
            trace=trace,
        )
    finally:
        if tmpdir_obj is not None:
            tmpdir_obj.cleanup()


def detailler(result: PlaybookResult, *, taches: int = 3) -> str:
    """Ce qu'il faut lire quand un playbook échoue, en quelques lignes.

    Trois niveaux, du plus utile au plus brut, parce qu'aucun n'est toujours
    disponible :

    1. les tâches qu'ansible a déclarées en échec — le cas courant ;
    2. à défaut, les dernières lignes parlantes de sa sortie — c'est ce qui
       reste quand le playbook meurt avant la première tâche, cas où les
       stats sont vides et où l'ancien message ne disait **rien** ;
    3. et toujours, le chemin de la trace complète.

    Le deuxième niveau est celui qui manquait : l'issue kubernetes#94 montre
    « Stats: {} », donc aucun événement d'échec, donc rien à afficher si l'on
    se contentait du premier.
    """
    lignes: list[str] = []

    for echec in result.echecs[:taches]:
        lignes.append(f"  ✘ {echec.resume()}")
    reste = len(result.echecs) - taches
    if reste > 0:
        lignes.append(_("ansible_autres_echecs", count=reste))

    if not lignes and result.stdout:
        # Les lignes qui disent quelque chose : on écarte le décor d'ansible
        # (titres de PLAY et de TASK, séparateurs) pour garder les messages.
        bruit = ("PLAY [", "TASK [", "PLAY RECAP", "***", "ok:", "skipping:")
        utiles = [
            ligne.rstrip()
            for ligne in result.stdout.splitlines()
            if ligne.strip() and not ligne.lstrip().startswith(bruit)
        ]
        lignes.extend(f"  {ligne}" for ligne in utiles[-6:])

    if result.trace is not None:
        lignes.append(_("ansible_trace_conservee", path=str(result.trace)))

    if not lignes:
        return ""
    return "\n" + "\n".join(lignes)


def _conserver_la_trace(playbook_path: Path, sortie: str) -> Path | None:
    """Écrit la sortie d'ansible là où on pourra la relire, et rend le chemin.

    Sous ``XDG_STATE_HOME`` plutôt que dans un tmpdir : un diagnostic qui
    disparaît avec le processus qui l'a produit ne sert à personne. Le nom
    porte le playbook et l'horodatage, pour qu'un second essai n'écrase pas le
    premier — c'est souvent la comparaison des deux qui parle.

    Toute erreur est avalée : ne pas pouvoir écrire une trace ne doit jamais
    remplacer l'échec qu'on cherchait à expliquer.
    """
    try:
        base = Path(
            os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
        ) / "dsoxlab" / "ansible"
        base.mkdir(parents=True, exist_ok=True)
        # UTC et non l'heure locale : une trace se compare entre machines,
        # et `dsoxlab support` la collecte.
        horodatage = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S")
        chemin = base / f"{playbook_path.parent.name}-{playbook_path.stem}-{horodatage}.log"
        chemin.write_text(sortie, encoding="utf-8")
        logger.info("ansible output kept at %s", chemin)
    except OSError:
        logger.exception("could not keep the ansible trace")
        return None
    return chemin


def _env_overrides() -> dict[str, str]:
    """Variables d'env qu'on force pour cohérence des labs.

    - ``ANSIBLE_HOST_KEY_CHECKING=False`` : les VMs lab sont jetables, pas
      de prompt sur la clé host à chaque provision.
    - ``ANSIBLE_STDOUT_CALLBACK=default`` : sortie stable lisible.
    """
    overrides = {
        "ANSIBLE_HOST_KEY_CHECKING": "False",
        "ANSIBLE_STDOUT_CALLBACK": "default",
    }
    # Conserve les overrides déjà posés dans l'env utilisateur
    for key, value in os.environ.items():
        if key.startswith("ANSIBLE_"):
            overrides.setdefault(key, value)
    return overrides


def _read_stdout(runner: Any) -> str:
    """Récupère le stdout agrégé d'un runner ansible-runner.

    L'attribut ``stdout`` peut être un IO non encore consommé selon la
    version. On essaye plusieurs accès.
    """
    stdout_attr = getattr(runner, "stdout", None)
    if stdout_attr is None:
        return ""
    if hasattr(stdout_attr, "read"):
        try:
            return str(stdout_attr.read())
        except Exception:  # noqa: BLE001 — best-effort logging
            return ""
        finally:
            # ansible-runner ouvre ce fichier d'artefact et ne le referme pas.
            # Sans ce close, chaque playbook joué fuit un descripteur : anodin
            # sur un lab, visible sur une campagne qui en enchaîne 84, et le
            # ResourceWarning se noyait dans le bruit des DeprecationWarning
            # de la bibliothèque elle-même.
            close = getattr(stdout_attr, "close", None)
            if callable(close):
                with suppress(Exception):
                    close()
    return str(stdout_attr)
