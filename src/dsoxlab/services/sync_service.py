"""Ce que `login` et `push` font vraiment, hors de la couche Typer.

LA REPRISE SUR CONFLIT N'EST PAS UN DÉTAIL, C'EST LA FONCTION

Le portail écrit sous condition : si quelqu'un a écrit entre notre lecture et
notre écriture, il refuse en **409 revision**. Ce cas est ordinaire, pas
exceptionnel — un apprenant qui joue un lab sur son poste et consulte son compte
dans un navigateur le produit tout seul.

Et il ne se reprend **que** par une fusion. Réécrire par-dessus avec la
révision fraîche effacerait les tentatives que le portail avait et que nous
n'avons pas : celles jouées depuis une autre machine, ou importées à la main.
C'est la seule famille de données que le portail réunit sans rien demander à
l'apprenant, et il attend de nous la même chose.

D'où la boucle : relire, refusionner, réécrire, un nombre **borné** de fois. Un
réessai infini sur un portail très sollicité tournerait sans fin ; après trois
tentatives, il vaut mieux rendre la main et le dire.

L'IDENTIFIANT D'OPÉRATION CHANGE À CHAQUE CONTENU, PAS À CHAQUE APPEL

Un même ``operationId`` rejoué rend le même résultat sans second effet : c'est
ce qui rend un envoi coupé en plein vol rejouable. Mais réutilisé pour un
**autre** contenu, il vaut un 409 ``operation-reutilisee``, qui dit un défaut de
la CLI. Chaque tour de la boucle de fusion produit donc un contenu différent,
donc un identifiant neuf.
"""

from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from typing import Any

from ..i18n import _
from ..models.repo import RepoMetadata
from ..security.urls import URLRefusee, url_de_portail
from ..sync import ErreurPortail, SansSession, SyncIndisponible, oidc
from ..sync import jetons as magasin_jetons
from ..sync import magasin as construction
from ..sync.oidc import Configuration
from ..sync.protocole import ClientPortail

#: Le seul protocole que ce moteur sait parler.
PROTOCOLE = "learner-sync/1"

#: Tours de fusion avant de rendre la main. Trois suffisent : au-delà, ce n'est
#: plus une course mais un portail qu'on sollicite trop.
TOURS_MAX = 3


@dataclass
class Envoi:
    """Ce qu'un `push` a fait, en chiffres qui se vérifient.

    ``ecartees`` est rendu plutôt que journalisé : une tentative non émise ne
    paraîtra jamais sur le compte, et l'apprenant doit l'apprendre de la CLI
    plutôt que de le déduire d'un total qui ne tombe pas juste.
    """

    ajoutees: int
    doublons: int
    ecartees: dict[str, int]
    revision: int
    rejoue: bool
    total: int

    ecrit: bool = True
    """Faux quand le compte portait déjà exactement ces preuves.

    Une écriture identique n'est pas neutre : elle brûle une révision, et le
    registre du site voit alors une mise à jour qui n'a pas eu lieu, ce qui
    reclasse des labs « à réattester » sans qu'une seule ligne ait changé.
    Mesuré en local contre le handler réel : un second ``push`` sans nouvelle
    tentative faisait passer la révision de 1 à 2."""


@dataclass
class Portail:
    """Le portail déclaré : son identité et son transport, côte à côte.

    Deux objets plutôt qu'un seul fourre-tout : :class:`Configuration` ne décrit
    que ce dont la connexion a besoin, et ``api`` ne la concerne pas. Les réunir
    ici donne un seul objet à passer, sans mêler les deux rôles que
    :mod:`dsoxlab.sync` tient séparés.
    """

    identite: Configuration
    api: str


