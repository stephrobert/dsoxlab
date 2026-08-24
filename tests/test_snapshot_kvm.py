"""Les snapshots ne fonctionnaient sur aucune VM dsoxlab, et l'échec était muet.

Deux défauts, empilés, et le second cachait le premier.

**Le premier** : le backend prenait des snapshots **internes**. Le template
Terraform packagé ici impose ``firmware = "efi"``, et libvirt refuse le
snapshot interne d'un domaine dont le firmware est en pflash. La commande ne
pouvait donc aboutir sur aucune machine que ``dsoxlab provision`` crée. Sur un
disque ``type='volume'`` — la forme que produit ce même template — libvirt
refuse en plus de déduire le nom du fichier de recouvrement, ce qui casse le
snapshot externe naïf. Les deux refus sont rejoués ici par le simulateur, à
l'identique.

**Le second** : ``runtimes/vm.py`` avalait l'échec en ``logger.warning``, et
aucun ``logging.basicConfig`` n'existe dans ce paquet. Un lab qui déclare
``snapshot_required: true`` démarrait donc **sans filet**, ``run`` sortait en
0, et l'apprenant l'apprenait au moment d'en avoir besoin. C'est ce silence
qui a laissé la fonctionnalité diverger sans que personne ne le voie ; c'est
lui que le test le plus important de ce module ferme.

Le simulateur n'est pas un enregistreur de commandes : il tient un **état** —
domaines, volumes, chaîne de recouvrement, et ce que chaque couche contient.
Un test peut donc écrire dans une machine, revenir en arrière, et vérifier que
l'écriture a disparu, ce qu'aucune assertion sur une ligne de commande ne
prouve. Aucun test n'exige un libvirt réel.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from dsoxlab import i18n
from dsoxlab.infra import libvirt
from dsoxlab.infra.libvirt import DomainNotFound
from dsoxlab.infra.snapshot import SnapshotError, kvm
from dsoxlab.models.repo import RepoMetadata
from dsoxlab.utils.shell import CommandError, CommandResult

#: Ce que rend une infrastructure conforme au template actuel : des FQDN.
DOMAINES_FQDN = "web1.lab\ncontrol-node.lab\ndb1.lab\n"

#: Ce que rend une infrastructure créée par une version antérieure du template.
DOMAINES_COURTS = "web1\ncontrol-node\ndb1\n"

#: Le pool et le répertoire que le template Terraform utilise.
POOL = "default"
REPERTOIRE = "/var/lib/libvirt/images"

#: La taille virtuelle des disques du banc d'essai (10 Gio).
CAPACITE = 10737418240


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


class Hyperviseur:
    """Un libvirt de papier : il garde un état, et le fait évoluer.

    Ce qu'il modélise, et pourquoi chaque point compte :

    * **le refus du snapshot interne sur pflash**, qui est le défaut d'origine ;
    * **le refus de déduire le nom d'un recouvrement** sur un disque
      ``type='volume'``, qui est la forme que produit le template Terraform ;
    * **la chaîne de recouvrement** : chaque couche porte son propre contenu,
      et ce que la machine voit est l'union de la chaîne. C'est ce qui permet
      d'écrire, de revenir en arrière et de vérifier une disparition ;
    * **la suppression d'un snapshot externe**, que les libvirt anciens ne
      savent pas faire (``supprime_externe=False`` rejoue ce cas).
    """

    def __init__(
        self,
        domaines: tuple[str, ...] = ("web1.lab", "control-node.lab", "db1.lab"),
        *,
        supprime_externe: bool = True,
        refuse_snapshot: bool = False,
    ) -> None:
        self.supprime_externe = supprime_externe
        self.refuse_snapshot = refuse_snapshot
        self.commandes: list[list[str]] = []
        #: chemin de la couche → ce qui y a été écrit
        self.volumes: dict[str, set[str]] = {}
        #: chemin d'une couche → la couche qu'elle recouvre
        self.backing: dict[str, str] = {}
        self.domaines: dict[str, dict[str, Any]] = {}
        for nom in domaines:
            disque = f"{REPERTOIRE}/{nom}.qcow2"
            self.volumes[disque] = set()
            self.domaines[nom] = {
                "etat": "running",
                "disques": {"vda": disque},
                "snapshots": {},
            }

    # ── ce que le test manipule ─────────────────────────────────────────────

    def ecrire(self, domaine: str, texte: str, dev: str = "vda") -> None:
        """Écrit dans la machine : l'écriture atterrit dans la couche du dessus."""
        self.volumes[self.domaines[domaine]["disques"][dev]].add(texte)

    def contenu(self, domaine: str, dev: str = "vda") -> set[str]:
        """Ce que la machine voit : l'union de sa chaîne de recouvrement."""
        vu: set[str] = set()
        couche: str | None = self.domaines[domaine]["disques"][dev]
        while couche is not None:
            vu |= self.volumes.get(couche, set())
            couche = self.backing.get(couche)
        return vu

    def fichiers(self) -> set[str]:
        """Les fichiers présents dans le pool, orphelins compris."""
        return set(self.volumes)

    @staticmethod
    def _args(cmd: list[str]) -> list[str]:
        """Les arguments de virsh, débarrassés du préfixe et de ``--connect``."""
        return cmd[cmd.index("--connect") + 2:]

    def verbes(self) -> list[str]:
        """Les sous-commandes reçues, dans l'ordre."""
        return [self._args(cmd)[0] for cmd in self.commandes]

    def jouees(self, sous_commande: str) -> list[list[str]]:
        """Les arguments reçus pour cette sous-commande, appel par appel."""
        return [
            args for cmd in self.commandes
            if (args := self._args(cmd))[0] == sous_commande
        ]

    def cibles(self, sous_commande: str) -> list[str]:
        """Le domaine visé par chaque appel à cette sous-commande."""
        return [
            args[args.index("--domain") + 1] if "--domain" in args else args[1]
            for args in self.jouees(sous_commande)
        ]

    # ── le faux virsh ───────────────────────────────────────────────────────

    def __call__(self, cmd: list[str], **kwargs: Any) -> CommandResult:
        self.commandes.append(cmd)
        args = cmd[cmd.index("--connect") + 2:]
        try:
            sortie = self._router(args)
        except _Refus as refus:
            resultat = CommandResult(returncode=1, stdout="", stderr=refus.raison)
            if kwargs.get("check", True):
                raise CommandError(cmd, resultat) from None
            return resultat
        return CommandResult(returncode=0, stdout=sortie, stderr="")

    def _router(self, args: list[str]) -> str:
        verbe = args[0]
        if verbe == "list":
            return "\n".join(self.domaines) + "\n"
        if verbe == "domstate":
            return self._domaine(args[1])["etat"] + "\n"
        if verbe == "destroy":
            self._domaine(args[1])["etat"] = "shut off"
            return ""
        if verbe == "start":
            self._domaine(args[1])["etat"] = "running"
            return ""
        if verbe == "dumpxml":
            return self._dumpxml(args[1])
        if verbe == "snapshot-list":
            return "\n".join(self._domaine(args[1])["snapshots"]) + "\n"
        if verbe == "snapshot-dumpxml":
            return self._snapshot_dumpxml(args[1], args[2])
        if verbe == "snapshot-create-as":
            return self._create(args)
        if verbe == "snapshot-delete":
            return self._delete(args)
        if verbe == "vol-path":
            return f"{REPERTOIRE}/{args[args.index('--pool') + 2]}\n"
        if verbe == "vol-pool":
            return POOL + "\n"
        if verbe == "vol-dumpxml":
            return f"<volume><capacity unit='bytes'>{CAPACITE}</capacity></volume>"
        if verbe == "pool-refresh":
            return ""
        if verbe == "vol-delete":
            return self._vol_delete(args)
        if verbe == "vol-create-as":
            return self._vol_create(args)
        raise _Refus(f"error: unsupported command: {verbe}")

    def _domaine(self, nom: str) -> dict[str, Any]:
        if nom not in self.domaines:
            raise _Refus(f"error: failed to get domain '{nom}'")
        return self.domaines[nom]

    def _disque_xml(self, dev: str, chemin: str) -> str:
        """Le disque, sous la forme que libvirt lui donne à cet instant.

        Terraform crée des disques ``type='volume'`` ; un snapshot externe les
        remplace par un ``type='file'`` qui pointe le recouvrement. Le module
        doit lire les deux, donc le simulateur produit les deux.
        """
        if chemin.endswith(".qcow2"):
            source = f"<source pool='{POOL}' volume='{Path(chemin).name}'/>"
        else:
            source = f"<source file='{chemin}'/>"
        return (
            f"<disk type='file' device='disk'>"
            f"<driver name='qemu' type='qcow2'/>{source}"
            f"<target dev='{dev}' bus='virtio'/></disk>"
        )

    def _disques_xml(self, disques: dict[str, str]) -> str:
        corps = "".join(self._disque_xml(dev, c) for dev, c in sorted(disques.items()))
        # Le cdrom cloud-init : présent sur toute machine du template, et jamais
        # à figer. S'il recevait un --diskspec, libvirt refuserait le snapshot.
        corps += (
            "<disk type='file' device='cdrom'>"
            "<driver name='qemu' type='raw'/>"
            "<source file='/var/lib/libvirt/images/seed.iso'/>"
            "<target dev='sda' bus='sata'/><readonly/></disk>"
        )
        return corps

    def _dumpxml(self, nom: str) -> str:
        dom = self._domaine(nom)
        return (
            f"<domain type='kvm'><name>{nom}</name>"
            f"<devices>{self._disques_xml(dom['disques'])}</devices></domain>"
        )

    def _snapshot_dumpxml(self, nom: str, snap: str) -> str:
        dom = self._domaine(nom)
        if snap not in dom["snapshots"]:
            raise _Refus(f"error: Domain snapshot not found: {snap}")
        etat = dom["snapshots"][snap]
        disques = "".join(
            f"<disk name='{dev}' snapshot='external' type='file'>"
            f"<driver type='qcow2'/><source file='{chemin}'/></disk>"
            for dev, chemin in sorted(etat["overlays"].items())
        )
        return (
            f"<domainsnapshot><name>{snap}</name><state>disk-snapshot</state>"
            f"<memory snapshot='no'/>"
            f"<disks>{disques}<disk name='sda' snapshot='no'/></disks>"
            f"<domain type='kvm'><name>{nom}</name>"
            f"<devices>{self._disques_xml(etat['bases'])}</devices></domain>"
            f"</domainsnapshot>"
        )

    def _create(self, args: list[str]) -> str:
        nom = args[args.index("--domain") + 1]
        snap = args[args.index("--name") + 1]
        dom = self._domaine(nom)
        if self.refuse_snapshot:
            # Un hyperviseur qui ne sait pas prendre ce snapshot : firmware
            # inattendu, disque en réseau, quota de stockage plein…
            raise _Refus("error: Operation not supported: snapshot refusé par cet hyperviseur")
        if snap in dom["snapshots"]:
            raise _Refus(f"error: operation failed: domain snapshot {snap} already exists")
        if "--disk-only" not in args:
            # Le refus qui a rendu la fonctionnalité inopérante.
            raise _Refus(
                "error: Operation not supported: internal snapshots of a VM "
                "with pflash based firmware are not supported"
            )
        specs: dict[str, str] = {}
        for i, arg in enumerate(args):
            if arg != "--diskspec":
                continue
            dev, *champs = args[i + 1].split(",")
            specs[dev] = dict(c.split("=", 1) for c in champs)["file"]
        for dev in dom["disques"]:
            if dev not in specs:
                # Le second refus : sur un disque type='volume', libvirt ne
                # déduit pas le nom du recouvrement.
                raise _Refus(
                    "error: unsupported configuration: cannot generate external "
                    f"snapshot name for disk '{dev}' without source"
                )
        bases = dict(dom["disques"])
        for dev, chemin in specs.items():
            self.volumes[chemin] = set()
            self.backing[chemin] = dom["disques"][dev]
            dom["disques"][dev] = chemin
        dom["snapshots"][snap] = {"overlays": dict(specs), "bases": bases}
        return f"Domain snapshot {snap} created"

    def _delete(self, args: list[str]) -> str:
        nom, snap = args[1], args[2]
        dom = self._domaine(nom)
        if snap not in dom["snapshots"]:
            raise _Refus(f"error: Domain snapshot not found: {snap}")
        etat = dom["snapshots"][snap]
        if "--metadata" in args:
            # Le point de reprise est oublié ; le recouvrement reste la couche
            # vive du disque. Rien n'est orphelin, la chaîne gagne une couche.
            del dom["snapshots"][snap]
            return f"Domain snapshot {snap} deleted"
        if not self.supprime_externe:
            raise _Refus(
                "error: unsupported configuration: deletion of external disk "
                "snapshots is not supported by this libvirt"
            )
        for dev, recouvrement in etat["overlays"].items():
            base = etat["bases"][dev]
            self.volumes[base] |= self.volumes.pop(recouvrement, set())
            self.backing.pop(recouvrement, None)
            dom["disques"][dev] = base
        del dom["snapshots"][snap]
        return f"Domain snapshot {snap} deleted"

    def _vol_delete(self, args: list[str]) -> str:
        chemin = f"{REPERTOIRE}/{args[args.index('--pool') + 2]}"
        if chemin not in self.volumes:
            raise _Refus(f"error: failed to get vol '{chemin}'")
        del self.volumes[chemin]
        self.backing.pop(chemin, None)
        return "Vol deleted"

    def _vol_create(self, args: list[str]) -> str:
        chemin = f"{REPERTOIRE}/{args[2]}"
        self.volumes[chemin] = set()
        self.backing[chemin] = args[args.index("--backing-vol") + 1]
        return "Vol created"


