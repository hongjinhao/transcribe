# transcribe

Transcribe audio or video files with the [xAI (Grok) Speech-to-Text API](https://docs.x.ai/), producing a timestamped Markdown (or plain-text) transcript with optional speaker labels.

Anything that isn't already an `.mp3` (video, `.mpeg`, `.m4a`, `.wav`, ...) is first converted with ffmpeg to a small speech-optimised MP3 (mono, 16 kHz, 64 kbps — about 29 MB per hour), saved next to the input, then uploaded.

## Requirements

- Python 3.9+
- [`requests`](https://pypi.org/project/requests/)
- ffmpeg — either on your `PATH` (`sudo apt install ffmpeg`) or via `pip install imageio-ffmpeg`
- An xAI API key

```bash
pip install requests
```

## Setup

Create a `.env` file next to `transcribe.py`:

```
XAI_API_KEY=xai-...
```

An `XAI_API_KEY` already set in your environment takes precedence. `.env` is gitignored.

## Usage

```bash
# Video with speaker labels -> interview.mp3 + interview.md
python3 transcribe.py interview.mp4 --diarize

# Audio -> audio.mp3 + audio.md
python3 transcribe.py audio.mpeg

# Plain-text output
python3 transcribe.py audio.mpeg -o out.txt

# Only extract the MP3, don't transcribe
python3 transcribe.py interview.mp4 --extract-only
```

### Options

| Option | Description |
| --- | --- |
| `-o`, `--output PATH` | Output file (`.md` or `.txt`). Default: `<input>.md` |
| `-l`, `--language CODE` | Language code, e.g. `en`, `zh`, `es`. Default: auto-detect |
| `--diarize` | Label different speakers |
| `--keep-json` | Also save the raw API response as `<output>.json` |
| `--extract-only` | Only convert to MP3; skip transcription |
| `--reconvert` | Redo the conversion even if an up-to-date MP3 exists |

## Output

Words are grouped into paragraphs, starting a new one on a speaker change (with `--diarize`) or after a pause of 2+ seconds:

```markdown
# Transcript: interview.mp4

- Language: en
- Duration: 45:12

---

**[00:00] Speaker 0:** Hi, thanks for joining today...

**[00:07] Speaker 1:** Thanks for having me...
```
