---
name: cuesheet-creator
description: Analyze a single video into a collaborative Cue Sheet draft with keyframe screenshots and an Excel deliverable. Suitable for PVs, trailers, cinematics, narrative clips, and game cutscenes that require coordination between directors, production, and music supervisors.

---

# cuesheet-creator

Turn a single video into a "discussable, confirmable, deliverable" cue sheet. The goal is not a mechanical cut list, but a shot block document that directors, producers, art, sound, and music teams can discuss together.

## When to trigger

- User provides a single video and wants a cue sheet, keyframe screenshots, or Excel deliverable.
- User wants structural analysis first, then one of three template outputs: production / music-director / script.
- User needs to confirm character, scene, and prop naming before generating final deliverables.
- User needs to capture video discussions into a reusable director/production/music collaboration document.

## When NOT to trigger

- Pure livestream recordings, meeting recordings, or surveillance footage where the user demands per-cut precision.
- User only wants subtitles, transcripts, or raw ASR text.
- User only wants a rough summary without shot, segment, or music information.

## v1 Scope

Single video → single cue sheet only. Not in v1: batch processing, merging multiple cue sheet versions, syncing to enterprise docs/spreadsheets, auto-generating scoring brief packages.

## Default deliverables

- `cue_sheet.md` — Markdown final
- `cue_sheet.xlsx` — Excel final (keyframe screenshots embedded for `production` template; `script` and `music-director` templates are text-focused without embedded images)
- `keyframes/` — Keyframe screenshot directory
- `audio.wav` — Extracted audio track (only when `--asr` is used; intermediate file, safe to delete after analysis)
- Optional intermediate files: `analysis.json`, `final_cues.json`

---

## Prerequisites

- **Python >= 3.10** (required; checked by `selfcheck`)
- **ffmpeg / ffprobe available either on PATH or from a local portable directory** (required; not auto-installed)
- Optional: `scenedetect`, `faster-whisper`, `rapidocr` / `easyocr` / `paddleocr` (may require first-run model downloads)

> **Install strategy**: `prepare-env` / `install-deps` auto-install packages with version constraints. Core package versions come from `requirements.txt`; optional component versions (scene/asr/ocr) are maintained in the script's `OPTIONAL_COMPONENTS` constant. For manual core install: `pip install -r requirements.txt`.

> **Windows / PowerShell note**: All `<video-path>` and `<out-dir>` arguments should be quoted if they contain spaces or special characters. If not running from the project root, use the full path to `scripts/cuesheet_creator.py`. Relative paths for `--video` and `--out-dir` are resolved from your current shell working directory, not the project directory.

> **Windows FFmpeg note**: To avoid touching system PATH, you can extract a portable FFmpeg build under `<skill-root>/tools/ffmpeg/`. cuesheet-creator will auto-detect either `<skill-root>/tools/ffmpeg/bin/ffmpeg.exe` or one nested release folder such as `<skill-root>/tools/ffmpeg/ffmpeg-7.x-essentials_build/bin/ffmpeg.exe`. You can also set `CUESHEET_CREATOR_FFMPEG_BIN_DIR` for the current shell.


---

## Mandatory principles

1. **Two-phase delivery**: Phase A draft first, then Phase B final. Do not skip Phase A; if user insists on immediate final, keep "temp-name" markers and unconfirmed columns.
2. **Temp-name protection**: Never write guessed names into the final. If user hasn't confirmed, continue but always keep "temp: xxx" markers visible.
3. **Shot block granularity**: Use "collaborative shot block" as the minimum row unit. Do not disguise output as a per-cut shot list.
4. **Perspective separation**: Keep director, production, and music supervisor perspectives separate. Do not blend them into a film-review paragraph.
5. **Long video protection**: For videos over 20 minutes, default to a structural draft first. Ask before doing full-detail expansion.
6. **Install safety**: When the user has not explicitly specified an install level, **never** auto-upgrade to any `install-*` mode. Default is always `check-only`. Even if the user says "set up my environment," confirm the exact install scope first.

---

## Workflow

### Step 0: Confirm input and delivery strategy

| Item | Default |
|---|---|
| Video path | (must be provided by user) |
| Output directory | `<video-dir>/<video-name>_cuesheet/` (same folder as the video) |
| Delivery phase | Draft first, then final |
| Output template | `production` |
| Analyze specific segment only | No |
| Keep intermediate JSON | Keep `analysis.json` |
| Install strategy | `check-only` |
| pip mirror | None (only if user specifies) |

