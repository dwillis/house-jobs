# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository processes U.S. House of Representatives job and internship announcements from PDF files into structured data. The system extracts text from PDFs, uses LLMs to parse listings into JSON, loads them into a SQLite database with deduplication and enrichment (party/district), and provides multiple interfaces for research and exploration.

**Key Data Flow:**
```
PDF → Text Extraction (pdftotext) → LLM Parsing → JSON → Database Loading → Web Interfaces
```

## Development Environment

**Python Version:** >=3.12 (specified in pyproject.toml)

**Package Management:** Uses `uv` for modern Python dependency management. The project has both legacy Pipfile and modern pyproject.toml.

**Install dependencies:**
```bash
uv sync
# Or legacy approach:
pip install -r requirements.txt
```

## Core Components & Architecture

### 1. PDF to Text Conversion
- **Location:** Handled by GitHub Actions (see `.github/`)
- **Tool:** `pdftotext` utility
- **Input:** PDF files in `input/` directory
- **Output:** Text files in `output/` directory with date-based filenames

### 2. LLM-based Parsers

**Parser 1** (`parser.py`):
- Legacy implementation using Gemini 1.5 Flash
- Processes entire text files at once
- Basic approach, kept for reference

**Parser 2** (`parser2.py`) - RECOMMENDED:
- Improved implementation using Gemini 2.0 Flash
- **Key Innovation:** Splits text into chunks based on job ID patterns (MEM-xxx-yy)
- Processes each job listing separately for better accuracy
- Better error handling and UTF-8 character normalization
- **Output:** JSON files in `json_gemini_flash/` directory

**Run Parser:**
```bash
python parser2.py
```

**Important Notes:**
- Parsers use the `llm` library with subprocess calls
- Rate limiting built in (7-8 second delays between chunks)
- Requires Gemini API access configured in `llm` tool

### 3. Job Classification System

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

### 4. Database System

**Database:** SQLite (`congress_jobs.db` or `house_jobs.db`)

**Key Tables:**
- `jobs` - Deduplicated master job listings
- `job_postings` - Individual postings tracking each bulletin appearance
- `legislators` - Current House members with party/district from congress-legislators repo
- `raw_jobs` - Raw JSON before processing
- `office_name_variants` - Office name normalization mapping

**Views:**
- `active_jobs` - Currently active listings with enriched legislator data
- `job_timeline` - Timeline of all postings for research

**Schema:** Defined in `schema.sql`

**Critical Feature - Deduplication:**
The system uses a `dedup_key` (MD5 hash of normalized office + title + description snippet) to identify the same job posted multiple times. This enables tracking:
- `times_posted` - How many times a job has appeared
- `first_posted` / `last_posted` - Temporal tracking
- Individual posting history in `job_postings` table

**Critical Feature - Enrichment:**
The `db_loader.py` implements fuzzy matching to link job listings to House members:
- Extracts state/district from office names (e.g., "(CA-43)")
- Fuzzy matches office names to legislator names
- Adds `party`, `state`, `district`, `legislator_id` fields
- Caches matches for performance

### 5. Database Initialization & Loading

**Initial Setup:**
```bash
# Clone legislator data (required for enrichment)
git clone --depth 1 https://github.com/unitedstates/congress-legislators.git /tmp/congress-legislators

# Initialize database with all existing data
python init_database.py
```

**Load Additional Data:**
```bash
# Load single file
python db_loader.py --load-file path/to/new_jobs.json

# Load entire directory
python db_loader.py --load-dir json_gemini_flash/

# View statistics
python db_loader.py --stats
```

**db_loader.py Architecture:**
- Context manager pattern (`with CongressionalJobsDB(db_path) as db`)
- Automatic deduplication on load
- Automatic legislator matching and enrichment
- Handles various JSON field formats with normalization
- Updates existing jobs on repost, creates new entries otherwise

### 6. Web Interfaces

Two different approaches for different use cases:

**Datasette Interface** (`run_datasette.py`) - RECOMMENDED for research:
```bash
python run_datasette.py
# Visit http://localhost:8001
```
- Faceted search on any column
- Full SQL query interface
- Built-in CSV/JSON export
- Pre-built research queries (defined in `metadata.yml`)
- Automatic API endpoints
- Zero code maintenance
- **Use when:** Doing research, need SQL access, want exports

**Flask Interface** (`web_interface.py`) - For custom job board:
```bash
python web_interface.py
# Visit http://localhost:5000
```
- Custom-designed job search UI
- Job seeker-friendly interface
- Modal dialogs for job details
- **Use when:** Need custom branding, building public job board

