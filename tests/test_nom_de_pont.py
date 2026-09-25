"""Le pont réseau qu'un provider créera, et la limite du noyau (#214).

Le noyau Linux refuse un nom d'interface de plus de quinze caractères
(``IFNAMSIZ`` vaut 16, terminateur compris). Le template kvm **calcule** ce nom
depuis ``infra.network``, si bien que le nom fautif n'apparaît nulle part dans le
``meta.yml`` — et l'échec arrive après le téléchargement de l'image de base, sur
un « Numerical result out of range » qui ne nomme ni le pont, ni la limite, ni le
champ qui l'a produit.

Le test le plus important de ce fichier n'est pas celui de la limite :
c'est :func:`test_la_derivation_kvm_est_celle_du_template`, qui confronte la
règle Python à l'expression HCL réellement écrite. Deux définitions de « comment
s'appelle le pont » finiraient par diverger, et la divergence resterait invisible
jusqu'au prochain catalogue au nom long.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import dsoxlab
from dsoxlab.infra.pont import (
    IFNAMSIZ_UTILES,
    NomDePontTropLong,
    nom_du_pont,
    reseau_raccourci,
    verifier_nom_de_pont,
)
from dsoxlab.models.repo import HostDefinition, InfraDefinition, RepoMetadata

_TEMPLATE_KVM = (
    Path(dsoxlab.__file__).resolve().parent
    / "templates" / "terraform" / "kvm" / "main.tf"
)


def _meta(
    reseau: str, *, provider: str = "kvm", overrides: dict[str, object] | None = None,
) -> RepoMetadata:
    return RepoMetadata(
        id="catalogue-test",
        category="demo",
        # Jamais lu : ces contrôles comptent des caractères, ils
        # n'ouvrent aucun fichier.
        path=Path(__file__).parent,
        infra=InfraDefinition(
            provider=provider,
            network=reseau,
            cidr="10.10.10.0/24",
            hosts=[HostDefinition(name="n1.lab", distro="debian13")],
            providers={provider: overrides} if overrides else {},
        ),
    )


# ── la dérivation, par provider ──────────────────────────────────────────────

@pytest.mark.parametrize(("reseau", "attendu"), [
    ("lab-linux", "virbr-linux"),
    ("lab-k8s", "virbr-k8s"),
    ("lab-kubernetes", "virbr-kubernetes"),
    # `replace` en HCL retire l'occurrence OÙ QU'ELLE SOIT, pas un préfixe :
    # « mon-lab-reseau » perd son « lab- » au milieu et garde le reste. On
    # reproduit ce comportement, pas celui qu'on aurait choisi.
    ("mon-lab-reseau", "virbr-mon-reseau"),
    ("sans-prefixe", "virbr-sans-prefixe"),
])
def test_la_derivation_kvm_suit_le_template(reseau: str, attendu: str) -> None:
    assert nom_du_pont(_meta(reseau), "kvm") == attendu


def test_incus_nomme_son_pont_comme_son_reseau() -> None:
    """Incus crée un pont Linux portant exactement le nom du réseau.

    La limite s'applique donc directement à `infra.network`, sans la marge de
    quatre caractères que `lab-` offre côté kvm.
    """
    assert nom_du_pont(_meta("lab-kubernetes", provider="incus"), "incus") == (
        "lab-kubernetes"
    )


def test_un_provider_cloud_ne_cree_aucun_pont() -> None:
    """Outscale provisionne ailleurs : il n'y a pas d'interface sur ce poste."""
    assert nom_du_pont(_meta("lab-x", provider="outscale"), "outscale") is None


def test_sans_reseau_declare_il_n_y_a_rien_a_mesurer() -> None:
    assert nom_du_pont(_meta(""), "kvm") is None


def test_un_bridge_name_declare_l_emporte() -> None:
    """Le template lit `bridge_name` en premier : le contrôle doit faire pareil.

    Sinon il refuserait un catalogue qui a précisément contourné le problème en
    nommant son pont lui-même.
    """
    meta = _meta("lab-kubernetes", overrides={"bridge_name": "br-k8s"})

    assert nom_du_pont(meta, "kvm") == "br-k8s"
    verifier_nom_de_pont(meta, "kvm")  # ne lève pas


# ── la limite ────────────────────────────────────────────────────────────────

def test_quinze_caracteres_passent() -> None:
    """La limite est la dernière valeur acceptée, pas la première refusée."""
    meta = _meta("lab-" + "a" * 9)  # virbr- + 9 = 15
    pont = nom_du_pont(meta, "kvm")

    assert pont is not None
    assert len(pont) == IFNAMSIZ_UTILES
    verifier_nom_de_pont(meta, "kvm")


def test_seize_caracteres_levent_avec_les_faits() -> None:
    """Le cas exact de l'issue : `lab-kubernetes` → `virbr-kubernetes`."""
    with pytest.raises(NomDePontTropLong) as leve:
        verifier_nom_de_pont(_meta("lab-kubernetes"), "kvm")

    exc = leve.value
    assert exc.pont == "virbr-kubernetes"
    assert exc.reseau == "lab-kubernetes"
    assert exc.provider == "kvm"
    assert exc.limite == 15
    assert exc.trop == 1
    # La cible que le message annonce : « lab-kubernetes » fait 14, il faut 13.
    assert exc.max_reseau == 13


