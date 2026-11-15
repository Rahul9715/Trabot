"""Daily-sheet Excel mirror for suggested trade records.

The SQLite hash-chain remains the audit source of truth. This workbook is a
convenient, rebuildable review/export view, with one worksheet per local date.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

WORKBOOK_PATH = Path(os.getenv("CANDIDATE_XLSX_PATH", "./data/suggested_trades.xlsx"))
LOCAL_TZ = ZoneInfo("Asia/Kolkata")
HEADERS = ["Candidate ID", "Created (UTC)", "Symbol", "Instrument", "Side", "Entry", "Stop Loss", "Target", "Confidence %", "Status", "Expiry Reason", "Rationale", "Target Rationale", "Stop Rationale", "Evidence JSON", "Updated (UTC)"]
_LOCK = threading.RLock()


def _safe_text(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def _sheet_name(item: dict) -> str:
    stamp = item.get("created_at") or datetime.now().astimezone().isoformat()
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        return parsed.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")


def _values(item: dict) -> list:
    return [
        _safe_text(item.get("candidate_id")), _safe_text(item.get("created_at")),
        _safe_text(item.get("symbol")), _safe_text(item.get("instrument_token")),
        _safe_text(item.get("side")), item.get("entry"), item.get("stop_loss"), item.get("target"),
        item.get("confidence"), _safe_text(item.get("status")), _safe_text(item.get("expiry_reason")),
        _safe_text(item.get("rationale")), _safe_text(item.get("target_rationale")),
        _safe_text(item.get("stop_loss_rationale")),
        _safe_text(json.dumps(item.get("evidence", {}), ensure_ascii=False, sort_keys=True, default=str)),
        _safe_text(item.get("updated_at") or item.get("decided_at") or item.get("expired_at") or ""),
    ]


def upsert_candidate(item: dict) -> Path:
    """Create or update one candidate row atomically in its date worksheet."""
    with _LOCK:
        WORKBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
        if WORKBOOK_PATH.exists():
            workbook = load_workbook(WORKBOOK_PATH)
        else:
            workbook = Workbook()
            workbook.remove(workbook.active)
        name = _sheet_name(item)
        sheet = workbook[name] if name in workbook.sheetnames else workbook.create_sheet(name)
        if sheet.max_row == 1 and sheet.cell(1, 1).value is None:
            for col, header in enumerate(HEADERS, 1):
                sheet.cell(1, col, header)
        elif sheet.max_row == 0:
            sheet.append(HEADERS)
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")
        candidate_id = str(item.get("candidate_id", ""))
        row = next((idx for idx in range(2, sheet.max_row + 1) if str(sheet.cell(idx, 1).value).lstrip("'") == candidate_id), None)
        values = _values(item)
        if row is None:
            sheet.append(values)
            row = sheet.max_row
        else:
            for col, value in enumerate(values, 1):
                sheet.cell(row, col, value)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        widths = [24, 28, 18, 28, 10, 14, 14, 14, 15, 16, 36, 60, 40, 40, 80, 28]
        for col, width in enumerate(widths, 1):
            sheet.column_dimensions[get_column_letter(col)].width = width
        handle, temp_name = tempfile.mkstemp(prefix="suggested_trades_", suffix=".xlsx", dir=WORKBOOK_PATH.parent)
        os.close(handle)
        try:
            workbook.save(temp_name)
            os.replace(temp_name, WORKBOOK_PATH)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
            workbook.close()
        return WORKBOOK_PATH


def ensure_export() -> Path:
    """Ensure a downloadable workbook exists, even before the first suggestion."""
    with _LOCK:
        if WORKBOOK_PATH.exists():
            return WORKBOOK_PATH
        WORKBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
        for col, header in enumerate(HEADERS, 1):
            sheet.cell(1, col, header)
        handle, temp_name = tempfile.mkstemp(prefix="suggested_trades_", suffix=".xlsx", dir=WORKBOOK_PATH.parent)
        os.close(handle)
        try:
            workbook.save(temp_name)
            os.replace(temp_name, WORKBOOK_PATH)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
            workbook.close()
        return WORKBOOK_PATH
