"""Score a generated score (MusicXML) against its plan. Higher is better, range ~0..1.

Components (each 0..1):
  structure   : bar count, key signature and time signature match the plan
  range_iou   : per planned bar, overlap between actual and planned pitch range
  chord_share : per planned bar, fraction of notes that are planned chord tones (skipped if plan has no chords)
  activity    : fraction of planned instruments/parts that actually play
  variety     : 1 - fraction of consecutive identical bars (per part, averaged)

A candidate that fails to convert to XML or parse gets no score (it is invalid).
"""
import warnings
import statistics as st
import music21 as m21
from check_plan import parse_plan, measure_notes

warnings.filterwarnings("ignore")

WEIGHTS = dict(structure=0.20, range_iou=0.25, chord_share=0.25, activity=0.15, variety=0.15)


def _is_perc(part):
    return any(isinstance(c, m21.clef.PercussionClef) for c in part.recurse().getElementsByClass("Clef"))


def score_xml(plan_text, xml_path):
    total, plan = parse_plan(plan_text)
    s = m21.converter.parse(str(xml_path))
    first = plan[min(plan)]

    # structure
    n_meas = len(s.parts[0].getElementsByClass("Measure"))
    ks = s.recurse().getElementsByClass("KeySignature").first()
    ts = s.recurse().getElementsByClass("TimeSignature").first()
    structure = st.mean([
        n_meas == total,
        bool(ks) and ks.sharps == first["key"],
        bool(ts) and ts.ratioString == first["ts"],
    ])

    # per planned bar: range overlap + chord tones
    notes = measure_notes(s)
    ious, chords = [], []
    for num, p in plan.items():
        ps = notes.get(num, [])
        if not ps:
            ious.append(0.0)
            if p["chords"]:
                chords.append(0.0)
            continue
        lo, hi = min(ps), max(ps)
        inter = max(0, min(hi, p["hi"]) - max(lo, p["lo"]))
        union = max(hi, p["hi"]) - min(lo, p["lo"])
        ious.append(inter / union if union else 1.0)
        if p["chords"]:
            chords.append(sum(x % 12 in p["chords"] for x in ps) / len(ps))

    # activity: parts with at least one note (piano staves etc. count individually)
    played = [len(part.recurse().notes) > 0 for part in s.parts]
    activity = st.mean(played) if played else 0.0

    # variety: identical consecutive bars, per pitched part that plays
    rep_fracs = []
    for part in s.parts:
        if _is_perc(part) or not len(part.recurse().notes):
            continue
        meas = part.getElementsByClass("Measure")
        sigs = [tuple((n.offset, tuple(p.midi for p in n.pitches), n.quarterLength) for n in m.recurse().notes) for m in meas]
        pairs = [(a, b) for a, b in zip(sigs, sigs[1:]) if a]
        if pairs:
            rep_fracs.append(sum(a == b for a, b in pairs) / len(pairs))
    variety = 1 - (st.mean(rep_fracs) if rep_fracs else 0.0)

    parts = dict(structure=structure, range_iou=st.mean(ious) if ious else 0.0,
                 chord_share=st.mean(chords) if chords else None, activity=activity, variety=variety)
    w = {k: v for k, v in WEIGHTS.items() if parts[k] is not None}
    total_score = sum(w[k] * parts[k] for k in w) / sum(w.values())
    return total_score, parts
