"""La grille du formateur signale-t-elle ce qu'elle doit, et rien d'autre ?

Cette grille est née d'une lecture de labs à la place d'un apprenant, sur cinq
catalogues. Elle a confirmé que `linux-dsoxlab-training` et
`terraform-dsoxlab-training` donnent tout ce qu'il faut, et trouvé dans
`ansible-training` 42 labs dont la majorité des assertions ne portent aucun
message, plus un lab noté **sans aucune mission** (`bootstrap-prepare-managed-nodes`,
dont `challenge/` ne contient que `hints.yaml` et `tests/`).

Un contrôle qui refuse doit être éprouvé sur ce qu'il doit refuser **et** sur ce
qu'il doit laisser passer : les faux positifs sont testés aussi explicitement
que les vrais, parce qu'un audit bavard ne se lit plus.
"""

from __future__ import annotations

from pathlib import Path

from dsoxlab.models.lab import LabDefinition, ValidationConfig
from dsoxlab.models.runtime import RuntimeConfig, RuntimeType
from dsoxlab.services.audit_pedagogique import (
    ATTENTION,
    MANQUE,
    analyser_assertions,
    dossier_pour_relecture,
    examiner,
    examiner_lab,
)

COURS = "# Lab\n\n## Un\n\nDu texte.\n\n## Deux\n\nDu texte.\n\n## Trois\n\nEt.\n"

MISSION_COMPLETE = """# Challenge

## Mission

Faire la chose.

## Validation

```bash
dsoxlab check mon-lab
```
"""

TESTS_AVEC_MESSAGES = '''
def test_la_chose_est_faite() -> None:
    assert chose.exists(), "Crée la chose : touch chose"
    assert chose.read_text(), "La chose est vide : écris-y le mot du cours"
'''

TESTS_SANS_MESSAGE = '''
def test_la_chose_est_faite() -> None:
    assert chose.exists()
    assert chose.read_text()
    assert chose.stat().st_size > 10
'''


def _poser_lab(
    racine: Path,
    *,
    cours: str = COURS,
    mission: str = MISSION_COMPLETE,
    tests: str = TESTS_AVEC_MESSAGES,
    indices: bool = True,
) -> LabDefinition:
    """Un lab complet sur le disque, dont chaque pièce est retirable."""
    (racine / "challenge" / "tests").mkdir(parents=True, exist_ok=True)
    if cours:
        (racine / "README.md").write_text(cours, encoding="utf-8")
    if mission:
        (racine / "challenge" / "README.md").write_text(mission, encoding="utf-8")
    if tests:
        (racine / "challenge" / "tests" / "test_functional.py").write_text(
            tests, encoding="utf-8"
        )
    if indices:
        (racine / "challenge" / "hints.yaml").write_text("hints: []\n", encoding="utf-8")
    return LabDefinition(
        id="mon-lab",
        title="Mon lab",
        level="l1",
        path=racine,
        skills=["demo"],
        distros=["any"],
        doc_url="https://example.invalid/guide",
        validation=ValidationConfig(),
        runtime=RuntimeConfig(type=RuntimeType.SHELL, workdir="challenge/work"),
    )


class TestUnLabCompletNeDeclencheRien:
    def test_rien_a_signaler(self, tmp_path: Path) -> None:
        """Le contre-test : sans lui, une grille qui crie toujours passerait."""
        assert examiner_lab(_poser_lab(tmp_path))[0] == []


class TestCeQuiEmpecheDeFaireLeTravail:
    def test_une_mission_dans_le_scenario_ne_declenche_rien(
        self, tmp_path: Path
    ) -> None:
        """La disposition de kubernetes : pas de challenge/README.md, l'énoncé
        vit dans le cours. C'est ce que la première version de la grille
        déclarait « aucune mission », soixante-quatre fois de suite."""
        cours = COURS + "\n## What is expected of you\n\nFaire la chose.\n\n"
        cours += "```bash\ndsoxlab check mon-lab\n```\n"
        constats, _mesure = examiner_lab(_poser_lab(tmp_path, cours=cours, mission=""))

        assert [c.cle for c in constats] == []

    def test_un_lab_sans_aucun_document_est_un_manque(self, tmp_path: Path) -> None:
        """Le silence total se dit une fois, par le cours : la mission n'a pas
        de constat à elle, faute de pouvoir distinguer mécaniquement un énoncé
        d'une explication."""
        constats, _mesure = examiner_lab(_poser_lab(tmp_path, mission="", cours=""))
        assert [c.cle for c in constats] == ["audit_cours_absent"]
        assert constats[0].niveau == MANQUE

    def test_des_asserts_sans_message_sont_un_manque(self, tmp_path: Path) -> None:
        """Sans message, `check` dit QUELS tests échouent et rien de plus."""
        constats, _mesure = examiner_lab(_poser_lab(tmp_path, tests=TESTS_SANS_MESSAGE))
        cles = [c.cle for c in constats]
        assert "audit_asserts_sans_message" in cles
        constat = next(c for c in constats if c.cle == "audit_asserts_sans_message")
        assert constat.niveau == MANQUE
        assert constat.params == {"sans": 3, "total": 3}

    def test_aucun_test_est_un_manque(self, tmp_path: Path) -> None:
        constats, _mesure = examiner_lab(_poser_lab(tmp_path, tests=""))
        assert "audit_aucun_test" in [c.cle for c in constats]

    def test_aucun_cours_est_un_manque(self, tmp_path: Path) -> None:
        constats, _mesure = examiner_lab(_poser_lab(tmp_path, cours=""))
        assert "audit_cours_absent" in [c.cle for c in constats]