class _Refus(Exception):
    """Ce que libvirt répond quand il refuse : un code non nul et un stderr."""

    def __init__(self, raison: str) -> None:
        self.raison = raison
        super().__init__(raison)


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
    return faux


@pytest.fixture
def hyperviseur(monkeypatch: pytest.MonkeyPatch) -> Hyperviseur:
    faux = Hyperviseur()
    monkeypatch.setattr(libvirt, "run_command", faux)
    # Le préfixe est mémorisé pour tout le processus : le figer évite qu'un
    # sondage `virsh list` s'ajoute aux commandes que les tests comptent.
    monkeypatch.setattr(libvirt, "_prefixe_retenu", [])
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
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    kvm.create(meta, ["control-node.lab", "web1.lab"], "pre-lab")
    assert hyperviseur.cibles("snapshot-create-as") == ["control-node.lab", "web1.lab"]


def test_revert_vise_le_domaine_qui_existe(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    kvm.create(meta, ["control-node.lab"], "pre-lab")
    kvm.revert(meta, ["control-node.lab"], "pre-lab")
    assert hyperviseur.cibles("destroy") == ["control-node.lab"]


def test_delete_vise_le_domaine_qui_existe(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    kvm.create(meta, ["control-node.lab"], "pre-lab")
    kvm.delete(meta, ["control-node.lab"], "pre-lab")
    assert hyperviseur.cibles("snapshot-delete") == ["control-node.lab"]


def test_list_vise_le_domaine_qui_existe(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    kvm.list_(meta, "control-node.lab")
    assert hyperviseur.cibles("snapshot-list") == ["control-node.lab"]


def test_list_rend_les_snapshots_existants(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    kvm.create(meta, ["control-node.lab"], "pre-lab")
    assert kvm.list_(meta, "control-node.lab") == ["pre-lab"]


# ── Le snapshot est externe, parce que l'UEFI l'impose ──────────────────────

def test_le_snapshot_est_externe_faute_de_quoi_l_uefi_le_refuse(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Le défaut d'origine : sans ``--disk-only``, libvirt refuse sur pflash."""
    kvm.create(meta, ["web1.lab"], "pre-lab")

    (commande,) = hyperviseur.jouees("snapshot-create-as")
    assert "--disk-only" in commande
    assert "--atomic" in commande


def test_chaque_disque_recoit_le_chemin_de_son_recouvrement(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Sur un disque type='volume', libvirt refuse de le déduire lui-même."""
    kvm.create(meta, ["web1.lab"], "pre-lab")

    (commande,) = hyperviseur.jouees("snapshot-create-as")
    specs = [commande[i + 1] for i, a in enumerate(commande) if a == "--diskspec"]
    assert specs == [
        f"vda,snapshot=external,file={REPERTOIRE}/web1.lab.qcow2.pre-lab"
    ]


def test_le_cdrom_cloud_init_n_est_jamais_fige(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Lui passer un --diskspec ferait échouer tout le snapshot."""
    kvm.create(meta, ["web1.lab"], "pre-lab")

    (commande,) = hyperviseur.jouees("snapshot-create-as")
    assert not any(spec.startswith("sda,") for spec in commande)


def test_reprendre_un_point_de_reprise_du_meme_nom_le_remplace(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Sinon le second ``dsoxlab run`` échouerait sur un nom déjà pris."""
    kvm.create(meta, ["web1.lab"], "pre-lab")
    hyperviseur.ecrire("web1.lab", "travail-du-premier-run")

    kvm.create(meta, ["web1.lab"], "pre-lab")

    assert kvm.list_(meta, "web1.lab") == ["pre-lab"]
    assert len(hyperviseur.jouees("snapshot-create-as")) == 2


# ── Le retour arrière, prouvé par ce qu'il efface ───────────────────────────

def test_le_retour_arriere_efface_ce_qui_a_ete_ecrit_apres(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Le critère de l'issue, mesuré sur l'état et non sur un code retour."""
    kvm.create(meta, ["web1.lab"], "pre-lab")
    hyperviseur.ecrire("web1.lab", "fichier-ecrit-apres-le-snapshot")
    assert "fichier-ecrit-apres-le-snapshot" in hyperviseur.contenu("web1.lab")

    kvm.revert(meta, ["web1.lab"], "pre-lab")

    assert "fichier-ecrit-apres-le-snapshot" not in hyperviseur.contenu("web1.lab")


def test_le_retour_arriere_garde_ce_qui_precedait_le_snapshot(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Un retour arrière qui viderait le disque de base ne serait pas un filet."""
    hyperviseur.ecrire("web1.lab", "installe-par-le-provisionnement")
    kvm.create(meta, ["web1.lab"], "pre-lab")
    hyperviseur.ecrire("web1.lab", "ecrit-par-l-apprenant")

    kvm.revert(meta, ["web1.lab"], "pre-lab")

    assert hyperviseur.contenu("web1.lab") == {"installe-par-le-provisionnement"}


def test_le_retour_arriere_reste_rejouable(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Le snapshot survit au retour arrière : le filet sert plus d'une fois."""
    kvm.create(meta, ["web1.lab"], "pre-lab")
    kvm.revert(meta, ["web1.lab"], "pre-lab")
    hyperviseur.ecrire("web1.lab", "deuxieme-essai")

    kvm.revert(meta, ["web1.lab"], "pre-lab")

    assert hyperviseur.contenu("web1.lab") == set()
    assert kvm.list_(meta, "web1.lab") == ["pre-lab"]


def test_la_machine_est_arretee_puis_relancee_pour_le_retour_arriere(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Rejeter le recouvrement sous un qemu qui l'a ouvert ne marcherait pas."""
    kvm.create(meta, ["web1.lab"], "pre-lab")

    kvm.revert(meta, ["web1.lab"], "pre-lab")

    verbes = hyperviseur.verbes()
    assert verbes.index("destroy") < verbes.index("vol-create-as") < verbes.index("start")
    assert hyperviseur.domaines["web1.lab"]["etat"] == "running"


def test_une_machine_eteinte_ne_se_reveille_pas_toute_seule(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Le retour arrière ne change pas l'état de marche, il le rétablit."""
    kvm.create(meta, ["web1.lab"], "pre-lab")
    hyperviseur.domaines["web1.lab"]["etat"] = "shut off"

    kvm.revert(meta, ["web1.lab"], "pre-lab")

    assert hyperviseur.jouees("start") == []
    assert hyperviseur.domaines["web1.lab"]["etat"] == "shut off"


def test_le_retour_arriere_refuse_une_couche_qui_n_est_plus_du_dessus(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Jeter la mauvaise couche détruirait des écritures jamais couvertes."""
    kvm.create(meta, ["web1.lab"], "pre-un")
    kvm.create(meta, ["web1.lab"], "pre-deux")
    hyperviseur.ecrire("web1.lab", "ecrit-sous-le-second-snapshot")

    with pytest.raises(SnapshotError) as leve:
        kvm.revert(meta, ["web1.lab"], "pre-un")

    assert "pre-un" in str(leve.value)
    assert "ecrit-sous-le-second-snapshot" in hyperviseur.contenu("web1.lab")


def test_un_snapshot_sans_disque_fige_ne_passe_pas_pour_un_filet(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Une liste vide ferait passer un retour arrière impossible pour un succès."""
    hyperviseur.domaines["web1.lab"]["snapshots"]["vide"] = {"overlays": {}, "bases": {}}

    with pytest.raises(SnapshotError):
        kvm.revert(meta, ["web1.lab"], "vide")


# ── Supprimer le point de reprise, sans rien laisser derrière ───────────────

def test_supprimer_le_point_de_reprise_garde_l_etat_courant(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Supprimer un snapshot n'est pas revenir en arrière."""
    kvm.create(meta, ["web1.lab"], "pre-lab")
    hyperviseur.ecrire("web1.lab", "travail-de-l-apprenant")

    kvm.delete(meta, ["web1.lab"], "pre-lab")

    assert "travail-de-l-apprenant" in hyperviseur.contenu("web1.lab")
    assert kvm.list_(meta, "web1.lab") == []


def test_supprimer_ne_laisse_aucun_fichier_de_recouvrement(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Le cousin de #107 : l'artefact que Terraform ne connaît pas."""
    avant = hyperviseur.fichiers()
    kvm.create(meta, ["web1.lab"], "pre-lab")
    assert hyperviseur.fichiers() != avant

    kvm.delete(meta, ["web1.lab"], "pre-lab")

    assert hyperviseur.fichiers() == avant


def test_un_libvirt_ancien_retombe_sur_l_oubli_de_la_metadonnee(
    monkeypatch: pytest.MonkeyPatch,
    meta: RepoMetadata,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Sans fusion possible, le recouvrement reste la couche vive : pas un orphelin."""
    faux = Hyperviseur(supprime_externe=False)
    monkeypatch.setattr(libvirt, "run_command", faux)
    monkeypatch.setattr(libvirt, "_prefixe_retenu", [])

    kvm.create(meta, ["web1.lab"], "pre-lab")
    faux.ecrire("web1.lab", "travail-de-l-apprenant")

    with caplog.at_level(logging.WARNING, logger="dsoxlab.infra.snapshot.kvm"):
        kvm.delete(meta, ["web1.lab"], "pre-lab")

    assert kvm.list_(meta, "web1.lab") == []
    assert "travail-de-l-apprenant" in faux.contenu("web1.lab")
    assert faux.domaines["web1.lab"]["disques"]["vda"] in faux.fichiers()
    # Le journal est en anglais depuis #140 : l'assertion suit la règle.
    assert "without merge" in caplog.text


def test_delete_tolere_un_domaine_absent_mais_le_journalise(
    hyperviseur: Hyperviseur,
    meta: RepoMetadata,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Un nettoyage ne doit pas échouer sur ce qui a déjà disparu, mais il
    doit dire ce qu'il n'a pas trouvé."""
    kvm.create(meta, ["web1.lab"], "pre-lab")

    with caplog.at_level(logging.WARNING, logger="dsoxlab.infra.snapshot.kvm"):
        kvm.delete(meta, ["absent.lab", "web1.lab"], "pre-lab")

    assert "absent.lab" in caplog.text
    # L'hôte suivant est tout de même traité : une absence n'interrompt pas.
    assert hyperviseur.cibles("snapshot-delete") == ["web1.lab"]


# ── La purge, avant que Terraform ne passe ──────────────────────────────────

def test_la_purge_retire_le_snapshot_et_son_fichier(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Terraform ne connaît pas le recouvrement : il lui survivrait."""
    avant = hyperviseur.fichiers()
    kvm.create(meta, ["web1.lab", "db1.lab"], "pre-lab")

    retires = kvm.purge(meta, ["web1.lab", "db1.lab"])

    assert sorted(retires) == [
        f"{REPERTOIRE}/db1.lab.qcow2.pre-lab",
        f"{REPERTOIRE}/web1.lab.qcow2.pre-lab",
    ]
    assert hyperviseur.fichiers() == avant
    assert kvm.list_(meta, "web1.lab") == []


def test_la_purge_ignore_les_machines_deja_disparues(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Une destruction partielle ne doit pas bloquer sur ce qui n'est plus là."""
    kvm.create(meta, ["web1.lab"], "pre-lab")

    retires = kvm.purge(meta, ["absent.lab", "web1.lab"])

    assert retires == [f"{REPERTOIRE}/web1.lab.qcow2.pre-lab"]


def test_la_purge_ne_conclut_pas_a_l_absence_quand_virsh_est_muet(
    monkeypatch: pytest.MonkeyPatch,
    meta: RepoMetadata,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Une interrogation impossible n'est jamais une absence."""

    def virsh_absent(cmd: list[str], **kwargs: Any) -> CommandResult:
        raise CommandError(
            cmd, CommandResult(returncode=-1, stdout="", stderr="Commande introuvable: virsh")
        )

    monkeypatch.setattr(libvirt, "run_command", virsh_absent)
    monkeypatch.setattr(libvirt, "_prefixe_retenu", [])

    with caplog.at_level(logging.WARNING, logger="dsoxlab.infra.snapshot.kvm"):
        assert kvm.purge(meta, ["web1.lab"]) == []

    assert "purge" in caplog.text


# ── Ce que chaque opération fait d'un domaine absent ────────────────────────

def test_create_leve_sur_un_domaine_absent(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """Un snapshot silencieusement non pris rendrait le rollback illusoire."""
    with pytest.raises(DomainNotFound):
        kvm.create(meta, ["absent.lab"], "pre-lab")
    assert hyperviseur.jouees("snapshot-create-as") == []


def test_revert_leve_sur_un_domaine_absent(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    with pytest.raises(DomainNotFound):
        kvm.revert(meta, ["absent.lab"], "pre-lab")


def test_list_leve_sur_un_domaine_absent(
    hyperviseur: Hyperviseur, meta: RepoMetadata
) -> None:
    """« Pas de snapshot » et « pas de domaine » appellent des gestes opposés."""
    with pytest.raises(DomainNotFound):
        kvm.list_(meta, "absent.lab")


# ── « required » veut dire required ─────────────────────────────────────────
#
# Le critère le plus important de l'issue #127, et le seul qui empêche la
# fonctionnalité de se recasser en silence : un point de reprise qu'on n'a pas
# pris doit faire échouer `dsoxlab run`. Avant, il sortait en 0.

def _lab_vm(tmp_path: Path, *, filet: bool) -> Any:
    """Un lab ``runtime: vm`` dont le setup.yaml existe, filet déclaré ou non."""
    from dsoxlab.models.lab import LabDefinition, ValidationConfig
    from dsoxlab.models.runtime import RuntimeConfig, RuntimeType, Target

    racine = tmp_path / "labs" / "demo"
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "setup.yaml").write_text("- hosts: lab_target\n")
    (racine / "cleanup.yaml").write_text("- hosts: lab_target\n")
    return LabDefinition(
        id="demo-vm",
        title="Demo VM",
        level="l1",
        skills=["s"],
        runtime=RuntimeConfig(
            type=RuntimeType.VM,
            targets=[Target(name="t", host="web1.lab")],
            snapshot_required=filet,
        ),
        distros=["alma9"],
        doc_url="https://example.test/doc",
        validation=ValidationConfig(),
        path=racine,
    )


class PlaybooksJoues:
    """Remplace ``ansible-runner`` : note quels playbooks auraient été joués."""

    def __init__(self) -> None:
        self.joues: list[str] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.joues.append(Path(kwargs["playbook_path"]).name)
        return type("R", (), {"ok": True, "rc": 0, "status": "successful", "stats": {}})()


@pytest.fixture
def runtime_vm(monkeypatch: pytest.MonkeyPatch, meta: RepoMetadata) -> Any:
    """Un VmRuntime dont le meta.yml et l'inventaire sont neutralisés."""
    from dsoxlab.infra import ansible as ansible_infra
    from dsoxlab.runtimes.vm import VmRuntime

    joues = PlaybooksJoues()
    monkeypatch.setattr(ansible_infra, "run_playbook", joues)
    runtime = VmRuntime()
    monkeypatch.setattr(runtime, "_repo_meta", lambda lab: meta)
    monkeypatch.setattr(runtime, "_inventory", lambda repo_meta, target: {})
    runtime.playbooks = joues  # type: ignore[attr-defined]
    return runtime


@pytest.fixture
def hyperviseur_qui_refuse(monkeypatch: pytest.MonkeyPatch) -> Hyperviseur:
    """Un hyperviseur qui ne sait pas prendre le snapshot demandé."""
    faux = Hyperviseur(refuse_snapshot=True)
    monkeypatch.setattr(libvirt, "run_command", faux)
    monkeypatch.setattr(libvirt, "_prefixe_retenu", [])
    return faux


def test_run_echoue_quand_le_point_de_reprise_exige_ne_peut_pas_etre_pris(
    hyperviseur_qui_refuse: Hyperviseur, tmp_path: Path, runtime_vm: Any
) -> None:
    """Le défaut central : l'échec sortait en 0 et le lab démarrait sans filet."""
    with pytest.raises(RuntimeError) as leve:
        runtime_vm.start(_lab_vm(tmp_path, filet=True))

    message = str(leve.value)
    assert "snapshot_required" in message
    assert "demo-vm" in message
    assert "web1.lab" in message


def test_le_setup_n_est_pas_joue_quand_le_filet_a_manque(
    hyperviseur_qui_refuse: Hyperviseur, tmp_path: Path, runtime_vm: Any
) -> None:
    """Échouer après avoir modifié la machine ne vaudrait guère mieux que se taire."""
    with pytest.raises(RuntimeError):
        runtime_vm.start(_lab_vm(tmp_path, filet=True))

    assert runtime_vm.playbooks.joues == []


def test_un_lab_sans_filet_demarre_sans_toucher_a_l_hyperviseur(
    hyperviseur: Hyperviseur, tmp_path: Path, runtime_vm: Any
) -> None:
    """``snapshot_required: false`` reste la déclaration de ceux qui s'en passent."""
    runtime_vm.start(_lab_vm(tmp_path, filet=False))

    assert runtime_vm.playbooks.joues == ["setup.yaml"]
    assert hyperviseur.commandes == []


def test_le_point_de_reprise_est_pris_avant_le_setup(
    hyperviseur: Hyperviseur, meta: RepoMetadata, tmp_path: Path, runtime_vm: Any
) -> None:
    """Le prendre après figerait un état déjà modifié : le filet ne servirait à rien."""
    runtime_vm.start(_lab_vm(tmp_path, filet=True))

    assert runtime_vm.playbooks.joues == ["setup.yaml"]
    assert kvm.list_(meta, "web1.lab") == ["pre-demo-vm"]


def test_clean_retire_le_point_de_reprise_et_son_fichier(
    hyperviseur: Hyperviseur, tmp_path: Path, runtime_vm: Any
) -> None:
    """Le laisser abandonnerait dans le pool un fichier que Terraform ignore."""
    avant = hyperviseur.fichiers()
    lab = _lab_vm(tmp_path, filet=True)
    runtime_vm.start(lab)

    runtime_vm.clean(lab)

    assert runtime_vm.playbooks.joues == ["setup.yaml", "cleanup.yaml"]
    assert hyperviseur.fichiers() == avant


def test_reset_revient_au_point_de_reprise_au_lieu_du_cleanup(
    hyperviseur: Hyperviseur, tmp_path: Path, runtime_vm: Any
) -> None:
    """C'est là que le filet sert, et ce qui donne enfin un effet à ce champ."""
    lab = _lab_vm(tmp_path, filet=True)
    runtime_vm.start(lab)
    hyperviseur.ecrire("web1.lab", "degat-fait-par-l-apprenant")

    runtime_vm.reset(lab)

    assert "degat-fait-par-l-apprenant" not in hyperviseur.contenu("web1.lab")
    assert runtime_vm.playbooks.joues == ["setup.yaml", "setup.yaml"]


def test_reset_sans_filet_declare_rejoue_le_cleanup_comme_avant(
    hyperviseur: Hyperviseur, tmp_path: Path, runtime_vm: Any
) -> None:
    """Les catalogues déclarent tous ``false`` : leur comportement ne bouge pas."""
    lab = _lab_vm(tmp_path, filet=False)

    runtime_vm.reset(lab)

    assert runtime_vm.playbooks.joues == ["cleanup.yaml", "setup.yaml"]
    assert hyperviseur.commandes == []
