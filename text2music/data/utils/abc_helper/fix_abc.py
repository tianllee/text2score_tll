def fix_missing_voice_field(abc_lines):
    # Check if a voice field exists
    has_voice_field = any(line.strip().startswith("V:") for line in abc_lines)
    if has_voice_field:
        return abc_lines

    fixed_lines = []
    voice_inserted = False
    body_started = False
    header_fields = ("X:", "T:", "C:", "R:", "S:", "M:", "L:", "Q:", "K:", "Z:", "N:", "P:")

    for line in abc_lines:
        stripped = line.strip()

        # Insert V:1 right after K:
        if not voice_inserted and stripped.startswith("K:"):
            fixed_lines.append(line)
            fixed_lines.append("V:1")
            voice_inserted = True
            continue

        # After V:1, any line that is not a header is assumed to be body
        if voice_inserted and not stripped.startswith(header_fields) and stripped != "":
            body_started = True

        # If in body and line does not start with [V: or is not blank, add [V:1]
        if body_started and not stripped.startswith("[V:") and stripped != "":
            fixed_lines.append(f"[V:1]{line}")
        else:
            fixed_lines.append(line)

    return fixed_lines


def remove_empty_lines(abc_lines):
    # Remove lines that are completely empty or contain only whitespace
    return [line for line in abc_lines if line.strip()]
