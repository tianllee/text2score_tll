import os
import re
import math
import shutil
import random
import subprocess
from tqdm import tqdm
from multiprocessing import Pool
import argparse

# ====== ORIGINAL FUNCTIONS (UNMODIFIED) ======

def convert_abci_to_abc_logic(data):
    """
    Extracted the core logic from your first script to use 
    inside the main processing loop.
    """
    # Step 1: Remove %number patterns
    data = re.sub(r'%\d+', '', data)
    # Step 2: Ensure each [V:x] starts on a new line
    data = re.sub(r'(?<!\n)(\[V:\d+\])', r'\n\1', data)
    # Step 3: Collapse multiple blank lines
    data = re.sub(r'\n{2,}', '\n', data)
    # Step 4: Strip whitespace
    lines = [line.strip() for line in data.splitlines()]
    return "\n".join(lines)

def convert_abc2xml_worker(file_list):
    """
    Combined worker that performs both cleaning and XML conversion.
    """
    cmd_base = 'python text2music/data/utils/abc_helper/abc2xml.py '
    
    for file_path in tqdm(file_list):
        try:
            # 1. Setup Paths
            # file_path is: .../[num]/interleaved/file.abc
            numbered_dir = os.path.dirname(os.path.dirname(file_path))
            abc_dir = os.path.join(numbered_dir, "abc")
            xml_dir = os.path.join(numbered_dir, "xml")
            
            os.makedirs(abc_dir, exist_ok=True)
            os.makedirs(xml_dir, exist_ok=True)
            
            filename = os.path.basename(file_path)
            base_name = ".".join(filename.split(".")[:-1])
            
            clean_abc_path = os.path.join(abc_dir, filename)
            xml_output_path = os.path.join(xml_dir, base_name + ".xml")

            # 2. STEP ONE: ABCI to ABC (Cleaning)
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = f.read()
            
            cleaned_data = convert_abci_to_abc_logic(raw_data)
            
            with open(clean_abc_path, 'w', encoding='utf-8') as f:
                f.write(cleaned_data)

            # 3. STEP TWO: ABC to XML
            p = subprocess.Popen(cmd_base + '"' + clean_abc_path + '"', 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE, 
                                 shell=True)
            stdout, stderr = p.communicate()
            output = stdout.decode('utf-8')

            if output == '':
                with open("logs/combined_error_log.txt", "a", encoding="utf-8") as f:
                    f.write(f"XML EMPTY: {clean_abc_path} - {stderr.decode('utf-8')}\n")
            else:
                with open(xml_output_path, 'w', encoding='utf-8') as f:
                    f.write(output)

        except Exception as e:
            os.makedirs("logs", exist_ok=True)
            with open("logs/combined_error_log.txt", "a", encoding="utf-8") as f:
                f.write(f"CRITICAL ERROR: {file_path} {str(e)}\n")

# ====== UPDATED MAIN ======

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root_folder', type=str, 
                        default="./text2music/artifacts/output/", 
                        help="Parent folder containing numbered subdirectories (1, 2, 3...)")
    args = parser.parse_args()

    ROOT_FOLDER = args.root_folder
    file_list = []
    os.makedirs("logs", exist_ok=True)

    if not os.path.exists(ROOT_FOLDER):
        print(f"❌ Error: {ROOT_FOLDER} does not exist.")
        exit(1)

    print(f"🔍 Searching for 'interleaved' folders in {ROOT_FOLDER}...")

    # Traverse the directory structure
    for item in os.listdir(ROOT_FOLDER):
        subdir_path = os.path.join(ROOT_FOLDER, item)
        
        if os.path.isdir(subdir_path):
            interleaved_path = os.path.join(subdir_path, "interleaved")
            
            if os.path.exists(interleaved_path):
                # Clean up existing output folders to prevent stale data
                for folder in ["abc", "xml"]:
                    target = os.path.join(subdir_path, folder)
                    if os.path.exists(target):
                        shutil.rmtree(target)
                
                # Collect .abc files from interleaved folder
                for file in os.listdir(interleaved_path):
                    if file.endswith(".abc"):
                        file_list.append(os.path.join(interleaved_path, file).replace("\\", "/"))

    if not file_list:
        print("⚠️ No .abc files found in the interleaved subdirectories.")
        exit(0)

    # Multiprocessing Setup
    random.shuffle(file_list)
    cpu_count = os.cpu_count() or 4
    # Split file list into chunks for each CPU
    chunks = [file_list[i::cpu_count] for i in range(cpu_count)]

    print(f"🚀 Processing {len(file_list)} files across {cpu_count} workers...")
    
    pool = Pool(processes=cpu_count)
    pool.map(convert_abc2xml_worker, chunks)
    pool.close()
    pool.join()

    print(f"✅ Finished! Cleaned .abc and .xml files are now in their respective numbered subdirectories.")