Video length strategy:

- 0–8 min: Full analysis by default
- 8–20 min: Coarse cut first, then refine
- 20+ min: Structural draft first, adjust `--sample-interval`

### Step 1: Environment check

Detailed commands in `references/dependency-setup.md`.

Default:

```bash
python scripts/cuesheet_creator.py prepare-env --mode check-only --out-dir <out-dir>
```

Only when user **explicitly allows** auto-install:

```bash
python scripts/cuesheet_creator.py prepare-env --mode install-required --out-dir <out-dir>
```

Optional enhanced installs:

```bash
# Install scenedetect for better cut detection
python scripts/cuesheet_creator.py prepare-env --mode install-scene --out-dir <out-dir>

# Install ASR components
python scripts/cuesheet_creator.py prepare-env --mode install-asr --out-dir <out-dir>

# Install OCR components
python scripts/cuesheet_creator.py prepare-env --mode install-ocr --out-dir <out-dir>

# Install everything (required + scene + asr + ocr)
python scripts/cuesheet_creator.py prepare-env --mode install-all --out-dir <out-dir>
```

#### Step 1.5: FFmpeg confirmation checkpoint

> **This is a hard gate.** If ffmpeg / ffprobe are not found after Step 1, you MUST stop and guide the user through installation. Do NOT attempt to download or install FFmpeg automatically. Do NOT proceed to Step 2 until both `ffmpeg : OK` and `ffprobe: OK` appear in selfcheck output.

**Agent behavior when ffmpeg is MISSING:**

1. **Give the user exactly ONE instruction** — the simplest option for their platform (see below). Do NOT present multiple options at once.
2. **Wait** for the user to confirm they've done it.
3. **Re-run selfcheck** to verify.
4. **Only if that fails**, offer the next fallback option.

**Round 1 — give only this (one option per platform):**

| Platform | What to tell the user |
|---|---|
| **Windows** | "请从 https://www.gyan.dev/ffmpeg/builds/ 下载 **essentials build** 的 zip 文件，解压后把整个文件夹放到 `<skill-root>/tools/ffmpeg/` 下面（最终路径类似 `tools/ffmpeg/ffmpeg-7.x-essentials_build/bin/ffmpeg.exe`）。不需要改系统 PATH，cuesheet-creator 会自动找到它。放好后告诉我，我来验证。" |
| **macOS** | "请在终端运行 `brew install ffmpeg`，装完后告诉我，我来验证。" |
| **Linux** | "请运行 `sudo apt install ffmpeg`（或你发行版对应的命令），装完后告诉我，我来验证。" |

**After user confirms**, re-run:

```bash
python scripts/cuesheet_creator.py selfcheck
```

Look for `ffmpeg : OK [source]` and `ffprobe: OK [source]` in the output.

**Round 2 — only if Round 1 failed (user says they did it but selfcheck still shows MISSING):**

Troubleshoot in this order:

