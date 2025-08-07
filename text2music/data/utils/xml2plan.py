import partitura as pt
import xml.etree.ElementTree as ET
from typing import Dict, Optional
import random
# Ignore user warnings
import warnings
warnings.filterwarnings("ignore", category=UserWarning)


def find_tempo_in_measure(measure_element: ET.Element) -> Optional[int]:
    """Checks for tempo markings within a single measure element."""
    # Tempo is often specified in a <direction> element.
    for direction in measure_element.findall('direction'):
        # It can be in a <sound> element's 'tempo' attribute.
        sound_element = direction.find('sound')
        if sound_element is not None and 'tempo' in sound_element.attrib:
            try:
                return int(float(sound_element.attrib['tempo']))
            except (ValueError, TypeError):
                continue # Ignore if tempo is not a valid number

        # Or it can be in a <metronome> element.
        direction_type = direction.find('direction-type')
        if direction_type is not None:
            metronome = direction_type.find('metronome')
            if metronome is not None:
                per_minute = metronome.find('per-minute')
                if per_minute is not None and per_minute.text:
                    try:
                        return int(per_minute.text)
                    except (ValueError, TypeError):
                        continue # Ignore if not a valid number
    return None

def extract(filepath: str) -> Dict[int, Optional[int]]:
    """
    Parses a MusicXML file and extracts tempo for each measure.

    Args:
        filepath: The path to the MusicXML file.

    Returns:
        A dictionary where keys are measure numbers (int) and values are
        the tempo in BPM (int), or None if no tempo has been set.
    """
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"Error parsing XML file: {e}")
        return {}

    tempo_by_measure: Dict[int, Optional[int]] = {}
    current_tempo: Optional[int] = None

    # Tempo information is usually in the first part, so we only need to parse that.
    first_part = root.find('part')
    if first_part is None:
        print("No <part> elements found in the MusicXML file.")
        return {}

    measures = first_part.findall('measure')
    for measure_element in measures:
        measure_number_str = measure_element.get('number')
        if not measure_number_str:
            continue
        
        measure_number = int(measure_number_str)

        # Search for tempo markings within the measure
        # A new tempo found here will override the current_tempo
        found_tempo = find_tempo_in_measure(measure_element)
        if found_tempo is not None:
            current_tempo = found_tempo
        
        tempo_by_measure[measure_number] = current_tempo
        
    return tempo_by_measure


