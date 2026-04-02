# Delivery Checklist

> Core checks are embedded in the SKILL.md "Delivery checklist" section. This file provides the full version.

## Phase A: Draft check

### Environment & input

- [ ] Confirmed video path, template, and whether to analyze specific segment only
- [ ] Confirmed install strategy (default `check-only`; never upgrade without explicit user permission)
- [ ] Completed environment check and recorded blocking / warning items
- [ ] Retained `prepare_env.json`

### Content

- [ ] Output video basic info (duration, resolution, FPS, audio tracks)
- [ ] Provided candidate segments and keyframe candidates
- [ ] Listed character / scene / prop summaries
- [ ] Provided standalone naming confirmation tables (characters, scenes, props — one each)
- [ ] Marked low-confidence items and pending questions
- [ ] If no ASR / OCR, explicitly stated degradation impact

## Phase B: Final check

- [ ] User confirmed template, or explicitly accepted "continue with temp names"
- [ ] Every row is a collaborative shot block, not a mechanical per-cut split
- [ ] Keyframe is a representative frame, not a mechanical first-frame
- [ ] Director / production / music supervisor perspectives not mixed
- [ ] Low-confidence content still has `confidence` / `needs_confirmation`
- [ ] Ran `validate-cue-json` and passed validation
- [ ] Markdown and Excel fields are consistent
- [ ] Excel has embedded keyframe screenshots
- [ ] If user requested, retained `analysis.json` and `final_cues.json`

## Failure fallback check

- [ ] When `ffmpeg` missing: stopped and provided install guidance
- [ ] When ASR missing: stated dialogue confidence is degraded
- [ ] When OCR missing: stated on-screen text layer is skipped
- [ ] Long video: produced structural draft first
- [ ] Cut detection anomaly: fell back to fixed-interval sampling + manual merge

## Recommended question groupings

### Group 1: Input & scope

- What is the video path?
- Analyze specific segment only?
- Draft first, or proceed directly to final?

### Group 2: Naming confirmation

- Do characters have official names?
- Do scenes / setups have internal project names?
- Do key props have standardized names?

### Group 3: Output preferences

- Prefer `production`, `music-director`, or `script`?
- Keep intermediate JSON?
- Enable ASR / OCR (if environment supports)?
