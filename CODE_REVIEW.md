# Code Review: cuesheet-creator (Merged — Round 3)

**Reviewers**: Vincent (AI) + 2 External Reviewers
**Date**: 2026-04-07
**Version**: 1.4.0 (from 1.3.0)
**Scope**: Full codebase — scripts, templates, tests, CI

---

## Changes Applied in v1.4.0

### From Round 1 (commit a0cdd20)
- P0: Fixed `missing_keyframes` NameError in `cmd_build_xlsx`
- P1: Created shared `validate_temp_marker_coverage()` function
- P1: Removed unused `sampled_frames` param from `compute_block_continuity`
- P1: Added try/finally for VideoCapture and thumbnail cleanup
- P2: Removed dead `_ensure_templates_loaded()`, fixed indentation

### From Round 2 (this commit)
- **export-md now uses `evaluate_delivery_readiness()`** — same delivery verdict as build-xlsx and validate-cue-json. No more silent export of unconfirmed temp names.
- **`validate_temp_marker_coverage()` is now template-aware** — reads `naming_field=true` from template metadata instead of hardcoding (scene, characters, location). Custom template naming fields are now properly validated.
- **`naming_category` metadata** added to template columns — custom templates can specify whether a naming field belongs to characters/scenes/props. Default fallback changed from "scenes" to "props" (less harmful).
- **All paths in `analysis.json` are now relative to out_dir** — `sampled_frames[].image_path`, `scene_candidates[].image_path`, `agent_summary.keyframe_batches` all use portable relative paths.
- **Motion pre-analysis via phase correlation** — `scan-video` now runs a lightweight 4-frame phase-correlation analysis per block to classify `likely-static` / `likely-camera-move` / `uncertain`. Pre-filled into `draft_fill.json` as `[motion-hint: ...]` hints. Saves LLM from guessing motion on single keyframes.
- **`--output-format json` added to all pipeline commands** — draft-from-analysis, build-xlsx, export-md, build-final-skeleton, apply-naming, derive-naming-tables, normalize-fill, merge-blocks, suggest-merges.
- **Template schema versioning** — `schema_version` field added to all built-in templates (v2). `validate_template_json` checks version compatibility. Future template schema changes can be detected.
- **`pyproject.toml`** with extras: `.[scene]`, `.[asr]`, `.[ocr]`, `.[all]`, `.[dev]`. Console entry point: `cuesheet-creator`.
- **GitHub Actions CI** — tests on 3 OS x 2 Python versions + ruff lint + template validation.
- **P3 cleanups**: removed useless `--validate` flag from save-template, fixed `PILImage.LANCZOS` deprecation, fixed f-strings without placeholders, fixed same-line imports.

---

## Remaining Items

### Deferred: Monolith split
The physical file split (4600 lines into ~11 modules) is deferred to a separate commit. All behavioral fixes are shipped first to avoid compounding risk. Recommended split order:
1. `cc/validation.py` — delivery readiness, temp marker coverage
2. `cc/templates.py` — registry, schema, naming metadata
3. `cc/exporters/xlsx.py`, `cc/exporters/markdown.py`
4. `cc/scan.py`, `cc/merge.py`
5. `cc/cli.py` — argparse + main

### Future Enhancements
- `analysis.json` compact/raw split for large videos
- Template schema documentation
- Enhanced motion analysis (optical flow for directional detection)
- shot_size/angle mechanical pre-fill candidates

---

## Test Results

```
48 passed, 0 failed out of 48 tests.
```
