from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime
from typing import Any

from src.threshold_service import apply_threshold, get_threshold_config

DEFAULT_REVIEW_THRESHOLD = 0.70


def aggregate_patient_profile(connection: sqlite3.Connection, patient_profile_id: int) -> dict[str, Any]:
    """Merge intake and extracted entities into a unified profile with intake priority."""
    profile_row = connection.execute(
        "SELECT * FROM clinical_profile WHERE patient_profile_id = ?",
        [patient_profile_id],
    ).fetchone()

    current = {
        "medications": _json_list(profile_row, "medications_json"),
        "allergies": _json_list(profile_row, "allergies_json"),
        "diagnoses": _json_list(profile_row, "diagnoses_json"),
        "procedures": _json_list(profile_row, "procedures_json"),
        "vitals": _json_list(profile_row, "vitals_json"),
        "lab_results": _json_list(profile_row, "lab_results_json"),
    }

    extracted = connection.execute(
        """
        SELECT entity_type, entity_value, confidence_score, source_type, source_id, extracted_at, evidence_text
        FROM extracted_entities
        WHERE patient_profile_id = ?
        ORDER BY extracted_at DESC
        """,
        [patient_profile_id],
    ).fetchall()

    type_map = {
        "medication": "medications",
        "allergy": "allergies",
        "diagnosis": "diagnoses",
        "procedure": "procedures",
        "vital": "vitals",
        "lab_result": "lab_results",
    }

    merged = {key: list(values) for key, values in current.items()}
    for row in extracted:
        bucket = type_map.get(row["entity_type"])
        if not bucket:
            continue
        merged[bucket].append(
            {
                "entity_value": row["entity_value"],
                "confidence_score": row["confidence_score"],
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "extracted_at": row["extracted_at"],
                "evidence_text": row["evidence_text"],
            }
        )

    deduped = {key: _dedupe_entities(values) for key, values in merged.items()}

    if profile_row:
        connection.execute(
            """
            UPDATE clinical_profile
            SET medications_json = ?,
                allergies_json = ?,
                diagnoses_json = ?,
                procedures_json = ?,
                vitals_json = ?,
                lab_results_json = ?,
                last_aggregated_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE patient_profile_id = ?
            """,
            [
                json.dumps(deduped["medications"]),
                json.dumps(deduped["allergies"]),
                json.dumps(deduped["diagnoses"]),
                json.dumps(deduped["procedures"]),
                json.dumps(deduped["vitals"]),
                json.dumps(deduped["lab_results"]),
                patient_profile_id,
            ],
        )
    else:
        connection.execute(
            """
            INSERT INTO clinical_profile(
                patient_profile_id,
                medications_json,
                allergies_json,
                diagnoses_json,
                procedures_json,
                vitals_json,
                lab_results_json,
                last_aggregated_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [
                patient_profile_id,
                json.dumps(deduped["medications"]),
                json.dumps(deduped["allergies"]),
                json.dumps(deduped["diagnoses"]),
                json.dumps(deduped["procedures"]),
                json.dumps(deduped["vitals"]),
                json.dumps(deduped["lab_results"]),
            ],
        )

    connection.execute(
        """
        INSERT INTO clinical_audit_log(
            patient_profile_id, action_type, actor_type, actor_id, entity_type, details_json
        )
        VALUES (?, 'profile_aggregation', 'system', 'aggregator', 'clinical_profile', ?)
        """,
        [
            patient_profile_id,
            json.dumps(
                {
                    "counts": {
                        "medications": len(deduped["medications"]),
                        "allergies": len(deduped["allergies"]),
                        "diagnoses": len(deduped["diagnoses"]),
                        "procedures": len(deduped["procedures"]),
                        "vitals": len(deduped["vitals"]),
                        "lab_results": len(deduped["lab_results"]),
                    }
                }
            ),
        ],
    )

    connection.commit()
    return get_patient_profile(connection, patient_profile_id)


def get_patient_profile(connection: sqlite3.Connection, patient_profile_id: int) -> dict[str, Any]:
    profile_row = connection.execute(
        "SELECT * FROM clinical_profile WHERE patient_profile_id = ?",
        [patient_profile_id],
    ).fetchone()

    if not profile_row:
        return {
            "patient_profile_id": patient_profile_id,
            "medications": [],
            "allergies": [],
            "diagnoses": [],
            "procedures": [],
            "vitals": [],
            "lab_results": [],
            "conflicts": [],
            "code_suggestions": [],
            "last_aggregated_at": None,
        }

    return {
        "patient_profile_id": patient_profile_id,
        "medications": _json_list(profile_row, "medications_json"),
        "allergies": _json_list(profile_row, "allergies_json"),
        "diagnoses": _json_list(profile_row, "diagnoses_json"),
        "procedures": _json_list(profile_row, "procedures_json"),
        "vitals": _json_list(profile_row, "vitals_json"),
        "lab_results": _json_list(profile_row, "lab_results_json"),
        "conflicts": _json_list(profile_row, "conflicts_json"),
        "code_suggestions": _json_list(profile_row, "code_suggestions_json"),
        "last_aggregated_at": profile_row["last_aggregated_at"],
    }


def detect_medication_conflicts(connection: sqlite3.Connection, patient_profile_id: int) -> list[dict[str, Any]]:
    meds = connection.execute(
        """
        SELECT id, entity_value
        FROM extracted_entities
        WHERE patient_profile_id = ? AND entity_type = 'medication'
        ORDER BY id ASC
        """,
        [patient_profile_id],
    ).fetchall()

    results: list[dict[str, Any]] = []
    for i in range(len(meds)):
        for j in range(i + 1, len(meds)):
            med1 = meds[i]
            med2 = meds[j]
            conflict = _match_medication_conflict(med1["entity_value"], med2["entity_value"])
            if not conflict:
                continue

            exists = connection.execute(
                """
                SELECT id
                FROM medication_conflicts
                WHERE patient_profile_id = ?
                  AND medication_1_id = ?
                  AND medication_2_id = ?
                  AND conflict_type = ?
                """,
                [patient_profile_id, med1["id"], med2["id"], conflict["conflict_type"]],
            ).fetchone()
            if exists:
                continue

            cursor = connection.execute(
                """
                INSERT INTO medication_conflicts(
                    patient_profile_id,
                    medication_1_id,
                    medication_2_id,
                    conflict_type,
                    severity,
                    conflict_description
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    patient_profile_id,
                    med1["id"],
                    med2["id"],
                    conflict["conflict_type"],
                    conflict["severity"],
                    conflict["description"],
                ],
            )
            results.append(
                {
                    "id": cursor.lastrowid,
                    "medication_1_id": med1["id"],
                    "medication_2_id": med2["id"],
                    "conflict_type": conflict["conflict_type"],
                    "severity": conflict["severity"],
                    "conflict_description": conflict["description"],
                }
            )

    if results:
        connection.execute(
            """
            INSERT INTO clinical_audit_log(
                patient_profile_id, action_type, actor_type, actor_id, entity_type, details_json
            )
            VALUES (?, 'conflict_detected', 'system', 'medication_conflict_engine', 'medication_conflict', ?)
            """,
            [patient_profile_id, json.dumps({"count": len(results)})],
        )

    connection.commit()
    return results


