# House Jobs

Tools and a public archive for U.S. House of Representatives **job and internship announcements**. The Office of the Chief Administrative Officer publishes weekly bulletins as PDFs; this repository archives them, extracts text, and parses each listing into structured JSON with an LLM. The `json/` directory is the primary corpus — over 12 years of weekly bulletins dating back to 2013.

Companion blog post: <https://thescoop.org/archives/2025/02/28/turning-congressional-job-listings-into-data/index.html>

## Pipeline

```
PDF  →  pdftotext  →  parser.py (LLM)  →  JSON  →  skills/ (NLP analysis)
input/    output/        json/
```

- `input/` — original PDFs, committed for provenance.
- `output/` — extracted text, produced automatically by GitHub Actions.
- `json/` — structured listings, one file per bulletin (~600 files, 2013–present).
- `skills/` — NLP analysis: skill extraction, embeddings, and semantic clustering.

## Quick start

```bash
# Install dependencies
uv sync
```

To process a new bulletin:

```bash
pdftotext -layout input/<file>.pdf output/<file>.txt
uv run python parser.py                  # writes json/<file>.json
uv run python job_classifier.py          # adds job_category to each listing (optional)
```

To run NLP analysis on the full corpus:

```bash
# Regex-based skill extraction and trend charts
uv run python skills/skill_extractor.py

# Semantic clustering via Ollama embeddings + UMAP + HDBSCAN
# Requires: ollama serve (uses qwen3-embedding:latest by default)
uv run python skills/cluster_jobs.py
uv run python skills/cluster_jobs.py --model embeddinggemma   # faster alternative
```

## NLP Analysis (`skills/`)

**Skill extraction** (`skills/skill_extractor.py`) matches 80+ named skills across categories (software tools, languages, policy areas, communications, clearances) against deduplicated job text. Counts are normalised by total jobs per period so trend charts reflect actual demand change rather than corpus growth.

Outputs: `skills_raw.csv`, `skill_trends.csv`, `skill_trends.png`, `skill_categories.png`, `skill_emerging.png`.

**Semantic clustering** (`skills/cluster_jobs.py`) embeds each job description via Ollama, reduces to 2-D with UMAP, and clusters with HDBSCAN. Clusters are auto-labelled by tf-idf top terms. Embeddings are cached locally and invalidated automatically when the corpus or model changes.

Outputs: `job_embeddings.csv`, `clusters.png`, `cluster_drift.png`, `cluster_summary.txt`.

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

- [docs/research.md](docs/research.md) — research guide (query examples, classifier).
- [CLAUDE.md](CLAUDE.md) — developer reference for the codebase.

## Contributing

If you have House job-announcement PDFs or emails not in this collection, please send them to `dwillis+housejobs@gmail.com`.

## License

MIT — see [LICENSE](LICENSE).
