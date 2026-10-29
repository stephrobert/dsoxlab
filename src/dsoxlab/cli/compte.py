"""Le compte de l'apprenant : se connecter, se déconnecter, envoyer ses preuves.

TROIS COMMANDES, ET AUCUNE QUI AGISSE TOUTE SEULE

`check` et `submit` n'envoient rien, et ce n'est pas un oubli. Un apprenant qui
rejoue dix fois un lab produirait dix écritures sur son compte, et un envoi
déclenché par une commande d'apprentissage ferait sortir des données de la
machine sans qu'il l'ait demandé. Le compte est **facultatif** sur ce portail :
pousser en silence trahirait ce choix.

D'où le découpage : `login` établit le consentement, `push` l'exerce, `logout`
le retire. Chacun se tape.

CE QUE `push` NE PROMET PAS

Il n'envoie pas « la progression » : il envoie des **tentatives**, celles que la
base locale a enregistrées, et seulement celles que le portail saura relire. Ce
qu'il laisse derrière lui est compté et dit, parce qu'une preuve non émise ne
paraîtra jamais sur le compte et que l'apprenant n'a aucun moyen de le deviner.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from ..i18n import _
from ..reporting import error, info, note, success, warn
from ..reporting.console import console
from ..security import IdentifiantRefuse
from ..security.terminal import texte_affichable
from ..sync import ChargeRefusee, ErreurPortail, SansSession, SyncIndisponible
from ._commun import (
    LabHomeOption,
    _catalogue,
    _lang,
    _root,
)
from ._socle import app

if TYPE_CHECKING:
    from ..services.sync_service import Portail


def _portail(root: Path) -> Portail:
    """Le portail déclaré par le catalogue de ``root``.

    Rend le portail SEUL, et pas un couple avec la racine : la version
    précédente en rendait deux, l'appelant écrivait ``portail, _ = ...``, et ce
    ``_`` écrasait la fonction de traduction importée au-dessus. Toutes les
    phrases de ces commandes auraient levé à l'exécution. `mypy` l'a vu, pas
    moi : c'est la raison pour laquelle cette fonction ne rend qu'une chose.
    """
    from ..discovery.repo import read_repo_metadata
    from ..services import sync_service

    try:
        repo_meta = read_repo_metadata(root)
    except Exception:  # noqa: BLE001 — un meta.yml illisible se dit par la suite
        repo_meta = None
    return sync_service.configuration(repo_meta)


def _dire_indisponible(refus: SyncIndisponible) -> None:
    error(_(refus.cle, **refus.params))


@app.command("login", help=_("cmd_login_help"))
def login(
    lab_home: LabHomeOption = None,
    sans_navigateur: Annotated[bool, typer.Option(
        "--no-browser", help=_("opt_login_no_browser"),
    )] = False,
) -> None:
    """Connecte l'apprenant au portail que ce catalogue déclare.

    ``--no-browser`` est le repli pour une machine qui n'en a pas : un serveur
    distant, une session SSH. L'URL s'affiche, l'apprenant l'ouvre **sur un
    autre poste**, et recopie l'URL de retour. Le vérificateur PKCE ne quitte
    jamais cette machine, et aucun jeton ne passe par l'historique du shell :
    seul le code d'autorisation voyage, à usage unique et inutile sans lui.
    """
    from ..services import sync_service

    try:
        portail = _portail(_root(lab_home))
    except SyncIndisponible as refus:
        _dire_indisponible(refus)
        raise typer.Exit(1) from None

    def demander(url: str) -> str:
        # Deux consignes, parce que l'apprenant verra deux choses. Avec une
        # adresse de retour déclarée, il atterrit sur une VRAIE page, qui lui
        # montre son code. Avec une boucle locale recopiée à la main, la page
        # reste blanche et seule l'adresse compte. Un message unique ferait
        # chercher au mauvais endroit dans un cas sur deux.
        if portail.identite.url_retour:
            note(_("login_ouvrir_puis_recopier"))
        else:
            note(_("login_ouvrir_cette_url"))
        # `soft_wrap` : une URL d'autorisation dépasse largement la largeur
        # d'un terminal, et Rich la couperait sur plusieurs lignes. Elle
        # cesserait alors d'être copiable, et l'apprenant recopierait une URL
        # amputée de son `code_challenge` : l'échange échouerait en
        # `invalid_grant`, sans que rien ne relie la cause à l'effet. Mesuré
        # sur un banc local : URL rendue à 80 caractères, PKCE perdu.
        # `markup=False` pour la même raison que `guide --print` : des crochets
        # dans une URL ne sont pas des balises.
        console.print(url, soft_wrap=True, markup=False)
        # `typer.prompt` n'est pas typé : on fixe le type ici plutôt que de
        # laisser un `Any` traverser la frontière vers le service.
        return str(typer.prompt(_("login_coller_le_retour")))

    try:
        session = sync_service.connecter(
            portail.identite,
            sans_navigateur=sans_navigateur,
            demander=demander,
        )
    except ErreurPortail as erreur:
        error(_("login_echoue", code=erreur.code))
        if erreur.code == "port_occupe":
            note(_("login_port_occupe", port=erreur.detail))
        elif sans_navigateur:
            # Le mode sans navigateur a une cause d'échec qui lui est propre, et
            # qui domine toutes les autres : l'URL de retour recopiée à la main
            # arrive tronquée ou réécrite. Le code OAuth seul (`invalid_grant`)
            # ne la désigne pas, et l'apprenant cherche alors du côté du
            # portail. Mesuré sur un poste réel : zsh réécrit une URL AU
            # COLLAGE, avant tout quoting, et rien dans la sortie ne le dit.
            note(_("login_echoue_suite"))
        raise typer.Exit(1) from None

    success(_("login_reussi", portail=texte_affichable(session.emetteur)))
    note(_("login_ou_vit_le_jeton"))


@app.command("logout", help=_("cmd_logout_help"))
def logout(lab_home: LabHomeOption = None) -> None:
    """Efface la session locale de ce portail.

    Efface **le fichier**, et ne révoque pas le jeton côté portail : une
    révocation qui échouerait laisserait l'apprenant croire qu'il est
    déconnecté alors qu'un jeton vit encore. On dit donc exactement ce qui a
    été fait, et où se déconnecter vraiment.
    """
    from ..sync import jetons

    try:
        portail = _portail(_root(lab_home))
    except SyncIndisponible as refus:
        _dire_indisponible(refus)
        raise typer.Exit(1) from None

    emetteur = portail.identite.emetteur
    if jetons.oublier(emetteur):
        success(_("logout_fait", portail=texte_affichable(emetteur)))
    else:
        info(_("logout_rien_a_faire"))
    note(_("logout_revocation"))


@app.command("push", help=_("cmd_push_help"))
def push(
    lab_home: LabHomeOption = None,
    dry_run: Annotated[bool, typer.Option(
        "--dry-run", help=_("opt_push_dry_run"),
    )] = False,
) -> None:
    """Envoie les preuves locales vers le compte, en les fusionnant.

    ``--dry-run`` dit ce qui partirait, sans rien envoyer ni demander de
    session : c'est la façon de voir ce que le portail écarterait avant de
    s'engager, et la seule qui ne touche à rien.

    Jamais un écrasement : le compte peut porter des tentatives jouées sur une
    autre machine, et un envoi les réunit aux nôtres.
    """
    from ..discovery.repo import read_repo_metadata
    from ..services import sync_service
    from ..services.evidence import construire_document, identifiant_de_catalogue
    from ..sync import magasin as construction

    root = _root(lab_home)
    try:
        portail = _portail(root)
    except SyncIndisponible as refus:
        _dire_indisponible(refus)
        raise typer.Exit(1) from None

    labs = {d.id: d for d in _catalogue(root, _lang(root), quiet=True)}
    try:
        repo_meta = read_repo_metadata(root)
    except Exception:  # noqa: BLE001 — déjà toléré par `export`, même raison
        repo_meta = None
    try:
        catalog_id = identifiant_de_catalogue(
            root, repo_meta.id if repo_meta else None
        )
        document = construire_document(root, labs, catalog_id=catalog_id)
    except IdentifiantRefuse as refus:
        error(_("export_identifiant_refuse", field=refus.champ,
                reason=_(refus.cle, **refus.params)))
        raise typer.Exit(1) from None

    if dry_run:
        conversion = construction.convertir(document)
        info(_("push_essai", preuves=len(conversion["preuves"])))
        _dire_les_ecarts(conversion["ecartees"])
        return

    try:
        envoi = sync_service.pousser(portail, document)
    except SansSession as absence:
        error(_(absence.cle))
        note(_("push_connectez_vous"))
        raise typer.Exit(1) from None
    except ChargeRefusee as refus:
        error(_(refus.cle, **refus.params))
        note(_("push_charge_refusee_suite"))
        raise typer.Exit(1) from None
    except ErreurPortail as erreur:
        error(_("push_refuse", statut=erreur.statut, code=erreur.code))
        note(_(_CONSIGNES.get(erreur.code, "push_refuse_suite")))
        raise typer.Exit(1) from None

    if envoi.rejoue:
        # Pas un échec : notre propre écriture, rejouée après une coupure. C'est
        # exactement ce que l'identifiant d'opération achète, et le dire évite
        # que l'apprenant la relance une troisième fois.
        info(_("push_rejoue"))
    if not envoi.ecrit:
        # Le compte portait déjà exactement ces preuves : on n'a pas écrit, et
        # c'est à dire plutôt qu'à masquer derrière un « 0 ajoutée » qui
        # laisserait croire qu'une révision a été consommée.
        success(_("push_rien_a_ajouter", total=envoi.total,
                  revision=envoi.revision))
    else:
        success(_("push_reussi", ajoutees=envoi.ajoutees, total=envoi.total,
                  revision=envoi.revision))
    if envoi.doublons:
        info(_("push_doublons", doublons=envoi.doublons))
    _dire_les_ecarts(envoi.ecartees)


#: Ce qu'il faut faire selon le refus du portail. Un code par geste : un
#: message unique renverrait à un « réessayez » qui ne s'applique qu'à un cas
#: sur quatre.
_CONSIGNES = {
    "injoignable": "push_injoignable",
    "revision": "push_conflit_persistant",
    "operation-reutilisee": "push_operation_reutilisee",
    "compte-supprime": "push_compte_supprime",
    "trop-gros": "push_charge_refusee_suite",
}


def _dire_les_ecarts(ecartees: dict[str, int]) -> None:
    """Nomme les tentatives laissées de côté, motif par motif.

    En avertissement et non en information : ces tentatives ne paraîtront
    **jamais** sur le compte. Le motif le plus courant, un lab disparu du
    catalogue, a son propre message parce qu'il n'y a rien à corriger côté
    apprenant et qu'il faut le dire pour qu'il ne le cherche pas.
    """
    for motif, combien in sorted(ecartees.items()):
        cle = f"push_ecart_{motif}"
        warn(_(cle, count=combien))
