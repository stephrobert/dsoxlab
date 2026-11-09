"""Persistance SQLite : résultats de validation et demandes de hints."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DB_FILE = ".dsoxlab.db"


# ── Connexion & schéma ────────────────────────────────────────────────────────

def _get_db(root: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(root / _DB_FILE)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS results (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id        TEXT    NOT NULL,
            section       TEXT    NOT NULL,
            validated_at  TEXT    NOT NULL,
            score         INTEGER NOT NULL,
            max_score     INTEGER NOT NULL,
            passed_tests  INTEGER NOT NULL,
            total_tests   INTEGER NOT NULL,
            hints_used    INTEGER NOT NULL,
            -- Les contrôles bloquants qui ont échoué, séparés par une virgule.
            -- Vide veut dire « aucun », et c'est aussi ce que portent les
            -- lignes écrites avant que cette colonne existe : pour elles, on
            -- ne sait pas, et le verdict retombe sur le seul score. Deviner
            -- aurait été pire.
            blocking_failed TEXT NOT NULL DEFAULT '',
            -- TOUS les contrôles qui ont échoué, séparés par une virgule, dont
            -- les bloquants. C'est ce qui permet de dire À QUOI se remettre :
            -- un verdict exact qui ne nomme rien laisse l'apprenant devant
            -- « 3 sur 5 », et le portail n'a rien à lui proposer.
            failed_checks  TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS hint_requests (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id       TEXT    NOT NULL,
            hint_index   INTEGER NOT NULL,
            requested_at TEXT    NOT NULL,
            cost         INTEGER NOT NULL
        );
    """)
    _ajouter_colonnes_manquantes(conn)
    conn.commit()


def _ajouter_colonnes_manquantes(conn: sqlite3.Connection) -> None:
    """Les colonnes ajoutées après coup, sur une base qui existe déjà.

    `CREATE TABLE IF NOT EXISTS` ne touche pas une table présente : une base
    créée avant l'ajout d'une colonne ne l'aurait jamais. Toute l'écriture
    lèverait alors `no such column`, sur la machine de quelqu'un qui joue des
    labs depuis des mois, et le message ne dirait rien d'utile.

    La migration est ADDITIVE et idempotente : on lit les colonnes présentes,
    on ajoute celles qui manquent, avec une valeur par défaut. Aucune donnée
    n'est réécrite, et une base déjà à jour ne subit rien.
    """
    attendues = {
        "blocking_failed": "TEXT NOT NULL DEFAULT ''",
        "failed_checks": "TEXT NOT NULL DEFAULT ''",
        # 0.8.0 (#336, lot B). Toutes NULL par défaut, et NULL veut dire
        # INCONNU : une ligne écrite avant cette version n'a rien de tout cela,
        # et on ne reconstitue pas ce qu'on n'a pas mesuré.
        #
        # attempt_id       uuid4 de la tentative.
        # lab_digest       empreinte du lab (lab.yaml, tests, hints.yaml).
        # catalog_revision révision du catalogue AU MOMENT du check.
        # criteria         JSON compact : un résultat par critère.
        # hints_seen       JSON : les indices vus, copiés ici parce que
        #                  `reset_hints` efface `hint_requests`.
        "attempt_id": "TEXT DEFAULT NULL",
        "lab_digest": "TEXT DEFAULT NULL",
        "catalog_revision": "TEXT DEFAULT NULL",
        "criteria": "TEXT DEFAULT NULL",
        "hints_seen": "TEXT DEFAULT NULL",
    }
    presentes = {
        ligne["name"] for ligne in conn.execute("PRAGMA table_info(results)")
    }
    for nom, declaration in attendues.items():
        if nom not in presentes:
            conn.execute(f"ALTER TABLE results ADD COLUMN {nom} {declaration}")


# ── Hints ─────────────────────────────────────────────────────────────────────

def next_hint_index(root: Path, lab_id: str) -> int:
    """Retourne l'index du prochain hint non encore demandé (0-based)."""
    with _get_db(root) as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(hint_index), -1) AS last FROM hint_requests WHERE lab_id = ?",
            (lab_id,),
        ).fetchone()
        return (row["last"] + 1) if row else 0


def hints_used_count(root: Path, lab_id: str) -> int:
    with _get_db(root) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM hint_requests WHERE lab_id = ?",
            (lab_id,),
        ).fetchone()
        return row["n"] if row else 0


def hints_cost_total(root: Path, lab_id: str) -> int:
    """Retourne la somme des coûts de tous les hints déjà demandés."""
    with _get_db(root) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost), 0) AS total FROM hint_requests WHERE lab_id = ?",
            (lab_id,),
        ).fetchone()
        return int(row["total"]) if row else 0


def hint_requests_for(root: Path, lab_id: str) -> list[dict[str, Any]]:
    """Les indices demandés pour ce lab, dans l'ordre où ils l'ont été."""
    with _get_db(root) as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT hint_index, requested_at, cost FROM hint_requests "
                "WHERE lab_id = ? ORDER BY id ASC",
                (lab_id,),
            ).fetchall()
        ]


def record_hint(root: Path, lab_id: str, hint_index: int, cost: int) -> None:
    with _get_db(root) as conn:
        conn.execute(
            "INSERT INTO hint_requests (lab_id, hint_index, requested_at, cost) VALUES (?, ?, ?, ?)",
            (lab_id, hint_index, _now(), cost),
        )
        conn.commit()


