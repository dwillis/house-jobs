import os
import json
import subprocess
import time
from typing import List, Dict
import re

def split_into_job_chunks(text: str) -> List[str]:
    """Split text into chunks based on MEM- pattern while keeping each job listing intact."""
    # Split on MEM- pattern but keep the delimiter
    chunks = re.split(r'(?=MEM-)', text)[1:]
    # Remove empty chunks and strip whitespace
    return [chunk.strip() for chunk in chunks if chunk.strip()]

def process_chunk(chunk: str, example_text: str, filename: str) -> List[Dict]:
    """Process a single chunk using the LLM."""
    try:
        # Write chunk to temporary file
        with open("temp_chunk.txt", "w", encoding="utf-8") as f:
            f.write(filename + "\n" + chunk)

        command = f"""cat temp_chunk.txt | llm --system $'You are an expert in parsing congressional job listings from text files split into chunks. Extract job listings into a structured JSON array where each listing is an object with consistent fields. Handle the following formatting requirements: \\
            1. Convert any non-ASCII characters \\(including smartquotes, em-dashes, etc.\\) to their closest ASCII equivalent \\
            2. Normalize bullet points and list formatting into consistent structures \\
            3. Maintain hierarchical relationships in nested lists \\
            4. Preserve paragraph breaks in description fields \\
            5. Format all dates in ISO 8601 format \\(YYYY-MM-DD\\)' \\
            -m gemini-2.5-pro-preview-06-05 -o json_object 1 \\
            $'Create a JSON array containing objects for each job listing with the following required fields: \\
            - id: Job ID in format "MEM-XXX-YY", where XXX is the number from the listing \\(do not use literally XXX\\). do not carry over IDs from one chunk to the next. \\
            - position_title: Full position title \\
            - office: Congressional office or committee name - do not use placeholders \\
            - location: Primary work location \\
            - posting_date: Date from filename \\(format: YYYY-MM-DD\\) \\
            - description: Full job description \\
            - responsibilities: Array of responsibilities \\
            - qualifications: Array of required qualifications \\
            - how_to_apply: Application instructions \\
            - salary_info: Salary information if provided \\(use null if not specified\\) \\
            - contact: Contact information for applications \\
            - equal_opportunity: Equal opportunity statement if present \\(use null if not specified\\) \\
            Do not process introductory boilerplate language or subscribe/unsubscribe sections as job listings. Format all text fields as UTF-8 strings, convert bullet points to array elements, and maintain paragraph structure in longer text fields. Remove any formatting characters while preserving the semantic structure of the content.'"""

        # Run command and capture both stdout and stderr
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            check=True
        )

        # Print command output for debugging if needed
        if result.stderr:
            print(f"Command stderr: {result.stderr}")

        try:
            parsed_jobs = json.loads(result.stdout)
            return parsed_jobs
        except json.JSONDecodeError as je:
            print(f"JSON Decode Error: {je}")
            print(f"Raw output that failed to parse: {result.stdout}...")  # Print first 500 chars
            return []

    except subprocess.CalledProcessError as ce:
        print(f"Command failed with return code: {ce.returncode}")
        print(f"Command stdout: {ce.stdout}")
        print(f"Command stderr: {ce.stderr}")
        print(f"Failed command: {command}")
        return []
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return []
    finally:
        # Clean up temporary file
        if os.path.exists("temp_chunk.txt"):
            try:
                os.remove("temp_chunk.txt")
            except Exception as e:
                print(f"Error removing temporary file: {e}")

def main():
    directory_path = "output"
    output_dir = "json_gemini_flash"  # change this depending on the llm
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Get list of already processed files
    output_files = {f.split('.json')[0] for f in os.listdir(output_dir)}
    
    # Example template for JSON structure
    example = [{
        "date": "2024-11-04",
        "id": "MEM-458-24",
        "office": "Congressman Steven Horsford",
        "position": "District Representative",
        "location": "North Las Vegas, Nevada",
        "key_responsibilities": [
            "strengthening relationships with key stakeholders, as well as attending engagements on behalf of the Member",
            "helping constituents resolve problems with federal agencies through written and verbal communication"
        ],
        "requirements": [
            "Political knowledge and comfortable navigating complicated situations",
            "Strong written, verbal, analytical, and organization skills; impeccable customer service manners; public speaking skills"
        ],
        "job_type": "Full-time",
        "salary": "Commensurate with experience",
        "email": "NV04Resume@mail.house.gov"
    }]
    example_text = json.dumps(example)

    for filename in os.listdir(directory_path):
        if 'Member' in filename and filename.endswith(".txt") and filename.split(".txt")[0] not in output_files:
            print(f"Processing {filename}")
            
            # Read the entire file
            with open(os.path.join(directory_path, filename), "r", encoding="utf-8") as f:
                text_string = f.read()
            
            # Split into manageable chunks
            chunks = split_into_job_chunks(text_string)
            all_jobs = []
            
            # Process each chunk
            for i, chunk in enumerate(chunks):
                print(f"Processing chunk {i+1}/{len(chunks)} of {filename}")
                time.sleep(8)  # Rate limiting
                jobs = process_chunk(chunk, example_text, filename)
                all_jobs.extend(jobs)
            
            # Write combined results to output file
            output_path = os.path.join(output_dir, filename.replace('.txt', '.json'))
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(all_jobs, f, indent=2, ensure_ascii=False)
            
            print(f"Completed processing {filename}")
            time.sleep(5)  # Rate limiting between files

if __name__ == "__main__":
    main()