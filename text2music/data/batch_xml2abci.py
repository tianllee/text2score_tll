import argparse
from os import path
from glob import glob
from multiprocessing import Pool
from functools import partial
from tqdm import tqdm
from utils.convert_formats import convert_xml2abc_interleaved

def process_file(xml_file, data_root=None, output_dir=None):
    """Process a single XML file to ABC interleaved format."""
    try:
        abci_file = xml_file.replace(".musicxml", ".abci")
        if output_dir and data_root:
            # Get relative path from data_root to preserve subdirectory structure
            rel_path = path.relpath(path.dirname(xml_file), data_root)
            # Construct output path maintaining the subdirectory structure
            abci_file = path.join(output_dir, rel_path, path.basename(abci_file))
        
        abci_lines = convert_xml2abc_interleaved(xml_file, abci_file)
        if abci_lines is None:
            return False, xml_file
        return True, xml_file
    except Exception as e:
        return False, xml_file

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Convert MusicXML files to ABC interleaved format")
    parser.add_argument('--data_root', type=str, default="../../abrsm_data/musicXML",
                        help='Root directory containing MusicXML files')
    parser.add_argument('--output_dir', type=str, default=None,
                        help='Output directory for ABCI files (optional)')
    parser.add_argument('--num_workers', type=int, default=4,
                        help='Number of worker processes for parallel processing')
    
    args = parser.parse_args()

    # Get list of XML files
    xml_filelist = glob(path.join(args.data_root, "**/*.musicxml"), recursive=True)
    
    if not xml_filelist:
        print(f"No MusicXML files found in {args.data_root}")
        return

    # Initialize counters
    success, fail = 0, 0

    # Process files using multiprocessing
    with Pool(processes=args.num_workers) as pool:
        # Create partial function with data_root and output_dir
        process_func = partial(process_file, data_root=args.data_root, output_dir=args.output_dir)
        
        # Process files with tqdm progress bar
        results = list(tqdm(pool.imap(process_func, xml_filelist), 
                           total=len(xml_filelist), 
                           desc="Converting MusicXML to ABCI"))

    # Count successes and failures
    for result, xml_file in results:
        if result:
            success += 1
        else:
            fail += 1
            print(f"Failed to convert {xml_file}")

    print(f"\nxml to abc_interleaved: success={success}, failure={fail}")

if __name__ == "__main__":
    main()