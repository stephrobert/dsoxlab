"""La frontière de confiance du moteur, et ce qui la traverse.

**Un catalogue est une entrée non fiable.** `dsoxlab catalog add <url>` clone un
dépôt git arbitraire, et tout ce qu'il déclare — identifiants, titres, URL —
est une **donnée**, jamais une instruction. Ce paquet porte les contrôles qui
tiennent cette règle, en un seul endroit : deux implémentations d'une même
politique finissent toujours par diverger, et c'est la plus permissive qui
décide.

Ce qui vit ici concerne les valeurs qui **sortent** du moteur ou qui
**agissent** : un identifiant recopié dans un document remis à un tiers, une
URL affichée ou ouverte. Les contrôles de forme qui aident l'auteur d'un
catalogue restent dans ``validators/`` — ce n'est pas la même chose, et
``validate-structure`` n'est pas une barrière de sécurité : il n'est ni
automatique, ni exigé avant d'utiliser un catalogue.

Rien ici ne sonde le réseau. Un contrôle de sécurité qui résout un nom ou
ouvre une connexion donnerait à un catalogue le pouvoir de faire émettre des
requêtes depuis le poste de l'apprenant, ce qui est exactement ce qu'on refuse.
"""

from __future__ import annotations

#: Les plages de caractères qu'un identifiant ne peut pas porter, et pourquoi.
#:
#: Exprimées en codes plutôt qu'en littéraux : la classe de caractères écrite
#: en clair contiendrait des caractères invisibles dans le fichier source, et
#: un formateur automatique l'a déjà réécrite une fois en remplaçant les
#: échappements par les caractères eux-mêmes. Un contrôle de sécurité doit
#: rester lisible pour être relu.
_PLAGES_INTERDITES: tuple[tuple[int, int, str], ...] = (
    # Un `\r` dans un identifiant recopié dans un en-tête ou un journal y
    # injecte une ligne ; un `\x1b` y injecte une séquence de terminal.
    (0x00, 0x1F, "commandes C0"),
    (0x7F, 0x9F, "DEL et commandes C1"),
    # Elles inversent l'affichage sans changer la valeur : `lab\u202egnp.exe`
    # se lit `labexe.png` dans un terminal. C'est la technique employée pour
    # faire prendre un exécutable pour une image.
    (0x200E, 0x200F, "marques de direction"),
    (0x202A, 0x202E, "surcharges de direction"),
    (0x2066, 0x2069, "isolats de direction"),
    # Deux identifiants visuellement identiques, distincts en machine.
    (0x200B, 0x200D, "caractères de largeur nulle"),
    (0xFEFF, 0xFEFF, "marque d'ordre des octets"),
)

LONGUEUR_MAX_IDENTIFIANT = 128


class IdentifiantRefuse(ValueError):
    """Un identifiant de catalogue ou de lab ne peut pas être transmis tel quel.

    Porte une **clé** de traduction et ses paramètres, jamais une phrase :
    l'appelant est une commande, et une commande parle la langue de
    l'apprenant. C'est la même discipline que :class:`ContentIssue` dans les
    validators.
    """

    def __init__(self, champ: str, valeur: str, cle: str, **params: object) -> None:
        self.champ = champ
        self.valeur = valeur
        self.cle = cle
        self.params = params
        super().__init__(f"{champ}: {cle} {params}")


def _premier_caractere_interdit(valeur: str) -> str | None:
    for caractere in valeur:
        code = ord(caractere)
        if any(debut <= code <= fin for debut, fin, _ in _PLAGES_INTERDITES):
            return caractere
    return None


def identifiant_sur(valeur: str, *, champ: str, vide_permis: bool = False) -> str:
    """Rend l'identifiant s'il peut voyager, lève sinon.

    Appelé sur ce qui **quitte** le moteur : le document de preuve part vers un
    portail, un LMS, un fichier transféré. Le consommateur applique ses propres
    règles — le site qui reçoit ces preuves refuse exactement ces caractères —
    et un identifiant qu'il rejettera n'a aucune raison d'être émis. Mieux vaut
    le dire ici, où l'on sait quel champ et quel catalogue sont en cause, que
    le laisser échouer chez quelqu'un d'autre.

    On **refuse** plutôt qu'on assainit : nettoyer changerait l'identifiant,
    donc romprait le rattachement entre une preuve et le lab qu'elle atteste.
    Un identifiant faux vaut mieux qu'un identifiant faussé en silence.

    ``vide_permis`` sert à ``section``, qu'un lab qu'aucune règle ne rattache
    laisse vide légitimement.
    """
    if not valeur:
        if vide_permis:
            return valeur
        raise IdentifiantRefuse(champ, valeur, "securite_identifiant_vide")
    if len(valeur) > LONGUEUR_MAX_IDENTIFIANT:
        raise IdentifiantRefuse(
            champ, valeur, "securite_identifiant_trop_long",
            max=LONGUEUR_MAX_IDENTIFIANT, length=len(valeur),
        )
    fautif = _premier_caractere_interdit(valeur)
    if fautif is not None:
        raise IdentifiantRefuse(
            champ, valeur, "securite_identifiant_caractere",
            code=f"U+{ord(fautif):04X}",
        )
    return valeur
