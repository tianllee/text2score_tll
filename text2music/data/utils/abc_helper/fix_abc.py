def fix_missing_voice_field(abc_lines):
    has_voice_header = any(line.strip().startswith("V:") for line in abc_lines)
    has_voice_tags = any("[V:" in line for line in abc_lines)

    if has_voice_header and has_voice_tags:
        return abc_lines  # Already has proper voice structure

    fixed_lines = []
    voice_inserted = False
    body_started = False
    header_fields = ("X:", "T:", "C:", "R:", "S:", "M:", "L:", "Q:", "K:", "Z:", "N:", "P:", "V:")

    for line in abc_lines:
        stripped = line.strip()

        # Insert V:1 after K: if V: doesn't exist yet
        if not has_voice_header and not voice_inserted and stripped.startswith("K:"):
            fixed_lines.append(line)
            fixed_lines.append("V:1")
            voice_inserted = True
            continue

        # After V:1 or K:, we consider body has started once we hit a non-header, non-empty line
        if (has_voice_header or voice_inserted) and not stripped.startswith(header_fields) and stripped != "":
            body_started = True

        # If in body and line does not have [V:, prefix it
        if body_started and not stripped.startswith("[V:") and stripped != "":
            fixed_lines.append(f"[V:1]{line}")
        else:
            fixed_lines.append(line)

    return fixed_lines


def remove_empty_lines(abc_lines):
    # Remove lines that are completely empty or contain only whitespace
    return [line for line in abc_lines if line.strip()]
