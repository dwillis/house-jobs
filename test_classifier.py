#!/usr/bin/env uv run python
"""
Test script for the congressional job classifier.
Tests the classification on a small sample before running on the full dataset.
"""

import json
import os
from job_classifier import classify_job

def test_sample_job():
    """Test classification on a sample job."""
    sample_job = {
        "id": "MEM-TEST-01",
        "position_title": "Legislative Assistant",
        "office": "Congressman John Doe",
        "location": "Washington, D.C.",
        "posting_date": "2024-07-30",
        "description": "The Legislative Assistant will work closely with the Member and senior staff to develop and advance the Member's legislative priorities. This position requires strong research and writing skills to analyze proposed legislation and draft policy memos.",
        "responsibilities": [
            "Research and analyze proposed legislation",
            "Draft policy memos and legislative summaries", 
            "Track committee activity and floor votes",
            "Attend committee hearings and briefings",
            "Coordinate with other congressional offices on legislation"
        ],
        "qualifications": [
            "Bachelor's degree required",
            "Experience in policy research or government",
            "Excellent written and verbal communication skills",
            "Knowledge of the legislative process"
        ],
        "how_to_apply": "Send resume and cover letter to jobs@example.gov",
        "salary_info": "$45,000 - $55,000",
        "contact": "jobs@example.gov",
        "equal_opportunity": "Equal opportunity employer"
    }
    
    print("Testing job classifier...")
    print(f"Sample job: {sample_job['position_title']}")
    print("Expected category: legislative")
    
    classification = classify_job(sample_job)
    print(f"Actual classification: {classification}")
    
    if classification == "legislative":
        print("✅ Test PASSED!")
    else:
        print("❌ Test FAILED!")
    
    return classification == "legislative"

def test_multiple_categories():
    """Test classification on multiple job types."""
    test_jobs = [
        {
            "position_title": "Press Secretary",
            "description": "Manage media relations and public communications for the Member",
            "responsibilities": ["Write press releases", "Coordinate with media", "Manage social media"],
            "expected": "communications"
        },
        {
            "position_title": "District Representative", 
            "description": "Serve constituents in the district and handle casework",
            "responsibilities": ["Handle constituent casework", "Represent Member at events", "Community outreach"],
            "expected": "constituent_services"
        },
        {
            "position_title": "Office Manager",
            "description": "Manage day-to-day office operations and administrative tasks", 
            "responsibilities": ["Manage office operations", "Handle scheduling", "Coordinate staff activities"],
            "expected": "administrative"
        },
        {
            "position_title": "Legislative Counsel",
            "description": "Provide legal analysis on proposed legislation and policy matters",
            "responsibilities": ["Legal research", "Bill analysis", "Policy recommendations"],
            "expected": "legislative"
        }
    ]
    
    print("\nTesting multiple job categories...")
    passed = 0
    total = len(test_jobs)
    
    for i, job_data in enumerate(test_jobs, 1):
        # Create a minimal job dict for testing
        job = {
            "id": f"TEST-{i:02d}",
            "position_title": job_data["position_title"],
            "description": job_data["description"],
            "responsibilities": job_data["responsibilities"],
            "qualifications": [],
            "office": "Test Office"
        }
        
        print(f"\nTest {i}/{total}: {job['position_title']}")
        print(f"Expected: {job_data['expected']}")
        
        classification = classify_job(job)
        print(f"Actual: {classification}")
        
        if classification == job_data["expected"]:
            print("✅ PASSED")
            passed += 1
        else:
            print("❌ FAILED")
    
    print(f"\nResults: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    return passed == total

def main():
    """Run all tests."""
    print("Congressional Job Classifier Test Suite")
    print("=" * 40)
    
    # Check if LLM is available
    try:
        import subprocess
        result = subprocess.run(['uv', 'run', 'llm', '--version'], capture_output=True, text=True)
        print(f"LLM version: {result.stdout.strip()}")
    except Exception as e:
        print(f"Error checking LLM: {e}")
        print("Make sure 'uv' is installed and 'llm' is available via 'uv run llm --version'")
        return
    
    # Run tests
    test1_passed = test_sample_job()
    test2_passed = test_multiple_categories()
    
    print("\n" + "=" * 40)
    if test1_passed and test2_passed:
        print("🎉 All tests PASSED! The classifier is working correctly.")
        print("You can now run the full classification with: python job_classifier.py")
    else:
        print("⚠️  Some tests FAILED. Check the LLM responses and prompts.")

if __name__ == "__main__":
    main()
