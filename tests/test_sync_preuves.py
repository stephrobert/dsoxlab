"""L'envoi des preuves : ce que le portail relira, et ce qu'on refuse d'émettre.

Chaque test porte sur un COMPORTEMENT, et le plus important d'entre eux est
celui du magasin vidé : le portail relit son magasin en tout ou rien, donc une
seule ligne qu'il écarterait effacerait l'historique affiché de l'apprenant.
C'est la raison d'être de `sync/magasin.py`, et c'est ce qui se casserait sans
bruit si quelqu'un « simplifiait » le filtre.

Aucun réseau : le client du portail reçoit un faux transport.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Self

import pytest

from dsoxlab.models.repo import RepoMetadata
from dsoxlab.sync import ChargeRefusee, SansSession, SyncIndisponible, oidc
from dsoxlab.sync import magasin as m

MAINTENANT = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)


def _ligne(**surcharges: Any) -> dict[str, Any]:
    """Une ligne d'export valide, que chaque test abîme à sa façon."""
    base: dict[str, Any] = {
        "catalog": "publier-service-dsoxlab-training",
        "lab_id": "pub-nginx-cache",
        "lab_type": "lab",
        "section": "publier-service",
        "validated": True,
        "score": 100,
        "max_score": 100,
        "passed_tests": 4,
        "total_tests": 4,
        "hints_used": 0,
        "attempted_at": "2026-10-27T11:06:54.708357+00:00",
    }
    base.update(surcharges)
    return base


def _document(*lignes: dict[str, Any], catalogue: str = "publier-service-dsoxlab-training",
              revision: str | None = "1aebf49") -> dict[str, Any]:
    return {
        "schema": "dsoxlab-evidence-v1",
        "generated_at": "2026-10-28T12:00:00+00:00",
        "producer": {"name": "dsoxlab", "version": "dsoxlab 0.5.5"},
        "catalog": {"id": catalogue, "version": revision},
        "count": len(lignes),
        "results": list(lignes),
    }


# ── Ce qu'on refuse d'émettre, et pourquoi ────────────────────────────────────

class TestLeMagasinNeDoitJamaisEtreVide:
    """Le portail relit en tout ou rien : une ligne écartée vide le magasin."""

    def test_un_lab_disparu_du_catalogue_n_est_pas_emis(self) -> None:
        # `export` rend `lab_type: null` pour un lab renommé, déplacé ou
        # supprimé : la tentative a eu lieu. Mais le portail l'écarte à la
        # relecture, et il ne garde alors AUCUNE des autres.
        document = _document(_ligne(), _ligne(lab_id="parti", lab_type=None))
        issue = m.convertir(document, maintenant=MAINTENANT)
        assert len(issue["preuves"]) == 1
        assert issue["ecartees"] == {"lab_absent_du_catalogue": 1}

    def test_un_lab_de_validation_n_est_jamais_emis(self) -> None:
        document = _document(_ligne(lab_type="validation"))
        issue = m.convertir(document, maintenant=MAINTENANT)
        assert issue["preuves"] == []
        assert issue["ecartees"] == {"type_validation": 1}

    def test_un_type_inconnu_est_distingue_d_un_lab_disparu(self) -> None:
        # Deux motifs, deux messages : « rien à corriger de ton côté » pour un
        # lab disparu, « un autre producteur » pour un type inconnu.
        issue = m.convertir(
            _document(_ligne(lab_type="epreuve")), maintenant=MAINTENANT
        )
        assert issue["ecartees"] == {"type_inconnu": 1}

    def test_un_verdict_contradictoire_n_est_pas_emis(self) -> None:
        # Le portail refuse le document ENTIER sur cette contradiction.
        issue = m.convertir(
            _document(_ligne(validated=True, passed_tests=3, total_tests=4)),
            maintenant=MAINTENANT,
        )
        assert issue["ecartees"] == {"verdict_contradictoire": 1}

    def test_un_compte_de_tests_impossible_n_est_pas_emis(self) -> None:
        issue = m.convertir(
            _document(_ligne(validated=False, passed_tests=5, total_tests=4)),
            maintenant=MAINTENANT,
        )
        assert issue["ecartees"] == {"compte_incoherent": 1}

    def test_un_catalogue_dans_un_espace_reserve_n_est_pas_emis(self) -> None:
        issue = m.convertir(
            _document(_ligne(catalog="dossier"), catalogue="dossier"),
            maintenant=MAINTENANT,
        )
        assert issue["ecartees"] == {"catalogue_reserve": 1}

    def test_un_booleen_ne_passe_pas_pour_un_entier(self) -> None:
        # `bool` est un `int` en Python : sans garde, `True` vaudrait 1 et le
        # portail refuserait la ligne pour une raison qu'on n'aurait pas vue.
        issue = m.convertir(_document(_ligne(score=True)), maintenant=MAINTENANT)
        assert issue["ecartees"] == {"champ_hors_contrat": 1}


