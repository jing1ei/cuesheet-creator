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
- User wants to create or customize a cue sheet template for a specific department or workflow.
- User mentions a specific role (e.g. "sound designer", "VFX supervisor") not covered by built-in templates.

## When NOT to trigger

- Pure livestream recordings, meeting recordings, or surveillance footage where the user demands per-cut precision.
- User only wants subtitles, transcripts, or raw ASR text.
- User only wants a rough summary without shot, segment, or music information.

## v1 Scope

Single video → single cue sheet only. Not in v1: batch processing, merging multiple cue sheet versions, syncing to enterprise docs/spreadsheets, auto-generating scoring brief packages.

---

## Agent Contract

> This section defines what an agent MUST know to execute this skill reliably. It is the authoritative reference for inputs, outputs, decision points, and failure behavior.

### Required inputs

| Input | Notes |
|---|---|
| **Video file path** | The only mandatory input. Must be a local file path the agent can access. |

Everything else has sensible defaults. If the user provides only a video, the agent can run the full workflow without asking further questions (except at mandatory checkpoints below).

### Optional inputs

| Input | Default | When to ask |
|---|---|---|
| Output template | `production` | Only if user mentions music/scoring, script/story focus, or a specific department role. Custom templates supported — use `list-templates` to see options. |
| Output directory | `<video-dir>/<video-stem>_cuesheet/` | Only if user wants output elsewhere |
| ASR (speech recognition) | Off | Offer if dialogue analysis is needed |
| OCR (on-screen text) | Off | Offer if video has subtitles/UI text |
| Clip range (`--start-time` / `--end-time`) | Full video | Only for long videos or user-specified segments |
| Naming overrides | None | Only after Phase A draft is generated |
| pip mirror (`--index-url`) | None | Only if user is in China or on restricted network |

### Produced artifacts

| File | Always? | Notes |
|---|---|---|
| `<out-dir>/analysis.json` | ✅ | Raw scan output — scene candidates, keyframes, ASR/OCR data. Contains `agent_summary` for compact LLM consumption. |
| `<out-dir>/keyframes/*.jpg` | ✅ | Keyframe screenshots with sharpness scores |
| `<out-dir>/cue_sheet.md` | ✅ | Markdown deliverable (draft in Phase A, final in Phase B) |
| `<out-dir>/draft_fill.json` | ✅ | **JSON fill-in file** — LLM edits THIS instead of the Markdown table. Pre-populated with block IDs, times, keyframe paths; all content fields are empty strings for LLM to fill. |
| `<out-dir>/final_cues.json` | ✅ | Structured cue data for export |
| `<out-dir>/cue_sheet.xlsx` | ✅ | Excel deliverable with embedded keyframes (production template) |
| `<out-dir>/audio.wav` | Only with `--asr` | Intermediate; safe to delete after analysis |
| `<out-dir>/merged_blocks.json` | Only if merge step runs | LLM-driven block merge output |

### Stop-and-ask checkpoints

The agent **MUST stop and wait for user response** at these points. Do NOT auto-continue past them.

| # | Checkpoint | When | What to ask |
|---|---|---|---|
| **C1** | FFmpeg missing | After Step 1 selfcheck | Guide installation (one option at a time per Step 1.5) |
| **C2** | Naming confirmation | After Phase A draft | Present naming tables for characters, scenes, props. Ask user to confirm or override. |
| **C3** | Template + final confirmation | Before Phase B export | "Proceed to final export with template X? Any naming changes?" |

### Auto-continue rules

The agent **MAY proceed automatically** (no user confirmation needed) in these cases:

| Situation | Action |
|---|---|
| scan-video succeeds | → Automatically run draft-from-analysis |
| validate-cue-json reports warnings but no errors | → Report warnings, continue to export |
| validate-cue-json reports errors | → Report errors, do NOT export. Ask user how to fix. |
| ASR/OCR unavailable | → Continue without them, note degradation in draft |
| User says "skip naming" or "use temp names" | → Proceed with temp markers, list unconfirmed items in final |
| User provides naming overrides after C2 | → Apply overrides, then proceed to merge/final |

