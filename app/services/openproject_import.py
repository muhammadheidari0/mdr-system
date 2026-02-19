from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from io import BytesIO
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel


TASK_TABLE_SHEET = "Task_Table1"

_HEADER_ALIASES: dict[str, str] = {
    "name": "name",
    "duration": "duration",
    "startdate": "start_date",
    "finishdate": "finish_date",
    "predecessors": "predecessors",
    "resourcenames": "resource_names",
}

_DATE_FORMATS: tuple[str, ...] = (
    "%d %B %Y %I:%M %p",
    "%d %B %Y %H:%M",
    "%d %B %Y",
    "%d %b %Y",
    "%a %d/%m/%y",
    "%d/%m/%y",
    "%d/%m/%Y",
    "%Y-%m-%d",
)


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _header_key(value: Any) -> str:
    return re.sub(r"[\s_]+", "", _norm_text(value).lower())


def _normalize_excel_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        try:
            parsed = from_excel(value)
            if isinstance(parsed, datetime):
                return parsed.date().isoformat()
            if isinstance(parsed, date):
                return parsed.isoformat()
        except Exception:
            return None
    raw = _norm_text(value)
    if not raw:
        return None

    normalized = (
        raw.replace("ق.ظ", "AM")
        .replace("ب.ظ", "PM")
        .replace("\u200c", " ")
        .replace("،", " ")
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).date().isoformat()
        except Exception:
            continue

    m = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", normalized)
    if m:
        value_only = m.group(1)
        for fmt in ("%d/%m/%y", "%d/%m/%Y"):
            try:
                return datetime.strptime(value_only, fmt).date().isoformat()
            except Exception:
                continue

    m = re.search(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})", normalized)
    if m:
        value_only = m.group(1)
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(value_only, fmt).date().isoformat()
            except Exception:
                continue

    return None


def _parse_duration_days(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        days = int(value)
        return days if days >= 0 else None
    raw = _norm_text(value)
    if not raw:
        return None
    match = re.search(r"(-?\d+)", raw)
    if not match:
        return None
    days = int(match.group(1))
    return days if days >= 0 else None


def _split_multi_values(raw_value: Any) -> list[str]:
    raw = _norm_text(raw_value)
    if not raw:
        return []
    values: list[str] = []
    for part in re.split(r"[;,]", raw):
        value = _norm_text(part)
        if not value:
            continue
        if value not in values:
            values.append(value)
    return values


def parse_task_table_from_bytes(
    file_bytes: bytes,
    *,
    source_file_name: str,
) -> dict[str, Any]:
    if not file_bytes:
        raise ValueError("Uploaded file is empty.")

    digest = hashlib.sha256(file_bytes).hexdigest()
    try:
        workbook = load_workbook(filename=BytesIO(file_bytes), data_only=True, read_only=True)
    except Exception as exc:
        raise ValueError(f"Invalid Excel file: {exc}") from exc

    if TASK_TABLE_SHEET not in workbook.sheetnames:
        raise ValueError(f"Sheet `{TASK_TABLE_SHEET}` not found in workbook.")

    sheet = workbook[TASK_TABLE_SHEET]
    rows_iter = sheet.iter_rows(min_row=1, max_row=1, values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration as exc:
        raise ValueError("Task sheet header is empty.") from exc

    headers: dict[str, int] = {}
    for idx, cell_value in enumerate(header_row):
        alias = _HEADER_ALIASES.get(_header_key(cell_value))
        if alias and alias not in headers:
            headers[alias] = idx

    if "name" not in headers:
        raise ValueError("Task sheet must contain `Name` column.")

    parsed_rows: list[dict[str, Any]] = []
    total_rows = 0
    valid_rows = 0
    invalid_rows = 0

    for excel_row_no, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        def value_of(field: str) -> Any:
            pos = headers.get(field)
            if pos is None or pos >= len(row):
                return None
            return row[pos]

        if all(not _norm_text(v) for v in row):
            continue

        total_rows += 1
        task_name = _norm_text(value_of("name"))
        duration_raw = _norm_text(value_of("duration"))
        start_raw = _norm_text(value_of("start_date"))
        finish_raw = _norm_text(value_of("finish_date"))
        predecessors_raw = _norm_text(value_of("predecessors"))
        resource_names_raw = _norm_text(value_of("resource_names"))

        normalized_start = _normalize_excel_date(value_of("start_date"))
        normalized_finish = _normalize_excel_date(value_of("finish_date"))
        duration_days = _parse_duration_days(value_of("duration"))
        predecessor_items = _split_multi_values(predecessors_raw)
        resource_items = _split_multi_values(resource_names_raw)

        row_errors: list[str] = []
        if not task_name:
            row_errors.append("Name is required.")
        if start_raw and not normalized_start:
            row_errors.append("Start_Date is invalid.")
        if finish_raw and not normalized_finish:
            row_errors.append("Finish_Date is invalid.")
        if normalized_start and normalized_finish and normalized_finish < normalized_start:
            row_errors.append("Finish_Date must be greater than or equal to Start_Date.")

        validation_status = "VALID" if not row_errors else "INVALID"
        if validation_status == "VALID":
            valid_rows += 1
        else:
            invalid_rows += 1

        payload = {
            "sheet": TASK_TABLE_SHEET,
            "task_name": task_name,
            "duration_days": duration_days,
            "normalized_start_date": normalized_start,
            "normalized_finish_date": normalized_finish,
            "predecessors": predecessor_items,
            "resources": resource_items,
            "errors": row_errors,
        }

        parsed_rows.append(
            {
                "row_no": int(excel_row_no),
                "task_name": task_name or None,
                "duration_raw": duration_raw or None,
                "start_raw": start_raw or None,
                "finish_raw": finish_raw or None,
                "predecessors_raw": predecessors_raw or None,
                "resource_names_raw": resource_names_raw or None,
                "normalized_start_date": normalized_start,
                "normalized_finish_date": normalized_finish,
                "validation_status": validation_status,
                "execution_status": "PENDING",
                "error_message": "; ".join(row_errors) if row_errors else None,
                "payload_json": json.dumps(payload, ensure_ascii=False),
            }
        )

    summary = {
        "sheet": TASK_TABLE_SHEET,
        "source_file_name": _norm_text(source_file_name) or "openproject_import.xlsx",
        "source_sha256": digest,
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "created_rows": 0,
        "failed_rows": 0,
    }
    return {
        "summary": summary,
        "rows": parsed_rows,
        "source_sha256": digest,
    }


def parse_summary_json(value: str | None) -> dict[str, Any]:
    raw = _norm_text(value)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_work_package_create_payload(
    *,
    row_task_name: str,
    row_start_date: str | None,
    row_finish_date: str | None,
    row_no: int,
    run_no: str,
    parent_work_package_id: int,
    project_href: str,
    type_href: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "subject": row_task_name,
        "description": {
            "format": "markdown",
            "raw": f"Imported from Excel run {run_no} (row {row_no}).",
        },
        "_links": {
            "project": {"href": project_href},
            "type": {"href": type_href},
            "parent": {"href": f"/api/v3/work_packages/{int(parent_work_package_id)}"},
        },
    }
    if row_start_date:
        payload["startDate"] = row_start_date
    if row_finish_date:
        payload["dueDate"] = row_finish_date
    return payload
