"""Le cloud-init Ubuntu choisit un miroir de paquets qui répond.

archive.ubuntu.com et security.ubuntu.com, tous deux servis par Canonical, ont
cessé de répondre en HTTP deux fois le 2026-11-19, alors que le ping passait.
cloud-init n'installait aucun paquet, et tout setup.yaml qui passe par apt
échouait sur une machine annoncée prête.

Ces tests JOUENT le script du ``bootcmd`` tel que le template le livre, après
la substitution de templatefile(). Seuls changent les chemins absolus, ramenés
dans un répertoire temporaire, et ``curl``, remplacé par un faux qui répond
selon le miroir. Un test qui se contenterait de lire le texte du template ne
dirait pas si la réécriture des sources marche.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from dsoxlab.templates import cloud_init_template

_SOURCES = """\
Types: deb
URIs: http://archive.ubuntu.com/ubuntu
Suites: noble noble-updates noble-backports
Components: main universe restricted multiverse

Types: deb
URIs: http://security.ubuntu.com/ubuntu
Suites: noble-security
Components: main universe restricted multiverse
"""


def _cloud_config() -> dict[str, object]:
    texte = cloud_init_template("ubuntu").read_text(encoding="utf-8")
    rendu = texte.replace("${hostname}", "essai").replace("${ssh_pubkey}", "ssh-ed25519 AAAA")
    doc = yaml.safe_load(rendu)
    assert isinstance(doc, dict)
    return doc


def _script() -> str:
    bootcmd = _cloud_config()["bootcmd"]
    assert isinstance(bootcmd, list) and isinstance(bootcmd[0], str)
    return bootcmd[0]


def _jouer(tmp_path: Path, repondent: set[str]) -> tuple[str, Path]:
    """Joue le script dans ``tmp_path``. ``repondent`` : les hôtes qui répondent."""
    etc = tmp_path / "etc" / "apt"
    (etc / "sources.list.d").mkdir(parents=True)
    (etc / "sources.list.d" / "ubuntu.sources").write_text(_SOURCES, encoding="utf-8")
    (etc / "sources.list").write_text("# Ubuntu sources have moved\n", encoding="utf-8")
    (tmp_path / "os-release").write_text("VERSION_CODENAME=noble\n", encoding="utf-8")
    var = tmp_path / "var" / "lib" / "dsoxlab"

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    faux_curl = bin_dir / "curl"
    faux_curl.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do url="$a"; done\n'
        'echo "$url" >> "$JOURNAL_CURL"\n'
        f"for h in {' '.join(sorted(repondent)) or 'aucun'}; do\n"
        '  case "$url" in "http://$h/"*) exit 0 ;; esac\n'
        "done\n"
        "exit 28\n",
        encoding="utf-8",
    )
    faux_curl.chmod(0o755)

    script = (
        _script()
        .replace("/etc/apt", str(etc))
        .replace("/etc/os-release", str(tmp_path / "os-release"))
        .replace("/var/lib/dsoxlab", str(var))
    )
    journal = tmp_path / "curl.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "JOURNAL_CURL": str(journal),
    }
    res = subprocess.run(
        [shutil.which("sh") or "/bin/sh", "-c", script],
        env=env, capture_output=True, text=True, check=False,
    )
    assert res.returncode == 0, res.stderr
    return (etc / "sources.list.d" / "ubuntu.sources").read_text(encoding="utf-8"), var


def test_archive_qui_repond_laisse_les_sources_intactes(tmp_path: Path) -> None:
    sources, var = _jouer(tmp_path, {"archive.ubuntu.com"})
    assert sources == _SOURCES
    assert (var / "miroir-apt").read_text().strip() == "http://archive.ubuntu.com/ubuntu"


def test_archive_muet_bascule_paquets_et_securite_sur_le_premier_miroir_qui_repond(
    tmp_path: Path,
) -> None:
    sources, var = _jouer(tmp_path, {"de.archive.ubuntu.com", "nl.archive.ubuntu.com"})
    assert "archive.ubuntu.com/ubuntu" not in sources.replace("de.archive", "")
    assert "security.ubuntu.com" not in sources
    assert sources.count("URIs: http://de.archive.ubuntu.com/ubuntu") == 2
    assert (var / "miroir-apt").read_text().strip() == "http://de.archive.ubuntu.com/ubuntu"


def test_la_sonde_lit_la_poche_security(tmp_path: Path) -> None:
    _jouer(tmp_path, {"fr.archive.ubuntu.com"})
    urls = (tmp_path / "curl.log").read_text().split()
    assert urls[0] == "http://archive.ubuntu.com/ubuntu/dists/noble-security/Release"


def test_aucun_miroir_ne_touche_rien_et_laisse_reessayer_au_demarrage_suivant(
    tmp_path: Path,
) -> None:
    sources, var = _jouer(tmp_path, set())
    assert sources == _SOURCES
    assert not (var / "miroir-apt").exists()


def test_un_choix_deja_fait_n_est_jamais_refait(tmp_path: Path) -> None:
    _jouer(tmp_path, {"fr.archive.ubuntu.com"})
    journal = tmp_path / "curl.log"
    journal.unlink()
    script = _script().replace("/var/lib/dsoxlab", str(tmp_path / "var" / "lib" / "dsoxlab"))
    env = {
        **os.environ,
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "JOURNAL_CURL": str(journal),
    }
    res = subprocess.run(
        ["sh", "-c", script], env=env, capture_output=True, text=True, check=False,
    )
    assert res.returncode == 0
    assert not journal.exists(), "le faux curl a été appelé : le choix a été refait"


def test_aucun_miroir_de_secours_n_est_heberge_par_canonical() -> None:
    """gb et us pointent sur les serveurs de Canonical : ils tombent avec eux."""
    script = _script()
    for national in ("gb.archive", "us.archive"):
        assert national not in script


@pytest.mark.parametrize("cle", ["preserve_sources_list"])
def test_apt_configure_ne_reecrit_pas_le_choix(cle: str) -> None:
    """bootcmd passe avant apt_configure, qui régénère ubuntu.sources."""
    apt = _cloud_config()["apt"]
    assert isinstance(apt, dict) and apt.get(cle) is True
