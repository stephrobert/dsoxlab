"""Traduire les événements d'un outil externe en avancement, sans rien afficher.

Ce que ce module corrige
========================

``cli/_barres.py`` mêlait trois choses dans une seule fonction par outil : la
**lecture** d'un événement brut d'ansible-runner ou de ``terraform -json``,
l'**état** de la progression, et son **rendu** Rich. L'état vivait dans un
``dict`` capturé par fermeture, que le callback modifiait au passage.

Mesuré le 2026-10-16, et c'est ce qui a motivé l'extraction :

=====================================  =========  =========  ==========
fonction                               ruff C901  cognitive  profondeur
=====================================  =========  =========  ==========
``_run_ansible_with_progress``                 1         54           7
``_run_terraform_with_progress``              16         77           8
=====================================  =========  =========  ==========

Une cyclomatique de **1** pour 91 lignes : pour ruff, cette fonction était
triviale. Le module était en réalité le plus difficile du dépôt, et le moins
couvert (**19 %**), parce qu'on ne teste pas une fermeture sans monter un
terminal.

Ici, un suivi est un objet : on lui donne des événements, il rend des
:class:`Avancement`. Cela se teste avec une liste, sans terminal, et cela sert
aussi bien une barre Rich qu'un widget d'une autre interface.

Ce que ce module ne fait pas
============================

**Aucun balisage.** Une :class:`Ligne` porte une *marque* (``ok``, ``echec``…)
et un texte ; c'est l'appelant qui décide qu'un ``ok`` s'écrit en vert. Sans
cette séparation, un test devrait comparer des chaînes ``[green]✔[/green]``, et
l'on mesurerait la mise en forme de Rich plutôt que la lecture des événements.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..i18n import _
from ..interrupt import EVENT_INTERRUPT

#: Marques possibles d'une ligne. Ce sont des **sens**, pas des couleurs.
OK = "ok"
CHANGE = "change"
IGNORE = "ignore"
ECHEC = "echec"
DETAIL = "detail"
AVIS = "avis"


@dataclass(frozen=True)
class Ligne:
    """Une ligne à écrire au-dessus de la barre, et ce qu'elle signifie."""

    marque: str
    texte: str


@dataclass(frozen=True)
class Avancement:
    """Ce qu'un événement change dans une barre de progression.

    Les champs à ``None`` ne changent rien : un événement qui ne fait
    qu'imprimer une ligne ne touche ni le total ni le compteur.
    """

    total: int | None = None
    fait: int | None = None
    description: str | None = None
    lignes: tuple[Ligne, ...] = ()


def _avis_interruption(evenement: dict[str, object]) -> Avancement:
    """Le Ctrl-C, dit une fois doucement, la seconde fois fermement."""
    premier = evenement.get("count", 1) == 1
    cle = "interrupt_notice_first" if premier else "interrupt_notice_second"
    return Avancement(lignes=(Ligne(AVIS, _(cle)),))


