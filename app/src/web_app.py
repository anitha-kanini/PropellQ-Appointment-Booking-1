from __future__ import annotations

import json
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import parse_qs

from src.booking_service import (
    authorize_provider,
    build_calendar_payload,
    complete_provider_authorization,
    create_checkout_reservation,
    dashboard_metrics,
    disconnect_provider,
    finalize_booking,
    get_appointment_details,
    get_integration_state,
    get_patient_profile,
    process_calendar_sync_queue,
    process_confirmation_queue,
    process_due_reminders,
    process_preferred_swaps,
    run_pull_reconciliation,
)
from src.clinical_service import (
    aggregate_patient_profile,
    detect_allergy_drug_conflicts,
    detect_medication_conflicts,
    get_patient_profile as get_clinical_profile,
    get_review_queue,
    get_threshold_snapshot,
    review_code_suggestion,
    suggest_cpt_codes,
    suggest_icd10_codes,
)
from src.db import DEFAULT_DB_PATH, initialize_database, get_connection
from src.conflict_service import get_unresolved_conflicts, resolve_conflict
from src.document_service import (
    get_document_status,
    get_patient_documents,
    process_document,
    upload_document,
)
from src.threshold_service import get_threshold_config, get_threshold_history, update_threshold_config
from src.search_service import (
    book_appointment,
    get_provider,
    list_specialties,
    parse_filters,
    search_appointments,
    suggest_providers,
)

BASE_DIR = Path(__file__).resolve().parents[1]
PUBLIC_DIR = BASE_DIR / "public"


@dataclass
class SearchMetrics:
    total_queries: int = 0
    empty_results: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    def record(self, latency_ms: float, result_count: int) -> None:
        self.total_queries += 1
        if result_count == 0:
            self.empty_results += 1
        self.latencies_ms.append(latency_ms)
        if len(self.latencies_ms) > 2000:
            self.latencies_ms = self.latencies_ms[-1000:]

    def snapshot(self) -> dict[str, Any]:
        if not self.latencies_ms:
            return {
                "totalQueries": self.total_queries,
                "emptyResults": self.empty_results,
                "emptyResultRate": 0,
                "p95LatencyMs": 0,
                "averageLatencyMs": 0,
                "alertBreached": False,
            }

        ordered = sorted(self.latencies_ms)
        p95_index = max(0, int(len(ordered) * 0.95) - 1)
        p95 = round(ordered[p95_index], 2)
        avg = round(sum(self.latencies_ms) / len(self.latencies_ms), 2)
        empty_rate = round((self.empty_results / max(1, self.total_queries)) * 100, 2)

        return {
            "totalQueries": self.total_queries,
            "emptyResults": self.empty_results,
            "emptyResultRate": empty_rate,
            "p95LatencyMs": p95,
            "averageLatencyMs": avg,
            "alertBreached": p95 > 2000,
        }


