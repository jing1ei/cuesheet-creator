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
| `<out-dir>/keyframes/contact_batch_N.jpg` | ✅ | **Contact sheets** — grid images showing all keyframes in each batch with block ID labels. LLM reads ONE contact sheet per batch instead of N individual keyframes. Listed in `agent_summary.contact_sheets`. |
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
| **C2** | Draft review + naming + final confirmation | After Phase A export (Excel + Markdown generated with `temp:` markers) | Present the Excel/Markdown deliverable first. Then: "Here's the draft cue sheet (temporary names marked with temp:). Want to replace them with official names, or use this version as-is?" |

> **Design rationale for C2**: Users understand naming better when they can **see** the cue sheet with `temp:` markers in context — in the actual Excel layout with keyframes — rather than staring at an abstract naming confirmation table. So we generate the full deliverable first (with `temp:` markers and `delivery_ready: NO`), show it, and THEN offer naming replacement as an optional refinement step. If the user provides names, apply them and re-export. If the user says "use as-is" / "skip naming", deliver as-is.

**Previous C3 (template + final confirmation) is absorbed into C2.** Template is now confirmed in Step 0 upfront, so no need for a separate pre-export gate.

### Auto-continue rules

The agent **MAY proceed automatically** (no user confirmation needed) in these cases:

| Situation | Action |
|---|---|
| scan-video succeeds | → Automatically run draft-from-analysis |
| validate-cue-json reports warnings but no errors | → Report warnings, continue to export |
| validate-cue-json reports errors | → Report errors, do NOT export. Ask user how to fix. |
| ASR/OCR unavailable | → Continue without them, note degradation in draft |
| User says "skip naming" or "use temp names" | → Proceed with temp markers, list unconfirmed items in final |
| User provides naming overrides after C2 | → Apply overrides, then re-export |
| Runtime assessment selects Tier 2 or 3 | → Announce tier selection, proceed without asking. Do NOT ask "should I use Tier 3?" — just do it and declare it. |
| fill_status is "data-only" after Tier 3 | → Proceed to export. At C2, inform user about data-only limitations. |
| Previous session failed at Step 3b | → On resume, escalate tier (see Resume rules). Do NOT retry same strategy. |

### Progress signals (mandatory)

> **The #1 UX failure mode is silence.** If the user sees no output for >60 seconds, they assume the skill is dead. Preventing this is non-negotiable.

The agent **MUST** emit a short status line to the user at these points. These are NOT checkpoints — they do not require a user response, do not block the workflow, and must cost ≤ 15 words each.

| When | What to say (example) |
|---|---|
| Before `prepare-env` / `install-deps` starts | `Checking runtime environment...` |
| After env check, before `scan-video` starts | `Environment ready. Starting video scan...` |
| If `scan-video` runs >30s (long video) | `Scanning video (sampled N frames so far)...` |
| After `scan-video` completes | `Scan complete: N scene candidates, M keyframes extracted.` |
| If ASR/OCR degrades or fails | `ASR unavailable — will rely on OCR subtitles / visual-only analysis.` |
| Before starting keyframe batch fill-in | `Starting keyframe review and semantic fill-in (N batches total)...` |
| After each keyframe batch is filled | `[progress] Completed batch X/N (Y/Z blocks filled)` |
| Before export step starts | `Generating Excel + Markdown deliverables...` |
| After export completes | `Done: cue_sheet.xlsx and cue_sheet.md generated.` |

**Rule**: If any single operation (command execution, keyframe viewing, file writing) is expected to take >30 seconds, emit a progress signal BEFORE starting it. If a multi-batch operation (like keyframe fill-in) will take multiple rounds, emit progress AFTER each round.

**Token budget**: All progress signals combined should cost <200 tokens per full workflow. Use terse, factual messages. No pleasantries, no explanations.

### Runtime capability assessment (mandatory before Step 3b)

> **Before starting keyframe fill-in, the agent MUST assess its own runtime constraints and select the appropriate fill-in tier.** This is not optional — skipping this assessment is the #1 cause of workflow failure.

**Assess these three dimensions:**