def reset_hints(root: Path, lab_id: str) -> None:
    """Supprime tous les hints enregistrés pour ce lab (appelé lors d'un reset)."""
    with _get_db(root) as conn:
        conn.execute("DELETE FROM hint_requests WHERE lab_id = ?", (lab_id,))
        conn.commit()


# ── Résultats ─────────────────────────────────────────────────────────────────

def record_result(
    root: Path,
    *,
    lab_id: str,
    section: str,
    score: int,
    max_score: int,
    passed_tests: int,
    total_tests: int,
    hints_used: int,
    blocking_failed: tuple[str, ...] = (),
    failed_checks: tuple[str, ...] = (),
    attempt_id: str | None = None,
    lab_digest: str | None = None,
    catalog_revision: str | None = None,
    criteria: str | None = None,
    hints_seen: str | None = None,
) -> None:
    """Inscrit une tentative. Les cinq derniers champs (0.8.0) valent ``None``
    = inconnu, et c'est ce que portent aussi les lignes plus anciennes."""
    with _get_db(root) as conn:
        conn.execute(
            """INSERT INTO results
               (lab_id, section, validated_at, score, max_score, passed_tests,
                total_tests, hints_used, blocking_failed, failed_checks,
                attempt_id, lab_digest, catalog_revision, criteria, hints_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (lab_id, section, _now(), score, max_score, passed_tests, total_tests,
             hints_used, ",".join(blocking_failed), ",".join(failed_checks),
             attempt_id, lab_digest, catalog_revision, criteria, hints_seen),
        )
        conn.commit()


def get_results(
    root: Path,
    *,
    lab_id: str | None = None,
    section: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    with _get_db(root) as conn:
        query = "SELECT * FROM results"
        params: list[Any] = []
        conditions: list[str] = []
        if lab_id:
            conditions.append("lab_id = ?")
            params.append(lab_id)
        if section:
            conditions.append("section = ?")
            params.append(section)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY validated_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_all_results(root: Path) -> list[dict[str, Any]]:
    """Tous les résultats du dépôt, sans limite ni troncature.

    ``get_results`` plafonne à cinquante lignes, ce qui convient à un affichage
    et **pas** à un export : un document qui s'arrête sans le dire est pire
    qu'un document absent, parce que celui qui le lit croit tout avoir. La
    limite n'est donc pas relevée ici, elle n'existe pas.

    Ordre chronologique croissant, contrairement à l'affichage : un export se
    lit comme un historique, du premier résultat au dernier.
    """
    with _get_db(root) as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM results ORDER BY validated_at ASC, id ASC"
            ).fetchall()
        ]


def get_best_scores(
    root: Path,
    lab_ids: list[str] | None = None,
) -> dict[str, tuple[int, int]]:
    """Retourne {lab_id: (best_score, max_score)} pour les labs ayant au moins un résultat."""
    with _get_db(root) as conn:
        if lab_ids:
            # placeholders ne contient que des "?" (un par lab_id) ; les valeurs
            # passent en paramètres liés -> pas d'injection possible.
            placeholders = ",".join("?" * len(lab_ids))
            rows = conn.execute(
                f"SELECT lab_id, MAX(score) AS best, MAX(max_score) AS max_s "  # noqa: S608 — placeholders = "?" liés, requête paramétrée
                f"FROM results WHERE lab_id IN ({placeholders}) GROUP BY lab_id",
                lab_ids,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT lab_id, MAX(score) AS best, MAX(max_score) AS max_s "
                "FROM results GROUP BY lab_id"
            ).fetchall()
    return {r["lab_id"]: (r["best"], r["max_s"]) for r in rows}


def get_exam_outcomes(
    root: Path, labs: dict[str, int]
) -> dict[str, bool]:
    """Pour chaque épreuve, une tentative l'a-t-elle REMPORTÉE ?

    ``labs`` associe un ``lab_id`` à son ``exam_passing_score``. Rend un
    booléen par lab ayant au moins une tentative.

    POURQUOI CETTE FONCTION PLUTÔT QUE ``get_best_scores``. Le meilleur score
    ne suffit pas à dire qu'une épreuve est remportée : il ignore le seuil, et
    surtout il ignore les contrôles bloquants. Mesuré avant cette correction,
    une épreuve à 0 sur 100 dont le contrôle critique avait échoué était
    déclarée validée par `dsoxlab progress`, pendant que `submit` la refusait.

    UNE TENTATIVE SUFFIT, et ce n'est pas la meilleure au sens du score : une
    tentative à 80 avec un blocage ne vaut pas une tentative à 76 sans. On
    cherche donc s'il EXISTE une tentative qui franchit le seuil sans blocage,
    ce qui est la définition même de « remportée ». Un apprenant qui réussit,
    puis rejoue et rate, n'a pas désappris.
    """
    if not labs:
        return {}
    with _get_db(root) as conn:
        placeholders = ",".join("?" * len(labs))
        rows = conn.execute(
            f"SELECT lab_id, score, max_score, blocking_failed "  # noqa: S608 — placeholders = "?" liés
            f"FROM results WHERE lab_id IN ({placeholders})",
            list(labs),
        ).fetchall()
    issues: dict[str, bool] = {}
    for r in rows:
        lab_id = r["lab_id"]
        seuil = labs[lab_id]
        # La même comparaison en entiers que `exam_verdict`, pour que les deux
        # ne puissent pas diverger d'un arrondi.
        reussie = (
            not (r["blocking_failed"] or "")
            and r["max_score"] > 0
            and r["score"] * 100 >= seuil * r["max_score"]
        )
        issues[lab_id] = issues.get(lab_id, False) or reussie
    return issues


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(UTC).isoformat()