### Efficiency rules

- **Step 2 (scan-video)**: `analysis.json` now contains an `agent_summary` field — a compact overview with block IDs, keyframe paths grouped into batches, and ASR/OCR summaries. **Read `agent_summary` instead of the full `analysis.json`** to avoid exhausting token budget.
- **Step 3b (LLM fill-in)**: Fill in `draft_fill.json` (a JSON file), NOT the Markdown table. View keyframes in batches of 5-8 images using the batch groups listed in `agent_summary.keyframe_batches`. Fill ALL blocks in one writing pass per batch. Do NOT loop one image at a time — this will exhaust token budget and step limits.
- **Step 7 (Export)**: Run `build-xlsx` and `export-md` as single CLI commands. Do NOT manually embed images or generate Excel content in the conversation.

### Resume rules

If the workflow is interrupted mid-session:

1. **Check what already exists** in `<out-dir>/`:
   - If `analysis.json` exists → skip scan-video.
   - If `draft_fill.json` exists → check its `fill_status` field:
     - `"pending"` → fill-in has NOT been done yet. Read `draft_fill.json` and continue filling.
     - `"complete"` → fill-in is done. Proceed to naming confirmation (C2) or merge step.
   - If `cue_sheet.md` exists but `draft_fill.json` does not → skeleton was generated but JSON fill-in file is missing. Re-run `draft-from-analysis` to regenerate both.
2. **Re-read existing artifacts** before continuing — don't regenerate what's already there.
3. **Re-running any command is safe** — all commands overwrite their output files without corrupting other artifacts in the same directory.
4. **Naming confirmation state is NOT persisted** — if the session is interrupted after C2, ask again.

### Hard acceptance criteria (for validate-cue-json)

A cue sheet is **not delivery-ready** if any of these fail:

- Every row has `start_time` and `end_time` in `HH:MM:SS.mmm` format
- No duplicate `shot_block` IDs
- Every `temp:` marker in naming fields has a corresponding `needs_confirmation` entry
- Template-required fields are non-empty (see `references/field-templates.md`)
- Keyframe files exist on disk (when `--check-files` is used)

### Non-goals — what this skill will NOT do

- Will not guess official character/scene/prop names — always uses `temp:` markers until confirmed
- Will not auto-install ffmpeg
- Will not auto-upgrade pip packages without explicit user permission
- Will not process multiple videos in one run
- Will not generate music/scoring briefs (v1 scope)
- Will not sync outputs to external services (Google Sheets, TAPD, etc.)

---

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
- SceneDetect missing → **Continue** (histogram fallback works), but mention to the user: "场景检测目前用的是基础模式。如果你的视频有很多溶解或渐变转场，可以安装 scenedetect 提升准确度。需要我帮你装吗？" If user says yes, run `prepare-env --mode install-scene --out-dir <out-dir>` and re-run scan-video.
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

Outputs `analysis.json` containing: video metadata, `agent_summary` (compact LLM overview), scene candidates, keyframe screenshots (with sharpness scores), draft block candidates, ASR speech segments (if enabled), OCR text detections (if enabled), analysis notes.

### Step 3: Form Phase A draft

**Two steps: generate skeleton first, then LLM fills in content via JSON.**

#### 3a. Generate skeleton draft + JSON fill-in file

```bash
python scripts/cuesheet_creator.py draft-from-analysis --analysis-json <out-dir>/analysis.json --output <out-dir>/cue_sheet.md --template production
```

This generates TWO files:
- `cue_sheet.md` — Markdown skeleton with keyframe batch groups and fill-in guidance
- `draft_fill.json` — **JSON fill-in file** (the primary file LLM should edit)

