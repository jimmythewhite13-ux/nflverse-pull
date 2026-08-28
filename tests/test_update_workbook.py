import pandas as pd
import pytest

from nflverse_pull.update_workbook import (
    _write_efficiency_section,
    _write_yoy_section,
    build_efficiency_updates,
    build_yoy_updates,
)


def test_build_yoy_updates_maps_team_season_to_ppg():
    ppg = pd.DataFrame([
        {"Team": "Buffalo Bills", "Season": 2023, "Off PPG": 22.7, "Def PPG": 18.2},
        {"Team": "Buffalo Bills", "Season": 2024, "Off PPG": 24.3, "Def PPG": 19.8},
        {"Team": "Miami Dolphins", "Season": 2023, "Off PPG": 20.9, "Def PPG": 19.2},
    ])

    updates = build_yoy_updates(ppg)

    assert updates[("Buffalo Bills", 2023)] == (22.7, 18.2)
    assert updates[("Buffalo Bills", 2024)] == (24.3, 19.8)
    assert updates[("Miami Dolphins", 2023)] == (20.9, 19.2)
    assert len(updates) == 3


def test_build_efficiency_updates_maps_team_season_to_metric_tuple():
    season_eff = pd.DataFrame([
        {"Team": "Buffalo Bills", "Season": 2023, "EPA/Play (Off)": 0.1,
         "EPA/Play Allowed (Def)": -0.05, "Success Rate (Off)": 0.48,
         "Success Rate Allowed (Def)": 0.43, "NY/A (Off)": 6.6, "NY/A Allowed (Def)": 5.3,
         "PROE (Off)": -0.02},
        {"Team": "Buffalo Bills", "Season": 2024, "EPA/Play (Off)": 0.15,
         "EPA/Play Allowed (Def)": -0.03, "Success Rate (Off)": 0.49,
         "Success Rate Allowed (Def)": 0.42, "NY/A (Off)": 6.8, "NY/A Allowed (Def)": 5.2,
         "PROE (Off)": -0.01},
    ])

    updates = build_efficiency_updates(season_eff)

    assert updates[("Buffalo Bills", 2023)] == (0.1, -0.05, 0.48, 0.43, 6.6, 5.3, -0.02)
    assert updates[("Buffalo Bills", 2024)] == (0.15, -0.03, 0.49, 0.42, 6.8, 5.2, -0.01)
    assert len(updates) == 2


class _FakeCell:
    def __init__(self, value=None):
        self.value = value


class _FakeSheet:
    """Minimal stand-in for an openpyxl worksheet: a dict of {(row, col): _FakeCell}."""

    def __init__(self, rows: list[list]):
        self._cells = {}
        for r, row_values in enumerate(rows, start=1):
            for c, v in enumerate(row_values, start=1):
                self._cells[(r, c)] = _FakeCell(v)

    def cell(self, row, column, value=None):
        key = (row, column)
        if key not in self._cells:
            self._cells[key] = _FakeCell()
        if value is not None:
            self._cells[key].value = value
        return self._cells[key]


def test_write_yoy_section_writes_ppg_into_matching_rows_and_stops_at_blank_row():
    # Row 5-6 mimic the workbook's real layout (rows 1-4 are headers, omitted here);
    # a blank row 7 (all None) must stop the scan, matching Section 1's real boundary.
    sheet_rows = [[None]] * 4 + [
        ["Buffalo Bills", 2023, 0.0, 0.0],
        ["Buffalo Bills", 2024, 0.0, 0.0],
        [None, None, None, None],
    ]
    ws = _FakeSheet(sheet_rows)
    updates = {("Buffalo Bills", 2023): (22.7, 18.2), ("Buffalo Bills", 2024): (24.3, 19.8)}

    written = _write_yoy_section(ws, updates)

    assert written == 2
    assert ws.cell(row=5, column=3).value == 22.7
    assert ws.cell(row=5, column=4).value == 18.2
    assert ws.cell(row=6, column=3).value == 24.3
    assert ws.cell(row=6, column=4).value == 19.8


def test_write_yoy_section_raises_on_workbook_pull_mismatch():
    sheet_rows = [[None]] * 4 + [["Buffalo Bills", 2023, 0.0, 0.0]]
    ws = _FakeSheet(sheet_rows)
    with pytest.raises(KeyError):
        _write_yoy_section(ws, {})  # no pulled data for the team/season the sheet expects


def test_write_efficiency_section_writes_all_seven_metric_columns_per_team_season():
    # Team, Season, then 7 metric columns (C-I) -- matches the Multi-Year Efficiency
    # Engine's Section 1 shape (same (Team, Season) keying as YoY Section 1).
    sheet_rows = [[None]] * 4 + [
        ["Buffalo Bills", 2023, 0, 0, 0, 0, 0, 0, 0],
        ["Buffalo Bills", 2024, 0, 0, 0, 0, 0, 0, 0],
        [None] * 9,
    ]
    ws = _FakeSheet(sheet_rows)
    updates = {
        ("Buffalo Bills", 2023): (0.1, -0.05, 0.48, 0.43, 6.6, 5.3, -0.02),
        ("Buffalo Bills", 2024): (0.15, -0.03, 0.49, 0.42, 6.8, 5.2, -0.01),
    }

    written = _write_efficiency_section(ws, updates)

    assert written == 2
    assert [ws.cell(row=5, column=c).value for c in range(3, 10)] == [
        0.1, -0.05, 0.48, 0.43, 6.6, 5.3, -0.02,
    ]
    assert [ws.cell(row=6, column=c).value for c in range(3, 10)] == [
        0.15, -0.03, 0.49, 0.42, 6.8, 5.2, -0.01,
    ]


def test_write_efficiency_section_raises_on_workbook_pull_mismatch():
    sheet_rows = [[None]] * 4 + [["Buffalo Bills", 2023, 0, 0, 0, 0, 0, 0, 0]]
    ws = _FakeSheet(sheet_rows)
    with pytest.raises(KeyError):
        _write_efficiency_section(ws, {})
