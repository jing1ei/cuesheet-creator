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

## Quick Start (Windows)

```powershell
# 1. Check environment (no installs)
python scripts/cuesheet_creator.py prepare-env --mode check-only --out-dir ./output

# 2. If ffmpeg is missing: download from https://www.gyan.dev/ffmpeg/builds/
#    Extract to <this-folder>/tools/ffmpeg/ — cuesheet-creator auto-detects it.

# 3. Install required Python packages (when ready)
python scripts/cuesheet_creator.py prepare-env --mode install-required --out-dir ./output

# 4. Scan a video
python scripts/cuesheet_creator.py scan-video --video "path/to/video.mp4" --out-dir ./output

# 5. Generate draft skeleton
python scripts/cuesheet_creator.py draft-from-analysis --analysis-json ./output/analysis.json --output ./output/cue_sheet.md --template production
```

## Quick Start (macOS / Linux)

```bash
# 1. Install ffmpeg
brew install ffmpeg   # macOS
# sudo apt install ffmpeg   # Ubuntu/Debian

# 2. Check environment
python3 scripts/cuesheet_creator.py prepare-env --mode check-only --out-dir ./output

# 3. Install required Python packages
python3 scripts/cuesheet_creator.py prepare-env --mode install-required --out-dir ./output

# 4. Scan and draft (same as above)
```

## Prerequisites

- **Python >= 3.10**
- **ffmpeg / ffprobe** (not auto-installed — see [dependency-setup.md](references/dependency-setup.md))
- Core packages: `opencv-python-headless`, `numpy`, `Pillow`, `openpyxl` (auto-installed by `prepare-env`)
- Optional: `scenedetect`, `faster-whisper`, `rapidocr-onnxruntime`

> **Tip**: Use a virtual environment (`python -m venv .venv`) to keep dependencies isolated.

## Templates

| Template | Audience | Focus |
|---|---|---|
| `production` (default) | Director, producer, art, cinematography | Camera language, cross-dept coordination |
| `music-director` | Composer, scoring team | Mood progression, rhythm, instrumentation |
| `script` | Writers, story discussion | Narrative events, characters, locations |

## Workflow Overview

```
Video → scan-video → analysis.json (with agent_summary + visual_features) + keyframes/
     → draft-from-analysis → cue_sheet.md + draft_fill.json (auto-prefilled: ASR dialogue, confidence, mood hints, OCR)
     → LLM fills remaining fields in draft_fill.json
     → Naming confirmation gate
     → suggest-merges → suggested_merges.json (auto-scored continuity)
     → LLM reviews merge suggestions for narrative boundaries
     → merge-blocks (optional, using reviewed merge plan)
     → build-final-skeleton (accepts draft_fill.json directly) → final_cues.json
     → validate-cue-json
     → build-xlsx + export-md (Phase B final)
```

## Command Reference

| Command | Purpose |
|---|---|
| `prepare-env` | One-command env check + optional install + recheck |
| `selfcheck` | Standalone environment check |
| `install-deps` | Install missing Python packages |
| `scan-video` | Extract frames + scene detection + visual feature analysis + optional ASR/OCR |
| `draft-from-analysis` | Generate draft skeleton + JSON fill-in file with auto-prefilled fields |
| `suggest-merges` | **Auto-compute inter-block continuity scores** and output a suggested merge plan. LLM reviews for narrative boundaries before executing. Use `--threshold` to adjust sensitivity (default 0.65). |
| `merge-blocks` | Merge draft blocks based on a merge plan (validated) |
| `build-final-skeleton` | Generate final_cues.json from draft_fill.json, merged blocks, or analysis.json |
| `apply-naming` | Batch-apply naming overrides |
| `validate-cue-json` | Structural + delivery readiness validation (`--check-files` recommended before export) |
| `export-md` | Generate Markdown final from final_cues.json |
| `build-xlsx` | Generate Excel final with embedded keyframes |

Run `python scripts/cuesheet_creator.py <command> --help` for detailed options.

### Exit codes for automation

By default, `selfcheck` and `prepare-env` return exit code 0 even when the environment is not ready (so you can read the report). For CI or scripted workflows, use:

- `selfcheck --fail-on-missing-required` — returns non-zero if any blocking issue exists
- `prepare-env --fail-on-blocking` — returns non-zero if blocking issues remain after install

## Demo Output

The `assets/` directory contains structural samples showing the expected data formats:

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


Run `python scripts/cuesheet_creator.py --version` to check the installed version.

## License

Licensed under the [Apache License 2.0](LICENSE).