| Dimension | How to check | What matters |
|---|---|---|
| **Step budget** | Count remaining available tool calls in this session. If unknown, assume 50 total, subtract calls already made. | Fill-in needs ~(N_batches × 2) calls minimum: N reads + N writes. If budget < (batches × 2 + 10), use Tier 2 or 3. |
| **Image viewing** | Can the agent call `read_file` on a `.jpg` and receive visual content (not just bytes)? | If NO image capability → must use Tier 3. |
| **Context capacity** | Is the context window large enough to hold agent_summary + all batch images + draft_fill.json simultaneously? | With 1M context this is rarely the issue. With <200K, may need Tier 2. |

**Select a tier based on assessment:**

| Tier | When to use | Strategy | `fill_status` value |
|---|---|---|---|
| **Tier 1: Full visual** | Image viewing works AND step budget ≥ (batches × 2 + 10) | Read keyframes in batches, fill all semantic fields from visual analysis | `"complete"` |
| **Tier 2: Batch-compressed visual** | Image viewing works BUT step budget is tight | Read ALL keyframes in ONE tool call batch (parallel read_file calls), fill ALL blocks in ONE write pass | `"complete"` |
| **Tier 3: Data-informed fill** | No image viewing capability OR step budget critically low | Use `visual_features`, `motion_hint`, ASR, OCR data from `analysis.json` to fill fields. Do NOT fabricate scene/character details not supported by data. | `"data-only"` |

> **Tier selection is announced to the user** as a progress signal:
> - Tier 1: `Fill-in: Tier 1 (full visual), N batches.`
> - Tier 2: `Fill-in: Tier 2 (compressed), all keyframes in 1 round.`
> - Tier 3: `Fill-in: Tier 3 (data-informed, no visual review). Scene/character fields may need manual review.`

**Tier 3 constraints** (data-only fill-in):
- `shot_size`: Infer ONLY if `visual_features` data is present (cannot determine without seeing the frame — leave empty if unsure)
- `motion`: Use `motion_hint` field directly (`likely-static` → `static`, `likely-camera-move` → leave as description)
- `mood`: Derive from `visual_features.tone` + `visual_features.color_temp` + `visual_features.contrast` using the mapping rules
- `scene` / `characters` / `event`: Mark as `"[data-only: requires visual confirmation]"` — do NOT guess
- `important_dialogue`: Use ASR prefill as-is (already populated by draft-from-analysis)
- `confidence`: Append `; fill=data-only` to the existing confidence string

> **Critical**: Tier 3 exists to **unblock the pipeline**, not to produce final content. The output will have gaps. This is explicitly better than the workflow hanging forever at Step 3b.

### Efficiency rules

- **Step 2 (scan-video)**: `analysis.json` now contains an `agent_summary` field — a compact overview with block IDs, keyframe paths grouped into batches, and ASR/OCR summaries. **Read `agent_summary` instead of the full `analysis.json`** to avoid exhausting token budget.
- **Step 3b (LLM fill-in)**: Fill in `draft_fill.json` (a JSON file), NOT the Markdown table. **First run the runtime capability assessment above and select a tier.** Then execute accordingly. Do NOT loop one image at a time — this will exhaust step limits regardless of token budget.
- **Step 3b tool call pattern** (Tier 1 and 2): Use **parallel tool calls** where the runtime supports it. Read multiple keyframe images in the SAME tool call batch (not sequentially). Write ALL blocks for a batch in ONE `replace_in_file` or `write_to_file` call, not one block at a time.
- **Step 7 (Export)**: Run `build-xlsx` and `export-md` as single CLI commands. Do NOT manually embed images or generate Excel content in the conversation.

### Resume rules

If the workflow is interrupted mid-session:

1. **Check what already exists** in `<out-dir>/`:
   - If `analysis.json` exists → skip scan-video.
   - If `draft_fill.json` exists → check its `fill_status` field:
     - `"pending"` → fill-in has NOT been done yet. Run runtime capability assessment, then start filling.
     - `"partial"` → fill-in was started but not completed. **Check which blocks already have content** (non-empty `scene` or `event` field). Skip those blocks, continue filling only empty ones. Do NOT restart from Batch 1.
     - `"data-only"` → data-informed fill was completed. Proceed to Step 4 export. At C2 checkpoint, inform user: "This draft was filled using algorithm data only (no visual review). Scene/character fields may need manual correction."
     - `"complete"` → fill-in is done. Proceed to naming confirmation (C2) or merge step.
   - If `cue_sheet.md` exists but `draft_fill.json` does not → skeleton was generated but JSON fill-in file is missing. Re-run `draft-from-analysis` to regenerate both.