def create_app(db_path: Path | None = None):
    selected_db = db_path or DEFAULT_DB_PATH
    initialize_database(selected_db)
    metrics = SearchMetrics()

    def app(environ, start_response):
        started_at = perf_counter()
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")

        if method == "GET" and path == "/api/appointments/search":
            return _handle_search(environ, start_response, selected_db, metrics, started_at)

        if method == "GET" and path == "/api/appointments/specialties":
            return _handle_specialties(start_response, selected_db)

        if method == "GET" and path == "/api/providers/suggest":
            return _handle_provider_suggest(environ, start_response, selected_db)

        if method == "GET" and path == "/api/appointments/calendar":
            return _handle_calendar(environ, start_response, selected_db)

        appointment_match = re.match(r"^/api/appointments/(\d+)$", path)
        if method == "GET" and appointment_match:
            return _handle_appointment_details(start_response, selected_db, int(appointment_match.group(1)))

        provider_match = re.match(r"^/api/providers/(\d+)$", path)
        if method == "GET" and provider_match:
            return _handle_provider_details(start_response, selected_db, int(provider_match.group(1)))

        checkout_match = re.match(r"^/api/appointments/(\d+)/checkout$", path)
        if method == "POST" and checkout_match:
            return _handle_checkout(environ, start_response, selected_db, int(checkout_match.group(1)))

        if method == "POST" and path == "/api/appointments/book":
            return _handle_finalize_booking(environ, start_response, selected_db)

        book_match = re.match(r"^/api/appointments/(\d+)/book$", path)
        if method == "POST" and book_match:
            return _handle_book_appointment(start_response, selected_db, int(book_match.group(1)))

        if method == "GET" and path == "/api/patient/profile":
            return _handle_patient_profile(start_response, selected_db)

        if method == "GET" and path == "/api/integrations/status":
            return _handle_integration_status(start_response, selected_db)

        auth_authorize_match = re.match(r"^/api/auth/(google|outlook)/authorize$", path)
        if method == "GET" and auth_authorize_match:
            return _handle_auth_authorize(start_response, selected_db, auth_authorize_match.group(1))

        auth_callback_match = re.match(r"^/api/auth/(google|outlook)/callback$", path)
        if method == "GET" and auth_callback_match:
            return _handle_auth_callback(environ, start_response, selected_db, auth_callback_match.group(1))

        auth_disconnect_match = re.match(r"^/api/auth/(google|outlook)/disconnect$", path)
        if method == "POST" and auth_disconnect_match:
            return _handle_auth_disconnect(start_response, selected_db, auth_disconnect_match.group(1))

        if method == "POST" and path == "/api/jobs/process-confirmations":
            return _handle_process_confirmations(start_response, selected_db)

        if method == "POST" and path == "/api/jobs/process-reminders":
            return _handle_process_reminders(start_response, selected_db)

        if method == "POST" and path == "/api/jobs/process-swaps":
            return _handle_process_swaps(start_response, selected_db)

        if method == "POST" and path == "/api/jobs/process-calendar-sync":
            return _handle_process_calendar_sync(start_response, selected_db)

        if method == "POST" and path == "/api/jobs/reconcile-calendar-sync":
            return _handle_reconcile_sync(start_response, selected_db)

        if method == "GET" and path == "/api/dashboard/metrics":
            return _handle_dashboard_metrics(start_response, selected_db)

        if method == "GET" and path == "/api/metrics/search":
            return _json_response(start_response, 200, {"success": True, "data": metrics.snapshot()})

        document_status_match = re.match(r"^/api/documents/(\d+)/status$", path)
        if method == "GET" and document_status_match:
            return _handle_document_status(start_response, selected_db, int(document_status_match.group(1)))

        if method == "POST" and path == "/api/documents/upload":
            return _handle_document_upload(environ, start_response, selected_db)

        if method == "GET" and path == "/api/clinical/documents":
            return _handle_list_documents(environ, start_response, selected_db)

        if method == "GET" and path == "/api/clinical/profile":
            return _handle_clinical_profile(environ, start_response, selected_db)

        if method == "GET" and path == "/api/clinical/review-queue":
            return _handle_review_queue(environ, start_response, selected_db)

        if method == "GET" and path == "/api/clinical/conflicts":
            return _handle_conflict_queue(environ, start_response, selected_db)

        if method == "GET" and path == "/api/clinical/thresholds":
            return _handle_threshold_snapshot(start_response, selected_db)

        if method == "POST" and path == "/api/clinical/thresholds":
            return _handle_threshold_update(environ, start_response, selected_db)

        if method == "GET" and path == "/api/clinical/thresholds/history":
            return _handle_threshold_history(environ, start_response, selected_db)

        if method == "POST" and path == "/api/clinical/extract":
            return _handle_extract_document(environ, start_response, selected_db)

        if method == "POST" and path == "/api/clinical/aggregate":
            return _handle_aggregate_profile(environ, start_response, selected_db)

        if method == "POST" and path == "/api/clinical/detect-conflicts":
            return _handle_detect_conflicts(environ, start_response, selected_db)

        if method == "POST" and path == "/api/clinical/suggest-codes":
            return _handle_suggest_codes(environ, start_response, selected_db)

        if method == "POST" and path == "/api/clinical/review-code":
            return _handle_review_code(environ, start_response, selected_db)

        conflict_resolve_match = re.match(r"^/api/conflicts/(\d+)/resolve$", path)
        if method == "POST" and conflict_resolve_match:
            return _handle_conflict_resolve(environ, start_response, selected_db, int(conflict_resolve_match.group(1)))

        if path.startswith("/api/"):
            return _json_response(
                start_response,
                404,
                {
                    "success": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "API route not found",
                    },
                },
            )

        return _serve_static(path, start_response)

    return app