The JSON file has `fill_status: "partial"` (when pre-fills exist) or `"pending"` and contains rows with:
- **Pre-populated**: `shot_block`, `start_time`, `end_time`, `keyframe`
- **Auto-filled from data**: `important_dialogue` (from ASR time-overlap), `confidence` (from detection method + ASR coverage), `needs_confirmation` (standard items), `mood` hints (from visual features: tone, contrast, color temperature)
- **OCR hints**: `director_note` or `event` may contain `[OCR detected: ...]` prefixes when on-screen text was found
- **Empty for LLM**: all remaining content fields (scene, location, characters, event, shot_size, motion, etc.)

#### 3b. LLM content fill-in (critical step — use JSON, not Markdown)

> **CRITICAL — JSON fill-in workflow**: Edit `draft_fill.json`, NOT the Markdown table.
> 1. Read `agent_summary` from `analysis.json` (NOT the full file — just the `agent_summary` field)
> 2. View keyframe images in batches listed in `agent_summary.keyframe_batches` (5-8 at a time)
> 3. For each batch, fill in ALL corresponding blocks in `draft_fill.json` in one write pass
> 4. After ALL blocks are filled, update `fill_status` from `"partial"` (or `"pending"`) to `"complete"`
> 5. Note: some fields already have auto-generated content (e.g. `important_dialogue` from ASR, `mood` with `[visual: ...]` hints, `confidence`). The LLM should **incorporate or replace** these — they are hints, not final content.
>
> **Why JSON instead of Markdown**: JSON fields avoid column-misalignment bugs from Markdown pipe characters. LLM can target specific fields without counting table columns. The filled JSON can feed directly into `build-final-skeleton` and `validate-cue-json`.
>
> The goal is to minimize tool calls. A 20-block cue sheet should take 2-4 rounds (one per keyframe batch), not 20.

For each shot block, use the corresponding keyframe to fill in fields using these rules:

> **Template-aware fill-in**: The rules below are the DEFAULT rules for the 3 built-in templates. When using a **custom template**, the template's `perspective`, `segmentation.split_triggers`, and `segmentation.keyframe_priority` fields override these defaults. Read the active template's definition (via `show-template --name <name> --output-format json`) to get the specific rules. The template's `fill_guidance` field provides column-specific instructions.

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

**New: Auto-suggest merge candidates first, then LLM reviews.**

```bash
python scripts/cuesheet_creator.py suggest-merges --analysis-json <out-dir>/analysis.json --output <out-dir>/suggested_merges.json
```

`suggest-merges` computes inter-block continuity scores based on:
- Visual similarity (brightness, contrast, saturation, hue distance)
- Cut boundary strength (histogram distance)
- ASR continuity (dialogue spanning boundaries)
- Short block detection

Blocks with continuity score ≥ 0.65 are suggested for merging. The output is a preliminary merge plan that the **LLM must review** — the script cannot detect narrative-function boundaries (scene changes, flashback transitions) which are semantic Tier 1 must-split rules.

**LLM review workflow:**
1. Read `suggested_merges.json`
2. For each suggested merge group, verify that Tier 1 must-split rules are NOT violated
3. Adjust the merge plan (split groups that cross narrative boundaries, merge additional groups the score missed)
4. Pass the reviewed plan to `merge-blocks`

**This step is still partly executed by the LLM.** Based on Step 3 fill-in results AND the auto-suggested merge plan, apply these trigger priorities:

> **Template-aware merging**: The tier rules below are the DEFAULT rules for the `production` template (strategy: `scene-cut`). When using a **custom template**, the template's `segmentation.merge_bias` rules override the Tier 2/3 defaults. Tier 1 (must-split) rules always apply regardless of template. The `suggest-merges` command automatically adjusts its continuity scoring weights based on the template's segmentation strategy — for example, an `emotional-arc` strategy weights visual tone/color similarity higher and hard cuts lower than `scene-cut`.

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

