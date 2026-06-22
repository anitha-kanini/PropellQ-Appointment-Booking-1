from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

SUPPORTED_TYPES = {"pdf", "docx"}


def upload_document(
    connection: sqlite3.Connection,
    patient_profile_id: int,
    file_name: str,
    file_type: str,
    file_size_bytes: int | None = None,
) -> dict[str, Any]:
    normalized_type = file_type.lower().strip()
    if normalized_type not in SUPPORTED_TYPES:
        raise ValueError("Unsupported file type. Supported types are PDF and DOCX.")

    storage_path = str(Path("clinical_uploads") / f"{patient_profile_id}" / file_name)
    cursor = connection.execute(
        """
        INSERT INTO clinical_documents(
            patient_profile_id,
            file_name,
            file_type,
            storage_path,
            file_size_bytes,
            upload_status,
            extraction_version
        )
        VALUES (?, ?, ?, ?, ?, 'uploaded', 'v1-mock')
        """,
        [patient_profile_id, file_name, normalized_type, storage_path, file_size_bytes],
    )

    connection.execute(
        """
        INSERT INTO clinical_audit_log(
            patient_profile_id,
            action_type,
            actor_type,
            actor_id,
            entity_type,
            entity_id,
            details_json
        )
        VALUES (?, 'document_upload', 'patient', 'patient_portal', 'document', ?, ?)
        """,
        [
            patient_profile_id,
            cursor.lastrowid,
            json.dumps({"file_name": file_name, "file_type": normalized_type, "size": file_size_bytes}),
        ],
    )

    connection.commit()
    return {
        "document_id": cursor.lastrowid,
        "patient_profile_id": patient_profile_id,
        "file_name": file_name,
        "file_type": normalized_type,
        "upload_status": "uploaded",
    }


def process_document(connection: sqlite3.Connection, document_id: int) -> dict[str, Any]:
    document = connection.execute(
        "SELECT * FROM clinical_documents WHERE id = ?",
        [document_id],
    ).fetchone()
    if not document:
        raise ValueError("Document not found")

    connection.execute(
        "UPDATE clinical_documents SET upload_status = 'processing' WHERE id = ?",
        [document_id],
    )

    entities = _simulate_extraction(document["file_name"])
    extracted_count = 0
    now = datetime.utcnow().isoformat() + "Z"

    for entity in entities:
        connection.execute(
            """
            INSERT INTO extracted_entities(
                patient_profile_id,
                document_id,
                entity_type,
                entity_value,
                confidence_score,
                source_type,
                source_id,
                evidence_text,
                extraction_model,
                extracted_at
            )
            VALUES (?, ?, ?, ?, ?, 'document', ?, ?, 'mock-clinical-nlp-v1', ?)
            """,
            [
                document["patient_profile_id"],
                document_id,
                entity["entity_type"],
                entity["entity_value"],
                entity["confidence_score"],
                f"doc:{document_id}",
                entity.get("evidence_text", entity["entity_value"]),
                now,
            ],
        )
        extracted_count += 1

    connection.execute(
        """
        UPDATE clinical_documents
        SET upload_status = 'complete', extracted_at = ?, processing_error = NULL
        WHERE id = ?
        """,
        [now, document_id],
    )

    connection.execute(
        """
        INSERT INTO clinical_audit_log(
            patient_profile_id,
            action_type,
            actor_type,
            actor_id,
            entity_type,
            entity_id,
            details_json
        )
        VALUES (?, 'extraction', 'system', 'document_processor', 'document', ?, ?)
        """,
        [
            document["patient_profile_id"],
            document_id,
            json.dumps({"entities_extracted": extracted_count}),
        ],
    )

    connection.commit()
    return {
        "document_id": document_id,
        "upload_status": "complete",
        "entities_extracted": extracted_count,
    }


def get_document_status(connection: sqlite3.Connection, document_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT id, patient_profile_id, file_name, file_type, upload_status, processing_error, extracted_at, upload_timestamp
        FROM clinical_documents
        WHERE id = ?
        """,
        [document_id],
    ).fetchone()
    if not row:
        return None
    return dict(row)


def get_patient_documents(connection: sqlite3.Connection, patient_profile_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, file_name, file_type, file_size_bytes, upload_status, processing_error, extracted_at, upload_timestamp
        FROM clinical_documents
        WHERE patient_profile_id = ?
        ORDER BY upload_timestamp DESC, id DESC
        """,
        [patient_profile_id],
    ).fetchall()
    return [dict(row) for row in rows]


def _simulate_extraction(file_name: str) -> list[dict[str, Any]]:
    lower = file_name.lower()
    base = [
        {
            "entity_type": "medication",
            "entity_value": "Aspirin 81mg daily",
            "confidence_score": 0.87,
            "evidence_text": "Medication list includes aspirin 81mg daily.",
        },
        {
            "entity_type": "diagnosis",
            "entity_value": "Hypertension",
            "confidence_score": 0.91,
            "evidence_text": "Assessment lists chronic hypertension.",
        },
        {
            "entity_type": "procedure",
            "entity_value": "Office follow-up visit",
            "confidence_score": 0.82,
            "evidence_text": "Plan includes office follow-up in 3 months.",
        },
    ]

    if "allergy" in lower:
        base.append(
            {
                "entity_type": "allergy",
                "entity_value": "Penicillin",
                "confidence_score": 0.93,
                "evidence_text": "Allergy list notes penicillin reaction.",
            }
        )

    if "lab" in lower:
        base.append(
            {
                "entity_type": "lab_result",
                "entity_value": "Glucose 145 mg/dL",
                "confidence_score": 0.85,
                "evidence_text": "Recent lab shows glucose 145.",
            }
        )

    return base