1. **Windows portable**: Did they extract to the right location? `<skill-root>/tools/ffmpeg/` should contain either `bin/ffmpeg.exe` directly or `<release-folder>/bin/ffmpeg.exe` one level down.
2. **macOS/Linux package install**: The install command might have succeeded but the current shell session doesn't see it yet. Tell the user: "请关闭当前终端窗口，重新打开一个新的，然后告诉我。"（Concrete action, not abstract "PATH" concepts.）
3. **Direct path override** (escape hatch — offer only if steps above didn't resolve):

```bash
python scripts/cuesheet_creator.py --ffmpeg-path /full/path/to/ffmpeg --ffprobe-path /full/path/to/ffprobe selfcheck
```

**Round 3 — only if user explicitly asks for alternatives:**

Offer package manager install: `winget install Gyan.FFmpeg` / `scoop install ffmpeg` / `choco install ffmpeg`. After install, tell the user: "请关闭当前 PowerShell 窗口，重新打开一个新窗口，然后告诉我——我会重新检查。"

**Key principle:** Never dump all options at once. One instruction → verify → next fallback only if needed.

Post-check rules:

- `ffmpeg` / `ffprobe` missing → **Stop**, provide install guidance as above.
- Required Python packages missing → Based on user choice, stop at check or continue installing.
- Optional ASR missing → Continue, but mark "dialogue confidence degraded."
- Optional OCR missing → Continue, skip on-screen text recognition.


### Step 2: Pre-analysis

```bash
python scripts/cuesheet_creator.py scan-video --video <video-path>
```

> **Output directory**: If `--out-dir` is not specified, outputs are written to `<video-dir>/<video-name>_cuesheet/` — a folder created next to the video file. The script prints the output directory path after completion. You can override with `--out-dir <custom-path>` if needed.

Optional enhancements (add as needed):

```bash
# Enable ASR speech recognition (requires faster-whisper)
python scripts/cuesheet_creator.py scan-video --video <path> --out-dir <dir> --asr --asr-model base

# Enable OCR text detection (requires rapidocr / easyocr / paddleocr)
python scripts/cuesheet_creator.py scan-video --video <path> --out-dir <dir> --ocr

# Analyze only a specific segment (useful for long videos)
python scripts/cuesheet_creator.py scan-video --video <path> --out-dir <dir> --start-time 00:05:00.000 --end-time 00:08:30.000

# Full-featured scan with clip range
python scripts/cuesheet_creator.py scan-video --video <path> --out-dir <dir> --asr --ocr --start-time 00:02:00.000 --end-time 00:10:00.000
```

**Scene detection strategy**: If PySceneDetect is available, automatically uses ContentDetector (more accurate, handles dissolves and slow transitions); otherwise falls back to histogram correlation detection. Use `--content-threshold` to adjust scenedetect sensitivity (default 27.0).

**Keyframe scoring**: Every frame gets a Laplacian sharpness score. In scenedetect mode, automatically selects the sharpest frame near each cut point as the representative frame.

Outputs `analysis.json` containing: video metadata, scene candidates, keyframe screenshots (with sharpness scores), draft block candidates, ASR speech segments (if enabled), OCR text detections (if enabled), analysis notes.

### Step 3: Form Phase A draft

**Two steps: generate skeleton first, then LLM fills in content.**

#### 3a. Generate skeleton draft

```bash
python scripts/cuesheet_creator.py draft-from-analysis --analysis-json <out-dir>/analysis.json --output <out-dir>/cue_sheet.md --template production
```

Skeleton includes: video info table, candidate segment table (time + cut reason), blank naming confirmation tables, pending questions list.

#### 3b. LLM content fill-in (critical step)

Read the skeleton draft and `keyframes/` screenshots. **For each shot block**, examine the corresponding keyframe and fill in using the following rules:

**Visual cue → field mapping rules:**

| You observe in the keyframe… | Field | Fill with |
|---|---|---|
| Subject fills >60% of frame, head to chin | `shot_size` | CU (close-up) |
| Subject fills ~40-60%, waist up | `shot_size` | MS (medium shot) |
| Subject fills <30%, full environment visible | `shot_size` | WS (wide shot) |
| Extreme distance, subject tiny or invisible | `shot_size` | EWS (extreme wide shot) |
| Camera moves from far to near or near to far | `motion` | push-in / pull-out |
| Camera moves horizontally following subject | `motion` | tracking / pan |
| Slight frame instability, wobble | `motion` | handheld |
| Completely still frame | `motion` | static |
| Viewing one character from behind another's shoulder | `angle_or_lens` | OTS (over-the-shoulder) |
| Looking up at subject from below | `angle_or_lens` | low angle |
| Looking down at subject from above | `angle_or_lens` | high angle |
| Straight-on, eye level, no tilt | `angle_or_lens` | front / eye-level |

**Mood inference rules:**

| Visual combination | `mood` tendency |
|---|---|
| Dark tones + low angle + slow motion | Heavy, oppressive, tense |
| Bright tones + wide shot + static | Open, calm, establishing |
| Close-up + handheld + fast cuts | Urgent, anxious, intense |
| Soft light + medium shot + slow push | Warm, intimate, expectant |
| High contrast + low angle + static | Authoritative, heroic, powerful |
| Backlight + silhouette + slow pull | Lonely, mysterious, farewell |

**Narrative function rules:**

| Feature | Block function |
|---|---|
| First wide/long shot of a new space | Establishing |
| Two+ characters in shot/reverse-shot or dialogue framing | Dialogue |
| Single close-up + spatial shift suggesting memory | Flashback |
| Slow-down or pause after a climactic action | Payoff / release |
| Music fading + empty shot + text appearing | Epilogue |
| Rapid montage editing | Transition / time compression |

**Music suggestion rules (all templates may reference; music-director template must use):**

| Visual/narrative feature | `music_note` direction |
|---|---|
| Establishing shot, space reveal | Thin pad + ambient, don't compete for attention |
| Rising tension, character conflict | Sub-bass drone enters, gradually layer up |
| Dialogue segment, performance focus | Music recedes or goes minimal, don't cover lines |
| Climax / payoff | Full ensemble enters, dynamics at maximum |
| Epilogue / farewell | Layers exit gradually, leave resonance |
| Transition | Begin preparing the shift 0.5-1s before the cut |

After fill-in, the draft must contain:

- Video basic info
- Candidate segments (with event, mood, camera language descriptions)
- Character / scene / prop summary
- Naming confirmation tables
- Low-confidence items
- Pending questions
- ASR / OCR key info if available

### Step 4: Naming confirmation gate

**Confirm by category**, not as one lump question:

1. Character official names
2. Scene / setup official names
3. Key prop official names
4. Output template preference
5. Whether to proceed to final

If user doesn't respond → Allow continuation, keep "temp:" markers in final, explicitly list unconfirmed items in the pending column.

If user provides naming overrides, apply them to the draft Markdown or (later) to the final JSON:

```bash
# Preview changes without modifying files
python scripts/cuesheet_creator.py apply-naming --overrides <naming_overrides.json> --md <cue_sheet.md> --dry-run

# Apply to final JSON (after Step 6), write to a new file
python scripts/cuesheet_creator.py apply-naming --overrides <naming_overrides.json> --cue-json <final_cues.json> --output <new_final_cues.json>

# Apply in-place to both files
python scripts/cuesheet_creator.py apply-naming --overrides <naming_overrides.json> --cue-json <final_cues.json> --md <cue_sheet.md>
```

Note: JSON replacements are field-scoped (only naming-relevant fields like scene, characters, location, event, dialogue, needs_confirmation are modified). Markdown replacements are full-text.

### Step 5: Director-style block merging

**This step is executed by the LLM.** Based on Step 3 fill-in results, merge segments by the following trigger priorities:

**Tier 1: Must split**

- Scene change
- Time-layer change (reality / flashback / dream / white-out)
- Narrative function change (establishing / dialogue / payoff / flashback / epilogue)
- Visual format change (storyboard / CG / hand-drawn / UI)

**Tier 2: Usually split**

- Dominant camera language change
- Dominant mood change
- Core character relationship change
- Music function change

**Tier 3: Usually do NOT split separately**

- Minor reverse shots within the same functional block
- Brief insert shots within the same functional block
- Shot size changes that don't change block function

**LLM merge execution steps:**

1. Tag each draft_block with its narrative function (establishing / dialogue / payoff / flashback / epilogue / transition).
2. Merge adjacent blocks if narrative function, scene, and mood are continuous.
3. Renumber after merge (A1, A2, A3…).
4. Select the most representative keyframe from each merged block.

After merging, the script can validate and combine:

```bash
python scripts/cuesheet_creator.py merge-blocks --analysis-json <analysis.json> --merge-plan <merge_plan.json> --output <merged_blocks.json>
```

### Step 6: Generate final structure JSON

**Option A: Generate skeleton first, then LLM fills content** (recommended for consistency):

```bash
python scripts/cuesheet_creator.py build-final-skeleton --source-json <out-dir>/merged_blocks.json --output <out-dir>/final_cues.json --template production --video-title "My Video" --source-path <video-path>
```

> **Note**: When the source is merged blocks (not raw analysis.json), always pass `--source-path` and `--video-title` explicitly. Otherwise metadata may fall back to intermediate file paths.

This creates a `final_cues.json` with correct structure and empty fields for LLM to fill in. Then LLM fills the empty fields.

**Option B: LLM generates the full JSON directly** — structure reference: `assets/final_cues.sample.json`.

Requirements:

- All time fields use `HH:MM:SS.mmm`
- Time input arguments (`--start-time`, `--end-time`) accept flexible formats: `HH:MM:SS.mmm`, `HH:MM:SS`, `MM:SS.mmm`, `MM:SS`, or bare seconds
- `keyframe` should be the frame that best represents the block's dominant composition
- Use `confidence` / `needs_confirmation` to flag low-confidence items
- Select fields based on template; don't force irrelevant columns (field definitions in `references/field-templates.md`)

Validate immediately after generation:

```bash
python scripts/cuesheet_creator.py validate-cue-json --cue-json <out-dir>/final_cues.json --template production --base-dir <out-dir> --check-files
```

Validates: time continuity, required field completeness, temp-name marker consistency, template field matching, keyframe file existence (with `--check-files`).

### Step 7: Export final deliverables

**Excel:**

```bash
python scripts/cuesheet_creator.py build-xlsx --cue-json <out-dir>/final_cues.json --output <out-dir>/cue_sheet.xlsx --base-dir <out-dir>
```

**Markdown sync version:**

```bash
python scripts/cuesheet_creator.py export-md --cue-json <out-dir>/final_cues.json --output <out-dir>/cue_sheet.md --template production
```

---

## Template selection rules

Field definitions in `references/field-templates.md`.

### production (default)

For director, producer, art, cinematography, and sound cross-department collaboration.

**Perspective**: Prioritize "what needs cross-department alignment in this segment." Clarify space, composition, relationships, execution risks. `director_note` covers camera language and production coordination points — no vague commentary.

**Example shot block:**

```json
{
  "shot_block": "A1",
  "start_time": "00:00:00.000",
  "end_time": "00:00:08.400",
  "keyframe": "keyframes/A1.jpg",
  "shot_size": "WS",
  "angle_or_lens": "front / centered",
  "motion": "slow push-in",
  "scene": "temp: Main Hall",
  "mood": "establishing, solemn, expectant",
  "location": "interior main hall",
  "characters": "temp: Girl-A; extras",
  "event": "Establish main space and introduce central character",
  "important_dialogue": "Narrator: Welcome to...",
  "music_note": "thin pad + light pulse, prepare shift at 8.4s",
  "director_note": "Composition emphasizes depth; watch crowd blocking and center axis",
  "confidence": "segment=high; names=low",
  "needs_confirmation": "character official names; main hall setup name"
}
```

### music-director

For composer / scoring communication.

**Perspective**: Judge mood and rhythmic function first. Specify music entry, change, and exit points. Instrumentation suggestions should be concrete (e.g., "pizzicato bass + granular electronic pulse," not "add some tension").

**Example shot block:**

```json
{
  "shot_block": "A2",
  "start_time": "00:00:08.400",
  "end_time": "00:00:17.900",
  "mood": "tension rising → brief suppression → pre-burst buildup",
  "event": "Character confrontation, Girl-A and Boy-B lock eyes",
  "important_dialogue": "Girl-A: You finally came.",
  "music_note": "sub-bass drone enters at 8.4s, add unstable string tremolo at 12s, lift tension once before 17.9s for next-block burst",
  "rhythm_change": "8.4s: from no rhythm into slow pulse (~60bpm); 15s: pulse accelerates to ~90bpm",
  "instrumentation": "sub-bass drone + strings col legno → tremolo transition + metallic percussion prep",
  "dynamics": "pp → mp → mf (buildup, do not release in this block)",
  "confidence": "mood=medium; dialogue=medium",
  "needs_confirmation": "both character official names"
}
```

### script

For story discussion and early-stage breakdown.

**Perspective**: State what happens first, then who is present and where. Do not over-load with camera technical info.

**Example shot block:**

```json
{
  "shot_block": "B1",
  "start_time": "00:00:18.000",
  "end_time": "00:00:35.200",
  "scene": "temp: Rooftop",
  "location": "exterior rooftop, dusk",
  "characters": "temp: Girl-A",
  "event": "Girl-A stands alone at the rooftop edge, recalling prior conversation with Boy-B. Intercut with flashback fragments.",
  "important_dialogue": "(inner monologue) I actually knew all along.",
  "confidence": "segment=high; dialogue=low (no ASR, dialogue inferred from visuals)",
  "needs_confirmation": "character official name; rooftop project name"
}
```

---

## Segmentation rules

### Tier 1: Must split

- Scene change
- Time-layer change (reality / flashback / dream / white-out)
- Narrative function change (establishing / dialogue / payoff / flashback / epilogue)
- Visual format change (storyboard / CG / hand-drawn / UI)

### Tier 2: Usually split

- Dominant camera language change
- Dominant mood change
- Core character relationship change
- Music function change

### Tier 3: Usually do NOT split separately

- Minor reverse shots within the same functional block
- Brief insert shots within the same functional block
- Shot size changes that don't change block function

**Principle**: Each row represents a shot block that multiple departments can discuss together — not a disguised per-cut shot list.

---

## Naming confirmation mechanism

Place a standalone "naming confirmation table" in the draft.

### Characters

| temporary_name | evidence | confidence | confirmed_name | status |
|---|---|---|---|---|
| temp: Girl-A | red jacket, long hair, main POV in first block | medium | | pending |

### Scenes

| temporary_setup | space_note | confidence | confirmed_setup | status |
|---|---|---|---|---|
| temp: Corridor-1 | white ceiling lights, long straight corridor | medium | | pending |

### Props

| temporary_prop | importance | evidence | confirmed_prop | status |
|---|---|---|---|---|
| temp: Box-A | key-prop | featured in multiple close-ups and handoffs | | pending |

Naming override format: see `assets/naming_overrides.sample.json`.

---

## Keyframe strategy

Do not take the first frame of each block as the representative frame. Within the same shot block, prioritize:

1. Frame that best represents the block's dominant composition
2. Frame that best shows character relationships
3. Frame that best shows key props / actions
4. For transition blocks, prioritize the frame with the clearest visual format

---

## Failure fallback rules

| Situation | Action |
|---|---|
| No `ffmpeg` / `ffprobe` | **Stop**, provide platform-specific install guidance |
| No ASR | Continue with visual-only cue sheet, mark dialogue confidence as degraded |
| No OCR | Skip on-screen text layer |
| Video too long (>20min) | Default to structural draft only, ask before full expansion |
| Cut detection anomaly | Fall back to fixed-interval sampling + manual merge |

---

## Delivery checklist

Detailed checklist in `references/review-checklist.md`. Core checks:

- [ ] Draft first, final second
- [ ] Naming confirmation table explicitly provided
- [ ] Segments at "collaborative shot block" granularity
- [ ] Keyframe is representative, not mechanical first-frame
- [ ] Low-confidence items marked with `confidence` / `needs_confirmation`
- [ ] Director / production / music supervisor perspectives not mixed
- [ ] Markdown and Excel fields consistent
- [ ] Excel has embedded keyframe screenshots

---

## Reference files

| File | Purpose |
|---|---|
| `references/dependency-setup.md` | Detailed environment install commands and evaluation rules |
| `references/field-templates.md` | Field definitions, conventions, final JSON structure |
| `references/review-checklist.md` | Full delivery checklist and question groupings |
| `references/spec.md` | Internal design notes and maturity roadmap (not a runtime reference) |
| `assets/final_cues.sample.json` | Final JSON sample |
| `assets/naming_overrides.sample.json` | Naming override sample |
| `assets/merge_plan.sample.json` | Merge plan sample (merge-blocks input format) |
| `scripts/cuesheet_creator.py` | Script entry point |

---

## Script command reference

**Global arguments** (apply to all commands):

| Argument | Purpose |
|---|---|
| `--ffmpeg-path <path>` | Explicit path to ffmpeg executable (overrides auto-detection) |
| `--ffprobe-path <path>` | Explicit path to ffprobe executable (overrides auto-detection) |

| Command | Purpose |
|---|---|
| `prepare-env` | One-command env check + optional install + recheck |
| `selfcheck` | Standalone environment check |
| `install-deps` | Install missing Python packages |
| `scan-video` | Extract frames + scene detection + optional ASR/OCR + output analysis.json. Default output: `<video-dir>/<video-name>_cuesheet/`. Supports `--start-time` / `--end-time` for clip range. |
| `draft-from-analysis` | Generate template-differentiated draft skeleton from analysis.json |
| `merge-blocks` | Merge draft blocks based on a merge plan (with validation). Unreferenced blocks are auto-appended with `"unmerged": true` flag (not silently dropped). Use `--strict` to fail on unreferenced blocks instead. |
| `build-final-skeleton` | Generate empty final_cues.json skeleton from merged/draft blocks for LLM fill-in |
| `apply-naming` | Batch-apply naming overrides (field-scoped JSON, full-text MD). Supports `--dry-run` / `--output`. |
| `validate-cue-json` | Structural validation (time, required fields, duplicates) + quality warnings (empty recommended fields, temp-name consistency) + delivery readiness check. `Valid: YES` means no structural errors; `Delivery ready: YES` means all recommended fields are filled and naming is consistent. |
| `export-md` | Generate Markdown final from final_cues.json |
| `build-xlsx` | Generate Excel final from final_cues.json |