class TestCeQuiMeriteAttentionSansEmpecher:
    def test_une_mission_sans_validation(self, tmp_path: Path) -> None:
        """Le cas de devsecops et de python : 20 labs sur 20."""
        mission = "# Challenge\n\n## Mission\n\nFaire la chose.\n"
        constats, _mesure = examiner_lab(_poser_lab(tmp_path, mission=mission))
        assert [c.cle for c in constats] == ["audit_mission_sans_validation"]
        assert constats[0].niveau == ATTENTION

    def test_aucun_indice(self, tmp_path: Path) -> None:
        """Le cas de 13 labs de linux : un apprenant bloqué n'a aucun palier."""
        constats, _mesure = examiner_lab(_poser_lab(tmp_path, indices=False))
        assert [c.cle for c in constats] == ["audit_aucun_indice"]
        assert constats[0].niveau == ATTENTION


class TestLeVerdict:
    def test_un_manque_rend_le_rapport_non_ok(self, tmp_path: Path) -> None:
        lab = _poser_lab(tmp_path, mission="", cours="")
        assert examiner([lab]).ok is False

    def test_une_attention_seule_laisse_le_rapport_ok(self, tmp_path: Path) -> None:
        """Un lab sans indice reste jouable : ce n'est pas un échec."""
        lab = _poser_lab(tmp_path, indices=False)
        rapport = examiner([lab])
        assert rapport.ok is True
        assert len(rapport.par_niveau(ATTENTION)) == 1

    def test_le_nombre_de_labs_examines_est_dit(self, tmp_path: Path) -> None:
        """« Je n'ai rien trouvé » doit se distinguer de « je n'ai rien lu »."""
        assert examiner([]).labs_examines == 0


class TestDossierDeRelecture:
    def test_le_dossier_porte_les_trois_pieces_de_chaque_lab(
        self, tmp_path: Path
    ) -> None:
        """Cours, mission et tests : ce qu'il faut pour juger, et dans cet ordre."""
        dossier = dossier_pour_relecture([_poser_lab(tmp_path)])

        assert "Du texte." in dossier, "le cours"
        assert "Faire la chose." in dossier, "la mission"
        assert "test_la_chose_est_faite" in dossier, "les tests"
        assert dossier.index("Du texte.") < dossier.index("Faire la chose.")

    def test_le_dossier_ne_fuit_aucun_chemin_de_la_machine(
        self, tmp_path: Path
    ) -> None:
        """Il part à un relecteur, voire à un service tiers : il ne porte que
        ce que le catalogue déclare."""
        dossier = dossier_pour_relecture([_poser_lab(tmp_path)])

        assert str(tmp_path) not in dossier
        assert str(Path.home()) not in dossier