def _handle_search(environ, start_response, db_path: Path, metrics: SearchMetrics, started_at: float):
    query_params = _flat_query_params(environ.get("QUERY_STRING", ""))

    with get_connection(db_path) as connection:
        validated = parse_filters(query_params, connection)
        if validated.errors:
            return _json_response(
                start_response,
                400,
                {
                    "success": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid search parameters",
                        "details": validated.errors,
                    },
                },
            )

        results = search_appointments(connection, validated.data)

    elapsed_ms = (perf_counter() - started_at) * 1000
    metrics.record(elapsed_ms, len(results["items"]))

    return _json_response(
        start_response,
        200,
        {
            "success": True,
            "data": results,
            "meta": {
                "latencyMs": round(elapsed_ms, 2),
            },
        },
    )


def _handle_specialties(start_response, db_path: Path):
    with get_connection(db_path) as connection:
        rows = list_specialties(connection)
    return _json_response(start_response, 200, {"success": True, "data": rows})


def _handle_provider_suggest(environ, start_response, db_path: Path):
    params = _flat_query_params(environ.get("QUERY_STRING", ""))
    query = (params.get("query") or "").strip()
    if len(query) < 2:
        return _json_response(start_response, 200, {"success": True, "data": []})

    with get_connection(db_path) as connection:
        rows = suggest_providers(connection, query)
    return _json_response(start_response, 200, {"success": True, "data": rows})


def _handle_calendar(environ, start_response, db_path: Path):
    query_params = _flat_query_params(environ.get("QUERY_STRING", ""))
    with get_connection(db_path) as connection:
        validated = parse_filters(query_params, connection)
        if validated.errors:
            return _json_response(
                start_response,
                400,
                {
                    "success": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid calendar parameters",
                        "details": validated.errors,
                    },
                },
            )
        data = build_calendar_payload(
            connection,
            validated.data,
            query_params.get("view", "month"),
            query_params.get("anchorDate"),
        )
    return _json_response(start_response, 200, {"success": True, "data": data})


def _handle_appointment_details(start_response, db_path: Path, appointment_id: int):
    with get_connection(db_path) as connection:
        data = get_appointment_details(connection, appointment_id)
    if data is None:
        return _json_response(
            start_response,
            404,
            {"success": False, "error": {"code": "APPOINTMENT_NOT_FOUND", "message": "Appointment not found"}},
        )
    return _json_response(start_response, 200, {"success": True, "data": data})


def _handle_provider_details(start_response, db_path: Path, provider_id: int):
    with get_connection(db_path) as connection:
        data = get_provider(connection, provider_id)

    if data is None:
        return _json_response(
            start_response,
            404,
            {
                "success": False,
                "error": {
                    "code": "PROVIDER_NOT_FOUND",
                    "message": "Provider not found",
                },
            },
        )

    return _json_response(start_response, 200, {"success": True, "data": data})


