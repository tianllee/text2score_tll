"""Compare generated scores against their plans.

Usage: python my_experiments/check_plan.py PROMPTS_JSON OUTPUTS_DIR [OFFSET]
OFFSET: added to plan bar numbers to get score bar numbers (1 if plan is 0-indexed).
"""
import json, re, sys, warnings
from pathlib import Path
import music21 as m21

warnings.filterwarnings("ignore")


def parse_plan(text):
    total = int(re.search(r"Total Measures:\s*(\d+)", text).group(1))
    measures = {}
    for block in re.split(r"\n\s*\n", text):
        mm = re.search(r"Measure:\s*(\d+)", block)
        if not mm:
            continue
        d = {}
        for line in block.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                d[k.strip()] = v.strip()
        lo, hi = re.split(r"[–-]", d["Pitch Range"])
        chords = None if d["Chords"] == "None" else json.loads(d["Chords"])
        measures[int(mm.group(1))] = dict(lo=int(lo), hi=int(hi), chords=chords,
                                          density=d["Note Density"], ts=d["Time Signature"],
                                          key=int(d["Key Signature"]), tempo=int(d["Tempo"].split()[0]))
    return total, measures


def measure_notes(score):
    """measure number -> list of MIDI pitches across all parts (excluding percussion)."""
    out = {}
    for part in score.parts:
        if any(isinstance(c, m21.clef.PercussionClef) for c in part.recurse().getElementsByClass("Clef")):
            continue
        for meas in part.getElementsByClass("Measure"):
            ps = [p.midi for n in meas.recurse().notes for p in n.pitches]
            out.setdefault(meas.number, []).extend(ps)
    return out


def main(prompts_json, outputs_dir, offset=0):
    offset = int(offset)
    items = json.load(open(prompts_json))
    for it in items:
        pid = str(it["id"])
        xml = next(Path(outputs_dir, pid, "xml").glob("*.xml"), None)
        print(f"\n=== {pid}: {it['prompt']}")
        if xml is None:
            print("  NO XML OUTPUT"); continue
        total, plan = parse_plan(it["openai_plan"])
        s = m21.converter.parse(str(xml))
        n_meas = len(s.parts[0].getElementsByClass("Measure"))
        ks = s.recurse().getElementsByClass("KeySignature").first()
        ts = s.recurse().getElementsByClass("TimeSignature").first()
        first = plan[min(plan)]
        print(f"  measures: {n_meas} (plan {total})  {'OK' if n_meas == total else 'MISMATCH'}")
        print(f"  key sig: {ks.sharps if ks else None} (plan {first['key']})  "
              f"time sig: {ts.ratioString if ts else None} (plan {first['ts']})")
        try:
            print(f"  analyzed key: {s.analyze('key')}")
        except Exception:
            pass

        # Per-part activity
        for part in s.parts:
            notes = len(part.recurse().notes)
            name = part.partName or part.id
            flag = "  <-- SILENT" if notes == 0 else ""
            print(f"  part {name!s:25} notes={notes}{flag}")

        # Per planned measure: pitch range + chord adherence
        mn = measure_notes(s)
        in_range = chord_hits = chord_total = 0
        for num, p in sorted(plan.items()):
            ps = mn.get(num + offset, [])
            if not ps:
                print(f"  m{num}: no pitched notes"); continue
            lo, hi = min(ps), max(ps)
            ok_range = lo >= p["lo"] - 2 and hi <= p["hi"] + 2
            in_range += ok_range
            line = f"  m{num}: range {lo}-{hi} (plan {p['lo']}-{p['hi']}) {'ok' if ok_range else 'OFF'}"
            if p["chords"]:
                pcs = [x % 12 for x in ps]
                frac = sum(pc in p["chords"] for pc in pcs) / len(pcs)
                chord_hits += frac; chord_total += 1
                line += f" | {frac:.0%} notes in chord {p['chords']}"
            print(line)

        # Repetition: identical consecutive measures in the top part
        top = s.parts[0].getElementsByClass("Measure")
        sigs = [tuple((n.offset, tuple(p.midi for p in n.pitches), n.quarterLength) for n in m.recurse().notes) for m in top]
        repeats = sum(1 for a, b in zip(sigs, sigs[1:]) if a and a == b)
        print(f"  summary: pitch-range ok {in_range}/{len(plan)}"
              + (f", avg chord-tone share {chord_hits / chord_total:.0%}" if chord_total else "")
              + f", repeated consecutive bars (top part) {repeats}/{len(sigs) - 1}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
