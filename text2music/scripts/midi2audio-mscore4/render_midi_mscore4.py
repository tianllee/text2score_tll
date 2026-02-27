#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class AudioFormat:
    ext: str
    ffmpeg_args: tuple[str, ...]


AUDIO_FORMATS: dict[str, AudioFormat] = {
    "mp3_192k": AudioFormat(ext="mp3", ffmpeg_args=("-c:a", "libmp3lame", "-b:a", "192k")),
    "mp3_128k": AudioFormat(ext="mp3", ffmpeg_args=("-c:a", "libmp3lame", "-b:a", "128k")),
    "wav_44k": AudioFormat(ext="wav", ffmpeg_args=("-c:a", "pcm_s16le", "-ar", "44100")),
    "wav_22k": AudioFormat(ext="wav", ffmpeg_args=("-c:a", "pcm_s16le", "-ar", "22050")),
    "wav_16k": AudioFormat(ext="wav", ffmpeg_args=("-c:a", "pcm_s16le", "-ar", "16000")),
}


def collect_midi_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"Input path does not exist: {path}")
    files = sorted(
        p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in {".mid", ".midi"}
    )
    return files


def resolve_outputs(
    midi_files: list[Path], input_path: Path, output: Path, audio_ext: str
) -> list[Path]:
    if input_path.is_file():
        if output.is_dir():
            output.mkdir(parents=True, exist_ok=True)
            return [output / f"{midi_files[0].stem}.{audio_ext}"]
        if output.suffix.lower() == f".{audio_ext}":
            return [output]
        return [output.with_suffix(f".{audio_ext}")]

    if output.exists() and output.is_file():
        raise NotADirectoryError(f"Output must be a directory for batch input: {output}")

    output.mkdir(parents=True, exist_ok=True)
    return [
        output / midi_file.relative_to(input_path).with_suffix(f".{audio_ext}")
        for midi_file in midi_files
    ]


def run_musescore_render(
    mscore_bin: Path,
    midi_file: Path,
    out_wav_file: Path,
    sound_profile: Optional[str],
    home_dir: Path,
) -> int:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["MU_QT_QPA_PLATFORM"] = "offscreen"
    existing_rules = env.get("QT_LOGGING_RULES", "")
    suppress_rule = "qt.qml.typeregistration=false"
    env["QT_LOGGING_RULES"] = (
        f"{existing_rules};{suppress_rule}" if existing_rules else suppress_rule
    )
    env["HOME"] = str(home_dir)
    home_dir.mkdir(parents=True, exist_ok=True)

    cmd = [str(mscore_bin)]
    if sound_profile:
        cmd += ["--sound-profile", sound_profile]
    cmd += ["-o", str(out_wav_file), str(midi_file)]

    print(f"[render] {midi_file} -> {out_wav_file}")
    proc = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.stdout:
        print(proc.stdout.strip())
    return proc.returncode


def transcode_audio(
    ffmpeg_bin: str,
    in_wav_file: Path,
    out_file: Path,
    audio_format: AudioFormat,
    mono: bool,
) -> int:
    channels = "1" if mono else "2"
    cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(in_wav_file),
        "-ac",
        channels,
        *audio_format.ffmpeg_args,
        str(out_file),
    ]
    mode = "mono" if mono else "stereo"
    print(f"[encode] {in_wav_file} -> {out_file} ({mode})")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.stdout:
        print(proc.stdout.strip())
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render MIDI to audio using MuseScore 4 in offscreen mode."
    )
    parser.add_argument("input", help="Input .mid/.midi file or directory")
    parser.add_argument(
        "output",
        help="Output audio file (single input) or output directory (batch input)",
    )
    parser.add_argument(
        "--mscore-bin",
        default="./.muse4/musescore4/squashfs-root/bin/mscore4portable",
        help="Path to MuseScore 4 binary",
    )
    parser.add_argument(
        "--sound-profile",
        default="MuseSounds",
        help='Sound profile to request, e.g. "MuseSounds" or "MuseScore Basic"',
    )
    parser.add_argument(
        "--audio-format",
        default="mp3_192k",
        choices=list(AUDIO_FORMATS.keys()),
        help="Output format preset: mp3_192k (default), mp3_128k, wav_44k, wav_22k, wav_16k",
    )
    parser.add_argument(
        "--mono",
        action="store_true",
        help="Save output as mono. Default is stereo.",
    )
    parser.add_argument(
        "--home-dir",
        default="./.home",
        help="HOME directory used by MuseScore runtime",
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    mscore_bin = Path(args.mscore_bin).resolve()
    home_dir = Path(args.home_dir).resolve()
    audio_format = AUDIO_FORMATS[args.audio_format]

    if not mscore_bin.exists():
        print(f"MuseScore binary not found: {mscore_bin}", file=sys.stderr)
        return 2

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        print("ffmpeg not found in PATH. Install ffmpeg first.", file=sys.stderr)
        return 4

    try:
        midi_files = collect_midi_files(input_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    if not midi_files:
        print(f"No MIDI files found in: {input_path}", file=sys.stderr)
        return 3

    try:
        outputs = resolve_outputs(midi_files, input_path, output_path, audio_format.ext)
    except NotADirectoryError as exc:
        print(str(exc), file=sys.stderr)
        return 5
    failures = 0
    for midi_file, out_file in zip(midi_files, outputs):
        out_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_wav_path = tempfile.mkstemp(
            prefix=f".{midi_file.stem}_",
            suffix=".wav",
            dir=str(out_file.parent),
        )
        os.close(tmp_fd)
        tmp_wav = Path(tmp_wav_path)
        try:
            rc = run_musescore_render(
                mscore_bin=mscore_bin,
                midi_file=midi_file,
                out_wav_file=tmp_wav,
                sound_profile=args.sound_profile,
                home_dir=home_dir,
            )
            if rc != 0:
                failures += 1
                print(f"[error] MuseScore return code {rc} for {midi_file}", file=sys.stderr)
                continue

            rc = transcode_audio(
                ffmpeg_bin=ffmpeg_bin,
                in_wav_file=tmp_wav,
                out_file=out_file,
                audio_format=audio_format,
                mono=args.mono,
            )
            if rc != 0:
                failures += 1
                print(f"[error] ffmpeg return code {rc} for {midi_file}", file=sys.stderr)
                if out_file.exists():
                    out_file.unlink()
        finally:
            if tmp_wav.exists():
                tmp_wav.unlink()

    if failures:
        print(f"Completed with {failures} failure(s).", file=sys.stderr)
        return 10
    print(f"Rendered {len(midi_files)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