def _handle_book_appointment(start_response, db_path: Path, appointment_id: int):
    with get_connection(db_path) as connection:
        booked = book_appointment(connection, appointment_id)

    if not booked:
        return _json_response(
            start_response,
            409,
            {
                "success": False,
                "error": {
                    "code": "UNAVAILABLE_SLOT",
                    "message": "Selected appointment slot is no longer available",
                },
            },
        )

    return _json_response(
        start_response,
        200,
        {"success": True, "data": {"appointmentId": appointment_id, "status": "booked"}},
    )


def _handle_checkout(environ, start_response, db_path: Path, appointment_id: int):
    payload = _read_json_body(environ)
    with get_connection(db_path) as connection:
        status_code, data = create_checkout_reservation(connection, appointment_id, payload)
    success = status_code == 200
    return _json_response(
        start_response,
        status_code,
        {"success": success, "data": data} if success else {"success": False, "error": data},
    )


def _handle_finalize_booking(environ, start_response, db_path: Path):
    payload = _read_json_body(environ)
    reservation_token = payload.get("reservationToken")
    if not reservation_token:
        return _json_response(
            start_response,
            400,
            {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "reservationToken is required"}},
        )
    with get_connection(db_path) as connection:
        status_code, data = finalize_booking(connection, reservation_token, payload)
    success = status_code == 200
    return _json_response(
        start_response,
        status_code,
        {"success": success, "data": data} if success else {"success": False, "error": data},
    )


def _handle_patient_profile(start_response, db_path: Path):
    with get_connection(db_path) as connection:
        profile = get_patient_profile(connection)
    return _json_response(start_response, 200, {"success": True, "data": profile})


def _handle_integration_status(start_response, db_path: Path):
    with get_connection(db_path) as connection:
        data = get_integration_state(connection)
    return _json_response(start_response, 200, {"success": True, "data": data})


def _handle_auth_authorize(start_response, db_path: Path, provider: str):
    with get_connection(db_path) as connection:
        redirect_url = authorize_provider(connection, provider)
    return _json_response(
        start_response,
        200,
        {
            "success": True,
            "data": {
                "provider": provider,
                "authorizeUrl": redirect_url,
                "message": f"PropellQ will request access to manage your {provider.title()} calendar events.",
            },
        },
    )


def _handle_auth_callback(environ, start_response, db_path: Path, provider: str):
    params = _flat_query_params(environ.get("QUERY_STRING", ""))
    with get_connection(db_path) as connection:
        success, state = complete_provider_authorization(
            connection,
            provider,
            params.get("state", ""),
            params.get("code"),
            params.get("error"),
        )
        integration = get_integration_state(connection)
    if success:
        return _json_response(
            start_response,
            200,
            {
                "success": True,
                "data": {
                    "provider": provider,
                    "status": state,
                    "integration": integration,
                    "message": f"{provider.title()} Calendar connected! Appointments will be added automatically.",
                },
            },
        )
    return _json_response(
        start_response,
        400,
        {
            "success": False,
            "error": {
                "code": state.upper(),
                "message": f"{provider.title()} Calendar authorization failed. Please try again or contact support.",
            },
        },
    )


def _handle_auth_disconnect(start_response, db_path: Path, provider: str):
    with get_connection(db_path) as connection:
        disconnect_provider(connection, provider)
        integration = get_integration_state(connection)
    return _json_response(
        start_response,
        200,
        {"success": True, "data": {"provider": provider, "integration": integration}},
    )


def _handle_process_confirmations(start_response, db_path: Path):
    with get_connection(db_path) as connection:
        data = process_confirmation_queue(connection)
    return _json_response(start_response, 200, {"success": True, "data": data})


def _handle_process_reminders(start_response, db_path: Path):
    with get_connection(db_path) as connection:
        data = process_due_reminders(connection)
    return _json_response(start_response, 200, {"success": True, "data": data})


