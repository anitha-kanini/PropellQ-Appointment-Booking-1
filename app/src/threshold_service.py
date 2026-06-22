from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

DEFAULT_THRESHOLDS = {
    "icd10": 0.70,
    "cpt": 0.70,
}
AUTHORIZED_THRESHOLD_ROLES = {"admin", "coder"}


def get_threshold_config(connection: sqlite3.Connection, code_type: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT code_type, confidence_threshold, updated_by, updated_at
        FROM code_threshold_config
        WHERE code_type = ?
        """,
        [code_type],
    ).fetchone()
    if row:
        return dict(row)

    default_threshold = DEFAULT_THRESHOLDS.get(code_type, 0.70)
    connection.execute(
        """
        INSERT OR IGNORE INTO code_threshold_config(code_type, confidence_threshold, updated_by, updated_at)
        VALUES (?, ?, 'system', CURRENT_TIMESTAMP)
        """,
        [code_type, default_threshold],
    )
    connection.commit()
    return {
        "code_type": code_type,
        "confidence_threshold": default_threshold,
        "updated_by": "system",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


def update_threshold_config(
    connection: sqlite3.Connection,
    code_type: str,
    confidence_threshold: float,
    actor_id: str,
    actor_role: str,
    change_reason: str | None = None,
) -> dict[str, Any]:
    if actor_role not in AUTHORIZED_THRESHOLD_ROLES:
        raise PermissionError("Unauthorized threshold update")
    if code_type not in DEFAULT_THRESHOLDS:
        raise ValueError("Unsupported code type")
    if confidence_threshold < 0 or confidence_threshold > 1:
        raise ValueError("Threshold must be between 0 and 1")

    current = get_threshold_config(connection, code_type)
    connection.execute(
        """
        INSERT INTO threshold_config_audit(code_type, old_threshold, new_threshold, actor_id, actor_role, change_reason)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [code_type, current["confidence_threshold"], confidence_threshold, actor_id, actor_role, change_reason],
    )
    connection.execute(
        """
        INSERT INTO code_threshold_config(code_type, confidence_threshold, updated_by, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(code_type) DO UPDATE SET
            confidence_threshold = excluded.confidence_threshold,
            updated_by = excluded.updated_by,
            updated_at = excluded.updated_at
        """,
        [code_type, confidence_threshold, actor_id],
    )
    connection.commit()
    return get_threshold_config(connection, code_type)


def get_threshold_history(connection: sqlite3.Connection, code_type: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT code_type, old_threshold, new_threshold, actor_id, actor_role, change_reason, changed_at
        FROM threshold_config_audit
        WHERE code_type = ?
        ORDER BY changed_at DESC, id DESC
        """,
        [code_type],
    ).fetchall()
    return [dict(row) for row in rows]


def apply_threshold(
    connection: sqlite3.Connection,
    code_type: str,
    confidence_score: float,
) -> dict[str, Any]:
    threshold = get_threshold_config(connection, code_type)["confidence_threshold"]
    auto_accepted = confidence_score >= threshold
    return {
        "code_type": code_type,
        "confidence_threshold": threshold,
        "auto_accepted": auto_accepted,
        "review_required": not auto_accepted,
    }