def get_raw_xml_info(musicxml_file: str, verbose: bool = False) -> list:
    """
    Extracts raw XML information from a MusicXML file.

    Args:
        musicxml_file: The path to the MusicXML file.

    Returns:
        A list containing the raw XML information.
    """
    
    # Load the score
    score = pt.load_musicxml(musicxml_file)
    all_tempos = extract(musicxml_file)

    data = []
    # Iterate through all parts in the score
    for i, part in enumerate(score.parts):

        part_name = part.part_name
        if not part_name:
            # Assign piano as default part name if not specified
            part_name = f"Piano {i+1}" if i > 0 else "Piano"

        for p in data:
            n = 1
            if p['part_name'] == part_name:
                # If part name already exists, increment the part number
                part_name += f" {n+1}"
                # Check if new part name already exists
                while any(p['part_name'] == part_name for p in data):
                    n += 1
                    part_name = f"{part.part_name} {n+1}"
        if verbose:
            print(f"Part Name: {part_name}")

        # Define the extended note array with additional fields
        extended_score_note_array = pt.utils.music.ensure_notearray(
            part,
            include_pitch_spelling=True, # adds 3 fields: step, alter, octave
            include_key_signature=True, # adds 2 fields: ks_fifths, ks_mode
            include_time_signature=True, # adds 2 fields: ts_beats, ts_beat_type
            include_metrical_position=True, # adds 3 fields: is_downbeat, rel_onset_div, tot_measure_div
            include_grace_notes=True # adds 2 fields: is_grace, grace_type
        )

        # Get all measures in the part
        measures = list(part.iter_all(pt.score.Measure, include_subclasses=True))
        if verbose:
            print(f"Number of measures in part: {len(measures)}")

        part_data = {
                "part_name": part_name,
                "measures": []
            }

        for measure in measures:
            ts_num = int(part.time_signature_map(measure.start.t)[0])
            ts_den = int(part.time_signature_map(measure.start.t)[1])
            ts_beats = int(part.time_signature_map(measure.start.t)[2])
            ks_fifths = int(part.key_signature_map(measure.start.t)[0])
            ks_mode = int(part.key_signature_map(measure.start.t)[1])
            measure_data = {
                    "measure": measure.number,
                    "start_time": measure.start.t,
                    "end_time": measure.end.t,
                    "ts_num": ts_num,
                    "ts_den": ts_den,
                    "ts_beats": ts_beats,
                    "ks_fifths": ks_fifths,
                    "ks_mode": ks_mode,
                    "tempo": all_tempos.get(measure.number, None)  # Get tempo for this measure
                }
            # Get all notes in that measure
            notes_in_measure = [n for n in extended_score_note_array if measure.start.t <= n[4] < measure.end.t]
            notes = []
            for n, note in enumerate(notes_in_measure):
                note_data = {
                    "pitch": note['pitch'],
                    "start_time": note['onset_div'],
                    "end_time": note['onset_div'] + note['duration_div'],
                    "rel_onset_div": note['rel_onset_div'],
                    "tot_measure_div": note['tot_measure_div'],
                    "duration": note['duration_div'],
                    "is_grace": note['is_grace'],
                    "grace_type": note['grace_type']
                }
                notes.append(note_data)
            measure_data["notes"] = notes
            
            part_data["measures"].append(measure_data)
        data.append(part_data)

    return data

def combine_raw_xml_info(data):
    """
    Combines the raw XML information from multiple parts into a single dictionary.

    Args:
        data: A list of dictionaries containing raw XML information for each part.

    Returns:
        A combined dictionary with all parts' data.
    """
    # Combine all measures for all parts into a single measure structure
    # where each measure contains information from all parts.

    combined_measures = {}
    for part_data in data:
        part_name = part_data['part_name']
        for measure_data in part_data['measures']:
            measure_num = measure_data['measure']
            if f"Measure: {measure_num}" not in combined_measures:
                combined_measures[f"Measure: {measure_num}"] = {}
            
            combined_measures[f"Measure: {measure_num}"][part_name] = {
                'info': {
                    'start_time': measure_data['start_time'],
                    'end_time': measure_data['end_time'],
                    'ts_num': measure_data['ts_num'],
                    'ts_den': measure_data['ts_den'],
                    'ts_beats': measure_data['ts_beats'],
                    'ks_fifths': measure_data['ks_fifths'],
                    'ks_mode': measure_data['ks_mode'],
                    'tempo': measure_data['tempo'],
                    'notes': measure_data['notes']
                }
            }

    return combined_measures


