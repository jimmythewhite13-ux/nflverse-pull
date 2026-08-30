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


def test_append_term_once_stays_idempotent_when_a_different_term_is_appended_after_it():
    """
    Real bug found live (claude_code_spec_defensive_matchup_engine.md Part C): the original
    fix only stripped a TRAILING run of `term`, correct as long as `term` was always the
    LAST thing ever appended. That broke once a second script (build_defensive_matchup_
    wiring.py) started appending its OWN different term ("+BG{r}") after Replacement
    Value's "+AS{r}" -- re-running both left Z reading
    "...+AS3+BG3+AS3+BG3+AS3+BG3" because each script's trailing-anchored strip found
    nothing to remove (its own term was no longer at the very end). Simulates exactly that
    two-script interleaving.
    """
    formula = "=A1+B1"
    formula = append_term_once(formula, "+AS3")  # Replacement Value's own term
    formula = append_term_once(formula, "+BG3")  # a second script's different term
    # Re-running BOTH scripts again must not duplicate either term, regardless of order.
    formula = append_term_once(formula, "+AS3")
    formula = append_term_once(formula, "+BG3")
    formula = append_term_once(formula, "+AS3")
    formula = append_term_once(formula, "+BG3")

    assert formula == "=A1+B1+AS3+BG3"
