"""Les pools de stockage libvirt, AppArmor, et l'explication des échecs de provision.

Extrait de ``services/doctor.py`` (issue #199), sans changement de
comportement. Voir ce module pour les principes du diagnostic.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from ...i18n import _
from ...utils.shell import CommandResult
from .modele import STATE_UNKNOWN, Check, Fix, _check, _doctor, _fix, _installer


def creer_pool_fix(pool: str) -> Fix:
    """Le correctif qui crée un pool libvirt de bout en bout.

    Les quatre étapes comptent : ``pool-define-as`` seul laisse un pool défini
    mais **inactif**, dans lequel Terraform ne peut rien écrire.
    """
    return _fix(
        ["sudo", "virsh", "pool-define-as", pool, "dir",
         "--target", "/var/lib/libvirt/images"],
        ["sudo", "virsh", "pool-build", pool],
        ["sudo", "virsh", "pool-start", pool],
        ["sudo", "virsh", "pool-autostart", pool],
    )


def demarrer_pool_fix(pool: str) -> Fix:
    """Le correctif qui démarre un pool déjà défini, et le rend permanent."""
    return _fix(
        ["sudo", "virsh", "pool-start", pool],
        ["sudo", "virsh", "pool-autostart", pool],
    )


def creer_pool_command(pool: str) -> str:
    """La création du pool, en une ligne à copier après un échec de provision."""
    return creer_pool_fix(pool).display


def demarrer_pool_command(pool: str) -> str:
    """Le démarrage du pool, en une ligne à copier après un échec de provision."""
    return demarrer_pool_fix(pool).display


def _pools_libvirt(*, definis: bool) -> list[str] | None:
    """Noms des pools libvirt : les actifs seuls, ou tous ceux qui sont définis.

    Rendre ``None`` quand la sonde n'aboutit pas. ``virsh`` absent ou muet est
    l'affaire du contrôle KVM ; le redire ici empilerait deux rouges pour une
    seule cause. Mais ``None`` n'est pas un vert : le contrôle appelant doit le
    traduire en :data:`STATE_UNKNOWN`, jamais en « tout va bien ».

    La sonde passe par :func:`~dsoxlab.infra.libvirt.run_virsh` : invoquer
    ``virsh`` en direct échouait systématiquement sur les machines où l'URI
    système exige ``sudo``, et l'échec permanent de la sonde peignait le
    contrôle en vert permanent.
    """
    args = ["pool-list"]
    if definis:
        args.append("--all")
    args.append("--name")
    probe: CommandResult | None = _doctor()._sonde_virsh(args)
    if probe is None or not probe.ok:
        return None
    return probe.stdout.split()


def _check_libvirt_pool(pool: str) -> Check:
    """Le template KVM écrit ses volumes dans un pool libvirt.

    Une Ubuntu fraîche avec ``libvirt-daemon-system`` n'en déclare aucun :
    ``virsh pool-list --all`` est vide, et ``provision`` échoue sur un « Pool
    Not Found » brut de Terraform, que rien n'explique.

    Le nom vient de ``meta.yml: infra.providers.kvm.storage_pool``, faute de
    quoi ``default``. Le contrôle porte donc sur le pool que le dépôt vise
    réellement, et non sur un nom présumé.

    Absent et inactif sont **deux états distincts**, et les confondre faisait
    mentir le diagnostic. ``virsh pool-list --name`` ne liste que les pools
    **actifs** : un pool défini mais jamais démarré n'y figure pas, le contrôle
    le déclarait donc introuvable et proposait un ``pool-define-as`` qui échoue
    aussitôt (« pool already exists »). Or Terraform, lui, sort sur une erreur
    entièrement différente (« storage pool 'x' is not active »), et le geste qui
    débloque est ``pool-start``, pas une création.
    """
    actifs = _pools_libvirt(definis=False)
    if actifs is None:
        # La sonde n'a pas pu regarder : ni vert, ni rouge. L'ancien code
        # rendait ``ok=True`` ici — le vert affiché faute d'avoir mesuré,
        # exactement le mensonge que STATE_UNKNOWN existe pour interdire.
        return _check(
            "libvirt_pool", False, _("detail_pool_unknown"),
            forced_state=STATE_UNKNOWN,
        )
    if pool in actifs:
        return _check("libvirt_pool", True, pool)

    definis = _pools_libvirt(definis=True)
    if definis is None:
        # Le pool n'est pas actif, mais sans la liste des pools définis on ne
        # sait pas si le geste est « créer » ou « démarrer » : proposer l'un
        # des deux au hasard ferait échouer la remédiation sur l'autre cas.
        return _check(
            "libvirt_pool", False, _("detail_pool_unknown"),
            forced_state=STATE_UNKNOWN,
        )
    if pool in definis:
        return _check(
            "libvirt_pool", False, _("detail_pool_inactive", pool=pool),
            fix=demarrer_pool_fix(pool),
        )
    return _check(
        "libvirt_pool", False, _("detail_pool_missing", pool=pool),
        fix=creer_pool_fix(pool),
    )


#: Fichier d'override AppArmor qui rend les images libvirt lisibles par qemu.
_APPARMOR_OVERRIDE = Path("/etc/apparmor.d/local/abstractions/libvirt-qemu")


def apparmor_override_absent() -> bool:
    """AppArmor est-il actif SANS l'override qui autorise les images libvirt ?

    Volontairement **pas** un ``Check``. Sur une Ubuntu 24.04 fraîche, l'absence
    de cet override fait échouer tout démarrage de domaine : ``virt-aa-helper``
    construit le profil à partir du XML, or terraform-provider-libvirt déclare
    ses disques par référence de pool (``<disk type='volume'>``), une forme
    qu'il ne sait pas résoudre en chemin. Aucun disque n'entre dans le profil,
    et qemu se voit tout refuser par un « Permission denied » qui ressemble à un
    problème de propriétaire sans en être un.

    Mais l'inverse n'est pas vrai, et c'est ce qui interdit d'en faire un
    diagnostic préventif : mesuré sur une machine où AppArmor est actif, où cet
    override est absent, et où huit domaines libvirt tournent pourtant sans
    incident. La version de ``virt-aa-helper``, le pilote de sécurité déclaré
    dans ``qemu.conf`` et l'emplacement réel des images changent la conclusion.

    Ce module s'interdit précisément ce genre d'affirmation : un rouge affiché
    devant une commande qui fonctionne est ce qui décourageait au premier
    lancement. On garde donc l'information pour le seul moment où elle est
    certaine, celui où le provisionnement a réellement échoué là-dessus.
    """
    if not Path("/sys/module/apparmor/parameters/enabled").is_file():
        return False
    try:
        return "/var/lib/libvirt/images/" not in _APPARMOR_OVERRIDE.read_text(
            encoding="utf-8"
        )
    except OSError:
        return True


def apparmor_fix_command() -> str:
    """La commande qui pose l'override. Le droit ``k`` n'est pas décoratif :
    avec ``r`` seul, l'erreur devient « Failed to lock byte 100 »."""
    return (
        "echo '  /var/lib/libvirt/images/** rwk,' | sudo tee "
        f"{_APPARMOR_OVERRIDE} && sudo systemctl restart libvirtd"
    )


