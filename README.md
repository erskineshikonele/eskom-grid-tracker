# ⚡ Eskom Grid Recovery Tracker

A data journalism dashboard tracking South Africa's national electricity grid recovery in real time — EAF trends, unplanned outages, diesel expenditure, and the load-shedding-free streak counter.

**Live dashboard:** https://erskineshikonele.github.io/eskom-grid-tracker

---

## What it tracks

| Metric | Description |
|---|---|
| **EAF (YTD %)** | Energy Availability Factor — % of time the fleet is available to generate. Target: 70% |
| **UCLF (weekly %)** | Unplanned Capacity Loss Factor — % of capacity lost to unexpected breakdowns |
| **PCLF (weekly %)** | Planned Capacity Loss Factor — scheduled maintenance as % of capacity |
| **Unplanned outages MW** | Average MW offline due to breakdowns in the measurement week |
| **Diesel expenditure** | Weekly and year-to-date diesel spend on OCGT peaker plants (R millions) |
| **Streak counter** | Consecutive days without load shedding, live and animated |

---

## Data source

All data is sourced from Eskom's official weekly Friday press releases at [eskom.co.za/power-system-status](https://www.eskom.co.za/power-system-status/).

The scraper (`scripts/scrape_eskom.py`) runs every Friday at 18:00 SAST via GitHub Actions. It fetches the latest press release, extracts structured metrics via regex, and appends a new row to `data/eskom_grid_metrics.csv`.

---

## Data integrity note — Week 52, 2025

The 26 December 2025 data point is flagged **⚠ DISPUTED** in the dashboard.

Energy analyst [Chris Yelland](https://eebusiness.co.za) publicly questioned an anomalous spike in that week's figures: the weekly EAF reportedly jumped to over 74% while unplanned outages plunged to ~16%, a ~34% year-on-year improvement. Yelland described this as "atypical" and statistically anomalous relative to every surrounding week.

Eskom chairman Mteto Nyati defended the data but did not identify which specific generating units returned online to cause the jump. The dashboard surfaces this dispute rather than silently presenting the figures as reliable — because accurate data journalism requires flagging methodological uncertainty, not hiding it.

---

## Architecture

Same proven pattern as the [SA Lotto Predictor](https://erskineshikonele.github.io/sa-lotto-predictor):

```
GitHub Actions (cron: Friday 16:00 UTC)
    └── scripts/scrape_eskom.py
        └── data/eskom_grid_metrics.csv  ← source of truth
            └── index.html (Chart.js + PapaParse dashboard)
                └── GitHub Pages (auto-deploy on push to main)
```

No backend, no database, no runtime cost. Pure static files.

---

## Local development

```bash
# Clone and serve locally
git clone https://github.com/ErskineShi/eskom-grid-tracker.git
cd eskom-grid-tracker
python -m http.server 8000
# Open http://localhost:8000
```

To run the scraper manually:
```bash
pip install requests
python scripts/scrape_eskom.py
```

---

## Historical backfill

`data/eskom_grid_metrics.csv` was seeded with **23 data points** spanning September 2025 to June 2026, extracted manually from archived Eskom press releases. Each row was verified against the original source URL. The Week 52 disputed flag is documented with the original Yelland quote.

---

Built by [Erskine Shikonele](https://www.linkedin.com/in/erskine-shikonele) · Data: Eskom (official press releases) · Stack: Python · GitHub Actions · Chart.js · GitHub Pages
