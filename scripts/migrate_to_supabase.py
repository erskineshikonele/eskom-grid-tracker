#!/usr/bin/env python3
"""
One-time migration: seeds Supabase eskom_grid_metrics table
from the historical CSV backfill.

Run once locally:
  pip install supabase
  python scripts/migrate_to_supabase.py
"""

import csv
from pathlib import Path
from supabase import create_client

SUPABASE_URL = "https://jgpcdnttmmzhofmbhfgo.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpncGNkbnR0bW16aG9mbWJoZmdvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIxNDkyNjYsImV4cCI6MjA5NzcyNTI2Nn0.6k_qWkAOiMgyFREpNHRjdBi8KxUtZ0nHl3HCmQhy9jY"

CSV_PATH = Path(__file__).parent.parent / "data" / "eskom_grid_metrics.csv"

def clean(val):
    if val == "" or val is None:
        return None
    return val.strip()

def to_float(val):
    v = clean(val)
    if v is None:
        return None
    try:
        return float(v.replace(",", ""))
    except ValueError:
        return None

def to_int(val):
    v = clean(val)
    if v is None:
        return None
    try:
        return int(float(v.replace(",", "")))
    except ValueError:
        return None

def to_bool(val):
    return str(val).strip().upper() == "TRUE"

def to_date(val):
    v = clean(val)
    return v if v else None

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

with open(CSV_PATH, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

print(f"Migrating {len(rows)} rows...")

for row in rows:
    record = {
        "report_date":        to_date(row["report_date"]),
        "week_start":         to_date(row["week_start"]),
        "week_end":           to_date(row["week_end"]),
        "financial_year":     clean(row["financial_year"]),
        "eaf_period_pct":     to_float(row["eaf_period_pct"]),
        "eaf_period_type":    clean(row["eaf_period_type"]),
        "eaf_ytd_pct":        to_float(row["eaf_ytd_pct"]),
        "uclf_week_pct":      to_float(row["uclf_week_pct"]),
        "pclf_week_pct":      to_float(row["pclf_week_pct"]),
        "unplanned_mw_avg":   to_float(row["unplanned_mw_avg"]),
        "diesel_weekly_mzar": to_float(row["diesel_weekly_mzar"]),
        "diesel_ytd_mzar":    to_float(row["diesel_ytd_mzar"]),
        "consec_days_no_ls":  to_int(row["consec_days_no_ls"]),
        "eaf70_count_ytd":    to_int(row["eaf70_count_ytd"]),
        "disputed":           to_bool(row["disputed"]),
        "notes":              clean(row["notes"]),
    }

    result = supabase.table("eskom_grid_metrics").upsert(record, on_conflict="report_date").execute()
    print(f"  ✓ {record['report_date']}")

print("\nMigration complete.")
