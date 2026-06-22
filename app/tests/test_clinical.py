from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.clinical_service import (
    aggregate_patient_profile,
    detect_allergy_drug_conflicts,
    detect_medication_conflicts,
    get_patient_profile as get_clinical_profile,
    review_code_suggestion,
    suggest_cpt_codes,
    suggest_icd10_codes,
)
from src.db import get_connection, initialize_database
from src.document_service import (
    get_document_status,
    get_patient_documents,
    process_document,
    upload_document,
)


class TestClinicalIntelligence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "clinical.db"
        initialize_database(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.temp_dir.cleanup()
        except PermissionError:
            pass

    def setUp(self):
        self.connection = get_connection(self.__class__.db_path)
        self.connection.execute("DELETE FROM clinical_documents")
        self.connection.execute("DELETE FROM extracted_entities")
        self.connection.execute("DELETE FROM medication_conflicts")
        self.connection.execute("DELETE FROM allergy_drug_conflicts")
        self.connection.execute("DELETE FROM code_review_actions")
        self.connection.execute("DELETE FROM code_suggestions")
        self.connection.execute("DELETE FROM clinical_audit_log")
        self.connection.commit()

    def tearDown(self):
        self.connection.close()

    def test_upload_document_success(self):
        result = upload_document(self.connection, 1, "visit-note.pdf", "pdf", 2048)
        self.assertIn("document_id", result)
        self.assertEqual(result["upload_status"], "uploaded")

    def test_upload_document_invalid_type(self):
        with self.assertRaises(ValueError):
            upload_document(self.connection, 1, "notes.txt", "txt")

    def test_process_document_extraction(self):
        uploaded = upload_document(self.connection, 1, "allergy-note.pdf", "pdf")
        processed = process_document(self.connection, uploaded["document_id"])
        self.assertEqual(processed["upload_status"], "complete")
        self.assertGreater(processed["entities_extracted"], 0)

    def test_detect_medication_conflicts(self):
        self.connection.execute(
            "INSERT INTO extracted_entities(patient_profile_id, entity_type, entity_value, confidence_score, source_type) VALUES (1, 'medication', 'Warfarin', 0.9, 'document')"
        )
        self.connection.execute(
            "INSERT INTO extracted_entities(patient_profile_id, entity_type, entity_value, confidence_score, source_type) VALUES (1, 'medication', 'Aspirin', 0.91, 'document')"
        )
        self.connection.commit()

        conflicts = detect_medication_conflicts(self.connection, 1)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["severity"], "high")

    def test_detect_allergy_drug_conflicts(self):
        self.connection.execute(
            "INSERT INTO extracted_entities(patient_profile_id, entity_type, entity_value, confidence_score, source_type) VALUES (1, 'allergy', 'Penicillin', 0.95, 'document')"
        )
        self.connection.execute(
            "INSERT INTO extracted_entities(patient_profile_id, entity_type, entity_value, confidence_score, source_type) VALUES (1, 'medication', 'Amoxicillin', 0.89, 'document')"
        )
        self.connection.commit()

        conflicts = detect_allergy_drug_conflicts(self.connection, 1)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["severity"], "high")

    def test_suggest_icd10_codes(self):
        self.connection.execute(
            "INSERT INTO extracted_entities(patient_profile_id, entity_type, entity_value, confidence_score, source_type) VALUES (1, 'diagnosis', 'Type 2 Diabetes', 0.92, 'document')"
        )
        self.connection.commit()
        suggestions = suggest_icd10_codes(self.connection, 1)
        self.assertTrue(any(item["code_value"] == "E11" for item in suggestions))

    def test_suggest_cpt_codes(self):
        self.connection.execute(
            "INSERT INTO extracted_entities(patient_profile_id, entity_type, entity_value, confidence_score, source_type) VALUES (1, 'procedure', 'Office follow-up visit', 0.9, 'document')"
        )
        self.connection.commit()
        suggestions = suggest_cpt_codes(self.connection, 1)
        self.assertTrue(any(item["code_value"] == "99213" for item in suggestions))

    def test_aggregate_patient_profile(self):
        self.connection.execute(
            "INSERT INTO extracted_entities(patient_profile_id, entity_type, entity_value, confidence_score, source_type) VALUES (1, 'diagnosis', 'Asthma', 0.86, 'document')"
        )
        self.connection.commit()
        profile = aggregate_patient_profile(self.connection, 1)
        self.assertIn("diagnoses", profile)
        self.assertTrue(any(item["entity_value"] == "Asthma" for item in profile["diagnoses"]))

    def test_get_clinical_profile(self):
        profile = get_clinical_profile(self.connection, 1)
        self.assertIn("medications", profile)
        self.assertIn("allergies", profile)
        self.assertIn("diagnoses", profile)

    def test_review_code_suggestion_accept(self):
        self.connection.execute(
            """
            INSERT INTO code_suggestions(patient_profile_id, code_type, code_value, code_description, confidence_score)
            VALUES (1, 'icd10', 'I10', 'Essential (primary) hypertension', 0.95)
            """
        )
        suggestion_id = self.connection.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        self.connection.commit()

        success = review_code_suggestion(self.connection, suggestion_id, "accept", "coder-1")
        self.assertTrue(success)

        row = self.connection.execute("SELECT suggestion_status FROM code_suggestions WHERE id = ?", [suggestion_id]).fetchone()
        self.assertEqual(row["suggestion_status"], "accepted")

    def test_review_code_suggestion_override(self):
        self.connection.execute(
            """
            INSERT INTO code_suggestions(patient_profile_id, code_type, code_value, code_description, confidence_score)
            VALUES (1, 'icd10', 'I10', 'Essential (primary) hypertension', 0.75)
            """
        )
        suggestion_id = self.connection.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        self.connection.commit()

        success = review_code_suggestion(
            self.connection,
            suggestion_id,
            "override",
            "coder-2",
            override_code="I15.9",
        )
        self.assertTrue(success)

        row = self.connection.execute("SELECT suggestion_status FROM code_suggestions WHERE id = ?", [suggestion_id]).fetchone()
        self.assertEqual(row["suggestion_status"], "overridden")

    def test_get_patient_documents(self):
        upload_document(self.connection, 1, "doc1.pdf", "pdf")
        upload_document(self.connection, 1, "doc2.docx", "docx")
        docs = get_patient_documents(self.connection, 1)
        self.assertEqual(len(docs), 2)

    def test_get_document_status(self):
        uploaded = upload_document(self.connection, 1, "status-test.pdf", "pdf")
        status = get_document_status(self.connection, uploaded["document_id"])
        self.assertIsNotNone(status)
        self.assertEqual(status["file_type"], "pdf")


if __name__ == "__main__":
    unittest.main()
