-- Congressional Jobs Research Database Schema

-- Table: legislators
-- Stores current House members with party and district info from congress-legislators
CREATE TABLE IF NOT EXISTS legislators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bioguide TEXT UNIQUE,
    name_first TEXT,
    name_last TEXT,
    name_official TEXT,
    state TEXT,
    district INTEGER,
    party TEXT,
    term_start TEXT,
    term_end TEXT,
    office_address TEXT,
    phone TEXT,
    contact_form TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_legislators_state_district ON legislators(state, district);
CREATE INDEX idx_legislators_bioguide ON legislators(bioguide);

-- Table: jobs
-- Deduplicated master job listings
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Deduplication key (hash of normalized office + title + description snippet)
    dedup_key TEXT UNIQUE,

    -- Core fields
    job_id TEXT,  -- e.g., MEM-452-24 (not unique, can be reposted)
    position_title TEXT NOT NULL,
    office TEXT,
    location TEXT,

    -- Enriched fields
    legislator_id INTEGER,  -- FK to legislators table
    state TEXT,
    district INTEGER,
    party TEXT,

    -- Temporal tracking
    first_posted DATE,
    last_posted DATE,
    times_posted INTEGER DEFAULT 1,

    -- Status
    status TEXT DEFAULT 'active',  -- active, filled, removed

    -- Full description (from most recent posting)
    description TEXT,
    responsibilities_json TEXT,  -- JSON array
    qualifications_json TEXT,    -- JSON array

    -- Application info
    how_to_apply TEXT,
    salary_info TEXT,
    contact TEXT,
    equal_opportunity TEXT,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (legislator_id) REFERENCES legislators(id)
);

CREATE INDEX idx_jobs_dedup_key ON jobs(dedup_key);
CREATE INDEX idx_jobs_office ON jobs(office);
CREATE INDEX idx_jobs_position_title ON jobs(position_title);
CREATE INDEX idx_jobs_first_posted ON jobs(first_posted);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_legislator_id ON jobs(legislator_id);
CREATE INDEX idx_jobs_party ON jobs(party);
CREATE INDEX idx_jobs_state_district ON jobs(state, district);

-- Table: job_postings
-- Individual postings (tracks each appearance in bulletins)
CREATE TABLE IF NOT EXISTS job_postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,  -- FK to jobs table

    -- Source information
    source_file TEXT,
    bulletin_date DATE,

    -- Original data (snapshot)
    original_job_id TEXT,
    position_title TEXT,
    office TEXT,
    location TEXT,
    posting_date DATE,
    description TEXT,
    responsibilities_json TEXT,
    qualifications_json TEXT,
    how_to_apply TEXT,
    salary_info TEXT,
    contact TEXT,
    equal_opportunity TEXT,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE INDEX idx_job_postings_job_id ON job_postings(job_id);
CREATE INDEX idx_job_postings_bulletin_date ON job_postings(bulletin_date);
CREATE INDEX idx_job_postings_source_file ON job_postings(source_file);

-- Table: raw_jobs
-- Raw data from any JSON source (before processing)
CREATE TABLE IF NOT EXISTS raw_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    source_type TEXT,  -- e.g., 'gemini_flash', 'manual', etc.
    raw_data TEXT NOT NULL,  -- Full JSON of the job
    processed BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_raw_jobs_source_file ON raw_jobs(source_file);
CREATE INDEX idx_raw_jobs_processed ON raw_jobs(processed);

-- Table: office_name_variants
-- Maps various office name formats to standardized names
CREATE TABLE IF NOT EXISTS office_name_variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    variant TEXT UNIQUE,
    canonical_office TEXT,
    legislator_id INTEGER,
    confidence REAL,  -- 0.0-1.0 matching confidence

    FOREIGN KEY (legislator_id) REFERENCES legislators(id)
);

CREATE INDEX idx_office_variants_variant ON office_name_variants(variant);
CREATE INDEX idx_office_variants_legislator ON office_name_variants(legislator_id);

-- Full-text search can be added later if needed
-- For now using regular indexes for performance

-- View: active_jobs
-- Currently active job listings with enriched data
CREATE VIEW IF NOT EXISTS active_jobs AS
SELECT
    j.*,
    l.name_official as legislator_name,
    l.bioguide,
    julianday('now') - julianday(j.first_posted) as days_since_first_posted,
    julianday('now') - julianday(j.last_posted) as days_since_last_posted
FROM jobs j
LEFT JOIN legislators l ON j.legislator_id = l.id
WHERE j.status = 'active';

-- View: job_timeline
-- Timeline of all postings for research
CREATE VIEW IF NOT EXISTS job_timeline AS
SELECT
    jp.bulletin_date,
    jp.position_title,
    jp.office,
    jp.location,
    j.state,
    j.district,
    j.party,
    j.times_posted,
    l.name_official as legislator_name
FROM job_postings jp
JOIN jobs j ON jp.job_id = j.id
LEFT JOIN legislators l ON j.legislator_id = l.id
ORDER BY jp.bulletin_date DESC;
