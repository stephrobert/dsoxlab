"""Ce qu'un formateur doit savoir avant de confier un catalogue à quelqu'un.

``validate-structure`` répond déjà à « ce catalogue respecte-t-il le contrat ? ».
Il ne répond pas à « un apprenant peut-il réaliser ce lab avec ce qu'on lui
donne ? », et c'est une autre question. Elle s'est posée en lisant des labs à la
place d'un apprenant, sur cinq catalogues, et ce qui en sort tient en trois
constats mesurés le 2026-10-16 :

- ``linux-dsoxlab-training`` et ``terraform-dsoxlab-training`` sont **bons** :
  chaque exigence de la mission a son test, et les messages d'assertion donnent
  le geste de réparation ;
- ``ansible-training`` compte des labs dont **aucun** assert ne porte de
  message (``ansible-vault`` : 0 sur 8, ``get-url`` : 1 sur 15). L'apprenant y
  voit quels tests échouent, et rien sur ce qu'il doit corriger ;
- **aucune** mission d'``ansible-training`` ne dit comment valider, alors que
  celles de ``linux`` finissent toutes par ``dsoxlab check <id>``.

Un quatrième constat, celui-là sur la grille elle-même : sa première version
cherchait la mission dans ``challenge/README.md`` et nulle part ailleurs. Elle
déclarait donc « aucune mission » sur les 64 labs de ``kubernetes``, qui
l'écrivent dans leur ``scenario.md``. Le contrat n'impose pas ce fichier, et
une règle qui encode la disposition d'un catalogue mesure ce catalogue.

Ce module mesure donc ce qui est **mécaniquement vérifiable** de cette
question, et rien de plus. Il ne juge pas la pertinence pédagogique d'un
exercice : aucun programme ne sait le faire, et prétendre le contraire
donnerait un feu vert trompeur. Pour cela, :func:`dossier_pour_relecture`
rassemble ce qu'il faut à une relecture humaine, ou à un modèle de langue.

Chaque constat porte un **niveau** et jamais un score global : un total
agrégerait des choses de nature différente, et ferait viser le chiffre.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from ..i18n import _
from ..models.lab import LabDefinition

#: Un assert sans message est un échec sans consigne. En dessous de cette part
#: d'asserts qui en portent un, le lab est signalé : l'apprenant verra quels
#: tests échouent sans savoir quoi corriger.
PART_MESSAGES_MINIMALE = 0.6

#: Le nom conventionnel du helper bilingue dans les tests d'un catalogue :
#: ``message(en="…", fr="…")``. Il est fourni par le ``conftest.py`` du
#: catalogue, **pas** importé de dsoxlab : un test de lab doit rester jouable
#: par un simple ``pytest``, sans l'outil, et c'est un invariant du contrat.
#: dsoxlab n'en mesure donc que la **forme**, jamais la provenance.
NOM_HELPER_BILINGUE = "message"

#: Les langues que tout texte affiché doit porter, dans l'outil comme dans les
#: catalogues. Un message d'assertion est du texte affiché : il échoue sous les
#: yeux de l'apprenant, dans sa langue.
LANGUES_ATTENDUES = frozenset({"en", "fr"})

#: Au-delà, le cours ne se lit plus d'un bloc. C'est le seuil à partir duquel le
#: découpage (`services.course_service`) devient indispensable, pas confortable.
LIGNES_COURS_MAX = 150

#: Niveaux de constat. « bloquant » n'existe pas : rien ici n'empêche de jouer
#: un lab, tout y rend l'apprentissage plus difficile.
MANQUE = "manque"
ATTENTION = "attention"

_DEF_TEST = re.compile(r"^\s*def (test_\w+)", re.MULTILINE)


@dataclass(frozen=True)
class Assertions:
    """Ce que les tests d'un lab disent à l'apprenant quand ils échouent.

    Les asserts sont comptés sur l'**arbre syntaxique**, pas à la regex. Une
    regex ne voyait pas un message écrit sur la ligne suivante, et surtout elle
    ne savait pas distinguer une chaîne d'un appel : or c'est exactement la
    distinction qui porte la parité des langues.
    """

    total: int = 0
    avec_message: int = 0
    bilingues: int = 0
    #: Les messages que l'assertion ne porte pas elle-même : elle relaie une
    #: variable, calculée ailleurs. Ni bilingues, ni monolingues.
    #:
    #: Le cas vient des catalogues eux-mêmes. Sept labs kubernetes écrivent
    #: un helper qui reçoit le message en paramètre :
    #:
    #:     def _json(host, args, absent):
    #:         assert res.rc == 0, absent
    #:
    #: Les appelants passent un `message(en=…, fr=…)`, donc l'apprenant lit
    #: bien sa langue ; l'assertion, elle, ne voit qu'un nom. Les compter
    #: comme monolingues laissait sept lignes rouges définitives dans un
    #: catalogue achevé, et un contrôle qu'on apprend à ignorer ne contrôle
    #: plus rien. Les compter comme bilingues serait pire : il suffirait
    #: d'affecter un texte français à une variable pour passer au vert.
    indirects: int = 0
    #: Les appels `message(en=…, fr=…)` qui ne peuvent pas s'exécuter : le
    #: nom n'est pas importé dans le module, ou une variable locale du même
    #: nom le masque dans la fonction qui l'appelle.
    #:
    #: Ce compte existe parce que la forme ne prouve rien. Mesuré le
    #: 2026-10-16 : un catalogue annonçait 93 messages bilingues sur 93, et
    #: ses 93 messages rendaient un `NameError`, le nom ayant atterri dans un
    #: commentaire au lieu de l'import. Trois autres catalogues portaient une
    #: variable locale `message` qui masquait le helper pour toute la
    #: fonction. Dans les deux cas le fichier s'importe, la collecte pytest
    #: passe, et l'apprenant est le premier à le découvrir.
    helper_injoignable: int = 0
    #: Le fichier n'est pas du Python valide. Rien n'a pu être compté, et
    #: `pytest` ne le chargera pas davantage : ce n'est pas « zéro assert ».
    illisible: bool = False
    raison: str = ""

    @property
    def sans_message(self) -> int:
        return self.total - self.avec_message

    @property
    def monolingues(self) -> int:
        """Ceux qu'il reste vraiment à traduire : l'indirect n'en est pas."""
        return self.avec_message - self.bilingues - self.indirects