def configuration(repo_meta: RepoMetadata | None) -> Portail:
    """Le portail déclaré, ou une erreur qui nomme le manque.

    Chaque champ absent est dit séparément : « ce catalogue ne synchronise pas »
    et « il le déclare à moitié » sont deux situations, et la seconde est une
    faute d'auteur de catalogue qu'il faut pouvoir corriger sans deviner.
    """
    if repo_meta is None or repo_meta.learning.sync is None:
        raise SyncIndisponible("sync_non_declare")
    bloc = repo_meta.learning.sync
    if bloc.protocol != PROTOCOLE:
        raise SyncIndisponible(
            "sync_protocole_inconnu",
            declare=bloc.protocol or "-",
            attendu=PROTOCOLE,
        )
    manquants = [
        nom
        for nom, valeur in (
            ("api", bloc.api),
            ("issuer", bloc.issuer),
            ("oauth_domain", bloc.oauth_domain),
            ("client_id", bloc.client_id),
        )
        if not valeur
    ]
    if manquants:
        raise SyncIndisponible("sync_declaration_incomplete", champs=", ".join(manquants))
    # L'adresse de retour : déclarée, ou une boucle locale, jamais les deux.
    # Les cumuler ne dirait pas laquelle sert, et le portail en enregistre une
    # seule : la CLI choisirait, et se tromperait une fois sur deux.
    if bloc.callback_url and bloc.callback_port:
        raise SyncIndisponible("sync_retour_ambigu")
    if not bloc.callback_url and not bloc.callback_port:
        raise SyncIndisponible("sync_retour_absent")
    if bloc.callback_url:
        try:
            url_de_portail(bloc.callback_url, champ="learning.sync.callback_url")
        except URLRefusee as refus:
            raise SyncIndisponible(
                "sync_url_refusee", champ="callback_url",
                raison=_(refus.cle, **refus.params),
            ) from None
    for nom, valeur in (("api", bloc.api), ("issuer", bloc.issuer),
                        ("oauth_domain", bloc.oauth_domain)):
        # La MÊME fonction que le lien de remise, et non un `startswith`
        # recopié : `https` seul, avec l'unique dérogation locale
        # (`DSOXLAB_PORTAL_LOCAL=1` vers localhost), qui est ce qui rend un
        # portail en cours d'écriture jouable sans affaiblir le cas réel. Deux
        # gardes plutôt qu'un, et c'est la machine qui l'accorde, jamais le
        # catalogue.
        try:
            url_de_portail(valeur, champ=f"learning.sync.{nom}")
        except URLRefusee as refus:
            # La raison est résolue ICI, et non portée en clé jusqu'à la CLI :
            # celle-ci rend `SyncIndisponible` d'une seule façon pour tous les
            # manques, et un cas qui demanderait un rendu à part ferait diverger
            # les six messages.
            raise SyncIndisponible(
                "sync_url_refusee", champ=nom,
                raison=_(refus.cle, **refus.params),
            ) from None
    return Portail(
        identite=Configuration(
            emetteur=bloc.issuer,
            domaine=bloc.oauth_domain,
            client_id=bloc.client_id,
            api=bloc.api,
            port_retour=bloc.callback_port,
            url_retour=bloc.callback_url,
        ),
        api=bloc.api,
    )


def session_valide(config: Configuration) -> magasin_jetons.Session:
    """La session enregistrée, rafraîchie si elle a expiré.

    Lève :class:`SansSession` quand il n'y a rien, ou quand le rafraîchissement
    échoue : dans les deux cas le geste est le même, une connexion, et c'est ce
    que le message doit dire plutôt que de rapporter une erreur OAuth.
    """
    session = magasin_jetons.lire(config.emetteur)
    if session is None:
        raise SansSession()
    if not session.liee_a(config.api, config.domaine, config.client_id):
        # LA session de cet émetteur existe, mais elle a été obtenue pour un
        # AUTRE portail. On refuse avant toute requête : présenter ce jeton
        # reviendrait à l'offrir à l'hôte qu'un catalogue aura déclaré. Un
        # message à part, parce que « reconnectez-vous » n'expliquerait pas
        # pourquoi, et que la bonne réaction peut être de se méfier du
        # catalogue plutôt que de rejouer `login`.
        raise SansSession("sync_session_autre_portail")
    if not session.expire:
        return session
    try:
        neuve = oidc.rafraichir(config, session)
    except ErreurPortail:
        raise SansSession("sync_session_expiree") from None
    magasin_jetons.ecrire(neuve)
    return neuve


