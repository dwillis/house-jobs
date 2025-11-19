# Congressional Jobs Research Tool

A comprehensive research database and web interface for analyzing U.S. House of Representatives job listings from 2013-2025.

## Features

### Phase 1 Implementation ✅

- **Deduplication Pipeline**: Fuzzy matching on job ID, title, office, and description to identify unique positions
- **SQLite Database**: Fast, portable database with full indexing
- **Party/District Enrichment**: Automatic matching of job listings to current House members with party affiliation
- **Flexible JSON Loader**: Can load job data from any JSON source (currently supports LLM-extracted data)
- **Web Search Interface**: Full-featured search and browse interface with filtering
- **Timeline Tracking**: Track when jobs were first posted, last seen, and how many times reposted
- **Full-Text Search**: Search across job titles, offices, and descriptions

## Database Statistics

- **5,272** unique jobs (deduplicated from 10,016 postings)
- **439** current House members
- **37%** of jobs enriched with legislator party/district data
- **11+ years** of historical data (2013-2025)
- Party distribution: 87% Democrat, 13% Republican (of enriched jobs)

## Installation

### Prerequisites

- Python 3.7+
- Git

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Clone congress-legislators data
git clone --depth 1 https://github.com/unitedstates/congress-legislators.git /tmp/congress-legislators

# Initialize and populate the database
python init_database.py
```

This will:
1. Create the SQLite database (`congress_jobs.db`)
2. Load current House member data
3. Process all JSON files in `json_gemini_flash/`
4. Deduplicate and enrich the data
5. Display statistics

## Usage

### Web Interface

The easiest way to explore the data:

```bash
python web_interface.py
```

Then open http://localhost:5000 in your browser.

Features:
- Search by keyword across titles, offices, and descriptions
- Filter by party, state, and position type
- View detailed job information including responsibilities and qualifications
- See posting history (first posted, last posted, times reposted)

### Command-Line Interface

Load data from a JSON file:

```bash
python db_loader.py --db congress_jobs.db --load-file path/to/jobs.json
```

Load all JSON files from a directory:

```bash
python db_loader.py --db congress_jobs.db --load-dir json_gemini_flash/
```

View database statistics:

```bash
python db_loader.py --db congress_jobs.db --stats
```

Update legislator data:

```bash
python db_loader.py --db congress_jobs.db --legislators /tmp/congress-legislators/legislators-current.yaml
```

### Direct SQL Queries

The database can be queried directly with SQLite:

```bash
sqlite3 congress_jobs.db
```

Example queries:

```sql
-- Find all Legislative Director positions
SELECT position_title, office, party, first_posted
FROM jobs
WHERE position_title LIKE '%Legislative Director%'
ORDER BY first_posted DESC;

-- Count jobs by party and position
SELECT party, position_title, COUNT(*) as count
FROM jobs
WHERE party IS NOT NULL
GROUP BY party, LOWER(position_title)
ORDER BY count DESC
LIMIT 20;

-- Find most frequently reposted jobs
SELECT position_title, office, times_posted, first_posted, last_posted
FROM jobs
WHERE times_posted >= 5
ORDER BY times_posted DESC;

-- Jobs with salary information
SELECT position_title, office, salary_info, party
FROM jobs
WHERE salary_info IS NOT NULL AND salary_info != ''
ORDER BY last_posted DESC
LIMIT 50;

-- Use the active_jobs view
SELECT * FROM active_jobs
WHERE party = 'Democrat' AND state = 'CA'
LIMIT 10;
```

## Database Schema

### Main Tables

**legislators** - Current House members
- Bioguide ID, name, state, district, party
- Contact information (office, phone)
- Source: unitedstates/congress-legislators

**jobs** - Deduplicated unique jobs
- Core fields: position_title, office, location
- Enriched: legislator_id, state, district, party
- Temporal: first_posted, last_posted, times_posted
- Full job details: description, responsibilities, qualifications

**job_postings** - Individual appearances in bulletins
- Links to jobs table
- Tracks each bulletin/date a job appeared
- Historical snapshots of job details

**raw_jobs** - Original JSON data
- Preserves all source data
- Enables reprocessing if needed

### Views

**active_jobs** - Currently active listings with member info

**job_timeline** - Complete posting history for analysis

## Data Quality

### Enrichment Rate: 37.1%

Jobs are enriched with party/district data when the office name can be matched to a current House member.

**Reasons for incomplete enrichment:**
- Generic office names ("Committee on...", "Congressional Office")
- Members no longer in Congress
- Variations in office name formatting
- Committee positions (not tied to individual members)

### Deduplication Method

Jobs are deduplicated using:
1. Normalized office name
2. Position title (case-insensitive)
3. First 500 characters of description
4. MD5 hash for fast matching

**Reposting tracking:**
- `first_posted`: When job first appeared
- `last_posted`: Most recent appearance
- `times_posted`: Number of times reposted
- Can infer when positions were filled (stopped appearing)

## Research Applications

### Labor Market Analysis

```sql
-- Track hiring trends over time
SELECT
  strftime('%Y-%m', first_posted) as month,
  COUNT(*) as new_jobs,
  party
FROM jobs
WHERE party IS NOT NULL
GROUP BY month, party
ORDER BY month;

