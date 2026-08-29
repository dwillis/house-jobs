# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository processes U.S. House of Representatives job and internship announcements from PDF files into structured data. The system extracts text from PDFs, uses LLMs to parse listings into JSON, loads them into a SQLite database with deduplication and enrichment (party/district), and provides multiple interfaces for research and exploration.

**Key Data Flow:**
```
PDF → Text Extraction (pdftotext) → DSPy/GEPA pipeline (parse + classify) → json_v3/ → skills/ (NLP Analysis)
```

The current parser/classifier is the `pipeline/` package (see "DSPy + GEPA Pipeline" below), which produced `json_v3/`. The older `parser.py` + `job_classifier.py` scripts and the `json/` / `json_qwen/` corpora are retained as legacy.

## Development Environment

**Python Version:** >=3.12 (specified in pyproject.toml)

**Package Management:** Uses `uv`. Dependencies are declared in `pyproject.toml`.

**Install dependencies:**
```bash
uv sync
```

## Core Components & Architecture

### 1. PDF to Text Conversion
- **Location:** Handled by GitHub Actions (see `.github/`)
- **Tool:** `pdftotext` utility
- **Input:** PDF files in `input/` directory
- **Output:** Text files in `output/` directory with date-based filenames

### 2. LLM-based Parser (legacy — superseded by `pipeline/`)

**`parser.py`** uses the `llm` Python API with `gemini-2.5-pro`:
- Splits each bulletin's text into chunks at MEM-XXX-YY job-ID boundaries
- Processes each chunk independently for accuracy
- UTF-8 normalization, structured JSON output
- Processes both Member and Internship bulletins
- **Output:** JSON files in `json/` directory (one per bulletin)

**Run:**
```bash
python parser.py
```

**Important Notes:**
- Requires Gemini API access configured via `llm keys set gemini`
- Rate limiting built in (8s between chunks, 5s between files)
- Skips bulletins already present in `json/`

### 3. Job Classification System (legacy — superseded by `pipeline/run_classify.py`)

**Script:** `job_classifier.py`

**Purpose:** Classifies jobs into four categories:
- `administrative` - Office management, HR, scheduling, administrative support
- `legislative` - Policy research, bill analysis, committee work, legal research
- `communications` - Press, media relations, social media, public outreach
- `constituent_services` - Casework, community engagement, district representation

**Architecture:**
- Uses `uv run` for execution
- Modifies JSON files in-place, adding `job_category` field
- Uses Gemini 2.5 Flash for classification
- Skips files that already have classifications

**Run Classifier:**
```bash
uv run python job_classifier.py
# or
./job_classifier.py
```

### 4. DSPy + GEPA Pipeline (`pipeline/`) — current parser

The `pipeline/` package is the current parsing and classification path, superseding `parser.py` and `job_classifier.py` (both retained as legacy). It uses DSPy modules (extraction + classification) whose prompts are optimized by GEPA, running `glm-5.2` on Ollama Cloud directly (`https://ollama.com/v1`, requires `OLLAMA_API_KEY` in `.env`). It has produced `json_v3/` — all 1,252 bulletins parsed into 25,655 job listings, every one classified (0 failures).

- `pipeline/lm.py` — `dspy.LM` config for Ollama Cloud (loads `.env`)
- `pipeline/schema.py` — Pydantic `JobListing` (same 12-field schema) and `Category`
- `pipeline/signatures.py` — `ExtractJobs`/`ClassifyJob` DSPy signatures and modules
- `pipeline/metric.py` — hybrid GEPA metric (programmatic formatting checks + gold-set field scoring); `--self-test` for sanity
- `pipeline/goldset.py` — sample/prefill gold examples in `gold/extraction/` (30) and `gold/classification/labels.jsonl` (120); `sample-classify` supports `--dir/--append/--balanced`
- `pipeline/optimize.py` — GEPA runs (`smoke-test`, `extract`, `classify`); saves compiled prompts to `pipeline/compiled/`
- `pipeline/run_parse.py` — bulk re-parse into `json_v3/` (concurrent, resumable, atomic writes, logs failures to `_failures.jsonl`)
- `pipeline/run_classify.py` — bulk classification over `json_v3/` (`--eval` checks accuracy against gold labels first)

**Compiled prompts** live in `pipeline/compiled/{extractor,classifier}.json` and are committed — they are the reproducible "prompt". Note both have been lightly hand-edited to correct GEPA artifacts (e.g. an ISO-date instruction; a generic-intern classification rule); regenerating them via `optimize.py` will overwrite those edits.

**Budgeting:** Ollama Cloud has a weekly call cap. Both runners take `--max-calls N` to stop under budget (resumable — re-run to continue) and `--max-tokens` (classify defaults to 16000 so glm-5.2's reasoning tokens don't truncate the answer). A full parse is ~25.5k calls; classification another ~25.7k.

**Reproduce from scratch:**
```bash
uv run python -m pipeline.optimize smoke-test          # verify OLLAMA_API_KEY / endpoint
uv run python -m pipeline.goldset sample --n 30
uv run python -m pipeline.goldset prefill              # fills from json_qwen/json where possible
# hand-correct any gold/extraction/*.json still marked "TODO"
uv run python -m pipeline.goldset sample-classify --n 120 --dir json_v3 --balanced
# hand-correct gold/classification/labels.jsonl
uv run python -m pipeline.optimize extract
uv run python -m pipeline.optimize classify
uv run python -m pipeline.run_parse   --out json_v3 --max-calls 6000   # repeat until done
uv run python -m pipeline.run_classify --eval                          # check accuracy
uv run python -m pipeline.run_classify --max-calls 6000                # repeat until done
```

