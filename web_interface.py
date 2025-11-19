#!/usr/bin/env python3
"""
Congressional Jobs Web Interface
Simple Flask app for searching and exploring the job listings database.
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
import json
from pathlib import Path
from datetime import datetime

app = Flask(__name__)
CORS(app)

DB_PATH = "congress_jobs.db"


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def dict_from_row(row):
    """Convert sqlite3.Row to dict."""
    return {k: row[k] for k in row.keys()}


@app.route('/')
def index():
    """Home page."""
    return render_template('index.html')


@app.route('/api/stats')
def stats():
    """Get database statistics."""
    conn = get_db()
    cursor = conn.cursor()

    stats = {}

    # Total jobs
    cursor.execute("SELECT COUNT(*) FROM jobs")
    stats['total_jobs'] = cursor.fetchone()[0]

    # Active jobs
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'active'")
    stats['active_jobs'] = cursor.fetchone()[0]

    # Jobs with party
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE party IS NOT NULL")
    stats['jobs_with_party'] = cursor.fetchone()[0]

    # Jobs by party
    cursor.execute("""
        SELECT party, COUNT(*) as count
        FROM jobs
        WHERE party IS NOT NULL
        GROUP BY party
        ORDER BY count DESC
    """)
    stats['by_party'] = [dict_from_row(row) for row in cursor.fetchall()]

    # Jobs by position title (top 10)
    cursor.execute("""
        SELECT position_title, COUNT(*) as count
        FROM jobs
        GROUP BY LOWER(position_title)
        ORDER BY count DESC
        LIMIT 10
    """)
    stats['top_positions'] = [dict_from_row(row) for row in cursor.fetchall()]

    # Jobs by state (top 10)
    cursor.execute("""
        SELECT state, COUNT(*) as count
        FROM jobs
        WHERE state IS NOT NULL
        GROUP BY state
        ORDER BY count DESC
        LIMIT 10
    """)
    stats['top_states'] = [dict_from_row(row) for row in cursor.fetchall()]

    # Date range
    cursor.execute("SELECT MIN(first_posted), MAX(last_posted) FROM jobs")
    result = cursor.fetchone()
    stats['date_range'] = {'start': result[0], 'end': result[1]}

    # Recent jobs
    cursor.execute("""
        SELECT position_title, office, location, last_posted, times_posted
        FROM jobs
        ORDER BY last_posted DESC
        LIMIT 5
    """)
    stats['recent_jobs'] = [dict_from_row(row) for row in cursor.fetchall()]

    conn.close()
    return jsonify(stats)


@app.route('/api/search')
def search():
    """Search for jobs."""
    # Get query parameters
    query = request.args.get('q', '').strip()
    party = request.args.get('party')
    state = request.args.get('state')
    position = request.args.get('position')
    salary_min = request.args.get('salary_min')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))

    conn = get_db()
    cursor = conn.cursor()

    # Build query
    conditions = ["status = 'active'"]
    params = []

    if query:
        conditions.append("(position_title LIKE ? OR office LIKE ? OR description LIKE ?)")
        search_term = f"%{query}%"
        params.extend([search_term, search_term, search_term])

    if party:
        conditions.append("party = ?")
        params.append(party)

    if state:
        conditions.append("state = ?")
        params.append(state)

    if position:
        conditions.append("LOWER(position_title) LIKE ?")
        params.append(f"%{position.lower()}%")

    if date_from:
        conditions.append("first_posted >= ?")
        params.append(date_from)

    if date_to:
        conditions.append("last_posted <= ?")
        params.append(date_to)

    where_clause = " AND ".join(conditions)

    # Get total count
    cursor.execute(f"SELECT COUNT(*) FROM jobs WHERE {where_clause}", params)
    total = cursor.fetchone()[0]

    # Get results
    offset = (page - 1) * per_page
    cursor.execute(f"""
        SELECT
            j.*,
            l.name_official as legislator_name
        FROM jobs j
        LEFT JOIN legislators l ON j.legislator_id = l.id
        WHERE {where_clause}
        ORDER BY j.last_posted DESC, j.times_posted DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])

    results = []
    for row in cursor.fetchall():
        job = dict_from_row(row)
        # Parse JSON fields
        job['responsibilities'] = json.loads(job['responsibilities_json']) if job['responsibilities_json'] else []
        job['qualifications'] = json.loads(job['qualifications_json']) if job['qualifications_json'] else []
        del job['responsibilities_json']
        del job['qualifications_json']
        results.append(job)

    conn.close()

    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'results': results
    })