class TestLaPariteDesLangues:
    """Un message d'assertion s'affiche à l'apprenant : il a les deux langues.

    C'est la seule pièce d'un lab qui ne peut pas vivre en deux fichiers, le
    contrat imposant le nom `test_functional.py`. D'où la forme conventionnelle
    `message(en=..., fr=...)`, que le `conftest.py` du catalogue fournit et que
    dsoxlab se contente de reconnaître : un test de lab doit rester jouable par
    un simple `pytest`, sans l'outil installé.
    """

    def test_un_appel_a_deux_langues_compte_comme_bilingue(self) -> None:
        mesure = analyser_assertions(
            'def test_x():\n'
            '    assert a, message(en="Create it", fr="Crée-le")\n'
        )
        assert (mesure.total, mesure.avec_message, mesure.bilingues) == (1, 1, 1)
        assert mesure.monolingues == 0

    def test_un_appel_a_une_seule_langue_n_est_pas_bilingue(self) -> None:
        """Le cas qu'on cherche : la traduction commencée et laissée en route."""
        mesure = analyser_assertions('def test_x():\n    assert a, message(en="Only")\n')
        assert mesure.bilingues == 0
        assert mesure.monolingues == 1

    def test_le_helper_peut_etre_qualifie(self) -> None:
        """`helpers.message(...)` autant que `message(...)` : la forme compte,
        pas l'endroit où le catalogue la définit."""
        mesure = analyser_assertions(
            'def test_x():\n    assert a, helpers.message(en="E", fr="F")\n'
        )
        assert mesure.bilingues == 1

    def test_une_chaine_est_un_message_monolingue(self) -> None:
        mesure = analyser_assertions('def test_x():\n    assert a, "Crée-le"\n')
        assert (mesure.avec_message, mesure.bilingues, mesure.monolingues) == (1, 0, 1)

    def test_un_message_sur_la_ligne_suivante_est_vu(self) -> None:
        """Ce que la regex d'avant ne voyait pas : elle exigeait la même ligne,
        et notait donc « sans message » un lab qui en avait."""
        mesure = analyser_assertions(
            'def test_x():\n'
            '    assert a, (\n'
            '        "Crée-le, par exemple : touch chose"\n'
            '    )\n'
        )
        assert mesure.avec_message == 1

    def test_un_lab_melange_est_signale(self, tmp_path: Path) -> None:
        tests = (
            'def test_x():\n'
            '    assert a, message(en="E", fr="F")\n'
            '    assert b, "Seulement du français"\n'
        )
        constats, _mesure = examiner_lab(_poser_lab(tmp_path, tests=tests))
        constat = next(c for c in constats if c.cle == "audit_messages_melanges")
        assert constat.niveau == ATTENTION
        assert constat.params == {"bilingues": 1, "total": 2}

    def test_un_lab_entierement_monolingue_n_est_pas_signale_par_lab(
        self, tmp_path: Path
    ) -> None:
        """Sinon un catalogue qui n'a pas commencé sa traduction prend cent
        lignes rouges d'un coup, et un mur ne se lit plus. Le chiffre du
        catalogue, lui, le dit."""
        constats, mesure = examiner_lab(_poser_lab(tmp_path))
        assert [c.cle for c in constats] == []
        assert mesure.bilingues == 0
        assert mesure.monolingues == 2

    def test_le_rapport_cumule_le_catalogue(self, tmp_path: Path) -> None:
        """La mesure que le formateur suit d'une version à l'autre."""
        a = _poser_lab(tmp_path / "a")
        b = _poser_lab(
            tmp_path / "b",
            tests='def test_y():\n    assert c, message(en="E", fr="F")\n',
        )
        rapport = examiner([a, b])
        assert rapport.assertions.total == 3
        assert rapport.assertions.bilingues == 1
        assert rapport.assertions.monolingues == 2
        assert rapport.assertions.sans_message == 0


class TestUnFichierDeTestsIllisible:
    def test_un_python_invalide_est_un_manque_et_pas_un_zero(
        self, tmp_path: Path
    ) -> None:
        """Une sonde qui n'a pas pu regarder ne conclut jamais au vert : ici,
        « aucun assert » serait faux, et `pytest` butera sur le même fichier."""
        constats, mesure = examiner_lab(
            _poser_lab(tmp_path, tests="def test_x(:\n    assert a\n")
        )
        assert mesure.illisible is True
        assert mesure.total == 0
        constat = next(c for c in constats if c.cle == "audit_tests_illisibles")
        assert constat.niveau == MANQUE
        assert constat.params["raison"], "la cause doit être nommée"

    def test_il_ne_se_confond_pas_avec_un_lab_sans_test(self, tmp_path: Path) -> None:
        """Le fichier est cassé AVANT tout `def`, donc rien ne se voit à la
        regex : sans le contrôle d'illisibilité d'abord, le lab serait déclaré
        « aucun test », ce qui envoie écrire des tests qui existent déjà."""
        constats, mesure = examiner_lab(_poser_lab(tmp_path, tests="assert a,\n"))

        cles = [c.cle for c in constats]
        assert "audit_tests_illisibles" in cles
        assert "audit_aucun_test" not in cles
        assert mesure.illisible is True