class TestLHorodatage:
    """La date entre dans la clé de dédoublonnage : elle ne se retouche pas."""

    def test_la_forme_ecrite_par_dsoxlab_passe_telle_quelle(self) -> None:
        # Microsecondes et `+00:00`, ce que `datetime.now(UTC).isoformat()`
        # produit et ce que la base stocke. Le portail l'accepte : la
        # « normaliser » en millisecondes et `Z` créerait un doublon pour la
        # même tentative.
        brut = "2026-10-27T11:06:54.708357+00:00"
        issue = m.convertir(_document(_ligne(attempted_at=brut)), maintenant=MAINTENANT)
        assert issue["preuves"][0]["attempted_at"] == brut

    def test_la_forme_en_z_passe_aussi(self) -> None:
        brut = "2026-10-27T11:06:54.708Z"
        issue = m.convertir(_document(_ligne(attempted_at=brut)), maintenant=MAINTENANT)
        assert issue["preuves"][0]["attempted_at"] == brut

    def test_une_date_sans_fuseau_est_refusee(self) -> None:
        issue = m.convertir(
            _document(_ligne(attempted_at="2026-10-27T11:06:54")), maintenant=MAINTENANT
        )
        assert issue["ecartees"] == {"champ_hors_contrat": 1}

    def test_une_date_trop_loin_dans_le_futur_est_refusee(self) -> None:
        tard = (MAINTENANT + timedelta(days=3)).isoformat()
        issue = m.convertir(
            _document(_ligne(attempted_at=tard)), maintenant=MAINTENANT
        )
        assert issue["ecartees"] == {"champ_hors_contrat": 1}


class TestLaRevisionDuCatalogue:
    def test_elle_suit_la_ligne_du_catalogue_du_document(self) -> None:
        issue = m.convertir(_document(_ligne()), maintenant=MAINTENANT)
        assert issue["preuves"][0]["catalogue_revision"] == "1aebf49"

    def test_une_ligne_d_un_autre_catalogue_ne_la_porte_pas(self) -> None:
        # Même règle que le portail : sinon la preuve diffère selon qu'elle
        # passe par le navigateur ou par la CLI.
        issue = m.convertir(
            _document(_ligne(catalog="linux-dsoxlab-training")), maintenant=MAINTENANT
        )
        assert issue["preuves"][0]["catalogue_revision"] is None


class TestLaFormeEmise:
    def test_les_quatorze_champs_du_portail_sont_la(self) -> None:
        issue = m.convertir(_document(_ligne()), maintenant=MAINTENANT)
        preuve = issue["preuves"][0]
        assert set(preuve) == {
            "source", "schema", "catalogue_id", "catalogue_revision", "lab_id",
            "lab_type", "validated", "score", "max_score", "passed_tests",
            "total_tests", "hints_used", "attempted_at", "producer_version",
        }
        # `catalog` de l'export devient `catalogue_id` du portail : deux noms
        # pour la même chose, et c'est le second qui part.
        assert preuve["catalogue_id"] == "publier-service-dsoxlab-training"
        assert preuve["source"] == "dsoxlab"
        assert preuve["schema"] == 1

    def test_un_document_sans_resultats_se_dit(self) -> None:
        issue = m.convertir({"schema": "dsoxlab-evidence-v1"}, maintenant=MAINTENANT)
        assert issue["ecartees"] == {"document_illisible": 1}


# ── La fusion : jamais un écrasement ──────────────────────────────────────────

