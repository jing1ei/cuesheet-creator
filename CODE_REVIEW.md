# Code Review: cuesheet-creator (Merged)

**Reviewers**: Vincent (AI) + External Reviewer
**Date**: 2026-04-07
**Commit**: `14f7cff` (with fixes applied)
**Scope**: Full codebase — 4456 LOC main script, 868 LOC SKILL.md, templates, tests, references

---

## Fixes Applied

### P0: `missing_keyframes` NameError in `cmd_build_xlsx` — FIXED
- Added `missing_keyframes: list[str] = []` initialization
- Added regression test `test_build_xlsx_missing_keyframe_does_not_crash`
- Both reviewers independently identified this

### P1: Temp marker validation too weak — FIXED
- Created shared `validate_temp_marker_coverage(row)` function
- Now checks per-marker: each `temp: XYZ` in naming fields must have a matching substring in `needs_confirmation`
- Previously only checked if `needs_confirmation` was empty (a generic "check later" would pass)
- Updated `evaluate_delivery_readiness`, `cmd_validate_cue_json`, and `cmd_normalize_fill` to use the shared function
- Added 3 new tests: `test_validate_temp_marker_requires_matching_needs_confirmation`, `test_validate_temp_marker_passes_when_markers_mentioned`, `test_delivery_readiness_temp_marker_gap_blocks_export`

### P1: `suggest-merges` docs/implementation drift — FIXED
- Removed unused `sampled_frames` parameter from `compute_block_continuity()`
- Removed unused `sampled_frames` load in `cmd_suggest_merges`
- Rewrote docstring to accurately describe what the function does: heuristic based on pre-computed visual_features, candidate_score, and ASR continuity — NOT frame-level histogram comparison
- Comment about "histogram distance between keyframes via sampled_frames" replaced with accurate description

### P1: Resource leaks — FIXED
- `cv2.VideoCapture` in `cmd_scan_video`: wrapped frame sampling loop in try/finally to ensure `capture.release()` on any exception
- Thumbnail files in `cmd_build_xlsx`: wrapped `wb.save()` in try/finally to clean up `.thumb_*.jpg` even if save fails

### P2: Dead code and style — FIXED
- Removed `_ensure_templates_loaded()` (defined but never called; templates loaded eagerly at module init)
- Fixed inconsistent 8-space indentation in `cmd_save_template` error handling block

---

## Remaining Issues (Not Fixed Yet)

### P2: Single 4456-line monolithic file
Both reviewers agree this should be split by responsibility. Suggested layout:
```
cc/
  templates.py, env.py, scan.py, draft.py, naming.py,
  normalize.py, merge.py, validation.py,
  exporters/{xlsx,markdown}.py, cli.py
```
**Effort**: ~half day. Gets more painful the longer you wait.

### P2: No pyproject.toml / CI / extras
Currently not installable as a proper Python package. Missing:
- `pyproject.toml` with `.[scene]`, `.[asr]`, `.[ocr]`, `.[all]` extras
- CI pipeline (lint + test)
- `python -m cuesheet_creator` entry point

### P2: Test coverage gaps
48 tests pass, but key failure paths are still untested:
- `cmd_scan_video` has zero test coverage (most complex command)
- `cmd_export_md` untested
- CLI-level smoke test (real command chain) missing

### P2: `analysis.json` uses absolute paths in `sampled_frames` / `scene_candidates`
Breaks portability when moving output directories between machines. `agent_summary` already uses relative paths correctly — the full arrays should too.

### P2: `analysis.json` grows large for long videos
External reviewer suggests a `--compact` mode or splitting into `analysis.json` (summary) + `analysis.raw.json` (full frame data).

### P2: Template schema versioning
No version field on templates. When custom templates are shared across teams, schema drift will cause silent failures. Should add version + formal schema docs.

### P3: `--output-format json` missing on several commands
`draft-from-analysis`, `merge-blocks`, `apply-naming`, `derive-naming-tables`, `normalize-fill`, `export-md`, `build-final-skeleton` lack structured JSON output mode. Blocks pipeline/agent integration.

### P3: `--verbose` / `--quiet` flags missing
No way to control output verbosity for CI/pipeline use.

### P3: Error semantics need grading
Not always clear to the user whether an error is "blocks export" vs "degraded but can continue". The `validate-cue-json` output should explicitly categorize.

### P3: `--validate` flag on `save-template` is always True
`save_tmpl.add_argument("--validate", action="store_true", default=True, ...)` — the flag does nothing. Either remove it or add `--no-validate` for power users.

### P3: SKILL.md step numbering is confusing
Step 5 (merge) says "proceed to Step 4" — creates a loop in the document flow. Should renumber or add a flow diagram.

### P3: `PILImage.LANCZOS` deprecation path
Pillow >= 10 prefers `PIL.Image.Resampling.LANCZOS`. Works today but may warn in future Pillow versions.

---

## Mechanical vs. LLM Boundary Assessment

### What's correctly scripted (both reviewers agree)
- Scene detection, keyframe extraction, sharpness scoring
- Visual feature computation (brightness/contrast/saturation/hue)
- ASR transcription, OCR text detection
- Timecode parsing, enum normalization, naming replacement
- Template validation, delivery readiness evaluation
- Continuity scoring for merge suggestions

### What's correctly LLM-delegated (both reviewers agree)
- Mood inference, narrative function tagging
- Block merge review (Tier 1/2/3 semantic rules)
- Character/scene/prop identification from keyframes
- Music note suggestions, custom template discovery

### Where the boundary could improve

**motion field** (external reviewer P1, Vincent concurs with lighter approach):
- motion (push-in/pull-out/pan/tracking/handheld/static) is time-domain information
- Single keyframe cannot reliably distinguish these
- External reviewer suggests optical flow; Vincent suggests cheaper phase-correlation on 3-5 frames per block
- Minimum viable: flag `likely-static` vs `uncertain` to skip 40-60% of blocks from LLM visual judgment
- Target: v1.4 enhancement

**shot_size / angle pre-fill** (external reviewer suggestion):
- Could add low-confidence mechanical candidates based on face detection + frame composition heuristics
- Lower priority than motion since single-frame analysis is more reliable for these

---

## Test Results After Fixes

```
48 passed, 0 failed out of 48 tests.
```

New tests added:
1. `test_build_xlsx_missing_keyframe_does_not_crash` (P0 regression)
2. `test_validate_temp_marker_requires_matching_needs_confirmation`
3. `test_validate_temp_marker_passes_when_markers_mentioned`
4. `test_delivery_readiness_temp_marker_gap_blocks_export`

---

## Recommended Priority Order for Remaining Work

1. **Split the monolith** — gets harder every release
2. **Add pyproject.toml + CI** — unblocks contributors
3. **Relative paths in analysis.json** — portability fix
4. **motion pre-analysis** — biggest LLM token saving opportunity
5. **--output-format json on all commands** — pipeline integration
6. **Template versioning** — team collaboration safety