@dataclass
class SuiviAnsible:
    """Les événements d'ansible-runner, traduits en avancement.

    Une tâche Ansible produit un événement par hôte : le compteur suit donc
    les couples tâche-hôte, et non les tâches. C'est ce que l'apprenant voit
    défiler, et c'est ce que le total de la barre doit mesurer.
    """

    playbook: str
    faits: int = 0
    tache_courante: str = ""

    def __call__(self, evenement: dict[str, object]) -> Avancement | None:
        type_ = evenement.get("event")
        if type_ == EVENT_INTERRUPT:
            return _avis_interruption(evenement)
        donnees = evenement.get("event_data") or {}
        if not isinstance(donnees, dict):
            return None

        if type_ == "playbook_on_task_start":
            nom = str(donnees.get("name") or donnees.get("task") or "")
            self.tache_courante = nom
            return Avancement(description=_("progress_ansible_task", task=nom))

        if type_ in ("runner_on_ok", "runner_on_skipped"):
            return self._tache_passee(type_, donnees)
        if type_ == "runner_on_failed":
            return self._tache_en_echec(donnees)
        if type_ == "runner_on_unreachable":
            hote = str(donnees.get("host", "?"))
            message = self._message(donnees) or "host unreachable"
            return Avancement(
                lignes=(Ligne(ECHEC, f"{hote}: UNREACHABLE: {message}"),)
            )
        return None

    def _tache_passee(self, type_: str, donnees: dict[str, object]) -> Avancement:
        hote = str(donnees.get("host", "?"))
        tache = str(donnees.get("task") or self.tache_courante)
        self.faits += 1
        if type_ == "runner_on_skipped":
            return Avancement(
                fait=self.faits, lignes=(Ligne(IGNORE, f"{hote}: {tache} (skipped)"),)
            )
        resultat = donnees.get("res")
        change = bool(isinstance(resultat, dict) and resultat.get("changed"))
        marque = CHANGE if change else OK
        etiquette = "changed" if change else "ok"
        return Avancement(
            fait=self.faits,
            lignes=(Ligne(marque, f"{hote}: {tache} ({etiquette})"),),
        )

    def _tache_en_echec(self, donnees: dict[str, object]) -> Avancement:
        """Un échec n'avance pas le compteur : la tâche n'est pas passée.

        Et son message est rendu sur une ligne à part : c'est ansible qui dit
        pourquoi, et c'est la seule information utile de l'écran.
        """
        hote = str(donnees.get("host", "?"))
        tache = str(donnees.get("task") or self.tache_courante)
        lignes = [Ligne(ECHEC, f"{hote}: {tache}")]
        message = self._message(donnees)
        if message:
            lignes.append(Ligne(DETAIL, message))
        return Avancement(lignes=tuple(lignes))

    @staticmethod
    def _message(donnees: dict[str, object]) -> str:
        resultat = donnees.get("res")
        if isinstance(resultat, dict):
            return str(resultat.get("msg") or "")
        return ""

    def fin(self) -> Avancement:
        return Avancement(
            description=_("progress_playbook_done", playbook=self.playbook)
        )


@dataclass
class SuiviTerraformInit:
    """``terraform init -json`` : un téléchargement de provider, pas un compte.

    Seules trois phrases de Terraform disent qu'il se passe quelque chose
    (« Finding », « Installing », « Reusing ») ; le reste du flux est du
    journal. Les reconnaître est la seule façon d'avoir une description qui
    bouge, et c'est pourquoi ces mots sont ici et non traduits : ils viennent
    de Terraform.
    """

    _PHRASES_UTILES = ("Installing", "Finding", "Reusing")

    def __call__(self, evenement: dict[str, object]) -> Avancement | None:
        if evenement.get("type") not in ("log", "diagnostic"):
            return None
        message = str(evenement.get("@message", "")).strip()
        if evenement.get("@level") == "error":
            return Avancement(lignes=(Ligne(ECHEC, message),))
        if any(mot in message for mot in self._PHRASES_UTILES):
            return Avancement(description=message)
        return None

    def fin(self) -> Avancement:
        return Avancement(description=_("progress_tf_init_done"))