class TestLaFusion:
    def test_une_preuve_que_seul_le_portail_porte_est_gardee(self) -> None:
        # Le cas qui compte : une tentative jouée sur une autre machine. La
        # perdre serait silencieux et irréversible.
        distante = m.lire(json.dumps({
            "v": 1,
            "preuves": [_preuve_portail(lab="joue-ailleurs")],
            "dernierImport": None,
        }))
        locale = m.convertir(_document(_ligne()), maintenant=MAINTENANT)["preuves"]
        fusion, ajoutees, doublons = m.fusionner(distante, locale)
        assert ajoutees == 1
        assert doublons == 0
        assert {p["lab_id"] for p in fusion["preuves"]} == {
            "joue-ailleurs", "pub-nginx-cache"
        }

    def test_la_meme_tentative_ne_se_duplique_pas(self) -> None:
        locale = m.convertir(_document(_ligne()), maintenant=MAINTENANT)["preuves"]
        distante = m.lire(json.dumps({
            "v": 1, "preuves": list(locale), "dernierImport": None,
        }))
        fusion, ajoutees, doublons = m.fusionner(distante, locale)
        assert (ajoutees, doublons) == (0, 1)
        assert len(fusion["preuves"]) == 1

    def test_la_cle_est_le_triplet_catalogue_lab_date(self) -> None:
        # Deux tentatives du même lab à des dates différentes sont deux
        # preuves : c'est l'historique, pas un doublon.
        premiere = _ligne(attempted_at="2026-10-27T11:06:54.000000+00:00")
        seconde = _ligne(attempted_at="2026-10-27T12:06:54.000000+00:00")
        locale = m.convertir(
            _document(premiere, seconde), maintenant=MAINTENANT
        )["preuves"]
        fusion, ajoutees, _ = m.fusionner(m.lire(None), locale)
        assert ajoutees == 2
        assert len(fusion["preuves"]) == 2

    def test_les_preuves_sortent_triees_par_leur_date(self) -> None:
        # Même tri que le portail : à magasin égal, même empreinte des deux
        # côtés, donc aucun faux conflit.
        tard = _ligne(attempted_at="2026-10-27T12:00:00.000000+00:00")
        tot = _ligne(attempted_at="2026-10-27T09:00:00.000000+00:00")
        locale = m.convertir(_document(tard, tot), maintenant=MAINTENANT)["preuves"]
        fusion, _, _ = m.fusionner(m.lire(None), locale)
        dates = [p["attempted_at"] for p in fusion["preuves"]]
        assert dates == sorted(dates)

    def test_sans_ajout_la_date_du_dernier_import_ne_bouge_pas(self) -> None:
        locale = m.convertir(_document(_ligne()), maintenant=MAINTENANT)["preuves"]
        distante = m.lire(json.dumps({
            "v": 1, "preuves": list(locale), "dernierImport": "2026-10-01T00:00:00+00:00",
        }))
        fusion, _, _ = m.fusionner(distante, locale)
        assert fusion["dernierImport"] == "2026-10-01T00:00:00+00:00"

    def test_un_magasin_distant_illisible_vaut_vide_sans_lever(self) -> None:
        # Tolérant à la LECTURE : ce qu'on relit a pu être écrit par un
        # navigateur ou une autre version. Mais jamais une raison d'écraser.
        for brut in (None, "", "{", "[]", '{"v": 2}', '{"v": 1}'):
            assert m.lire(brut)["preuves"] == []


class TestLesLimites:
    def test_au_dela_du_plafond_de_lignes_rien_ne_part(self) -> None:
        # Le portail refuse en bloc plutôt que de tronquer : mieux vaut le dire
        # avant l'aller-retour, et nommer la limite.
        trop: m.Magasin = {
            "v": 1,
            "preuves": [_preuve_portail(lab=f"l{i}") for i in range(m.LIGNES_MAX + 1)],
            "dernierImport": None,
        }
        with pytest.raises(ChargeRefusee) as refus:
            m.serialiser(trop)
        assert refus.value.cle == "sync_trop_de_lignes"

    def test_la_serialisation_est_compacte(self) -> None:
        # La limite porte sur les octets, et aucun humain ne lit cette chaîne.
        charge = m.serialiser(m.lire(None))
        assert ", " not in charge
        assert json.loads(charge)["v"] == 1


def _preuve_portail(*, lab: str) -> dict[str, Any]:
    return {
        "source": "dsoxlab",
        "schema": 1,
        "catalogue_id": "publier-service-dsoxlab-training",
        "catalogue_revision": None,
        "lab_id": lab,
        "lab_type": "lab",
        "validated": True,
        "score": 100,
        "max_score": 100,
        "passed_tests": 1,
        "total_tests": 1,
        "hints_used": 0,
        "attempted_at": "2026-10-20T08:00:00.000000+00:00",
        "producer_version": None,
    }