def _message_indirect(noeud: ast.expr) -> bool:
    """Vrai si le message n'est qu'un nom : il est écrit ailleurs.

    Un attribut (``self.msg``) ou un indice (``messages[0]``) comptent aussi :
    dans les trois cas, le texte ne se lit pas ici, et c'est l'appelant qu'il
    faut regarder. La frontière est stricte : une chaîne, une f-string ou une
    concaténation portent bien un texte, et restent à juger.
    """
    return isinstance(noeud, ast.Name | ast.Attribute | ast.Subscript)


def _message_bilingue(noeud: ast.expr) -> bool:
    """Vrai si ce message porte les deux langues, par la forme conventionnelle.

    On reconnaît ``message(en=…, fr=…)`` et ``helpers.message(en=…, fr=…)``,
    sans rien exiger de l'endroit où le helper est défini. Un appel qui ne
    nomme qu'une langue n'est pas bilingue : c'est le cas qu'on cherche, celui
    du message traduit à moitié.
    """
    if not isinstance(noeud, ast.Call):
        return False
    cible = noeud.func
    nom = cible.attr if isinstance(cible, ast.Attribute) else getattr(cible, "id", "")
    if nom != NOM_HELPER_BILINGUE:
        return False
    return {kw.arg for kw in noeud.keywords if kw.arg} >= LANGUES_ATTENDUES


