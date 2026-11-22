# Project Notes: Text2Score Extension

Last updated: 2026-11-22 (evening)

**Goal:** build on Text2Score to make a working, *good* text-to-sheet-music engine.

- Paper: https://arxiv.org/abs/2605.13431
- Upstream code: https://github.com/keshavbhandari/text2score (remote `upstream`)
- My fork: https://github.com/tianllee/text2score_tll (remote `origin`), working branch `mac-support`
- Dataset (only needed for training, 4.7 GB): https://huggingface.co/datasets/emotionwave-company/text2score

---

## How the pipeline works

1. **Prompt → plan:** an LLM (GPT-5.1 by default, prompt in `text2music/inference/prompt.py`) writes a per-bar plan: instruments, pitch range, note density, tempo, time signature, key signature (as a number of sharps or flats), and chords (as pitch-class sets).
2. **Plan → ABC notation:** the Text2Score model (3.4 GB weights, downloaded automatically to `text2music/artifacts/`).
3. **ABC → MusicXML / MIDI:** `text2music/data/batch_abci2xml.py`, then `text2music/data/utils/xml2mid.py`.

The model only ever sees the plan, never the original text prompt. Plan quality limits everything downstream.

---

## Setup on this Mac (done)

- Repo at `~/text2score`, conda env `text2score` (native arm64, Python 3.10, torch 2.14).
  - `/opt/miniconda3` is an Intel (x86) build. Always create new envs with `CONDA_SUBDIR=osx-arm64` or they run under Rosetta with an old torch.
