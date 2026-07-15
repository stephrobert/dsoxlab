"""Persistance SQLite : résultats de validation et demandes de hints."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
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
            hints_used    INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS hint_requests (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id       TEXT    NOT NULL,
            hint_index   INTEGER NOT NULL,
            requested_at TEXT    NOT NULL,
            cost         INTEGER NOT NULL
        );
    """)
    conn.commit()


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
) -> None:
    with _get_db(root) as conn:
        conn.execute(
            """INSERT INTO results
               (lab_id, section, validated_at, score, max_score, passed_tests, total_tests, hints_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (lab_id, section, _now(), score, max_score, passed_tests, total_tests, hints_used),
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