#: Le nom du pool tel que libvirt le cite dans ses deux messages d'échec.
#: L'extraire évite de nommer « default » à un dépôt qui vise le sien via
#: ``meta.yml: infra.providers.kvm.storage_pool`` : la remédiation porterait
#: alors sur un pool que personne n'utilise.
_POOL_ABSENT = re.compile(
    r"no storage pool with matching name '([^']+)'"
    r"|storage pool '([^']+)' not found",
    re.IGNORECASE,
)
_POOL_INACTIF = re.compile(
    r"storage pool '([^']+)' is not active", re.IGNORECASE
)


def _pool_cite(motif: re.Pattern[str], message: str) -> str | None:
    """Le pool que ``message`` nomme, ou ``None`` si le motif ne mord pas."""
    trouve = motif.search(message)
    if trouve is None:
        return None
    return next((groupe for groupe in trouve.groups() if groupe), None)


def explique_echec_provision(
    message: str, pool: str | None = None,
) -> tuple[str, str] | None:
    """Reconnaît une cause connue dans l'erreur brute d'un provisionnement.

    Terraform rend des messages exacts mais opaques pour qui découvre l'outil.
    Quelques-uns ont une cause connue et un correctif d'une ligne, et ce sont
    ceux qui arrêtent un débutant sur une machine fraîche.

    ``pool`` est celui que le dépôt utilise (``nom_du_pool``), pour les causes
    dont le message libvirt ne nomme pas le pool : sans lui, la commande
    proposée viserait ``default`` sur un dépôt qui déclare un autre pool, et
    échouerait sous les yeux de qui la copie.

    Rendre ``(explication, commande)``, ou ``None`` si rien n'est reconnu : on
    ne devine pas, on nomme ce qu'on sait nommer.
    """
    bas = message.lower()

    # « Permission denied » sur une image du pool : l'échec type d'AppArmor
    # décrit dans apparmor_override_absent(). On ne le propose QUE si
    # l'override manque effectivement, sans quoi ce serait une fausse piste.
    #
    # Depuis que le template déclare ses disques par chemin de fichier plutôt
    # que par référence de pool, une machine provisionnée par cette version ne
    # tombe plus là-dessus. La branche reste pour les domaines définis par une
    # version antérieure, qui portent encore la forme que virt-aa-helper ne sait
    # pas résoudre : eux ne guériront qu'en étant recréés.
    if (
        "permission denied" in bas
        and "/var/lib/libvirt/images" in bas
        and _doctor().apparmor_override_absent()
    ):
        return _("explain_apparmor_denied"), apparmor_fix_command()

    # « is not active » : le pool existe mais n'a jamais été démarré. C'est un
    # état DIFFÉRENT de l'absence, et il appelle un autre geste. Un
    # `pool-define-as` proposé ici échouerait sur « pool already exists ».
    pool_inactif = _pool_cite(_POOL_INACTIF, message)
    if pool_inactif is not None:
        return _("explain_pool_inactive"), demarrer_pool_command(pool_inactif)

    # « Pool not found » : le pool visé n'existe pas. Une installation fraîche
    # n'en déclare aucun. Le contrôle de doctor l'attrape en amont, mais un
    # provisionnement lancé sans diagnostic préalable tombe directement ici.
    pool_absent = _pool_cite(_POOL_ABSENT, message)
    if pool_absent is not None or "pool not found" in bas:
        return _("explain_pool_not_found"), creer_pool_command(
            pool_absent or pool or "default"
        )

    # Plus d'espace dans le pool. `doctor` ne peut pas l'annoncer d'avance : les
    # tailles déclarées sont nominales et les qcow2 s'allouent à la demande, donc
    # comparer le pool à leur somme accuserait à tort (issue #209). En revanche,
    # quand le disque manque VRAIMENT, c'est ici qu'on le sait, et le message de
    # libvirt ne nomme ni le pool ni le geste.
    if "no space left on device" in bas or "not enough space" in bas:
        return _("explain_pool_full"), (
            f"virsh -c qemu:///system pool-info {pool or 'default'}"
        )

    # `qemu-img` absent : libvirt sait créer un volume brut, pas un qcow2, et le
    # dit dans ses termes. Rencontré dans l'appliance, où le paquet `qemu-utils`
    # n'est qu'une recommandation de qemu-kvm : `--no-install-recommends` l'écarte,
    # et les quatre volumes du plan échouent d'un coup sans que rien ne nomme le
    # paquet qui manque.
    if "without qemu-img" in bas or "non-raw file images" in bas:
        return _("explain_qemu_img_absent"), shlex.join(
            _installer(["qemu-utils"], ["qemu-img"])
        )

    # « already exists » sur un domaine : un provisionnement précédent a échoué
    # APRÈS avoir défini la machine, qui n'est donc pas dans le state Terraform.
    # `destroy` ne peut pas la voir, et le message ne dit pas quoi faire.
    if "already exists with uuid" in bas:
        return _("explain_domain_exists"), (
            "virsh -c qemu:///system undefine --nvram <machine>"
        )

    return None
