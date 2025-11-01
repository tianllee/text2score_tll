import os
import json
import pandas as pd
from tqdm import tqdm

# --- 1. Define Paths ---
# This path assumes 'PDMX.csv' is in the same directory as the script
csv_path = "/data/scratch/eey549/ABC_Dataset/ABC_Dataset/PDMX_MXL_abci/PDMX.csv" 
# data_path = "/data/home/acw769/text2score/text2music/data/validation.jsonl"
# output_path = "/data/home/acw769/text2score/text2music/data/validation_with_genres.jsonl"
data_path = "/data/home/acw769/text2score/text2music/data/train.jsonl"
output_path = "/data/home/acw769/text2score/text2music/data/train_with_genres.jsonl"

# --- 2. Build Genre Lookup Map from PDMX.csv ---
print(f"Building genre lookup map from {csv_path}...")
genre_map = {}

try:
    # Read the CSV file using pandas
    # Added low_memory=False to handle potentially large and mixed-type columns
    df = pd.read_csv(csv_path, low_memory=False)
    
    # Check if required columns exist
    if 'path' not in df.columns or 'genres' not in df.columns:
        print(f"Error: {csv_path} is missing required 'path' or 'genres' columns.")
        raise ValueError(f"Missing required columns 'path' or 'genres' in {csv_path}")

    # Create a basename column for mapping
    # e.g., ./data/1/11/Qmbb...json -> Qmbb...
    # Added str() to handle any potential non-string paths
    df['basename'] = df['path'].apply(lambda x: os.path.splitext(os.path.basename(str(x)))[0])
    
    # Handle 'NA' values or other placeholders, convert them to None
    df['genres'] = df['genres'].replace('NA', pd.NA).where(pd.notna, None)
    
    # Create the lookup dictionary
    # { 'Qmbb...': 'classical', 'Qmcc...': None, ... }
    genre_map = df.set_index('basename')['genres'].to_dict()
    
    print(f"Successfully created a lookup map with {len(genre_map)} genre entries from CSV.")

except FileNotFoundError:
    print(f"Error: Metadata file not found at {csv_path}")
except Exception as e:
    print(f"An error occurred while processing {csv_path}: {e}")
    
if not genre_map:
    print("Genre map is empty. Cannot proceed with validation file processing.")
else:
    # --- 3. Process validation.jsonl and Add Genres ---
    print(f"\nProcessing {data_path} to add genres...")
    updated_data_entries_sample = [] # To store the first 10 for printing
    entry_count = 0
    lines_processed = 0

    try:
        # Open input and output files at the same time
        with open(data_path, 'r') as f_in, open(output_path, 'w') as f_out:
            
            lines = f_in.readlines()
            lines_processed = len(lines)
            
            for i, line in enumerate(tqdm(lines, desc="Processing validation file")):
                line = line.strip()
                if not line:
                    continue
                
                entry_count += 1
                try:
                    # Load the JSON data from the line
                    data_entry = json.loads(line)
                    file_path = data_entry.get('path')
                    
                    # Initialize genre_info to None
                    genre_info = None 
                    
                    if file_path:
                        # --- START: Modified Logic ---
                        # 1. Check for special dataset paths
                        if 'SymphonyNet_Dataset_MXL_abci' in file_path:
                            genre_info = 'symphony'
                        elif 'ASAP_MXL_abci' in file_path:
                            genre_info = 'classical piano'
                        else:
                            # 2. Fallback to CSV Lookup Logic
                            # e.g., PDMX_MXL_abci/.../Qmb1...abci -> Qmb1...
                            basename = os.path.splitext(os.path.basename(file_path))[0]
                            
                            # Look up the basename in our map
                            raw_genre = genre_map.get(basename)
                            
                            # Ensure that pandas NA/NaN values become None
                            genre_info = None if pd.isna(raw_genre) else raw_genre
                        # --- END: Modified Logic ---

                    # Add the new 'genre' key (will be None if not found)
                    data_entry['genre'] = genre_info
                    
                    # Write the updated JSON object to the new file
                    f_out.write(json.dumps(data_entry) + '\n')
                    
                    # Save the first 10 entries for printing
                    if i < 10:
                        updated_data_entries_sample.append(data_entry)

                except json.JSONDecodeError:
                    print(f"Warning: Skipping malformed line in {data_path} at line {i+1}: {line}")
                    
        print(f"\nSuccessfully processed {entry_count} entries (out of {lines_processed} lines) and wrote updated data to {output_path}.")

    except FileNotFoundError:
        print(f"Error: Input file not found at {data_path}")
    except IOError:
        print(f"Error: Could not write to output file at {output_path}")
    except Exception as e:
        print(f"An error occurred during validation file processing: {e}")

    # --- 4. Print First 10 Updated Entries ---
    if updated_data_entries_sample:
        print("\n--- Sample of Updated Data (First 10 Entries) ---")
        for entry in updated_data_entries_sample:
            print(json.dumps(entry))
    else:
        print("\nNo data was processed or saved for the sample printout.")