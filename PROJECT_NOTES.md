# Project Notes: Text2Score Extension

Last updated: 2026-11-22

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

### Known problems
- **Invalid ABC notation sometimes:** 2 of 40 trial pieces (both jazz trio) failed to convert, e.g. `^=e` (two accidentals on one note). The conversion script fails silently and the file is simply missing.
- Some parts rest for the whole piece; some bars repeat mechanically (the maracas in the example, `aaa aaa` in the jig).
- The jig melodies tend to be scale and arpeggio patterns.
- `xml2mid.py` only handles the numbered folder layout from batch runs.

---

## Where we left off and next steps

**Paused before:** listening to the 8 rendered pieces and rating them.
```bash
open ~/text2score/my_experiments/listen/*.mp3          # regenerate with mscore if missing (gitignored)
open -a "MuseScore 4" ~/text2score/my_experiments/outputs/10*/xml/*.xml
```

1. **Listen and rate (human).** For each piece, give a 1–10 score plus one line on what's wrong (boring melody, odd harmony, idle instrument, …). This shows what to fix first and is the first set of human ratings for checking an automatic critic.
2. **LLM critic experiment.** Claude rates the same 8 pieces from their ABC notation only, without seeing the human ratings; then compare the two sets. If they agree reasonably, use the critic in step 3. If not, try CLaMP3 (`text2music/scripts/clamp3.py`) or an audio-capable model.
3. **Generate several and keep the best.** Generate N candidates per prompt, discard any that fail to convert, score the rest with `check_plan.py` (and the critic, if it's validated), and keep the best. This fixes broken notation and loose plan-following.
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