def _message_d_un_echec(noeud: ast.AST) -> tuple[bool, ast.expr | None]:
    """Le message que ce nœud fait lire à l'apprenant, s'il en fait lire un.

    Deux formes disent exactement la même chose à l'apprenant : l'assertion
    et l'échec explicite.

        assert condition, "..."
        pytest.fail("...")

    Ne compter que la première était une mesure fausse, et elle l'était dans
    le sens le plus trompeur : elle annonçait trois catalogues « entièrement
    bilingues » alors qu'ils portaient encore vingt-cinq messages français,
    tous dans des `pytest.fail`. Mesuré le 2026-10-16 sur les six catalogues :
    256 échecs explicites, dont 220 pour le seul catalogue terraform.

    Rend ``(False, None)`` quand le nœud ne fait rien lire, et sinon
    ``(True, <message>)``, le message valant ``None`` pour un échec muet. Le
    couple plutôt qu'une valeur à trois cas : ``None`` est un message absent,
    pas « ce n'est pas un échec », et confondre les deux est précisément
    l'erreur que ce module cherche à éviter ailleurs.
    """
    if isinstance(noeud, ast.Assert):
        return True, noeud.msg
    if not isinstance(noeud, ast.Call):
        return False, None
    appele = noeud.func
    # `pytest.fail(...)` comme `fail(...)` importé directement : c'est le même
    # geste, et un catalogue écrit l'un ou l'autre.
    nom = (
        appele.attr if isinstance(appele, ast.Attribute)
        else appele.id if isinstance(appele, ast.Name)
        else None
    )
    if nom != "fail":
        return False, None
    arguments = [kw.value for kw in noeud.keywords if kw.arg == "reason"]
    arguments += list(noeud.args)
    return True, (arguments[0] if arguments else None)


