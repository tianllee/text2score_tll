import music21
import json

# Configuration: (Min MIDI, Max MIDI, Max Chord Interval, is_monophonic)
INSTRUMENT_CONSTRAINTS = {
    # Strings
    "violin":   {"range": (55, 105), "max_span": 13, "mono": False},
    "viola":    {"range": (48, 91), "max_span": 13, "mono": False},
    "cello":    {"range": (36, 76),  "max_span": 12, "mono": False},
    "contrabass": {"range": (28, 67),  "max_span": 8, "mono": False},
    # Woodwinds
    "flute":    {"range": (60, 96),  "max_span": 0,  "mono": True},
    "clarinet": {"range": (50, 94),  "max_span": 0,  "mono": True},
    "oboe":    {"range": (58, 92),  "max_span": 0,  "mono": True},
    "bassoon":  {"range": (34, 82),  "max_span": 0,  "mono": True},
    "piccolo": {"range": (72, 108), "max_span": 0,  "mono": True},
    # Brass
    "saxophone": {"range": (50, 94),  "max_span": 0,  "mono": True},
    "sax": {"range": (50, 94),  "max_span": 0,  "mono": True},
    "tenor sax": {"range": (44, 87),  "max_span": 0,  "mono": True},
    "alto sax": {"range": (49, 92),  "max_span": 0,  "mono": True},
    "trumpet":  {"range": (55, 86),  "max_span": 0,  "mono": True},
    "trombone": {"range": (40, 72),  "max_span": 0,  "mono": True},
    "tuba":     {"range": (28, 60),  "max_span": 0,  "mono": True},
    "horn":     {"range": (31, 77),  "max_span": 0,  "mono": True},
    "brass":    {"range": (28, 94),  "max_span": 0,  "mono": True},
    # Keyboards & Others
    "piano":    {"range": (21, 108), "max_span": 15, "mono": False},
    "synth": {"range": (21, 108), "max_span": 15, "mono": False},
    "pad": {"range": (21, 108), "max_span": 15, "mono": False},
    "organ":    {"range": (21, 108), "max_span": 15, "mono": False},
    "accordion": {"range": (53, 93), "max_span": 13, "mono": False},
    "harp":     {"range": (24, 104), "max_span": 12, "mono": False},
    # Plucked
    "guitar":   {"range": (40, 88),  "max_span": 17, "mono": False},
    # Vocals
    "voice":    {"range": (40, 84),  "max_span": 0,  "mono": True},
    "soprano":  {"range": (60, 84),  "max_span": 0,  "mono": True},
    "alto":     {"range": (55, 74),  "max_span": 0,  "mono": True},
    "tenor":    {"range": (48, 72),  "max_span": 0,  "mono": True},
    # Percussion
    "drum":      {"range": (35, 81),  "max_span": 4,  "mono": False},
    "kit":     {"range": (35, 81),  "max_span": 0,  "mono": False},
    "percussion": {"range": (35, 81),  "max_span": 0,  "mono": False},
}

def get_playability_metrics(xml_path):
    score = music21.converter.parse(xml_path)
    results = {}

    for part in score.parts:
        name = part.partName.lower() if part.partName else "unknown"
        config = next((v for k, v in INSTRUMENT_CONSTRAINTS.items() if k in name), None)
        
        if not config: continue

        total_elements = 0
        violations = {
            "pitch_range": 0,
            "monophonic_correctness": 0,
            "pitch_span": 0,
            "rhythmic_overlap": 0
        }

        elements = part.flatten().notes
        last_end = 0

        for el in elements:
            total_elements += 1
            
            # 1. pitch_range: Checks if any note in the element is out of bounds
            pitches = [p.ps for p in el.pitches]
            if any(p < config["range"][0] or p > config["range"][1] for p in pitches):
                violations["pitch_range"] += 1

            # 2. monophonic_correctness: Checks if a mono instrument is given a Chord
            if config["mono"] and isinstance(el, music21.chord.Chord):
                violations["monophonic_correctness"] += 1
            
            # 3. pitch_span: Checks if a chord is physically too wide (overstretch)
            if not config["mono"] and isinstance(el, music21.chord.Chord):
                span = max(pitches) - min(pitches)
                if span > config["max_span"]:
                    violations["pitch_span"] += 1
            
            # 4. rhythmic_overlap: Checks for MIDI-style "ghost" overlaps
            # In a clean ABC-to-XML, a note shouldn't start before the previous one ends
            if el.offset < last_end:
                violations["rhythmic_overlap"] += 1
            
            last_end = el.offset + el.duration.quarterLength

        # Normalizing to Percentages (100% = No Violations)
        if total_elements > 0:
            metrics = {
                "pitch_range": (1 - (violations["pitch_range"] / total_elements)) * 100,
                "monophonic_correctness": (1 - (violations["monophonic_correctness"] / total_elements)) * 100,
                "pitch_span": (1 - (violations["pitch_span"] / total_elements)) * 100,
                "rhythmic_overlap": (1 - (violations["rhythmic_overlap"] / total_elements)) * 100,
            }
            # Total Playability Score: Simple average of the 4 metrics
            metrics["total_playability_score"] = sum(metrics.values()) / 4
        else:
            metrics = {k: 100.0 for k in violations}
            metrics["total_playability_score"] = 100.0

        results[part.partName] = metrics

    return results

