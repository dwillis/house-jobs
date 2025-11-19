# Datasette Usage Examples

This guide shows powerful research queries you can run in Datasette that would be difficult or impossible with a traditional web interface.

## Getting Started

```bash
python run_datasette.py
```

Visit http://localhost:8001

## Pre-Built Research Queries

Click "Queries" in the navigation to access these:

### 1. Most Frequently Reposted Jobs

**What it reveals:** Jobs that are hard to fill (posted many times)

**Insights:**
- High repost count = difficult to fill or high turnover
- Time between first/last posting shows how long search lasted
- Can identify positions with challenging requirements

**Example finding:**
"Policy Director at Congressional Black Caucus - posted 32 times over 2 years"

### 2. Recent Jobs by Party

**What it reveals:** Current hiring patterns by political party

**Use cases:**
- Compare D vs R hiring volume
- Identify which parties hire for what roles
- Track seasonal hiring patterns

**Tip:** Export to CSV and create time-series charts

### 3. Salary Analysis

**What it reveals:** Which positions disclose salary information

**Key insights:**
- Only ~15-20% of jobs include salary info
- Higher-level positions more likely to state "commensurate with experience"
- Some offices consistently transparent, others never disclose

**Research potential:**
- Compare salary transparency by party
- Identify which position types get salary info
- Geographic salary differences

### 4. Monthly Hiring Trends

**What it reveals:** Hiring volume over time by party

**Patterns to look for:**
- Post-election hiring spikes
- Seasonal variations
- Long-term trends (growing/shrinking)

**Export & visualize:**
```bash
# From query page, click "Download CSV"
# Import to Excel/Google Sheets
# Create line chart: Month vs Jobs Posted, colored by Party
```

### 5. Top Hiring Offices

**What it reveals:** Which offices hire most frequently

**Insights:**
- High turnover offices
- Large staff operations
- Frequent restructuring

**Follow-up questions:**
- Do they hire for same positions repeatedly?
- What's their average time-to-fill?
- Are they good employers or revolving door?

### 6. Position Breakdown

**What it reveals:** Distribution of job types, repost rates by role

**Analysis opportunities:**
- Which roles are hardest to fill?
- Party differences in staffing structures
- Common vs rare positions

### 7. Jobs by State

**What it reveals:** Geographic distribution of opportunities

**Research questions:**
- Do larger states hire more?
- Regional differences in positions offered
- District vs DC office hiring patterns

### 8. Full-Text Search

**Dynamic search across all fields**

Example searches:
- "social media" - Find all communications roles
- "veterans" - Find roles focused on military issues
- "Spanish" - Find bilingual positions
- "security clearance" - Find roles requiring clearance

## Advanced SQL Queries

Click any table → "Run SQL" to write custom queries:

### Find All Entry-Level Positions

```sql
SELECT position_title, office, party, salary_info
FROM jobs
WHERE description LIKE '%entry level%'
   OR description LIKE '%no experience%'
   OR position_title LIKE '%assistant%'
ORDER BY last_posted DESC
```

### Calculate Average Time-to-Fill

```sql
SELECT
  position_title,
  COUNT(*) as occurrences,
  AVG(julianday(last_posted) - julianday(first_posted)) as avg_days_open,
  AVG(times_posted) as avg_reposts
FROM jobs
WHERE times_posted >= 3
GROUP BY LOWER(position_title)
HAVING occurrences >= 5
ORDER BY avg_days_open DESC
```

### Compare Party Hiring Patterns

```sql
SELECT
  party,
  position_title,
  COUNT(*) as count,
  ROUND(AVG(times_posted), 2) as avg_reposts,
  COUNT(CASE WHEN salary_info IS NOT NULL THEN 1 END) * 100.0 / COUNT(*) as pct_with_salary
FROM jobs
WHERE party IN ('Democrat', 'Republican')
GROUP BY party, LOWER(position_title)
HAVING count >= 3
ORDER BY count DESC
```

