"""Summarise best_of_n runs from a parameter sweep.

Usage: python my_experiments/summarize_sweep.py my_experiments/bon_temp_0.8 my_experiments/bon_temp_1.0 ...
"""
import json, sys, statistics as st
from pathlib import Path

COMPONENTS = ["range_iou", "chord_share", "variety"]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return st.mean(xs) if xs else float("nan")


print(f"{'run':18} {'valid':>7} {'mean':>6} {'best':>6} " + " ".join(f"{c:>11}" for c in COMPONENTS))
for d in sys.argv[1:]:
    rep = json.load(open(Path(d) / "report.json"))
    cands = [c for r in rep for c in r["candidates"]]
    valid = [c for c in cands if c["valid"]]
    best = [max(c["score"] for c in r["candidates"] if c["valid"]) for r in rep if any(c["valid"] for c in r["candidates"])]
    comps = [mean(c["parts"][k] for c in valid) for k in COMPONENTS]
    print(f"{Path(d).name:18} {len(valid):>3}/{len(cands):<3} {mean(c['score'] for c in valid):6.3f} {mean(best):6.3f} "
          + " ".join(f"{x:11.3f}" for x in comps))

print("\nPer prompt (mean / best):")
names = None
for d in sys.argv[1:]:
    rep = json.load(open(Path(d) / "report.json"))
    cells = []
    for r in rep:
        sc = [c["score"] for c in r["candidates"] if c["valid"]]
        cells.append(f"{r['id']}: {mean(sc):.3f}/{(max(sc) if sc else float('nan')):.3f} ({len(sc)}/{len(r['candidates'])})")
    print(f"  {Path(d).name:18} " + "  ".join(cells))
