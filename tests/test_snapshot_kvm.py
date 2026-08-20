"""Le snapshot KVM visait un domaine qui n'existe pas.

Le template Terraform packagé ici nomme le domaine libvirt avec le
``infra.hosts[].name`` du ``meta.yml``, **tel quel**, donc un FQDN. Le backend
de snapshot, lui, coupait ce FQDN au premier point. Les deux ont divergé sans
bruit, parce qu'aucun lab n'active ``snapshot_required`` et qu'aucun test ne
couvrait le module.

Ces tests ferment les deux causes de la divergence :

1. le nom du domaine est **résolu** contre ce que libvirt déclare, il n'est
   plus reconstruit de tête ;
2. les quatre opérations (``create``, ``revert``, ``delete``, ``list_``)
   passent par cette résolution, et non plus chacune par sa propre supposition.

Aucun test n'exige un libvirt réel : ``virsh`` est simulé au niveau du wrapper
``run_command``, ce qui laisse le test décider de la sortie de chaque commande.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from dsoxlab import i18n
from dsoxlab.infra import libvirt
from dsoxlab.infra.libvirt import DomainNotFound
from dsoxlab.infra.snapshot import kvm
from dsoxlab.models.repo import RepoMetadata
from dsoxlab.utils.shell import CommandError, CommandResult

#: Ce que rend une infrastructure conforme au template actuel : des FQDN.
DOMAINES_FQDN = "web1.lab\ncontrol-node.lab\ndb1.lab\n"

#: Ce que rend une infrastructure créée par une version antérieure du template.
DOMAINES_COURTS = "web1\ncontrol-node\ndb1\n"


class VirshSimule:
    """Un ``run_command`` de substitution, qui joue le rôle de ``virsh``.

    Enregistre les commandes reçues et rend la sortie que le test lui dicte.
    ``list --all --name`` a une réponse dédiée : c'est elle qui porte la
    vérité sur les domaines existants.
    """

    def __init__(self, domaines: str = DOMAINES_FQDN, *, echec: str = "") -> None:
        self.domaines = domaines
        self.echec = echec
        self.commandes: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs: Any) -> CommandResult:
        self.commandes.append(cmd)
        if "list" in cmd and "--all" in cmd:
            return CommandResult(returncode=0, stdout=self.domaines, stderr="")
        if self.echec and self.echec in cmd:
            resultat = CommandResult(returncode=1, stdout="", stderr="virsh: erreur simulée")
            if kwargs.get("check", True):
                raise CommandError(cmd, resultat)
            return resultat
        return CommandResult(returncode=0, stdout="", stderr="")

    def domaines_vises(self, sous_commande: str) -> list[str]:
        """Les domaines réellement passés à ``virsh <sous_commande>``."""
        vises: list[str] = []
        for cmd in self.commandes:
            if sous_commande not in cmd:
                continue
            # `snapshot-create-as` nomme le domaine derrière `--domain` ; les
            # autres sous-commandes le passent en premier argument positionnel.
            if "--domain" in cmd:
                vises.append(cmd[cmd.index("--domain") + 1])
            else:
                vises.append(cmd[cmd.index(sous_commande) + 1])
        return vises


@pytest.fixture(autouse=True)
def langue_en(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les assertions portent sur le texte anglais.

    Sans ce verrou, le résultat dépendrait de la ``LANG`` de la machine qui
    joue la suite : verte sur un poste anglophone, rouge sur un poste
    francophone, pour un code identique.
    """
    monkeypatch.setattr(i18n, "_strings", i18n._load("en"))


@pytest.fixture
def virsh(monkeypatch: pytest.MonkeyPatch) -> VirshSimule:
    faux = VirshSimule()
    monkeypatch.setattr(libvirt, "run_command", faux)
    monkeypatch.setattr(kvm, "run_command", faux)
    return faux


@pytest.fixture
def meta() -> RepoMetadata:
    """Le backend n'utilise pas le meta.yml : un objet minimal suffit."""
    return RepoMetadata(id="demo", category="demo")


# ── Résolution du nom de domaine ────────────────────────────────────────────