2. **Re-read existing artifacts** before continuing — don't regenerate what's already there.
3. **Re-running any command is safe** — all commands overwrite their output files without corrupting other artifacts in the same directory.
4. **On resume after step-limit failure**: Re-run the runtime capability assessment. If the previous attempt used Tier 1 and failed, **escalate to Tier 2**. If Tier 2 also failed, **escalate to Tier 3**. Do NOT retry the same tier that failed.
5. **Naming confirmation state is NOT persisted** — if the session is interrupted after C2, ask again about naming when you re-export.

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

> **Install strategy**: `prepare-env` / `install-deps` auto-install packages with version constraints. Core package versions come from `requirements.txt`; optional component versions (scene/asr/ocr) are maintained in `scripts/cc/constants.py` `OPTIONAL_COMPONENTS`. For manual core install: `pip install -r requirements.txt`.

> **Windows / PowerShell note**: All `<video-path>` and `<out-dir>` arguments should be quoted if they contain spaces or special characters. If not running from the project root, use the full path to `scripts/cuesheet_creator.py`. Relative paths for `--video` and `--out-dir` are resolved from your current shell working directory, not the project directory.

> **Windows FFmpeg**: Run `cuesheet-creator install-ffmpeg` (or `python scripts/cuesheet_creator.py install-ffmpeg`) to auto-download FFmpeg with progress display. Alternatively, extract a portable FFmpeg build under `<skill-root>/tools/ffmpeg/`. cuesheet-creator will auto-detect either `<skill-root>/tools/ffmpeg/bin/ffmpeg.exe` or one nested release folder. You can also set `CUESHEET_CREATOR_FFMPEG_BIN_DIR` for the current shell.


---

## Mandatory principles

1. **Two-phase delivery**: Phase A draft first, then Phase B final. Do not skip Phase A; if user insists on immediate final, keep "temp-name" markers and unconfirmed columns.
2. **Temp-name protection**: Never write guessed names into the final. If user hasn't confirmed, continue but always keep "temp: xxx" markers visible.
3. **Shot block granularity**: Use "collaborative shot block" as the minimum row unit. Do not disguise output as a per-cut shot list.
4. **Perspective separation**: Keep director, production, and music supervisor perspectives separate. Do not blend them into a film-review paragraph.
5. **Long video protection**: For videos over 20 minutes, default to a structural draft first. Ask before doing full-detail expansion.
6. **Install safety**: When the user has not explicitly specified an install level, **never** auto-upgrade to any `install-*` mode. Default is always `check-only`. Even if the user says "set up my environment," confirm the exact install scope first.
7. **Progress reporting**: Never let the user wait >60 seconds without a status signal. See **Progress signals** in Agent Contract. Silence = the user thinks you're dead.

---

## Workflow

### Step 0: Confirm user intent and delivery strategy

> **Intent confirmation is mandatory.** Before any analysis begins, the agent must understand what the user actually wants. Template selection is ONE part of intent — not the whole picture. Do NOT silently assume defaults for anything the user hasn't explicitly stated.

**What the agent must know before proceeding (the "intent checklist"):**

| # | Question | Why it matters | Default if user doesn't specify |
|---|----------|----------------|--------------------------------|
| **I1** | **Purpose**: Who will read this cue sheet and what will they do with it? | Determines template, column selection, fill-in perspective | `production` (cross-department collaboration) |
| **I2** | **Template**: Which template to use? | Determines columns, segmentation strategy, merge rules | Inferred from I1 answer |
| **I3** | **Keyframes in export**: Should the Excel/Markdown deliverable include embedded keyframe images? | Some templates (music-director, script) default to text-only, but the user may still want visual reference | `yes` for production; **ask** for music-director and script |
| **I4** | **ASR/OCR**: Is dialogue or on-screen text important? | Determines whether to enable --asr / --ocr during scan | Infer from context; if video has dialogue or UI text, suggest enabling |
| **I5** | **Output language**: What language should the cue sheet content be written in? | Fill-in text (scene descriptions, mood, event, music_note, director_note) must match the target audience's language. Column headers/field names stay in English (they are structural). | **Always ask.** Do NOT guess from the user's input language — users often mix languages in conversation but have a specific preference for deliverables. |

**Agent behavior — confirm what you can't infer:**

