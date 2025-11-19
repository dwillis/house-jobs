#!/usr/bin/env python3
"""
Initialize the congressional jobs database with all existing data.
"""

import os
from pathlib import Path
from db_loader import CongressionalJobsDB


def main():
    print("=" * 60)
    print("Congressional Jobs Research Database Initialization")
    print("=" * 60)

    # Paths
    db_path = "congress_jobs.db"
    legislators_path = "/tmp/congress-legislators/legislators-current.yaml"
    json_dir = "json_gemini_flash"

    # Check if legislators data exists
    if not Path(legislators_path).exists():
        print(f"\n⚠ Legislators data not found at {legislators_path}")
        print("Please ensure congress-legislators repo is cloned to /tmp/congress-legislators")
        return

    # Check if JSON directory exists
    if not Path(json_dir).exists():
        print(f"\n⚠ JSON directory not found: {json_dir}")
        return

    # Initialize database
    print(f"\n📊 Initializing database: {db_path}")

    with CongressionalJobsDB(db_path) as db:
        # Load legislators
        print("\n1️⃣  Loading current House members...")
        db.load_legislators(legislators_path)

        # Load all jobs
        print("\n2️⃣  Loading job listings from JSON files...")
        db.load_directory(json_dir, pattern="*.json", source_type="gemini_flash")

        # Show statistics
        print("\n" + "=" * 60)
        print("Database Statistics")
        print("=" * 60)
        stats = db.get_stats()

        print(f"\n📋 Jobs:")
        print(f"   • Total unique jobs: {stats['total_jobs']}")
        print(f"   • Active jobs: {stats['active_jobs']}")
        print(f"   • Total postings: {stats['total_postings']}")
        print(f"   • Enriched with legislator data: {stats['jobs_with_party']}")

        print(f"\n👥 Legislators:")
        print(f"   • Current House members loaded: {stats['legislators']}")

        print(f"\n📅 Date Range:")
        print(f"   • {stats['date_range']}")

        if stats['by_party']:
            print(f"\n🎯 Jobs by Party:")
            for party, count in stats['by_party'].items():
                pct = (count / stats['jobs_with_party'] * 100) if stats['jobs_with_party'] > 0 else 0
                print(f"   • {party}: {count} ({pct:.1f}%)")

        # Calculate enrichment rate
        enrichment_rate = (stats['jobs_with_party'] / stats['total_jobs'] * 100) if stats['total_jobs'] > 0 else 0
        print(f"\n✨ Enrichment Rate: {enrichment_rate:.1f}%")

        print("\n" + "=" * 60)
        print("✅ Database initialization complete!")
        print("=" * 60)
        print(f"\nDatabase file: {db_path}")
        print(f"Size: {Path(db_path).stat().st_size / 1024 / 1024:.2f} MB")
        print("\nYou can now:")
        print("  • Query the database with SQLite")
        print("  • Use the web interface (run web_interface.py)")
        print("  • Load additional data with db_loader.py")


if __name__ == '__main__':
    main()