def _portee_locale(corps: list[ast.stmt]) -> Iterator[ast.AST]:
    """Les nœuds de cette portée, sans entrer dans une portée imbriquée.

    `ast.walk` ne sait pas s'arrêter à une frontière de portée : il descend
    dans le corps des fonctions imbriquées, dont les affectations
    n'appartiennent pas à l'appelant. On s'arrête donc au nœud de la fonction,
    dont seul le NOM se lie ici.
    """
    pile: list[ast.AST] = list(corps)
    while pile:
        noeud = pile.pop()
        yield noeud
        if isinstance(noeud, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        pile.extend(ast.iter_child_nodes(noeud))


def _noms_lies(noeud: ast.AST) -> set[str]:
    """Les noms que ce nœud attache dans la portée où il se trouve."""
    if isinstance(noeud, ast.FunctionDef | ast.AsyncFunctionDef):
        return {noeud.name}
    if isinstance(noeud, ast.Import | ast.ImportFrom):
        return {a.asname or a.name.split(".")[0] for a in noeud.names}
    cibles: list[ast.expr] = []
    if isinstance(noeud, ast.Assign):
        cibles = list(noeud.targets)
    elif isinstance(
        noeud,
        ast.AnnAssign | ast.AugAssign | ast.NamedExpr | ast.For | ast.AsyncFor,
    ):
        cibles = [noeud.target]
    elif isinstance(noeud, ast.withitem) and noeud.optional_vars is not None:
        cibles = [noeud.optional_vars]
    return {
        atome.id
        for cible in cibles
        for atome in ast.walk(cible)
        if isinstance(atome, ast.Name)
    }


def _lie_le_nom(corps: list[ast.stmt], nom: str) -> bool:
    """Vrai si cette portée attache `nom`, de quelque façon que ce soit."""
    return any(nom in _noms_lies(noeud) for noeud in _portee_locale(corps))


def _disponible_au_module(arbre: ast.Module, nom: str) -> bool:
    """Vrai si le module donne ce nom : import, définition ou affectation."""
    return any(nom in _noms_lies(noeud) for noeud in arbre.body)


def _compter_helpers_injoignables(arbre: ast.Module) -> int:
    """Les appels au helper qui lèveraient au lieu d'afficher le message.

    Deux causes, une seule conséquence. Le nom absent du module donne un
    `NameError` ; une variable locale du même nom donne un
    `UnboundLocalError` ou un appel sur une chaîne. Dans les trois cas,
    l'apprenant lit une trace Python à la place de son message.
    """
    au_module = _disponible_au_module(arbre, NOM_HELPER_BILINGUE)
    injoignables = 0

    def visiter(noeud: ast.AST, masque: bool) -> None:
        nonlocal injoignables
        if isinstance(noeud, ast.FunctionDef | ast.AsyncFunctionDef):
            masque = masque or _lie_le_nom(noeud.body, NOM_HELPER_BILINGUE) or any(
                argument.arg == NOM_HELPER_BILINGUE
                for argument in _tous_les_arguments(noeud.args)
            )
        for enfant in ast.iter_child_nodes(noeud):
            if (
                isinstance(enfant, ast.Call)
                and isinstance(enfant.func, ast.Name)
                and enfant.func.id == NOM_HELPER_BILINGUE
                and (masque or not au_module)
            ):
                injoignables += 1
            visiter(enfant, masque)

    visiter(arbre, masque=False)
    return injoignables


def _tous_les_arguments(args: ast.arguments) -> list[ast.arg]:
    """Tous les paramètres d'une signature, quelle que soit leur sorte."""
    nommes = args.posonlyargs + args.args + args.kwonlyargs
    return nommes + [a for a in (args.vararg, args.kwarg) if a is not None]

def analyser_assertions(source: str) -> Assertions:
    """Compte ce qu'un fichier de tests dit à l'apprenant quand il échoue."""
    try:
        arbre = ast.parse(source)
    except SyntaxError as exc:
        return Assertions(illisible=True, raison=f"{exc.msg} (ligne {exc.lineno})")

    total = avec = bilingues = indirects = 0
    for noeud in ast.walk(arbre):
        est_un_echec, message = _message_d_un_echec(noeud)
        if not est_un_echec:
            continue
        total += 1
        if message is None:
            continue
        avec += 1
        if _message_bilingue(message):
            bilingues += 1
        elif _message_indirect(message):
            indirects += 1
    return Assertions(
        total=total,
        avec_message=avec,
        bilingues=bilingues,
        indirects=indirects,
        helper_injoignable=_compter_helpers_injoignables(arbre),
    )


@dataclass(frozen=True)
class Constat:
    """Une chose à savoir sur un lab, et pourquoi elle compte."""

    lab_id: str
    cle: str
    niveau: str
    params: dict[str, object] = field(default_factory=dict)

    def phrase(self) -> str:
        return _(self.cle, **self.params)


@dataclass
class RapportPedagogique:
    """Les constats, et de quoi dire ce qui a été regardé."""

    labs_examines: int = 0
    constats: list[Constat] = field(default_factory=list)
    #: Le cumul sur tout le catalogue. Il n'y a pas de constat par lab pour la
    #: parité des langues, et c'est voulu : un catalogue qui n'a pas commencé sa
    #: traduction produirait une ligne rouge par lab, c'est-à-dire un mur qu'on
    #: apprend à ignorer. Le chiffre, lui, se suit d'une version à l'autre et se
    #: lit en CI. Le constat par lab ne se déclenche que sur un lab **mélangé**,
    #: le cas où l'alignement a été perdu en route.
    assertions: Assertions = field(default_factory=Assertions)

    @property
    def ok(self) -> bool:
        return not any(c.niveau == MANQUE for c in self.constats)

    def par_niveau(self, niveau: str) -> list[Constat]:
        return [c for c in self.constats if c.niveau == niveau]


def _mission(lab: LabDefinition, lang: str) -> str:
    """Ce qui dit à l'apprenant quel travail produire, où qu'il soit écrit.

    Deux dispositions coexistent dans les catalogues, et le contrat les permet
    toutes les deux : il exige `README.md`, `scenario.md` et les tests, **pas**
    `challenge/README.md`. `ansible` et `linux` écrivent la mission dans ce
    dernier ; `kubernetes` l'écrit dans son `scenario.md`, sous « What is
    expected of you », et ses labs sont parmi les mieux tenus du lot.

    La version d'avant ne regardait que `challenge/README.md` : elle déclarait
    donc « aucune mission » sur les 64 labs de `kubernetes`, c'est-à-dire
    soixante-quatre fois rien. Une règle qui encode la disposition d'un
    catalogue mesure ce catalogue, pas la qualité d'un lab.
    """
    for nom in (f"README.{lang}.md", "README.md"):
        chemin = lab.path / "challenge" / nom
        if chemin.is_file():
            return chemin.read_text(encoding="utf-8", errors="replace")
    return _cours(lab, lang)


def _tests(lab: LabDefinition) -> str:
    chemin = lab.path / "challenge" / "tests" / "test_functional.py"
    return chemin.read_text(encoding="utf-8", errors="replace") if chemin.is_file() else ""


def _cours(lab: LabDefinition, lang: str) -> str:
    morceaux: list[str] = []
    for nom in ("scenario.md", "README.md"):
        tige, suffixe = nom.rsplit(".", 1)
        for candidat in (f"{tige}.{lang}.{suffixe}", nom):
            chemin = lab.path / candidat
            if chemin.is_file():
                morceaux.append(chemin.read_text(encoding="utf-8", errors="replace"))
                break
    return "\n\n".join(morceaux)


def _constats_mission(lab_id: str, mission: str) -> list[Constat]:
    """Le silence total est signalé par `audit_cours_absent`, pas ici.

    Il n'existe aucun moyen mécanique de distinguer un document qui énonce un
    travail d'un document qui explique une notion : prétendre le contraire
    reviendrait à noter la rédaction d'un auteur sur un mot-clé. Ce qui se
    vérifie, c'est que le geste de validation est écrit quelque part.
    """
    if not mission.strip():
        return []
    if "dsoxlab check" not in mission:
        # Le geste qui valide n'est pas devinable : il porte l'identifiant du
        # lab, que l'apprenant n'a pas forcément sous les yeux.
        return [Constat(lab_id, "audit_mission_sans_validation", ATTENTION)]
    return []


def _constats_tests(lab_id: str, tests: str, mesure: Assertions) -> list[Constat]:
    """Ce que les tests ne diront pas à l'apprenant qui échoue."""
    if mesure.illisible:
        # Ni vert ni « zéro assert » : une sonde qui n'a pas pu regarder ne
        # conclut jamais. `pytest` butera sur le même fichier.
        return [Constat(lab_id, "audit_tests_illisibles", MANQUE, {"raison": mesure.raison})]
    if not _DEF_TEST.findall(tests):
        return [Constat(lab_id, "audit_aucun_test", MANQUE)]

    constats: list[Constat] = []
    if mesure.total and mesure.avec_message / mesure.total < PART_MESSAGES_MINIMALE:
        constats.append(
            Constat(
                lab_id,
                "audit_asserts_sans_message",
                MANQUE,
                {"sans": mesure.sans_message, "total": mesure.total},
            )
        )
    if mesure.bilingues and mesure.monolingues:
        # Un lab dont la traduction s'est arrêtée en chemin. C'est le même
        # contrôle que la parité des documents dans `validators/content.py`,
        # porté sur le seul texte qui ne peut pas vivre en deux fichiers.
        constats.append(
            Constat(
                lab_id,
                "audit_messages_melanges",
                ATTENTION,
                {"bilingues": mesure.bilingues, "total": mesure.avec_message},
            )
        )
    return constats


def examiner_lab(lab: LabDefinition, lang: str = "en") -> tuple[list[Constat], Assertions]:
    """Ce qui manque à CE lab pour être réalisable sans deviner.

    Rend aussi le décompte de ses assertions, pour que l'appelant cumule sur le
    catalogue sans relire les fichiers une seconde fois.

    L'ordre des contrôles est celui dans lequel un apprenant les rencontre : la
    mission d'abord, puisque c'est ce qu'il lit ; les messages d'assertion
    ensuite, puisque c'est ce qu'il lira en échouant.
    """
    tests = _tests(lab)
    cours = _cours(lab, lang)
    mesure = analyser_assertions(tests)

    constats = _constats_mission(lab.id, _mission(lab, lang))
    constats += _constats_tests(lab.id, tests, mesure)

    lignes = len(cours.splitlines())
    if not cours.strip():
        constats.append(Constat(lab.id, "audit_cours_absent", MANQUE))
    elif lignes > LIGNES_COURS_MAX:
        from .course_service import manifeste_automatique

        decoupe = manifeste_automatique(lab.path, lab.title, lang=lang)
        if decoupe is None:
            # Un pavé que même le découpage automatique ne sait pas ouvrir :
            # l'apprenant le reçoit d'un bloc, quoi qu'il fasse.
            constats.append(
                Constat(lab.id, "audit_cours_indivisible", ATTENTION, {"lignes": lignes})
            )

    if not (lab.path / "challenge" / "hints.yaml").is_file():
        constats.append(Constat(lab.id, "audit_aucun_indice", ATTENTION))

    return constats, mesure


def examiner(labs: list[LabDefinition], lang: str = "en") -> RapportPedagogique:
    """La même grille sur tout un catalogue, et le cumul de ses assertions."""
    rapport = RapportPedagogique(labs_examines=len(labs))
    total = avec = bilingues = indirects = 0
    for lab in labs:
        constats, mesure = examiner_lab(lab, lang)
        rapport.constats.extend(constats)
        total += mesure.total
        avec += mesure.avec_message
        bilingues += mesure.bilingues
        indirects += mesure.indirects
    rapport.assertions = Assertions(
        total=total, avec_message=avec, bilingues=bilingues, indirects=indirects
    )
    return rapport


def dossier_pour_relecture(labs: list[LabDefinition], lang: str = "en") -> str:
    """Le catalogue en un seul Markdown, pour une relecture humaine ou par un modèle.

    Pourquoi un export plutôt qu'un verdict
    ---------------------------------------

    « Cet exercice est-il pertinent ? », « ce cours prépare-t-il à cette
    mission ? », « ce lab apprend-il quelque chose ? » : aucune de ces questions
    n'est mécanisable, et ce module se garde d'y répondre. Mais elles sont
    répondables par quelqu'un qui lit, et ce qu'il faut lire est dispersé dans
    quatre fichiers par lab, sur parfois plus de cent labs.

    Ce dossier les rassemble dans l'ordre où un apprenant les rencontre, avec
    ce que les tests exigent en regard. Il tient dans une fenêtre de contexte,
    se relit à deux, et ne contient **que** ce que le catalogue déclare : aucun
    chemin absolu, aucune donnée de la machine.
    """
    lignes: list[str] = [
        f"# {_('audit_dossier_titre')}",
        "",
        _("audit_dossier_intro", count=len(labs)),
        "",
    ]
    for lab in labs:
        lignes += [
            "---",
            "",
            f"## {lab.id} : {lab.title}",
            "",
            f"- {_('audit_dossier_niveau')} : {lab.level}",
            f"- {_('audit_dossier_runtime')} : {lab.runtime.type.value}",
            f"- {_('audit_dossier_competences')} : {', '.join(lab.skills) or _('audit_dossier_vide')}",
            "",
            f"### {_('audit_dossier_cours')}",
            "",
            _cours(lab, lang).strip() or _("audit_dossier_vide"),
            "",
            f"### {_('audit_dossier_mission')}",
            "",
            _mission(lab, lang).strip() or _("audit_dossier_vide"),
            "",
            f"### {_('audit_dossier_tests')}",
            "",
            "```python",
            _tests(lab).strip() or "# " + _("audit_dossier_vide"),
            "```",
            "",
        ]
    return "\n".join(lignes)
