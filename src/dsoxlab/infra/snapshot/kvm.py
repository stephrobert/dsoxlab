"""Backend snapshot KVM via ``virsh`` : **externe**, parce que l'UEFI l'impose.

Ce module prenait des snapshots **internes** (``snapshot-create-as`` sans
``--disk-only``). Sur les machines que ``dsoxlab provision`` crée réellement,
cette commande ne peut pas aboutir : le template Terraform packagé ici impose
``firmware = "efi"`` — les images cloud modernes n'embarquent plus de
bootloader BIOS — et libvirt refuse le snapshot interne d'un domaine dont le
firmware est en pflash ::

    error: Operation not supported: internal snapshots of a VM with pflash
           based firmware are not supported

Le geste juste est donc le snapshot **externe** (``--disk-only --atomic``), qui
fige le disque en le figeant : libvirt crée un fichier de **recouvrement**
(overlay qcow2), y bascule le domaine, et le disque d'origine devient
immuable. Trois conséquences, assumées ici plutôt que découvertes plus tard.

**1. Le nom du fichier de recouvrement ne peut pas être laissé à libvirt.**
Sur un disque ``type='volume'`` — la forme exacte que produit le template
Terraform — libvirt refuse de le déduire ::

    error: unsupported configuration: cannot generate external snapshot name
           for disk 'vda' without source

``create`` passe donc un ``--diskspec`` par disque inscriptible, avec un chemin
qu'il calcule : ``<disque>.<nom du snapshot>``, à côté du disque.

**2. Le retour arrière n'est pas un ``snapshot-revert``.** libvirt le refuse sur
un snapshot externe (``Invalid target domain state 'disk-snapshot'``), et ce
jusqu'à des versions récentes. Revenir en arrière, c'est **jeter le
recouvrement** : on arrête le domaine, on supprime le fichier de recouvrement,
on en recrée un vide adossé au même disque de base, on redémarre. Le chemin ne
change pas, donc le XML du domaine n'est jamais réécrit — c'est ce qui rend
l'opération rejouable et sans effet de bord.

**3. L'état mémoire n'est pas capturé.** ``--disk-only`` fige le disque, pas la
RAM : le retour arrière redémarre la machine depuis un état disque cohérent,
il ne la replace pas dans la seconde d'avant. Pour un lab c'est le bon
compromis, et c'est écrit dans le contrat pour que personne n'attende autre
chose.

Tout passe par ``virsh`` et par **lui seul**, y compris la manipulation des
fichiers : ``vol-delete`` et ``vol-create-as`` s'exécutent dans libvirtd, donc
avec ses droits. Un ``qemu-img`` lancé en direct échouerait sur la moitié des
postes, ceux où ``virsh`` est joignable par appartenance au groupe ``libvirt``
et non par ``sudo``, et où le pool n'est pas accessible en écriture à
l'utilisateur.

**Le nom du domaine n'est pas déduit, il est résolu** (voir ``infra.libvirt``).
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import PurePosixPath

from ...i18n import _
from ...models.repo import RepoMetadata
from ...utils.shell import CommandError
from ..libvirt import (
    RUNNING_STATES,
    DomainNotFound,
    domain_state,
    list_domains,
    resolve_domain,
    run_virsh,
)
from . import SnapshotError

logger = logging.getLogger(__name__)

#: La description posée sur chaque snapshot. Elle sert à un humain qui lit un
#: ``virsh snapshot-list`` et se demande d'où sort ce point de reprise.
DESCRIPTION = "dsoxlab checkpoint"

#: Fusionner un recouvrement dans son disque de base recopie des données : sur
#: un lab qui a beaucoup écrit, cela dépasse la minute. Le timeout des
#: interrogations ne convient pas ici.
_TIMEOUT_LONG = 900


@dataclass(frozen=True)
class Layer:
    """Une couche de recouvrement, et le disque qu'elle recouvre.

    ``base_pool`` peut être ``None`` : un disque déclaré par chemin de fichier
    n'a pas de pool dans le XML, il faut le demander à libvirt.
    """

    target: str
    overlay: str
    base: str
    base_format: str
    base_pool: str | None = None


# ── lecture du XML de libvirt ───────────────────────────────────────────────

def _xml(args: list[str], *, timeout: int = 60) -> ET.Element:
    """Rend la racine du document XML que ``virsh <args>`` produit."""
    result = run_virsh(args, timeout=timeout)
    return ET.fromstring(result.stdout)  # noqa: S314 — sortie de notre propre virsh


def _source_path(element: ET.Element | None) -> str | None:
    """Le chemin réel derrière un ``<source>``, quelle que soit sa forme.

    libvirt en écrit deux : ``<source file='/chemin'/>`` et
    ``<source pool='P' volume='V'/>``. Le template Terraform produit la
    seconde, et c'est précisément celle que le code d'origine ne savait pas
    lire.
    """
    if element is None:
        return None
    source = element if element.tag == "source" else element.find("source")
    if source is None:
        return None
    fichier = source.get("file")
    if fichier:
        return fichier
    pool, volume = source.get("pool"), source.get("volume")
    if pool and volume:
        return run_virsh(["vol-path", "--pool", pool, volume]).stdout.strip()
    return None


def _writable_disks(domain: str) -> dict[str, str]:
    """Les disques que le snapshot doit figer : ``{cible: chemin actuel}``.

    Écarte les périphériques qui ne sont pas des disques (le cdrom cloud-init)
    et ceux en lecture seule : libvirt les ignore de toute façon, et leur
    passer un ``--diskspec`` le ferait échouer.
    """
    racine = _xml(["dumpxml", domain])
    disques: dict[str, str] = {}
    for disque in racine.findall("./devices/disk"):
        if disque.get("device") != "disk" or disque.find("readonly") is not None:
            continue
        cible = disque.find("target")
        chemin = _source_path(disque)
        if cible is None or not chemin:
            continue
        dev = cible.get("dev")
        if dev:
            disques[dev] = chemin
    return disques


def _snapshot_layers(domain: str, name: str) -> list[Layer]:
    """Ce que le snapshot ``name`` a créé, et ce qu'il recouvre.

    Tout se lit dans un seul document : ``snapshot-dumpxml`` porte à la fois
    les fichiers de recouvrement (section ``<disks>``) et le domaine **tel
    qu'il était** au moment du snapshot (section ``<domain>``), donc les
    disques de base et leur pool.

    Raises:
        SnapshotError: si le snapshot n'a figé aucun disque, ou si un disque
            figé n'a pas de base identifiable. Rendre une liste vide ferait
            passer un retour arrière impossible pour un retour arrière réussi.
    """
    racine = _xml(["snapshot-dumpxml", domain, name])

    recouvrements: dict[str, str] = {}
    for disque in racine.findall("./disks/disk"):
        if disque.get("snapshot") != "external":
            continue
        dev, chemin = disque.get("name"), _source_path(disque)
        if dev and chemin:
            recouvrements[dev] = chemin
    if not recouvrements:
        raise SnapshotError(_("err_snapshot_no_disk", snapshot=name, domain=domain))

    couches: list[Layer] = []
    for disque in racine.findall("./domain/devices/disk"):
        cible = disque.find("target")
        dev = cible.get("dev") if cible is not None else None
        if dev is None or dev not in recouvrements:
            continue
        base = _source_path(disque)
        if not base:
            raise SnapshotError(
                _("err_snapshot_no_base", snapshot=name, domain=domain, disk=dev)
            )
        pilote = disque.find("driver")
        source = disque.find("source")
        couches.append(Layer(
            target=dev,
            overlay=recouvrements[dev],
            base=base,
            base_format=(pilote.get("type") if pilote is not None else None) or "qcow2",
            base_pool=source.get("pool") if source is not None else None,
        ))

    manquants = sorted(set(recouvrements) - {c.target for c in couches})
    if manquants:
        raise SnapshotError(
            _("err_snapshot_no_base", snapshot=name, domain=domain,
              disk=", ".join(manquants))
        )
    return couches


def _snapshot_names(domain: str) -> list[str]:
    """Les snapshots que libvirt connaît pour ce domaine."""
    result = run_virsh(["snapshot-list", domain, "--name"], check=False)
    if not result.ok:
        return []
    return [ligne.strip() for ligne in result.stdout.splitlines() if ligne.strip()]


# ── manipulation des volumes, par libvirt et jamais en direct ───────────────

def _pool_of(layer: Layer) -> str:
    """Le pool où vit le disque de base, donc aussi son recouvrement.

    Le XML le donne quand le disque est déclaré en ``pool``/``volume``. Sinon
    on le demande à libvirt à partir du chemin.
    """
    if layer.base_pool:
        return layer.base_pool
    return run_virsh(["vol-pool", layer.base]).stdout.strip()


def _capacity(pool: str, path: str) -> int:
    """La taille virtuelle du disque de base, en octets.

    Un recouvrement recréé doit la reprendre à l'identique : un qcow2 plus
    petit que sa base tronquerait le disque vu par la machine.
    """
    racine = _xml(["vol-dumpxml", "--pool", pool, path])
    capacite = racine.find("capacity")
    octets = (capacite.text or "").strip() if capacite is not None else ""
    if not octets:
        raise SnapshotError(_("err_snapshot_no_capacity", path=path))
    return int(octets)


def _delete_volume(pool: str, path: str) -> bool:
    """Retire un fichier de recouvrement du pool. Rend ``False`` s'il n'y était pas.

    Le rafraîchissement n'est pas une précaution : libvirt tient un catalogue
    en mémoire, et un fichier que ``snapshot-create-as`` vient de créer n'y
    figure pas encore. Sans lui, ``vol-delete`` répond « volume introuvable »
    sur un fichier bien présent sur le disque.
    """
    run_virsh(["pool-refresh", pool], check=False, timeout=120)
    nom = PurePosixPath(path).name
    result = run_virsh(["vol-delete", "--pool", pool, nom], check=False, timeout=120)
    if not result.ok:
        logger.warning(
            "vol-delete had no effect for %s in %s: %s",
            nom, pool, result.stderr.strip(),
        )
    return result.ok


def _reset_overlay(layer: Layer) -> None:
    """Rend le fichier de recouvrement vide, sans toucher au XML du domaine.

    C'est **tout** le retour arrière : le domaine continue de pointer sur le
    même chemin, qui ne contient plus rien, donc il relit le disque de base.
    Recréer plutôt que réécrire garde le snapshot valide, donc rejouable.
    """
    pool = _pool_of(layer)
    capacite = _capacity(pool, layer.base)
    _delete_volume(pool, layer.overlay)
    run_virsh(
        [
            "vol-create-as", pool, PurePosixPath(layer.overlay).name, str(capacite),
            "--format", "qcow2",
            "--backing-vol", layer.base,
            "--backing-vol-format", layer.base_format,
        ],
        timeout=120,
    )


# ── l'interface du backend ──────────────────────────────────────────────────

def create(repo_meta: RepoMetadata, hosts: list[str], name: str) -> None:
    """Fige le disque de chaque domaine listé, sous le nom ``name``.

    Rejouable : un snapshot du même nom est d'abord supprimé, de sorte qu'un
    second ``dsoxlab run`` reparte d'un point de reprise à jour au lieu
    d'échouer sur un nom déjà pris.

    Raises:
        DomainNotFound: si un hôte ne correspond à aucun domaine.
        CommandError: si libvirt refuse le snapshot. **L'appelant doit laisser
            remonter** quand le lab déclare ``snapshot_required: true`` : un
            filet qu'on n'a pas tendu ne se signale pas par un avertissement.
    """
    del repo_meta  # le domaine se résout contre libvirt, pas contre le meta.yml
    known = list_domains()
    for fqdn in hosts:
        domain = resolve_domain(fqdn, known=known)
        if name in _snapshot_names(domain):
            logger.info("snapshot %s already present on %s: replaced", name, domain)
            _drop(domain, name)
        args = [
            "snapshot-create-as",
            "--domain", domain,
            "--name", name,
            "--description", DESCRIPTION,
            "--disk-only",
            "--atomic",
        ]
        for cible, chemin in sorted(_writable_disks(domain).items()):
            args += ["--diskspec", f"{cible},snapshot=external,file={chemin}.{name}"]
        logger.info("virsh snapshot-create-as %s %s (external)", domain, name)
        run_virsh(args, timeout=300)


def revert(repo_meta: RepoMetadata, hosts: list[str], name: str) -> None:
    """Ramène chaque domaine à l'état disque du snapshot ``name``.

    La machine est arrêtée le temps de l'opération, puis redémarrée si elle
    tournait. L'état mémoire n'est pas restauré : il n'a jamais été capturé.

    Raises:
        DomainNotFound: si un hôte ne correspond à aucun domaine.
        SnapshotError: si le snapshot n'est plus la couche du dessus. Le cas
            existe — un second snapshot posé par-dessus, une fusion faite à la
            main — et jeter la mauvaise couche détruirait des données.
    """
    del repo_meta
    known = list_domains()
    for fqdn in hosts:
        domain = resolve_domain(fqdn, known=known)
        couches = _snapshot_layers(domain, name)
        _check_top_layer(domain, name, couches)

        tournait = domain_state(domain) in RUNNING_STATES
        if tournait:
            run_virsh(["destroy", domain], timeout=120)
        for couche in couches:
            logger.info("revert %s:%s -> %s", domain, couche.target, couche.base)
            _reset_overlay(couche)
        if tournait:
            run_virsh(["start", domain], timeout=300)


def _check_top_layer(domain: str, name: str, couches: list[Layer]) -> None:
    """Le domaine écrit-il bien dans les recouvrements de CE snapshot ?

    Raises:
        SnapshotError: sinon. C'est le garde-fou qui empêche de jeter une
            couche qui porte autre chose que ce qu'on croit jeter.
    """
    actuels = _writable_disks(domain)
    for couche in couches:
        actuel = actuels.get(couche.target)
        if actuel != couche.overlay:
            raise SnapshotError(_(
                "err_snapshot_not_top_layer",
                snapshot=name, domain=domain, disk=couche.target,
                expected=couche.overlay, found=actuel or "-",
            ))


def delete(repo_meta: RepoMetadata, hosts: list[str], name: str) -> None:
    """Supprime le point de reprise ``name``, en gardant l'état courant.

    Best-effort assumé : un snapshot déjà absent, comme un domaine déjà
    détruit, ne doit pas faire échouer un nettoyage. Les deux cas sont
    journalisés en nommant ce qui manque.
    """
    del repo_meta
    known = list_domains()
    for fqdn in hosts:
        try:
            domain = resolve_domain(fqdn, known=known)
        except DomainNotFound as exc:
            logger.warning("snapshot-delete skipped: %s", exc)
            continue
        _drop(domain, name)


def _drop(domain: str, name: str) -> None:
    """Retire un snapshot externe : fusion du recouvrement, puis oubli.

    ``virsh snapshot-delete`` fait les deux d'un coup sur un libvirt récent :
    il recopie le recouvrement dans le disque de base, y repointe le domaine
    et supprime le fichier. Sur un libvirt qui ne sait pas encore supprimer un
    snapshot externe, on retombe sur ``--metadata`` : le point de reprise
    disparaît, le recouvrement **reste le disque vif** du domaine. Ce n'est
    pas un orphelin — rien ne le référence en trop — mais la chaîne gagne une
    couche, et cela se dit.
    """
    try:
        run_virsh(["snapshot-delete", domain, name], timeout=_TIMEOUT_LONG)
        return
    except CommandError as exc:
        logger.warning(
            "snapshot-delete failed for %s/%s: %s",
            domain, name, exc.result.stderr.strip(),
        )
    result = run_virsh(
        ["snapshot-delete", domain, name, "--metadata"], check=False, timeout=120
    )
    if result.ok:
        logger.warning(
            "snapshot %s/%s dropped without merge: the overlay remains the "
            "live disk layer", domain, name,
        )
    else:
        logger.warning(
            "snapshot %s/%s not deleted: %s", domain, name, result.stderr.strip()
        )


def purge(repo_meta: RepoMetadata, hosts: list[str]) -> list[str]:
    """Retire tout snapshot **et son fichier de recouvrement**, avant destruction.

    Terraform ne détruit que ce qu'il a créé. Un fichier de recouvrement lui
    est invisible : il n'est dans aucun state, et le volume qu'il recouvre est
    supprimé sous lui. Sans ce passage, il survit à la machine qu'il servait —
    le cousin exact des domaines orphelins de #107.

    L'état courant est ici perdu volontairement : tout ce qui porte ces
    disques est sur le point de disparaître.

    Returns:
        Les chemins des fichiers de recouvrement réellement retirés. Vide si
        l'hyperviseur n'est pas interrogeable : une interrogation impossible
        n'est jamais une absence, et l'appelant doit le dire plutôt que
        conclure que rien ne traîne.
    """
    del repo_meta
    retires: list[str] = []
    try:
        known = list_domains()
    except CommandError as exc:
        logger.warning("cannot purge snapshots: %s", exc)
        return retires

    for fqdn in hosts:
        try:
            domain = resolve_domain(fqdn, known=known)
        except DomainNotFound:
            continue
        for name in _snapshot_names(domain):
            try:
                couches = _snapshot_layers(domain, name)
            except (SnapshotError, CommandError) as exc:
                logger.warning("snapshot %s/%s unreadable: %s", domain, name, exc)
                couches = []
            run_virsh(
                ["snapshot-delete", domain, name, "--metadata"],
                check=False, timeout=120,
            )
            for couche in couches:
                if _delete_volume(_pool_of(couche), couche.overlay):
                    retires.append(couche.overlay)
    return retires


def list_(repo_meta: RepoMetadata, host: str) -> list[str]:
    """Retourne la liste des snapshots libvirt pour ``host``.

    Raises:
        DomainNotFound: si l'hôte ne correspond à aucun domaine. Rendre une
            liste vide confondrait « ce domaine n'a pas de snapshot » avec
            « ce domaine n'existe pas », qui appellent des gestes opposés.
    """
    del repo_meta
    return _snapshot_names(resolve_domain(host))
