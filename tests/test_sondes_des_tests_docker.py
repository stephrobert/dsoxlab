"""Tout test qui démarre un vrai conteneur déclare une sonde (#155).

Deux tests de `test_services.py` échouaient par intermittence, toujours sous
charge, jamais au repos. Leur point commun : ils attendaient qu'un **vrai**
conteneur soit prêt.

C'est la mécanique que le contrat décrit déjà pour les labs. `ready_tcp` seul ne
prouve rien sur un port publié — le proxy de Docker accepte les connexions dès
le `run`, avant que le service écoute — et sans aucune sonde, `start` rend la
main sans qu'aucune étape n'ait établi que le conteneur accepte un `docker
exec`. L'enchaînement devient alors une course, que seule une machine chargée
perd.

**Ce module ne rejoue pas l'instabilité** : elle ne se reproduit plus. Mesuré le
2026-08-24 sous une charge Docker soutenue — 12 exécutions ciblées et 4 suites
complètes, aucun échec. Il empêche la **régression** de ce qui l'a corrigée :
qu'un test crée un conteneur sans déclarer de sonde, ce qui ramènerait la course
sans que rien ne le dise, et rouvrirait une issue dont le coût principal est
d'apprendre à ne plus croire la suite.
"""

from __future__ import annotations

import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parent

#: Les tests dont le conteneur ne devient JAMAIS prêt, par conception : leur
#: sujet est justement ce qui se passe quand il meurt. Une sonde y échouerait,
#: et l'exiger transformerait le garde-fou en obstacle.
#:
#: Nommés un par un, avec la raison. Une exemption qui se déduit d'un motif —
#: « les tests dont le nom contient mort » — finit par couvrir des cas qu'on
#: n'a pas examinés, et le contrôle s'érode sans que personne ne le décide.
_SANS_SONDE_A_DESSEIN = {
    "test_start_status_stop_cycle":
        "hello-world s'arrête aussitôt : le cycle testé est start → status → "
        "stop, pas l'attente d'un service.",
    "test_conteneur_mort_ne_avant_post_start_dit_pourquoi_en_vrai":
        "le conteneur meurt volontairement ; c'est le diagnostic de sa mort "
        "qui est éprouvé.",
}


def _services_sans_sonde(chemin: Path) -> list[str]:
    """Les `Service(...)` construits sans sonde, dans un test d'intégration.

    Seuls comptent les tests qui touchent un vrai Docker : les autres passent
    par un `run_command` neutralisé et n'attendent rien de réel.
    """
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    coupables: list[str] = []

    for fonction in ast.walk(arbre):
        if not isinstance(fonction, ast.FunctionDef):
            continue
        if not _touche_un_vrai_docker(fonction):
            continue
        for noeud in ast.walk(fonction):
            if not isinstance(noeud, ast.Call):
                continue
            if getattr(noeud.func, "id", "") != "Service":
                continue
            if fonction.name in _SANS_SONDE_A_DESSEIN:
                continue
            sondes = {kw.arg for kw in noeud.keywords} & {"ready_exec", "ready_tcp"}
            if not sondes:
                coupables.append(f"{fonction.name} (ligne {noeud.lineno})")
    return coupables


def _touche_un_vrai_docker(fonction: ast.FunctionDef) -> bool:
    """Le test est-il gardé par `skipif(not svc.docker_available())` ?

    C'est la marque, dans ce dépôt, d'un test qui parle au démon plutôt qu'à un
    `run_command` neutralisé.
    """
    return any(
        "docker_available" in ast.dump(decorateur)
        for decorateur in fonction.decorator_list
    )


def test_la_lecture_des_tests_est_representative() -> None:
    """Sans ce contrôle, une lecture cassée rendrait le suivant toujours vert.

    C'est le défaut que tout ce lot corrige, et il serait piquant de l'écrire
    dans le garde-fou censé l'empêcher.
    """
    chemin = RACINE / "test_services.py"
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    integration = [
        f for f in ast.walk(arbre)
        if isinstance(f, ast.FunctionDef) and _touche_un_vrai_docker(f)
    ]

    assert len(integration) >= 3, (
        f"seulement {len(integration)} tests d'intégration repérés : la "
        "détection est cassée, et le contrôle suivant ne mesure rien"
    )


def test_chaque_exemption_designe_un_test_existant() -> None:
    """Une exemption dont le test a disparu couvre le vide, et le cache.

    Elle survivrait au renommage du test qu'elle exemptait, et exempterait
    silencieusement le suivant portant le même nom.
    """
    source = (RACINE / "test_services.py").read_text(encoding="utf-8")

    orphelines = [nom for nom in _SANS_SONDE_A_DESSEIN
                  if f"def {nom}(" not in source]

    assert orphelines == [], f"exemptions sans test correspondant : {orphelines}"


def test_aucun_conteneur_reel_ne_demarre_sans_sonde() -> None:
    """La correction de #155, tenue par un test plutôt que par la mémoire.

    Un `Service` sans sonde rend la main dès que `docker run` a répondu, ce qui
    ne dit rien de l'état du service à l'intérieur. Le test qui suit devient
    alors une course, gagnée au repos et perdue sous charge — un rouge qui
    redevient vert sans qu'on ait rien fait, c'est-à-dire pire qu'un test
    absent : il apprend à relancer plutôt qu'à lire.
    """
    coupables = _services_sans_sonde(RACINE / "test_services.py")

    assert coupables == [], (
        "ces tests démarrent un vrai conteneur sans déclarer ready_exec ni "
        f"ready_tcp : {coupables}"
    )
