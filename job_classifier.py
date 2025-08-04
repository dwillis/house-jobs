#!/usr/bin/env uv run python
"""
Congressional Job Classifier

This script classifies congressional job listings into four categories:
- administrative: Office management, HR, scheduling, administrative support
- legislative: Policy research, bill analysis, committee work, legal research
- communications: Press, media relations, social media, public outreach
- constituent_services: Casework, community engagement, district representation

Uses the LLM library for AI-powered classification based on job descriptions,
responsibilities, and qualifications.
"""

import os
import json
import subprocess
import time
from typing import List, Dict, Optional
from pathlib import Path

def classify_job(job_data: Dict) -> Optional[str]:
    """
    Classify a single job using the LLM library.
    
    Args:
        job_data: Dictionary containing job information
        
    Returns:
        Classification category or None if classification fails
    """
    try:
        # Extract relevant fields for classification
        position_title = job_data.get('position_title', '')
        description = job_data.get('description', '')
        responsibilities = job_data.get('responsibilities', [])
        qualifications = job_data.get('qualifications', [])
        office = job_data.get('office', '')
        
        # Combine responsibilities and qualifications into strings
        responsibilities_text = ' '.join(responsibilities) if isinstance(responsibilities, list) else str(responsibilities)
        qualifications_text = ' '.join(qualifications) if isinstance(qualifications, list) else str(qualifications)
        
        # Create the text to be classified
        job_text = f"""Position Title: {position_title}
Office: {office}
Description: {description}
Responsibilities: {responsibilities_text}
Qualifications: {qualifications_text}"""
        
        # Create the classification prompt
        system_prompt = """You are an expert in categorizing congressional job positions. You must classify each job into exactly one of these four categories:

1. administrative - Office management, human resources, scheduling, administrative support, finance, operations, executive assistance, office coordination
2. legislative - Policy research, bill analysis, committee work, legal research, legislative counsel, legislative assistant, policy advisor
3. communications - Press secretary, communications director, media relations, social media, public outreach, marketing, digital communications
4. constituent_services - Casework, community engagement, district representation, field representative, outreach coordinator, constituent liaison

Respond with ONLY the category name (administrative, legislative, communications, or constituent_services). Do not include any other text or explanation."""

        user_prompt = """Classify this congressional job position into one of the four categories: administrative, legislative, communications, or constituent_services.

Based on the job title, description, responsibilities, and qualifications, determine which category best fits this position."""

        # Run the LLM command with direct input
        result = subprocess.run(
            ['uv', 'run', 'llm', '--system', system_prompt, '-m', 'gemini-2.5-flash', user_prompt],
            input=job_text,
            capture_output=True,
            text=True,
            check=True
        )
        
        classification = result.stdout.strip().lower()
        
        # Validate the classification
        valid_categories = ['administrative', 'legislative', 'communications', 'constituent_services']
        if classification in valid_categories:
            return classification
        else:
            print(f"Invalid classification '{classification}' for job {job_data.get('id', 'unknown')}")
            return None
            
    except subprocess.CalledProcessError as e:
        print(f"LLM command failed for job {job_data.get('id', 'unknown')}: {e}")
        print(f"Command stderr: {e.stderr}")
        return None
    except Exception as e:
        print(f"Unexpected error classifying job {job_data.get('id', 'unknown')}: {e}")
        return None

def process_json_file(input_file: str) -> Dict[str, int]:
    """
    Process a single JSON file and add classifications to each job, updating the file in place.
    
    Args:
        input_file: Path to JSON file to process and update
        
    Returns:
        Dictionary with classification counts
    """
    print(f"Processing {os.path.basename(input_file)}...")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            jobs = json.load(f)
        
        if not isinstance(jobs, list):
            print(f"Warning: {input_file} does not contain a list of jobs")
            return {}
        
        # Check if any jobs already have classifications
        already_classified = any('job_category' in job for job in jobs)
        if already_classified:
            print(f"  File already contains classifications, skipping...")
            return {}
        
        classification_counts = {
            'administrative': 0,
            'legislative': 0,
            'communications': 0,
            'constituent_services': 0,
            'unclassified': 0
        }
        
        for i, job in enumerate(jobs):
            print(f"  Classifying job {i+1}/{len(jobs)}: {job.get('position_title', 'Unknown')}")
            
            # Add small delay to respect rate limits
            time.sleep(2)
            
            classification = classify_job(job)
            
            # Add classification directly to the job data
            if classification:
                job['job_category'] = classification
                classification_counts[classification] += 1
            else:
                job['job_category'] = 'unclassified'
                classification_counts['unclassified'] += 1
        
        # Write updated jobs back to the same file
        with open(input_file, 'w', encoding='utf-8') as f:
            json.dump(jobs, f, indent=2, ensure_ascii=False)
        
        print(f"  Completed {os.path.basename(input_file)}")
        print(f"  Classifications: {classification_counts}")
        
        return classification_counts
        
    except Exception as e:
        print(f"Error processing {input_file}: {e}")
        return {}

def main():
    """Main function to process all JSON files."""
    # Configuration
    input_dir = "json_gemini_flash"
    
    # Get list of JSON files to process
    input_path = Path(input_dir)
    if not input_path.exists():
        print(f"Error: Input directory '{input_dir}' does not exist")
        return
    
    json_files = list(input_path.glob("*.json"))
    if not json_files:
        print(f"No JSON files found in '{input_dir}'")
        return
    
    # Process files
    total_counts = {
        'administrative': 0,
        'legislative': 0,
        'communications': 0,
        'constituent_services': 0,
        'unclassified': 0
    }
    
    files_processed = 0
    files_skipped = 0
    
    for json_file in sorted(json_files):
        file_counts = process_json_file(str(json_file))
        
        # Add to total counts only if file was actually processed
        if file_counts:
            for category, count in file_counts.items():
                total_counts[category] += count
            files_processed += 1
            
            # Add delay between files to respect rate limits
            print("  Waiting 5 seconds before next file...")
            time.sleep(5)
        else:
            files_skipped += 1
    
    # Print summary
    print("\n" + "="*50)
    print("CLASSIFICATION SUMMARY")
    print("="*50)
    print(f"Files processed: {files_processed}")
    print(f"Files skipped (already classified): {files_skipped}")
    print(f"Total jobs classified: {sum(total_counts.values())}")
    
    if sum(total_counts.values()) > 0:
        print("\nBreakdown by category:")
        for category, count in total_counts.items():
            percentage = (count / sum(total_counts.values()) * 100)
            print(f"  {category}: {count} ({percentage:.1f}%)")
    
    print(f"\nJSON files updated in: {input_dir}/")
    print("Each job listing now has a 'job_category' field.")

if __name__ == "__main__":
    main()
