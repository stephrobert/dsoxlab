"""L'avis de mise à jour doit se faire oublier.

Ces tests portent moins sur « détecte-t-il une nouvelle version » que sur
« peut-il nuire ». Un avis qui casse une commande, qui fait attendre, ou qui
glisse une ligne de texte devant un document JSON coûterait bien plus cher
que le service qu'il rend.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dsoxlab.services import update_check


@pytest.fixture(autouse=True)
def _cache_isole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Jamais le vrai cache de l'utilisateur, jamais son opt-out."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.delenv("DSOXLAB_NO_UPDATE_CHECK", raising=False)


class TestParseVersion:
    @pytest.mark.parametrize(
        ("brut", "attendu"),
        [
            ("0.1.24", (0, 1, 24)),
            ("1.0.0", (1, 0, 0)),
            ("0.2", (0, 2, 0)),
            ("3", (3, 0, 0)),
            # Une pré-release est ramenée à sa version de base : on ne
            # propose jamais une rc comme si c'était une sortie.
            ("0.2.0rc1", (0, 2, 0)),
            ("1.0.0.dev3", (1, 0, 0)),
            # Illisible plutôt qu'une exception : l'avis se tait, il ne casse pas.
            ("", (0, 0, 0)),
            ("abc", (0, 0, 0)),
        ],
    )
    def test_decoupe(self, brut: str, attendu: tuple[int, int, int]) -> None:
        assert update_check.parse_version(brut) == attendu

    def test_ordre_numerique_et_non_alphabetique(self) -> None:
        """0.1.9 < 0.1.24, ce qu'une comparaison de chaînes rate."""
        assert update_check.parse_version("0.1.9") < update_check.parse_version("0.1.24")


class TestAvailableUpdate:
    def test_signale_une_version_plus_recente(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(update_check, "fetch_latest_version", lambda: "0.2.0")
        assert update_check.available_update("0.1.24") == "0.2.0"

    def test_se_tait_si_a_jour(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(update_check, "fetch_latest_version", lambda: "0.1.24")
        assert update_check.available_update("0.1.24") is None

    def test_se_tait_si_installee_plus_recente(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cas d'un développeur en editable, en avance sur PyPI."""
        monkeypatch.setattr(update_check, "fetch_latest_version", lambda: "0.1.24")
        assert update_check.available_update("0.2.0") is None

    def test_se_tait_hors_ligne(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(update_check, "fetch_latest_version", lambda: None)
        assert update_check.available_update("0.1.1") is None

    def test_opt_out_court_circuite_le_reseau(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DSOXLAB_NO_UPDATE_CHECK doit couper avant toute requête."""
        appels = []

        def _interdit() -> str:
            appels.append(1)
            return "0.2.0"

        monkeypatch.setattr(update_check, "fetch_latest_version", _interdit)
        monkeypatch.setenv("DSOXLAB_NO_UPDATE_CHECK", "1")
        assert update_check.available_update("0.1.1") is None
        assert appels == [], "PyPI a été interrogé malgré l'opt-out"


class TestCache:
    def test_deuxieme_appel_ne_refait_pas_de_requete(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        appels: list[int] = []

        def _compte() -> str:
            appels.append(1)
            return "0.2.0"

        monkeypatch.setattr(update_check, "fetch_latest_version", _compte)
        assert update_check.available_update("0.1.1") == "0.2.0"
        assert update_check.available_update("0.1.1") == "0.2.0"
        assert len(appels) == 1, "le cache n'a pas servi"

    def test_cache_perime_declenche_une_requete(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(update_check, "fetch_latest_version", lambda: "0.2.0")
        update_check.available_update("0.1.1")

        chemin = update_check.cache_path()
        payload = json.loads(chemin.read_text(encoding="utf-8"))
        payload["checked_at"] -= update_check.CACHE_TTL_SECONDS + 1
        chemin.write_text(json.dumps(payload), encoding="utf-8")

        monkeypatch.setattr(update_check, "fetch_latest_version", lambda: "0.3.0")
        assert update_check.available_update("0.1.1") == "0.3.0"

    def test_force_ignore_le_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(update_check, "fetch_latest_version", lambda: "0.2.0")
        update_check.available_update("0.1.1")
        monkeypatch.setattr(update_check, "fetch_latest_version", lambda: "0.3.0")
        assert update_check.available_update("0.1.1", force=True) == "0.3.0"

    def test_cache_corrompu_est_traite_comme_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chemin = update_check.cache_path()
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("{ ceci n'est pas du json", encoding="utf-8")
        monkeypatch.setattr(update_check, "fetch_latest_version", lambda: "0.2.0")
        assert update_check.available_update("0.1.1") == "0.2.0"

    def test_cache_illisible_ne_leve_pas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Home en lecture seule : on perd le cache, pas la commande."""

        def _echec(*_args: object, **_kwargs: object) -> None:
            raise OSError("read-only file system")

        monkeypatch.setattr(update_check.Path, "write_text", _echec)
        monkeypatch.setattr(update_check, "fetch_latest_version", lambda: "0.2.0")
        assert update_check.available_update("0.1.1") == "0.2.0"


class TestFetchNeLevePas:
    """Quoi que rende le réseau, fetch_latest_version() rend None ou un str."""

    @pytest.mark.parametrize(
        "reponse",
        [
            b"pas du json",
            b"{}",
            b'{"info": {}}',
            b'{"info": {"version": null}}',
            b'{"info": {"version": "   "}}',
            b"[]",
        ],
    )
    def test_reponse_inattendue(
        self, reponse: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Reponse:
            def __enter__(self) -> _Reponse:
                return self

            def __exit__(self, *_exc: object) -> None:
                return None

            def read(self) -> bytes:
                return reponse

        monkeypatch.setattr(
            update_check.urllib.request, "urlopen", lambda *a, **k: _Reponse()
        )
        assert update_check.fetch_latest_version() is None

    def test_erreur_reseau(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boum(*_args: object, **_kwargs: object) -> None:
            raise OSError("network is unreachable")

        monkeypatch.setattr(update_check.urllib.request, "urlopen", _boum)
        assert update_check.fetch_latest_version() is None
