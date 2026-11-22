"""Aggregate plan adherence for the bar-numbering trial.

For every piece, measure how well each planned bar is realised at a given score bar:
  - range_ok:    planned bar's notes stay within planned pitch range (+/-2 semitones)
  - range_iou:   overlap of actual vs planned pitch range (0..1), finer-grained than range_ok
  - chord_share: fraction of pitched notes that are planned chord tones

Variant "orig"  = 1-indexed plan, read at score bar = plan bar        (offset 0)
Variant "shift" = 0-indexed plan, read at score bar = plan bar + 1    (offset 1)
Both target the SAME intended bars, so they are directly comparable.
As a diagnostic we also read "orig" at offset +1 (does the model land one bar late?).

Usage: python my_experiments/compare_trial.py my_experiments/trial_prompts.json my_experiments/trial_outputs
"""
import json, sys, statistics as st, warnings
from pathlib import Path
import music21 as m21
from check_plan import parse_plan, measure_notes

warnings.filterwarnings("ignore")


def score_piece(plan, notes, offset):
    r_ok, r_iou, ch = [], [], []
    for num, p in plan.items():
        ps = notes.get(num + offset, [])
        if not ps:
            r_ok.append(0); r_iou.append(0)
            if p["chords"]: ch.append(0)
            continue
        lo, hi = min(ps), max(ps)
        r_ok.append(int(lo >= p["lo"] - 2 and hi <= p["hi"] + 2))
        inter = max(0, min(hi, p["hi"]) - max(lo, p["lo"]))
        union = max(hi, p["hi"]) - min(lo, p["lo"])
        r_iou.append(inter / union if union else 1.0)
        if p["chords"]:
            ch.append(sum(x % 12 in p["chords"] for x in ps) / len(ps))
    return st.mean(r_ok), st.mean(r_iou), (st.mean(ch) if ch else None)


def main(trial_json, out_dir):
    items = json.load(open(trial_json))
    rows = []
    for it in items:
        xml = next(Path(out_dir, str(it["id"]), "xml").glob("*.xml"), None)
        if xml is None:
            print(f"missing output for {it['id']}"); continue
        _, plan = parse_plan(it["openai_plan"])
        notes = measure_notes(m21.converter.parse(str(xml)))
        offsets = [("orig@0", 0), ("orig@+1", 1)] if it["variant"] == "orig" else [("shift@+1", 1)]
        for label, off in offsets:
            rows.append((label, it["base"], *score_piece(plan, notes, off)))

    names = {1: "lullaby", 2: "quartet", 3: "jazz", 4: "jig"}
    print(f"{'condition':10} {'piece':8} {'range_ok':>9} {'range_iou':>10} {'chord':>7}  n")
    for label in ["orig@0", "shift@+1", "orig@+1"]:
        for base in [1, 2, 3, 4, None]:
            sel = [r for r in rows if r[0] == label and (base is None or r[1] == base)]
            if not sel: continue
            chords = [r[4] for r in sel if r[4] is not None]
            print(f"{label:10} {names.get(base, 'ALL'):8} {st.mean(r[2] for r in sel):9.2f} "
                  f"{st.mean(r[3] for r in sel):10.2f} {(st.mean(chords) if chords else float('nan')):7.2f}  {len(sel)}")
        print()


if __name__ == "__main__":
    main(*sys.argv[1:3])
