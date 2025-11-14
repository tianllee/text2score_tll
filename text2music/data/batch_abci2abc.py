import os
import re
import math
import random
from tqdm import tqdm
from multiprocessing import Pool

# ====== CONFIG ======
ORI_FOLDER = "/data/home/acw769/text2score/text2music/artifacts/output/interleaved/weights_notagen_pretrain_p_size_16_p_length_2048_p_layers_16_c_layers_3_h_size_768_lr_0.0001_batch_8_k_9_p_0.9_temp_1.2"  # Folder containing .abci files
DES_FOLDER = "/data/home/acw769/text2score/text2music/artifacts/output/abc/weights_notagen_pretrain_p_size_16_p_length_2048_p_layers_16_c_layers_3_h_size_768_lr_0.0001_batch_8_k_9_p_0.9_temp_1.2"   # Output folder for converted .abc files

# ====== FUNCTION ======
def convert_abci_to_abc(file_list):
    for file in tqdm(file_list):
        filename = os.path.basename(file)
        output_path = os.path.join(DES_FOLDER, ".".join(filename.split(".")[:-1]) + ".abc")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = f.read()

            # Step 1: Remove %number patterns (like %5, %123)
            data = re.sub(r'%\d+', '', data)

            # Step 2: Ensure each [V:x] starts on a new line
            data = re.sub(r'(?<!\n)(\[V:\d+\])', r'\n\1', data)

            # Step 3: Collapse multiple blank lines
            data = re.sub(r'\n{2,}', '\n', data)

            # Step 4: Strip whitespace
            lines = [line.strip() for line in data.splitlines()]
            data = "\n".join(lines)

            # Step 5: Write the cleaned .abc file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(data)

        except Exception as e:
            os.makedirs("logs", exist_ok=True)
            with open("logs/abci2abc_error_log.txt", "a", encoding="utf-8") as logf:
                logf.write(file + " " + str(e) + "\n")
            continue


# ====== MAIN ======
if __name__ == '__main__':
    os.makedirs(DES_FOLDER, exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    # Collect all .abci files
    file_list = []
    for root, dirs, files in os.walk(ORI_FOLDER):
        for file in files:
            if not file.endswith(".abc"):
                continue
            filename = os.path.join(root, file).replace("\\", "/")
            file_list.append(filename)

    if not file_list:
        print("⚠️ No .abc files found in", ORI_FOLDER)
        exit(0)

    # Split files for multiprocessing
    file_lists = []
    random.shuffle(file_list)
    cpu_count = os.cpu_count() or 4
    for i in range(cpu_count):
        start_idx = int(math.floor(i * len(file_list) / cpu_count))
        end_idx = int(math.floor((i + 1) * len(file_list) / cpu_count))
        file_lists.append(file_list[start_idx:end_idx])

    # Run conversions in parallel
    print(f"🚀 Starting conversion of {len(file_list)} files using {cpu_count} workers...")
    pool = Pool(processes=cpu_count)
    pool.map(convert_abci_to_abc, file_lists)
    pool.close()
    pool.join()

    print("✅ Conversion complete! Saved .abc files to:", DES_FOLDER)