def get_readability_metrics(xml_path):
    score = music21.converter.parse(xml_path)
    results = {}

    for part in score.parts:
        elements = part.flatten().notes
        total_elements = len(elements)
        
        violations = {
            "rhythmic_complexity": 0,    # Ties
            "micro_rhythmic_jitter": 0,  # 64th note onsets/durations
            "accidental_consistency": 0, # Diatonic check
            "enharmonic_directionality": 0 # Sharp/Flat mismatch
        }
        
        # Key context for accidental checking
        ks = part.flatten().getContextByClass(music21.key.KeySignature)
        key_obj = ks.asKey() if ks else music21.key.Key('C')
        diatonic_names = [p.name for p in key_obj.pitches]
        
        # Determine if the key is "Sharp-based" or "Flat-based"
        key_type = 'neutral' # C Maj / A Min
        if ks:
            if ks.sharps > 0: key_type = 'sharp'
            elif ks.sharps < 0: key_type = 'flat'

        for el in elements:
            # 1. rhythmic_complexity (Ties)
            if el.tie is not None:
                violations["rhythmic_complexity"] += 1

            # 2. micro_rhythmic_jitter (64th note threshold)
            # Quarter length for 64th note = 0.0625
            is_jitter_duration = el.duration.quarterLength <= 0.0625
            is_jitter_onset = (el.offset % 0.0625) != 0
            if is_jitter_duration or is_jitter_onset:
                violations["micro_rhythmic_jitter"] += 1

            # 3. accidental_consistency (Diatonic)
            pitches = el.pitches if hasattr(el, 'pitches') else []
            if any(p.name not in diatonic_names for p in pitches):
                violations["accidental_consistency"] += 1
            
            # 4. enharmonic_directionality
            # Flag if note uses Sharp in a Flat key, or Flat in a Sharp key.
            for p in pitches:
                if p.accidental:
                    acc_name = p.accidental.name
                    if key_type == 'sharp' and 'flat' in acc_name:
                        violations["enharmonic_directionality"] += 1
                    elif key_type == 'flat' and 'sharp' in acc_name:
                        violations["enharmonic_directionality"] += 1

        if total_elements > 0:
            metrics = {k: (1 - (v / total_elements)) * 100 for k, v in violations.items()}
            metrics["total_readability_score"] = sum(metrics.values()) / 4
        else:
            metrics = {k: 100.0 for k in violations}
            metrics["total_readability_score"] = 100.0

        part_name = part.partName if part.partName else "Unknown"
        results[part_name] = metrics

    return results


def validate_musicxml_metadata(xml_path, expected_tempo, expected_key, expected_ts):
    score = music21.converter.parse(xml_path)
    
    # 1. TIME SIGNATURE VALIDATION
    # Some XMLs don't 'flatten' well, so we search explicitly in the first part/measure
    all_ts = score.flatten().getElementsByClass(music21.meter.TimeSignature)
    ts_actual = all_ts[0] if len(all_ts) > 0 else None
    
    # Check ratioString (e.g., '4/4')
    ts_score = 1 if (ts_actual and ts_actual.ratioString == expected_ts) else 0

    # 2. KEY SIGNATURE VALIDATION
    # KeySignatures (sharps/flats) are different from Key objects (Major/Minor)
    all_ks = score.flatten().getElementsByClass(music21.key.KeySignature)
    ks_actual = all_ks[0] if len(all_ks) > 0 else None
    
    key_score = 0
    if ks_actual:
        # We convert the KeySignature to a Key object to get a comparable string
        # This handles cases like 'G major' vs 'G'
        actual_key_str = ks_actual.asKey().name.lower()
        if actual_key_str == expected_key.lower():
            key_score = 1
            
    # 3. TEMPO VALIDATION
    # If getContextByClass failed, we search for MetronomeMark specifically
    all_metronomes = score.flatten().getElementsByClass(music21.tempo.MetronomeMark)
    tempo_actual = all_metronomes[0] if len(all_metronomes) > 0 else None
    
    tempo_score = 0
    if tempo_actual:
        # Use a small delta for float comparison in case of rounding
        if abs(float(tempo_actual.number) - float(expected_tempo)) <= 1.0:
            tempo_score = 1
    else:
        # Backup: Some ABC-to-XML converters put tempo in a TextExpression
        all_text = score.flatten().getElementsByClass(music21.expressions.TextExpression)
        for t in all_text:
            if "BPM" in t.content or "=" in t.content:
                # Try to extract numbers from text if MetronomeMark is missing
                import re
                match = re.search(r'\d+', t.content)
                if match and abs(float(match.group()) - float(expected_tempo)) <= 1.0:
                    tempo_score = 1

    return {
        "tempo_match": tempo_score,
        "key_match": key_score,
        "time_sig_match": ts_score
    }

# Example Usage with your JSON data:
results = validate_musicxml_metadata("/gpfs/scratch/acw769/text2score/text2score_ablated_v2/1/xml/1_output.xml", 72, "G major", "4/4")
print(results)

# Example usage:
metrics = get_playability_metrics('/data/home/acw769/text2score/text2music/notebooks/reconstructed_amt.xml')
print(json.dumps(metrics, indent=4))

metrics = get_playability_metrics('/gpfs/scratch/acw769/text2score/text2score_ablated_v2/1/xml/1_output.xml')
print(json.dumps(metrics, indent=4))

# Example usage:
metrics = get_readability_metrics('/data/home/acw769/text2score/text2music/notebooks/reconstructed_amt.xml')
print(json.dumps(metrics, indent=4))

metrics = get_readability_metrics('/gpfs/scratch/acw769/text2score/text2score_ablated_v2/1/xml/1_output.xml')
print(json.dumps(metrics, indent=4))