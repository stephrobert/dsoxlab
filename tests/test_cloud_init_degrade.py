"""Un cloud-init qui a mal fini se dit, au lieu d'être jeté (#178).

`wait_for_hosts_ready` lançait `cloud-init status --wait >/dev/null 2>&1 ||
true` : l'état **et** le code de retour partaient tous les deux à la poubelle.
Hors ligne, derrière un proxy ou sur un miroir lent, les quinze paquets du
premier boot ne s'installaient pas, cloud-init finissait en `degraded`, et
l'hôte était **tout de même déclaré prêt**. Les labs échouaient ensuite sur des
commandes absentes, sans que rien ne relie les deux.

Ne pas bloquer reste la bonne décision — ce qui compte pour rendre la main,
c'est que cloud-init ait *terminé*. Mais terminer mal doit se dire, et à trois
moments : avant (le contrôle `egress`), pendant (l'avertissement), après (le
geste de reprise, dans le message).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsoxlab.infra.inventory import _etat_cloud_init

# ── La lecture de ce que l'hôte a répondu ───────────────────────────────────

def test_un_cloud_init_reussi_ne_dit_rien() -> None:
    code, detail = _etat_cloud_init(
        "__dsoxlab_cloudinit_rc=0\nstatus: done\nextended_status: done\n"
    )

    assert code == 0
    assert "done" in detail


def test_un_cloud_init_degrade_est_lu_avec_son_detail() -> None:
    """Le cas de l'issue : cloud-init a fini, mais mal."""
    code, detail = _etat_cloud_init(
        "__dsoxlab_cloudinit_rc=2\n"
        "status: degraded done\n"
        "errors:\n"
        "  - Package installation failed: firewalld\n"
    )

    assert code == 2
    assert "degraded" in detail
    assert "firewalld" in detail, "le détail doit nommer ce qui a échoué"


def test_un_hote_sans_cloud_init_n_est_pas_un_defaut() -> None:
    """Une image qui n'embarque pas cloud-init n'a rien à signaler.

    Sans ce cas, chaque hôte d'une telle image produirait un avertissement que
    rien ne justifie — et un avertissement systématique cesse d'être lu.
    """
    code, detail = _etat_cloud_init("")

    assert code is None
    assert detail == ""


def test_une_sortie_illisible_ne_fait_pas_lever() -> None:
    """La sortie de `status --long` change d'une version à l'autre.

    Un parseur qui lève sur une forme inattendue ferait planter un
    provisionnement réussi.
    """
    code, _detail = _etat_cloud_init("__dsoxlab_cloudinit_rc=inattendu\nbruit\n")

    assert code is None


def test_le_detail_est_borne() -> None:
    """`status --long` peut rendre des dizaines de lignes ; un mur de texte
    dans un terminal ne se lit pas plus qu'un journal."""
    sortie = "__dsoxlab_cloudinit_rc=2\n" + "\n".join(
        f"ligne {n}" for n in range(200)
    )

    _, detail = _etat_cloud_init(sortie)

    assert len(detail.splitlines()) <= 12


# ── La commande distante remonte ce qu'il faut ──────────────────────────────

def test_la_commande_distante_ne_jette_plus_l_etat() -> None:
    """Le défaut tenait en deux redirections : `>/dev/null 2>&1 || true`.

    La commande est appelée, pas relue dans le fichier : c'est ce qu'elle
    **envoie** qui est le contrat, et une assertion sur la source aurait été
    satisfaite par du texte que le programme ne produit jamais.
    """
    from dsoxlab.infra.inventory import _MARQUEUR_RC, _commande_cloud_init

    commande = _commande_cloud_init()

    assert "--wait" in commande, "il faut toujours attendre la fin"
    assert "--long" in commande, "l'état doit être demandé, pas seulement attendu"
    assert _MARQUEUR_RC in commande, (
        "le code de retour doit remonter, sinon on ne sait pas comment ça a fini"
    )
    assert "sudo -n" in commande, (
        "sans privilèges, cloud-init sort en PermissionError et l'attente ne "
        "garantit plus rien"
    )


