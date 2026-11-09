"""D'où vient une machine : l'index, les métadonnées natives, et `infra origin`.

Ce que ces tests défendent (issue #345)
---------------------------------------

Retrouver le répertoire d'un catalogue depuis une ressource provisionnée tient à
quatre propriétés, et chacune peut se perdre sans que rien ne le dise :

1. **l'origine ne se réécrit pas.** C'est ce qui fait d'elle une preuve plutôt
   qu'un pointeur, et c'est la différence avec ``catalogue-actif``. Un
   reprovision, même depuis un répertoire déplacé, garde la date et le chemin du
   provisionnement ;
2. **la provenance est STABLE entre deux applies.** Ce n'est pas une élégance :
   mesuré sur un provision réel avec `dmacvicar/libvirt` 0.9.7, toute mise à
   jour in-place d'un domaine en marche échoue sur « Provider produced
   inconsistent result after apply », son `.id` passant de 21 à 22 entre l'envoi
   et la relecture. Un XML qui changerait à chaque provision rendrait donc le
   dépôt improvisionnable — défaut bien réel, rencontré en construisant cette
   fonctionnalité, et c'est pourquoi la ressource est relue avant d'être
   réécrite ;
3. **elle survit à la perte de l'index**, par les métadonnées que la ressource
   porte elle-même ;
4. **un chemin disparu se dit**, au lieu d'être présenté comme actif.

Ces tests ne lancent ni Terraform ni hyperviseur : ils mesurent les décisions
(que consigne-t-on, qu'écrase-t-on, que répond-on) et non le provider, dont les
propriétés ont été mesurées à part, par exécution réelle, et consignées dans la
docstring de `services/provenance.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dsoxlab.models.repo import InfraDefinition, RepoMetadata
from dsoxlab.services import provenance as prov


@pytest.fixture(autouse=True)
def _etat_isole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def _depot(tmp_path: Path, *, repo_id: str = "depot-a", nom: str = "clone") -> RepoMetadata:
    chemin = tmp_path / nom
    chemin.mkdir(parents=True, exist_ok=True)
    return RepoMetadata(
        id=repo_id,
        path=chemin,
        infra=InfraDefinition(provider="kvm", network="lab-a", cidr="10.9.9.0/24"),
    )


def _sans_hyperviseur(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aucune ressource ne répond : le gabarit est alors seul à décider.

    Sans ce simulacre, ces tests interrogeraient le libvirt de la machine qui les
    exécute, et mesureraient donc son parc plutôt que le code.
    """
    monkeypatch.setattr(prov, "lire_sur_la_ressource", lambda nom, provider: None)


# ── 1. l'index ────────────────────────────────────────────────────────────────


