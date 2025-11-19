#!/usr/bin/env python3
"""
Congressional Jobs Database Loader
Loads job listings from any JSON source into SQLite with deduplication and enrichment.
"""

import sqlite3
import json
import hashlib
import re
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import yaml
from difflib import SequenceMatcher
from collections import defaultdict


class CongressionalJobsDB:
    def __init__(self, db_path: str = "congress_jobs.db"):
        self.db_path = db_path
        self.conn = None
        self.legislators_cache = {}
        self.office_matcher_cache = {}

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self):
        """Connect to database and create schema if needed."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.commit()
            self.conn.close()

    def _create_schema(self):
        """Create database schema from schema.sql."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path) as f:
            self.conn.executescript(f.read())
        self.conn.commit()

    def load_legislators(self, legislators_yaml_path: str):
        """
        Load current House members from congress-legislators YAML file.
        Only loads current House members (not Senate, not historical).
        """
        with open(legislators_yaml_path) as f:
            legislators = yaml.safe_load(f)

        cursor = self.conn.cursor()
        loaded_count = 0

        for leg in legislators:
            # Get current term
            terms = leg.get('terms', [])
            if not terms:
                continue

            # Find most recent House term
            current_term = None
            for term in reversed(terms):
                if term.get('type') == 'rep':
                    # Check if term is current (end date is in future or not set)
                    end_date = term.get('end', '9999-12-31')
                    if end_date >= datetime.now().strftime('%Y-%m-%d'):
                        current_term = term
                        break

            if not current_term:
                continue  # Not a current House member

            # Extract data
            bioguide = leg['id']['bioguide']
            name = leg.get('name', {})
            bio = leg.get('bio', {})

            cursor.execute("""
                INSERT OR REPLACE INTO legislators (
                    bioguide, name_first, name_last, name_official,
                    state, district, party, term_start, term_end,
                    office_address, phone, contact_form
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bioguide,
                name.get('first'),
                name.get('last'),
                name.get('official_full'),
                current_term.get('state'),
                current_term.get('district'),
                current_term.get('party'),
                current_term.get('start'),
                current_term.get('end'),
                current_term.get('address'),
                current_term.get('phone'),
                current_term.get('contact_form')
            ))
            loaded_count += 1

            # Cache for matching
            self.legislators_cache[bioguide] = {
                'id': cursor.lastrowid,
                'name_official': name.get('official_full'),
                'name_first': name.get('first'),
                'name_last': name.get('last'),
                'state': current_term.get('state'),
                'district': current_term.get('district'),
                'party': current_term.get('party')
            }

        self.conn.commit()
        print(f"✓ Loaded {loaded_count} current House members")
        return loaded_count

    def _normalize_office_name(self, office: str) -> str:
        """Normalize office name for matching."""
        if not office:
            return ""

        # Convert to lowercase
        office = office.lower()

        # Remove common prefixes/suffixes
        patterns = [
            r'^office of\s+',
            r'^the office of\s+',
            r'^congressman\s+',
            r'^congresswoman\s+',
            r'^representative\s+',
            r'^rep\.?\s+',
            r'\s+\([^)]+\)$',  # Remove (STATE-DISTRICT)
        ]

        for pattern in patterns:
            office = re.sub(pattern, '', office)

        # Remove extra whitespace
        office = ' '.join(office.split())

        return office

    def _extract_state_district(self, office: str) -> Tuple[Optional[str], Optional[int]]:
        """Extract state and district from office name like '(PA-2)' or '(CA-43)'."""
        match = re.search(r'\(([A-Z]{2})-(\d+)\)', office)
        if match:
            return match.group(1), int(match.group(2))
        return None, None

    def match_office_to_legislator(self, office: str) -> Optional[Dict]:
        """
        Match an office name to a legislator using fuzzy matching.
        Returns legislator data or None.
        """
        if not office:
            return None

        # Check cache first
        if office in self.office_matcher_cache:
            return self.office_matcher_cache[office]

        # Extract state/district if present
        state, district = self._extract_state_district(office)

        # Normalize office name
        normalized = self._normalize_office_name(office)

        best_match = None
        best_score = 0.0

        for bioguide, leg in self.legislators_cache.items():
            score = 0.0

            # Exact state/district match gets high score
            if state and district:
                if leg['state'] == state and leg['district'] == district:
                    score += 50.0

            # Fuzzy match on names
            if leg['name_official']:
                name_score = SequenceMatcher(None, normalized, leg['name_official'].lower()).ratio()
                score += name_score * 30.0

            if leg['name_last']:
                last_name_lower = leg['name_last'].lower()
                if last_name_lower in normalized:
                    score += 20.0

            # Committee/office without specific member name
            if not state and not district:
                # Check if it's a committee or generic office
                if any(keyword in normalized for keyword in ['committee', 'subcommittee', 'select', 'joint']):
                    # Don't match committees to individual members
                    continue

            if score > best_score:
                best_score = score
                best_match = leg

        # Require minimum confidence score
        if best_score >= 40.0:
            result = {
                'legislator_id': best_match['id'],
                'state': best_match['state'],
                'district': best_match['district'],
                'party': best_match['party'],
                'confidence': best_score / 100.0
            }
            self.office_matcher_cache[office] = result
            return result

        # Cache negative results too
        self.office_matcher_cache[office] = None
        return None

    def _generate_dedup_key(self, job: Dict) -> str:
        """
        Generate a deduplication key for a job.
        Uses normalized office + title + description snippet.
        """
        office = self._normalize_office_name(job.get('office', ''))
        title = (job.get('position_title', '') or '').lower().strip()
        desc = (job.get('description', '') or '')[:500].lower().strip()

        # Create hash of key components
        key_string = f"{office}|{title}|{desc}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def _normalize_job_field(self, value, expected_type='str'):
        """Normalize job field to expected type, handling various input formats."""
        if expected_type == 'str':
            if value is None:
                return None
            if isinstance(value, str):
                return value
            if isinstance(value, (dict, list)):
                # Convert dict/list to JSON string
                return json.dumps(value)
            return str(value)
        elif expected_type == 'list':
            if value is None:
                return []
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                # Try to extract values from dict
                return list(value.values())
            if isinstance(value, str):
                # Split by newlines or return as single item
                return [value] if value.strip() else []
            return [str(value)]
        return value

    def load_jobs_from_json(self, json_path: str, source_type: str = "json"):
        """
        Load jobs from a JSON file (can be single job or array).
        Handles deduplication and enrichment automatically.
        """
        with open(json_path) as f:
            data = json.load(f)

        # Handle both single job objects and arrays
        jobs = data if isinstance(data, list) else [data]

        source_file = Path(json_path).name

        # Extract bulletin date from filename
        bulletin_date = self._extract_date_from_filename(source_file)

        cursor = self.conn.cursor()
        stats = {
            'new_jobs': 0,
            'reposted_jobs': 0,
            'enriched_jobs': 0,
            'total_processed': 0,
            'skipped': 0
        }

        for job in jobs:
            stats['total_processed'] += 1

            # Normalize job fields
            try:
                position_title = self._normalize_job_field(job.get('position_title'), 'str')
                if not position_title or not position_title.strip():
                    # Skip jobs without a title
                    stats['skipped'] += 1
                    continue

                # Normalize all fields
                office = self._normalize_job_field(job.get('office'), 'str')
                location = self._normalize_job_field(job.get('location'), 'str')
                description = self._normalize_job_field(job.get('description'), 'str')
                responsibilities = self._normalize_job_field(job.get('responsibilities'), 'list')
                qualifications = self._normalize_job_field(job.get('qualifications'), 'list')
                how_to_apply = self._normalize_job_field(job.get('how_to_apply'), 'str')
                salary_info = self._normalize_job_field(job.get('salary_info'), 'str')
                contact = self._normalize_job_field(job.get('contact'), 'str')
                equal_opportunity = self._normalize_job_field(job.get('equal_opportunity'), 'str')

            except Exception as e:
                print(f"  Warning: Failed to normalize fields in {source_file}: {e}")
                stats['skipped'] += 1
                continue

            # Store raw job
            try:
                cursor.execute("""
                    INSERT INTO raw_jobs (source_file, source_type, raw_data, processed)
                    VALUES (?, ?, ?, 1)
                """, (source_file, source_type, json.dumps(job)))
            except Exception as e:
                print(f"  Warning: Failed to store raw job in {source_file}: {e}")

            # Generate dedup key
            dedup_key = self._generate_dedup_key(job)

            # Check if job already exists
            cursor.execute("SELECT id, times_posted FROM jobs WHERE dedup_key = ?", (dedup_key,))
            existing = cursor.fetchone()

            # Match to legislator
            legislator_match = self.match_office_to_legislator(office or '')

            posting_date = job.get('posting_date') or bulletin_date

            try:
                if existing:
                    # Update existing job
                    job_id = existing[0]
                    times_posted = existing[1] + 1

                    cursor.execute("""
                        UPDATE jobs SET
                            last_posted = ?,
                            times_posted = ?,
                            description = ?,
                            responsibilities_json = ?,
                            qualifications_json = ?,
                            how_to_apply = ?,
                            salary_info = ?,
                            contact = ?,
                            equal_opportunity = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (
                        posting_date,
                        times_posted,
                        description,
                        json.dumps(responsibilities),
                        json.dumps(qualifications),
                        how_to_apply,
                        salary_info,
                        contact,
                        equal_opportunity,
                        job_id
                    ))
                    stats['reposted_jobs'] += 1
                else:
                    # Insert new job
                    cursor.execute("""
                        INSERT INTO jobs (
                            dedup_key, job_id, position_title, office, location,
                            legislator_id, state, district, party,
                            first_posted, last_posted, times_posted,
                            description, responsibilities_json, qualifications_json,
                            how_to_apply, salary_info, contact, equal_opportunity
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        dedup_key,
                        job.get('id'),
                        position_title,
                        office,
                        location,
                        legislator_match['legislator_id'] if legislator_match else None,
                        legislator_match['state'] if legislator_match else None,
                        legislator_match['district'] if legislator_match else None,
                        legislator_match['party'] if legislator_match else None,
                        posting_date,
                        posting_date,
                        1,
                        description,
                        json.dumps(responsibilities),
                        json.dumps(qualifications),
                        how_to_apply,
                        salary_info,
                        contact,
                        equal_opportunity
                    ))
                    job_id = cursor.lastrowid
                    stats['new_jobs'] += 1

                    if legislator_match:
                        stats['enriched_jobs'] += 1

                # Record this posting
                cursor.execute("""
                    INSERT INTO job_postings (
                        job_id, source_file, bulletin_date,
                        original_job_id, position_title, office, location, posting_date,
                        description, responsibilities_json, qualifications_json,
                        how_to_apply, salary_info, contact, equal_opportunity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job_id,
                    source_file,
                    bulletin_date,
                    job.get('id'),
                    position_title,
                    office,
                    location,
                    posting_date,
                    description,
                    json.dumps(responsibilities),
                    json.dumps(qualifications),
                    how_to_apply,
                    salary_info,
                    contact,
                    equal_opportunity
                ))

            except Exception as e:
                print(f"  Error inserting job from {source_file}: {e}")
                stats['skipped'] += 1
                continue

        self.conn.commit()
        return stats

    def _extract_date_from_filename(self, filename: str) -> Optional[str]:
        """Extract date from filename in various formats."""
        # Try YYYY_MM_DD format (e.g., 2024_10_28)
        match = re.search(r'(\d{4})_(\d{2})_(\d{2})', filename)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

        # Try MM-DD-YY format (e.g., 01-06-14)
        match = re.search(r'(\d{2})-(\d{2})-(\d{2})', filename)
        if match:
            mm, dd, yy = match.groups()
            # Assume 20XX for years
            year = f"20{yy}" if int(yy) < 50 else f"19{yy}"
            return f"{year}-{mm}-{dd}"

        # Try M.DD.YYYY format (e.g., 1.26.2015)
        match = re.search(r'(\d{1,2})\.(\d{2})\.(\d{4})', filename)
        if match:
            m, dd, yyyy = match.groups()
            return f"{yyyy}-{m.zfill(2)}-{dd}"

        return None

    def load_directory(self, directory: str, pattern: str = "*.json", source_type: str = "json"):
        """Load all JSON files from a directory."""
        directory = Path(directory)
        files = sorted(directory.glob(pattern))

        total_stats = defaultdict(int)

        print(f"\nLoading jobs from {len(files)} files in {directory}...")

        for i, file_path in enumerate(files, 1):
            try:
                stats = self.load_jobs_from_json(str(file_path), source_type)
                for key, value in stats.items():
                    total_stats[key] += value

                if i % 50 == 0:
                    print(f"  Processed {i}/{len(files)} files...")

            except Exception as e:
                print(f"  Error processing {file_path.name}: {e}")
                continue

        print(f"\n✓ Loading complete!")
        print(f"  Total processed: {total_stats['total_processed']}")
        print(f"  New jobs: {total_stats['new_jobs']}")
        print(f"  Reposted jobs: {total_stats['reposted_jobs']}")
        print(f"  Enriched with legislator data: {total_stats['enriched_jobs']}")

        return total_stats

    def get_stats(self) -> Dict:
        """Get database statistics."""
        cursor = self.conn.cursor()

        stats = {}

        # Total jobs
        cursor.execute("SELECT COUNT(*) FROM jobs")
        stats['total_jobs'] = cursor.fetchone()[0]

        # Active jobs
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'active'")
        stats['active_jobs'] = cursor.fetchone()[0]

        # Jobs with party data
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE party IS NOT NULL")
        stats['jobs_with_party'] = cursor.fetchone()[0]

        # Postings
        cursor.execute("SELECT COUNT(*) FROM job_postings")
        stats['total_postings'] = cursor.fetchone()[0]

        # Legislators
        cursor.execute("SELECT COUNT(*) FROM legislators")
        stats['legislators'] = cursor.fetchone()[0]

        # Date range
        cursor.execute("SELECT MIN(first_posted), MAX(last_posted) FROM jobs")
        result = cursor.fetchone()
        stats['date_range'] = f"{result[0]} to {result[1]}"

        # Jobs by party
        cursor.execute("""
            SELECT party, COUNT(*) as count
            FROM jobs
            WHERE party IS NOT NULL
            GROUP BY party
            ORDER BY count DESC
        """)
        stats['by_party'] = dict(cursor.fetchall())

        return stats


