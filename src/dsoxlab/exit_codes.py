"""Les codes de sortie de la CLI, en un seul endroit.

Un code de sortie est le contrat le plus dur que cet outil expose : il n'a ni
schéma, ni version, ni message. Un document JSON peut gagner un champ, une
phrase traduite peut changer de mot ; un code, une fois qu'un script le lit, ne
peut plus bouger sans casser cet appelant en silence.

Ils étaient pourtant dispersés — ``locking.py`` portait le 7, ``inventory.py``
le 8, ``doctor.py`` les 9 et 10, ``_socle.py`` un 127 écrit en clair, et les
codes 1 à 6 n'existaient nulle part ailleurs qu'aux points d'appel. Quatre ont
été ajoutés dans la même journée, chacun dans le module qui en avait besoin :
rien n'empêchait d'attribuer deux fois la même valeur, et aucun test ne
comparait les modules entre eux (issue #197).

Cet énuméré les rassemble. Les constantes d'origine restent, en alias, parce
qu'elles sont importées ailleurs et que rien n'oblige à casser un import pour
ranger une valeur.

**Les deux invariants, tenus par ``tests/test_codes_de_sortie.py``** :

- aucune valeur en double — un doublon dans un ``IntEnum`` ne lève pas, il crée
  un alias silencieux, et deux causes distinctes se diraient alors du même code ;
- chaque code figure dans ``docs/exit-codes.md`` **et** dans sa version
  française — un code non documenté est un contrat que personne ne peut lire.

Les valeurs 1 et 2 recouvrent beaucoup de causes, et c'est assumé : elles
distinguent « la commande a répondu, et la réponse est non » de « la commande
n'a pas pu s'exécuter ». Les suivantes sont des causes précises, parce qu'un
script doit pouvoir réagir différemment à chacune — réessayer sur le verrou,
nettoyer sur les orphelins, remesurer sur l'indéterminé.
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Tous les codes que la CLI peut rendre, avec ce que chacun veut dire."""

    #: La commande a fait son travail, et la réponse est non : un identifiant de
    #: lab inconnu, un test rouge, un hôte qui ne répond pas, un contexte actif
    #: absent. C'est le seul code qu'un humain rencontre en usage normal.
    ECHEC = 1

    #: La commande n'a pas pu s'exécuter : l'état du poste ou le contrat s'y
    #: oppose. Infrastructure non provisionnée, provider non packagé, fixture
    #: déclarée mais absente du disque, point de reprise impossible alors que le
    #: lab l'exige, fichier attendu introuvable. Distinct de ``ECHEC`` parce que
    #: le geste diffère : ici il y a quelque chose à préparer, pas à corriger
    #: dans son travail.
    IMPOSSIBLE = 2

    #: Terraform n'est pas installé, donc ``provision`` et ``destroy`` n'ont
    #: aucun moyen d'agir. Séparé de ``IMPOSSIBLE`` parce que la remédiation est
    #: une installation, et qu'un pipeline peut l'automatiser.
    TERRAFORM_ABSENT = 3

    #: Terraform a répondu, et il a échoué. Le message porte sa sortie, et
    #: ``explique_echec_provision`` y reconnaît les causes connues.
    TERRAFORM_ECHOUE = 4

    #: Un ``provision`` a laissé des domaines orphelins — définis sur
    #: l'hyperviseur, absents du state — ou en a trouvé avant de commencer. Le
    #: message les nomme avec la commande qui les retire.
    ORPHELINS = 5

    #: Un ``destroy`` n'a pas pu retirer ces orphelins. Il sortait en 0 en
    #: laissant les machines debout, ce qui est le contraire de sa promesse.
    ORPHELINS_NON_RETIRES = 6

    #: Une autre commande dsoxlab tient déjà le verrou de ce dépôt. C'est le
    #: seul code sur lequel un script a raison de **réessayer** : la cause est
    #: temporaire par nature, et le message nomme le processus qui le détient.
    VERROU = 7

    #: Un ``provision`` a rendu la main sans que tous les hôtes ciblés
    #: répondent. Avant, il annonçait « ✔ N hôtes provisionnés » et sortait en
    #: 0 : l'échec était invisible à tout script, et le ``run`` suivant
    #: échouait en « unreachable » sans lien visible avec sa cause.
    HOTES_INJOIGNABLES = 8

    #: ``doctor --strict`` : un contrôle **requis** a échoué, c'est établi.
    DOCTOR_REQUIS_KO = 9

    #: ``doctor --strict`` : un contrôle requis n'a **pas pu** être mesuré. Ce
    #: n'est pas un échec, et ce n'est surtout pas un succès : un appelant
    #: automatisé ne peut rien conclure d'une sonde qui n'a pas regardé. Le
    #: code se distingue du précédent parce que les gestes diffèrent — réparer,
    #: ou refaire la mesure. Quand les deux coexistent, 9 l'emporte : une
    #: certitude est plus forte qu'une ignorance.
    DOCTOR_INDETERMINE = 10

    #: Un exécutable attendu est introuvable dans le ``PATH``. 127 est le code
    #: que le shell rend lui-même dans ce cas : l'outil dit donc la même chose
    #: que son environnement, ce qu'un script sait déjà interpréter.
    EXECUTABLE_INTROUVABLE = 127

    #: ``128 + SIGINT``. Le shell rend déjà ce code quand il tue un processus au
    #: Ctrl-C, et le message donne le geste de reprise.
    INTERROMPU = 130