def test_la_cible_annoncee_tient_vraiment() -> None:
    """Un nom à la longueur annoncée doit passer, sinon le message ment.

    Le contrôle porte sur le PONT, la cible est donnée sur le RÉSEAU : ces deux
    longueurs diffèrent de la dérivation, et c'est exactement le genre d'écart
    qu'un message calculé à la main rate.
    """
    for reseau in ("lab-kubernetes", "lab-observabilite", "sans-prefixe-long-nom"):
        with pytest.raises(NomDePontTropLong) as leve:
            verifier_nom_de_pont(_meta(reseau), "kvm")
        cible = leve.value.max_reseau

        verifier_nom_de_pont(_meta(reseau[:cible]), "kvm")  # ne lève pas


def test_l_exception_ne_porte_aucune_phrase() -> None:
    """Elle porte des données : c'est la CLI qui traduit.

    Un message écrit ici s'afficherait dans une seule langue, et ce module est
    sous `infra/`, où rien ne passe par `_()`.
    """
    with pytest.raises(NomDePontTropLong) as leve:
        verifier_nom_de_pont(_meta("lab-kubernetes"), "kvm")

    assert "kubernetes" in str(leve.value)
    for mot in ("noyau", "kernel", "raccourci", "shorten"):
        assert mot not in str(leve.value).lower()


# ── la suggestion ────────────────────────────────────────────────────────────

def test_la_suggestion_tient_dans_la_limite() -> None:
    """Proposer vaut mieux que dire « raccourcissez ».

    L'auteur devrait sinon recalculer une dérivation qu'il ne connaît pas — et
    c'est précisément ce que l'issue reproche au message de libvirt.
    """
    for reseau in ("lab-kubernetes", "lab-observabilite-complete", "tres-long-reseau"):
        pont = nom_du_pont(_meta(reseau), "kvm")
        assert pont is not None
        propose = reseau_raccourci(reseau, pont)

        nouveau = nom_du_pont(_meta(propose), "kvm")
        assert nouveau is not None
        assert len(nouveau) <= IFNAMSIZ_UTILES, (
            f"{reseau} → {propose} → {nouveau} dépasse encore"
        )
        assert propose


def test_la_suggestion_n_est_jamais_vide() -> None:
    """Un nom vide ferait disparaître le réseau du contrat, ce qui est pire."""
    assert reseau_raccourci("l", "virbr-" + "x" * 20)


# ── la cohérence avec le template, le vrai garde-fou ─────────────────────────

def test_la_derivation_kvm_est_celle_du_template() -> None:
    """La règle Python doit être celle du HCL, ou le contrôle mentira.

    On ne compare pas des chaînes au hasard : on extrait l'expression du
    template et on vérifie qu'elle porte bien le préfixe et l'élagage que
    `pont.py` reproduit. Si quelqu'un change le template, ce test échoue et
    nomme le fichier.
    """
    hcl = _TEMPLATE_KVM.read_text(encoding="utf-8")
    ligne = re.search(r"bridge_name\s*=\s*lookup\((.+)\)\n", hcl)

    assert ligne is not None, f"la dérivation a disparu de {_TEMPLATE_KVM.name}"
    expression = ligne.group(1)
    assert '"bridge_name"' in expression, "l'override bridge_name n'est plus lu"
    assert 'virbr-${replace(var.network_name, "lab-", "")}' in expression, (
        "le template ne dérive plus le pont comme pont.py le reproduit : "
        "mets les deux en accord, ou le contrôle annoncera un nom qui n'existe pas"
    )
