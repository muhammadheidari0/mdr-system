from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook

from app.services.openproject_import import parse_task_table_from_bytes


def _build_workbook_bytes(*, include_task_sheet: bool = True) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Task_Table1" if include_task_sheet else "Sheet1"
    ws.append(["Name", "Duration", "Start_Date", "Finish_Date", "Predecessors", "Resource_Names"])
    ws.append(["Task A", "5 days", "14 February 2026 08:00 AM", "19 February 2026 05:00 PM", "1", "Crew A"])
    ws.append(["", "1 day", "bad-date", "", "", ""])
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


def test_openproject_import_parser_valid_and_invalid_rows() -> None:
    payload = parse_task_table_from_bytes(
        _build_workbook_bytes(include_task_sheet=True),
        source_file_name="sample.xlsx",
    )
    summary = payload.get("summary") or {}
    rows = payload.get("rows") or []
    assert summary.get("total_rows") == 2
    assert summary.get("valid_rows") == 1
    assert summary.get("invalid_rows") == 1
    assert len(rows) == 2
    assert rows[0]["validation_status"] == "VALID"
    assert rows[0]["normalized_start_date"] == "2026-02-14"
    assert rows[1]["validation_status"] == "INVALID"
    assert "Name is required." in str(rows[1]["error_message"] or "")


def test_openproject_import_parser_missing_task_sheet_raises() -> None:
    with pytest.raises(ValueError, match="Task_Table1"):
        parse_task_table_from_bytes(
            _build_workbook_bytes(include_task_sheet=False),
            source_file_name="sample.xlsx",
        )
