# Research guide

This guide is for journalists and researchers using the `congress_jobs.db` SQLite database produced by this repository. It covers the schema, the two web interfaces, the job classifier, and example queries.

## Database overview

After running `python init_database.py` (see the [README](../README.md) for setup), you have a SQLite database with several tables:

| Table | What it holds |
| --- | --- |
| `jobs` | Deduplicated unique listings, one row per distinct job. Includes posting history (`first_posted`, `last_posted`, `times_posted`) and enriched fields (`party`, `state`, `district`, `legislator_id`). |
| `job_postings` | Every individual appearance of a job in a bulletin. Use this for time-series and reposting analysis. |
| `legislators` | Current House members (loaded from [unitedstates/congress-legislators](https://github.com/unitedstates/congress-legislators)). |
| `raw_jobs` | Raw JSON of every loaded record, for forensic queries. |
| `office_name_variants` | Cache of fuzzy-matched office-name → legislator mappings. |

Two views make most queries easier:

- `active_jobs` — currently active listings joined to legislator data.
- `job_timeline` — chronological view of every posting.

The full schema lives in [`schema.sql`](../schema.sql).

### Deduplication and enrichment

Each listing is hashed on `office + title + description-snippet` (`dedup_key`). When the same job appears in a later bulletin it bumps `times_posted` and updates `last_posted` instead of creating a new row.

Enrichment links each job to a House member by extracting state/district from the office name (e.g. `(CA-43)`) and fuzzy-matching surnames. The current rate is ~37%; committee jobs and oddly-formatted office names account for most misses.

## Querying the database

The dataset is a SQLite file. Point any SQL tool at `congress_jobs.db` — the
command-line `sqlite3`, [DB Browser for SQLite](https://sqlitebrowser.org/),
DuckDB, pandas, R's `RSQLite`, etc. The `web_interface.py` Flask app
(`python web_interface.py`, http://localhost:5000) provides a job-seeker UI
on top of the same database; it is not intended for analytical use.

## Example queries

```sql
-- Hardest-to-fill positions (reposted ≥ 5 times)
SELECT position_title, office, times_posted, first_posted, last_posted
FROM jobs
WHERE times_posted >= 5
ORDER BY times_posted DESC;

-- Hiring volume by party
SELECT party, COUNT(*) AS jobs
FROM jobs
WHERE party IS NOT NULL
GROUP BY party;

-- Reposting rates by position type
SELECT LOWER(position_title) AS title, AVG(times_posted) AS avg_reposts, COUNT(*) AS n
FROM jobs
GROUP BY LOWER(position_title)
HAVING n >= 10
ORDER BY avg_reposts DESC
LIMIT 25;

-- Jobs newly posted in the last 30 days
SELECT bulletin_date, position_title, office, location
FROM job_timeline
WHERE bulletin_date >= date('now', '-30 days')
ORDER BY bulletin_date DESC;
```

## Job classifier

`job_classifier.py` adds a `job_category` field to each listing in `json/`, using Gemini to assign one of:

- **administrative** — office management, scheduling, HR, finance, operations
- **legislative** — policy research, bill analysis, committee work, legal counsel
- **communications** — press, media, social, public outreach
- **constituent_services** — casework, community engagement, district representation

```bash
uv run python job_classifier.py        # classify everything in json/ (skips already-classified files)
uv run python test_classifier.py       # smoke test on a small sample
uv run python analyze_classifications.py  # writes summary report + charts to analysis_reports/
```

The script is rate-limited (2s/job, 5s/file). Roughly 45–60 minutes for 1,000 jobs.

## Loading new data

```bash
python db_loader.py --load-file path/to/new_jobs.json
python db_loader.py --load-dir json/
python db_loader.py --stats
```

The loader is idempotent: rerunning on the same files updates posting history rather than creating duplicates.

## Known limitations

These are areas where the dataset is currently less useful than it could be — improvements are tracked separately and welcomed as PRs.

- **Salaries are free text.** `salary_info` ranges from `"$60,000-$75,000"` to `"Commensurate with experience"` to `null`. There is no structured `salary_min` / `salary_max` field yet.
- **Application deadlines are unstructured.** Close dates appear in description prose; there is no `deadline_date` column.
- **Locations are not normalized.** `"DC"`, `"Washington, DC"`, `"District Office"`, and `"Las Vegas, NV"` all coexist.
- **Status is static.** Schema has `status` (active/filled/removed) but no sweep currently retires stale postings, so time-to-fill analysis is not yet possible.
- **Enrichment ~37%.** Committee jobs and unusual office spellings frequently fail to match a legislator.

## File structure cheat-sheet

```
house-jobs/
├── input/                # PDFs (committed)
├── output/               # text extracted from PDFs
├── json/                 # parsed listings, one file per bulletin
├── parser.py             # PDF→JSON (Gemini 2.5 Pro)
├── job_classifier.py     # adds job_category
├── analyze_classifications.py
├── schema.sql
├── init_database.py      # builds congress_jobs.db
├── db_loader.py
├── web_interface.py      # job-board interface
└── congress_jobs.db
```
