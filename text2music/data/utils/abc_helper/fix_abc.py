def fix_missing_voice_field(abc_lines):
    # Check if any line starts with "V:" (i.e., voice field already present)
    has_voice_field = any(line.strip().startswith("V:") for line in abc_lines)
    if has_voice_field:
        return abc_lines  # No changes needed if V: field exists

    fixed_lines = []
    voice_inserted = False

    for line in abc_lines:
        stripped = line.strip()
        fixed_lines.append(line)
        # Insert "V:1" right after the "K:" key signature line
        if not voice_inserted and stripped.startswith("K:"):
            fixed_lines.append("V:1")
            voice_inserted = True

    # Add "[V:1]" to each body line (after the header), unless it already specifies a voice
    final_lines = []
    in_body = False
    for line in fixed_lines:
        if not in_body and line.strip().startswith("K:"):
            in_body = True
        if in_body and line.strip() and not line.strip().startswith("[V:"):
            final_lines.append(f"[V:1]{line}")
        else:
            final_lines.append(line)

    return final_lines


def remove_empty_lines(abc_lines):
    # Remove lines that are completely empty or contain only whitespace
    return [line for line in abc_lines if line.strip()]