- Added Apple GPU (MPS) support to `inference.py` and `run_inference.py`.
- Installed `music21`, which the MIDI script needs but the dependency list doesn't include.
- MuseScore 4 is installed. Use it to view and play the XML files, or to render MP3s (IINA can't play `.mid`):
  `"/Applications/MuseScore 4.app/Contents/MacOS/mscore" -o out.mp3 in.xml`
- The GitHub CLI (`gh`) is installed and logged in as tianllee.

### Common commands
```bash
source /opt/miniconda3/etc/profile.d/conda.sh && conda activate text2score
cd ~/text2score

# Single piece from a plan file
python text2music/inference/inference.py --plan_path text2music/artifacts/example_plans/partial_plan.txt

# Batch run (JSON list of {id, prompt, openai_plan})
python text2music/inference/run_inference.py --prompt_path_json my_experiments/my_prompts.json --output_folder my_experiments/outputs/
python text2music/data/batch_abci2xml.py --root_folder my_experiments/outputs/
python text2music/data/utils/xml2mid.py --data_dir my_experiments/outputs/

# Check outputs against their plans
python my_experiments/check_plan.py my_experiments/my_prompts.json my_experiments/outputs
```

**Speed on the M3 Pro:** about 40 s per piece once the model is loaded. Generating and reviewing music works fine locally; a cloud GPU is only needed for training.

---

## What we've done and found

### Step 1: reproduce (done)
The example plan generated a valid 29-bar, 8-part score.

### Step 2: own prompts (done)
4 test prompts (`my_experiments/my_prompts.json`), with plans written by hand following the planner prompt:
101 piano lullaby · 102 string quartet · 103 jazz trio · 104 Irish violin jig.

- The overall settings (key, time signature, tempo, instruments, number of bars) were correct in every piece.
- Bar-by-bar plan adherence is moderate: pitch ranges were followed in about 74% of planned bars, and about 61% of notes belong to the planned chord.
- Upstream's own GPT plans contain mistakes (for example, the first prompt in their evaluation set switches to 3/4 time without being asked).

### Bar-numbering trial (done): no change needed
We suspected the model was one bar off (plans counting from 0 vs. 1). A trial with 40 pieces (4 plans × 5 samples × 2 numberings) showed that counting from 1, as the planner prompt does, is correct. Plans read one bar late scored clearly worse. Results are in `my_experiments/trial_results.txt`.

### Phase 2, #2: best-of-N (done)
`my_experiments/best_of_n.py` + `scoring.py`. For each prompt: generate N candidates, discard any that fail XML conversion, score the rest, keep the winner. Winners go to `<out>/best/` as xml/abc/mid (+ mp3 with `--mp3`), and all scores go to `report.json`.
```bash
python my_experiments/best_of_n.py --prompts my_experiments/my_prompts.json --n 4 --out my_experiments/bon --mp3
```
- **Score (0–1)** = 0.20 structure (bar count, key and time signature) + 0.25 pitch-range overlap + 0.25 chord-tone share + 0.15 share of parts that play + 0.15 variety (no identical consecutive bars). Scores are comparable only within a prompt (prompts without chords skip that term).
- **First run (N=4):** 16/16 valid. The winner beats the average candidate by about +0.04 (quartet +0.08).
- Structure and activity were 1.0 for every candidate, so they don't help rank. The ranking comes from range, chord and variety. A musical-quality signal (human or a validated critic) is still missing.
- Winners to listen to: `my_experiments/bon/best/*.mp3` (gitignored; regenerate with the command above).

### Phase 2, #5: sampling temperature (done): keep the default 1.2
Sampling settings can now be overridden without editing code: `T2S_TEMPERATURE`, `T2S_TOP_K`, `T2S_TOP_P` (env vars read in `text2music/inference/config.py`; defaults unchanged: 1.2 / 9 / 0.9).
Sweep: 4 prompts × 5 candidates × temperatures 0.8 / 1.0 / 1.2 (`my_experiments/temp_sweep_results.txt`):

| Temperature | Valid | Average score | Best-of-5 | Range | Chord | Variety |
|---|---|---|---|---|---|---|
| 0.8 | 20/20 | 0.862 | 0.900 | 0.778 | 0.659 | 0.918 |
| 1.0 | 20/20 | 0.862 | 0.889 | 0.785 | 0.623 | 0.955 |
| 1.2 | 20/20 | 0.859 | 0.897 | 0.804 | 0.619 | 0.948 |

- No real difference overall (<0.003), which is noise at this sample size. Temperature isn't a useful setting to tune; best-of-N (+0.04) matters far more.
- There's a small trade-off: lower temperature hits a few more chord tones but repeats more (one T=0.8 jazz candidate had variety 0.53) and fits the pitch range less well.
- All 60 were valid, so the earlier 2/40 broken-notation rate doesn't look temperature-driven. It's rare, and best-of-N handles it anyway.
- Top-k and top-p haven't been swept. Given this result, they're low priority.

### Known problems
- **Invalid ABC notation sometimes:** 2 of 40 trial pieces (both jazz trio) failed to convert, e.g. `^=e` (two accidentals on one note). The conversion script fails silently and the file is simply missing.
- Some parts rest for the whole piece; some bars repeat mechanically (the maracas in the example, `aaa aaa` in the jig).
- The jig melodies tend to be scale and arpeggio patterns.
- `xml2mid.py` only handles the numbered folder layout from batch runs.
- music21 can't export some pieces to MIDI ("badly formed repeats"); the model sometimes writes unbalanced repeat signs. `best_of_n.py` falls back to MuseScore for those.
- Don't import `text2music/inference/config.py` from anywhere except the repo root. It uses relative paths, and if it can't find the weights it starts a new 3.4 GB download in the wrong place.

---

## Where we left off and next steps

**Done since the first pause:** best-of-N (#2) and the temperature sweep (#5), see above.
**Waiting on the human:** listening to and rating the pieces. That's now the main blocker for choosing between the planner, the critic and the app.
```bash
open ~/text2score/my_experiments/listen/*.mp3          # the 8 single samples (regenerate with mscore if missing)
open ~/text2score/my_experiments/bon/best/*.mp3        # the 4 best-of-4 winners
open -a "MuseScore 4" ~/text2score/my_experiments/bon/best/*.xml
```

1. **Listen and rate (human).** For each piece, give a 1–10 score plus one line on what's wrong (boring melody, odd harmony, idle instrument, …). Also: do the best-of-4 winners sound better than the single samples? If not, the plan-adherence score isn't measuring what matters.
2. **LLM critic experiment.** Claude rates the same pieces from their ABC notation only, without seeing the human ratings; then compare the two sets. If they agree reasonably, add the critic as a term in `scoring.py`. If not, try CLaMP3 (`text2music/scripts/clamp3.py`) or an audio-capable model.
3. ~~Generate several and keep the best~~ ✅ done (`best_of_n.py`).
4. Then, depending on the listening results:
   - Plans followed but the music is dull → improve the planner (richer plans, better chord progressions, more bars specified).
   - Something usable wanted soon → build a Gradio app: prompt → editable plan → rendered score → playback → export.
5. **Long term:** use critic scores, once checked against human ratings, as a training signal to fine-tune the model (needs cloud GPUs; upstream scripts assume 2 GPUs).

### The LLM-as-critic idea (discussed, not started)
- LLMs already know a lot of theory and criticism. The bottleneck is *perception*: reading ABC text is not hearing the music. Text-only critics are fair on structure (repetition, phrasing, voice leading, idle parts) and weak on "does it sound good".
- Composition and orchestration teaching material is more useful than music criticism, which is mostly about performances and context.
- **Always check the critic against human ratings**, otherwise we end up optimising for the critic's taste.
- Ways to use it, easiest first: pick the best of several versions → give feedback for revising the plan or regenerating bars → provide a training signal.

### Decisions still open
- What "good" means: pick 2–3 measurable checks plus listening tests.
- Scope: start narrow (e.g. solo piano or lead sheets) before full ensembles?
- Licensing: the full dataset is non-commercial only. For anything commercial, use only the MIT subsets (PDMX, SymphonyNet) and check the license on the weights.

---

## Files in `my_experiments/`
| File | What |
|---|---|
| `my_prompts.json` | 4 test prompts with plans (ids 101–104) |
| `my_prompts_shifted.json` | Same plans with bar numbers lowered by 1 (ids 201–204) |
| `trial_prompts.json` | 40-piece bar-numbering trial |
| `check_plan.py` | Compare a score against its plan (bars, key, time signature, range, chord share, silent parts, repeated bars). Optional OFFSET argument. |
| `compare_trial.py` | Aggregate results for the bar-numbering trial |
| `check_results*.txt`, `trial_results.txt` | Results |
| `outputs/`, `trial_outputs/`, `listen/` | Generated scores, MIDI and MP3 (gitignored; regenerate as needed) |
