# Congressional Jobs Research Tool - Quick Start

Get started in under 5 minutes!

## 1. Setup Database (One Time)

```bash
# Install dependencies
pip install -r requirements.txt

# Clone legislator data
git clone --depth 1 https://github.com/unitedstates/congress-legislators.git /tmp/congress-legislators

# Build database (takes ~2 minutes)
python init_database.py
```

You'll see:
```
✅ Loaded 439 current House members
✅ Loaded 5,272 unique jobs from 10,016 postings
✅ Enriched 37% with party/district data
✅ Database: 69 MB
```

## 2. Choose Your Interface

### For Research & Exploration → Datasette ⭐ Recommended

```bash
python run_datasette.py
```

**Visit:** http://localhost:8001

**You get:**
- ✅ Faceted search on ANY column
- ✅ 8 pre-built research queries
- ✅ Full SQL interface
- ✅ CSV/JSON export everywhere
- ✅ Automatic API
- ✅ Shareable URLs

**Try this:**
1. Click "jobs" table
2. Click "Facets" → Add "party" and "position_title"
3. See instant breakdowns with counts
4. Filter by clicking any value
5. Click "Download CSV" to export

**Or:** Click "Queries" → "Most Frequently Reposted Jobs"

---

### For Custom Job Board → Flask

```bash
python web_interface.py
```

**Visit:** http://localhost:5000

**You get:**
- Custom-designed search interface
- Job seeker-friendly UI
- Modal dialogs for details
- Mobile-responsive

## 3. Try Some Research

### In Datasette:

**Question:** Which positions are hardest to fill?

1. Go to "Queries" → "Most Frequently Reposted Jobs"
2. See jobs posted 10+ times
3. Export to CSV for analysis

**Question:** What are Democrats hiring for in California?

1. Go to "jobs" table
2. Where `party` = "Democrat"
3. Where `state` = "CA"
4. Sort by `last_posted`
5. URL updates - share with colleagues!

**Question:** Which offices hire most frequently?

1. Go to "Queries" → "Top Hiring Offices"
2. See offices with 5+ job postings
3. Click office name to see all their jobs

**Custom SQL:**
1. Click "jobs" → "Run SQL"
2. Paste query:
```sql
SELECT position_title, AVG(times_posted) as avg_reposts
FROM jobs
GROUP BY LOWER(position_title)
HAVING COUNT(*) >= 10
ORDER BY avg_reposts DESC
LIMIT 20
```
3. Click "Run SQL"
4. Export results

## 4. Load New Data

```bash
# From a single JSON file
python db_loader.py --load-file new_jobs.json

# From a directory
python db_loader.py --load-dir path/to/json/

# View stats
python db_loader.py --stats
```

## File Structure

```
house-jobs/
├── congress_jobs.db          # Your database (69 MB)
├── init_database.py          # ← Run once to setup
├── run_datasette.py          # ← Launch Datasette
├── web_interface.py          # ← Launch Flask
├── db_loader.py              # Load additional data
│
├── metadata.yml              # Datasette config
├── schema.sql                # Database schema
│
└── Documentation:
    ├── README_RESEARCH_TOOL.md    # Main docs
    ├── INTERFACES.md              # Flask vs Datasette
    ├── DATASETTE_EXAMPLES.md      # Research examples
    └── QUICK_START.md             # This file!
```

## Common Tasks

### Search for "legislative assistant" jobs

**Datasette:**
- Go to jobs table
- Filter where `position_title` contains "Legislative Assistant"

**Flask:**
- Type "legislative assistant" in search box

### Export all Democrat jobs to CSV

**Datasette:**
1. Filter: `party` = "Democrat"
2. Click "Download CSV"

**Flask:** Not available (use Datasette)

### Find jobs with salary information

**Datasette:**
1. "Queries" → "Jobs with Salary Information"
2. Or filter: `salary_info` is not null

**SQL:**
```sql
SELECT * FROM jobs
WHERE salary_info IS NOT NULL
  AND salary_info != ''
```

### Track hiring trends over time

**Datasette:**
1. "Queries" → "Monthly Hiring Trends"
2. Export CSV
3. Create chart in Excel/Sheets

### Share a specific filtered view

**Datasette:** Just copy the URL!
- Example: `http://localhost:8001/congress_jobs/jobs?party=Democrat&state=CA`
- Anyone with link sees exact same view

**Flask:** Not easily shareable

## Tips

### Datasette Tips

- **Facets are your friend** - Add them to any column for instant breakdowns
- **SQL is optional** - Pre-built queries + facets cover most use cases
- **URLs are shareable** - Bookmark your favorite filtered views
- **Export everything** - Every view has CSV/JSON download
- **`.json` trick** - Add `.json` to any URL for API access

### Database Tips

- Tables are **read-only** in interfaces (protection against accidental changes)
- To modify: Use `db_loader.py` to reload data
- Deduplication is automatic
- Party enrichment improves as congress-legislators updates

### Research Tips

- Start with pre-built queries
- Export to CSV for complex analysis
- Use SQL for joins across tables
- Check `active_jobs` view for legislator-enriched data
- Filter `times_posted >= 5` to find hard-to-fill jobs

## What's Next?

### Phase 2 Ideas (Not Yet Implemented)

1. **Enhanced extraction** - Use LLM to parse:
   - Salary ranges (even from vague text)
   - Required years of experience
   - Education requirements
   - Skills/software requirements

2. **Advanced analytics**:
   - Skills trend analysis
   - Predictive time-to-fill
   - Career path mapping
   - Comparative visualizations

3. **More data sources**:
   - Senate job listings
   - Historical member matching
   - District demographics

## Getting Help

### Datasette
- Docs: https://docs.datasette.io
- In-app: Click "Database: congress_jobs" → "View schema"

### SQL
- Tutorial: https://www.sqlitetutorial.net
- In-app: Pre-built queries show examples

### This Project
- See [README_RESEARCH_TOOL.md](README_RESEARCH_TOOL.md) for detailed docs
- See [DATASETTE_EXAMPLES.md](DATASETTE_EXAMPLES.md) for research examples
- See [INTERFACES.md](INTERFACES.md) for Flask vs Datasette comparison

## Publishing Online

Want to share your database with the world?

```bash
# Publish to Vercel (free, 30 seconds)
datasette publish vercel congress_jobs.db \
  --metadata metadata.yml \
  --project congress-jobs-research

# Or Google Cloud Run
datasette publish cloudrun congress_jobs.db \
  --metadata metadata.yml \
  --service congress-jobs
```

Your database is now live at: `https://congress-jobs-research.vercel.app`

All queries, exports, and API access work exactly the same!

## Summary

**You now have:**
- ✅ 5,272 deduplicated jobs from 11 years
- ✅ Party/district enrichment (37%)
- ✅ Timeline tracking (reposts, time-to-fill)
- ✅ Two web interfaces (Datasette + Flask)
- ✅ 8 pre-built research queries
- ✅ Full SQL access
- ✅ CSV/JSON export
- ✅ Automatic API
- ✅ Shareable URLs
- ✅ Can load data from any JSON source

**Datasette gives you:**
- Zero-code data exploration
- Researcher-friendly tools
- Publication-ready exports
- Professional API

**All in 69 MB SQLite database!**

## Questions?

Read the docs:
- [README_RESEARCH_TOOL.md](README_RESEARCH_TOOL.md) - Comprehensive guide
- [DATASETTE_EXAMPLES.md](DATASETTE_EXAMPLES.md) - Research examples & SQL queries
- [INTERFACES.md](INTERFACES.md) - Choose the right interface

Start exploring:
```bash
python run_datasette.py
```