**Option A: Use the filled `draft_fill.json` directly** (recommended — fewest steps):

```bash
python scripts/cuesheet_creator.py build-final-skeleton --source-json <out-dir>/draft_fill.json --output <out-dir>/final_cues.json --template production
```

> `build-final-skeleton` now accepts `draft_fill.json` as input. It detects the `fill_status` field and preserves all LLM-filled content. This skips the separate "empty skeleton → LLM fill" step entirely.

**Option B: From merged blocks** (when merge step is used):

```bash
python scripts/cuesheet_creator.py build-final-skeleton --source-json <out-dir>/merged_blocks.json --output <out-dir>/final_cues.json --template production --video-title "My Video" --source-path <video-path>
```

> **Note**: When the source is merged blocks (not raw analysis.json), always pass `--source-path` and `--video-title` explicitly. Otherwise metadata may fall back to intermediate file paths.

**Option C: LLM generates the full JSON directly** — structure reference: `assets/final_cues.sample.json`.

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

> **CRITICAL for agents**: Both `build-xlsx` and `export-md` are **single CLI commands** that handle everything internally — including keyframe embedding into Excel. Do NOT attempt to embed images manually or process keyframes one-by-one in the conversation. Just run the command and let it finish.

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

> **Custom templates**: In addition to the 3 built-in templates below, users can create custom templates for specific departments or workflows. Custom templates are stored as JSON in `templates/custom/` and define not just columns but also segmentation strategy, keyframe selection criteria, and block merging bias. Use `list-templates` to see all available templates. See the **Custom templates** section below for the guided creation workflow.

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

## Custom templates

Templates control not just **columns** (what information each shot block captures), but also **segmentation strategy** (what constitutes a block boundary), **keyframe selection** (what makes a frame representative), and **block merging bias** (what continuity signals matter). Different perspectives need fundamentally different rules — a sound designer splits on action events, while a music director splits on emotional transitions.

### When to trigger guided template creation

- User asks for a template that doesn't exist (e.g. "I need a cue sheet for sound design")
- User wants custom columns for their specific workflow
- User mentions a specific department or role not covered by built-in templates (sound design, VFX, color grading, etc.)
- User says "create a template" or "customize the template"

### Guided creation workflow

#### Phase 1: Discovery (LLM-driven conversation)

Ask the user one question at a time. Infer when possible — if the user gives a clear role (e.g. "sound designer"), infer most answers and jump to drafting, only confirming ambiguous points.

1. "What is this template for? Who will read the cue sheet?"
   → Determines `name`, `description`, `perspective`
2. "What should define where one shot block ends and another begins? What kind of transitions matter most for your work?"
   → Determines `segmentation.strategy`, `split_triggers`, `merge_bias`
3. "When you look at a representative frame for a block, what should it show you?"
   → Determines `segmentation.keyframe_priority`
4. "What information do you need for each shot block?"
   → Determines `columns`
5. "Should dialogue/speech be included?" → ASR prefill column
6. "Should on-screen text be captured?" → OCR prefill column
7. "Any naming entities to track?" → naming_field columns

#### Phase 2: Draft generation (LLM generates, script validates)

Generate a template JSON and save via:
```bash
python scripts/cuesheet_creator.py save-template --input <template.json> --validate
```

`save-template` validates:
- Required fields present (name, description, perspective, segmentation, columns)
- Field names valid, no duplicates, no conflicts with structural columns
- Segmentation has valid strategy with split_triggers, merge_bias, keyframe_priority
- If validation passes: saves to `templates/custom/<name>.json`
- If fails: prints specific errors for LLM to fix

Present the summary to the user:
> "I've drafted a 'sound-design' template:
> - **Segmentation**: splits on action events (impacts, ambience changes, vehicle passes)
> - **Keyframes**: prioritize peak action moments and sound source visibility
> - **Merge bias**: merge across visual cuts if ambient sound is continuous
> - **Columns** (8): Ambience Zone, Sound Events, Foley Notes, Scene, Event, Dialogue (auto-ASR), Confidence, Needs Confirmation
>
> Want to adjust anything?"

