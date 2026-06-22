from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "db" / "appointments.db"
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    target = db_path or DEFAULT_DB_PATH
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def initialize_database(db_path: Path | None = None) -> None:
    target = db_path or DEFAULT_DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(target) as connection:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        connection.executescript(schema_sql)
        _seed_if_empty(connection)
        _seed_supporting_records(connection)
        _migrate_clinical_schema(connection)


def _seed_if_empty(connection: sqlite3.Connection) -> None:
    existing = connection.execute("SELECT COUNT(*) AS count FROM appointments").fetchone()["count"]
    if existing > 0:
        return

    specialties = [
        (1, "Cardiology"),
        (2, "Dermatology"),
        (3, "General Medicine"),
        (4, "Neurology"),
        (5, "Orthopedics"),
        (6, "Pediatrics"),
    ]
    providers = [
        (
            1,
            "Dr. Ava Patel",
            "MD",
            1,
            "https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&w=640&q=80",
            184,
            "Heart rhythm specialist focused on preventive care and same-week access.",
        ),
        (
            2,
            "Dr. Lucas Kim",
            "MD",
            2,
            "https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?auto=format&fit=crop&w=640&q=80",
            126,
            "Dermatology lead with fast virtual follow-up and procedural consults.",
        ),
        (
            3,
            "Dr. Nora Singh",
            "DO",
            3,
            "https://images.unsplash.com/photo-1594824476967-48c8b964273f?auto=format&fit=crop&w=640&q=80",
            241,
            "Primary care physician coordinating preventive visits and chronic care plans.",
        ),
        (
            4,
            "Dr. Ethan Brooks",
            "MD",
            4,
            "https://images.unsplash.com/photo-1622253692010-333f2da6031d?auto=format&fit=crop&w=640&q=80",
            98,
            "Neurology consultant specializing in migraine, balance, and diagnostic reviews.",
        ),
        (
            5,
            "Dr. Mia Chen",
            "MD",
            5,
            "https://images.unsplash.com/photo-1651008376811-b90baee60c1f?auto=format&fit=crop&w=640&q=80",
            153,
            "Orthopedics surgeon focused on sports injuries, joint pain, and rehab planning.",
        ),
        (
            6,
            "Dr. Sophia Diaz",
            "MD",
            6,
            "https://images.unsplash.com/photo-1614436163996-25cee5f54290?auto=format&fit=crop&w=640&q=80",
            211,
            "Pediatrics physician with extended family scheduling and vaccine counseling.",
        ),
    ]
    locations = [
        "Downtown Clinic",
        "Northside Care Center",
        "Lakeside Medical Pavilion",
    ]

    connection.executemany(
        "INSERT INTO specialties(id, name, is_active) VALUES (?, ?, 1)", specialties
    )
    connection.executemany(
        """
        INSERT INTO providers(
            id,
            name,
            credentials,
            specialty_id,
            photo_url,
            review_count,
            bio,
            is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """,
        providers,
    )

    random.seed(42)
    slots = []
    slot_id = 1
    start_day = date.today()
    time_blocks = [
        ("08:30", "09:00"),
        ("12:30", "13:00"),
        ("17:30", "18:00"),
    ]

    for offset in range(0, 45):
        day_value = (start_day + timedelta(days=offset)).isoformat()
        for provider_id, _name, _credentials, specialty_id, _photo_url, _review_count, _bio in providers:
            for start_time, end_time in time_blocks:
                status = "available" if random.random() > 0.15 else "booked"
                slots.append(
                    (
                        slot_id,
                        provider_id,
                        specialty_id,
                        day_value,
                        start_time,
                        end_time,
                        random.choice(locations),
                        status,
                    )
                )
                slot_id += 1

    connection.executemany(
        """
        INSERT INTO appointments(
            id,
            provider_id,
            specialty_id,
            appointment_date,
            start_time,
            end_time,
            location,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        slots,
    )
    connection.commit()


def _seed_supporting_records(connection: sqlite3.Connection) -> None:
    import json

    patient_exists = connection.execute(
        "SELECT COUNT(*) AS count FROM patient_profiles WHERE id = 1"
    ).fetchone()["count"]
    if patient_exists == 0:
        connection.execute(
            """
            INSERT INTO patient_profiles(
                id,
                first_name,
                last_name,
                email,
                phone,
                preferred_timezone,
                reminder_channels,
                do_not_disturb
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                1,
                "Alex",
                "Morgan",
                "alex.morgan@example.com",
                "+1-312-555-0186",
                "America/Chicago",
                '["sms", "email"]',
            ),
        )

    session_exists = connection.execute(
        "SELECT COUNT(*) AS count FROM patient_sessions WHERE patient_profile_id = 1"
    ).fetchone()["count"]
    if session_exists == 0:
        connection.execute(
            """
            INSERT INTO patient_sessions(
                patient_profile_id,
                google_auth_status,
                outlook_auth_status
            )
            VALUES (?, 'revoked', 'revoked')
            """,
            (1,),
        )

    clinical_profile_exists = connection.execute(
        "SELECT COUNT(*) AS count FROM clinical_profile WHERE patient_profile_id = 1"
    ).fetchone()["count"]
    if clinical_profile_exists == 0:
        connection.execute(
            """
            INSERT INTO clinical_profile(
                patient_profile_id,
                medications_json,
                allergies_json,
                diagnoses_json,
                procedures_json,
                vitals_json,
                lab_results_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                json.dumps(
                    [
                        {"entity_value": "Lisinopril 10mg daily", "confidence_score": 0.92, "source_type": "intake"},
                        {"entity_value": "Metformin 500mg twice daily", "confidence_score": 0.88, "source_type": "intake"},
                    ]
                ),
                json.dumps(
                    [
                        {"entity_value": "Penicillin", "confidence_score": 0.95, "source_type": "intake"},
                    ]
                ),
                json.dumps(
                    [
                        {"entity_value": "Type 2 Diabetes", "confidence_score": 0.90, "source_type": "intake"},
                        {"entity_value": "Hypertension", "confidence_score": 0.88, "source_type": "intake"},
                    ]
                ),
                json.dumps(
                    [
                        {"entity_value": "Office follow-up visit", "confidence_score": 0.85, "source_type": "intake"},
                    ]
                ),
                json.dumps(
                    [
                        {"entity_value": "BP 140/90", "confidence_score": 0.92, "source_type": "intake"},
                        {"entity_value": "HR 72", "confidence_score": 0.91, "source_type": "intake"},
                    ]
                ),
                json.dumps(
                    [
                        {"entity_value": "Glucose 145", "confidence_score": 0.89, "source_type": "intake"},
                    ]
                ),
            ),
        )

    for code_type in ("icd10", "cpt"):
        threshold_exists = connection.execute(
            "SELECT COUNT(*) AS count FROM code_threshold_config WHERE code_type = ?",
            (code_type,),
        ).fetchone()["count"]
        if threshold_exists == 0:
            connection.execute(
                """
                INSERT INTO code_threshold_config(code_type, confidence_threshold, updated_by)
                VALUES (?, ?, ?)
                """,
                (code_type, 0.70, "system"),
            )

    provider_rows = connection.execute("SELECT id FROM providers").fetchall()
    for provider in provider_rows:
        for calendar_type in ("google", "outlook"):
            exists = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM provider_calendar_state
                WHERE provider_id = ? AND calendar_type = ?
                """,
                (provider["id"], calendar_type),
            ).fetchone()["count"]
            if exists == 0:
                connection.execute(
                    """
                    INSERT INTO provider_calendar_state(provider_id, calendar_type, webhook_enabled)
                    VALUES (?, ?, 0)
                    """,
                    (provider["id"], calendar_type),
                )

    connection.commit()