@dataclass
class SuiviTerraform:
    """``terraform apply``/``destroy`` : un compte de ressources, et qui traîne.

    ``operation`` vaut ``provision`` ou ``destroy``, et décide de l'action
    comptée : Terraform annonce ses changements prévus avec une action
    (``create``, ``delete``…), et compter les deux donnerait un total faux sur
    un plan qui remplace une ressource.
    """

    operation: str
    total: int = 0
    faits: int = 0
    #: Ressources dont l'application a commencé sans finir, et depuis combien de
    #: secondes. C'est ce qui permet de dire « ce qui prend du temps » plutôt que
    #: de laisser une barre figée sans explication.
    en_cours: dict[str, int] = field(default_factory=dict)

    @property
    def action_comptee(self) -> str:
        return "create" if self.operation == "provision" else "delete"

    @property
    def libelle_action(self) -> str:
        return "Creating" if self.operation == "provision" else "Destroying"

    def __call__(self, evenement: dict[str, object]) -> Avancement | None:
        type_ = evenement.get("type")
        if type_ == EVENT_INTERRUPT:
            return _avis_interruption(evenement)
        if type_ == "planned_change":
            return self._changement_prevu(evenement)
        if type_ in ("apply_start", "apply_progress", "apply_complete", "apply_errored"):
            return self._etape(type_, evenement)
        if type_ == "diagnostic" and evenement.get("@level") == "error":
            diagnostic = evenement.get("diagnostic")
            resume = (
                str(diagnostic.get("summary", "")) if isinstance(diagnostic, dict) else ""
            )
            return Avancement(lignes=(Ligne(ECHEC, f"Error: {resume}"),))
        return None

    def _changement_prevu(self, evenement: dict[str, object]) -> Avancement | None:
        changement = evenement.get("change")
        action = changement.get("action") if isinstance(changement, dict) else None
        if action != self.action_comptee:
            return None
        self.total += 1
        return Avancement(total=self.total)

    def _etape(self, type_: str, evenement: dict[str, object]) -> Avancement | None:
        adresse, secondes = _ressource(evenement)
        if type_ == "apply_start":
            self.en_cours[adresse] = 0
            return Avancement(description=self.description())
        if type_ == "apply_progress":
            if adresse not in self.en_cours:
                return None
            self.en_cours[adresse] = int(secondes)
            return Avancement(description=self.description())
        if type_ == "apply_complete":
            self.en_cours.pop(adresse, None)
            self.faits += 1
            return Avancement(
                fait=self.faits,
                description=self.description(),
                lignes=(Ligne(OK, f"{nom_court(adresse)} ({secondes:.0f}s)"),),
            )
        self.en_cours.pop(adresse, None)  # apply_errored
        return Avancement(
            description=self.description(), lignes=(Ligne(ECHEC, nom_court(adresse)),)
        )

    def description(self, *, combien: int = 2) -> str:
        """Ce qui est en cours, les plus lentes d'abord.

        Deux ressources au plus, et le compte des autres : une description qui
        liste douze adresses ne se lit plus, et une barre qui n'annonce rien
        pendant trois minutes fait croire à un blocage.
        """
        if not self.en_cours:
            return f"{self.libelle_action}…"
        plus_lentes = sorted(self.en_cours.items(), key=lambda kv: -kv[1])
        tete = plus_lentes[:combien]
        reste = len(plus_lentes) - len(tete)
        parts = ", ".join(f"{nom_court(a)} ({s}s)" for a, s in tete)
        suffixe = f" +{reste}" if reste > 0 else ""
        return f"{self.libelle_action} {parts}{suffixe}"

    def fin(self) -> Avancement:
        if self.total > 0:
            return Avancement(
                description=_("progress_action_done", action=self.libelle_action),
                fait=self.total,
            )
        return Avancement(description=_("progress_nothing_to_do"), total=1, fait=1)


def nom_court(adresse: str) -> str:
    """``outscale_security_group_rule.bastion_ssh_in`` devient ``bastion_ssh_in``.

    Le type de la ressource est le même pour toutes celles d'un plan : l'écrire
    seize fois dans une barre de progression n'ajoute rien et prend la largeur
    du terminal.
    """
    return adresse.split(".", 1)[-1] if "." in adresse else adresse


def _ressource(evenement: dict[str, object]) -> tuple[str, float]:
    """L'adresse de la ressource d'un événement ``apply_*``, et son temps écoulé."""
    hook = evenement.get("hook")
    if not isinstance(hook, dict):
        return "?", 0.0
    ressource = hook.get("resource")
    adresse = (
        str(ressource.get("addr", "?")) if isinstance(ressource, dict) else "?"
    )
    try:
        secondes = float(hook.get("elapsed_seconds", 0) or 0)
    except (TypeError, ValueError):
        secondes = 0.0
    return adresse, secondes