**Quality of the current `json_v3/` run:** 0 empty responsibilities/qualifications, 0 non-ISO dates, no residual OCR ligature damage; classifier ~89% on the 120-label gold set. Two deliberate trade-offs: `office` is null (~41%) rather than free text when no named member/committee is resolvable, and `salary_info` is null (~93%) unless a dollar figure is stated (phrases like "unpaid"/"commensurate" are dropped).

Each `json_v3/` listing also carries provenance fields `source_model` and `parsed_at` beyond the 12-field schema.

## Common Development Tasks

### Running Tests
```bash
# Test classifier on sample data
python test_classifier.py
```

### Processing New PDF Files

1. Add PDF files to `input/` directory
2. Extract text (if not using GitHub Actions):
   ```bash
   pdftotext -layout input/filename.pdf output/filename.txt
   ```
3. Parse with LLM:
   ```bash
   python parser.py
   ```
4. Optionally classify jobs:
   ```bash
   uv run python job_classifier.py
   ```
5. Load into database:
   ```bash
   python db_loader.py --load-dir json/
   ```

### Validating JSON Output
```bash
python validate.py json/          # report-only
python validate.py json/ --delete # destructive
```

## Important Implementation Details

### UTF-8 and Character Normalization
The PDFs often contain smart quotes, em-dashes, and other non-ASCII characters. The parser system prompt normalizes these to UTF-8 equivalents — preserve those instructions when modifying the prompt.

### Job ID Pattern
House job listings use the pattern `MEM-XXX-YY` where:
- `MEM` = Member office
- `XXX` = Sequential number
- `YY` = Two-digit year

This pattern is used in `parser.py` to split text into chunks: `re.split(r'(?=MEM-)', text)`

### Date Extraction from Filenames
The `db_loader.py` includes logic to extract dates from various filename formats:
- `YYYY_MM_DD` (e.g., 2025_01_12)
- `MM-DD-YY` (e.g., 01-06-14)
- `M.DD.YYYY` (e.g., 1.26.2015)

Add new patterns to `_extract_date_from_filename()` if needed.

### Rate Limiting
The parser and classifier include sleep() calls to respect API rate limits:
- `parser.py`: 8 seconds between chunks, 5 seconds between files
- `job_classifier.py`: 2 seconds between jobs, 5 seconds between files

Adjust these if you hit rate limits or want faster processing.

## File Structure

```
house-jobs/
├── input/              # PDF files (tracked in git)
├── output/             # Extracted text files (tracked in git)
├── json/               # Parsed JSON output — primary corpus (tracked in git)
├── json_qwen/          # Alternate parse corpus (Qwen model, includes internships)
├── json_v3/            # DSPy/GEPA pipeline output — future canonical corpus (in progress)
├── gold/               # Hand-corrected examples for GEPA optimization
│
├── parser.py           # Bulletin parser (Gemini 2.5 Pro, llm Python API)
├── job_classifier.py   # Job categorization (Gemini 2.5 Flash)
├── pipeline/           # DSPy + GEPA parsing/classification pipeline (see above)
├── config.py           # Shared path/db constants
│
├── validate.py         # JSON validation (report-only by default)
├── compare_parses.py   # Compare outputs across parse runs
├── find_duplicates.py  # Identify duplicate listings
├── analyze_classifications.py  # Classification analysis
├── test_classifier.py  # Classifier tests
│
├── house_jobs.csv      # Flattened export
├── duplicates.csv      # Duplicate listing report
├── data/
│   └── duplicates.csv
├── docs/
│   └── research.md
│
└── skills/             # NLP analysis
    ├── skill_extractor.py      # Regex-based skill extraction + trend charts
    ├── cluster_jobs.py         # Ollama embeddings + UMAP + HDBSCAN clustering
    ├── skills_raw.csv          # Output: skill × job mentions (gitignored)
    ├── skill_trends.csv        # Output: annual skill pivot
    ├── skill_trends.png        # Output: trend chart
    ├── skill_categories.png    # Output: category bar chart
    ├── skill_emerging.png      # Output: prevalence-change chart
```

## Data Formats

### JSON Job Listing Structure
```json
{
  "id": "MEM-458-24",
  "position_title": "District Representative",
  "office": "Congressman Steven Horsford",
  "location": "North Las Vegas, Nevada",
  "posting_date": "2024-11-04",
  "description": "Full job description...",
  "responsibilities": ["Array", "of", "strings"],
  "qualifications": ["Array", "of", "strings"],
  "how_to_apply": "Application instructions",
  "salary_info": "Commensurate with experience",
  "contact": "email@mail.house.gov",
  "equal_opportunity": "Equal opportunity statement",
  "job_category": "constituent_services"
}
```

## GitHub Actions

The repository uses GitHub Actions for automated processing (see `.github/` directory). Text extraction from PDFs happens automatically on push.

## External Dependencies

- **congress-legislators repo:** Required for legislator data enrichment. Must be cloned to `/tmp/congress-legislators` before running `init_database.py`
- **pdftotext:** System utility for PDF text extraction
- **llm library:** Simon Willison's tool for LLM interaction, requires API key configuration

## Notes for AI Assistants

- When modifying parsers, always test on a small subset of files first
- The database system is designed to be idempotent - loading the same data twice is safe
- Enrichment rate is typically ~37% due to committee jobs and imperfect name matching
- The project tracks both Members (staff positions) and Internships separately
- File naming convention: `HVAPS Template_{Members|Internships}_YYYY_MM_DD.pdf`