def get_full_plan(combined_data):
    """
    Generates a full plan from the combined data.

    Args:
        combined_data: A dictionary containing combined measure data.

    Returns:
        A dictionary representing the full plan.
    """

    plan = {}
    all_instruments = set()
    for measure in combined_data.keys():
        measure_info = combined_data[measure]
        # Add the measure number to the plan
        plan[measure] = {}

        # Add instruments in this measure to all_instruments
        for instrument in measure_info.keys():
            all_instruments.add(instrument)

        # Add instruments which have notes in this measure
        plan[measure]['instruments'] = [instrument for instrument in combined_data[measure].keys() if len(combined_data[measure][instrument]['info']['notes']) > 0]
        
        # Add pitch range
        pitch_ranges = []
        for instrument in plan[measure]['instruments']:
            notes = combined_data[measure][instrument]['info']['notes']
            if notes:
                pitches = [note['pitch'] for note in notes]
                max_pitch = max(pitches)
                min_pitch = min(pitches)
                pitch_ranges.append((min_pitch, max_pitch))
        if pitch_ranges:
            plan[measure]['pitch_range'] = {
                'min': min(p[0] for p in pitch_ranges),
                'max': max(p[1] for p in pitch_ranges)
            }
        else:
            plan[measure]['pitch_range'] = {'min': None, 'max': None}
        
        # Add note density
        total_notes = sum(len(combined_data[measure][instrument]['info']['notes']) for instrument in plan[measure]['instruments'])
        if plan[measure]['instruments']:
            average_notes = total_notes / len(plan[measure]['instruments'])
        else:
            average_notes = 0
        plan[measure]['note_density'] = average_notes
        
        # Add time signature
        # Assuming all instruments in the measure share the same time signature
        if plan[measure]['instruments']:
            first_instrument = plan[measure]['instruments'][0]
            ts_num = combined_data[measure][first_instrument]['info']['ts_num']
            ts_den = combined_data[measure][first_instrument]['info']['ts_den']
            plan[measure]['time_signature'] = f"{ts_num}/{ts_den}" 
        else:
            plan[measure]['time_signature'] = None
        
        # Add key signature
        instruments_to_exclude = ['Drum', 'Percussion', 'Drumset', 'Drums', 'Saxophone', 'Clarinet']
        # Key signature is majority voted across instruments or if piano is present, use its key signature
        plan[measure]['key_signature'] = None
        if 'Piano' in plan[measure]['instruments']:
            # If Piano is present, use its key signature
            plan[measure]['key_signature'] = combined_data[measure]['Piano']['info']['ks_fifths']
        # Else, if there are multiple instruments, use the most common key signature
        elif plan[measure]['instruments']:
            # Collect key signatures from all instruments, excluding those in instruments_to_exclude
            # If any of the instruments_to_exclude items is not contained in the instrument name
            key_signatures = [combined_data[measure][instrument]['info']['ks_fifths'] 
                              for instrument in plan[measure]['instruments'] 
                              if not any(excluded in instrument for excluded in instruments_to_exclude)]
            if key_signatures:
                # Use the most common key signature
                plan[measure]['key_signature'] = max(set(key_signatures), key=key_signatures.count)
            else:
                plan[measure]['key_signature'] = None

        # Add key mode
        # Key mode can be first instrument's mode or None if no instruments
        first_instrument = plan[measure]['instruments'][0] if plan[measure]['instruments'] else None
        if first_instrument and 'info' in combined_data[measure][first_instrument]:
            plan[measure]['key_mode'] = combined_data[measure][first_instrument]['info']['ks_mode']
        else:
            plan[measure]['key_mode'] = None

        # Add tempo
        # Tempo is taken from the first instrument's info, if available
        if first_instrument and 'info' in combined_data[measure][first_instrument]:
            plan[measure]['tempo'] = combined_data[measure][first_instrument]['info']['tempo']
        else:
            plan[measure]['tempo'] = None

        # Add chord notes
        # A chord is defined as a set of notes that occur within a beat
        plan[measure]['chords'] = []
        if not plan[measure]['instruments']:
            continue  # Skip measures with no instruments
        ts_beats = combined_data[measure][first_instrument]['info']['ts_beats']
        ticks_in_measure = combined_data[measure][first_instrument]['info']['end_time'] - combined_data[measure][first_instrument]['info']['start_time']
        beats_in_measure = ticks_in_measure / ts_beats
        for beat in range(ts_beats):
            chord_notes = []
            for instrument in plan[measure]['instruments']:
                notes = combined_data[measure][instrument]['info']['notes']
                for note in notes:
                    if note['rel_onset_div'] // beats_in_measure == beat and note['is_grace'] == 0:
                        note_pitch = note['pitch'] % 12  # Get the pitch class (0-11)
                        chord_notes.append(note_pitch)
            if chord_notes:
                # Remove duplicates and sort
                chord_notes = set(chord_notes)
                plan[measure]['chords'].append(chord_notes)

    # Add all instruments to the plan
    plan['all_instruments'] = list(all_instruments)

    return plan



