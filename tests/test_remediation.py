"""Ce que `doctor --fix` décide, éprouvé sans toucher la machine.

Ces décisions vivaient dans la commande, donc derrière un `CliRunner` et des
`monkeypatch` sur `subprocess`. Les cas qu'on ne pouvait pas écrire sont
justement ceux qui coûtent cher quand ils tombent mal : un terminal absent, un
`sudo` introuvable, une cascade dont un maillon rate.
"""

from __future__ import annotations

from dsoxlab.services.doctor import Check, DoctorReport, Fix, FixKind
from dsoxlab.services.remediation import (
    Application,
    appliquer,
    obstacle,
    planifier,
)


def _check(key: str, fix: Fix | None, *, ok: bool = False) -> Check:
    return Check(key=key, label=key, ok=ok, detail="", fix=fix)


def _fix(*, kind: FixKind = FixKind.AUTOMATIC, sudo: bool = False) -> Fix:
    commande = ("sudo", "apt", "install", "x") if sudo else ("apt", "install", "x")
    return Fix((commande,), kind=kind)


class TestLePlan:
    def test_un_manuel_et_un_automatique_sont_separes(self) -> None:
        report = DoctorReport(required=[
            _check("manuel", _fix(kind=FixKind.MANUAL)),
            _check("auto", _fix()),
        ])

        plan = planifier(report)

        assert [label for label, _ in plan.manuels] == ["manuel"]
        assert [label for label, _ in plan.executables] == ["auto"]

    def test_un_controle_vert_n_est_pas_a_reparer(self) -> None:
        report = DoctorReport(required=[_check("vert", _fix(), ok=True)])
        assert planifier(report).vide

    def test_un_controle_rouge_sans_correctif_est_ignore(self) -> None:
        """Il reste rouge et il se dit : simplement, `--fix` n'a rien à jouer."""
        report = DoctorReport(required=[_check("rouge", None)])
        assert planifier(report).vide

    def test_les_correctifs_informatifs_ne_comptent_pas(self) -> None:
        """`fixable()` ne regarde que le tableau des contrôles REQUIS : un
        composant que ce dépôt n'utilise pas ne se répare pas de force."""
        report = DoctorReport(required=[], optional=[_check("docker", _fix())])
        assert planifier(report).vide


class TestCeQuiEmpecheLaCascade:
    def test_sans_sudo_requis_la_voie_est_libre_meme_hors_terminal(self) -> None:
        """Un `--fix` sans sudo doit tourner en CI, où il n'y a pas de TTY."""
        plan = planifier(DoctorReport(required=[_check("auto", _fix())]))
        assert obstacle(plan, interactif=False) is None

    def test_sans_terminal_un_correctif_sudo_est_refuse_avant_de_commencer(
        self,
    ) -> None:
        """Échouer au milieu d'une cascade laisse la machine dans un état que
        personne n'a décrit : le refus vient avant le premier correctif."""
        plan = planifier(DoctorReport(required=[_check("auto", _fix(sudo=True))]))
        assert obstacle(plan, interactif=False) == "fix_needs_tty"

    def test_sans_le_binaire_sudo_la_cascade_est_refusee(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr("dsoxlab.services.remediation.shutil.which", lambda _: None)
        plan = planifier(DoctorReport(required=[_check("auto", _fix(sudo=True))]))

        assert obstacle(plan, interactif=True) == "fix_no_sudo"

    def test_tout_en_place_ne_renvoie_aucun_obstacle(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "dsoxlab.services.remediation.shutil.which", lambda _: "/usr/bin/sudo"
        )
        plan = planifier(DoctorReport(required=[_check("auto", _fix(sudo=True))]))

        assert obstacle(plan, interactif=True) is None

    def test_le_compte_de_correctifs_sudo_est_celui_annonce(self) -> None:
        """Il est affiché avant la pré-authentification : il doit être juste."""
        report = DoctorReport(required=[
            _check("a", _fix(sudo=True)),
            _check("b", _fix(sudo=False)),
            _check("c", _fix(sudo=True)),
        ])
        assert planifier(report).correctifs_sudo == 2


class TestLaCascade:
    def test_un_echec_n_arrete_pas_les_suivants(self) -> None:
        """`--fix` répare des choses indépendantes : lever sur la première qui
        rate abandonnerait les autres sans le dire."""
        joues: list[str] = []

        def executer(fix: Fix) -> int:
            joues.append(fix.commands[0][-1])
            return 1 if fix.commands[0][-1] == "b" else 0

        plan = planifier(DoctorReport(required=[
            _check("a", Fix((("cmd", "a"),))),
            _check("b", Fix((("cmd", "b"),))),
            _check("c", Fix((("cmd", "c"),))),
        ]))
        resultats = appliquer(plan.executables, executer)

        assert joues == ["a", "b", "c"]
        assert [r.ok for r in resultats] == [True, False, True]

    def test_les_deux_rappels_encadrent_chaque_correctif(self) -> None:
        """La commande est nommée AVANT de partir, sinon sa sortie arrive sur
        le terminal sans que rien ne dise à qui elle appartient."""
        trace: list[str] = []
        plan = planifier(DoctorReport(required=[_check("a", Fix((("cmd", "a"),)))]))

        appliquer(
            plan.executables,
            lambda _fix: 0,
            sur_debut=lambda label, _fix: trace.append(f"debut:{label}"),
            sur_resultat=lambda app: trace.append(f"fin:{app.label}"),
        )

        assert trace == ["debut:a", "fin:a"]


class TestCeQuOnDitApres:
    def test_un_succes_immediat_n_annonce_rien_de_differe(self) -> None:
        assert Application("x", 0, FixKind.AUTOMATIC).avis_differe is None

    def test_une_reconnexion_requise_est_annoncee(self) -> None:
        """Sans ce message, le prochain `doctor` remontre la même ligne rouge
        et l'utilisateur conclut, à tort, que le correctif a échoué."""
        assert Application("x", 0, FixKind.NEEDS_RELOGIN).avis_differe == (
            "fix_needs_relogin"
        )

    def test_un_redemarrage_requis_est_annonce(self) -> None:
        assert Application("x", 0, FixKind.NEEDS_REBOOT).avis_differe == (
            "fix_needs_reboot"
        )

    def test_un_echec_n_annonce_aucun_effet_differe(self) -> None:
        """Promettre « effectif après reconnexion » sur un correctif qui a raté
        enverrait l'utilisateur redémarrer pour rien."""
        assert Application("x", 1, FixKind.NEEDS_REBOOT).avis_differe is None
