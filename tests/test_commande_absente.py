"""`check=False` tient sa promesse, et git comme docker sont déclarés (#174).

`run_command` transformait `TimeoutExpired`, `FileNotFoundError` et toute autre
`OSError` en `CommandError` **même avec `check=False`**. Tout appelant qui
croyait recevoir un `CommandResult` en toutes circonstances se trompait — et le
nom du paramètre l'encourageait à le croire.

Deux victimes, mesurées par exécution avant d'être corrigées :

- **git absent** : `dsoxlab catalog add` sortait en trace Python. C'est la
  deuxième commande du parcours d'accueil, donc le plus mauvais moment possible
  pour montrer une trace à quelqu'un. Or git n'est ni une dépendance déclarée,
  ni un contrôle de `doctor`.
- **une sonde qui expire** : la `CommandError` faisait sauter la boucle de
  réessai *entière*, au lieu d'être comptée comme un échec à réessayer.

Ce module éprouve la racine et les deux bords, parce que corriger la racine sans
vérifier les bords laisserait croire le travail fait.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from dsoxlab.utils.shell import (
    FAILURE_NOT_FOUND,
    FAILURE_OS_ERROR,
    FAILURE_TIMEOUT,
    CommandError,
    run_command,
)

# ── La racine : la promesse de check=False ──────────────────────────────────

def test_un_binaire_absent_ne_leve_plus_sans_check(tmp_path: Path) -> None:
    resultat = run_command(["binaire-qui-n-existe-pas-du-tout"], check=False)

    assert resultat.returncode == -1
    assert resultat.failure == FAILURE_NOT_FOUND
    assert not resultat.ok


def test_un_binaire_absent_leve_toujours_avec_check() -> None:
    """L'autre bout : `check=True` garde exactement le comportement d'avant."""
    with pytest.raises(CommandError):
        run_command(["binaire-qui-n-existe-pas-du-tout"], check=True)


def test_un_delai_depasse_ne_leve_plus_sans_check() -> None:
    resultat = run_command(["sleep", "5"], check=False, timeout=1)

    assert resultat.failure == FAILURE_TIMEOUT
    assert not resultat.ok


def test_un_delai_depasse_leve_toujours_avec_check() -> None:
    with pytest.raises(CommandError):
        run_command(["sleep", "5"], check=True, timeout=1)


def test_une_erreur_systeme_est_nommee(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un exec refusé, un descripteur épuisé : la cause se distingue des autres."""
    def _refuse(*args: Any, **kwargs: Any) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(subprocess, "run", _refuse)
    resultat = run_command(["peu-importe"], check=False)

    assert resultat.failure == FAILURE_OS_ERROR


def test_une_commande_qui_repond_mal_n_est_pas_un_echec_d_execution() -> None:
    """La distinction qui justifie le champ : répondre mal ≠ ne pas répondre.

    Les deux gestes sont opposés — lire stderr d'un côté, installer un paquet
    ou réessayer de l'autre. Un appelant qui ne regarde que `returncode` les
    confondrait.
    """
    resultat = run_command(["sh", "-c", "exit 3"], check=False)

    assert resultat.returncode == 3
    assert resultat.failure is None, "la commande a bien tourné, elle a mal fini"
    assert not resultat.ok


def test_une_commande_qui_reussit_ne_porte_aucune_cause() -> None:
    resultat = run_command(["sh", "-c", "exit 0"], check=False)

    assert resultat.ok and resultat.failure is None


def test_le_message_d_absence_ne_depend_pas_de_la_langue() -> None:
    """`utils/` est sous la couche i18n : il n'y compose aucune phrase traduite.

    Une phrase française en dur y serait sortie telle quelle sous
    `DSOXLAB_LANG=en`, et la traduction appartient à la couche qui affiche.
    """
    resultat = run_command(["binaire-qui-n-existe-pas-du-tout"], check=False)

    assert "introuvable" not in resultat.stderr.lower()


# ── Le bord : git absent devient une phrase, pas une trace ──────────────────

def test_git_absent_donne_une_erreur_de_catalogue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """`catalog add` sortait en trace Python sur un poste sans git."""
    from dsoxlab.services import catalog

    monkeypatch.setattr(catalog, "run_command", lambda *a, **k: _absent())

    with pytest.raises(catalog.CatalogueError) as exc:
        catalog._git(["clone", "https://example.org/x", str(tmp_path)], timeout=5)

    message = str(exc.value)
    # Assertion durcie : la version d'origine se contentait de « git », que la
    # clé i18n `catalog_git_absent` contient elle-même. Elle passait donc au
    # vert alors que la clé n'existait dans aucun dictionnaire et s'affichait
    # brute à l'utilisateur — le faux positif que ce test devait exclure.
    assert message != "catalog_git_absent", "la clé i18n n'est pas traduite"
    assert "git" in message.lower()


def _absent() -> Any:
    from dsoxlab.utils.shell import CommandResult

    return CommandResult(returncode=-1, stdout="", stderr="…",
                         failure=FAILURE_NOT_FOUND)


# ── Le bord : doctor déclare enfin les deux outils ──────────────────────────