def detect_allergy_drug_conflicts(connection: sqlite3.Connection, patient_profile_id: int) -> list[dict[str, Any]]:
    allergies = connection.execute(
        """
        SELECT id, entity_value
        FROM extracted_entities
        WHERE patient_profile_id = ? AND entity_type = 'allergy'
        ORDER BY id ASC
        """,
        [patient_profile_id],
    ).fetchall()

    meds = connection.execute(
        """
        SELECT id, entity_value
        FROM extracted_entities
        WHERE patient_profile_id = ? AND entity_type = 'medication'
        ORDER BY id ASC
        """,
        [patient_profile_id],
    ).fetchall()

    results: list[dict[str, Any]] = []
    for allergy in allergies:
        for med in meds:
            conflict = _match_allergy_conflict(allergy["entity_value"], med["entity_value"])
            if not conflict:
                continue

            exists = connection.execute(
                """
                SELECT id
                FROM allergy_drug_conflicts
                WHERE patient_profile_id = ?
                  AND allergy_id = ?
                  AND medication_id = ?
                """,
                [patient_profile_id, allergy["id"], med["id"]],
            ).fetchone()
            if exists:
                continue

            cursor = connection.execute(
                """
                INSERT INTO allergy_drug_conflicts(
                    patient_profile_id,
                    allergy_id,
                    medication_id,
                    severity,
                    conflict_description
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    patient_profile_id,
                    allergy["id"],
                    med["id"],
                    conflict["severity"],
                    conflict["description"],
                ],
            )
            results.append(
                {
                    "id": cursor.lastrowid,
                    "allergy_id": allergy["id"],
                    "medication_id": med["id"],
                    "severity": conflict["severity"],
                    "conflict_description": conflict["description"],
                }
            )

    if results:
        connection.execute(
            """
            INSERT INTO clinical_audit_log(
                patient_profile_id, action_type, actor_type, actor_id, entity_type, details_json
            )
            VALUES (?, 'conflict_detected', 'system', 'allergy_conflict_engine', 'allergy_drug_conflict', ?)
            """,
            [patient_profile_id, json.dumps({"count": len(results)})],
        )

    connection.commit()
    return results


def suggest_icd10_codes(connection: sqlite3.Connection, patient_profile_id: int) -> list[dict[str, Any]]:
    diagnoses = _collect_text_values(connection, patient_profile_id, "diagnosis", "diagnoses_json")
    rules = {
        "hypertension": ("I10", "Essential (primary) hypertension", 0.94),
        "type 2 diabetes": ("E11", "Type 2 diabetes mellitus", 0.93),
        "asthma": ("J45.9", "Asthma, unspecified", 0.86),
    }
    _persist_code_suggestions(connection, patient_profile_id, "icd10", diagnoses, rules)
    return _get_pending_code_suggestions(connection, patient_profile_id, "icd10")


def suggest_cpt_codes(connection: sqlite3.Connection, patient_profile_id: int) -> list[dict[str, Any]]:
    procedures = _collect_text_values(connection, patient_profile_id, "procedure", "procedures_json")
    rules = {
        "office": ("99213", "Office or other outpatient visit", 0.91),
        "blood draw": ("36415", "Collection of venous blood by venipuncture", 0.83),
        "ekg": ("93000", "Electrocardiogram routine ECG", 0.84),
    }
    _persist_code_suggestions(connection, patient_profile_id, "cpt", procedures, rules)
    return _get_pending_code_suggestions(connection, patient_profile_id, "cpt")


def review_code_suggestion(
    connection: sqlite3.Connection,
    code_suggestion_id: int,
    action: str,
    reviewer_id: str,
    override_code: str | None = None,
    rejection_reason: str | None = None,
) -> bool:
    suggestion = connection.execute(
        "SELECT * FROM code_suggestions WHERE id = ?",
        [code_suggestion_id],
    ).fetchone()
    if not suggestion:
        return False

    new_status = "accepted" if action == "accept" else "rejected" if action == "reject" else "overridden"

    connection.execute(
        """
        UPDATE code_suggestions
        SET suggestion_status = ?, reviewer_id = ?, reviewed_at = CURRENT_TIMESTAMP,
            override_code = ?, rejection_reason = ?
        WHERE id = ?
        """,
        [new_status, reviewer_id, override_code, rejection_reason, code_suggestion_id],
    )

    connection.execute(
        """
        INSERT INTO code_review_actions(
            code_suggestion_id, reviewer_id, action, override_code, rejection_reason
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        [code_suggestion_id, reviewer_id, action, override_code, rejection_reason],
    )

    connection.execute(
        """
        INSERT INTO clinical_audit_log(
            patient_profile_id, action_type, actor_type, actor_id, entity_type, entity_id, details_json
        )
        VALUES (?, 'code_review', 'clinician', ?, 'code_suggestion', ?, ?)
        """,
        [
            suggestion["patient_profile_id"],
            reviewer_id,
            code_suggestion_id,
            json.dumps({"action": action, "override_code": override_code, "rejection_reason": rejection_reason}),
        ],
    )

    connection.commit()
    return True


def _persist_code_suggestions(
    connection: sqlite3.Connection,
    patient_profile_id: int,
    code_type: str,
    inputs: list[str],
    rules: dict[str, tuple[str, str, float]],
) -> list[dict[str, Any]]:
    persisted: list[dict[str, Any]] = []
    for value in inputs:
        normalized = value.lower()
        match = None
        for token, spec in rules.items():
            if token in normalized:
                match = spec
                break
        if not match:
            continue

        code_value, description, base_confidence = match
        confidence = round(max(0.75, min(0.97, base_confidence + random.uniform(-0.02, 0.02))), 2)
        threshold_result = apply_threshold(connection, code_type, confidence)
        review_required = 1 if threshold_result["review_required"] else 0
        auto_accepted = 1 if threshold_result["auto_accepted"] else 0
        suggestion_status = "accepted" if auto_accepted else "pending"

        existing = connection.execute(
            """
            SELECT id
            FROM code_suggestions
            WHERE patient_profile_id = ?
              AND code_type = ?
              AND code_value = ?
            """,
            [patient_profile_id, code_type, code_value],
        ).fetchone()
        if existing:
            continue

        cursor = connection.execute(
            """
            INSERT INTO code_suggestions(
                patient_profile_id,
                code_type,
                code_value,
                code_description,
                confidence_score,
                evidence_text,
                review_required,
                auto_accepted,
                suggestion_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                patient_profile_id,
                code_type,
                code_value,
                description,
                confidence,
                value,
                review_required,
                auto_accepted,
                suggestion_status,
            ],
        )
        persisted.append(
            {
                "id": cursor.lastrowid,
                "code_type": code_type,
                "code_value": code_value,
                "code_description": description,
                "confidence_score": confidence,
                "evidence_text": value,
                "review_required": review_required == 1,
                "auto_accepted": auto_accepted == 1,
                "suggestion_status": suggestion_status,
                "threshold": get_threshold_config(connection, code_type)["confidence_threshold"],
            }
        )

    connection.commit()
    return persisted


def _get_pending_code_suggestions(
    connection: sqlite3.Connection,
    patient_profile_id: int,
    code_type: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, patient_profile_id, code_type, code_value, code_description, confidence_score,
             evidence_text, review_required, auto_accepted, suggestion_status, reviewer_id, reviewed_at,
               override_code, rejection_reason, created_at
        FROM code_suggestions
        WHERE patient_profile_id = ? AND code_type = ? AND suggestion_status = 'pending'
        ORDER BY confidence_score DESC, created_at DESC
        """,
        [patient_profile_id, code_type],
    ).fetchall()
    return [dict(row) for row in rows]


def get_review_queue(connection: sqlite3.Connection, patient_profile_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, patient_profile_id, code_type, code_value, code_description, confidence_score,
               evidence_text, review_required, auto_accepted, suggestion_status, reviewer_id, reviewed_at,
               override_code, rejection_reason, created_at
        FROM code_suggestions
        WHERE patient_profile_id = ? AND review_required = 1 AND suggestion_status = 'pending'
        ORDER BY confidence_score ASC, created_at DESC
        """,
        [patient_profile_id],
    ).fetchall()
    return [dict(row) for row in rows]


def get_threshold_snapshot(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT code_type, confidence_threshold, updated_by, updated_at FROM code_threshold_config ORDER BY code_type ASC"
    ).fetchall()
    return [dict(row) for row in rows]


def _collect_text_values(
    connection: sqlite3.Connection,
    patient_profile_id: int,
    extracted_type: str,
    profile_column: str,
) -> list[str]:
    values: list[str] = []
    rows = connection.execute(
        """
        SELECT entity_value
        FROM extracted_entities
        WHERE patient_profile_id = ? AND entity_type = ?
        """,
        [patient_profile_id, extracted_type],
    ).fetchall()
    values.extend([row["entity_value"] for row in rows])

    profile = connection.execute(
        f"SELECT {profile_column} FROM clinical_profile WHERE patient_profile_id = ?",
        [patient_profile_id],
    ).fetchone()
    if profile and profile[profile_column]:
        for item in json.loads(profile[profile_column]):
            values.append(str(item.get("entity_value", "")))

    return [value for value in values if value]


def _match_medication_conflict(medication_1: str, medication_2: str) -> dict[str, str] | None:
    left = medication_1.lower()
    right = medication_2.lower()
    pair = {left, right}

    if any("warfarin" in value for value in pair) and any("aspirin" in value for value in pair):
        return {
            "conflict_type": "interaction",
            "severity": "high",
            "description": "Warfarin with aspirin may increase bleeding risk.",
        }

    if any("metformin" in value for value in pair) and any("contrast" in value for value in pair):
        return {
            "conflict_type": "interaction",
            "severity": "medium",
            "description": "Metformin with contrast exposure requires renal monitoring.",
        }

    if left == right:
        return {
            "conflict_type": "duplicate_therapy",
            "severity": "low",
            "description": "Duplicate therapy appears in the current medication list.",
        }

    return None


def _match_allergy_conflict(allergy: str, medication: str) -> dict[str, str] | None:
    allergy_lower = allergy.lower()
    medication_lower = medication.lower()

    if "penicillin" in allergy_lower and any(token in medication_lower for token in ("amoxicillin", "penicillin")):
        return {
            "severity": "high",
            "description": "Penicillin allergy conflicts with prescribed penicillin-class medication.",
        }

    if "sulfa" in allergy_lower and "sulfamethoxazole" in medication_lower:
        return {
            "severity": "high",
            "description": "Sulfa allergy conflicts with sulfonamide medication.",
        }

    return None


def _dedupe_entities(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for item in values:
        value = str(item.get("entity_value", "")).strip()
        if not value:
            continue
        key = value.lower()
        existing = selected.get(key)
        if not existing:
            selected[key] = item
            continue
        if _source_rank(item.get("source_type")) < _source_rank(existing.get("source_type")):
            selected[key] = item
        elif (item.get("confidence_score") or 0) > (existing.get("confidence_score") or 0):
            selected[key] = item
    return list(selected.values())


def _source_rank(source_type: Any) -> int:
    if source_type == "intake":
        return 0
    if source_type == "document":
        return 1
    return 2


def _json_list(row: sqlite3.Row | None, key: str) -> list[dict[str, Any]]:
    if not row:
        return []
    raw = row[key] if key in row.keys() else None
    if not raw:
        return []
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, list) else []