def connecter(config: Configuration, *, sans_navigateur: bool,
              demander: Any = None) -> magasin_jetons.Session:
    """Mène la connexion PKCE et enregistre la session.

    ``demander`` est la fonction qui réclame l'URL de retour en mode sans
    navigateur. Injectée plutôt qu'appelée directement : la couche Typer sait
    poser une question, ce module ne doit pas en dépendre pour être testable.
    """
    verificateur = oidc.nouveau_verificateur()
    etat = oidc.etat_neuf()
    url = oidc.url_autorisation(config, verificateur, etat)

    # Deux raisons de recopier le code à la main, et une seule est un choix de
    # l'apprenant. L'autre vient du portail : quand il déclare une adresse de
    # retour, il n'y a aucune boucle locale à écouter, donc rien à attendre.
    # Le navigateur s'ouvre quand même, c'est seulement le retour qui change.
    if config.url_retour or sans_navigateur:
        if demander is None:  # pragma: no cover — garde de programmation
            raise SansSession("sync_sans_session")
        if not sans_navigateur:
            webbrowser.open(url)
        code = oidc.code_depuis_url(str(demander(url)), etat)
    else:
        if not oidc.port_libre(config.port_retour):
            # Sondé AVANT d'ouvrir le navigateur : l'apprenant serait sinon
            # devant une page de connexion dont le retour ne mènerait nulle part.
            raise ErreurPortail(0, "port_occupe", detail=str(config.port_retour))
        webbrowser.open(url)
        code = oidc.attendre_le_code(config, etat)

    session = oidc.echanger_le_code(config, code, verificateur)
    magasin_jetons.ecrire(session)
    return session


def pousser(portail: Portail, document: dict[str, Any]) -> Envoi:
    """Fusionne les preuves locales avec celles du compte, et écrit.

    Le document local est **réduit d'abord** : ce qui ne serait pas relu par le
    portail n'est pas émis, parce qu'une seule ligne écartée lui ferait rendre
    un magasin vide à la relecture. Voir :mod:`dsoxlab.sync.magasin`.
    """
    conversion = construction.convertir(document)
    client = ClientPortail(
        portail.api, lambda: session_valide(portail.identite).acces
    )

    dernier: ErreurPortail | None = None
    for _tour in range(TOURS_MAX):
        etat, brut = client.lire()
        distant = construction.lire(brut)
        fusion, ajoutees, doublons = construction.fusionner(
            distant, conversion["preuves"]
        )
        charge = construction.serialiser(fusion)
        if ajoutees == 0 and brut is not None and charge == brut:
            # RIEN À ÉCRIRE, et ne pas écrire est le bon geste. Le portail
            # accepterait cette écriture identique et incrémenterait sa
            # révision, ce qui fait voir au registre du site une mise à jour qui
            # n'a pas eu lieu. La comparaison porte sur la charge sérialisée, et
            # non sur le seul compte d'ajouts : le magasin distant a pu être
            # écrit par un navigateur, dans un ordre que notre tri change.
            return Envoi(
                ajoutees=0,
                doublons=doublons,
                ecartees=conversion["ecartees"],
                revision=etat["revision"],
                rejoue=False,
                total=len(fusion["preuves"]),
                ecrit=False,
            )
        try:
            # Un identifiant par TOUR : le contenu diffère d'un tour à l'autre,
            # et réutiliser l'identifiant vaudrait `operation-reutilisee`.
            ecriture = client.ecrire(etat["revision"], charge)
        except ErreurPortail as erreur:
            if erreur.statut == 409 and erreur.code == "revision":
                # Quelqu'un a écrit entre notre lecture et notre écriture. On
                # relit et on refusionne : jamais on n'écrase.
                dernier = erreur
                continue
            raise
        return Envoi(
            ajoutees=ajoutees,
            doublons=doublons,
            ecartees=conversion["ecartees"],
            revision=ecriture["revision"],
            rejoue=ecriture["rejoue"],
            total=len(fusion["preuves"]),
        )

    # Trois tours n'ont pas suffi : on rend le dernier refus tel quel plutôt
    # qu'un message à nous. Le code `revision` dit déjà ce qui se passe, et un
    # quatrième tour ne changerait rien à la cause.
    raise dernier or ErreurPortail(409, "revision")
