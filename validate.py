import json
import os
import csv
from pathlib import Path
from datetime import datetime

def validate_json_files(directory_path):
    """
    Validates all JSON files in the specified directory and creates a CSV report of invalid files.
    
    Args:
        directory_path (str): Path to the directory containing JSON files
    
    Returns:
        tuple: (total_files, invalid_files_count, output_csv_path)
    """
    # Convert to Path object for better path handling
    dir_path = Path(directory_path)
    
    if not dir_path.is_dir():
        raise ValueError(f"'{directory_path}' is not a valid directory")

    # Initialize counters and results list
    total_files = 0
    invalid_files = []
    
    # Create timestamp for the output file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_csv = dir_path / f"invalid_json_report_{timestamp}.csv"
    
    # Scan all files in directory
    for file_path in dir_path.glob("*.json"):
        total_files += 1
        
        try:
            # Attempt to read and parse the JSON file
            with open(file_path, 'r', encoding='utf-8') as f:
                json.load(f)
                
        except json.JSONDecodeError as e:
            # Collect details about invalid files
            invalid_files.append({
                'file_name': file_path.name,
                'error_message': str(e),
                'error_line': e.lineno,
                'error_column': e.colno
            })
        except Exception as e:
            # Handle other potential errors (e.g., permission issues)
            invalid_files.append({
                'file_name': file_path.name,
                'error_message': f"Error reading file: {str(e)}",
                'error_line': 'N/A',
                'error_column': 'N/A'
            })

    # Write results to CSV if any invalid files were found
    if invalid_files:
        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['file_name', 'error_message', 'error_line', 'error_column']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for file_info in invalid_files:
                writer.writerow(file_info)
            
            # Delete the invalid file
            try:
                Path(dir_path / file_info['file_name']).unlink()
            except Exception as e:
                print(f"Warning: Could not delete {file_info['file_name']}: {str(e)}")
    
    return total_files, len(invalid_files), output_csv if invalid_files else None

def main():
    """
    Main function to run the JSON validation script.
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Validate JSON files in a directory, report and delete invalid ones'
    )
    parser.add_argument(
        'directory',
        help='Directory containing JSON files to validate'
    )
    
    args = parser.parse_args()
    
    try:
        total, invalid_count, output_path = validate_json_files(args.directory)
        
        print(f"\nValidation Complete:")
        print(f"Total JSON files processed: {total}")
        print(f"Invalid JSON files found: {invalid_count}")
        
        if output_path:
            print(f"Report generated: {output_path}")
            print(f"Invalid files have been deleted.")
        else:
            print("All files are valid JSON!")
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1
        
    return 0

if __name__ == "__main__":
    exit(main())