def main():
    """Main entry point for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(description="Load congressional job data into SQLite")
    parser.add_argument('--db', default='congress_jobs.db', help='Database path')
    parser.add_argument('--legislators', help='Path to legislators-current.yaml')
    parser.add_argument('--load-dir', help='Directory containing JSON files to load')
    parser.add_argument('--load-file', help='Single JSON file to load')
    parser.add_argument('--stats', action='store_true', help='Show database statistics')

    args = parser.parse_args()

    with CongressionalJobsDB(args.db) as db:
        if args.legislators:
            db.load_legislators(args.legislators)

        if args.load_file:
            stats = db.load_jobs_from_json(args.load_file)
            print(f"\nLoaded from {args.load_file}:")
            print(f"  New jobs: {stats['new_jobs']}")
            print(f"  Reposted: {stats['reposted_jobs']}")
            print(f"  Enriched: {stats['enriched_jobs']}")

        if args.load_dir:
            db.load_directory(args.load_dir)

        if args.stats or not any([args.legislators, args.load_file, args.load_dir]):
            stats = db.get_stats()
            print("\n=== Database Statistics ===")
            print(f"Total unique jobs: {stats['total_jobs']}")
            print(f"Active jobs: {stats['active_jobs']}")
            print(f"Total postings: {stats['total_postings']}")
            print(f"Jobs with party data: {stats['jobs_with_party']}")
            print(f"Legislators loaded: {stats['legislators']}")
            print(f"Date range: {stats['date_range']}")
            if stats['by_party']:
                print("\nJobs by party:")
                for party, count in stats['by_party'].items():
                    print(f"  {party}: {count}")


if __name__ == '__main__':
    main()
