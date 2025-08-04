#!/usr/bin/env uv run python
"""
Congressional Job Classification Analyzer

This script analyzes the classified congressional job data and generates reports
showing distribution of job categories over time and by various dimensions.
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict, Counter
import re

# Optional imports for analysis
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

def parse_date_from_filename(filename: str) -> Optional[str]:
    """Extract date from filename and normalize to YYYY-MM-DD format."""
    # Try various date patterns in filenames
    patterns = [
        r'(\d{4})_(\d{1,2})_(\d{1,2})',  # 2024_11_04
        r'(\d{1,2})[-_](\d{1,2})[-_](\d{2,4})',  # 11-04-24 or 11_04_2024
        r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})',  # 11.04.24
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            groups = match.groups()
            if len(groups) == 3:
                # Handle different date formats
                if len(groups[2]) == 2:  # 2-digit year
                    year = 2000 + int(groups[2]) if int(groups[2]) < 50 else 1900 + int(groups[2])
                else:
                    year = int(groups[2])
                
                # Determine if first group is year or month
                if len(groups[0]) == 4:  # YYYY_MM_DD
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                else:  # MM_DD_YY or MM_DD_YYYY
                    month, day = int(groups[0]), int(groups[1])
                
                try:
                    return f"{year:04d}-{month:02d}-{day:02d}"
                except ValueError:
                    continue
    
    return None

def load_classified_data(directory: str) -> List[Dict]:
    """Load all classified job data from JSON files."""
    all_jobs = []
    
    data_path = Path(directory)
    if not data_path.exists():
        print(f"Directory {directory} does not exist")
        return []
    
    for json_file in data_path.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                jobs = json.load(f)
            
            if not isinstance(jobs, list):
                continue
            
            # Add filename info to each job
            file_date = parse_date_from_filename(json_file.name)
            for job in jobs:
                job['source_file'] = json_file.name
                job['file_date'] = file_date
                all_jobs.append(job)
                
        except Exception as e:
            print(f"Error loading {json_file}: {e}")
    
    return all_jobs

def analyze_category_distribution(jobs: List[Dict]) -> Dict:
    """Analyze the distribution of job categories."""
    categories = [job.get('job_category', 'unclassified') for job in jobs]
    category_counts = Counter(categories)
    
    total_jobs = len(jobs)
    distribution = {
        'counts': dict(category_counts),
        'percentages': {cat: (count/total_jobs)*100 for cat, count in category_counts.items()},
        'total': total_jobs
    }
    
    return distribution

def analyze_temporal_trends(jobs: List[Dict]) -> Dict:
    """Analyze how job categories change over time."""
    # Group jobs by date
    jobs_by_date = defaultdict(lambda: defaultdict(int))
    
    for job in jobs:
        date = job.get('posting_date') or job.get('file_date')
        if date:
            category = job.get('job_category', 'unclassified')
            jobs_by_date[date][category] += 1
    
    return dict(jobs_by_date)

def analyze_position_titles(jobs: List[Dict]) -> Dict:
    """Analyze most common position titles by category."""
    titles_by_category = defaultdict(Counter)
    
    for job in jobs:
        category = job.get('job_category', 'unclassified')
        title = job.get('position_title', 'Unknown')
        titles_by_category[category][title] += 1
    
    # Get top 10 for each category
    top_titles = {}
    for category, titles in titles_by_category.items():
        top_titles[category] = titles.most_common(10)
    
    return top_titles

def analyze_offices(jobs: List[Dict]) -> Dict:
    """Analyze job distribution by congressional office."""
    offices_by_category = defaultdict(Counter)
    
    for job in jobs:
        category = job.get('job_category', 'unclassified')
        office = job.get('office', 'Unknown')
        # Clean up office names
        office = office.replace('Congressman ', '').replace('Congresswoman ', '').replace('Representative ', '')
        offices_by_category[category][office] += 1
    
    return dict(offices_by_category)

def generate_summary_report(jobs: List[Dict]) -> str:
    """Generate a text summary report."""
    distribution = analyze_category_distribution(jobs)
    temporal_trends = analyze_temporal_trends(jobs)
    top_titles = analyze_position_titles(jobs)
    
    report = []
    report.append("CONGRESSIONAL JOB CLASSIFICATION REPORT")
    report.append("=" * 50)
    report.append("")
    
    # Overall distribution
    report.append(f"Total Jobs Analyzed: {distribution['total']}")
    report.append("")
    report.append("Category Distribution:")
    for category, count in distribution['counts'].items():
        percentage = distribution['percentages'][category]
        report.append(f"  {category.replace('_', ' ').title()}: {count} ({percentage:.1f}%)")
    
    report.append("")
    
    # Temporal analysis
    if temporal_trends:
        report.append("Temporal Coverage:")
        dates = sorted(temporal_trends.keys())
        if dates:
            report.append(f"  Date Range: {dates[0]} to {dates[-1]}")
            report.append(f"  Files Analyzed: {len(dates)}")
    
    report.append("")
    
    # Top position titles by category
    report.append("Most Common Position Titles by Category:")
    for category, titles in top_titles.items():
        if titles:
            report.append(f"\n  {category.replace('_', ' ').title()}:")
            for title, count in titles[:5]:  # Top 5
                report.append(f"    {title}: {count}")
    
    return "\n".join(report)

def create_visualizations(jobs: List[Dict], output_dir: str):
    """Create visualization charts."""
    if not HAS_MATPLOTLIB:
        print("Matplotlib not available. Skipping visualizations.")
        print("Install with: pip install matplotlib seaborn")
        return
        
    try:
        import seaborn as sns
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Set style
        plt.style.use('default')
        sns.set_palette("husl")
        
        # 1. Category Distribution Pie Chart
        distribution = analyze_category_distribution(jobs)
        
        plt.figure(figsize=(10, 8))
        categories = list(distribution['counts'].keys())
        counts = list(distribution['counts'].values())
        
        # Clean up category names for display
        display_categories = [cat.replace('_', ' ').title() for cat in categories]
        
        plt.pie(counts, labels=display_categories, autopct='%1.1f%%', startangle=90)
        plt.title('Distribution of Congressional Job Categories', fontsize=16, fontweight='bold')
        plt.axis('equal')
        plt.tight_layout()
        plt.savefig(f'{output_dir}/category_distribution.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. Temporal trends (if enough data)
        temporal_trends = analyze_temporal_trends(jobs)
        if len(temporal_trends) > 5:  # Only if we have enough data points
            
            # Convert to DataFrame for easier plotting
            df_list = []
            for date, categories in temporal_trends.items():
                for category, count in categories.items():
                    df_list.append({'date': date, 'category': category, 'count': count})
            
            if df_list and HAS_PANDAS:
                df = pd.DataFrame(df_list)
                df['date'] = pd.to_datetime(df['date'])
                
                plt.figure(figsize=(15, 8))
                
                # Pivot for plotting
                pivot_df = df.pivot(index='date', columns='category', values='count').fillna(0)
                
                for category in pivot_df.columns:
                    plt.plot(pivot_df.index, pivot_df[category], 
                           marker='o', label=category.replace('_', ' ').title(), linewidth=2)
                
                plt.title('Congressional Job Postings Over Time by Category', fontsize=16, fontweight='bold')
                plt.xlabel('Date', fontsize=12)
                plt.ylabel('Number of Job Postings', fontsize=12)
                plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
                plt.grid(True, alpha=0.3)
                plt.xticks(rotation=45)
                plt.tight_layout()
                plt.savefig(f'{output_dir}/temporal_trends.png', dpi=300, bbox_inches='tight')
                plt.close()
        
        print(f"Visualizations saved to {output_dir}/")
        
    except ImportError as e:
        print(f"Visualization libraries not available: {e}")
        print("Install with: pip install matplotlib seaborn")

def main():
    """Main analysis function."""
    # Configuration
    classified_dir = "json_classified"
    output_dir = "analysis_reports"
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Load data
    print("Loading classified job data...")
    jobs = load_classified_data(classified_dir)
    
    if not jobs:
        print(f"No classified job data found in {classified_dir}/")
        print("Run job_classifier.py first to classify jobs.")
        return
    
    print(f"Loaded {len(jobs)} classified jobs")
    
    # Generate analyses
    print("Generating analyses...")
    
    # 1. Summary report
    summary = generate_summary_report(jobs)
    
    # Save summary report
    with open(f"{output_dir}/classification_summary.txt", "w", encoding="utf-8") as f:
        f.write(summary)
    
    print(summary)
    
    # 2. Detailed CSV export for further analysis
    job_records = []
    for job in jobs:
        record = {
            'id': job.get('id', ''),
            'position_title': job.get('position_title', ''),
            'office': job.get('office', ''),
            'location': job.get('location', ''),
            'posting_date': job.get('posting_date', ''),
            'job_category': job.get('job_category', ''),
            'source_file': job.get('source_file', ''),
            'file_date': job.get('file_date', ''),
            'salary_info': job.get('salary_info', ''),
        }
        job_records.append(record)
    
    # Save to CSV
    if HAS_PANDAS:
        try:
            df = pd.DataFrame(job_records)
            df.to_csv(f"{output_dir}/classified_jobs.csv", index=False, encoding='utf-8')
            print(f"\nDetailed data exported to {output_dir}/classified_jobs.csv")
        except Exception as e:
            print(f"Error creating CSV: {e}")
    else:
        # Manual CSV creation without pandas
        try:
            import csv
            with open(f"{output_dir}/classified_jobs.csv", "w", newline='', encoding='utf-8') as csvfile:
                if job_records:
                    fieldnames = job_records[0].keys()
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(job_records)
                    print(f"\nDetailed data exported to {output_dir}/classified_jobs.csv")
        except Exception as e:
            print(f"Error creating CSV: {e}")
    
    # 3. Create visualizations
    print("\nGenerating visualizations...")
    create_visualizations(jobs, output_dir)
    
    print(f"\nAnalysis complete! Reports saved to {output_dir}/")

if __name__ == "__main__":
    main()