# ── L'identité ────────────────────────────────────────────────────────────────

class TestPkce:
    def test_le_condensat_est_bien_le_sha256_du_verificateur(self) -> None:
        import base64
        import hashlib

        verificateur = oidc.nouveau_verificateur()
        config = oidc.Configuration(
            emetteur="https://e.example",
            domaine="https://d.example",
            client_id="c",
            port_retour=14123,
        )
        url = oidc.url_autorisation(config, verificateur, "etat")
        attendu = base64.urlsafe_b64encode(
            hashlib.sha256(verificateur.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        assert f"code_challenge={attendu}" in url
        assert "code_challenge_method=S256" in url

    def test_le_verificateur_fait_la_longueur_exigee(self) -> None:
        # 43 à 128 caractères, base64url sans remplissage (RFC 7636).
        verificateur = oidc.nouveau_verificateur()
        assert 43 <= len(verificateur) <= 128
        assert "=" not in verificateur

    def test_l_adresse_de_retour_est_la_boucle_locale_en_ipv4(self) -> None:
        # `127.0.0.1` et non `localhost` : le nom peut résoudre en IPv6, et le
        # `redirect_uri` enregistré ne correspondrait plus à la lettre.
        config = oidc.Configuration(
            emetteur="https://e.example", domaine="https://d.example",
            client_id="c", port_retour=14123,
        )
        assert "127.0.0.1%3A14123" in oidc.url_autorisation(config, "v", "e")

    def test_le_code_se_lit_dans_les_trois_formes_recopiees(self) -> None:
        for brut in (
            "http://127.0.0.1:14123/?code=abc&state=etat",
            "?code=abc&state=etat",
            "abc",
        ):
            assert oidc.code_depuis_url(brut, "etat") == "abc"

    def test_un_etat_qui_ne_correspond_pas_est_refuse(self) -> None:
        from dsoxlab.sync import ErreurPortail

        with pytest.raises(ErreurPortail) as refus:
            oidc.code_depuis_url("?code=abc&state=forge", "etat")
        assert refus.value.code == "etat_incoherent"


# ── Le contrat d'entrée ───────────────────────────────────────────────────────

class TestLaDeclarationDuCatalogue:
    def test_un_catalogue_sans_bloc_sync_n_en_declare_aucun(self) -> None:
        meta = _meta({"repo": {"id": "x"}})
        assert meta.learning.sync is None

    def test_le_bloc_est_lu_champ_par_champ(self) -> None:
        meta = _meta({
            "repo": {"id": "x"},
            "learning": {
                "portal_url": "https://portail.example/remise/",
                "sync": {
                    "protocol": "learner-sync/1",
                    "api": "https://api.example",
                    "issuer": "https://issuer.example",
                    "oauth_domain": "https://oauth.example",
                    "client_id": "abc123",
                    "callback_port": 14123,
                },
            },
        })
        assert meta.learning.sync is not None
        assert meta.learning.sync.protocol == "learner-sync/1"
        assert meta.learning.sync.callback_port == 14123
        # Le lien de remise et la synchronisation cohabitent : l'un est un lien
        # que l'apprenant ouvre, l'autre un envoi qu'il déclenche.
        assert meta.learning.portal_url == "https://portail.example/remise/"


class TestLaPolitiqueAuPointDUsage:
    """Le parseur charge, la politique refuse : deux endroits, deux rôles."""

    def test_un_catalogue_sans_sync_le_dit_plutot_que_de_lever_une_trace(self) -> None:
        from dsoxlab.services import sync_service

        with pytest.raises(SyncIndisponible) as refus:
            sync_service.configuration(_meta({"repo": {"id": "x"}}))
        assert refus.value.cle == "sync_non_declare"

    def test_un_protocole_inconnu_nomme_celui_qui_est_attendu(self) -> None:
        from dsoxlab.services import sync_service

        meta = _meta({"repo": {"id": "x"},
                      "learning": {"sync": {"protocol": "learner-sync/2"}}})
        with pytest.raises(SyncIndisponible) as refus:
            sync_service.configuration(meta)
        assert refus.value.cle == "sync_protocole_inconnu"
        assert refus.value.params["attendu"] == sync_service.PROTOCOLE

    def test_une_declaration_incomplete_nomme_les_champs_manquants(self) -> None:
        from dsoxlab.services import sync_service

        meta = _meta({"repo": {"id": "x"},
                      "learning": {"sync": {"protocol": "learner-sync/1",
                                            "api": "https://api.example"}}})
        with pytest.raises(SyncIndisponible) as refus:
            sync_service.configuration(meta)
        assert refus.value.cle == "sync_declaration_incomplete"
        champs = str(refus.value.params["champs"])
        for attendu in ("issuer", "oauth_domain", "client_id"):
            assert attendu in champs

    def test_sans_adresse_de_retour_les_deux_formes_sont_nommees(self) -> None:
        from dsoxlab.services import sync_service

        meta = _meta({"repo": {"id": "x"}, "learning": {"sync": _bloc()}})
        with pytest.raises(SyncIndisponible) as refus:
            sync_service.configuration(meta)
        assert refus.value.cle == "sync_retour_absent"

    def test_declarer_les_deux_retours_est_refuse(self) -> None:
        """Les cumuler ne dit pas lequel sert, et le portail en enregistre un.

        Choisir à la place de l'auteur serait se tromper une fois sur deux, et
        l'échec arriverait bien plus tard, en `invalid_request` chez Cognito.
        """
        from dsoxlab.services import sync_service

        meta = _meta({"repo": {"id": "x"}, "learning": {"sync": _bloc(
            callback_url="https://exemple.test/auth/cli/", callback_port=14123)}})
        with pytest.raises(SyncIndisponible) as refus:
            sync_service.configuration(meta)
        assert refus.value.cle == "sync_retour_ambigu"

    def test_une_adresse_de_retour_en_clair_est_refusee(self) -> None:
        from dsoxlab.services import sync_service

        meta = _meta({"repo": {"id": "x"}, "learning": {"sync": _bloc(
            callback_url="http://exemple.test/auth/cli/")}})
        with pytest.raises(SyncIndisponible) as refus:
            sync_service.configuration(meta)
        assert refus.value.cle == "sync_url_refusee"
        assert refus.value.params["champ"] == "callback_url"

    def test_l_adresse_declaree_devient_la_redirect_uri(self) -> None:
        """Et elle part telle quelle : le portail les compare à l'identique."""
        from dsoxlab.services import sync_service

        meta = _meta({"repo": {"id": "x"}, "learning": {"sync": _bloc(
            callback_url="https://exemple.test/auth/cli/")}})
        portail = sync_service.configuration(meta)
        url = oidc.url_autorisation(portail.identite, "v" * 43, "etat")
        assert "redirect_uri=https%3A%2F%2Fexemple.test%2Fauth%2Fcli%2F" in url
        assert "127.0.0.1" not in url

    def test_une_adresse_en_clair_est_refusee(self) -> None:
        # Un portail qui reçoit une preuve ne se joint jamais en http.
        from dsoxlab.services import sync_service

        meta = _meta({"repo": {"id": "x"}, "learning": {"sync": {
            "protocol": "learner-sync/1",
            "api": "http://api.example",
            "issuer": "https://issuer.example",
            "oauth_domain": "https://oauth.example",
            "client_id": "abc",
            "callback_port": 14123,
        }}})
        with pytest.raises(SyncIndisponible) as refus:
            sync_service.configuration(meta)
        assert refus.value.cle == "sync_url_refusee"
        assert refus.value.params["champ"] == "api"


def _bloc(**surcharges: Any) -> dict[str, Any]:
    """Un `learning.sync` complet, sauf ce que le test veut éprouver."""
    bloc: dict[str, Any] = {
        "protocol": "learner-sync/1",
        "api": "https://api.example",
        "issuer": "https://issuer.example",
        "oauth_domain": "https://oauth.example",
        "client_id": "abc",
    }
    bloc.update(surcharges)
    return bloc


def _meta(donnees: dict[str, Any], tmp: Path | None = None) -> RepoMetadata:
    import tempfile

        # Un fichier réel : `from_yaml` nomme le chemin dans ses erreurs, et un
    # faux chemin rendrait les messages invérifiables.
    racine = Path(tmp or tempfile.mkdtemp())
    chemin = racine / "meta.yml"
    import yaml

    chemin.write_text(yaml.safe_dump(donnees), encoding="utf-8")
    return RepoMetadata.from_yaml(chemin)


# ── Ce que `login` conseille quand il échoue ──────────────────────────────────


class TestLeConseilQuandLaConnexionEchoue:
    """Le mode sans navigateur a sa propre cause d'échec, et elle doit se dire.

    L'URL de retour y est recopiée à la main, donc elle arrive parfois tronquée
    ou réécrite : zsh la réécrit AU COLLAGE, avant tout quoting, et le code
    OAuth rendu (`invalid_grant`) ne désigne pas cette cause. Mesuré sur un
    poste réel, trois essais perdus. Le conseil ne vaut que pour ce mode : avec
    navigateur, l'URL ne passe par aucune main.
    """

    def _echouer(self, *, sans_navigateur: bool) -> list[str]:
        """Joue `login` contre une connexion qui lève, et rend les clés dites.

        On interroge les APPELS, pas la sortie rendue : un test qui lirait le
        rendu Rich mesurerait la largeur du terminal.
        """
        import typer

        from dsoxlab.cli import compte
        from dsoxlab.services import sync_service
        from dsoxlab.sync import ErreurPortail
        from dsoxlab.sync.oidc import Configuration

        dites: list[str] = []
        portail = sync_service.Portail(
            identite=Configuration(
                emetteur="https://exemple.test",
                domaine="https://exemple.test",
                client_id="x",
                port_retour=14123,
            ),
            api="https://exemple.test",
        )

        def lever(*_a: object, **_k: object) -> None:
            raise ErreurPortail(400, "invalid_grant")

        anciens = (compte._portail, sync_service.connecter, compte.note,
                   compte.error)
        compte._portail = lambda _root: portail  # type: ignore[assignment]
        sync_service.connecter = lever  # type: ignore[assignment]
        compte.note = dites.append  # type: ignore[assignment]
        compte.error = lambda texte: None  # type: ignore[assignment]
        try:
            with pytest.raises(typer.Exit):
                compte.login(lab_home=None, sans_navigateur=sans_navigateur)
        finally:
            (compte._portail, sync_service.connecter, compte.note,
             compte.error) = anciens  # type: ignore[assignment]
        return dites

    def test_sans_navigateur_le_collage_est_nomme(self) -> None:
        dites = self._echouer(sans_navigateur=True)
        assert any("barre d" in t or "address bar" in t for t in dites), dites

    def test_avec_navigateur_ce_conseil_ne_s_affiche_pas(self) -> None:
        dites = self._echouer(sans_navigateur=False)
        assert not any("barre d" in t or "address bar" in t for t in dites), dites


# ── Ce qui empêche un catalogue de détourner un jeton ─────────────────────────


class TestUnCatalogueNePeutPasDetournerUnJeton:
    """Le défaut que ces tests défendent a été MESURÉ, pas imaginé.

    Un catalogue s'installe par `catalog add`, qui clone un dépôt depuis une
    adresse quelconque, et son `meta.yml` déclare `issuer`, `api` et
    `oauth_domain`. Ces trois adresses étaient validées **indépendamment**, et
    la session n'était nommée que par l'émetteur : un catalogue tiers déclarant
    l'émetteur du vrai portail et sa propre `api` récupérait la session de
    l'apprenant. Au premier `push`, avant toute écriture, le jeton d'accès
    partait vers l'hôte de son choix ; l'heure passée, le jeton de
    rafraîchissement partait vers son `oauth_domain`.
    """

    def _session(self, **surcharges: Any) -> Any:
        from datetime import UTC, datetime, timedelta

        from dsoxlab.sync.jetons import Session

        base: dict[str, Any] = {
            "emetteur": "https://issuer.example",
            "acces": "jeton-d-acces",
            "expire_le": datetime.now(UTC) + timedelta(hours=1),
            "rafraichissement": "jeton-de-rafraichissement",
            "api": "https://api.example",
            "domaine": "https://oauth.example",
            "client_id": "abc",
        }
        base.update(surcharges)
        return Session(**base)

    def test_une_session_dun_autre_portail_est_refusee(self, monkeypatch: Any) -> None:
        from dsoxlab.services import sync_service
        from dsoxlab.sync import jetons as magasin_jetons

        meta = _meta({"repo": {"id": "x"}, "learning": {"sync": _bloc(
            api="https://api.attaquant.test",
            callback_url="https://attaquant.test/retour/")}})
        portail = sync_service.configuration(meta)
        monkeypatch.setattr(magasin_jetons, "lire", lambda _e: self._session())
        with pytest.raises(SansSession) as refus:
            sync_service.session_valide(portail.identite)
        assert refus.value.cle == "sync_session_autre_portail"

    def test_la_session_du_bon_portail_passe(self, monkeypatch: Any) -> None:
        from dsoxlab.services import sync_service
        from dsoxlab.sync import jetons as magasin_jetons

        meta = _meta({"repo": {"id": "x"}, "learning": {"sync": _bloc(
            callback_url="https://exemple.test/auth/cli/")}})
        portail = sync_service.configuration(meta)
        monkeypatch.setattr(magasin_jetons, "lire", lambda _e: self._session())
        assert sync_service.session_valide(portail.identite).acces == "jeton-d-acces"

    def test_une_session_davant_ce_champ_appelle_une_reconnexion(
        self, monkeypatch: Any
    ) -> None:
        """Un fichier écrit par une version antérieure n'a pas d'`api`.

        Le laisser passer rouvrirait exactement la porte qu'on ferme.
        """
        from dsoxlab.services import sync_service
        from dsoxlab.sync import jetons as magasin_jetons

        meta = _meta({"repo": {"id": "x"}, "learning": {"sync": _bloc(
            callback_url="https://exemple.test/auth/cli/")}})
        portail = sync_service.configuration(meta)
        monkeypatch.setattr(magasin_jetons, "lire",
                            lambda _e: self._session(api="", domaine="", client_id=""))
        with pytest.raises(SansSession):
            sync_service.session_valide(portail.identite)

    def test_le_portail_entier_fait_l_aller_retour_sur_disque(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        from dsoxlab.sync import jetons as magasin_jetons

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        magasin_jetons.ecrire(self._session())
        relue = magasin_jetons.lire("https://issuer.example")
        assert relue is not None
        assert relue.liee_a("https://api.example", "https://oauth.example", "abc")
        assert not relue.liee_a("https://api.attaquant.test",
                                "https://oauth.example", "abc")


class TestLeTransportNeSuitAucuneRedirection:
    """``urllib`` suit les redirections en gardant l'en-tête ``Authorization``.

    Son ``HTTPRedirectHandler`` ne retire que ``content-length`` et
    ``content-type``, et accepte une cible en ``http``. Un portail répondant
    ``302 Location: http://ailleurs.test/`` ferait donc partir le jeton en
    clair, contournant la politique d'URL qui n'a contrôlé que le départ.
    """

    def test_une_redirection_n_est_pas_suivie(self) -> None:
        import urllib.error
        import urllib.request

        from dsoxlab.sync import transport

        requete = urllib.request.Request("https://portail.test/v1/x")
        gestionnaire = transport._SansRedirection()
        assert gestionnaire.redirect_request(
            requete, None, 302, "Found", {}, "http://ailleurs.test/"
        ) is None

    def test_la_lecture_est_bornee(self) -> None:
        from dsoxlab.sync import transport

        # Une borne absente se lit ici : `read()` sans argument rend tout.
        assert transport.REPONSE_MAX > 0
        lus: list[int | None] = []

        class _Fausse:
            status = 200

            def read(self, taille: int | None = None) -> bytes:
                lus.append(taille)
                return b"{}"

            def __enter__(self) -> Self:
                return self

            def __exit__(self, *_a: object) -> None:
                return None

        transport._OPENER.open = lambda *_a, **_k: _Fausse()  # type: ignore[method-assign]
        try:
            transport.ouvrir(object(), 1.0)  # type: ignore[arg-type]
        finally:
            del transport._OPENER.open  # type: ignore[attr-defined]
        assert lus == [transport.REPONSE_MAX]


class TestLeCodeDAutorisationNeVaPasAuJournal:
    """Le journal est ramassé par `dsoxlab support`, et publié par `--issue`.

    L'anonymiseur n'y traite que le home, l'utilisateur et les IPv4 : un
    `code=` dans une ligne de requête passait tel quel.
    """

    def test_la_ligne_de_requete_n_est_pas_journalisee(self, caplog: Any) -> None:
        import logging

        from dsoxlab.sync import oidc

        class _Muet(oidc._Retour):  # type: ignore[misc, name-defined]
            def __init__(self) -> None:  # ne pas ouvrir de prise
                self.requestline = "GET /?code=SECRET-123&state=abc HTTP/1.1"

        with caplog.at_level(logging.DEBUG, logger="dsoxlab.sync.oidc"):
            _Muet().log_request(200, 12)
        trace = "\n".join(r.getMessage() for r in caplog.records)
        assert "SECRET-123" not in trace, trace
        assert "code=" not in trace, trace
