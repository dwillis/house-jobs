import os
import json
import subprocess
import time

directory_path = "output"
output_dir = "json_gemini_flash" # change this depending on the llm

output_files = [f.split('.json')[0] for f in os.listdir(output_dir)]

example = [{
    "date": "extract date from filename in yyyy-mm-dd format",
    "id": "MEM-458-24",
    "office": "Congressman Steven Horsford",
    "position": "District Representative",
    "location": "North Las Vegas, Nevada",
    "key_responsibilities": ["strengthening relationships with key stakeholders, as well as attending engagements on behalf of the Member", "helping constituents resolve problems with federal agencies through written and verbal communication"],
    "requirements": ["Political knowledge and comfortable navigating complicated situations", "Strong written, verbal, analytical, and organization skills; impeccable customer service manners; public speaking skills"],
    "job_type": "Full-time",
    "salary": "Commensurate with experience",
    "email": "NV04Resume@mail.house.gov"
},]

example_text = json.dumps(example)

for filename in os.listdir(directory_path):
    if 'Members' in filename and filename.endswith(".txt") and filename.split(".txt")[0] not in output_files:
        time.sleep(7)
        print(filename)
        text_string = open(f"output/{filename}", "r").read()
        try:
            file_id = filename.replace('.txt','').split('-')[1]
        except:
            file_id = filename.replace('.txt','').split('-')[0]
        command = f"cat output/{filename} | llm --system 'You are an expert in parsing congressional job listings from text in structured UTF-8 data. Produce a response that is only a JSON object extracting all job listings from each text file. For each non-ASCII character, including smartquotes, replace it with the closest UTF-8 equivalent. If a direct equivalent is not available, use a sensible approximation or remove diacritical marks.' -m gemini-1.5-flash-latest -o json_object 1 'Create a JSON object from the input based on the following example: {example_text} . If a value is not present, use None, and all other values must be enclosed in quotemarks. Place all JSON objects - using the identical structure - in a single array. -o json_object 1' > {output_dir}/{filename.replace('.txt','.json')}"

        try:
            # Execute the command
            subprocess.run(command, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error executing command for {filename}: {e}")
