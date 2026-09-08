"""
Automated agent layer -- real, scheduled input refresh (injuries, rosters, schedule
confirmation, market-line capture). Per the governing spec (Downloads/NFL Model — Automated
Agent Specification): this package NEVER changes a coefficient, formula, weight, or feature
inclusion. Every job here writes into the standalone `ingestion_runs`/`raw_*` tables
(`prediction_audit/db/schema.py`), deliberately decoupled from `prediction_runs` -- it never
generates or touches a model prediction, by construction, not merely by convention.
"""
