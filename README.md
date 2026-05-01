# house-jobs

Tools and a public archive for U.S. House of Representatives **job and internship announcements**. The Office of the Chief Administrative Officer publishes weekly bulletins as PDFs; this repository archives them, extracts text, parses each listing into structured JSON with an LLM, and loads everything into a deduplicated SQLite database enriched with party/district data.

Companion blog post: <https://thescoop.org/archives/2025/02/28/turning-congressional-job-listings-into-data/index.html>

## Pipeline

```
PDF  →  pdftotext  →  parser.py (LLM)  →  JSON  →  db_loader.py  →  SQLite
input/    output/        json/                       congress_jobs.db
```

- `input/` — original PDFs, committed for provenance.
- `output/` — extracted text, produced automatically by GitHub Actions.
- `json/` — structured listings, one file per bulletin.
- `congress_jobs.db` — SQLite database with deduplication, posting history, and legislator enrichment.

## Quick start

```bash
# 1. Install
uv sync

# 2. Get House member data (one-time, used for party/district enrichment)
git clone --depth 1 https://github.com/unitedstates/congress-legislators.git /tmp/congress-legislators

# 3. Build the database
python init_database.py

# 4. Explore
python web_interface.py        # http://localhost:5000 — job-board UI
# or query congress_jobs.db directly with sqlite3 / your tool of choice
```

To process a new bulletin:

```bash
pdftotext -layout input/<file>.pdf output/<file>.txt
python parser.py                       # writes json/<file>.json
python job_classifier.py               # adds job_category to each listing (optional)
python db_loader.py --load-dir json/   # loads + dedupes + enriches
```

## Example listing

```json
{
  "id": "MEM-458-24",
  "position_title": "District Representative",
  "office": "Congressman Steven Horsford",
  "location": "North Las Vegas, Nevada",
  "posting_date": "2024-11-04",
  "description": "...",
  "responsibilities": ["..."],
  "qualifications": ["..."],
  "how_to_apply": "Submit resume and cover letter to NV04Resume@mail.house.gov",
  "salary_info": "Commensurate with experience",
  "contact": "NV04Resume@mail.house.gov",
  "equal_opportunity": "...",
  "job_category": "constituent_services"
}
```

`job_category` is one of `administrative`, `legislative`, `communications`, `constituent_services`. The parser produces every other field directly from the bulletin.

## Documentation

- [docs/research.md](docs/research.md) — research guide (database schema, query examples, classifier).
- [CLAUDE.md](CLAUDE.md) — developer reference for the codebase.

## Contributing

If you have House job-announcement PDFs or emails not in this collection, please send them to `dwillis+housejobs@gmail.com`.

## License

MIT — see [LICENSE](LICENSE).