def _handle_process_swaps(start_response, db_path: Path):
    with get_connection(db_path) as connection:
        data = process_preferred_swaps(connection)
    return _json_response(start_response, 200, {"success": True, "data": data})


def _handle_process_calendar_sync(start_response, db_path: Path):
    with get_connection(db_path) as connection:
        data = process_calendar_sync_queue(connection)
    return _json_response(start_response, 200, {"success": True, "data": data})


def _handle_reconcile_sync(start_response, db_path: Path):
    with get_connection(db_path) as connection:
        data = run_pull_reconciliation(connection)
    return _json_response(start_response, 200, {"success": True, "data": data})


def _handle_dashboard_metrics(start_response, db_path: Path):
    with get_connection(db_path) as connection:
        data = dashboard_metrics(connection)
    return _json_response(start_response, 200, {"success": True, "data": data})


def _handle_document_upload(environ, start_response, db_path: Path):
    payload = _read_json_body(environ)
    patient_profile_id = int(payload.get("patientProfileId") or 1)
    file_name = (payload.get("fileName") or "").strip()
    file_type = (payload.get("fileType") or "").strip().lower()
    file_size_bytes = payload.get("fileSizeBytes")

    if not file_name or not file_type:
        return _json_response(
            start_response,
            400,
            {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "fileName and fileType are required"}},
        )

    try:
        with get_connection(db_path) as connection:
            result = upload_document(connection, patient_profile_id, file_name, file_type, file_size_bytes)
        return _json_response(start_response, 200, {"success": True, "data": result})
    except ValueError as exc:
        return _json_response(
            start_response,
            400,
            {"success": False, "error": {"code": "VALIDATION_ERROR", "message": str(exc)}},
        )


def _handle_document_status(start_response, db_path: Path, document_id: int):
    with get_connection(db_path) as connection:
        status = get_document_status(connection, document_id)
    if not status:
        return _json_response(
            start_response,
            404,
            {"success": False, "error": {"code": "NOT_FOUND", "message": "Document not found"}},
        )
    return _json_response(start_response, 200, {"success": True, "data": status})


def _handle_list_documents(environ, start_response, db_path: Path):
    params = _flat_query_params(environ.get("QUERY_STRING", ""))
    patient_profile_id = int(params.get("patientProfileId") or 1)
    with get_connection(db_path) as connection:
        documents = get_patient_documents(connection, patient_profile_id)
    return _json_response(start_response, 200, {"success": True, "data": documents})


def _handle_clinical_profile(environ, start_response, db_path: Path):
    params = _flat_query_params(environ.get("QUERY_STRING", ""))
    patient_profile_id = int(params.get("patientProfileId") or 1)
    with get_connection(db_path) as connection:
        profile = get_clinical_profile(connection, patient_profile_id)
    return _json_response(start_response, 200, {"success": True, "data": profile})


def _handle_review_queue(environ, start_response, db_path: Path):
    params = _flat_query_params(environ.get("QUERY_STRING", ""))
    patient_profile_id = int(params.get("patientProfileId") or 1)
    with get_connection(db_path) as connection:
        queue = get_review_queue(connection, patient_profile_id)
    return _json_response(start_response, 200, {"success": True, "data": queue})


def _handle_conflict_queue(environ, start_response, db_path: Path):
    params = _flat_query_params(environ.get("QUERY_STRING", ""))
    patient_profile_id = int(params.get("patientProfileId") or 1)
    severity = params.get("severity") or None
    with get_connection(db_path) as connection:
        conflicts = get_unresolved_conflicts(connection, patient_profile_id, severity)
    return _json_response(start_response, 200, {"success": True, "data": conflicts})


def _handle_threshold_snapshot(start_response, db_path: Path):
    with get_connection(db_path) as connection:
        thresholds = get_threshold_snapshot(connection)
    return _json_response(start_response, 200, {"success": True, "data": thresholds})


