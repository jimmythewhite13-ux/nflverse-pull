"""
Step 1 of the NFL Model v35 Validation/Audit master spec: mechanical extraction of the
frozen v35 workbook's real structure into a machine-readable manifest. Deliberately does
NOT touch the workbook -- read-only, `data_only=False` (formula text, not cached values).

Extracts, per worksheet:
  - dimensions (max_row, max_col)
  - every real Model Assumptions constant (row, label, value, note) -- this IS the
    "Coefficient" column of the manifest, extracted directly from the real cell values,
    not from memory.
  - which build script(s) actually reference each Model Assumptions constant (grepped
    directly against this repo's own scripts/ -- ground truth for "Dependencies", not
    recalled from memory).

Output: prediction_audit/manifests/v35_model_assumptions_manifest.csv (one row per real
tunable constant) and prediction_audit/manifests/v35_worksheet_inventory.csv (one row per
worksheet).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKBOOK = Path(__file__).resolve().parent / "frozen_baselines" / "NFL_Prediction_Model_v35.xlsx"
SCRIPTS_DIR = REPO_ROOT / "scripts"
OUT_DIR = Path(__file__).resolve().parent / "manifests"


def find_constant_references() -> dict[int, list[str]]:
    """Grep every scripts/*.py file for 'Model Assumptions'!$C$<row> references, returning
    {row: [script_names_that_reference_it]}. Ground truth from the actual repo, not memory."""
    refs: dict[int, set[str]] = {}
    pattern = re.compile(r"\$C\$(\d+)")
    for path in sorted(SCRIPTS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        # Only count occurrences that appear near a "Model Assumptions" sheet reference in
        # the same file (a rough but effective filter -- this repo always writes the sheet
        # name literal right before the cell reference in an f-string).
        if "Model Assumptions" not in text:
            continue
        for m in pattern.finditer(text):
            row = int(m.group(1))
            refs.setdefault(row, set()).add(path.stem)
    return {k: sorted(v) for k, v in refs.items()}


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    wb = openpyxl.load_workbook(WORKBOOK, data_only=False)
    refs = find_constant_references()

    # ---- Worksheet inventory --------------------------------------------------------------
    with open(OUT_DIR / "v35_worksheet_inventory.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Worksheet", "Max_Row", "Max_Column", "A1_Title_Text"])
        for name in wb.sheetnames:
            ws = wb[name]
            a1 = ws.cell(row=1, column=1).value
            a1_text = (str(a1)[:200] if a1 else "")
            writer.writerow([name, ws.max_row, ws.max_column, a1_text])

    # ---- Model Assumptions constants (every real tunable coefficient) ---------------------
    ma = wb["Model Assumptions"]
    rows_out = []
    for r in range(1, ma.max_row + 1):
        label = ma.cell(row=r, column=2).value
        value = ma.cell(row=r, column=3).value
        note = ma.cell(row=r, column=4).value
        title = ma.cell(row=r, column=1).value
        if label is None and value is None and title is None:
            continue
        referenced_by = refs.get(r, [])
        rows_out.append({
            "Row": r,
            "Section_Title": str(title)[:150] if title else "",
            "Label": str(label) if label else "",
            "Value": value,
            "Note": str(note)[:300] if note else "",
            "Referenced_By_Scripts": ";".join(referenced_by),
            "Referenced_Anywhere": bool(referenced_by),
        })

    with open(OUT_DIR / "v35_model_assumptions_manifest.csv", "w", newline="",
              encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "Row", "Section_Title", "Label", "Value", "Note", "Referenced_By_Scripts",
            "Referenced_Anywhere",
        ])
        writer.writeheader()
        writer.writerows(rows_out)

    n_constants = sum(1 for r in rows_out if r["Label"])
    n_unreferenced = sum(1 for r in rows_out if r["Label"] and not r["Referenced_Anywhere"])
    print(f"Worksheet inventory: {len(wb.sheetnames)} sheets -> "
          f"{OUT_DIR / 'v35_worksheet_inventory.csv'}")
    print(f"Model Assumptions manifest: {n_constants} real labeled constants "
          f"({n_unreferenced} not referenced by any script -- worth checking) -> "
          f"{OUT_DIR / 'v35_model_assumptions_manifest.csv'}")


if __name__ == "__main__":
    main()
