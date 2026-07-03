---
name: audio-transcription
description: Set up and troubleshoot audio transcription / speech-to-text pipelines with OpenAI Whisper. Covers installation pitfalls, model setup, GPU configuration, and common errors.
category: media
---

# Audio Transcription (Whisper)

Set up and troubleshoot speech-to-text pipelines using OpenAI Whisper.

## Pitfall: `pip install whisper` is WRONG

**PyPI has a name-squatted package called `whisper` that is NOT OpenAI's Whisper.** Installing it gives you a dummy package with no `load_model()` function, producing:

```
AttributeError: module 'whisper' has no attribute 'load_model'
```

**Always install the correct package:**

```bash
# Wrong (installs the squatted package):
pip install whisper

# Correct:
pip install openai-whisper
```

If you already have the wrong package installed, remove it first:

```bash
pip uninstall whisper -y
pip install openai-whisper
```

In `requirements.txt`, write `openai-whisper`, never `whisper`.

## Dependencies

- `openai-whisper` — the official OpenAI Whisper package
- `torch` with CUDA — for GPU acceleration (installed automatically with openai-whisper)
- `ffmpeg` — required for audio file processing

## Model Management

Whisper models are downloaded on first use or can be pre-downloaded:

```python
import whisper
model = whisper.load_model("medium")  # tiny, base, small, medium, large, turbo
```

For offline use, place the `.pt` file locally and pass the path:

```python
model = whisper.load_model("/path/to/medium.pt")
```