1. If the user says *"make a cue sheet for this video"* with no further context → you know NOTHING about I1-I5. Ask:
   > "Got the video. Before I start:
   > 1. Who is this cue sheet for? (director/producer collab, composer/scoring, script/story, or tell me your role)
   > 2. Should the Excel include keyframe images, or text-only?
   > 3. What language for the cue sheet content? (e.g. English, 中文)"

2. If the user says *"I need a music cue sheet"* → you can infer I1 (composer/scoring) and I2 (music-director). But I3 and I5 are still unknown. Ask:
   > "Using `music-director` template. Two quick questions:
   > 1. Include keyframe screenshots in Excel, or text-only?
   > 2. Content language? (English, 中文, etc.)"

3. If the user says *"帮我做一个这个视频的 cue sheet，production 模板，要图，中文"* → all intent is clear: I1=production, I2=production, I3=yes, I4=infer, I5=中文. Proceed without asking.

4. If the user says *"just do it"* or *"default is fine"* → use `production` template with keyframes embedded. I5 is still unknown → ask language only:
   > "Using production template with keyframes. What language for the content? (English, 中文)"

**Rule: If intent is 100% clear from context, proceed immediately. If ANY ambiguity exists in I1-I5, ask ONCE with all unclear items in a single question. Never ask more than one round of questions.**

**Only proceed to Step 1 after intent is confirmed.**

| Item | Default |
|---|---|
| Video path | (must be provided by user) |
| Output directory | `<video-dir>/<video-name>_cuesheet/` (same folder as the video) |
| Delivery phase | Draft first, then final |
| Output template | **Infer from intent, confirm if ambiguous** (fallback `production`) |
| Embed keyframes in export | **yes** for production; **ask** for music-director/script |
| Output language | **Always ask** (no default — do not guess) |
| Analyze specific segment only | No |
| Keep intermediate JSON | Keep `analysis.json` |
| Install strategy | `check-only` |
| pip mirror | None (only if user specifies) |

**Keyframe embedding override**: When the user requests keyframes in a template that doesn't have a `keyframe` column (e.g. music-director, script), the agent should pass `--embed-keyframes` to `build-xlsx` / `export-md` for the export step. The fill-in still uses the original template's perspective and columns. See Step 4 for details.

### Keyframe density (the agent suggests, the user confirms)

