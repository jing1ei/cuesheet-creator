# cuesheet-creator

Turn a single video into a "discussable, confirmable, deliverable" cue sheet — designed for directors, producers, and music supervisors who need to collaborate on shot blocks rather than wade through per-cut shot lists.

## Who is this for

| Audience | How they use it |
|---|---|
| **LLM agents / AI assistants** | Primary consumer — reads SKILL.md, runs CLI commands, fills in content |
| **Pipeline TDs / technical artists** | Integrate into production pipelines, automate with scripts |
| **Technical producers / supervisors** | Run directly via CLI, review and confirm outputs |
| **Directors / composers / non-technical team** | Review the *outputs* (Excel, Markdown) — they don't need to install or run anything themselves |

> **In short**: Technical users and agents run the tool. Creative leads review the deliverables.

## What it does

1. **Scans** a video → extracts keyframes, detects scene cuts, optionally runs ASR/OCR
2. **Generates** a template-differentiated draft (production / music-director / script)
3. **Gates** on naming confirmation — temp names never silently become final
4. **Exports** to Excel (with embedded keyframe screenshots) and Markdown

## Installation

### From source (recommended for development)

```bash
git clone https://github.com/jing1ei/cuesheet-creator.git
cd cuesheet-creator
pip install -e ".[dev]"
```

### As a package

```bash
pip install .
cuesheet-creator --version
```

### Optional extras

```bash
pip install ".[all]"       # scene detection + ASR + OCR (primary engine)
pip install ".[scene]"     # scene detection only
pip install ".[asr]"       # ASR only
pip install ".[ocr]"       # OCR primary engine only
```

> **Note**: `.[all]` installs scene + ASR + primary OCR (rapidocr). Alternative OCR engines (easyocr, paddleocr) are heavier — install them manually or use `prepare-env --mode install-ocr-extra` if needed.

## Quick Start

```bash
# 1. Check environment (no installs)
cuesheet-creator prepare-env --mode check-only --out-dir ./output

# 2. Install FFmpeg (if not already on PATH)
cuesheet-creator install-ffmpeg

# 3. Install required Python packages
cuesheet-creator prepare-env --mode install-required --out-dir ./output

# 4. Scan a video
cuesheet-creator scan-video --video "path/to/video.mp4" --out-dir ./output

# 5. Generate draft skeleton
cuesheet-creator draft-from-analysis \
    --analysis-json ./output/analysis.json \
    --output ./output/cue_sheet.md \
    --template production
```

> **FFmpeg**: On Windows, `cuesheet-creator install-ffmpeg` auto-downloads FFmpeg from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) with progress display. On macOS/Linux, use your package manager (`brew install ffmpeg` / `sudo apt install ffmpeg`). See [dependency-setup.md](references/dependency-setup.md) for details.

> **Running from source** (without pip install): Replace `cuesheet-creator` with `python scripts/cuesheet_creator.py` in all commands above.

## Prerequisites

- **Python >= 3.10**
- **ffmpeg / ffprobe** (auto-downloadable on Windows via `install-ffmpeg`; see [dependency-setup.md](references/dependency-setup.md))
- Core packages: `opencv-python-headless`, `numpy`, `Pillow`, `openpyxl` (auto-installed by `prepare-env`)
- Optional: `scenedetect`, `faster-whisper`, `rapidocr-onnxruntime`

> **Tip**: Use a virtual environment (`python -m venv .venv`) to keep dependencies isolated.

## Templates

| Template | Audience | Focus |
|---|---|---|
| `production` (default) | Director, producer, art, cinematography | Camera language, cross-dept coordination |
| `music-director` | Composer, scoring team | Mood progression, rhythm, instrumentation |
| `script` | Writers, story discussion | Narrative events, characters, locations |

Custom templates: save a JSON file via `save-template` (see `show-template --name production` for structure).

## Workflow Overview

