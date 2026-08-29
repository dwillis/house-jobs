# House Jobs

Tools and a public archive for U.S. House of Representatives **job and internship announcements**. The Office of the Chief Administrative Officer publishes weekly bulletins as PDFs; this repository archives them, extracts text, and parses each listing into structured JSON with an LLM. The `json_v3/` directory is the current corpus — every one of ~1,250 weekly bulletins since 2013, parsed and classified into 25,655 listings.

Companion blog post: <https://thescoop.org/archives/2025/02/28/turning-congressional-job-listings-into-data/index.html>

## Pipeline

```
PDF  →  pdftotext  →  pipeline/ (DSPy + GEPA, glm-5.2)  →  json_v3/  →  skills/ (NLP analysis)
input/    output/        parse + classify
```

- `input/` — original PDFs, committed for provenance.
- `output/` — extracted text, produced automatically by GitHub Actions.
- `json_v3/` — structured, classified listings, one file per bulletin (~1,250 files, 2013–present).
- `pipeline/` — the DSPy program (extraction + classification) with GEPA-optimized prompts; see [CLAUDE.md](CLAUDE.md).
- `skills/` — NLP analysis: skill extraction, embeddings, and semantic clustering.

Earlier corpora `json/` (Gemini) and `json_qwen/` (Qwen), and the `parser.py` / `job_classifier.py` scripts that produced them, are retained as legacy.

## Quick start

```bash
# Install dependencies
uv sync

# Set your Ollama Cloud key (used by the pipeline)
echo "OLLAMA_API_KEY=..." > .env    # key from https://ollama.com/settings/keys
```

To process new bulletins (parsing + classification via the current pipeline):

```bash
pdftotext -layout input/<file>.pdf output/<file>.txt
uv run python -m pipeline.run_parse    --out json_v3 --files <file>.txt   # extract listings
uv run python -m pipeline.run_classify --dir json_v3                      # add job_category
```

To run NLP analysis on the full corpus:

```bash
# Regex-based skill extraction and trend charts
uv run python skills/skill_extractor.py

# Semantic clustering via Ollama embeddings + UMAP + HDBSCAN
# Requires: ollama serve (uses qwen3-embedding:latest by default)
uv run python skills/cluster_jobs.py --dir json_v3
uv run python skills/cluster_jobs.py --dir json_v3 --model embeddinggemma   # faster alternative
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

`job_category` is one of `administrative`, `legislative`, `communications`, `constituent_services`. The pipeline produces every other field directly from the bulletin. Listings in `json_v3/` also carry `source_model` and `parsed_at` provenance fields. `office` and `salary_info` are `null` when the bulletin gives no resolvable member/committee name or no dollar-figure salary, respectively.

## Documentation

- [docs/research.md](docs/research.md) — research guide (query examples, classifier).
- [CLAUDE.md](CLAUDE.md) — developer reference for the codebase.

## Contributing

If you have House job-announcement PDFs or emails not in this collection, please send them to `dwillis+housejobs@gmail.com`.

## License

MIT — see [LICENSE](LICENSE).