def get_top_measures_instrument(full_plan, top_pct=10):
    """
    Get the top N measures based on note density.

    Args:
        full_plan: The full plan dictionary containing measure information.
        top_pct: The pct of top measures to return.

    Returns:
        A dict of measures
    """
    
    # Get change in instrument count compared to the previous measure across all measures
    instrument_count_changes = {}
    previous_instrument_count = 0
    for measure, info in full_plan.items():
        current_instrument_count = len(info['instruments'])
        if previous_instrument_count == 0:
            change = current_instrument_count  # First measure, no previous count
        else:
            change = current_instrument_count - previous_instrument_count
        instrument_count_changes[measure] = change
        previous_instrument_count = current_instrument_count

    # Sort the absolute values of instrument count changes by measure
    sorted_instrument_count_changes = sorted(instrument_count_changes.items(), key=lambda x: abs(x[1]), reverse=True)

    # Take the top 10% of measures with the largest absolute changes
    top_10_percent_count = max(5, len(sorted_instrument_count_changes) // top_pct)  # Ensure at least one measure is selected
    top_instrument_changes = sorted_instrument_count_changes[:top_10_percent_count]
    
    return {measure: change for measure, change in top_instrument_changes}


def get_top_measures_tempo(full_plan, top_pct=10):
    """
    Get the top N measures based on tempo changes.

    Args:
        full_plan: The full plan dictionary containing measure information.
        top_pct: The pct of top measures to return.

    Returns:
        A dict of measures
    """
    
    # Get change in tempo compared to the previous measure across all measures
    tempo_changes = {}
    previous_tempo = None
    for measure, info in full_plan.items():
        current_tempo = info.get('tempo', 0)
        if current_tempo is None:
            current_tempo = 0
        if previous_tempo is None:
            change = current_tempo  # First measure, no previous tempo
        else:
            change = (current_tempo - previous_tempo) if current_tempo is not None and previous_tempo is not None else 0
        tempo_changes[measure] = change
        previous_tempo = current_tempo

    # Sort the absolute values of tempo changes by measure
    sorted_tempo_changes = sorted(tempo_changes.items(), key=lambda x: abs(x[1]), reverse=True)

    # Take the top 10% of measures with the largest absolute changes
    top_10_percent_tempo_count = max(5, len(sorted_tempo_changes) // top_pct)  # Ensure at least one measure is selected
    top_tempo_changes = sorted_tempo_changes[:top_10_percent_tempo_count]
    
    return {measure: change for measure, change in top_tempo_changes}


def get_top_measures_key_signature(full_plan, top_pct=10):
    """
    Get the top N measures based on key signature changes.

    Args:
        full_plan: The full plan dictionary containing measure information.
        top_pct: The pct of top measures to return.

    Returns:
        A dict of measures
    """
    
    # Get change in key signature per measure across all measures
    key_signature_changes = {}
    previous_key_signature = None
    for measure, info in full_plan.items():
        current_key_signature = info.get('key_signature')
        if previous_key_signature is None:
            change = 1 #current_key_signature  # First measure, no previous key signature
        else:
            # change = (current_key_signature - previous_key_signature) if current_key_signature is not None and previous_key_signature is not None else 0
            change = 1 if current_key_signature is not None and previous_key_signature is not None and current_key_signature != previous_key_signature else 0
        key_signature_changes[measure] = change
        previous_key_signature = current_key_signature

    # Sort the absolute values of key signature changes by measure
    sorted_key_signature_changes = sorted(key_signature_changes.items(), key=lambda x: abs(x[1]), reverse=True)

    # Take the top 10% of measures with the largest absolute changes
    top_10_percent_key_signature_count = max(5, len(sorted_key_signature_changes) // top_pct)  # Ensure at least one measure is selected
    top_key_signature_changes = sorted_key_signature_changes[:top_10_percent_key_signature_count]
    
    return {measure: change for measure, change in top_key_signature_changes}


def get_top_measures_time_signature(full_plan, top_pct=10):
    """
    Get the top N measures based on time signature changes.

    Args:
        full_plan: The full plan dictionary containing measure information.
        top_pct: The pct of top measures to return.

    Returns:
        A dict of measures
    """
    
    # Get change in time signature per measure across all measures
    time_signature_changes = {}
    previous_time_signature = None  # Initialize previous time signature
    for measure, info in full_plan.items():
        current_time_signature = info.get('time_signature')
        if previous_time_signature is None:
            change = 1  # First measure, no previous time signature
        else:
            change = 1 if current_time_signature is not None and previous_time_signature is not None and current_time_signature != previous_time_signature else 0
        time_signature_changes[measure] = change
        previous_time_signature = current_time_signature

    # Sort the absolute values of time signature changes by measure
    sorted_time_signature_changes = sorted(time_signature_changes.items(), key=lambda x: abs(x[1]), reverse=True)

    # Take the top 10% of measures with the largest absolute changes
    top_10_percent_time_signature_count = max(5, len(sorted_time_signature_changes) // top_pct)  # Ensure at least one measure is selected
    top_time_signature_changes = sorted_time_signature_changes[:top_10_percent_time_signature_count]
    
    return {measure: change for measure, change in top_time_signature_changes}


def get_top_measures_note_density(full_plan, top_pct=10):
    """
    Get the top N measures based on note density.

    Args:
        full_plan: The full plan dictionary containing measure information.
        top_pct: The pct of top measures to return.

    Returns:
        A dict of measures
    """
    
    # Get change in note density across all measures
    note_density_changes = {}
    previous_note_density = 0
    for measure, info in full_plan.items():
        current_note_density = info.get('note_density', 0)
        change = current_note_density - previous_note_density
        note_density_changes[measure] = change
        previous_note_density = current_note_density

    # Sort the absolute values of note density changes by measure
    sorted_note_density_changes = sorted(note_density_changes.items(), key=lambda x: abs(x[1]), reverse=True)

    # Take the top 10% of measures with the largest absolute changes
    top_10_percent_note_density_count = max(5, len(sorted_note_density_changes) // top_pct)  # Ensure at least one measure is selected
    top_note_density_changes = sorted_note_density_changes[:top_10_percent_note_density_count]
    
    return {measure: change for measure, change in top_note_density_changes}


def get_top_measures_pitch_range(full_plan, top_pct=10):
    """
    Get the top N measures based on pitch range.

    Args:
        full_plan: The full plan dictionary containing measure information.
        top_pct: The pct of top measures to return.

    Returns:
        A dict of measures
    """
    
    # Get changes in pitch range per measure across all measures
    # Pitch range is highest pitch - lowest pitch in the measure
    pitch_range_changes = {}
    for measure, info in full_plan.items():
        current_pitch_range = info.get('pitch_range', {'min': None, 'max': None})
        if current_pitch_range['min'] is None or current_pitch_range['max'] is None:
            change = 0  # No pitch range defined
        else:
            change = current_pitch_range['max'] - current_pitch_range['min']
        pitch_range_changes[measure] = change

    # Sort the absolute values of pitch range changes by measure
    sorted_pitch_range_changes = sorted(pitch_range_changes.items(), key=lambda x: abs(x[1]), reverse=True)

    # Take the top 10% of measures with the largest absolute changes
    top_10_percent_pitch_range_count = max(5, len(sorted_pitch_range_changes) // top_pct)  # Ensure at least one measure is selected
    top_pitch_range_changes = sorted_pitch_range_changes[:top_10_percent_pitch_range_count]
    
    return {measure: change for measure, change in top_pitch_range_changes}


def get_priority_order(full_plan, top_pct=10, top_n=5):
    """
    Get the priority order of measures based on various musical features.

    Args:
        full_plan: The full plan dictionary containing measure information.
        top_pct: The pct of top measures to consider from each attribute.
        top_n: The number of top measures to return.

    Returns:
        A list of measures ordered by priority.
    """

    # Remove all_instruments from full_plan to avoid confusion
    if 'all_instruments' in full_plan:
        all_instruments = full_plan['all_instruments']
        del full_plan['all_instruments']
    
    top_instrument_changes = get_top_measures_instrument(full_plan, top_pct=top_pct)
    top_tempo_changes = get_top_measures_tempo(full_plan, top_pct=top_pct)
    top_key_signature_changes = get_top_measures_key_signature(full_plan, top_pct=top_pct)
    top_time_signature_changes = get_top_measures_time_signature(full_plan, top_pct=top_pct)
    top_note_density_changes = get_top_measures_note_density(full_plan, top_pct=top_pct)
    top_pitch_range_changes = get_top_measures_pitch_range(full_plan, top_pct=top_pct)

    weighting_1 = {
        'instrument_changes': 2,
        'tempo_changes': 5,
        'key_signature_changes': 3,
        'time_signature_changes': 4,
        'note_density_changes': 3,
        'pitch_range_changes': 1
    }

    weighting_2 = {
        'instrument_changes': 1,
        'tempo_changes': 1,
        'key_signature_changes': 1,
        'time_signature_changes': 1,
        'note_density_changes': 5,
        'pitch_range_changes': 5
    }

    weighting_3 = {
        'instrument_changes': 5,
        'tempo_changes': 1,
        'key_signature_changes': 1,
        'time_signature_changes': 1,
        'note_density_changes': 1,
        'pitch_range_changes': 1
    }

    weighting_4 = {
        'instrument_changes': 1,
        'tempo_changes': 2,
        'key_signature_changes': 5,
        'time_signature_changes': 5,
        'note_density_changes': 1,
        'pitch_range_changes': 1
    }

    # Get random weighting
    weighting = random.choice([weighting_1, weighting_2, weighting_3, weighting_4])

    priority_order = {}
    for measure, change in top_tempo_changes.items():
        priority_order[measure] = priority_order.get(measure, 0) + weighting['tempo_changes']
    for measure, change in top_time_signature_changes.items():
        priority_order[measure] = priority_order.get(measure, 0) + weighting['time_signature_changes']
    for measure, change in top_key_signature_changes.items():
        priority_order[measure] = priority_order.get(measure, 0) + weighting['key_signature_changes']
    for measure, change in top_note_density_changes.items():
        priority_order[measure] = priority_order.get(measure, 0) + weighting['note_density_changes']
    for measure, change in top_instrument_changes.items():
        priority_order[measure] = priority_order.get(measure, 0) + weighting['instrument_changes']
    for measure, change in top_pitch_range_changes.items():
        priority_order[measure] = priority_order.get(measure, 0) + weighting['pitch_range_changes']

    # Sort measures by priority score in descending order
    sorted_priority_order = sorted(priority_order.items(), key=lambda x: x[1], reverse=True)

    top_priority_measures = sorted_priority_order[:top_n] # Get the top n measures based on priority score

    # Sort the top priority measures by their measure number for better readability
    top_priority_measures.sort(key=lambda x: int(x[0].split(': ')[1]))

    # Return only the measure numbers in the order of priority
    return (top_priority_measures, all_instruments)


def get_consecutive_measures(full_plan, top_priority_measures):
    """
    Get consecutive measures based on the top priority measures.

    Args:
        full_plan: The full plan dictionary containing measure information.
        top_priority_measures: A list of top priority measures.

    Returns:
        A list of measures with consecutive measures appended.
    """

    # Remove all_instruments from full_plan to avoid confusion
    if 'all_instruments' in full_plan:
        del full_plan['all_instruments']

    # Randomly append a consecutive measure (above or below each measure) to the top priority measures
    top_priority_measures_with_consecutive = []
    for measure, priority in top_priority_measures:
        measure_num = int(measure.split(': ')[1])
        # Check if the next measure exists
        next_measure = f"Measure: {measure_num + 1}"
        previous_measure = f"Measure: {measure_num - 1}"

        # Append current measure
        if measure not in top_priority_measures_with_consecutive:
            top_priority_measures_with_consecutive.append((measure))
        
        # 50% chance to append the next measure if it exists, otherwise append the previous measure
        if next_measure in full_plan and next_measure not in top_priority_measures_with_consecutive and random.random() < 0.5:
            top_priority_measures_with_consecutive.append((next_measure))
        elif previous_measure in full_plan and previous_measure not in top_priority_measures_with_consecutive and random.random() < 0.5:
            top_priority_measures_with_consecutive.append((previous_measure))

    # Sort the top priority measures with consecutive measures by their measure number for better readability
    top_priority_measures_with_consecutive.sort(key=lambda x: int(x.split(': ')[1]))

    consecutive_measures = {measure: full_plan[measure] for measure in top_priority_measures_with_consecutive}

    return consecutive_measures

def convert_plan_to_text(data, pitch_shift: int = 0):
    # Remove all_instruments from full_plan to avoid confusion
    if 'all_instruments' in data:
        all_instruments = data['all_instruments']
        del data['all_instruments']

    lines = []

    # Add header with all instruments
    lines.append("Instruments: " + ", ".join(all_instruments))
    lines.append("")

    # Iterate through data.items() and add pitch shift to pitch range, key signature, and chords
    for measure, details in data.items():
        # Adjust pitch range with pitch shift
        if details['pitch_range']['min'] is not None:
            details['pitch_range']['min'] += pitch_shift
        if details['pitch_range']['max'] is not None:
            details['pitch_range']['max'] += pitch_shift
        
        # Adjust key signature with pitch shift
        if details['key_signature'] is not None:
            details['key_signature'] += pitch_shift
        
        # Adjust chords with pitch shift
        if details['chords']:
            chords = [[i + pitch_shift for i in chord] for chord in details['chords']]
            details['chords'] = chords
            

    for measure, details in data.items():
        lines.append(f"{measure}")
        lines.append(f"  Instruments: {', '.join(details['instruments'])}")
        lines.append(f"  Pitch Range: {details['pitch_range']['min']}–{details['pitch_range']['max']}")
        lines.append(f"  Note Density: {details['note_density']}")
        lines.append(f"  Tempo: {details['tempo']} BPM" if details['tempo'] is not None else "  Tempo: None")
        lines.append(f"  Time Signature: {details['time_signature']}")
        lines.append(f"  Key Signature: {details['key_signature']}")
        chords = [f"[{', '.join(map(str, chord))}]" for chord in details['chords']]
        if not chords:
            lines.append("  Chords: None")
        else:
            lines.append(f"  Chords: {', '.join(chords)}")
        lines.append("")  # Blank line between measures
    return "\n".join(lines)

def convert_measures_to_text(data, all_instruments, pitch_shift: int = 0):
    key_mode_map = {0: "minor", 1: "major"}
    lines = []

    # Add header with all instruments
    lines.append("Instruments: " + ", ".join(all_instruments))
    lines.append("")

    # Iterate through data.items() and add pitch shift to pitch range, key signature, and chords
    for measure, details in data.items():
        # Adjust pitch range with pitch shift
        if details['pitch_range']['min'] is not None:
            details['pitch_range']['min'] += pitch_shift
        if details['pitch_range']['max'] is not None:
            details['pitch_range']['max'] += pitch_shift
        
        # Adjust key signature with pitch shift
        if details['key_signature'] is not None:
            details['key_signature'] += pitch_shift
        
        # Adjust chords with pitch shift
        if details['chords']:
            chords = [[i + pitch_shift for i in chord] for chord in details['chords']]
            details['chords'] = chords
            

    for measure, details in data.items():
        lines.append(f"{measure}")
        lines.append(f"  Instruments: {', '.join(details['instruments'])}")
        lines.append(f"  Pitch Range: {details['pitch_range']['min']}–{details['pitch_range']['max']}")
        lines.append(f"  Note Density: {details['note_density']}")
        lines.append(f"  Tempo: {details['tempo']} BPM" if details['tempo'] is not None else "  Tempo: None")
        lines.append(f"  Time Signature: {details['time_signature']}")
        key_mode = key_mode_map.get(details['key_mode'], "Unknown")
        lines.append(f"  Key Signature: {details['key_signature']} ({key_mode})")
        chords = [f"[{', '.join(map(str, chord))}]" for chord in details['chords']]
        if not chords:
            lines.append("  Chords: None")
        else:
            lines.append(f"  Chords: {', '.join(chords)}")
        lines.append("")  # Blank line between measures
    return "\n".join(lines)

def get_full_plan_pipeline(musicxml_file: str):
    """
    Pipeline to get the full plan from a MusicXML file.

    Args:
        musicxml_file: The path to the MusicXML file.

    Returns:
        A dictionary representing the full plan.
    """
    data = get_raw_xml_info(musicxml_file)
    combined_data = combine_raw_xml_info(data)
    full_plan = get_full_plan(combined_data)
    return full_plan

def get_text_from_xml(musicxml_file: str, pitch_shift: int = 0):
    """
    Extracts text representation from a MusicXML file.

    Args:
        musicxml_file: The path to the MusicXML file.

    Returns:
        A string containing the text representation of the measures.
    """
    data = get_raw_xml_info(musicxml_file)
    combined_data = combine_raw_xml_info(data)
    full_plan = get_full_plan(combined_data)
    top_priority_measures, all_instruments = get_priority_order(full_plan, top_pct=10, top_n=5)
    consecutive_measures = get_consecutive_measures(full_plan, top_priority_measures)
    return convert_measures_to_text(consecutive_measures, all_instruments, pitch_shift=pitch_shift)

def get_text_from_pkl(pkl_file: str, pitch_shift: int = 0):
    """
    Extracts text representation from a pickled full plan file.

    Args:
        pkl_file: The path to the pickled full plan file.

    Returns:
        A string containing the text representation of the measures.
    """
    import pickle
    with open(pkl_file, 'rb') as f:
        full_plan = pickle.load(f)
    
    top_priority_measures, all_instruments = get_priority_order(full_plan, top_pct=10, top_n=5)
    consecutive_measures = get_consecutive_measures(full_plan, top_priority_measures)
    return convert_measures_to_text(consecutive_measures, all_instruments, pitch_shift=pitch_shift)

def get_plan_text_from_pkl(pkl_file: str, pitch_shift: int = 0):
    """
    Extracts text representation from a pickled full plan file.

    Args:
        pkl_file: The path to the pickled full plan file.

    Returns:
        A string containing the text representation of the measures.
    """
    import pickle
    with open(pkl_file, 'rb') as f:
        full_plan = pickle.load(f)
    
    return convert_plan_to_text(full_plan, pitch_shift=pitch_shift)


if __name__ == "__main__":
    # Example usage
    filepath = "/data/scratch/acw769/ABC_Dataset/SymphonyNet_Dataset_MXL_abci/outputs/1203.pkl" # Replace with your MusicXML file path
    # filepath = "/data/scratch/acw769/ABC_Dataset/PDMX_MXL_abci/mxl_abci/7/20/QmPFakSAmBn3atKBGdmUK2oad6Age7SqLs8qVUja8TgAZW.pkl"
    text = get_plan_text_from_pkl(filepath)
    print(text)

    # data = get_raw_xml_info(musicxml_file)
    # combined_data = combine_raw_xml_info(data)
    # full_plan = get_full_plan(combined_data)

    # # Example usage of get_priority_order
    # top_priority_measures, all_instruments = get_priority_order(full_plan, top_pct=10, top_n=5)
    # print("Top Priority Measures:", top_priority_measures)

    # # Example usage of get_consecutive_measures
    # consecutive_measures = get_consecutive_measures(full_plan, top_priority_measures)
    # print("Consecutive Measures:", consecutive_measures)

    # # Example usage of convert_measures_to_text
    # text_representation = convert_measures_to_text(consecutive_measures)
    # print("Text Representation of Measures:\n", text_representation)