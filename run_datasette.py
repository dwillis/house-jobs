#!/usr/bin/env python3
"""
Launch Datasette interface for Congressional Jobs database.

Datasette provides a powerful, zero-code web interface for exploring SQLite databases
with built-in faceted search, custom queries, JSON API, and CSV exports.
"""

import subprocess
import sys
from pathlib import Path

DB_PATH = "congress_jobs.db"
METADATA_PATH = "metadata.yml"

if not Path(DB_PATH).exists():
    print(f"❌ Error: Database not found at {DB_PATH}")
    print("Please run init_database.py first to create the database")
    sys.exit(1)

print("=" * 60)
print("Congressional Jobs Research Database - Datasette Interface")
print("=" * 60)
print(f"\n📊 Database: {DB_PATH}")
print(f"📝 Metadata: {METADATA_PATH}")
print("\n🚀 Starting Datasette...")
print("\nFeatures available:")
print("  • Faceted search and filtering")
print("  • Pre-built research queries")
print("  • JSON API for all data")
print("  • CSV/JSON export")
print("  • Custom SQL query interface")
print("  • Full database exploration")
print("\n" + "=" * 60)
print("\nServer will start at http://localhost:8001")
print("Press Ctrl+C to stop")
print("=" * 60 + "\n")

# Launch Datasette with configuration
cmd = [
    "datasette",
    DB_PATH,
    "--metadata", METADATA_PATH,
    "--port", "8001",
    "--setting", "sql_time_limit_ms", "5000",
    "--setting", "default_page_size", "50",
    "--setting", "max_returned_rows", "1000",
    "--setting", "num_sql_threads", "3",
]

try:
    subprocess.run(cmd)
except KeyboardInterrupt:
    print("\n\n✅ Datasette stopped")