def _migrate_clinical_schema(connection: sqlite3.Connection) -> None:
    def ensure_column(table_name: str, column_name: str, column_sql: str) -> None:
        existing_columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in existing_columns:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")

    ensure_column("medication_conflicts", "resolution_status", "resolution_status TEXT NOT NULL DEFAULT 'unresolved'")
    ensure_column("medication_conflicts", "resolution_action", "resolution_action TEXT")
    ensure_column("medication_conflicts", "resolution_notes", "resolution_notes TEXT")
    ensure_column("medication_conflicts", "resolved_by", "resolved_by TEXT")
    ensure_column("medication_conflicts", "resolved_at", "resolved_at TEXT")

    ensure_column("allergy_drug_conflicts", "resolution_status", "resolution_status TEXT NOT NULL DEFAULT 'unresolved'")
    ensure_column("allergy_drug_conflicts", "resolution_action", "resolution_action TEXT")
    ensure_column("allergy_drug_conflicts", "resolution_notes", "resolution_notes TEXT")
    ensure_column("allergy_drug_conflicts", "resolved_by", "resolved_by TEXT")
    ensure_column("allergy_drug_conflicts", "resolved_at", "resolved_at TEXT")

    ensure_column("code_suggestions", "auto_accepted", "auto_accepted INTEGER NOT NULL DEFAULT 0")