@app.route('/api/job/<int:job_id>')
def job_detail(job_id):
    """Get detailed job information."""
    conn = get_db()
    cursor = conn.cursor()

    # Get job
    cursor.execute("""
        SELECT
            j.*,
            l.name_official as legislator_name,
            l.bioguide,
            l.office_address,
            l.phone
        FROM jobs j
        LEFT JOIN legislators l ON j.legislator_id = l.id
        WHERE j.id = ?
    """, (job_id,))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Job not found'}), 404

    job = dict_from_row(row)
    job['responsibilities'] = json.loads(job['responsibilities_json']) if job['responsibilities_json'] else []
    job['qualifications'] = json.loads(job['qualifications_json']) if job['qualifications_json'] else []
    del job['responsibilities_json']
    del job['qualifications_json']

    # Get posting history
    cursor.execute("""
        SELECT bulletin_date, source_file
        FROM job_postings
        WHERE job_id = ?
        ORDER BY bulletin_date DESC
    """, (job_id,))
    job['postings'] = [dict_from_row(row) for row in cursor.fetchall()]

    conn.close()
    return jsonify(job)


@app.route('/api/filters')
def filters():
    """Get available filter options."""
    conn = get_db()
    cursor = conn.cursor()

    # Get unique parties
    cursor.execute("""
        SELECT DISTINCT party
        FROM jobs
        WHERE party IS NOT NULL
        ORDER BY party
    """)
    parties = [row[0] for row in cursor.fetchall()]

    # Get unique states
    cursor.execute("""
        SELECT DISTINCT state
        FROM jobs
        WHERE state IS NOT NULL
        ORDER BY state
    """)
    states = [row[0] for row in cursor.fetchall()]

    # Get common position titles
    cursor.execute("""
        SELECT DISTINCT position_title
        FROM jobs
        GROUP BY LOWER(position_title)
        HAVING COUNT(*) >= 5
        ORDER BY COUNT(*) DESC
        LIMIT 50
    """)
    positions = [row[0] for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        'parties': parties,
        'states': states,
        'positions': positions
    })


@app.route('/api/analytics/timeline')
def timeline():
    """Get timeline of job postings."""
    conn = get_db()
    cursor = conn.cursor()

    # Monthly job counts
    cursor.execute("""
        SELECT
            strftime('%Y-%m', first_posted) as month,
            COUNT(*) as count
        FROM jobs
        WHERE first_posted IS NOT NULL
        GROUP BY month
        ORDER BY month
    """)
    timeline_data = [dict_from_row(row) for row in cursor.fetchall()]

    conn.close()
    return jsonify(timeline_data)


@app.route('/api/analytics/salary')
def salary_analysis():
    """Analyze salary information."""
    conn = get_db()
    cursor = conn.cursor()

    # Jobs with salary info
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(salary_info) as with_salary,
            party,
            position_title
        FROM jobs
        WHERE party IS NOT NULL
        GROUP BY party, LOWER(position_title)
        HAVING COUNT(*) >= 3
        ORDER BY COUNT(*) DESC
        LIMIT 20
    """)
    salary_data = [dict_from_row(row) for row in cursor.fetchall()]

    conn.close()
    return jsonify(salary_data)


if __name__ == '__main__':
    if not Path(DB_PATH).exists():
        print(f"Error: Database not found at {DB_PATH}")
        print("Please run init_database.py first")
        exit(1)

    print("=" * 60)
    print("Congressional Jobs Research Tool - Web Interface")
    print("=" * 60)
    print(f"\nDatabase: {DB_PATH}")
    print("Starting server at http://localhost:5000")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)

    app.run(debug=True, host='0.0.0.0', port=5000)
