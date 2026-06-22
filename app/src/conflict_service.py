from __future__ import annotations

import json
import sqlite3
from typing import Any


def get_unresolved_conflicts(
    connection: sqlite3.Connection,
    patient_profile_id: int,
    severity: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["patient_profile_id = ?", "resolution_status = 'unresolved'"]
    params: list[Any] = [patient_profile_id]
    if severity:
        clauses.append("severity = ?")
        params.append(severity)

    med_rows = connection.execute(
        f"""
        SELECT id, patient_profile_id, medication_1_id AS left_entity_id, medication_2_id AS right_entity_id,
               conflict_type, severity, conflict_description, detected_at, resolution_status,
               resolution_action, resolution_notes, resolved_by, resolved_at
        FROM medication_conflicts
        WHERE {' AND '.join(clauses)}
        ORDER BY CASE severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, detected_at DESC
        """,
        params,
    ).fetchall()

    allergy_rows = connection.execute(
        f"""
        SELECT id, patient_profile_id, allergy_id AS left_entity_id, medication_id AS right_entity_id,
               'allergy' AS conflict_type, severity, conflict_description, detected_at, resolution_status,
               resolution_action, resolution_notes, resolved_by, resolved_at
        FROM allergy_drug_conflicts
        WHERE {' AND '.join(clauses)}
        ORDER BY CASE severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, detected_at DESC
        """,
        params,
    ).fetchall()

    conflicts = [dict(row) for row in med_rows] + [dict(row) for row in allergy_rows]
    for conflict in conflicts:
        conflict.update(get_conflict_sources(connection, conflict["conflict_type"], conflict["id"]))
    return conflicts


def get_conflict_sources(
    connection: sqlite3.Connection,
    conflict_type: str,
    conflict_id: int,
) -> dict[str, Any]:
    if conflict_type == "allergy":
        row = connection.execute(
            """
            SELECT c.id, c.patient_profile_id, c.allergy_id, c.medication_id, c.severity,
                   c.conflict_description, c.detected_at, c.resolution_status, c.resolution_action,
                   c.resolution_notes, c.resolved_by, c.resolved_at,
                   a.entity_value AS left_entity_value,
                   a.source_type AS left_source_type,
                   a.source_id AS left_source_id,
                   a.confidence_score AS left_confidence_score,
                   a.extracted_at AS left_extracted_at,
                   a.evidence_text AS left_evidence_text,
                   m.entity_value AS right_entity_value,
                   m.source_type AS right_source_type,
                   m.source_id AS right_source_id,
                   m.confidence_score AS right_confidence_score,
                   m.extracted_at AS right_extracted_at,
                   m.evidence_text AS right_evidence_text
            FROM allergy_drug_conflicts c
            JOIN extracted_entities a ON a.id = c.allergy_id
            JOIN extracted_entities m ON m.id = c.medication_id
            WHERE c.id = ?
            """,
            [conflict_id],
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT c.id, c.patient_profile_id, c.medication_1_id, c.medication_2_id, c.conflict_type,
                   c.severity, c.conflict_description, c.detected_at, c.resolution_status,
                   c.resolution_action, c.resolution_notes, c.resolved_by, c.resolved_at,
                   m1.entity_value AS left_entity_value,
                   m1.source_type AS left_source_type,
                   m1.source_id AS left_source_id,
                   m1.confidence_score AS left_confidence_score,
                   m1.extracted_at AS left_extracted_at,
                   m1.evidence_text AS left_evidence_text,
                   m2.entity_value AS right_entity_value,
                   m2.source_type AS right_source_type,
                   m2.source_id AS right_source_id,
                   m2.confidence_score AS right_confidence_score,
                   m2.extracted_at AS right_extracted_at,
                   m2.evidence_text AS right_evidence_text
            FROM medication_conflicts c
            JOIN extracted_entities m1 ON m1.id = c.medication_1_id
            JOIN extracted_entities m2 ON m2.id = c.medication_2_id
            WHERE c.id = ?
            """,
            [conflict_id],
        ).fetchone()

    return dict(row) if row else {}


def resolve_conflict(
    connection: sqlite3.Connection,
    conflict_type: str,
    conflict_id: int,
    action: str,
    reviewer_id: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if action not in {"resolve", "merge", "discard"}:
        raise ValueError("Unsupported resolution action")

    conflict = get_conflict_sources(connection, conflict_type, conflict_id)
    if not conflict:
        raise ValueError("Conflict not found")

    resolution_status = {
        "resolve": "resolved",
        "merge": "merged",
        "discard": "discarded",
    }[action]

    if conflict_type == "allergy":
        connection.execute(
            """
            UPDATE allergy_drug_conflicts
            SET resolution_status = ?, resolution_action = ?, resolution_notes = ?,
                resolved_by = ?, resolved_at = CURRENT_TIMESTAMP, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            [resolution_status, action, json.dumps(details or {}), reviewer_id, reviewer_id, conflict_id],
        )
    else:
        connection.execute(
            """
            UPDATE medication_conflicts
            SET resolution_status = ?, resolution_action = ?, resolution_notes = ?,
                resolved_by = ?, resolved_at = CURRENT_TIMESTAMP, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            [resolution_status, action, json.dumps(details or {}), reviewer_id, reviewer_id, conflict_id],
        )

    connection.execute(
        """
        INSERT INTO conflict_resolutions(
            conflict_type, conflict_id, patient_profile_id, resolution_status, action_taken,
            reviewer_id, source_versions_json, details_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            conflict_type,
            conflict_id,
            conflict["patient_profile_id"],
            resolution_status,
            action,
            reviewer_id,
            json.dumps(
                {
                    "left": {
                        "entity_value": conflict.get("left_entity_value"),
                        "source_type": conflict.get("left_source_type"),
                        "source_id": conflict.get("left_source_id"),
                        "confidence_score": conflict.get("left_confidence_score"),
                        "extracted_at": conflict.get("left_extracted_at"),
                        "evidence_text": conflict.get("left_evidence_text"),
                    },
                    "right": {
                        "entity_value": conflict.get("right_entity_value"),
                        "source_type": conflict.get("right_source_type"),
                        "source_id": conflict.get("right_source_id"),
                        "confidence_score": conflict.get("right_confidence_score"),
                        "extracted_at": conflict.get("right_extracted_at"),
                        "evidence_text": conflict.get("right_evidence_text"),
                    },
                }
            ),
            json.dumps(details or {}),
        ],
    )
    try:
        connection.execute(
            """
            INSERT INTO clinical_audit_log(
                patient_profile_id, action_type, actor_type, actor_id, entity_type, entity_id, details_json
            )
            VALUES (?, 'conflict_resolution', 'clinician', ?, ?, ?, ?)
            """,
            [
                conflict["patient_profile_id"],
                reviewer_id,
                conflict_type,
                conflict_id,
                json.dumps({"action": action, "details": details or {}}),
            ],
        )
    except sqlite3.IntegrityError:
        pass
    connection.commit()
    conflict.update({"resolution_status": resolution_status, "resolution_action": action, "resolved_by": reviewer_id})
    return conflict