class TestLIndex:
    def test_ce_qui_est_enregistre_se_relit(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        origines = prov.construire(
            depot, provider="kvm", ressources=["a.lab", "b.lab"],
            provision_id="p1", horodate="2026-11-09T10:00:00Z",
        )
        prov.enregistrer(origines, depot.id)

        relues = prov.lire_l_index(depot.id)

        assert [o.resource for o in relues] == ["a.lab", "b.lab"]
        assert all(o.catalog_path == str(depot.path.resolve()) for o in relues)
        assert all(o.source == "index" for o in relues)

    def test_un_schema_inconnu_est_ignore_et_non_devine(self, tmp_path: Path) -> None:
        """Une provenance à moitié lue serait une preuve fausse."""
        depot = _depot(tmp_path)
        chemin = prov.chemin_de_l_index(depot.id)
        chemin.parent.mkdir(parents=True)
        chemin.write_text(
            json.dumps({"schema": "venu-du-futur", "resources": [{"resource": "x"}]}),
            encoding="utf-8",
        )

        assert prov.lire_l_index(depot.id) == []

    def test_un_index_illisible_ne_fait_pas_echouer_la_lecture(
        self, tmp_path: Path
    ) -> None:
        depot = _depot(tmp_path)
        chemin = prov.chemin_de_l_index(depot.id)
        chemin.parent.mkdir(parents=True)
        chemin.write_text("{ ceci n'est pas du json", encoding="utf-8")

        assert prov.lire_l_index(depot.id) == []

    def test_une_ligne_sans_champ_requis_est_ecartee(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        chemin = prov.chemin_de_l_index(depot.id)
        chemin.parent.mkdir(parents=True)
        chemin.write_text(json.dumps({
            "schema": prov.SCHEMA,
            "resources": [
                {"catalog_id": "a", "provider": "kvm", "resource": "x.lab"},
                {"catalog_id": "a", "catalog_path": "/c", "provider": "kvm",
                 "resource": "y.lab"},
            ],
        }), encoding="utf-8")

        assert [o.resource for o in prov.lire_l_index(depot.id)] == ["y.lab"]

    def test_deux_depots_ne_se_marchent_pas_dessus(self, tmp_path: Path) -> None:
        """Un index par dépôt : le verrou d'écriture de dsoxlab est par dépôt."""
        a = _depot(tmp_path, repo_id="depot-a", nom="a")
        b = _depot(tmp_path, repo_id="depot-b", nom="b")
        prov.enregistrer(prov.construire(
            a, provider="kvm", ressources=["m.lab"],
            provision_id="p", horodate="h"), a.id)
        prov.enregistrer(prov.construire(
            b, provider="kvm", ressources=["m.lab"],
            provision_id="p", horodate="h"), b.id)

        assert len(prov.lire_l_index(a.id)) == 1
        assert len(prov.toutes_les_origines()) == 2, (
            "deux machines homonymes de deux dépôts sont deux machines"
        )


# ── 2. l'origine ne se réécrit pas ────────────────────────────────────────────


class TestUneOrigineNeSeReecritPas:
    def test_un_reprovision_garde_la_date_et_le_chemin_d_origine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le cœur du contrat : une preuve ne se rafraîchit pas.

        Le dépôt est même DÉPLACÉ entre les deux provisions, ce qui est le cas où
        une réécriture serait la plus tentante et la plus trompeuse.
        """
        _sans_hyperviseur(monkeypatch)
        depot = _depot(tmp_path, nom="avant")
        premier = prov.gabarits(depot, provider="kvm", ressources=["a.lab"])
        prov.enregistrer(list(premier.values()), depot.id)
        origine_initiale = premier["a.lab"]

        deplace = _depot(tmp_path, nom="apres")
        second = prov.gabarits(deplace, provider="kvm", ressources=["a.lab"])

        assert second["a.lab"].catalog_path == origine_initiale.catalog_path
        assert second["a.lab"].provisioned_at == origine_initiale.provisioned_at
        assert second["a.lab"].provision_id == origine_initiale.provision_id

    def test_un_hote_ajoute_recoit_sa_propre_date(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Les deux cas cohabitent dans un même apply, et c'est le cas courant.

        Ajouter un hôte à un `meta.yml` déjà monté ne doit ni redater les
        anciennes machines, ni donner à la nouvelle la date des premières.
        """
        _sans_hyperviseur(monkeypatch)
        depot = _depot(tmp_path)
        prov.enregistrer(list(prov.gabarits(
            depot, provider="kvm", ressources=["a.lab"]).values()), depot.id)

        gabarit = prov.gabarits(depot, provider="kvm", ressources=["a.lab", "b.lab"])

        ancienne = prov.lire_l_index(depot.id)[0]
        assert gabarit["a.lab"].provision_id == ancienne.provision_id
        assert gabarit["a.lab"].provisioned_at == ancienne.provisioned_at
        # L'assertion porte sur l'IDENTIFIANT, et non sur l'horodatage : celui-ci
        # est à la seconde, et deux provisions peuvent tomber dans la même. C'est
        # `provision_id` qui discrimine, et c'est tout son rôle.
        assert gabarit["b.lab"].provision_id != ancienne.provision_id

    def test_la_ressource_fait_foi_quand_l_index_a_disparu(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LE défaut mesuré en construisant la fonctionnalité.

        Avec l'index pour seule mémoire, l'effacer suffisait à fabriquer un
        horodatage neuf, donc un XML différent, donc une mise à jour du domaine
        — et le provider libvirt échoue sur toute mise à jour in-place d'un
        domaine en marche. Un index effacé rendait le dépôt improvisionnable.
        """
        depot = _depot(tmp_path)
        porte_par_la_machine = prov.Origine(
            catalog_id=depot.id,
            catalog_path=str(depot.path.resolve()),
            provider="kvm",
            resource="a.lab",
            provisioned_at="2026-01-01T00:00:00Z",
            provision_id="celui-d-origine",
            source="ressource",
        )
        monkeypatch.setattr(
            prov, "lire_sur_la_ressource",
            lambda nom, provider: porte_par_la_machine if nom == "a.lab" else None,
        )

        gabarit = prov.gabarits(depot, provider="kvm", ressources=["a.lab"])

        assert gabarit["a.lab"].provision_id == "celui-d-origine"
        assert gabarit["a.lab"].provisioned_at == "2026-01-01T00:00:00Z"

    def test_le_xml_pose_est_identique_a_lui_meme(self, tmp_path: Path) -> None:
        """La stabilité se mesure sur ce qui est RÉELLEMENT passé au template.

        Deux appels successifs doivent rendre le même document, sinon Terraform
        voit une mise à jour là où rien n'a changé.
        """
        depot = _depot(tmp_path)
        origine = prov.construire(
            depot, provider="kvm", ressources=["a.lab"],
            provision_id="p", horodate="2026-11-09T10:00:00Z")[0]
        prov.enregistrer([origine], depot.id)

        premier = prov.tfvars_de_provenance(
            depot, provider="kvm", ressources=["a.lab"])
        second = prov.tfvars_de_provenance(
            depot, provider="kvm", ressources=["a.lab"])

        assert premier == second
        assert premier["provenance_xml"]["a.lab"].count(
            "<dsoxlab:provisionedAt>") == 1


# ── 3. ce que la ressource porte ──────────────────────────────────────────────


class TestLesMetadonneesNatives:
    def test_le_xml_echappe_ce_qui_casserait_le_document(self, tmp_path: Path) -> None:
        """Un chemin peut porter un `&`, et libvirt refuse alors le domaine ENTIER.

        C'est la raison pour laquelle ce XML est fabriqué en Python : HCL n'a
        aucune fonction d'échappement XML.
        """
        from xml.etree import ElementTree

        depot = _depot(tmp_path, nom="labs & co")
        origine = prov.construire(
            depot, provider="kvm", ressources=["a.lab"],
            provision_id="p", horodate="h")[0]

        xml = prov.xml_pour_libvirt(origine)

        assert "&amp;" in xml
        # Le document est RELU, et non seulement regardé : vérifier la présence
        # d'une entité ne dit pas qu'il est bien formé.
        racine = ElementTree.fromstring(xml)  # noqa: S314 — produit juste au-dessus
        valeurs = {e.tag.rsplit("}", 1)[-1]: e.text for e in racine}
        assert valeurs["catalogPath"] == str(depot.path.resolve())

    def test_les_cles_incus_vivent_dans_l_espace_utilisateur(
        self, tmp_path: Path
    ) -> None:
        """`user.` est le seul espace qu'Incus réserve aux applications."""
        depot = _depot(tmp_path)
        origine = prov.construire(
            depot, provider="incus", ressources=["a-lab"],
            provision_id="p", horodate="h")[0]

        config = prov.config_pour_incus(origine)

        assert all(cle.startswith("user.dsoxlab.") for cle in config)
        assert config["user.dsoxlab.catalog_path"] == str(depot.path.resolve())

    def test_un_provider_sans_metadonnees_natives_ne_recoit_aucune_variable(
        self, tmp_path: Path
    ) -> None:
        """Un tfvars qui porte une variable inconnue du template FAIT ÉCHOUER le plan."""
        depot = _depot(tmp_path)

        assert prov.tfvars_de_provenance(
            depot, provider="outscale", ressources=["a.lab"]) == {}

    def test_le_nom_consigne_est_celui_que_le_provider_porte(self) -> None:
        """Incus refuse les points : c'est `a-lab` qu'on lit dans `incus list`.

        Consigner le FQDN donnerait un index qu'on ne peut pas interroger avec ce
        qu'on a sous les yeux, ce qui est le défaut même que l'issue corrige.
        """
        assert prov.nom_chez_le_provider("incus", "alma-1.lab") == "alma-1-lab"
        assert prov.nom_chez_le_provider("kvm", "alma-1.lab") == "alma-1.lab"

    def test_un_xml_avec_dtd_est_refuse_avant_tout_parsing(self) -> None:
        """Le vecteur d'expansion récursive, que la bibliothèque standard ne borne pas."""
        assert not prov._xml_recevable('<!DOCTYPE x [<!ENTITY a "aa">]><x/>')
        assert not prov._xml_recevable("<x>" + "a" * (prov.XML_MAX + 1) + "</x>")
        assert prov._xml_recevable("<provenance><catalogId>x</catalogId></provenance>")


# ── 4. ce que `destroy` oublie, et ce qu'il garde ─────────────────────────────


class TestCeQueDestroyOublie:
    def test_une_ressource_detruite_sort_de_l_index(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        prov.enregistrer(prov.construire(
            depot, provider="kvm", ressources=["a.lab", "b.lab"],
            provision_id="p", horodate="h"), depot.id)

        prov.oublier(["a.lab"], depot.id, provider="kvm")

        assert [o.resource for o in prov.lire_l_index(depot.id)] == ["b.lab"]

    def test_un_autre_provider_n_est_pas_touche(self, tmp_path: Path) -> None:
        """Deux providers peuvent porter une machine de même nom : ce sont deux machines."""
        depot = _depot(tmp_path)
        prov.enregistrer(prov.construire(
            depot, provider="kvm", ressources=["a.lab"],
            provision_id="p", horodate="h"), depot.id)
        prov.enregistrer(prov.construire(
            depot, provider="incus", ressources=["a.lab"],
            provision_id="p", horodate="h"), depot.id)

        prov.oublier(["a.lab"], depot.id, provider="kvm")

        restantes = prov.lire_l_index(depot.id)
        assert [(o.provider, o.resource) for o in restantes] == [("incus", "a.lab")]


# ── 5. la recherche ───────────────────────────────────────────────────────────


class TestLaRecherche:
    def test_on_trouve_par_le_nom_du_meta_yml_comme_par_celui_du_provider(
        self, tmp_path: Path
    ) -> None:
        depot = _depot(tmp_path)
        prov.enregistrer(prov.construire(
            depot, provider="incus", ressources=["a-lab"],
            provision_id="p", horodate="h"), depot.id)

        assert prov.chercher("a-lab")
        assert prov.chercher("a.lab"), (
            "le nom déclaré dans le meta.yml doit mener à la ressource"
        )

    def test_on_trouve_par_uuid(self, tmp_path: Path) -> None:
        from dataclasses import replace

        depot = _depot(tmp_path)
        origine = prov.construire(
            depot, provider="kvm", ressources=["a.lab"],
            provision_id="p", horodate="h")[0]
        prov.enregistrer([replace(origine, resource_uuid="dae6-1234")], depot.id)

        assert prov.chercher("dae6-1234")

    def test_deux_homonymes_sont_tous_deux_rendus(self, tmp_path: Path) -> None:
        """Trancher à la place de l'utilisateur serait décider de quelle machine il parle."""
        a = _depot(tmp_path, repo_id="depot-a", nom="a")
        b = _depot(tmp_path, repo_id="depot-b", nom="b")
        for depot in (a, b):
            prov.enregistrer(prov.construire(
                depot, provider="kvm", ressources=["m.lab"],
                provision_id="p", horodate="h"), depot.id)

        assert len(prov.chercher("m.lab")) == 2

    def test_un_chemin_disparu_se_dit(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path, nom="ephemere")
        origine = prov.construire(
            depot, provider="kvm", ressources=["a.lab"],
            provision_id="p", horodate="h")[0]

        assert origine.etat_du_chemin() == "present"
        import shutil

        shutil.rmtree(depot.path)
        assert origine.etat_du_chemin() == "absent"
        assert origine.catalog_path == str(depot.path.resolve()), (
            "le chemin d'origine ne doit pas être effacé parce qu'il a disparu"
        )
