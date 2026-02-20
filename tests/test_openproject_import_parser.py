from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook

from app.services.openproject_import import parse_task_table_from_bytes


def _build_workbook_bytes(
    *,
    include_task_sheet: bool = True,
    headers: list[str] | None = None,
    rows: list[list[object]] | None = None,
) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Task_Table1" if include_task_sheet else "Sheet1"
    ws.append(headers or ["Name", "Duration", "Start_Date", "Finish_Date", "Predecessors", "Resource_Names"])
    for row in rows or []:
        ws.append(row)
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


def test_openproject_import_parser_legacy_template_auto_wbs() -> None:
    payload = parse_task_table_from_bytes(
        _build_workbook_bytes(
            include_task_sheet=True,
            rows=[
                ["Task A", "5 days", "14 February 2026 08:00 AM", "19 February 2026 05:00 PM", "", "Crew A"],
                ["Task B", "2 days", "20 February 2026", "22 February 2026", "1FS+2", "Crew B"],
            ],
        ),
        source_file_name="sample.xlsx",
    )
    summary = payload.get("summary") or {}
    rows = payload.get("rows") or []
    assert summary.get("total_rows") == 2
    assert summary.get("valid_rows") == 2
    assert summary.get("invalid_rows") == 0
    assert len(rows) == 2
    assert rows[0]["validation_status"] == "VALID"
    assert rows[0]["normalized_start_date"] == "2026-02-14"
    first_payload = rows[0]["payload_json"]
    assert "\"wbs_code\": \"1\"" in str(first_payload)
    assert "\"source\": \"auto_generated\"" in str(first_payload)
    assert "WBS column not found" in str(summary.get("mapping_warnings") or [])


def test_openproject_import_parser_new_template_invalid_wbs_done_ratio_and_predecessor() -> None:
    payload = parse_task_table_from_bytes(
        _build_workbook_bytes(
            include_task_sheet=True,
            headers=[
                "Subject",
                "WBS",
                "Start Date",
                "Finish Date",
                "%complete",
                "Predecessors",
            ],
            rows=[
                ["Task A", "1", "2026-02-14", "2026-02-18", "35", ""],
                ["Task B", "1.x", "2026-02-20", "2026-02-21", "120", "1SS+1"],
            ],
        ),
        source_file_name="sample_new.xlsx",
    )
    summary = payload.get("summary") or {}
    rows = payload.get("rows") or []
    assert summary.get("valid_rows") == 1
    assert summary.get("invalid_rows") == 1
    assert rows[1]["validation_status"] == "INVALID"
    message = str(rows[1]["error_message"] or "")
    assert "WBS format is invalid." in message
    assert "%complete must be a number between 0 and 100." in message
    assert "Predecessors format is invalid." in message


def test_openproject_import_parser_custom_columns_persist_in_payload() -> None:
    payload = parse_task_table_from_bytes(
        _build_workbook_bytes(
            include_task_sheet=True,
            headers=["Subject", "WBS", "CustomCode", "ExtraNote"],
            rows=[["Task A", "1", "C-100", "alpha"]],
        ),
        source_file_name="custom_cols.xlsx",
    )
    row = (payload.get("rows") or [])[0]
    raw_payload = str(row.get("payload_json") or "")
    assert "CustomCode" in raw_payload
    assert "C-100" in raw_payload
    assert "ExtraNote" in raw_payload
    assert "alpha" in raw_payload


def test_openproject_import_parser_missing_task_sheet_raises() -> None:
    with pytest.raises(ValueError, match="Task_Table1"):
        parse_task_table_from_bytes(
            _build_workbook_bytes(include_task_sheet=False),
            source_file_name="sample.xlsx",
        )
