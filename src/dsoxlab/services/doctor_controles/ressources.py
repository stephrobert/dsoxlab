"""Ce que le poste offre face à ce que le catalogue demande : mémoire, disque, pont.

Extrait de ``services/doctor.py`` (issue #199), sans changement de
comportement. Voir ce module pour les principes du diagnostic.
"""

from __future__ import annotations

import os
from pathlib import Path

from ...i18n import _
from ...infra.pont import IFNAMSIZ_UTILES, nom_du_pont, reseau_raccourci
from ...models import RepoMetadata
from ...models.repo import HostDefinition, InfraDefinition
from .modele import STATE_UNKNOWN, Check, _check, _doctor


def _mem_available_mb() -> int | None:
    """``MemAvailable`` de ``/proc/meminfo``, en MiB, ou ``None`` si illisible.

    ``MemAvailable`` plutôt que ``MemFree`` : c'est l'estimation du noyau de
    ce qu'une nouvelle charge peut réellement obtenir, cache compris.
    """
    try:
        contenu = Path("/proc/meminfo").read_text(encoding="ascii")
    except OSError:
        return None
    for ligne in contenu.splitlines():
        if ligne.startswith("MemAvailable:"):
            champs = ligne.split()
            if len(champs) >= 2 and champs[1].isdigit():
                return int(champs[1]) // 1024
    return None


def _pool_available_gb(pool: str) -> int | None:
    """L'espace disponible du pool libvirt visé, en GiB, ou ``None`` si non mesuré.

    ``pool-info --bytes`` rend la place telle que libvirt la voit, c'est-à-dire
    celle du répertoire cible réel du pool, où qu'il soit monté. ``LC_ALL=C``
    n'est pas décoratif : virsh traduit ses libellés, et « Available: » devient
    « Disponible : » sous une locale française.
    """
    probe = _doctor()._sonder(
        ["virsh", "-c", "qemu:///system", "pool-info", pool, "--bytes"],
        env={**os.environ, "LC_ALL": "C"},
    )
    if probe is None or probe.returncode != 0:
        return None
    for ligne in probe.stdout.splitlines():
        if ligne.startswith("Available:"):
            champs = ligne.split()
            if len(champs) >= 2 and champs[1].isdigit():
                return int(champs[1]) // 2**30
    return None


def _check_bridge_name(repo_meta: RepoMetadata, provider: str) -> Check:
    """Le pont que ce provider créera tient-il dans la limite du noyau ?

    Un contrôle qui ne sonde rien : il lit le contrat et compte des caractères.
    Il a donc toujours une réponse, et jamais d'``unknown``.

    Il vaut mieux ici qu'au premier ``provision``, où l'échec arrive après le
    téléchargement de l'image de base, sur un « Numerical result out of range »
    qui ne nomme ni le pont, ni la limite, ni le champ qui l'a produit — et le
    nom fautif n'apparaît nulle part dans le ``meta.yml``, puisqu'il est calculé
    (issue #214).
    """
    pont = nom_du_pont(repo_meta, provider)
    if pont is None:
        # Ce provider ne crée aucune interface sur ce poste, ou aucun réseau
        # n'est déclaré : il n'y a rien à mesurer, et rien à reprocher.
        return _check("bridge_name", True, _("detail_bridge_name_absent"))
    if len(pont) > IFNAMSIZ_UTILES:
        return _check(
            "bridge_name", False,
            _(
                "detail_bridge_name_too_long",
                bridge=pont, length=len(pont), limit=IFNAMSIZ_UTILES,
                network=repo_meta.infra.network,
            ),
            hint=_(
                "bridge_name_fix",
                max_network=max(
                    0,
                    len(repo_meta.infra.network) - (len(pont) - IFNAMSIZ_UTILES),
                ),
                suggestion=reseau_raccourci(repo_meta.infra.network, pont),
            ),
        )
    return _check(
        "bridge_name", True,
        _("detail_bridge_name_ok", bridge=pont, length=len(pont),
          limit=IFNAMSIZ_UTILES),
    )


def nom_du_pool(infra: InfraDefinition) -> str:
    """Le pool libvirt que ce dépôt utilise, ``default`` à défaut d'override.

    Public parce que deux appelants en ont besoin et qu'une seule les sert :
    ``doctor``, qui mesure la place, et la CLI, qui doit nommer le bon pool dans
    la commande qu'elle propose après un échec de provisionnement. Le template
    Terraform lit la même clé (``local.storage_pool``) ; la dupliquer une
    troisième fois serait le moyen sûr de les désaligner un jour.
    """
    return str(infra.provider_config("kvm").get("storage_pool") or "default")


