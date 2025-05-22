from typing import Optional
import os
import subprocess
from os import path
from utils.abc_helper.abc2abc_interleaved import abc2abc_interleaved
from utils.mtf_helper.midi2mtf import midi2mtf
from utils.mtf_helper.mtf2midi import mtf2midi
from utils.abc_helper.fix_abc import fix_missing_voice_field, remove_empty_lines


def convert_abc2abc_interleaved(input_file: str,
                                output_file: Optional[str] = None,
                                fix_abc: bool = True) -> Optional[list[str]]:
    """
    Convert ABC file to interleaved format for M3 model.

    Args:
        input_file (str): Path to the ABC file.
        output_file (Optional[str]): Path to save the interleaved file (.abci). If None, no file is saved.
        fix_abc (bool): Whether to fix the ABC file. Default is True.
    Returns:
        Optional[list[str]]: Interleaved ABC lines if successful, None if an error occurs.
    """
    assert path.exists(input_file)
    abc_lines = open(path.abspath(input_file), 'r', encoding='utf-8').readlines()

    if fix_abc:
        abc_lines = fix_missing_voice_field(abc_lines)
        abc_lines = remove_empty_lines(abc_lines)

    interleaved_abc_lines, error = abc2abc_interleaved(abc_lines)

    if not error:
        if output_file:
            os.makedirs(path.dirname(output_file), exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as w:
                w.writelines(interleaved_abc_lines)
        return interleaved_abc_lines

    os.makedirs("logs", exist_ok=True)
    with open("logs/abc2abc_error_log.txt", "a", encoding="utf-8") as f:
        f.write(f"{input_file} {error}\n")
    return None


def convert_xml2abc_interleaved(input_file: str, output_file: Optional[str] = None) -> None:
    """
    Convert XML files to ABC format (interleaved) for the M3 model.
    
    Args:
        input_file (str): Path to the XML file.
        output_file (str): Path to save the interleaved ABC file, typically with a .abci extension.
            If None, no file is saved.
    
    Returns:
        list: List of strings containing the interleaved ABC notation. None if unsuccessful.
    """
    assert path.exists(input_file)
    input_file = path.abspath(input_file)
    if output_file is not None:
        os.makedirs(path.dirname(output_file), exist_ok=True)

    # xml --> abc
    try:
        cmd = f'python utils/abc_helper/xml2abc.py -d 8 -x "{input_file}"'
        # p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=True)
        # result = p.communicate()
        # abc_output = result[0].decode('ucmdtf-8')
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
        abc_lines = result.splitlines()
    except Exception as e:
        print(f'Error converting {input_file}: {e}')
        os.makedirs("logs", exist_ok=True)
        with open("logs/xml2abc_error_log.txt", "a", encoding="utf-8") as f:
            f.write(input_file + ' ' + str(e) + '\n')
        return None
    if len(abc_lines) == 0:
        print(f'Error converting {input_file}: No ABC output')
        os.makedirs("logs", exist_ok=True)
        with open("logs/xml2abc_error_log.txt", "a", encoding="utf-8") as f:
            f.write(input_file + ' No ABC output\n')
        return None

    # abc --> interleaved abc
    interleaved_abc_lines, error = abc2abc_interleaved(abc_lines)
    if error is not None:
        os.makedirs("logs", exist_ok=True)
        with open("logs/xml2abc_error_log.txt", "a", encoding="utf-8") as f:
            f.write(input_file + ' ' + error + '\n')

    if interleaved_abc_lines is not None:
        if output_file is not None:
            with open(output_file, 'w', encoding='utf-8') as w:
                w.writelines(interleaved_abc_lines)
        return interleaved_abc_lines
    else:
        return None


def convert_abc2xml(input_file: str, output_file: Optional[str] = None) -> None:
    """
    Convert ABC file to XML format for the M3 model.
    """
    assert path.exists(input_file)
    input_file = path.abspath(input_file)
    if output_file is not None:
        os.makedirs(path.dirname(output_file), exist_ok=True)
    try:
        cmd = f'python utils/abc_helper/abc2xml.py -o "{output_file}" "{input_file}"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
        xml_lines = result.splitlines()
    except Exception as e:
        print(f'Error converting {input_file}: {e}')
        os.makedirs("logs", exist_ok=True)
        with open("logs/abc2xml_error_log.txt", "a", encoding="utf-8") as f:
            f.write(input_file + ' ' + str(e) + '\n')
    return xml_lines


def convert_midi2mtf(input_file: str, output_file: Optional[str] = None):
    """
    Convert MIDI file to MTF format for the M3 model.

    Args:
        input_file (str): Path to the MIDI file.
        output_file (Optional[str]): Path to save the MTF file (.mtf). If None, no file is saved.

    Returns:
        output: Output lines if successful, None if an error occurs.
        error: Error message if any. None if successful.
    """
    output, error = midi2mtf(input_file, output_file)
    if error is not None:
        print(error)
    return output


def convert_mtf2midi(input_file: str, output_file):
    return mtf2midi(input_file, output_file)