```
Video → scan-video → analysis.json + keyframes/
     → draft-from-analysis → cue_sheet.md + draft_fill.json
     → LLM fills remaining fields in draft_fill.json
     → normalize-fill --fix → standardize enums, strip hint prefixes
     → derive-naming-tables → naming_tables.json
     → Naming confirmation gate (user/director confirms temp: names)
     → suggest-merges → suggested merge plan (auto-scored continuity)
     → LLM reviews merge suggestions for narrative boundaries
     → merge-blocks (optional) → merged blocks
     → build-final-skeleton → final_cues.json
     → validate-cue-json (--check-files recommended)
     → build-xlsx + export-md → final deliverables
```

## Command Reference

| Command | Purpose |
|---|---|
| `prepare-env` | One-command env check + optional install + recheck |
| `selfcheck` | Standalone environment check |
| `install-deps` | Install missing Python packages (`--include-optional all\|scene\|asr\|ocr\|ocr-extra\|everything`) |
| `install-ffmpeg` | Auto-download FFmpeg essentials build (Windows; shows download progress) |
| `scan-video` | Extract frames + scene detection + visual features + optional ASR/OCR |
| `draft-from-analysis` | Generate draft skeleton + JSON fill-in file with auto-prefilled fields |
| `suggest-merges` | Auto-compute continuity scores, output suggested merge plan |
| `merge-blocks` | Execute block merging from a reviewed merge plan |
| `build-final-skeleton` | Generate `final_cues.json` from draft_fill.json or merged blocks |
| `apply-naming` | Batch-apply naming overrides (`--dry-run` supported) |
| `derive-naming-tables` | Scan filled JSON for `temp:` markers → naming confirmation tables |
| `normalize-fill` | Normalize/lint LLM-filled JSON (`--fix` to auto-apply) |
| `validate-cue-json` | Structural + delivery readiness validation |
| `export-md` | Generate Markdown final from `final_cues.json` |
| `build-xlsx` | Generate Excel final with embedded keyframes |
| `list-templates` | List all available templates |
| `show-template` | Show full details of a template |
| `save-template` | Validate and save a custom template |
| `delete-template` | Delete a custom template |

Run `cuesheet-creator <command> --help` for detailed options.

### Flags for automation / CI

| Flag | Available on | Effect |
|---|---|---|
| `--fail-on-missing-required` | `selfcheck` | Non-zero exit if blocking issues exist |
| `--fail-on-blocking` | `prepare-env` | Non-zero exit if blocking issues remain after install |
| `--fail-on-delivery-gap` | `build-xlsx`, `export-md` | Non-zero exit if `delivery_ready: NO` |
| `--output-format json` | Most commands | Machine-readable JSON output |
| `--dry-run` | `install-deps`, `prepare-env`, `apply-naming` | Preview without writing |

### ASR options

| Flag | Default | Notes |
|---|---|---|
| `--asr` | off | Enable speech recognition |
| `--asr-model` | `base` | Model size: `tiny` / `base` / `small` / `medium` / `large-v3` |
| `--asr-device` | `auto` | `auto` / `cpu` / `cuda` — auto uses GPU if available |
| `--asr-compute-type` | `auto` | `auto` / `int8` / `float16` — auto selects based on device |

## Demo Output

The `assets/` directory contains structural samples:

- [`final_cues.sample.json`](assets/final_cues.sample.json) — Final cue sheet JSON structure
- [`naming_overrides.sample.json`](assets/naming_overrides.sample.json) — Naming override format
- [`merge_plan.sample.json`](assets/merge_plan.sample.json) — Block merge plan format

## Reference Files

| File | Purpose |
|---|---|
| [`SKILL.md`](SKILL.md) | Full workflow definition (agent entry point) |
| [`references/dependency-setup.md`](references/dependency-setup.md) | Detailed environment setup |
| [`references/field-templates.md`](references/field-templates.md) | Field definitions per template |
| [`references/review-checklist.md`](references/review-checklist.md) | Delivery checklist |
| [`references/spec.md`](references/spec.md) | Internal design notes |

## License

Licensed under the [Apache License 2.0](LICENSE).