#### Phase 3: Iteration

User can say:
- "Add a column for reverb character"
- "Actually, split on every hard cut too, not just sound events"
- "Make the keyframe show the widest shot of the space, not the action moment"
- "Rename it to 'sfx-breakdown'"

LLM modifies the template JSON and re-validates until user approves.

### How segmentation strategy affects the workflow

The `segmentation` field is consumed at **two levels**:

**Level 1 — Script (mechanical):**
- `scan-video` always produces the same raw scene candidates (scene detection is algorithm-constant)
- `suggest-merges` adjusts continuity scoring weights based on the template's strategy:
  - `emotional-arc`: higher weight on visual tone/color similarity, lower on hard cuts
  - `action-event`: lower weight on visual similarity, higher on ASR/sound continuity
  - `scene-cut` (default): standard weights (backward compatible)
- The `split_triggers` are stored in `agent_summary` for LLM consumption

**Level 2 — LLM (semantic):**
- During Step 3b fill-in: uses `split_triggers` and `keyframe_priority` to judge block boundaries and select representative frames
- During Step 5 merge review: uses `merge_bias` instead of the default tier rules
- The `perspective` text guides the overall fill-in approach

### Template management commands

```bash
# List all available templates
python scripts/cuesheet_creator.py list-templates [--output-format text|json]

# Show full details of a template
python scripts/cuesheet_creator.py show-template --name <name> [--output-format text|json]

# Validate and save a new template
python scripts/cuesheet_creator.py save-template --input <path> [--overwrite]

# Delete a custom template (built-in templates cannot be deleted)
python scripts/cuesheet_creator.py delete-template --name <name>
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
| `suggest-merges` | Auto-compute inter-block continuity scores and output a suggested merge plan. LLM reviews and adjusts before passing to `merge-blocks`. Use `--threshold` to adjust sensitivity (default 0.65). Use `--template` to adjust scoring weights based on template segmentation strategy. |
| `build-final-skeleton` | Generate final_cues.json skeleton from merged/draft blocks or filled draft_fill.json |
| `apply-naming` | Batch-apply naming overrides (field-scoped JSON, full-text MD). Supports `--dry-run` / `--output`. |
| `derive-naming-tables` | Scan filled `draft_fill.json` for `temp:` markers, deduplicate, aggregate block references, output `naming_tables.json`. Optionally updates `cue_sheet.md` with derived naming tables (`--md`). |
| `normalize-fill` | Normalize/lint LLM-filled JSON. Standardizes `shot_size` (WS/MS/CU/EWS/ECU) and `motion` enums, strips `[visual: ...]` / `[OCR detected: ...]` hint prefixes, checks `temp:` marker consistency with `needs_confirmation`, reports empty required fields. Use `--fix` to auto-normalize + write; default is lint-only. |
| `validate-cue-json` | Structural validation (time, required fields, duplicates) + quality warnings (empty recommended fields, temp-name consistency) + delivery readiness check. `Valid: YES` means no structural errors; `Delivery ready: YES` means all recommended fields are filled and naming is consistent. |
| `export-md` | Generate Markdown final from final_cues.json |
| `build-xlsx` | Generate Excel final from final_cues.json |
| `list-templates` | List all available templates (built-in + custom) with name, description, strategy, column count, and source. |
| `show-template` | Show full details of a template: columns, segmentation strategy, split triggers, merge bias, keyframe priority, perspective, fill guidance. |
| `save-template` | Validate and save a template JSON to `templates/custom/`. Validates schema, checks required fields, saves on success. Use `--overwrite` to replace existing. |
| `delete-template` | Delete a custom template. Built-in templates cannot be deleted. |
