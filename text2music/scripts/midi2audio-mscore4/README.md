# MuseScore 4 + Muse Sounds Headless Rendering

This repository provides a reproducible workflow to:
- install MuseScore Studio 4 in this workspace
- install Muse Sounds Manager
- render `.mid/.midi` to audio in headless mode

## Files

- `setup_mscore4_musesounds.sh`: full install/bootstrap script
- `manual_install/run_mscore4_headless.sh`: helper wrapper for headless MuseScore 4
- `manual_install/run_musesounds_manager.sh`: helper wrapper for Muse Sounds Manager
- `manual_install/install_musesounds_headless.sh`: headless installer by library IDs
- `manual_install/verify_musesounds_ready.sh`: checks whether MuseSounds is actually installed
- `render_midi_mscore4.py`: Python renderer (single file or batch)
- `musesounds_library_ids.tsv`: discovered valid MuseSounds IDs


## Install (auto)

Run setup:

```bash
chmod +x ./setup_mscore4_musesounds.sh
./setup_mscore4_musesounds.sh
```

By default, setup now also runs headless MuseSounds installation for the resolved library set in this project.

## Usage

Single MIDI file:

```bash
python3 ./render_midi_mscore4.py input.mid output.mp3 --sound-profile "MuseSounds"
```

Batch directory:

```bash
python3 ./render_midi_mscore4.py ./midi_dir ./audio_dir --audio-format wav_44k --sound-profile "MuseSounds"
```

Batch mode scans subfolders recursively and recreates the same folder structure under the output directory.

Fallback profile (no MuseSounds dependency):

```bash
python3 ./render_midi_mscore4.py input.mid output.mp3 --sound-profile "MuseScore Basic"
```

Mono output:

```bash
python3 ./render_midi_mscore4.py input.mid output.mp3 --mono
```

`--audio-format` presets:

| Preset | Format details |
| --- | --- |
| `mp3_192k` (default) | MP3, 192 kbps CBR |
| `mp3_128k` | MP3, 128 kbps CBR |
| `wav_44k` | WAV PCM 16-bit, 44.1 kHz |
| `wav_22k` | WAV PCM 16-bit, 22.05 kHz |
| `wav_16k` | WAV PCM 16-bit, 16 kHz |

Filename behavior:
- Single-file mode: output extension is auto-adjusted to match `--audio-format` (for example, `out.wav` becomes `out.mp3` with default `mp3_192k`)
- Batch mode: output files are written with extension derived from `--audio-format` (`.mp3` or `.wav`)
- Channel mode: default is stereo, add `--mono` to force mono output

<details>
<summary><strong>Install (manual)</strong></summary>

Optional controls for setup stage:

- Disable auto library install:

```bash
INSTALL_MUSESOUNDS=0 ./setup_mscore4_musesounds.sh
```

- Override library IDs:

```bash
MUSESOUNDS_IDS="<id1,id2,...>" ./setup_mscore4_musesounds.sh
```

If you want to use Manager UI directly:

```bash
./manual_install/run_musesounds_manager.sh
```

Then:
1. Log in
2. Install the MuseSounds libraries you want

Alternative headless path if you already know library IDs:

```bash
chmod +x ./manual_install/install_musesounds_headless.sh
./manual_install/install_musesounds_headless.sh <id1,id2,...>
```

Discovered IDs are listed in:

```bash
cat ./musesounds_library_ids.tsv
```

Example install of core MuseSounds set:

```bash
./manual_install/install_musesounds_headless.sh \
0013e17f-55dd-42fb-bba3-110337a64849,e4a60bd8-4a44-4c5a-ad3a-3bccf48a5f64,f2fbf84c-06da-45c9-be57-f2722d9fd363,fbd15858-9185-41ed-918b-8e360a698dbe,d6353666-c534-4c48-833e-c86f0926656f,6a0d49c3-df4b-4f86-ad8f-61c131b7428c
```

Verify MuseSounds is ready:

```bash
chmod +x ./manual_install/verify_musesounds_ready.sh
./manual_install/verify_musesounds_ready.sh
```

If verification says `NOT READY`, finish library installation in Muse Sounds Manager and run verify again.

</details>

## Direct CLI (without Python wrapper)

```bash
QT_QPA_PLATFORM=offscreen MU_QT_QPA_PLATFORM=offscreen ./manual_install/run_mscore4_headless.sh --sound-profile "MuseSounds" -o output.wav input.mid
```

## Notes

- Headless rendering is done with:
  - `QT_QPA_PLATFORM=offscreen`
  - `MU_QT_QPA_PLATFORM=offscreen`
- MuseSounds libraries can be installed headlessly via `manual_install/install_musesounds_headless.sh` (Manager UI flow is optional).