def _hotes_a_compter(infra: InfraDefinition, hosts: list[str] | None) -> list[HostDefinition]:
    """Les hôtes dont le contrôle de ressources additionne la demande.

    ``hosts`` restreint aux FQDN demandés. Deux replis, et chacun va vers le
    PIRE CAS, jamais vers le plus petit :

    TROIS CAS, et ``None`` ne veut pas dire la même chose qu'une liste vide :

    - ``None`` : pas de restriction, donc tout le catalogue. C'est ce que voit
      le ``doctor`` lancé seul, et le comportement d'avant l'issue #358.
    - ``[]`` : le lab ne demande **aucun** hôte, et sa demande est donc nulle.
      C'est le cas d'un lab ``shell``, qui n'a pas d'infrastructure : lui faire
      réclamer la mémoire du catalogue le refuserait sur une petite machine
      pour des VM qu'il ne monte jamais.
    - des FQDN dont **aucun** n'est au catalogue : repli sur tout le catalogue.
      Ceux-là ne font pas une demande nulle ; annoncer « 0 Mo requis » serait
      vert sur n'importe quelle machine, et le contrôle cesserait de contrôler.
      Ce n'est pas à lui de refuser un hôte inconnu, l'inventaire le fera avec
      un message qui nomme la cause.

    « Tout le catalogue » veut dire ses hôtes COMMUNS (issue #365) : un hôte
    optionnel ne se monte que pour un lab qui le cite, et ce lab le demande
    alors par son nom. Le compter d'office ferait peser deux labs sur tous les
    autres, ce que les hôtes optionnels existent pour éviter.
    """
    if hosts is None:
        return infra.common_hosts
    if not hosts:
        return []
    demandes = set(hosts)
    retenus = [h for h in infra.hosts if h.name in demandes]
    return retenus or infra.common_hosts


def _check_resources(infra: InfraDefinition, provider: str,
                     hosts: list[str] | None = None) -> Check:
    """Ce que le poste offre, face à ce que le ``meta.yml`` déclare.

    Un provisionnement a déjà expiré sur un hôte à 2 vCPU / 4 Go (hôte prêt à
    181 secondes pour un délai de 180) sans que rien ne l'annonce. La somme des
    ``ram_mb`` du catalogue est la demande, ``MemAvailable`` est l'offre, et le
    contrôle porte sur elles : deux mesures de même nature. ``hosts`` restreint
    cette demande : voir :func:`_hotes_a_compter` (issue #358).

    Le disque, lui, est **affiché sans être jugé** (issue #209) — les tailles
    déclarées sont nominales quand les qcow2 s'allouent à la demande.

    Une sonde impossible ne vaut jamais « ok » : la portion non mesurée est
    nommée, et le contrôle sort en ``unknown``, sauf si une portion mesurée
    manque déjà, auquel cas le manque prouvé l'emporte.
    """
    comptes = _hotes_a_compter(infra, hosts)
    besoin_ram = sum(h.ram_mb for h in comptes)
    besoin_disk = sum(h.disk_gb + h.extra_disk_gb for h in comptes)

    manque = False
    inconnu = False
    portions: list[str] = []

    dispo_ram = _doctor()._mem_available_mb()
    if dispo_ram is None:
        inconnu = True
        portions.append(_("detail_resources_ram_unknown"))
    else:
        manque = manque or dispo_ram < besoin_ram
        portions.append(
            _("detail_resources_ram", avail=dispo_ram, need=besoin_ram)
        )

    if provider == "kvm":
        pool = nom_du_pool(infra)
        dispo_disk = _doctor()._pool_available_gb(pool)
        if dispo_disk is None:
            # Pool absent, inactif ou virsh muet : le contrôle du pool porte
            # déjà ce rouge-là, le redire ici empilerait deux échecs pour une
            # seule cause. Mais rien n'est mesuré, donc rien n'est vert.
            inconnu = True
            portions.append(_("detail_resources_disk_unknown", pool=pool))
        else:
            # La portion disque INFORME, elle ne conclut pas (issue #209).
            #
            # `besoin_disk` est la somme des tailles NOMINALES déclarées, et les
            # qcow2 s'allouent à la demande : le catalogue Linux annonce 65 Go
            # pour 3,2 Go réellement occupés, mesurés par un utilisateur. Le
            # comparer à l'espace libre revient à opposer un maximum théorique à
            # une mesure, et cela peignait en rouge — en contrôle **requis** —
            # des installations qui provisionnent parfaitement.
            #
            # On garde le chiffre, qui dit quelque chose de vrai sur le pire cas,
            # en l'annonçant comme tel. Un manque d'espace RÉEL, lui, se dit au
            # moment où il se produit : `explique_echec_provision` reconnaît
            # désormais « no space left on device » et nomme le pool.
            portions.append(
                _(
                    "detail_resources_disk",
                    pool=pool, avail=dispo_disk, need=besoin_disk,
                )
            )
    else:
        # L'outil ne sait pas mesurer le stockage de ce provider : le dire
        # vaut mieux qu'un vert conclu sur la seule RAM.
        inconnu = True
        portions.append(_("detail_resources_disk_unprobed", provider=provider))

    # Le joint se traduit : la typographie française met une espace avant le
    # point-virgule, l'anglaise non.
    detail = _("detail_resources_join").join(portions)
    if manque:
        return _check("resources", False, detail)
    if inconnu:
        return _check(
            "resources", False, detail, forced_state=STATE_UNKNOWN,
        )
    return _check("resources", True, detail)
