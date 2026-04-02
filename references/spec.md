# cuesheet-creator Internal Design Notes

> **This file is an internal design document and is NOT used as a runtime reference.** The sole runtime entry point is `SKILL.md`.

## Three-layer analysis model (design goal)

### Layer 1: Structure

Goal: Build the video skeleton.

Current status: **Implemented** (scan-video).

Output: duration, resolution/FPS, audio track info, auto scene candidates, keyframe sampling, coarse segmentation.

### Layer 2: Recognition

Goal: Identify objective content.

Current status: **LLM fills in based on keyframes.** ASR/OCR now integrated into scan-video as optional flags.

Output: characters, scene setups, props, on-screen text/logo/UI, dialogue/narration/lyrics.

### Layer 3: Interpretation

Goal: Generate director/production/music supervisor actionable information.

Current status: **LLM executes based on inference rules in SKILL.md.**

Output: block function, dominant camera language, mood progression, music suggestions, production coordination points.

## Maturity roadmap

### v1 (current)

- Single video
- Environment check
- Visual analysis (scenedetect with histogram fallback)
- LLM fills recognition and interpretation layers
- Optional ASR / OCR (integrated into scan-video)
- Keyframe sharpness scoring
- Draft → confirm → final
- Excel + keyframe screenshots + Markdown sync

### v2

- Enhanced naming library and project glossary
- More robust keyframe scoring (composition centrality, face detection)
- Music supervisor enhanced template
- Batch processing

### v3

- Cross-video unified naming
- Handoff suite (cue sheet + music brief + art highlights)
- Revision tracking (diff between draft and final)

## Design decision records

### Why shot blocks instead of per-cut

A per-cut shot list isn't useful in early production — 20 reverse shots in a dialogue scene don't need individual discussion. Shot blocks merged by narrative function are the right granularity for cross-department discussions.

### Why three templates

Directors need "what's the camera language here," scoring teams need "where does the mood shift," producers need "what requires cross-department alignment." Mixing them overloads everyone.

### Why naming confirmation needs its own gate

In real production, incorrect names leaking into finals is extremely common (especially during trailer phase when characters may not have official names yet). Without explicit confirmation, temp names become "fact" through propagation.