### Find Jobs Requiring Specific Skills

```sql
SELECT
  position_title,
  office,
  party,
  description
FROM jobs
WHERE
  description LIKE '%Python%'
  OR description LIKE '%data analysis%'
  OR description LIKE '%SQL%'
ORDER BY last_posted DESC
```

### Identify Offices with High Turnover

```sql
SELECT
  office,
  party,
  state,
  COUNT(DISTINCT position_title) as unique_positions,
  COUNT(*) as total_postings,
  SUM(times_posted) as total_reposts,
  MAX(last_posted) as most_recent
FROM jobs
WHERE party IS NOT NULL
GROUP BY office
HAVING total_postings >= 5
ORDER BY total_reposts DESC
```

### Salary Disclosure by Party

```sql
SELECT
  party,
  COUNT(*) as total_jobs,
  COUNT(CASE WHEN salary_info IS NOT NULL AND salary_info != '' THEN 1 END) as with_salary,
  ROUND(COUNT(CASE WHEN salary_info IS NOT NULL AND salary_info != '' THEN 1 END) * 100.0 / COUNT(*), 1) as pct_disclosed
FROM jobs
WHERE party IS NOT NULL
GROUP BY party
```

### Jobs Posted During Election Years

```sql
SELECT
  strftime('%Y', first_posted) as year,
  CASE WHEN CAST(strftime('%Y', first_posted) AS INTEGER) % 2 = 0
       THEN 'Election Year'
       ELSE 'Off Year'
  END as election_cycle,
  COUNT(*) as jobs_posted,
  party
FROM jobs
WHERE party IS NOT NULL
GROUP BY year, election_cycle, party
ORDER BY year DESC
```

## Faceted Search

Click "Facets" on any table view to add multi-dimensional filtering:

### Example: Find Progressive Communications Jobs

1. Go to `jobs` table
2. Click "Facets" → Add:
   - `party` → Select "Democrat"
   - `position_title` → Select "Communications Director"
   - `state` → Select states of interest
3. Use search box: "progressive" or "climate" or "justice"
4. Results automatically filter
5. **URL is shareable** - send link to colleagues!

### Example: Research Committee Hiring

1. Go to `jobs` table
2. Add facet: `office`
3. Scroll to committees (contain "Committee" in name)
4. Click committee name
5. See all jobs posted by that committee
6. Sort by `last_posted` to see most recent

## Export & Analysis

Every view can be exported:

### Export to CSV
1. Run any query
2. Click "CSV" at bottom of results
3. Opens in Excel/Google Sheets
4. Create pivot tables, charts, etc.

### Export to JSON
1. Add `.json` to any URL
2. Example: `http://localhost:8001/congress_jobs/jobs.json`
3. Use for programmatic access
4. Build external tools/dashboards

### API Access

Every table and query has automatic API:

```bash
# Get all Democrat jobs
curl 'http://localhost:8001/congress_jobs/jobs.json?party=Democrat&_size=100'

# Run custom query
curl 'http://localhost:8001/congress_jobs/jobs.json?sql=SELECT+*+FROM+jobs+WHERE+...'

# Get specific job
curl 'http://localhost:8001/congress_jobs/jobs/123.json'
```

## Combining Filters

Datasette's power is in combining multiple filters:

### Example: Senior Legislative Roles in California (Democrat)

Navigate to: `congress_jobs` → `jobs` → Add filters:
- Where `party` = `Democrat`
- Where `state` = `CA`
- Where `position_title` contains `Legislative Director` OR `Legislative Counsel`
- Sort by `salary_info` descending

The URL encodes all filters - bookmark or share it!

### Example: Recently Reposted Communications Jobs

- Where `position_title` contains `Communications`
- Where `times_posted` ≥ 3
- Where `last_posted` ≥ 2024-01-01
- Add facet: `party` (see D vs R breakdown)

## Sharing Research