def test_git_est_un_controle_requis(tmp_path: Path) -> None:
    """git sert au parcours d'accueil, quel que soit le domaine du dépôt."""
    from dsoxlab.services.doctor import collect_checks

    (tmp_path / "labs").mkdir()
    (tmp_path / "meta.yml").write_text("repo:\n  id: essai\n  category: essai\n",
                                       encoding="utf-8")
    rapport = collect_checks(tmp_path, None)

    assert "git" in [c.key for c in rapport.required]


def test_docker_suit_ce_que_le_catalogue_declare(tmp_path: Path) -> None:
    """Requis si un lab déclare des services, informatif sinon.

    Le classement lit le contrat et rien d'autre : un dépôt qui n'utilise pas
    docker n'a aucune raison d'en voir du rouge, et le moteur n'a pas à savoir
    quelles images un catalogue déclare.
    """
    from dsoxlab.services.doctor import collect_checks

    (tmp_path / "meta.yml").write_text("repo:\n  id: essai\n  category: essai\n",
                                       encoding="utf-8")
    base = tmp_path / "labs" / "l1"
    base.mkdir(parents=True)
    (base / "lab.yaml").write_text(
        "id: l1\ntitle: T\nlevel: l1\nskills: [s]\ndistros: [any]\n"
        "doc_url: https://example.org/\n"
        "runtime:\n  type: shell\n  workdir: challenge/work\n",
        encoding="utf-8")

    sans = collect_checks(tmp_path, None)
    assert "docker" in [c.key for c in sans.optional], (
        "sans service déclaré, docker ne doit pas bloquer"
    )

    (base / "lab.yaml").write_text(
        (base / "lab.yaml").read_text(encoding="utf-8")
        + "  services:\n    - name: db\n      image: postgres:16\n",
        encoding="utf-8")

    avec = collect_checks(tmp_path, None)
    assert "docker" in [c.key for c in avec.required], (
        "dès qu'un lab déclare des services, docker devient requis"
    )


# ── Le bord : le tirage d'image, distinct du démarrage ──────────────────────

def test_une_image_absente_est_tiree_avant_le_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le premier `docker run` tirait l'image dans SON délai.

    Au-delà, la commande échouait sur un message de démarrage qui ne parlait pas
    du réseau ; en deçà, `run` pendait plusieurs minutes sans rien dire.
    """
    from dsoxlab.runtimes import services as svc

    appels: list[list[str]] = []

    def _faux(cmd: list[str], **kwargs: Any) -> Any:
        from dsoxlab.utils.shell import CommandResult
        appels.append(cmd)
        # L'image n'est pas locale, le pull réussit.
        if cmd[:3] == ["docker", "image", "inspect"]:
            return CommandResult(returncode=1, stdout="", stderr="")
        return CommandResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(svc, "run_command", _faux)
    vus: list[str] = []
    svc._tirer("postgres:16", vus.append)

    assert ["docker", "pull", "postgres:16"] in appels
    assert vus == ["postgres:16"], "le tirage doit se dire, sinon run a l'air figé"


def test_une_image_deja_locale_n_est_pas_retiree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sinon chaque `run` repasserait par le réseau."""
    from dsoxlab.runtimes import services as svc

    appels: list[list[str]] = []

    def _faux(cmd: list[str], **kwargs: Any) -> Any:
        from dsoxlab.utils.shell import CommandResult
        appels.append(cmd)
        return CommandResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(svc, "run_command", _faux)
    vus: list[str] = []
    svc._tirer("postgres:16", vus.append)

    assert not any(c[:2] == ["docker", "pull"] for c in appels)
    assert vus == [], "rien à annoncer quand rien n'est téléchargé"


def test_le_delai_de_tirage_depasse_celui_du_demarrage() -> None:
    """Une image de plusieurs gigaoctets sur un réseau partagé de formation.

    C'est le contexte réel du défaut : le délai d'un démarrage de conteneur n'a
    aucune raison de borner un téléchargement.
    """
    from dsoxlab.runtimes.services import _DELAI_TIRAGE

    assert _DELAI_TIRAGE >= 900


# ── Le bord : une sonde qui expire se réessaie ──────────────────────────────

def test_une_sonde_qui_expire_est_reessayee(monkeypatch: pytest.MonkeyPatch) -> None:
    """La `CommandError` faisait sauter la boucle de réessai entière.

    Or c'est exactement ce qu'une sonde doit tolérer : un service qui n'est pas
    encore prêt peut ne pas répondre du tout, pas seulement répondre mal.
    """
    from dsoxlab.runtimes import services as svc
    from dsoxlab.utils.shell import CommandResult

    essais = {"n": 0}

    def _faux(cmd: list[str], **kwargs: Any) -> CommandResult:
        essais["n"] += 1
        if essais["n"] < 3:
            return CommandResult(returncode=-1, stdout="", stderr="…",
                                 failure=FAILURE_TIMEOUT)
        return CommandResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(svc, "run_command", _faux)
    monkeypatch.setattr(svc.time, "sleep", lambda _: None)

    assert svc._wait_exec("c", ["vrai"], timeout=30) is True
    assert essais["n"] == 3, "les deux délais dépassés devaient être réessayés"