def _handle_threshold_history(environ, start_response, db_path: Path):
    params = _flat_query_params(environ.get("QUERY_STRING", ""))
    code_type = params.get("codeType")
    if code_type not in ("icd10", "cpt"):
        return _json_response(
            start_response,
            400,
            {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "codeType is required"}},
        )
    with get_connection(db_path) as connection:
        history = get_threshold_history(connection, code_type)
    return _json_response(start_response, 200, {"success": True, "data": history})


def _handle_threshold_update(environ, start_response, db_path: Path):
    payload = _read_json_body(environ)
    code_type = payload.get("codeType")
    threshold_value = payload.get("confidenceThreshold")
    change_reason = payload.get("changeReason")
    actor_id = (environ.get("HTTP_X_USER_ID") or payload.get("actorId") or "unknown").strip()
    actor_role = (environ.get("HTTP_X_USER_ROLE") or payload.get("actorRole") or "viewer").strip()

    if code_type not in ("icd10", "cpt"):
        return _json_response(
            start_response,
            400,
            {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "codeType is required"}},
        )

    if not isinstance(threshold_value, (int, float)):
        return _json_response(
            start_response,
            400,
            {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "confidenceThreshold is required"}},
        )

    try:
        with get_connection(db_path) as connection:
            updated = update_threshold_config(
                connection,
                code_type,
                float(threshold_value),
                actor_id,
                actor_role,
                change_reason,
            )
    except PermissionError:
        return _json_response(
            start_response,
            403,
            {"success": False, "error": {"code": "FORBIDDEN", "message": "Threshold configuration requires admin or coder access"}},
        )
    except ValueError as exc:
        return _json_response(
            start_response,
            400,
            {"success": False, "error": {"code": "VALIDATION_ERROR", "message": str(exc)}},
        )

    return _json_response(start_response, 200, {"success": True, "data": updated})


def _handle_extract_document(environ, start_response, db_path: Path):
    payload = _read_json_body(environ)
    document_id = payload.get("documentId")
    if not document_id:
        return _json_response(
            start_response,
            400,
            {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "documentId is required"}},
        )

    try:
        with get_connection(db_path) as connection:
            result = process_document(connection, int(document_id))
        return _json_response(start_response, 200, {"success": True, "data": result})
    except ValueError as exc:
        return _json_response(
            start_response,
            404,
            {"success": False, "error": {"code": "NOT_FOUND", "message": str(exc)}},
        )


def _handle_aggregate_profile(environ, start_response, db_path: Path):
    payload = _read_json_body(environ)
    patient_profile_id = int(payload.get("patientProfileId") or 1)
    with get_connection(db_path) as connection:
        profile = aggregate_patient_profile(connection, patient_profile_id)
    return _json_response(start_response, 200, {"success": True, "data": profile})


def _handle_detect_conflicts(environ, start_response, db_path: Path):
    payload = _read_json_body(environ)
    patient_profile_id = int(payload.get("patientProfileId") or 1)
    with get_connection(db_path) as connection:
        medication_conflicts = detect_medication_conflicts(connection, patient_profile_id)
        allergy_conflicts = detect_allergy_drug_conflicts(connection, patient_profile_id)
    return _json_response(
        start_response,
        200,
        {
            "success": True,
            "data": {
                "medicationConflicts": medication_conflicts,
                "allergyConflicts": allergy_conflicts,
            },
        },
    )


def _handle_suggest_codes(environ, start_response, db_path: Path):
    payload = _read_json_body(environ)
    patient_profile_id = int(payload.get("patientProfileId") or 1)
    with get_connection(db_path) as connection:
        icd10_codes = suggest_icd10_codes(connection, patient_profile_id)
        cpt_codes = suggest_cpt_codes(connection, patient_profile_id)
    return _json_response(
        start_response,
        200,
        {
            "success": True,
            "data": {
                "icd10": icd10_codes,
                "cpt": cpt_codes,
            },
        },
    )


