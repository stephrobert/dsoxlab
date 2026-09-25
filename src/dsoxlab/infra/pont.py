"""Le nom de l'interface réseau que crée un provider local, et sa limite.

Le noyau Linux refuse un nom d'interface de plus de **quinze** caractères :
``IFNAMSIZ`` vaut 16, terminateur compris. Au-delà, la création du pont échoue
sur ``ENORANGE``, que libvirt remonte tel quel :

    Error: Network Start Failed
    Network defined but failed to start: error creating bridge interface
    virbr-kubernetes: Numerical result out of range

« Numerical result out of range » ne nomme ni le pont, ni la limite, ni le champ
du ``meta.yml`` qui l'a produit — et le nom fautif n'apparaît nulle part dans ce
fichier, puisqu'il est **calculé**. L'échec arrive de surcroît **après** le
téléchargement de l'image de base, donc chaque essai coûte une minute (issue
#214, rencontré en montant le catalogue Kubernetes).

Deux règles de dérivation, une par provider local, et c'est pourquoi ce module
existe : les deux vivaient dans les templates Terraform, où aucun contrôle
Python ne pouvait les lire.

``kvm``
    ``templates/terraform/kvm/main.tf`` calcule
    ``virbr-${replace(var.network_name, "lab-", "")}``. ``lab-kubernetes`` donne
    donc ``virbr-kubernetes``, seize caractères. La marge réelle est de **neuf
    caractères utiles** après ``lab-``, ce qui n'était écrit nulle part.

``incus``
    Incus crée un pont Linux portant **exactement** le nom du réseau. La limite
    s'applique donc directement à ``infra.network``, sans transformation.

``outscale``
    Un réseau cloud, aucun pont sur ce poste : la question ne se pose pas.

``tests/test_nom_de_pont.py`` compare cette dérivation à l'expression réellement
écrite dans le template : deux définitions de « comment s'appelle le pont »
finiraient par diverger, et la divergence serait invisible jusqu'au prochain
catalogue au nom long.
"""

from __future__ import annotations

from ..models import RepoMetadata

#: Caractères utiles d'un nom d'interface réseau sous Linux. ``IFNAMSIZ`` vaut
#: 16, terminateur nul compris, d'où 15.
IFNAMSIZ_UTILES = 15

#: Ce que le template kvm préfixe au nom de réseau élagué.
_PREFIXE_KVM = "virbr-"

#: Ce que le template kvm retire du nom de réseau. ``replace`` en HCL retire
#: l'occurrence **où qu'elle soit**, pas seulement un préfixe :
#: ``mon-lab-reseau`` donne ``virbr-mon-reseau``. On reproduit ce comportement,
#: pas celui qu'on aurait choisi — un test le confronte au template.
_ELAGUE_KVM = "lab-"


class NomDePontTropLong(RuntimeError):
    """Le pont que ce provider créerait dépasse ce que le noyau accepte.

    Porte des **données**, pas une phrase : c'est la CLI qui compose le message
    traduit, comme le fait déjà ``ProviderUnresolved``. Un validator ou une
    couche d'infra qui écrirait son texte l'afficherait dans une seule langue.
    """

    def __init__(self, *, pont: str, reseau: str, provider: str) -> None:
        self.pont = pont
        self.reseau = reseau
        self.provider = provider
        self.limite = IFNAMSIZ_UTILES
        #: Combien de caractères il faut retirer.
        self.trop = len(pont) - IFNAMSIZ_UTILES
        #: La longueur que le nom de RÉSEAU ne doit pas dépasser. C'est le fait
        #: que l'auteur a besoin de connaître : une troncature suggérée, il ne la
        #: voudra pas, mais une cible lui laisse choisir un nom qui a du sens.
        #: Dire une longueur évite aussi l'accord bancal d'un « 1 caractère(s) ».
        self.max_reseau = max(0, len(reseau) - self.trop)
        super().__init__(f"{pont} ({len(pont)} > {IFNAMSIZ_UTILES})")


def nom_du_pont(repo_meta: RepoMetadata, provider: str) -> str | None:
    """Le nom de l'interface que ``provider`` créera, ou ``None`` s'il n'en crée pas.

    Un ``bridge_name`` déclaré dans ``infra.providers.<provider>`` l'emporte : le
    template le lit en premier, donc le contrôle doit porter sur ce que
    l'apprenant obtiendra vraiment, et non sur ce que la dérivation aurait donné.
    """
    reseau = (repo_meta.infra.network or "").strip()
    if not reseau:
        return None

    declare = repo_meta.infra.provider_config(provider).get("bridge_name")
    if isinstance(declare, str) and declare.strip():
        return declare.strip()

    if provider == "kvm":
        return _PREFIXE_KVM + reseau.replace(_ELAGUE_KVM, "")
    if provider == "incus":
        return reseau
    return None


def verifier_nom_de_pont(repo_meta: RepoMetadata, provider: str) -> None:
    """Lève :class:`NomDePontTropLong` si le pont dépasse la limite du noyau.

    Appelée **avant** ``terraform init``, donc avant le téléchargement du
    provider et de l'image de base : c'est tout l'intérêt, puisque la cause est
    connue d'avance et que l'échec, lui, arrive une minute plus tard.
    """
    pont = nom_du_pont(repo_meta, provider)
    if pont is not None and len(pont) > IFNAMSIZ_UTILES:
        raise NomDePontTropLong(pont=pont, reseau=repo_meta.infra.network,
                                provider=provider)


def reseau_raccourci(reseau: str, pont: str) -> str:
    """Un nom de réseau qui tiendrait, à proposer dans le message.

    Suggérer vaut mieux que dire « raccourcissez » : l'auteur doit sinon
    recalculer lui-même une dérivation qu'il ne connaît pas. On coupe le nom du
    réseau de ce qui dépasse, et on garde au moins quelque chose de non vide.
    """
    trop = len(pont) - IFNAMSIZ_UTILES
    garde = max(1, len(reseau) - trop)
    return reseau[:garde].rstrip("-") or reseau[:1]