class TestLesEchecsExplicites:
    """`pytest.fail` dit la même chose à l'apprenant qu'un assert.

    Ne compter que les asserts était une mesure fausse, et fausse dans le sens
    le plus trompeur : elle annonçait `ansible`, `python` et `devsecops`
    « entièrement bilingues » alors qu'ils portaient encore vingt-cinq
    messages français, tous dans des `pytest.fail`. Mesuré le 2026-10-16 sur
    les six catalogues : 256 échecs explicites, dont 220 pour le seul
    catalogue terraform. Un contrôle qui ne regarde pas ne conclut jamais au
    vert, et celui-là concluait au vert sans regarder.
    """

    def test_un_echec_explicite_compte_comme_une_assertion(self) -> None:
        a = analyser_assertions(
            'import pytest\n'
            'def test_x():\n'
            '    pytest.fail("Aucun Deployment.")\n'
        )

        assert a.total == 1
        assert a.avec_message == 1
        assert a.bilingues == 0

    def test_un_echec_explicite_bilingue_est_compte_comme_tel(self) -> None:
        a = analyser_assertions(
            'import pytest\n'
            'def test_x():\n'
            '    pytest.fail(message(en="None", fr="Aucun"))\n'
        )

        assert (a.total, a.bilingues) == (1, 1)

    def test_la_forme_importee_directement_compte_aussi(self) -> None:
        """Un catalogue écrit `pytest.fail` ou `fail`, c'est le même geste."""
        a = analyser_assertions(
            'from pytest import fail\n'
            'def test_x():\n'
            '    fail("Aucun Deployment.")\n'
        )

        assert a.total == 1

    def test_le_mot_cle_reason_est_lu(self) -> None:
        a = analyser_assertions(
            'import pytest\n'
            'def test_x():\n'
            '    pytest.fail(reason=message(en="None", fr="Aucun"))\n'
        )

        assert (a.total, a.bilingues) == (1, 1)

    def test_un_echec_sans_message_est_muet_pas_absent(self) -> None:
        """La distinction qui porte tout le module : ni vert, ni ignoré."""
        a = analyser_assertions(
            'import pytest\n'
            'def test_x():\n'
            '    pytest.fail()\n'
        )

        assert a.total == 1
        assert a.avec_message == 0
        assert a.sans_message == 1

    def test_un_autre_appel_nomme_fail_ne_compte_pas(self) -> None:
        """Le détecteur ne doit pas gonfler le total avec n'importe quel appel."""
        a = analyser_assertions(
            'def test_x():\n'
            '    resultat = client.fail_over("db")\n'
            '    assert resultat\n'
        )

        assert a.total == 1


class TestLesMessagesIndirects:
    """Un message relayé par une variable n'est ni bilingue, ni monolingue.

    Sept labs kubernetes écrivent un helper qui reçoit le message en
    paramètre : l'apprenant lit bien sa langue, parce que les appelants
    passent un `message(en=…, fr=…)`, mais l'assertion ne voit qu'un nom. Les
    compter comme monolingues laissait sept lignes rouges définitives dans un
    catalogue achevé, et un contrôle qu'on apprend à ignorer ne contrôle plus
    rien. La troisième catégorie est la même réponse que `unknown` dans
    `doctor` : trois issues, pas deux.
    """

    def test_un_message_relaye_par_une_variable_est_indirect(self) -> None:
        a = analyser_assertions(
            'def test_x(absent):\n'
            '    assert resultat, absent\n'
        )

        assert a.avec_message == 1
        assert a.indirects == 1
        assert a.bilingues == 0
        # Et surtout : il ne reste rien à traduire ici.
        assert a.monolingues == 0

    def test_un_attribut_et_un_indice_comptent_aussi(self) -> None:
        a = analyser_assertions(
            'def test_x(ctx, messages):\n'
            '    assert a, ctx.message\n'
            '    assert b, messages[0]\n'
        )

        assert a.indirects == 2
        assert a.monolingues == 0

    def test_une_chaine_en_dur_reste_monolingue(self) -> None:
        """La frontière doit tenir : sinon elle devient une échappatoire.

        Affecter un texte français à une variable ne doit pas suffire à
        passer au vert ; c'est pourquoi seul un NOM est indirect, jamais une
        chaîne, une f-string ou une concaténation.
        """
        a = analyser_assertions(
            'def test_x(nom):\n'
            '    assert a, "Aucun Deployment."\n'
            '    assert b, f"Aucun Pod {nom}."\n'
            '    assert c, "Aucun " + nom\n'
        )

        assert a.indirects == 0
        assert a.monolingues == 3

    def test_un_lab_entierement_indirect_n_est_pas_signale_comme_melange(self) -> None:
        """Le constat de mélange porte sur une traduction arrêtée en chemin."""
        a = analyser_assertions(
            'def test_x(absent):\n'
            '    assert a, message(en="None", fr="Aucun")\n'
            '    assert b, absent\n'
        )

        assert (a.bilingues, a.indirects, a.monolingues) == (1, 1, 0)


