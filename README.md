# house-jobs
PDF files of House of Representatives Job and Internship Announcements

This repository contains tools for extracting, processing, and structuring job listings from the U.S. House of Representatives. See related blog post: https://thescoop.org/archives/2025/02/28/turning-congressional-job-listings-into-data/index.html

## Overview

The House of Representatives regularly distributes PDF files containing job and internship announcements from members and committees. This project:

1. Collects these PDF files
2. Extracts the text content
3. Processes the text using Large Language Models (LLMs)
4. Produces structured JSON files with detailed information about each job listing

This is a public archive of those files.

## Process Flow

```
PDF Files → Text Extraction → LLM Processing → Structured JSON
```

### 1. PDF Collection

Weekly emails from the House of Representatives include PDF attachments with job and internship listings. These are archived in this repository.

### 2. Text Extraction

The PDFs are converted to plain text files using `pdftotext`, triggered by GitHub Actions. The extracted text files are stored in the `output` directory with filenames that include the date of the listing.

### 3. LLM Processing

Two parser implementations are provided:

#### Parser 1 (`parser.py`)

The first approach:
- Processes entire text files at once
- Uses the Gemini 1.5 Flash model
- Formats output as a JSON array of job listings
- Handles basic text normalization

#### Parser 2 (`parser2.py`)

The improved implementation:
- Splits text into chunks based on job IDs (MEM-xxx-yy pattern)
- Processes each chunk separately
- Uses the Gemini 2.0 Flash model
- Implements more robust error handling
- Provides more comprehensive field extraction
- Includes better handling of non-ASCII characters and formatting

### 4. JSON Output

The final output is stored in JSON files with a structured format. Each job listing contains fields such as:

- `id`: Job ID in MEM-XXX-YY format
- `position_title`: Full position title
- `office`: Congressional office or committee name
- `location`: Primary work location
- `posting_date`: Date in YYYY-MM-DD format
- `description`: Full job description
- `responsibilities`: Array of responsibilities
- `qualifications`: Array of required qualifications
- `how_to_apply`: Application instructions
- `salary_info`: Salary information
- `contact`: Contact information
- `equal_opportunity`: Equal opportunity statement

## Example

Here's an example of a parsed job listing:

```json
{
  "id": "MEM-458-24",
  "office": "Congressman Steven Horsford",
  "position_title": "District Representative",
  "location": "North Las Vegas, Nevada",
  "posting_date": "2024-11-04",
  "responsibilities": [
    "strengthening relationships with key stakeholders, as well as attending engagements on behalf of the Member",
    "helping constituents resolve problems with federal agencies through written and verbal communication"
  ],
  "qualifications": [
    "Political knowledge and comfortable navigating complicated situations",
    "Strong written, verbal, analytical, and organization skills; impeccable customer service manners; public speaking skills"
  ],
  "job_type": "Full-time",
  "salary_info": "Commensurate with experience",
  "contact": "NV04Resume@mail.house.gov",
  "how_to_apply": "Submit resume and cover letter to NV04Resume@mail.house.gov",
  "description": "The Office of Congressman Steven Horsford seeks a District Representative to serve constituents in Nevada's 4th Congressional District.",
  "equal_opportunity": "The Office of Congressman Steven Horsford is an Equal Opportunity Employer."
}
```

## Usage

1. Place PDF-extracted text files in the `output` directory
2. Run either parser:
   ```bash
   python parser.py
   # or
   python parser2.py
   ```
3. Find parsed JSON files in the `json_gemini_flash` directory

## Requirements

- Python 3.6+
- Gemini API access
- Subprocess module
- JSON module
- Regular expressions library

## Contributing

If you have House job announcement PDFs or emails that aren't in this collection, please send them to dwillis+housejobs@gmail.com.

## License

MIT License

Copyright (c) 2025 Derek Willis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