def _handle_review_code(environ, start_response, db_path: Path):
    payload = _read_json_body(environ)
    code_suggestion_id = payload.get("codeSuggestionId")
    action = payload.get("action")
    reviewer_id = payload.get("reviewerId")
    override_code = payload.get("overrideCode")
    rejection_reason = payload.get("rejectionReason")

    if not code_suggestion_id or action not in ("accept", "reject", "override") or not reviewer_id:
        return _json_response(
            start_response,
            400,
            {
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "codeSuggestionId, action, and reviewerId are required",
                },
            },
        )

    with get_connection(db_path) as connection:
        success = review_code_suggestion(
            connection,
            int(code_suggestion_id),
            action,
            reviewer_id,
            override_code,
            rejection_reason,
        )

    if not success:
        return _json_response(
            start_response,
            404,
            {"success": False, "error": {"code": "NOT_FOUND", "message": "Code suggestion not found"}},
        )

    return _json_response(start_response, 200, {"success": True, "data": {"codeSuggestionId": code_suggestion_id, "action": action}})


def _handle_conflict_resolve(environ, start_response, db_path: Path, conflict_id: int):
    payload = _read_json_body(environ)
    conflict_type = payload.get("conflictType")
    action = payload.get("action")
    reviewer_id = (payload.get("reviewerId") or environ.get("HTTP_X_USER_ID") or "unknown").strip()
    details = {
        "selectedEntityId": payload.get("selectedEntityId"),
        "mergeNotes": payload.get("mergeNotes"),
        "discardReason": payload.get("discardReason"),
        "provenance": payload.get("provenance"),
    }

    if conflict_type not in ("medication", "allergy"):
        return _json_response(
            start_response,
            400,
            {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "conflictType is required"}},
        )

    try:
        with get_connection(db_path) as connection:
            resolved = resolve_conflict(connection, conflict_type, conflict_id, action, reviewer_id, details)
    except ValueError as exc:
        return _json_response(
            start_response,
            400,
            {"success": False, "error": {"code": "VALIDATION_ERROR", "message": str(exc)}},
        )

    return _json_response(start_response, 200, {"success": True, "data": resolved})


def _serve_static(path: str, start_response):
    requested = "index.html" if path in ("", "/") else path.lstrip("/")
    target = (PUBLIC_DIR / requested).resolve()

    if not str(target).startswith(str(PUBLIC_DIR.resolve())):
        return _plain_response(start_response, 403, b"Forbidden", "text/plain")

    if not target.exists() or target.is_dir():
        target = PUBLIC_DIR / "index.html"

    content = target.read_bytes()
    mime_type, _ = mimetypes.guess_type(target.name)
    return _plain_response(start_response, 200, content, mime_type or "text/html")


def _json_response(start_response, status_code: int, payload: dict[str, Any]):
    body = json.dumps(payload).encode("utf-8")
    status_text = f"{status_code} {_status_text(status_code)}"
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
    ]
    start_response(status_text, headers)
    return [body]


def _plain_response(start_response, status_code: int, body: bytes, content_type: str):
    status_text = f"{status_code} {_status_text(status_code)}"
    headers = [
        ("Content-Type", f"{content_type}; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ]
    start_response(status_text, headers)
    return [body]


def _status_text(status_code: int) -> str:
    text = {
        200: "OK",
        400: "Bad Request",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        410: "Gone",
    }
    return text.get(status_code, "OK")


def _read_json_body(environ) -> dict[str, Any]:
    size = int(environ.get("CONTENT_LENGTH") or 0)
    if size <= 0:
        return {}
    payload = environ["wsgi.input"].read(size).decode("utf-8")
    if not payload:
        return {}
    return json.loads(payload)


def _flat_query_params(query_string: str) -> dict[str, str]:
    parsed = parse_qs(query_string, keep_blank_values=False)
    return {key: values[0] for key, values in parsed.items() if values}