def test_la_commande_et_le_lecteur_parlent_la_meme_langue() -> None:
    """Les deux moitiés doivent s'accorder, sinon l'état est perdu en silence.

    C'est le seul vrai risque de ce mécanisme : un marqueur changé d'un côté
    et pas de l'autre rendrait `code = None` sur chaque hôte, donc un silence
    indistinguable d'un succès — le défaut même que cette issue corrige.
    """
    from dsoxlab.infra.inventory import _commande_cloud_init

    # Ce que l'hôte renverrait si cloud-init avait fini en degraded.
    sortie = _commande_cloud_init().splitlines()[2].replace(
        'echo "', "").replace('"', "").replace("$?", "2")

    code, _detail = _etat_cloud_init(sortie + "\nstatus: degraded done")

    assert code == 2


# ── Le contrôle d'accès sortant : avant, plutôt que trois labs plus tard ────

def test_les_hotes_sondes_viennent_des_templates() -> None:
    """Le moteur ne connaît aucun domaine : il les lit dans ce qui est packagé.

    Écrire `cloud-images.ubuntu.com` dans `doctor.py` serait exactement le
    couplage que le projet s'interdit.
    """
    from dsoxlab.services.doctor import _hotes_images

    hotes = _hotes_images()

    assert len(hotes) >= 3, f"lecture des templates trop maigre : {hotes}"
    assert all("/" not in h for h in hotes), "ce sont des hôtes, pas des URL"


def test_le_moteur_ne_cite_aucun_miroir_en_dur() -> None:
    """L'invariant, vérifié sur la source plutôt que sur la bonne volonté."""
    from dsoxlab.services import doctor

    source = Path(doctor.__file__).read_text(encoding="utf-8")

    for miroir in ("cloud-images.ubuntu.com", "cloud.debian.org",
                   "repo.almalinux.org"):
        assert miroir not in source, f"« {miroir} » est écrit en dur dans doctor.py"


def test_un_acces_sortant_coupe_se_voit(monkeypatch: pytest.MonkeyPatch) -> None:
    from dsoxlab.services import doctor

    monkeypatch.setattr(doctor, "_joignable", lambda hote: False)

    assert doctor._check_egress().ok is False


def test_un_seul_miroir_joignable_suffit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ce qui est en cause est l'accès sortant, pas un miroir en particulier.

    Exiger que les trois répondent ferait rougir un poste parfaitement
    fonctionnel dont un seul miroir est en maintenance.
    """
    from dsoxlab.services import doctor

    essais = {"n": 0}

    def _un_seul(hote: str) -> bool:
        essais["n"] += 1
        return essais["n"] > 1

    monkeypatch.setattr(doctor, "_joignable", _un_seul)

    resultat = doctor._check_egress()

    assert resultat.ok is True
    assert essais["n"] == 2, "le premier miroir refusé doit être suivi du second"


def test_le_controle_suit_ce_que_le_depot_provisionne(tmp_path: Path) -> None:
    """Requis si le dépôt a des labs `vm`, informatif sinon.

    Un catalogue entièrement `shell` ne provisionne rien : lui montrer du rouge
    pour un accès sortant qu'il n'utilise pas serait le contre-exemple même de
    l'agnosticisme.
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

    rapport = collect_checks(tmp_path, None)

    assert "egress" in [c.key for c in rapport.optional]
    assert "egress" not in [c.key for c in rapport.required]


# ── La décision est écrite ──────────────────────────────────────────────────

def test_la_decision_sur_les_paquets_est_ecrite() -> None:
    """Le deuxième critère de l'issue : un choix non écrit ne se distingue pas
    d'un oubli, et celui-ci a coûté des labs injouables en salle."""
    from dsoxlab.services import doctor

    readme = (Path(doctor.__file__).resolve().parent.parent
              / "templates" / "cloud-init" / "README.md")

    texte = readme.read_text(encoding="utf-8")
    assert "degraded" in texte
    for ecarte in ("bloquer", "pré-cuire", "lab par lab"):
        assert ecarte in texte, f"l'option « {ecarte} » n'est pas tranchée"