def test_le_fqdn_est_prefere_car_c_est_ce_que_le_template_produit(
    virsh: VirshSimule,
) -> None:
    """Le défaut d'origine : le FQDN était coupé, donc le domaine introuvable."""
    assert libvirt.resolve_domain("control-node.lab") == "control-node.lab"


def test_le_nom_court_sert_de_repli_sur_une_infra_ancienne(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une infrastructure créée avant le template actuel reste utilisable."""
    monkeypatch.setattr(libvirt, "run_command", VirshSimule(DOMAINES_COURTS))
    assert libvirt.resolve_domain("control-node.lab") == "control-node"


def test_le_fqdn_gagne_quand_les_deux_formes_existent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deux domaines homonymes : on vise celui que le template a créé."""
    monkeypatch.setattr(
        libvirt, "run_command", VirshSimule(DOMAINES_FQDN + DOMAINES_COURTS)
    )
    assert libvirt.resolve_domain("control-node.lab") == "control-node.lab"


def test_un_hote_sans_point_ne_tente_pas_deux_fois_le_meme_nom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sinon le message d'erreur listerait deux fois le même candidat."""
    monkeypatch.setattr(libvirt, "run_command", VirshSimule("autre.lab\n"))
    with pytest.raises(DomainNotFound) as leve:
        libvirt.resolve_domain("solo")
    assert leve.value.tried == ["solo"]


def test_les_domaines_connus_evitent_une_interrogation_par_hote(
    virsh: VirshSimule,
) -> None:
    """Résoudre quatre hôtes ne doit pas coûter quatre appels à virsh."""
    connus = libvirt.list_domains()
    for hote in ("web1.lab", "db1.lab", "control-node.lab"):
        libvirt.resolve_domain(hote, known=connus)
    listages = [c for c in virsh.commandes if "list" in c]
    assert len(listages) == 1


# ── Le message d'un domaine introuvable ─────────────────────────────────────

def test_le_message_nomme_l_hote_les_candidats_et_les_domaines_existants(
    virsh: VirshSimule,
) -> None:
    """Le critère de l'issue : ne plus laisser remonter le laconique
    ``error: failed to get domain`` de virsh."""
    with pytest.raises(DomainNotFound) as leve:
        libvirt.resolve_domain("absent.lab")

    exc = leve.value
    # Le contrat structuré : lisible sans reparser une phrase traduite.
    assert exc.host_fqdn == "absent.lab"
    assert exc.tried == ["absent.lab", "absent"]
    assert exc.known == ["web1.lab", "control-node.lab", "db1.lab"]

    message = str(exc)
    # L'hôte est nommé **pour lui-même**, pas seulement au détour de la liste
    # des candidats : deux occurrences au minimum. Sans ce compte, un gabarit
    # qui laisserait le champ vide passerait le test sans être remarqué.
    assert message.count("absent.lab") >= 2
    assert "absent" in message  # le nom court, essayé en repli
    for existant in ("web1.lab", "control-node.lab", "db1.lab"):
        assert existant in message


def test_le_message_dit_aucun_quand_l_hyperviseur_est_vide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une liste vide affichée telle quelle ne se lirait pas."""
    monkeypatch.setattr(libvirt, "run_command", VirshSimule(""))
    with pytest.raises(DomainNotFound) as leve:
        libvirt.resolve_domain("absent.lab")
    assert "none" in str(leve.value)


def test_le_message_est_traduit_en_francais(
    virsh: VirshSimule, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La règle du projet vaut aussi pour les messages du moteur."""
    monkeypatch.setattr(i18n, "_strings", i18n._load("fr"))

    with pytest.raises(DomainNotFound) as leve:
        libvirt.resolve_domain("absent.lab")

    message = str(leve.value)
    assert "Aucun domaine libvirt" in message
    assert message.count("absent.lab") >= 2
    for existant in ("web1.lab", "control-node.lab", "db1.lab"):
        assert existant in message


def test_virsh_injoignable_n_est_pas_une_absence_de_domaine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confondre les deux produirait « aucun domaine n'existe », qui est faux."""

    def virsh_absent(cmd: list[str], **kwargs: Any) -> CommandResult:
        raise CommandError(
            cmd, CommandResult(returncode=-1, stdout="", stderr="Commande introuvable: sudo")
        )

    monkeypatch.setattr(libvirt, "run_command", virsh_absent)
    with pytest.raises(CommandError):
        libvirt.resolve_domain("control-node.lab")


# ── Les quatre opérations visent le domaine résolu ──────────────────────────

def test_create_vise_le_domaine_qui_existe(
    virsh: VirshSimule, meta: RepoMetadata
) -> None:
    kvm.create(meta, ["control-node.lab", "web1.lab"], "pre-lab")
    assert virsh.domaines_vises("snapshot-create-as") == [
        "control-node.lab",
        "web1.lab",
    ]


def test_revert_vise_le_domaine_qui_existe(
    virsh: VirshSimule, meta: RepoMetadata
) -> None:
    kvm.revert(meta, ["control-node.lab"], "pre-lab")
    assert virsh.domaines_vises("snapshot-revert") == ["control-node.lab"]


def test_delete_vise_le_domaine_qui_existe(
    virsh: VirshSimule, meta: RepoMetadata
) -> None:
    kvm.delete(meta, ["control-node.lab"], "pre-lab")
    assert virsh.domaines_vises("snapshot-delete") == ["control-node.lab"]


def test_list_vise_le_domaine_qui_existe(
    virsh: VirshSimule, meta: RepoMetadata
) -> None:
    kvm.list_(meta, "control-node.lab")
    assert virsh.domaines_vises("snapshot-list") == ["control-node.lab"]


def test_list_rend_les_snapshots_existants(
    monkeypatch: pytest.MonkeyPatch, meta: RepoMetadata
) -> None:
    class AvecSnapshots(VirshSimule):
        def __call__(self, cmd: list[str], **kwargs: Any) -> CommandResult:
            resultat = super().__call__(cmd, **kwargs)
            if "snapshot-list" in cmd:
                return CommandResult(returncode=0, stdout="pre-lab\nautre\n", stderr="")
            return resultat

    faux = AvecSnapshots()
    monkeypatch.setattr(libvirt, "run_command", faux)
    monkeypatch.setattr(kvm, "run_command", faux)
    assert kvm.list_(meta, "control-node.lab") == ["pre-lab", "autre"]


# ── Ce que chaque opération fait d'un domaine absent ────────────────────────

def test_create_leve_sur_un_domaine_absent(
    virsh: VirshSimule, meta: RepoMetadata
) -> None:
    """Un snapshot silencieusement non pris rendrait le rollback illusoire."""
    with pytest.raises(DomainNotFound):
        kvm.create(meta, ["absent.lab"], "pre-lab")
    assert virsh.domaines_vises("snapshot-create-as") == []


def test_revert_leve_sur_un_domaine_absent(
    virsh: VirshSimule, meta: RepoMetadata
) -> None:
    with pytest.raises(DomainNotFound):
        kvm.revert(meta, ["absent.lab"], "pre-lab")


def test_list_leve_sur_un_domaine_absent(
    virsh: VirshSimule, meta: RepoMetadata
) -> None:
    """« Pas de snapshot » et « pas de domaine » appellent des gestes opposés."""
    with pytest.raises(DomainNotFound):
        kvm.list_(meta, "absent.lab")


def test_delete_tolere_un_domaine_absent_mais_le_journalise(
    virsh: VirshSimule,
    meta: RepoMetadata,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Un nettoyage ne doit pas échouer sur ce qui a déjà disparu, mais il
    doit dire ce qu'il n'a pas trouvé."""
    with caplog.at_level(logging.WARNING, logger="dsoxlab.infra.snapshot.kvm"):
        kvm.delete(meta, ["absent.lab", "web1.lab"], "pre-lab")

    assert "absent.lab" in caplog.text
    # L'hôte suivant est tout de même traité : une absence n'interrompt pas.
    assert virsh.domaines_vises("snapshot-delete") == ["web1.lab"]
