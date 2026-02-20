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
    """
    Evaluates the visual readability of a MusicXML file.
    Returns a dictionary of scores (0-100%) for each part.
    """
    # Load and parse the MusicXML file
    score = music21.converter.parse(xml_path)
    results = {}

    for part in score.parts:
        # Flatten the part to access notes and chords sequentially
        elements = part.flatten().notes
        total_elements = len(elements)
        
        violations = {
            "rhythmic_complexity": 0,
            "accidental_consistency": 0,
            "beam_stem_logic": 0
        }
        
        # Set up context for accidental checking
        # We extract pitch names from the Scale to avoid 'isDiatonic' attribute errors
        ks = part.flatten().getContextByClass(music21.key.KeySignature)
        key_obj = ks.asKey() if ks else music21.key.Key('C')
        diatonic_names = [p.name for p in key_obj.pitches]

        for el in elements:
            # 1. rhythmic_complexity (The "Ties" Metric)
            # High tie counts often indicate jittery MIDI-to-XML conversion.
            if el.tie is not None:
                violations["rhythmic_complexity"] += 1

            # 2. accidental_consistency (Diatonic Integrity)
            # Checks if the pitch name (e.g., 'F#') matches the scale of the key.
            pitches = el.pitches if hasattr(el, 'pitches') else []
            if any(p.name not in diatonic_names for p in pitches):
                violations["accidental_consistency"] += 1

            # 3. beam_stem_logic (Engraving Metadata)
            # Checks if the file contains explicit stem/beam instructions. 
            # ABC-to-XML is usually explicit; MIDI-to-XML relies on software auto-guessing.
            has_beams = len(el.beams) > 0
            has_stem = el.stemDirection not in [None, 'unspecified']
            if not (has_beams or has_stem):
                violations["beam_stem_logic"] += 1

        # Calculate final percentages (100% = No Violations / Perfect Readability)
        if total_elements > 0:
            metrics = {
                "rhythmic_complexity": (1 - (violations["rhythmic_complexity"] / total_elements)) * 100,
                "accidental_consistency": (1 - (violations["accidental_consistency"] / total_elements)) * 100,
                "beam_stem_logic": (1 - (violations["beam_stem_logic"] / total_elements)) * 100,
            }
            metrics["total_readability_score"] = sum(metrics.values()) / 3
        else:
            # Default to 100% if the part is empty
            metrics = {k: 100.0 for k in violations}
            metrics.update({"total_readability_score": 100.0})

        part_name = part.partName if part.partName else "Unknown"
        results[part_name] = metrics

    return results

# Example usage:
metrics = get_playability_metrics('/data/home/acw769/text2score/text2music/notebooks/reconstructed_amt.xml')
print(json.dumps(metrics, indent=4))

metrics = get_playability_metrics('/data/home/acw769/text2score/text2music/notebooks/flute_solo.xml')
print(json.dumps(metrics, indent=4))

# Example usage:
metrics = get_readability_metrics('/data/home/acw769/text2score/text2music/notebooks/reconstructed_amt.xml')
print(json.dumps(metrics, indent=4))

metrics = get_readability_metrics('/data/home/acw769/text2score/text2music/notebooks/flute_solo.xml')
print(json.dumps(metrics, indent=4))