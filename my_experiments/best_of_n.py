"""Best-of-N generation: generate N candidates per prompt, discard invalid ones, keep the best.

Usage (from repo root, conda env active):
  python my_experiments/best_of_n.py --prompts my_experiments/my_prompts.json --n 4 --out my_experiments/bon
  python my_experiments/best_of_n.py --prompts ... --out ... --skip_generate      # re-score existing candidates

Output:
  <out>/candidates/<id*100+k>/...   every candidate (abc, xml)
  <out>/best/<id>.xml / .abc / .mid  the winner for each prompt (+ .mp3 with --mp3)
  <out>/report.json                  all scores
"""
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from scoring import score_xml  # noqa: E402

MSCORE = "/Applications/MuseScore 4.app/Contents/MacOS/mscore"


def run(cmd, log):
    with open(log, "a") as f:
        subprocess.run(cmd, cwd=REPO, stdout=f, stderr=subprocess.STDOUT, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip_generate", action="store_true")
    ap.add_argument("--mp3", action="store_true", help="render winners to mp3 with MuseScore")
    args = ap.parse_args()
    assert 1 <= args.n <= 99

    out = Path(args.out).resolve()
    cand_dir = out / "candidates"
    best_dir = out / "best"
    log = out / "run.log"
    out.mkdir(parents=True, exist_ok=True)
    items = json.load(open(args.prompts))

    if not args.skip_generate:
        cands = [dict(it, id=it["id"] * 100 + k, parent=it["id"]) for it in items for k in range(1, args.n + 1)]
        cjson = out / "candidates.json"
        json.dump(cands, open(cjson, "w"), indent=1, ensure_ascii=False)
        print(f"Generating {len(cands)} candidates ({args.n} per prompt)... log: {log}", flush=True)
        run([sys.executable, "-u", "text2music/inference/run_inference.py",
             "--prompt_path_json", str(cjson), "--output_folder", str(cand_dir) + "/"], log)
        print("Converting to MusicXML...", flush=True)
        run([sys.executable, "text2music/data/batch_abci2xml.py", "--root_folder", str(cand_dir) + "/"], log)

    import music21 as m21
    best_dir.mkdir(exist_ok=True)
    report = []
    for it in items:
        rows = []
        for k in range(1, args.n + 1):
            cid = it["id"] * 100 + k
            xml = next((cand_dir / str(cid) / "xml").glob("*.xml"), None)
            row = dict(candidate=cid, valid=False, score=None)
            if xml:
                try:
                    sc, parts = score_xml(it["openai_plan"], xml)
                    row.update(valid=True, score=round(sc, 4), parts={k2: (round(v, 3) if v is not None else None) for k2, v in parts.items()}, xml=str(xml))
                except Exception as e:
                    row["error"] = f"parse failed: {e}"
            else:
                row["error"] = "no XML (conversion failed)"
            rows.append(row)

        valid = [r for r in rows if r["valid"]]
        winner = max(valid, key=lambda r: r["score"]) if valid else None
        report.append(dict(id=it["id"], prompt=it["prompt"], winner=winner and winner["candidate"], candidates=rows))

        print(f"\n=== {it['id']}: {it['prompt'][:80]}")
        for r in rows:
            mark = " <- BEST" if winner and r["candidate"] == winner["candidate"] else ""
            if r["valid"]:
                p = r["parts"]
                print(f"  {r['candidate']}: {r['score']:.3f}  (struct {p['structure']:.2f} range {p['range_iou']:.2f} "
                      f"chord {p['chord_share'] if p['chord_share'] is not None else '-'} active {p['activity']:.2f} "
                      f"variety {p['variety']:.2f}){mark}")
            else:
                print(f"  {r['candidate']}: INVALID ({r['error']})")

        if winner:
            stem = best_dir / str(it["id"])
            shutil.copy(winner["xml"], f"{stem}.xml")
            abc = next((cand_dir / str(winner["candidate"]) / "original").glob("*.abc"), None)
            if abc:
                shutil.copy(abc, f"{stem}.abc")
            m21.converter.parse(winner["xml"]).write("midi", fp=f"{stem}.mid")
            if args.mp3 and os.path.exists(MSCORE):
                subprocess.run([MSCORE, "-o", f"{stem}.mp3", winner["xml"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    json.dump(report, open(out / "report.json", "w"), indent=1, ensure_ascii=False)
    n_valid = sum(r["valid"] for rep in report for r in rep["candidates"])
    n_all = sum(len(rep["candidates"]) for rep in report)
    print(f"\nValid candidates: {n_valid}/{n_all}. Winners in {best_dir}")


if __name__ == "__main__":
    main()
