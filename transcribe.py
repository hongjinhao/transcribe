#!/usr/bin/env python3
"""Transcribe an audio or video file with the xAI (Grok) Speech-to-Text API.

Anything that isn't already an .mp3 (video, .mpeg, .m4a, .wav, ...) is first
converted with ffmpeg to a small speech-optimised MP3 (mono, 16 kHz, 64 kbps)
saved next to the input, then uploaded.

Usage:
    (put XAI_API_KEY=xai-... in .env next to this script)
    python3 transcribe.py "interview.mp4" --diarize    # -> interview.mp3 + interview.md
    python3 transcribe.py "audio.mpeg"                 # -> audio.mp3 + audio.md
    python3 transcribe.py "audio.mpeg" -o out.txt      # plain text output
    python3 transcribe.py "interview.mp4" --extract-only   # just make interview.mp3
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import requests

API_URL = "https://api.x.ai/v1/stt"
PAUSE_BREAK = 2.0  # seconds of silence that starts a new paragraph

# Speech-to-text models work at 16 kHz mono internally, so anything more is
# wasted upload. 64 kbps MP3 at 16 kHz mono is transparent for speech and
# comes to ~0.5 MB per minute (~29 MB per hour).
SAMPLE_RATE = 16000
BITRATE = "64k"


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:  # fallback: pip install imageio-ffmpeg (bundles a static ffmpeg)
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg not found. Install it with:  sudo apt install ffmpeg")


def to_audio(src: Path, force: bool = False) -> Path:
    """Extract/convert src to a speech-optimised MP3 next to it; return its path."""
    dst = src.with_suffix(".mp3")
    if dst == src:  # already an mp3
        return src
    if not force and dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        print(f"Using existing {dst.name}")
        return dst
    print(f"Converting {src.name} -> {dst.name} (mono, {SAMPLE_RATE // 1000} kHz, {BITRATE}bps MP3)...")
    cmd = [
        find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-stats", "-y",
        "-i", str(src),
        "-map", "0:a:0",          # first audio track only; drops video
        "-ac", "1",               # mono
        "-ar", str(SAMPLE_RATE),  # 16 kHz
        "-c:a", "libmp3lame", "-b:a", BITRATE,
        str(dst),
    ]
    if subprocess.run(cmd).returncode != 0:
        dst.unlink(missing_ok=True)
        sys.exit(f"ffmpeg failed to convert {src}")
    print(f"Saved {dst} ({dst.stat().st_size / 1e6:.1f} MB)")
    return dst


def load_dotenv(path: Path = Path(__file__).with_name(".env")) -> None:
    """Load KEY=value lines from .env next to this script (existing env vars win)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.removeprefix("export ").strip()
        os.environ.setdefault(k, v.strip().strip("'\""))


def ts(seconds: float) -> str:
    s = int(seconds)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def paragraphs(words, diarize):
    """Group words into paragraphs on speaker change or long pause."""
    paras, cur = [], None
    for w in words:
        spk = w.get("speaker") if diarize else None
        new = (
            cur is None
            or (diarize and spk != cur["speaker"])
            or w["start"] - cur["end"] > PAUSE_BREAK
        )
        if new:
            cur = {"speaker": spk, "start": w["start"], "end": w["end"], "words": []}
            paras.append(cur)
        cur["words"].append(w["text"])
        cur["end"] = w["end"]
    return paras


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", help="path to the audio or video file")
    ap.add_argument("-o", "--output", help="output path (.md or .txt); default: <audio>.md")
    ap.add_argument("-l", "--language", help="language code, e.g. en, zh, es (default: auto-detect)")
    ap.add_argument("--diarize", action="store_true", help="label different speakers")
    ap.add_argument("--keep-json", action="store_true", help="also save the raw API response")
    ap.add_argument("--extract-only", action="store_true", help="only convert to MP3, don't transcribe")
    ap.add_argument("--reconvert", action="store_true", help="redo the conversion even if the MP3 exists")
    args = ap.parse_args()

    src = Path(args.audio)
    if not src.exists():
        sys.exit(f"File not found: {src}")
    out = Path(args.output) if args.output else src.with_suffix(".md")
    audio = to_audio(src, force=args.reconvert)
    if args.extract_only:
        return

    load_dotenv()
    key = os.environ.get("XAI_API_KEY")
    if not key or key == "xai-paste-your-key-here":
        sys.exit("XAI_API_KEY is not set. Put your key in the .env file next to transcribe.py.")

    # Option fields must come before the file in the multipart body;
    # requests sends `data` fields first, then `files`.
    data = [("model", "grok-voice-transcribe-2.0")]
    if args.language:
        data += [("language", args.language), ("format", "true")]
    if args.diarize:
        data.append(("diarize", "true"))

    size_mb = audio.stat().st_size / 1e6
    print(f"Uploading {audio.name} ({size_mb:.1f} MB) — this can take a few minutes...")
    with audio.open("rb") as f:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {key}"},
            data=data,
            files={"file": (audio.stem + ".mp3", f, "audio/mpeg")},
            timeout=1800,
        )
    if not resp.ok:
        sys.exit(f"API error {resp.status_code}: {resp.text}")
    result = resp.json()

    if args.keep_json:
        out.with_suffix(".json").write_text(json.dumps(result, indent=2, ensure_ascii=False))

    words = result.get("words") or []
    paras = paragraphs(words, args.diarize) if words else []
    markdown = out.suffix.lower() == ".md"

    lines = []
    if markdown:
        lines += [
            f"# Transcript: {src.name}",
            "",
            f"- Language: {result.get('language', 'unknown')}",
            f"- Duration: {ts(result.get('duration', 0))}",
            "",
            "---",
            "",
        ]
    if paras:
        for p in paras:
            text = " ".join(p["words"])
            label = f"Speaker {p['speaker']}" if p["speaker"] is not None else ""
            if markdown:
                head = f"**[{ts(p['start'])}]{' ' + label if label else ''}:**"
                lines += [f"{head} {text}", ""]
            else:
                lines += [f"[{ts(p['start'])}]{' ' + label if label else ''} {text}", ""]
    else:
        lines.append(result.get("text", ""))

    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Done. Saved transcript to {out}")


if __name__ == "__main__":
    main()