**Configuration:** Datasette queries and metadata are defined in `metadata.yml`

## Common Development Tasks

### Running Tests
```bash
# Test classifier on sample data
python test_classifier.py

# Test validation
python test.py
```

### Processing New PDF Files

1. Add PDF files to `input/` directory
2. Extract text (if not using GitHub Actions):
   ```bash
   pdftotext -layout input/filename.pdf output/filename.txt
   ```
3. Parse with LLM:
   ```bash
   python parser2.py
   ```
4. Optionally classify jobs:
   ```bash
   uv run python job_classifier.py
   ```
5. Load into database:
   ```bash
   python db_loader.py --load-dir json_gemini_flash/
   ```

### Validating JSON Output
```bash
python validate.py
```

### Creating CSV Export
```bash
python make_csv.py
```

## Important Implementation Details

### UTF-8 and Character Normalization
The PDFs often contain smart quotes, em-dashes, and other non-ASCII characters. Both parsers include system prompts to normalize these to UTF-8 equivalents. Pay attention to this when modifying parser prompts.

### Job ID Pattern
House job listings use the pattern `MEM-XXX-YY` where:
- `MEM` = Member office
- `XXX` = Sequential number
- `YY` = Two-digit year

This pattern is used in `parser2.py` to split text into chunks: `re.split(r'(?=MEM-)', text)`

### Date Extraction from Filenames
The `db_loader.py` includes logic to extract dates from various filename formats:
- `YYYY_MM_DD` (e.g., 2025_01_12)
- `MM-DD-YY` (e.g., 01-06-14)
- `M.DD.YYYY` (e.g., 1.26.2015)

Add new patterns to `_extract_date_from_filename()` if needed.

### Fuzzy Matching Algorithm
Office name matching in `db_loader.py` uses:
- State/district extraction from patterns like "(PA-2)"
- Sequence matching on normalized office names
- Last name substring matching
- Minimum confidence threshold of 40.0
- Committee detection to avoid false matches

### Rate Limiting
Both parsers and the classifier include sleep() calls to respect API rate limits:
- `parser.py`: 7 seconds between files
- `parser2.py`: 8 seconds between chunks, 5 seconds between files
- `job_classifier.py`: 2 seconds between jobs, 5 seconds between files

Adjust these if you hit rate limits or want faster processing.

## File Structure

```
house-jobs/
├── input/              # PDF files (tracked in git)
├── output/             # Extracted text files (tracked in git)
├── json_gemini_flash/  # Parsed JSON output (tracked in git)
├── json_gemini_pro/    # Alternative parser output
├── json_classified/    # Classified job output
│
├── parser.py           # Legacy parser (Gemini 1.5)
├── parser2.py          # Recommended parser (Gemini 2.0)
├── job_classifier.py   # Job categorization
│
├── schema.sql          # Database schema
├── init_database.py    # Initial database setup
├── db_loader.py        # Core database loading logic
│
├── run_datasette.py    # Datasette interface (research)
├── web_interface.py    # Flask interface (job board)
├── metadata.yml        # Datasette configuration
├── templates/          # Flask templates
│
├── validate.py         # JSON validation
├── make_csv.py         # CSV export utility
├── test.py             # Tests
├── test_classifier.py  # Classifier tests
└── analyze_classifications.py  # Classification analysis
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

### Database Job Record
The database normalizes this into multiple tables with additional enriched fields (`party`, `state`, `district`, `legislator_id`, `times_posted`, `first_posted`, `last_posted`, etc.).

## GitHub Actions

The repository uses GitHub Actions for automated processing (see `.github/` directory). Text extraction from PDFs happens automatically on push.

## External Dependencies

- **congress-legislators repo:** Required for legislator data enrichment. Must be cloned to `/tmp/congress-legislators` before running `init_database.py`
- **pdftotext:** System utility for PDF text extraction
- **llm library:** Simon Willison's tool for LLM interaction, requires API key configuration
- **Datasette:** For research interface
- **sqlite-utils:** For database utilities

## Notes for AI Assistants

- When modifying parsers, always test on a small subset of files first
- The database system is designed to be idempotent - loading the same data twice is safe
- Enrichment rate is typically ~37% due to committee jobs and imperfect name matching
- The project tracks both Members (staff positions) and Internships separately
- File naming convention: `HVAPS Template_{Members|Internships}_YYYY_MM_DD.pdf`