-- Identify positions with highest turnover
SELECT position_title, COUNT(*) as postings, AVG(times_posted) as avg_reposts
FROM jobs
GROUP BY LOWER(position_title)
HAVING COUNT(*) >= 10
ORDER BY avg_reposts DESC;
```

### Political Science Research

```sql
-- Compare hiring patterns by party
SELECT
  party,
  position_title,
  COUNT(*) as count,
  AVG(times_posted) as avg_reposts,
  COUNT(CASE WHEN salary_info IS NOT NULL THEN 1 END) * 100.0 / COUNT(*) as pct_with_salary
FROM jobs
WHERE party IS NOT NULL
GROUP BY party, LOWER(position_title)
HAVING COUNT(*) >= 5
ORDER BY count DESC;

-- State-level analysis
SELECT
  state,
  COUNT(*) as total_jobs,
  AVG(times_posted) as avg_reposts,
  MIN(first_posted) as earliest,
  MAX(last_posted) as latest
FROM jobs
WHERE state IS NOT NULL
GROUP BY state
ORDER BY total_jobs DESC;
```

### Career Intelligence

```sql
-- Find common requirements for a position type
SELECT
  position_title,
  qualifications_json,
  party,
  salary_info
FROM jobs
WHERE position_title LIKE '%Communications Director%'
AND qualifications_json != '[]';

-- Identify offices with frequent hiring
SELECT
  office,
  legislator_name,
  party,
  state,
  COUNT(*) as jobs_posted
FROM active_jobs
GROUP BY office
HAVING COUNT(*) >= 3
ORDER BY jobs_posted DESC;
```

## Loading Data from New Sources

The system can load job data from any JSON source. The expected format:

```json
[
  {
    "id": "MEM-123-24",
    "position_title": "Legislative Assistant",
    "office": "Congressman John Smith (CA-12)",
    "location": "Washington, DC",
    "posting_date": "2024-10-28",
    "description": "Full job description...",
    "responsibilities": ["Duty 1", "Duty 2"],
    "qualifications": ["Requirement 1", "Requirement 2"],
    "how_to_apply": "Send resume to...",
    "salary_info": "$60,000-$70,000",
    "contact": "jobs@mail.house.gov",
    "equal_opportunity": "EEO statement..."
  }
]
```

**Required fields:**
- `position_title` (jobs without titles are skipped)

**Optional fields:**
- All others (nulls are handled gracefully)
- `responsibilities` and `qualifications` can be arrays, strings, or dicts
- The loader normalizes all field types automatically

**Loading:**

```bash
python db_loader.py --db congress_jobs.db --load-file your_data.json
```

The system will:
1. Store the raw JSON
2. Normalize all fields
3. Match to legislators (if possible)
4. Deduplicate against existing jobs
5. Track as a new posting if job already exists

## API Endpoints

The web interface exposes a REST API:

- `GET /api/stats` - Database statistics
- `GET /api/search?q=query&party=Democrat&state=CA&page=1` - Search jobs
- `GET /api/job/<id>` - Job details with posting history
- `GET /api/filters` - Available filter options
- `GET /api/analytics/timeline` - Monthly posting counts
- `GET /api/analytics/salary` - Salary analysis data

## Future Enhancements (Phase 2+)

### Enhanced Extraction (LLM)
- Extract salary ranges (even from vague text)
- Identify required years of experience
- Extract education requirements
- Detect remote/hybrid/in-person status
- Build skills taxonomy
- Classify seniority levels

### Advanced Analytics
- Longitudinal skills trend analysis
- Predictive time-to-fill estimates
- Comparative analysis tools
- Natural language query interface

### Data Expansion
- Senate job listings
- Historical member data (map to past Congresses)
- Committee membership correlation
- District demographics integration

## File Structure

```
house-jobs/
├── congress_jobs.db          # Main SQLite database
├── schema.sql                # Database schema definition
├── db_loader.py              # Data loading and deduplication
├── init_database.py          # Initial setup script
├── web_interface.py          # Flask web application
├── templates/
│   └── index.html            # Web UI
├── json_gemini_flash/        # LLM-extracted job data
├── input/                    # Original PDF files
├── output/                   # Extracted text files
└── requirements.txt          # Python dependencies
```

## Data Sources

- **Job Listings**: House Vacancy Announcement and Placement Service (HVAPS)
- **Member Data**: unitedstates/congress-legislators (https://github.com/unitedstates/congress-legislators)
- **Extraction**: Google Gemini Flash/Pro (see `parser.py` and `parser2.py`)

## License

MIT License (same as original house-jobs repository)

## Contributing

To add new data:
1. Place JSON files in any directory
2. Run: `python db_loader.py --load-dir your_directory/`
3. The system handles deduplication automatically

To improve office matching:
- Edit `match_office_to_legislator()` in `db_loader.py`
- Adjust fuzzy matching thresholds
- Add special case handling

## Support

For questions or issues:
- Check existing queries in this README
- Examine the database with: `sqlite3 congress_jobs.db .schema`
- Review source code comments in `db_loader.py`

## Acknowledgments

- Derek Willis (@dwillis) for the original house-jobs repository and data collection
- Sunlight Foundation / unitedstates project for legislators data
- Google Gemini for LLM-based extraction
