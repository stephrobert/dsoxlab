"""Un playbook qui échoue doit dire QUELLE tâche, et POURQUOI.

Écrit pour l'issue kubernetes#94, restée deux jours sans diagnostic possible
avec ce seul message :

    setup.yaml a échoué pour cka-troubleshoot-apiserver sur la target « cp »
    (rc=4, status=failed). Stats : {}

Trois faits se cachaient derrière : dsoxlab recevait les événements
`runner_on_failed` d'ansible et les laissait filer, il capturait la sortie
complète dans `PlaybookResult.stdout` sans jamais l'afficher, et il supprimait
le répertoire d'artefacts au retour. Ce qui est éprouvé ici est donc le
diagnostic lui-même — pas la mise en forme, mais ce qu'il contient.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.infra.ansible import PlaybookResult, TacheEnEchec, detailler


def _echec(**surcharges: object) -> TacheEnEchec:
    base: dict[str, object] = {
        "tache": "Initialiser le plan de contrôle",
        "hote": "k8s-cp.lab",
        "message": "kubeadm init a rendu 1",
    }
    base.update(surcharges)
    return TacheEnEchec(**base)  # type: ignore[arg-type]


# ── Le cas courant : ansible a signalé des tâches ──────────────────────────


def test_la_tache_fautive_est_nommee() -> None:
    """Sans son nom, on ne sait pas où chercher dans un socle de 230 lignes."""
    detail = detailler(PlaybookResult(rc=2, status="failed", echecs=[_echec()]))
    assert "Initialiser le plan de contrôle" in detail
    assert "k8s-cp.lab" in detail
    assert "kubeadm init a rendu 1" in detail


def test_un_hote_injoignable_se_distingue_d_une_tache_en_echec() -> None:
    """Les deux appellent des gestes opposés : réparer le lab, ou le lien."""
    detail = detailler(
        PlaybookResult(rc=4, status="failed", echecs=[_echec(injoignable=True)])
    )
    assert "injoignable" in detail


def test_les_echecs_en_nombre_sont_bornes_et_le_reste_annonce() -> None:
    """Vingt tâches en échec noieraient la première, qui est souvent la cause."""
    detail = detailler(
        PlaybookResult(
            rc=2,
            status="failed",
            echecs=[_echec(tache=f"tâche {n}") for n in range(10)],
        ),
        taches=3,
    )
    assert "tâche 0" in detail
    assert "tâche 9" not in detail
    assert "7" in detail, "le nombre de tâches non montrées doit être annoncé"


# ── Le cas de l'issue #94 : aucun événement, des stats vides ───────────────


def test_sans_aucun_echec_signale_la_sortie_brute_prend_le_relais() -> None:
    """C'est exactement `Stats: {}` : le playbook meurt avant toute tâche.

    Se contenter des événements laisserait alors un message vide — le défaut
    d'origine. Les dernières lignes parlantes de la sortie sont la seule chose
    qui reste.
    """
    sortie = (
        "PLAY [Préparer le lab] *********************************\n"
        "\n"
        "TASK [Gathering Facts] *********************************\n"
        "ok: [k8s-cp.lab]\n"
        "ERROR! couldn't resolve module/action 'kubernetes.core.k8s'\n"
    )
    detail = detailler(PlaybookResult(rc=4, status="failed", stdout=sortie))
    assert "couldn't resolve module/action" in detail


def test_le_decor_d_ansible_est_ecarte_de_la_sortie_brute() -> None:
    """Montrer « PLAY [...] » et « ok: [host] » n'apprend rien à personne."""
    sortie = "\n".join(
        [
            "PLAY [x] ****",
            "TASK [y] ****",
            "ok: [h]",
            "skipping: [h]",
            "ERROR! la seule ligne qui compte",
        ]
    )
    detail = detailler(PlaybookResult(rc=4, status="failed", stdout=sortie))
    assert "la seule ligne qui compte" in detail
    assert "PLAY [x]" not in detail
    assert "skipping" not in detail


def test_les_evenements_priment_sur_la_sortie_brute() -> None:
    """Quand ansible a nommé la tâche, inutile de relire son flux de texte."""
    detail = detailler(
        PlaybookResult(
            rc=2,
            status="failed",
            echecs=[_echec()],
            stdout="ERROR! une ligne qui ne doit pas s'afficher",
        )
    )
    assert "Initialiser le plan de contrôle" in detail
    assert "ne doit pas s'afficher" not in detail


# ── La trace, qui survit au répertoire temporaire ──────────────────────────


def test_le_chemin_de_la_trace_est_donne(tmp_path: Path) -> None:
    """Le détail tient en quelques lignes ; le reste doit rester joignable."""
    trace = tmp_path / "setup-20261012T120000.log"
    detail = detailler(
        PlaybookResult(rc=2, status="failed", echecs=[_echec()], trace=trace)
    )
    assert str(trace) in detail


def test_un_succes_ne_produit_aucun_detail() -> None:
    """Rien à dire quand tout va bien : le message ne doit pas s'alourdir."""
    assert detailler(PlaybookResult(rc=0, status="successful")) == ""


# ── Le résumé d'une tâche ──────────────────────────────────────────────────


def test_le_message_est_remis_sur_une_ligne_et_borne() -> None:
    """Un `msg` d'ansible porte souvent une trace entière, sur dix lignes.

    Telle quelle, elle noierait le terminal et la barre de progression Rich
    qui possède l'écran à cet instant.
    """
    resume = _echec(message="première ligne\n   deuxième\n\n\ttroisième" + "x" * 900).resume()
    assert "\n" not in resume
    assert "première ligne deuxième troisième" in resume
    assert len(resume) < 600


@pytest.mark.parametrize("vide", ["", "   ", "\n"])
def test_un_message_vide_ne_produit_pas_une_ligne_muette(vide: str) -> None:
    """Une ligne qui s'arrête sur deux-points se lit comme un bug d'affichage.

    L'invariant est là, et **pas** dans le texte du repli : la première
    version de ce test cherchait le mot « aucun », donc la traduction
    française. Il passait sur une machine en français et tombait en CI, où la
    langue par défaut est l'anglais — un test qui mesurait la locale de son
    auteur plutôt que le comportement.
    """
    resume = _echec(message=vide).resume()
    assert not resume.rstrip().endswith(":"), resume
    assert resume.rstrip() != f"{_echec().tache} — k8s-cp.lab (échec) :"