> **Do NOT present a video-type picklist.** Instead, the agent assesses what density is appropriate based on context (user's role, template, video description) and **proposes** a density level. The user confirms or adjusts.

**Four density levels:**

| Level | `--sample-interval` | What it captures | Typical use cases |
|---|---|---|---|
| **sparse** | 5–8s | Major narrative beats, scene/location changes, panel switches | Storyboard review, script discussion, live manga breakdown, podcast/tutorial structure, producer rough-cut review |
| **normal** | 2s (default) | Scene-level changes, character entrances, setup shifts, camera coverage | Director/editor collaboration, production coordination, ad review, game cinematic review, documentary structure |
| **dense** | 0.5–1s | Every cut, beat, sync point, rhythm change, choreography beat | Music scoring sync, trailer editing, MV direction, animation timing review, fight choreography, dance sequence |
| **frame-accurate** | Two-pass workflow (see below) | Every action, impact, transient, lip-sync frame, VFX event | Sound design breakdown, VFX shot detail, voice-over lip-sync, foley spotting, fight sound design |

> **Density is about WHAT NEEDS ITS OWN ROW, not about video type.** A short-film director may want `normal` for the whole film but `dense` for the climax fight. A sound designer may want `dense` as the base but `frame-accurate` on impact-heavy segments. Any role can use any density — the template's `recommended_density` is just the starting suggestion.

### Precision refinement (two-pass workflow)

> **This applies to ALL roles, not just sound designers.** Whenever the initial scan doesn't capture enough detail for specific segments, the agent should offer a precision re-scan.

**When to trigger:**
- User says *"this block needs more detail"* or *"the keyframes don't show the actual moment of X"*
- Template recommends `frame-accurate` (e.g. sound-design)
- User's role requires action-level precision for specific segments (VFX supervisor on a shot, VO director on a dialogue scene, editor on a montage)
- Agent notices a block spans a long time range but has complex visual content

**How it works (any density → higher density on selected segments):**
> 1. **Pass 1 (full-video scan)**: Run `scan-video` at the suggested density (sparse/normal/dense). Produces a complete cue sheet draft.
> 2. **Pass 1 deliverable**: Agent fills and exports the draft. User reviews it.
> 3. **User identifies segments needing more detail**: User marks specific time ranges — or agent suggests them based on block duration/complexity. Examples:
>    - Film director: *"00:45–00:52 needs per-cut detail for the fight"*
>    - Music director: *"the bridge at 01:20–01:35 needs beat-by-beat sync"*
>    - Sound designer: *"the explosion sequence 00:30–00:38 needs every foley event"*
>    - VFX supervisor: *"02:10–02:15 needs frame-level for the morphing shot"*
>    - VO director: *"the monologue 01:00–01:45 needs lip-sync level detail"*
> 4. **Pass 2 (precision re-scan)**: Run `scan-video` with `--start-time`/`--end-time` at a higher density (typically 0.25–0.5s). This produces a focused, manageable set of blocks.
> 5. **Pass 2 deliverable**: Agent fills the precision segments and delivers as a supplementary detail sheet or merged into the main cue sheet.

**Budget reality check** (why single-pass frame-accurate doesn't work):

| Video length | frame-accurate single-pass (0.25s) | Two-pass approach |
|---|---|---|
| 1 min | 240 blocks, 40 contact sheets → ❌ too many | Pass 1 dense: 60 blocks ✅ + Pass 2 on 3 segments: ~45 blocks ✅ |
| 2 min | 480 blocks → ❌ | Pass 1: ~120 blocks ✅ + Pass 2: ~45 blocks ✅ |
| 5 min | 1200 blocks → ❌❌ | Pass 1: ~300 blocks (split into 2 sessions) + Pass 2 on segments ✅ |

**The agent MUST use two-pass when `frame-accurate` is needed. Single-pass frame-accurate is never offered.**

### Density inference rules

The agent infers density from I1 (purpose), I2 (template), and context clues:

| Signal | Suggested density |
|---|---|
| Template has `recommended_density` field | Use that value |
| User mentions "storyboard", "manga", "rough cut", "structure" | sparse |
| User mentions "review", "collaboration", "production", "edit" | normal |
| User mentions "trailer", "MV", "music video", "choreography", "animation timing" | dense |
| User mentions "sound design", "foley", "VFX", "lip sync", "frame by frame" | frame-accurate (two-pass) |
| No clear signal from context | Use template's `recommended_density`, or `normal` as fallback |

**Agent presents the suggestion as part of the Step 0 confirmation, not as a separate question:**

> "Using `production` template, keyframes embedded. I'd suggest **normal** density (keyframe every 2s) for scene-level coverage. If specific segments need more detail, we can do a precision re-scan after the first pass. OK?"

> "Using `sound-design` template, content in 中文. I'd suggest **dense** as the base scan (0.5s interval), then **precision re-scan** on segments you flag for foley detail. OK, or start with normal first?"

The user says "ok" → proceed. The user says "this is a storyboard, sparse is fine" → adjust.

**Length-based adjustments:**

| Duration | Adjustment |
|---|---|
| 0–3 min | Use the density level as-is. Two-pass if frame-accurate. |
| 3–8 min | Warn if dense produces many blocks (100+). Two-pass if frame-accurate. |
| 8–20 min | For dense: suggest full scan OR segment-first. Two-pass mandatory for frame-accurate — user selects segments after Pass 1. |
| 20+ min | Structural pass first (sparse/normal). User picks segments for dense re-scan. Frame-accurate only on user-selected segments. |

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
| **Windows** | "Run `cuesheet-creator install-ffmpeg` to auto-download FFmpeg (shows download progress). If that doesn't work, download the **essentials build** zip from https://www.gyan.dev/ffmpeg/builds/ and extract it under `<skill-root>/tools/ffmpeg/`. No PATH changes needed. Let me know when it's done and I'll verify." |
| **macOS** | "Run `brew install ffmpeg` in Terminal. Let me know when it's done and I'll verify." |
| **Linux** | "Run `sudo apt install ffmpeg` (or the equivalent for your distro). Let me know when it's done and I'll verify." |

**After user confirms**, re-run:

```bash
python scripts/cuesheet_creator.py selfcheck
```

Look for `ffmpeg : OK [source]` and `ffprobe: OK [source]` in the output.

**Round 2 — only if Round 1 failed (user says they did it but selfcheck still shows MISSING):**

Troubleshoot in this order:

1. **Windows portable**: Did they extract to the right location? `<skill-root>/tools/ffmpeg/` should contain either `bin/ffmpeg.exe` directly or `<release-folder>/bin/ffmpeg.exe` one level down.
2. **macOS/Linux package install**: The install command might have succeeded but the current shell session doesn't see it yet. Tell the user: "Please close this terminal window and open a new one, then let me know." (Concrete action, not abstract "PATH" concepts.)
3. **Direct path override** (escape hatch — offer only if steps above didn't resolve):

```bash
python scripts/cuesheet_creator.py --ffmpeg-path /full/path/to/ffmpeg --ffprobe-path /full/path/to/ffprobe selfcheck
```

**Round 3 — only if user explicitly asks for alternatives:**

Offer package manager install: `winget install Gyan.FFmpeg` / `scoop install ffmpeg` / `choco install ffmpeg`. After install, tell the user: "Please close this PowerShell window and open a new one, then let me know — I'll re-check."

**Key principle:** Never dump all options at once. One instruction → verify → next fallback only if needed.

Post-check rules:

- `ffmpeg` / `ffprobe` missing → **Stop**, provide install guidance as above.
- Required Python packages missing → Based on user choice, stop at check or continue installing.
- SceneDetect missing → **Continue** (histogram fallback works), but mention to the user: "Scene detection is using basic mode. If your video has many dissolves or gradual transitions, installing scenedetect can improve accuracy. Want me to install it?" If user says yes, run `prepare-env --mode install-scene --out-dir <out-dir>` and re-run scan-video.
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

> **CRITICAL — Before starting, run the Runtime capability assessment** (see Agent Contract above) to select Tier 1, 2, or 3. Do NOT start reading images until you have confirmed which tier you are using.

> **CRITICAL — JSON fill-in workflow**: Edit `draft_fill.json`, NOT the Markdown table.

> **Contact sheets**: `scan-video` now generates **contact sheet images** — one per batch, each containing a grid of all keyframe thumbnails for that batch with block ID labels. These are listed in `agent_summary.contact_sheets`. **Use contact sheets instead of individual keyframes** to reduce tool calls from N to N/batch_size.

**Tier 1 (full visual) — default when step budget allows:**
> 1. Read `agent_summary` from `analysis.json` (NOT the full file — just the `agent_summary` field)
> 2. Check `agent_summary.contact_sheets` — if available, read ONE contact sheet image per batch (each shows ~6 keyframes in a labeled grid). If contact sheets are missing (e.g. older analysis.json), fall back to reading individual keyframes in batches.
> 3. For each batch, fill in ALL corresponding blocks in `draft_fill.json` in one write pass
> 4. After ALL blocks are filled, update `fill_status` from `"partial"` (or `"pending"`) to `"complete"`
>
> **Tool call budget with contact sheets**: For a 26-block cue sheet with 5 batches, this is 1 (read agent_summary) + 5 (read contact sheets) + 5 (write batches) + 1 (update fill_status) = **12 tool calls total**, down from 30+.

**Tier 2 (batch-compressed) — when step budget is tight:**
> 1. Read `agent_summary` from `analysis.json`
> 2. Read ALL contact sheet images in ONE parallel tool call batch (all read_file calls at once)
> 3. Fill ALL blocks in `draft_fill.json` in ONE write pass
> 4. Update `fill_status` to `"complete"`
>
> **Tool call budget**: 1 (read agent_summary) + 1 turn with N parallel reads + 1 (write all blocks) + 1 (update fill_status) = **4 turns total**.

**Tier 3 (data-informed) — when image viewing unavailable or step budget critically low:**
> 1. Read `agent_summary` from `analysis.json` (includes `visual_features`, `motion_hint`, ASR, OCR for each block)
> 2. Fill fields using ONLY the data available (see Tier 3 constraints in Runtime capability assessment)
> 3. Update `fill_status` to `"data-only"`

> Note: some fields already have auto-generated content (e.g. `important_dialogue` from ASR, `mood` with `[visual: ...]` hints, `confidence`). The LLM should **incorporate or replace** these — they are hints, not final content.
>
> **Why JSON instead of Markdown**: JSON fields avoid column-misalignment bugs from Markdown pipe characters. LLM can target specific fields without counting table columns. The filled JSON can feed directly into `build-final-skeleton` and `validate-cue-json`.
>
> The goal is to minimize tool calls. A 26-block cue sheet should take **5-6 turns** (Tier 1 with contact sheets) or **4 turns** (Tier 2), not 30+.

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

### Step 4: Export draft deliverables (Excel-first)

> **Show the user something tangible before asking questions.** Generate the full Excel + Markdown deliverables with `temp:` markers, then present them. This is more useful than an abstract naming table.

**Generate draft export** (with temp: markers, before naming confirmation):

```bash
# Generate final_cues.json from filled draft
python scripts/cuesheet_creator.py build-final-skeleton --source-json <out-dir>/draft_fill.json --output <out-dir>/final_cues.json

# Export Excel (with temp: markers visible)
python scripts/cuesheet_creator.py build-xlsx --cue-json <out-dir>/final_cues.json --output <out-dir>/cue_sheet.xlsx --base-dir <out-dir>

# Export Markdown
python scripts/cuesheet_creator.py export-md --cue-json <out-dir>/final_cues.json --output <out-dir>/cue_sheet.md
```

**Present the deliverable to the user** (this is checkpoint **C2**):

If `fill_status` was `"complete"` (Tier 1 or 2):
> "Here's the draft Cue Sheet. Temporary names (temp: xxx) haven't been replaced yet. Take a look at the overall structure and content first.
> Want to replace the temporary names? Or use this version as-is?"

If `fill_status` was `"data-only"` (Tier 3):
> "Here's the draft Cue Sheet — filled using algorithm analysis data only (no visual keyframe review was performed). Fields marked `[data-only: requires visual confirmation]` need manual review. The mood/motion fields are based on computed visual features and may be approximate.
> Options: (1) Review and correct specific blocks, (2) Accept as-is for now, (3) Re-run with visual review if you can provide a shorter video segment."

### Step 4b: Naming refinement (optional, only if user provides names)

If user provides naming overrides, apply them and re-export:

```bash
# Apply naming overrides
python scripts/cuesheet_creator.py apply-naming --overrides <naming_overrides.json> --cue-json <final_cues.json> --md <cue_sheet.md>

# Re-export Excel with confirmed names
python scripts/cuesheet_creator.py build-xlsx --cue-json <out-dir>/final_cues.json --output <out-dir>/cue_sheet.xlsx --base-dir <out-dir>
```

If user says "use as-is" or "skip naming" → deliver the current version as-is. Note unconfirmed items in the pending column.

If user doesn't respond → Allow continuation, keep "temp:" markers in final, explicitly list unconfirmed items in the pending column.

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

> **After merge (or if merge is skipped)**: proceed directly to **Step 4: Export draft deliverables**. The old separate "Generate final structure JSON" and "Export final deliverables" steps are now combined in Step 4.

### Validate before export

Always validate before exporting. Step 4 should run validation as part of the export flow:

```bash
python scripts/cuesheet_creator.py validate-cue-json --cue-json <out-dir>/final_cues.json --base-dir <out-dir> --check-files
```

Validates: time continuity, required field completeness, temp-name marker consistency, template field matching, keyframe file existence (with `--check-files`).

> **CRITICAL for agents**: Both `build-xlsx` and `export-md` are **single CLI commands** that handle everything internally — including keyframe embedding into Excel. Do NOT attempt to embed images manually or process keyframes one-by-one in the conversation. Just run the command and let it finish.

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
python scripts/cuesheet_creator.py save-template --input <template.json>
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
| `validate-cue-json` | Structural validation (time, required fields, duplicates) + quality warnings (empty recommended fields, temp-name consistency) + delivery readiness check. `Valid: YES` means no structural errors; `Delivery ready: YES` means all required fields are filled, all temp: markers have matching needs_confirmation entries, and keyframe files exist (with `--check-files`). Empty recommended fields generate warnings but do not block delivery. |
| `export-md` | Generate Markdown final from final_cues.json |
| `build-xlsx` | Generate Excel final from final_cues.json |
| `list-templates` | List all available templates (built-in + custom) with name, description, strategy, column count, and source. |
| `show-template` | Show full details of a template: columns, segmentation strategy, split triggers, merge bias, keyframe priority, perspective, fill guidance. |
| `save-template` | Validate and save a template JSON to `templates/custom/`. Validates schema, checks required fields, saves on success. Use `--overwrite` to replace existing. |
| `delete-template` | Delete a custom template. Built-in templates cannot be deleted. |
