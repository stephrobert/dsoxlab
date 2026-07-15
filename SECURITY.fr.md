# Politique de sécurité

**Langue :** [English](./SECURITY.md) · [Français](./SECURITY.fr.md)

## Versions supportées

`dsoxlab` est en développement actif. Les correctifs de sécurité sont appliqués
à la dernière version de la branche `main`.

| Version | Supportée |
| --- | --- |
| dernière (`main`) | ✅ |
| plus anciennes | ❌ |

## Signaler une vulnérabilité

**N'ouvrez pas d'issue publique pour une vulnérabilité de sécurité.**

Si vous pensez avoir trouvé une vulnérabilité, signalez-la en privé :

- De préférence : ouvrez un
  [avis de sécurité privé](https://github.com/stephrobert/dsoxlab/security/advisories/new)
  sur GitHub.
- Sinon, utilisez les coordonnées publiées sur
  <https://blog.stephane-robert.info>.

Merci d'inclure :

- une description de la vulnérabilité et de son impact,
- les étapes pour la reproduire (commande, environnement, `dsoxlab --version`),
- tout log ou preuve de concept pertinent.

Nous accuserons réception de votre signalement dès que possible, vous tiendrons
informé de l'avancement du correctif, et vous créditerons dans les notes de
version si vous le souhaitez.

## Périmètre

`dsoxlab` pilote des outils externes (SSH, Terraform, libvirt/Incus, `pytest`)
et exécute des scripts de lab fournis par les dépôts de labs. Les vulnérabilités
du moteur lui-même, de la façon dont il invoque ces outils, ou de sa gestion des
identifiants et des configurations générées, sont dans le périmètre. Les
problèmes des dépendances tierces doivent être signalés à leurs projets
respectifs.
