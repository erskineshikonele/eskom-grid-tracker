#!/usr/bin/env python3
"""
Eskom Grid Recovery Tracker — weekly scraper
Fetches the latest Eskom power system status page, extracts key metrics
via regex, and appends a new row to eskom_grid_metrics.csv.

Run every Friday evening via GitHub Actions.
"""

import re
import csv
import sys
import os
import json
import datetime
import requests
from pathlib import Path

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
STATUS_URL = "https://www.eskom.co.za/power-system-status/"
CSV_PATH   = Path(__file__).parent.parent / "data" / "eskom_grid_metrics.csv"
HEADERS    = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; EskomGridTracker/1.0; "
        "+https://github.com/ErskineShi/eskom-grid-tracker)"
    )
}


# ─────────────────────────────────────────────
# Regex extraction helpers
# ─────────────────────────────────────────────

def extract_first(pattern: str, text: str, group: int = 1, flags=re.IGNORECASE | re.DOTALL) -> str | None:
    """Return first match for pattern, or None."""
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else None


def parse_float(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_mw(s: str | None) -> float | None:
    """Parse MW value like '9 252' or '9,252' or '9252'."""
    if s is None:
        return None
    s = re.sub(r"[\s,]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


# ─────────────────────────────────────────────
# Field extractors (applied to article text)
# ─────────────────────────────────────────────

def extract_eaf_ytd(text: str) -> float | None:
    """YTD / financial-year-to-date EAF percentage."""
    patterns = [
        r"(?:financial year[\s\S]{0,30}?)EAF[^\d]{0,20}([\d]{2,3}\.[\d]{1,2})%",
        r"EAF[^\d]{0,30}([\d]{2,3}\.[\d]{1,2})%[^\n]{0,80}year[\s\-]to[\s\-]date",
        r"year[\s\-]to[\s\-]date[^\n]{0,80}EAF[^\d]{0,20}([\d]{2,3}\.[\d]{1,2})%",
        r"year[\s\-]to[\s\-]date.*?EAF.*?increased to ([\d]{2,3}\.[\d]{1,2})%",
        r"EAF.*?stands at ([\d]{2,3}\.[\d]{1,2})%.*?(?:year|financial year)[\s\-]to[\s\-]date",
        r"EAF.*?now stands at ([\d]{2,3}\.[\d]{1,2})%.*?(?:year|financial year)[\s\-]to[\s\-]date",
        r"EAF[^\n]{0,200}?(?:year|financial year)[\s\-]to[\s\-]date[^\n]{0,60}?([\d]{2,3}\.[\d]{1,2})%",
        r"(?:year|financial year)[\s\-]to[\s\-]date[^\n]{0,60}?EAF[^\d]{0,10}([\d]{2,3}\.[\d]{1,2})%",
        # fallback: any standalone YTD EAF figure near 60–70%
        r"EAF.*?(?:increased|improved|stands|rising|risen).*?(6[0-9]\.\d{1,2})%",
    ]
    for p in patterns:
        val = parse_float(extract_first(p, text))
        if val and 40 <= val <= 95:
            return val
    return None


def extract_uclf_week(text: str) -> float | None:
    """Weekly UCLF percentage."""
    patterns = [
        r"(?:average )?UCLF[^\d]{0,30}([\d]{1,2}\.[\d]{1,2})%[^\n]{0,60}(?:same period|reduction|improvement|last year|this period)",
        r"(?:average )?UCLF[^\n]{0,60}([\d]{1,2}\.[\d]{1,2})%",
        r"Unplanned Capabilit(?:y|ies) Loss Factor[^\d]{0,40}([\d]{1,2}\.[\d]{1,2})%",
        r"Unplanned Capacity Loss Factor[^\d]{0,40}([\d]{1,2}\.[\d]{1,2})%",
    ]
    for p in patterns:
        val = parse_float(extract_first(p, text))
        if val and 5 <= val <= 50:
            return val
    return None


def extract_pclf_week(text: str) -> float | None:
    """Weekly PCLF (planned maintenance) percentage."""
    patterns = [
        r"(?:average )?PCLF[^\d]{0,30}([\d]{1,2}\.[\d]{1,2})%",
        r"Planned Capacity Loss Factor[^\d]{0,40}([\d]{1,2}\.[\d]{1,2})%",
        r"planned maintenance[^\n]{0,40}([\d]{1,2}\.[\d]{1,2})%",
    ]
    for p in patterns:
        val = parse_float(extract_first(p, text))
        if val and 3 <= val <= 30:
            return val
    return None


def extract_unplanned_mw(text: str) -> float | None:
    """Average weekly unplanned outages in MW."""
    patterns = [
        r"average unplanned outages[^\d]{0,20}([\d][\d\s,]{2,7}MW)",
        r"average[^\n]{0,30}unplanned[^\d]{0,20}([\d][\d\s,]{2,7}MW)",
        r"unplanned outages[^\n]{0,20}decreased to ([\d][\d\s,]{2,7}MW)",
        r"unplanned outages[^\n]{0,20}(?:at|of|to|recorded at) ([\d][\d\s,]{2,7}MW)",
    ]
    for p in patterns:
        raw = extract_first(p, text)
        if raw:
            val = parse_mw(re.sub(r"MW", "", raw, flags=re.IGNORECASE))
            if val and 2000 <= val <= 25000:
                return val
    return None


def extract_diesel_weekly(text: str) -> float | None:
    """Weekly diesel expenditure in R millions."""
    patterns = [
        r"(?:last |past |this )?week[^\n]{0,60}diesel[^\n]{0,30}R([\d,]+(?:\.\d{1,2})?)\s*(?:million|m\b)",
        r"diesel[^\n]{0,60}R([\d,]+(?:\.\d{1,2})?)\s*(?:million|m\b)[^\n]{0,60}(?:week|past|last)",
        r"diesel expenditure[^\n]{0,60}R([\d,]+(?:\.\d{1,2})?)\s*(?:million|m\b)",
        r"(?:zero|R0\.0|R0\.00) million",   # explicit zero
    ]
    for p in patterns[:-1]:
        raw = extract_first(p, text)
        if raw:
            val = parse_float(raw)
            if val is not None and 0 <= val <= 500:
                return val
    # zero diesel
    if re.search(r"(?:zero|R0\.0{1,2}|no diesel)[^\n]{0,60}(?:expenditure|used|utilised|this week|past week)", text, re.IGNORECASE):
        return 0.0
    return None


def extract_consec_days(text: str) -> int | None:
    """Consecutive days without loadshedding."""
    patterns = [
        r"([\d,]+) consecutive days? without (?:an )?interruption",
        r"([\d,]+) consecutive days? without loadshedding",
        r"recorded ([\d,]+) consecutive days? without",
    ]
    for p in patterns:
        raw = extract_first(p, text)
        if raw:
            val = re.sub(r"[,\s]", "", raw)
            try:
                n = int(val)
                if 0 <= n <= 2000:
                    return n
            except ValueError:
                pass
    return None


def extract_eaf70_count(text: str) -> int | None:
    """Number of times EAF hit/exceeded 70% YTD."""
    patterns = [
        r"([\d]+) occasions[^\n]{0,60}(?:70|EAF)",
        r"achieved or (?:exceeded|surpassed)[^\n]{0,40}70%[^\n]{0,20}(?:on|for) ([\d]+) occasions",
        r"70%[^\n]{0,40}([\d]+) occasions",
    ]
    for p in patterns:
        raw = extract_first(p, text)
        if raw:
            try:
                n = int(raw)
                if 0 <= n <= 400:
                    return n
            except ValueError:
                pass
    return None


def extract_report_date(text: str) -> str | None:
    """Pull publication date from press release header like 'Friday, 19 June 2026:'"""
    m = re.search(
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
        r"(\d{1,2}\s+\w+\s+\d{4})",
        text, re.IGNORECASE
    )
    if m:
        try:
            d = datetime.datetime.strptime(m.group(1).strip(), "%d %B %Y")
            return d.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def fetch_article_text(url: str) -> str:
    """Fetch page and return combined inner text (strip HTML tags)."""
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    # Strip HTML tags naively
    text = re.sub(r"<[^>]+>", " ", r.text)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def load_existing_dates(csv_path: Path) -> set:
    if not csv_path.exists():
        return set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["report_date"] for row in reader}


def determine_financial_year(date_str: str) -> str:
    d = datetime.date.fromisoformat(date_str)
    if d.month >= 4:
        return f"FY{d.year}/{str(d.year+1)[2:]}"
    else:
        return f"FY{d.year-1}/{str(d.year)[2:]}"


def scrape_and_append():
    print(f"[scrape_eskom] Fetching {STATUS_URL}")
    text = fetch_article_text(STATUS_URL)

    report_date = extract_report_date(text) or datetime.date.today().strftime("%Y-%m-%d")
    print(f"[scrape_eskom] Detected report date: {report_date}")

    existing = load_existing_dates(CSV_PATH)
    if report_date in existing:
        print(f"[scrape_eskom] Date {report_date} already in CSV — skipping.")
        return

    eaf_ytd        = extract_eaf_ytd(text)
    uclf_week      = extract_uclf_week(text)
    pclf_week      = extract_pclf_week(text)
    unplanned_mw   = extract_unplanned_mw(text)
    diesel_weekly  = extract_diesel_weekly(text)
    consec_days    = extract_consec_days(text)
    eaf70_count    = extract_eaf70_count(text)
    fy             = determine_financial_year(report_date)

    row = {
        "report_date":        report_date,
        "week_start":         "",
        "week_end":           "",
        "financial_year":     fy,
        "eaf_period_pct":     "",
        "eaf_period_type":    "",
        "eaf_ytd_pct":        eaf_ytd if eaf_ytd is not None else "",
        "uclf_week_pct":      uclf_week if uclf_week is not None else "",
        "pclf_week_pct":      pclf_week if pclf_week is not None else "",
        "unplanned_mw_avg":   unplanned_mw if unplanned_mw is not None else "",
        "diesel_weekly_mzar": diesel_weekly if diesel_weekly is not None else "",
        "diesel_ytd_mzar":    "",
        "consec_days_no_ls":  consec_days if consec_days is not None else "",
        "eaf70_count_ytd":    eaf70_count if eaf70_count is not None else "",
        "disputed":           "FALSE",
        "notes":              "Auto-scraped",
    }

    print(f"[scrape_eskom] Extracted: {json.dumps({k:v for k,v in row.items() if v != ''}, indent=2)}")

    write_header = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        fieldnames = list(row.keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    print(f"[scrape_eskom] Appended row for {report_date} to {CSV_PATH}")


if __name__ == "__main__":
    scrape_and_append()