**Best feature:** URLs contain all filters/sorts/queries

```
# Share exact filtered view
http://localhost:8001/congress_jobs/jobs?party=Democrat&state=CA&position_title__contains=Director

# Share custom query results
http://localhost:8001/congress_jobs?sql=SELECT+...

# Share with colleagues - they see exactly what you see!
```

## Publishing Your Database

Share with the world:

```bash
# Publish to Vercel (free, takes 30 seconds)
datasette publish vercel congress_jobs.db --metadata metadata.yml --project=congress-jobs

# Or Google Cloud Run
datasette publish cloudrun congress_jobs.db --metadata metadata.yml --service=congress-jobs

# Or Heroku
datasette publish heroku congress_jobs.db --metadata metadata.yml --name=congress-jobs
```

Your database is now publicly accessible with:
- All queries working
- All exports working
- Automatic API
- Fast global CDN

Example: https://your-project.vercel.app

## Tips & Tricks

### 1. Use SQL for Complex Joins

```sql
-- Join jobs with legislators to get full member info
SELECT
  j.position_title,
  j.office,
  l.name_official,
  l.party,
  l.phone,
  j.last_posted
FROM jobs j
JOIN legislators l ON j.legislator_id = l.id
WHERE j.times_posted >= 5
```

### 2. Save Frequently Used Queries

Edit `metadata.yml` to add queries:

```yaml
queries:
  my_custom_query:
    title: My Analysis
    description: What this shows
    sql: SELECT ...
```

Restart Datasette - query appears in menu!

### 3. Use Query Parameters

Create parameterized queries:

```sql
SELECT * FROM jobs
WHERE party = :party
  AND state = :state
ORDER BY last_posted DESC
```

Datasette auto-generates form inputs for `:party` and `:state`!

### 4. Combine with External Tools

Export JSON → Import to:
- Python (pandas): `df = pd.read_json(url)`
- R: `data <- fromJSON(url)`
- JavaScript: `fetch(url).then(r => r.json())`
- Tableau: Direct JSON connector
- Excel: Power Query → From Web

### 5. Monitor Changes

Bookmark queries with filters, check daily:
- New jobs matching criteria
- Changes in hiring patterns
- Emerging position types

## Real Research Questions You Can Answer

1. **Do election years show hiring spikes?** → Monthly trends query + export to Excel
2. **Which positions have highest turnover?** → Repost analysis + time-to-fill calculation
3. **Are there regional differences in job types?** → State analysis + position breakdown
4. **How has salary transparency changed over time?** → Custom SQL + time series
5. **What skills are increasingly in demand?** → Full-text search trends over years
6. **Do committees hire differently than member offices?** → Filter by office type + compare
7. **Which offices are best to work for?** → Low repost rate + long posting duration
8. **Career path analysis:** → Track similar positions across offices
9. **Party differences in staffing:** → Everything filtered by party
10. **Impact of political events:** → Timeline around specific dates

## Getting Help

- Datasette docs: https://docs.datasette.io
- SQL tutorial: https://www.sqlitetutorial.net
- View schema: Click "Database: congress_jobs" → "View schema"
- Example queries: Built into metadata.yml

## Why This Beats a Traditional Web UI

| Task | Traditional UI | Datasette |
|------|---------------|-----------|
| Filter by any column | ❌ Must be pre-coded | ✅ Automatic |
| Complex queries | ❌ Not possible | ✅ Full SQL |
| Export results | ❌ Limited | ✅ Everything |
| Share exact view | ❌ Difficult | ✅ Just share URL |
| Add new filters | ⚠️ Edit code | ✅ Just click |
| API access | ⚠️ Document each endpoint | ✅ Automatic |
| Combine filters | ⚠️ Limited combinations | ✅ Unlimited |
| Custom calculations | ❌ Not available | ✅ SQL functions |

**Bottom line:** Datasette gives you the flexibility of SQL with the convenience of a web interface. Perfect for research.
