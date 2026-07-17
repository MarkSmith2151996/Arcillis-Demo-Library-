"""Live smoke test for the extended Google Sheets MCP tools.

Run with a service-account credential configured through GOOGLE_SHEETS_CREDENTIALS.
"""

from __future__ import annotations

import sys
import time
from typing import Any, Callable

from demo2_tools import (
    sheets_append,
    sheets_calculate,
    sheets_clear,
    sheets_conditional_format,
    sheets_find,
    sheets_format_cells,
    sheets_manage,
    sheets_merge,
    sheets_read_cells,
    sheets_snapshot,
    sheets_validate,
    sheets_write_cells,
)


DEFAULT_SPREADSHEET_ID = "14ud-CDITpFnNcZwqS0U5zoehthT84978l3Tty1YXT2g"


def run(name: str, tool: Callable[..., dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    """Run a tool, record its result, and print a concise pass/fail line."""
    result = tool(**kwargs)
    if result.get("error"):
        print(f"{name}: FAIL - {result['error']}")
    else:
        print(f"{name}: PASS")
    return result


def main() -> int:
    spreadsheet_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SPREADSHEET_ID
    timestamp = int(time.time())
    test_tab = f"ToolTest-{timestamp}"
    complete_tab = f"ToolTest-Complete-{timestamp}"

    created = run("sheets_manage add_sheet", sheets_manage, spreadsheet_id=spreadsheet_id, operation="add_sheet", new_name=test_tab)
    if created.get("error"):
        return 1

    rows = [["Demo Tool Test", "", "", ""], ["Item", "Amount", "Status", "Percent"]]
    rows.extend([[f"Item {index}", index * 10, "Pass" if index % 2 else "Review", index / 100] for index in range(1, 11)])
    run("sheets_write_cells", sheets_write_cells, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, range_str="A1:D12", values=rows)
    run("sheets_format_cells", sheets_format_cells, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, range_str="A2:D2", bold=True, background_color="#22C55E", column_width=140)
    run("sheets_format_cells borders", sheets_format_cells, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, range_str="A3:D12", borders={"top": True, "bottom": True, "left": True, "right": True})
    run("sheets_format_cells percentage", sheets_format_cells, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, range_str="D3:D12", number_format="0.0%")
    run("sheets_append", sheets_append, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, values=[["Item 11", 110, "Fail", 0.11], ["Item 12", 120, "Pass", 0.12], ["Item 13", 130, "Review", 0.13]])
    run("sheets_calculate average", sheets_calculate, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, formula="=AVERAGE(B3:B15)")
    run("sheets_calculate sum", sheets_calculate, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, formula="=SUM(B3:B15)")
    run("sheets_calculate countif", sheets_calculate, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, formula='=COUNTIF(C3:C15,"Pass")')
    run("sheets_merge", sheets_merge, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, range_str="A1:D1")
    found = run("sheets_find", sheets_find, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, query="Item 1")
    if not found.get("error") and found.get("count", 0) < 1:
        print("sheets_find verification: FAIL - expected at least one match")
    run("sheets_conditional_format", sheets_conditional_format, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, range_str="B3:B15", rule_type="NUMBER_LESS_THAN", values=["50"], format={"background_color": "#FF0000"})
    run("sheets_validate", sheets_validate, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, range_str="C3:C15", validation_type="ONE_OF_LIST", values=["Pass", "Review", "Fail"])
    snapshot = run("sheets_snapshot", sheets_snapshot, spreadsheet_id=spreadsheet_id, sheet_name=test_tab)
    if not snapshot.get("error") and snapshot.get("structure", {}).get("dimensions", {}).get("rows", 0) < 15:
        print("sheets_snapshot verification: FAIL - expected at least 15 populated rows")
    run("sheets_clear", sheets_clear, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, range_str="A15:D15")
    cleared = run("sheets_read_cells verify clear", sheets_read_cells, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, range_str="A15:D15")
    if not cleared.get("error") and cleared.get("values"):
        print("sheets_clear verification: FAIL - range still contains values")
    run("sheets_manage rename_sheet", sheets_manage, spreadsheet_id=spreadsheet_id, sheet_name=test_tab, operation="rename_sheet", new_name=complete_tab)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
