import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build_replacement_value import append_term_once  # noqa: E402


def test_append_term_once_appends_when_absent():
    assert append_term_once("=A1+B1", "+AS3") == "=A1+B1+AS3"


def test_append_term_once_is_idempotent_across_repeated_calls():
    """
    Regression test: running build_replacement_value.py against a workbook it already
    touched used to blindly append "+AS{r}" every time, so three manual pipeline runs left
    a real formula reading "...+AS3+AS3+AS3" -- silently tripling the QB replacement
    adjustment the moment anyone actually used it. append_term_once() must produce the same
    result no matter how many times it's applied.
    """
    once = append_term_once("=A1+B1", "+AS3")
    twice = append_term_once(once, "+AS3")
    thrice = append_term_once(twice, "+AS3")

    assert once == twice == thrice == "=A1+B1+AS3"


def test_append_term_once_collapses_pre_existing_duplicates():
    # Simulates repairing a formula that already accumulated duplicates before this fix.
    corrupted = "=A1+B1+AS3+AS3+AS3"
    assert append_term_once(corrupted, "+AS3") == "=A1+B1+AS3"


def test_append_term_once_does_not_confuse_similarly_named_rows():
    # +AS3 must not be stripped by a call meant for +AS30, or vice versa.
    formula = "=A1+B1+AS30"
    assert append_term_once(formula, "+AS3") == "=A1+B1+AS30+AS3"
