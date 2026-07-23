"""Contrôles de contenu : liens internes, doc_url, solutions chiffrées.

`validate_structure` répond à « les fichiers du contrat sont-ils là ? ». Ces
contrôles-ci répondent à « ce qu'ils contiennent tient-il debout ? ». Trois
dérives silencieuses, qu'aucun test fonctionnel n'attrape parce qu'elles ne
cassent pas l'exécution d'un lab, seulement l'expérience de l'apprenant :

- **un lien interne mort** ne casse que la navigation. Le dépôt Ansible en
  comptait 150 le jour où le contrôle y a été écrit ;
- **un `doc_url` mort** envoie l'apprenant vers une page disparue, alors que le
  contrat exige ce champ précisément pour le renvoyer au guide ;
- **une solution en clair** est irrattrapable : git la garde pour toujours, et
  le lab est gâché pour quiconque lit le dépôt.

Ces trois contrôles étaient écrits à la main dans chaque dépôt de labs. Ils
vivent ici pour que tout dépôt en bénéficie sans les recopier.

Rien ici n'est spécifique à un domaine : on ne lit que le contrat déclaratif et
l'arborescence.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from ..models.lab import LabDefinition

#: `[libellé](cible)` où la cible est relative. Les URL absolues relèvent du
#: contrôle des doc_url, pas de celui-ci.
_LIEN_RELATIF = re.compile(r"\[[^\]]*\]\((\.\.?/[^)]+)\)")

#: En-tête que `ansible-vault` écrit en première ligne d'un fichier chiffré.
#: Le vérifier vaut mieux que faire confiance à l'auteur.
_ENTETE_VAULT = "$ANSIBLE_VAULT"

#: Extensions considérées comme du contenu de solution. Une image ou un
#: README dans `solution/` n'a pas à être chiffré.
_EXTENSIONS_SOLUTION = {".yaml", ".yml", ".sh", ".py", ".bash", ".txt"}

_TIMEOUT_HTTP = 10.0

#: Beaucoup de sites refusent une requête sans User-Agent identifiable et
#: rendent 403. Sans cet en-tête, le contrôle déclarait morts des guides qui
#: répondent parfaitement dans un navigateur.
_ENTETES = {"User-Agent": "dsoxlab-doc-url-check/1.0"}


@dataclass
class ContentIssue:
    path: Path
    message: str


@dataclass
class ContentReport:
    lab_id: str
    issues: list[ContentIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.issues) == 0


def _liens_casses(fichier: Path) -> list[str]:
    """Cibles relatives introuvables depuis ce fichier.

    L'ancre (`#section`) est retirée avant le test : elle est résolue par le
    lecteur Markdown, pas par le système de fichiers.
    """
    try:
        contenu = fichier.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    casses = []
    for cible in _LIEN_RELATIF.findall(contenu):
        if not (fichier.parent / cible.split("#")[0]).resolve().exists():
            casses.append(cible)
    return casses


def validate_internal_links(lab: LabDefinition) -> ContentReport:
    """Tout lien relatif d'un Markdown du lab doit pointer sur un fichier."""
    report = ContentReport(lab_id=lab.id)
    for fichier in sorted(lab.path.rglob("*.md")):
        casses = _liens_casses(fichier)
        if casses:
            report.issues.append(ContentIssue(
                path=fichier,
                message=(
                    f"{len(casses)} lien(s) relatif(s) mort(s) : "
                    + ", ".join(casses)
                ),
            ))
    return report


def validate_solutions_encrypted(
    lab: LabDefinition, solutions_root: Path
) -> ContentReport:
    """Aucun fichier de solution ne doit être lisible en clair.

    Le contrôle ne s'applique qu'aux dépôts qui tiennent un répertoire de
    solutions : un dépôt sans `solution/` n'est pas en faute, il a simplement
    fait un autre choix.
    """
    report = ContentReport(lab_id=lab.id)
    if not solutions_root.is_dir():
        return report
    for fichier in sorted(solutions_root.rglob("*")):
        if not fichier.is_file() or fichier.suffix not in _EXTENSIONS_SOLUTION:
            continue
        try:
            with fichier.open("r", encoding="utf-8", errors="ignore") as flux:
                premiere = flux.readline()
        except OSError as exc:
            report.issues.append(ContentIssue(fichier, f"illisible : {exc}"))
            continue
        if not premiere.startswith(_ENTETE_VAULT):
            report.issues.append(ContentIssue(
                path=fichier,
                message=(
                    "solution en clair : chiffre-la avec "
                    "« ansible-vault encrypt », sinon git la garde pour "
                    "toujours et le lab est gâché"
                ),
            ))
    return report


def check_doc_url(lab: LabDefinition, *, timeout: float = _TIMEOUT_HTTP) -> str | None:
    """Vérifie que le `doc_url` du lab répond. Rend le motif d'échec, ou None.

    Séparé des autres contrôles parce qu'il sort sur le réseau : il n'a rien à
    faire dans une validation par défaut, qui doit rester rapide et jouable
    hors ligne.
    """
    url = lab.doc_url
    if not url:
        return None
    schema = urlparse(url).scheme
    if schema not in ("http", "https"):
        return f"schéma inattendu : {schema or '(aucun)'}"
    requete = urllib.request.Request(  # noqa: S310 - schéma vérifié
        url, method="HEAD", headers=_ENTETES
    )
    try:
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:  # noqa: S310
            code = reponse.status
    except urllib.error.HTTPError as exc:
        # Certains sites refusent HEAD mais servent GET : on retente avant
        # de déclarer une page morte.
        if exc.code in (403, 405):
            try:
                repli = urllib.request.Request(url, headers=_ENTETES)  # noqa: S310
                with urllib.request.urlopen(repli, timeout=timeout) as reponse:  # noqa: S310
                    code = reponse.status
            except (urllib.error.URLError, OSError) as exc2:
                return f"injoignable : {exc2}"
        else:
            return f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        return f"injoignable : {exc}"
    return None if 200 <= code < 400 else f"HTTP {code}"