class TestLeHelperDoitEtreJoignable:
    """Un message bilingue qui lève n'est pas un message traduit.

    Mesuré le 2026-10-16, et c'est la raison d'être de cette mesure : un
    catalogue affichait 93 messages bilingues sur 93, et ses 93 messages
    rendaient un `NameError`. Le nom `message` était parti dans un
    commentaire `noqa` au lieu de l'import, parce qu'un correcteur découpait la
    ligne sur les virgules. Trois autres catalogues portaient une variable
    locale du même nom, qui masque le helper pour toute la fonction.

    Les deux cas ont la même forme juste et le même comportement cassé. Le
    fichier s'importe, `pytest` le collecte, et l'apprenant est le premier à
    le découvrir : une trace Python à la place de son message, au moment où il
    est bloqué. Compter l'appel sans vérifier qu'il peut s'exécuter, c'est
    mesurer la forme.
    """

    def test_le_nom_absent_du_module_rend_l_appel_injoignable(self) -> None:
        a = analyser_assertions(
            'from conftest import lab_host  # noqa: E402, message\n'
            '\n'
            'def test_x(host):\n'
            '    assert host.exists, message(en="gone", fr="absent")\n'
        )

        # L'appel a bien la forme bilingue : c'est précisément le piège.
        assert a.bilingues == 1
        assert a.helper_injoignable == 1

    def test_une_variable_locale_du_meme_nom_masque_le_helper(self) -> None:
        a = analyser_assertions(
            'from conftest import message\n'
            '\n'
            'def test_y(banc):\n'
            '    admis, message = banc.admettre()\n'
            '    assert admis, message(en="no", fr="non")\n'
        )

        assert a.helper_injoignable == 1

    def test_un_appel_apres_l_affectation_leve_aussi(self) -> None:
        """Le cas que `ruff` ne voit pas, et qui a survécu à son contrôle.

        `F823` ne se déclenche que sur une lecture AVANT l'affectation. Quand
        l'appel vient après, ruff voit un appel légitime sur une variable, et
        Python lève `'str' object is not callable` à l'exécution. Quatre
        assertions d'un lab kubernetes étaient dans ce cas.
        """
        a = analyser_assertions(
            'from conftest import message\n'
            '\n'
            'def test_z(host):\n'
            '    rc, message = host.run("x")\n'
            '    assert rc == 0, message(en="failed", fr="échoué")\n'
        )

        assert a.helper_injoignable == 1

    def test_un_parametre_du_meme_nom_masque_aussi(self) -> None:
        a = analyser_assertions(
            'from conftest import message\n'
            '\n'
            'def _verifier(host, message):\n'
            '    assert host.exists, message(en="gone", fr="absent")\n'
        )

        assert a.helper_injoignable == 1

    def test_un_fichier_sain_ne_compte_aucun_injoignable(self) -> None:
        a = analyser_assertions(
            'from conftest import lab_host, message\n'
            '\n'
            'def test_ok(host):\n'
            '    sortie = host.run("x").stdout\n'
            '    assert sortie, message(en="empty", fr="vide")\n'
        )

        assert a.bilingues == 1
        assert a.helper_injoignable == 0

    def test_une_variable_locale_dans_une_AUTRE_fonction_ne_compte_pas(self) -> None:
        """La portée se juge par fonction, pas par fichier.

        Sans cela, un seul `message = …` quelque part peindrait en rouge tout
        le fichier, et le contrôle deviendrait un mur qu'on apprend à ignorer.
        """
        a = analyser_assertions(
            'from conftest import message\n'
            '\n'
            'def _journal(res):\n'
            '    message = res.stdout\n'
            '    return message.lower()\n'
            '\n'
            'def test_ok(host):\n'
            '    assert host.exists, message(en="gone", fr="absent")\n'
        )

        assert a.helper_injoignable == 0

    def test_le_helper_defini_dans_le_fichier_compte_comme_disponible(self) -> None:
        """Un lab `shell` sans conftest peut porter son propre helper."""
        a = analyser_assertions(
            'def message(en: str, fr: str) -> str:\n'
            '    return en\n'
            '\n'
            'def test_ok():\n'
            '    assert True, message(en="gone", fr="absent")\n'
        )

        assert a.helper_injoignable == 0
