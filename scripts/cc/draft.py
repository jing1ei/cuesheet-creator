"""Draft generation from analysis data."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from cc.constants import TEMPLATE_COLUMNS
from cc.naming import _get_naming_fields_from_template
from cc.templates import (
    get_template_definition,
    get_template_fill_guidance,
    get_template_perspective,
    get_template_prefill_map,
    get_template_segmentation,
)
from cc.utils import ensure_parent, read_json, relpath_for_markdown, write_json


def cmd_draft_from_analysis(args: "argparse.Namespace") -> int:  # noqa: F821, C901
    analysis_path = Path(args.analysis_json)
    if not analysis_path.exists():
        raise FileNotFoundError(f"analysis.json not found: {analysis_path}")

    analysis = read_json(analysis_path)
    output_path = Path(args.output)
    ensure_parent(output_path)

    video = analysis.get("video", {})
    blocks = analysis.get("draft_blocks", [])
    notes = analysis.get("notes", [])
    asr_data = analysis.get("asr", {})
    ocr_data = analysis.get("ocr", {})
    agent_summary = analysis.get("agent_summary", {})
    template = args.template

    # Validate template up front — fail before writing any artifacts
    if template not in TEMPLATE_COLUMNS:
        available = ", ".join(sorted(TEMPLATE_COLUMNS.keys()))
        print(f"ERROR: Unknown template '{template}'. Available templates: {available}", file=sys.stderr)
        return 1

    if not blocks:
        print("ERROR: No draft blocks found in analysis.json. "
              "Cannot generate draft. Check scan-video output.", file=sys.stderr)
        return 1

    # --- Template-driven column definitions for the draft Markdown table ---
    _STRUCTURAL_DRAFT_KEYS = {"shot_block", "start_time", "end_time"}
    _DATA_DERIVED_DRAFT_KEYS = {"confidence", "needs_confirmation"}

    def _build_draft_columns(tmpl_name: str) -> list[tuple[str, str]]:
        """Build draft Markdown column tuples from template definition."""
        tmpl_def = get_template_definition(tmpl_name)
        if tmpl_def and "columns" in tmpl_def:
            cols: list[tuple[str, str]] = []
            for col in tmpl_def["columns"]:
                field = col.get("field", "")
                label = col.get("label", field)
                if field in _STRUCTURAL_DRAFT_KEYS:
                    cols.append((label, field))
                elif field == "keyframe":
                    cols.append((label, "_keyframe"))
                elif field in _DATA_DERIVED_DRAFT_KEYS:
                    cols.append((label, f"_{field}"))
                else:
                    cols.append((label, "_placeholder"))
            cols.append(("Cut Reason", "cut_reason"))
            return cols
        field_list = TEMPLATE_COLUMNS.get(tmpl_name, TEMPLATE_COLUMNS.get("production", []))
        cols = []
        for field in field_list:
            if field in _STRUCTURAL_DRAFT_KEYS:
                cols.append((field, field))
            elif field == "keyframe":
                cols.append(("Keyframe", "_keyframe"))
            elif field in _DATA_DERIVED_DRAFT_KEYS:
                cols.append((field, f"_{field}"))
            else:
                cols.append((field, "_placeholder"))
        cols.append(("Cut Reason", "cut_reason"))
        return cols

    draft_cols = _build_draft_columns(template)

    lines: list[str] = []
    lines.append(f"# Cue Sheet Draft ({template})")
    lines.append("")

    # --- Video info ---
    lines.append("## Video Info")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Source | `{video.get('source_path', '')}` |")
    lines.append(f"| Duration | {video.get('duration_timecode', '')} |")
    res = video.get("resolution", {})
    lines.append(f"| Resolution | {res.get('width', '')}x{res.get('height', '')} |")
    lines.append(f"| FPS | {video.get('fps', '')} |")
    lines.append(f"| Audio tracks | {video.get('audio_tracks', '')} |")
    eff_range = analysis.get("analysis_config", {}).get("effective_range", {})
    if eff_range.get("is_clip"):
        lines.append(f"| **Analysis range** | {eff_range.get('start_time', '')} -- {eff_range.get('end_time', '')} (clip-only) |")
    lines.append("")

    # --- Keyframe batch plan ---
    keyframe_batches = agent_summary.get("keyframe_batches", [])
    if not keyframe_batches:
        KEYFRAME_BATCH_SIZE = 6
        all_kf = [b.get("keyframe") for b in blocks if b.get("keyframe")]
        keyframe_batches = [all_kf[i:i + KEYFRAME_BATCH_SIZE] for i in range(0, len(all_kf), KEYFRAME_BATCH_SIZE)]

    if keyframe_batches:
        lines.append("## Keyframe Batches for Fill-in")
        lines.append("")
        lines.append("> **Agent instruction**: View keyframes in these batches (not one-by-one).")
        lines.append("> After viewing each batch, fill in ALL corresponding blocks in the JSON fill-in file.")
        lines.append("")
        for batch_idx, batch in enumerate(keyframe_batches, start=1):
            paths_display = ", ".join(Path(p).name for p in batch)
            block_ids = []
            for b in blocks:
                kf = b.get("keyframe")
                if kf and str(kf) in batch:
                    block_ids.append(b["shot_block"])
            lines.append(f"- **Batch {batch_idx}** (blocks {', '.join(block_ids)}): `{paths_display}`")
        lines.append("")

    # --- Candidate segments table ---
    lines.append(f"## Candidate Segments ({template})")
    lines.append("")
    header = "| " + " | ".join(col[0] for col in draft_cols) + " |"
    separator = "|" + "|".join(["---"] * len(draft_cols)) + "|"
    lines.append(header)
    lines.append(separator)

    for block in blocks:
        cells: list[str] = []
        for _col_label, col_key in draft_cols:
            if col_key == "shot_block":
                cells.append(block.get("shot_block", ""))
            elif col_key == "start_time":
                cells.append(block.get("start_time", ""))
            elif col_key == "end_time":
                cells.append(block.get("end_time", ""))
            elif col_key == "_keyframe":
                img_rel = relpath_for_markdown(block.get("keyframe"), output_path)
                cells.append(f"![kf]({img_rel})" if img_rel else "*(no keyframe)*")
            elif col_key == "cut_reason":
                cells.append(block.get("cut_reason", ""))
            elif col_key == "_confidence":
                score = block.get("candidate_score")
                cells.append("high" if isinstance(score, (int, float)) and score >= 0.8 else "medium")
            elif col_key == "_needs_confirmation":
                cells.append("*(pending)*")
            elif col_key == "_placeholder":
                cells.append("*(pending)*")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # --- Fill-in guidance ---
    lines.append("## Fill-in Guidance")
    lines.append("")
    lines.append("> **IMPORTANT**: Use the JSON fill-in file (`draft_fill.json`) instead of editing this Markdown table.")
    lines.append("> The JSON file was generated alongside this draft. Fill in the empty fields there,")
    lines.append("> then the final export steps will consume the JSON directly.")
    lines.append("")
    tmpl_guidance = get_template_fill_guidance(template)
    if tmpl_guidance:
        lines.append("For each block, fill in these fields in `draft_fill.json`:")
        for g in tmpl_guidance:
            lines.append(f"- {g}")
    else:
        content_cols = [
            col for col in TEMPLATE_COLUMNS.get(template, [])
            if col not in _STRUCTURAL_DRAFT_KEYS and col not in {"keyframe", "confidence", "needs_confirmation"}
        ]
        if content_cols:
            lines.append("For each block, fill in these fields in `draft_fill.json`:")
            for col in content_cols:
                lines.append(f"- **{col}**")
    lines.append("")

    # --- ASR Highlights ---
    asr_segments = asr_data.get("segments", [])
    if asr_segments:
        lines.append("## ASR Highlights")
        lines.append("")
        lines.append("| Start | End | Text |")
        lines.append("|---|---|---|")
        for seg in asr_segments[:30]:
            text = seg.get("text", "").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {seg.get('start_time', '')} | {seg.get('end_time', '')} | {text} |")
        if len(asr_segments) > 30:
            lines.append(f"| ... | ... | ({len(asr_segments) - 30} more segments in analysis.json) |")
        lines.append("")
    elif asr_data.get("status") == "not-run":
        lines.append("## ASR Highlights")
        lines.append("")
        lines.append("*ASR was not enabled for this scan. Re-run with `--asr` to include speech recognition.*")
        lines.append("")
    else:
        asr_status = asr_data.get("status", "unknown")
        asr_error = asr_data.get("error", "")
        lines.append("## ASR Highlights")
        lines.append("")
        lines.append(f"*ASR status: {asr_status}.* {asr_error}")
        lines.append("")

    # --- OCR Highlights ---
    ocr_detections = ocr_data.get("detections", [])
    if ocr_detections:
        lines.append("## OCR Highlights")
        lines.append("")
        lines.append("| Frame | Detected Text |")
        lines.append("|---|---|")
        for det in ocr_detections:
            frame_name = Path(det.get("frame", "")).name
            texts = "; ".join(det.get("texts", []))
            lines.append(f"| {frame_name} | {texts} |")
        lines.append("")
    elif ocr_data.get("status") == "not-run":
        lines.append("## OCR Highlights")
        lines.append("")
        lines.append("*OCR was not enabled for this scan. Re-run with `--ocr` to include text detection.*")
        lines.append("")
    elif ocr_data.get("status") == "ok-no-text":
        lines.append("## OCR Highlights")
        lines.append("")
        lines.append("*OCR completed successfully but no on-screen text was detected in the analyzed frames.*")
        lines.append("")
    else:
        ocr_status = ocr_data.get("status", "unknown")
        ocr_error = ocr_data.get("error", "")
        lines.append("## OCR Highlights")
        lines.append("")
        lines.append(f"*OCR status: {ocr_status}.* {ocr_error}")
        lines.append("")

    # --- Template-conditional scaffolding sections ---
    # Only emit Character/Scene/Prop summaries and naming tables if the template
    # actually has naming_field columns for those categories.
    tmpl_def = get_template_definition(template)
    naming_categories: set[str] = set()
    if tmpl_def and "columns" in tmpl_def:
        for col in tmpl_def["columns"]:
            if isinstance(col, dict) and col.get("naming_field"):
                cat = col.get("naming_category", "")
                if not cat:
                    # Fallback: infer category from field name when naming_category is absent
                    field = col.get("field", "")
                    if field in ("characters",):
                        cat = "characters"
                    elif field in ("scene", "location"):
                        cat = "scenes"
                    elif field in ("props",):
                        cat = "props"
                if cat:
                    naming_categories.add(cat)

    has_characters = "characters" in naming_categories
    has_scenes = "scenes" in naming_categories
    has_props = "props" in naming_categories
    has_any_naming = bool(naming_categories)

    if has_characters:
        lines.append("## Character Summary")
        lines.append("")
        lines.append("*(Fill based on keyframe analysis -- list all identified characters with brief visual description, "
                     "role in the analyzed segment, and evidence from specific blocks.)*")
        lines.append("")
        lines.append("| Temp Name | Visual Description | Appears in Blocks | Role / Notes |")
        lines.append("|---|---|---|---|")
        lines.append("| temp: Character-A | *(describe appearance)* | *(list blocks)* | *(role or behavior)* |")
        lines.append("")

    if has_scenes:
        lines.append("## Scene / Setup Summary")
        lines.append("")
        lines.append("*(Fill based on keyframe analysis -- list all identified locations or setups.)*")
        lines.append("")
        lines.append("| Temp Name | Space Description | Appears in Blocks | Notes |")
        lines.append("|---|---|---|---|")
        lines.append("| temp: Scene-A | *(describe space)* | *(list blocks)* | *(lighting, mood, notable features)* |")
        lines.append("")

    if has_props:
        lines.append("## Prop Summary")
        lines.append("")
        lines.append("*(Fill if any key props are identified in close-ups, handoffs, or repeated appearances.)*")
        lines.append("")
        lines.append("| Temp Name | Description | Appears in Blocks | Importance |")
        lines.append("|---|---|---|---|")
        lines.append("| temp: Prop-A | *(describe prop)* | *(list blocks)* | *(key-prop / background)* |")
        lines.append("")

    # --- Naming confirmation tables (only if template has naming fields) ---
    if has_any_naming:
        lines.append("## Naming Confirmation Tables")
        lines.append("")

        if has_characters:
            lines.append("### Characters")
            lines.append("")
            lines.append("| temporary_name | evidence | confidence | confirmed_name | status |")
            lines.append("|---|---|---|---|---|")
            lines.append("| temp: Character-A | Fill based on keyframe & behavior | low |  | pending |")
            lines.append("")

        if has_scenes:
            lines.append("### Scenes / Setups")
            lines.append("")
            lines.append("| temporary_setup | space_note | confidence | confirmed_setup | status |")
            lines.append("|---|---|---|---|---|")
            lines.append("| temp: Scene-A | Fill based on space & establishing shots | low |  | pending |")
            lines.append("")

        if has_props:
            lines.append("### Props")
            lines.append("")
            lines.append("| temporary_prop | importance | evidence | confirmed_prop | status |")
            lines.append("|---|---|---|---|---|")
            lines.append("| temp: Prop-A | key-prop? | Fill based on close-ups & repeated appearances |  | pending |")
            lines.append("")

    # --- Pending questions (template-aware) ---
    lines.append("## Pending Questions")
    lines.append("")
    if has_characters:
        lines.append("- Do characters have official names?")
    if has_scenes:
        lines.append("- Do scenes have internal project setup names?")
    if has_props:
        lines.append("- Do key props have standardized names?")
    lines.append(f"- Proceed with `{template}` template for final?")
    lines.append("- Export final Excel?")
    lines.append("")

    # --- Notes ---
    lines.append("## Notes & Fallback Info")
    lines.append("")
    if not notes:
        lines.append("- No additional notes.")
    else:
        for note in notes:
            lines.append(f"- {note}")
    lines.append("")

    # --- Next steps ---
    lines.append("## Next Steps")
    lines.append("")
    lines.append("1. View keyframes in batches listed above.")
    lines.append("2. Fill in empty fields in `draft_fill.json` (the JSON fill-in file generated alongside this draft).")
    lines.append("3. Confirm character / scene / prop names (or keep temp markers).")
    lines.append("4. Merge blocks using `merge-blocks` if needed.")
    lines.append("5. Generate `final_cues.json` (or use `build-final-skeleton`).")
    lines.append("6. Validate with `validate-cue-json`.")
    lines.append("7. Export with `build-xlsx` and `export-md`.")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")

    # --- Generate JSON fill-in file (draft_fill.json) ---
    fill_in_path = output_path.parent / "draft_fill.json"
    columns = TEMPLATE_COLUMNS[template]

    asr_segments = asr_data.get("segments", [])
    ocr_detections = ocr_data.get("detections", [])
    ocr_by_frame: dict[str, list[str]] = {}
    for det in ocr_detections:
        frame_path = det.get("frame", "")
        ocr_by_frame[frame_path] = det.get("texts", [])
        if frame_path:
            ocr_by_frame[Path(frame_path).name] = det.get("texts", [])

    detection_method = analysis.get("analysis_config", {}).get("detection_method", "histogram")
    asr_status = asr_data.get("status", "not-run")

    has_prefill = False
    fill_rows: list[dict[str, Any]] = []
    for block in blocks:
        row: dict[str, Any] = {}
        kf_raw = block.get("keyframe")
        kf_rel = ""
        if kf_raw:
            kf_path = Path(kf_raw)
            if kf_path.is_absolute():
                # Absolute path: compute relative to output directory
                try:
                    kf_rel = os.path.relpath(str(kf_path), str(output_path.parent)).replace("\\", "/")
                except Exception:
                    kf_rel = kf_path.name
            else:
                # Already relative (e.g. "keyframes/frame_0001.jpg" from scan-video):
                # normalize separators and keep as-is to avoid Windows relpath drift
                kf_rel = str(kf_path).replace("\\", "/")

        block_start = block.get("start_seconds", 0.0)
        block_end = block.get("end_seconds", 0.0)
        vf = block.get("visual_features") or {}

        prefill_map = get_template_prefill_map(template)

        for col in columns:
            prefill_src = prefill_map.get(col)

            if col == "shot_block":
                row[col] = block.get("shot_block", "")
            elif col == "start_time":
                row[col] = block.get("start_time", "")
            elif col == "end_time":
                row[col] = block.get("end_time", "")
            elif col == "keyframe":
                row[col] = kf_rel

            elif prefill_src == "asr" and asr_segments:
                overlapping = [
                    s for s in asr_segments
                    if s.get("start", 0) < block_end and s.get("end", 0) > block_start
                ]
                if overlapping:
                    row[col] = "; ".join(
                        f"[{s.get('start_time', '')}] {s.get('text', '')}" for s in overlapping
                    )
                    has_prefill = True
                else:
                    row[col] = ""

            elif prefill_src == "confidence":
                parts = []
                score = block.get("candidate_score")
                if detection_method == "scenedetect":
                    parts.append("segment=high")
                elif isinstance(score, (int, float)) and score >= 0.8:
                    parts.append("segment=high")
                else:
                    parts.append("segment=medium")
                if asr_status == "ok":
                    asr_overlap = any(
                        s.get("start", 0) < block_end and s.get("end", 0) > block_start
                        for s in asr_segments
                    )
                    parts.append("dialogue=high" if asr_overlap else "dialogue=low")
                elif asr_status != "not-run":
                    parts.append("dialogue=degraded")
                parts.append("names=low")
                row[col] = "; ".join(parts)
                has_prefill = True

            elif prefill_src == "needs_confirmation":
                naming_fields_set = _get_naming_fields_from_template(template)
                if naming_fields_set:
                    categories: set[str] = set()
                    tmpl_def = get_template_definition(template)
                    if tmpl_def and "columns" in tmpl_def:
                        for c in tmpl_def["columns"]:
                            if isinstance(c, dict) and c.get("naming_field"):
                                cat = c.get("naming_category", "")
                                if cat:
                                    categories.add(cat)
                    if not categories:
                        for f in naming_fields_set:
                            if f == "characters":
                                categories.add("character names")
                            elif f in ("scene", "location"):
                                categories.add("scene names")
                            else:
                                categories.add(f"{f} names")
                    else:
                        categories = {f"{c.rstrip('s')} names" for c in categories}
                    row[col] = "; ".join(sorted(categories))
                    has_prefill = True
                else:
                    row[col] = ""

            elif prefill_src == "visual_mood" and vf:
                hints = []
                if vf.get("tone"):
                    hints.append(f"{vf['tone']} tones")
                if vf.get("color_temp") and vf["color_temp"] != "neutral":
                    hints.append(f"{vf['color_temp']} color")
                if vf.get("contrast", 0) > 70:
                    hints.append("high contrast")
                elif vf.get("contrast", 0) < 30:
                    hints.append("low contrast")
                if vf.get("saturation", 0) < 40:
                    hints.append("desaturated")
                elif vf.get("saturation", 0) > 150:
                    hints.append("vivid")
                if hints:
                    row[col] = f"[visual: {', '.join(hints)}] "
                    has_prefill = True
                else:
                    row[col] = ""

            else:
                motion_data = block.get("motion_hint")
                if col == "motion" and motion_data and isinstance(motion_data, dict):
                    hint = motion_data.get("motion_hint", "uncertain")
                    conf = motion_data.get("motion_confidence", 0)
                    if hint == "likely-static" and conf >= 0.5:
                        row[col] = "[motion-hint: likely-static] "
                        has_prefill = True
                    elif hint == "likely-camera-move":
                        row[col] = "[motion-hint: likely-camera-move] "
                        has_prefill = True
                    elif hint == "uncertain":
                        row[col] = "[motion-hint: uncertain] "
                        has_prefill = True
                    else:
                        row[col] = ""
                elif kf_raw and ocr_by_frame:
                    kf_name = Path(kf_raw).name if kf_raw else ""
                    ocr_texts = ocr_by_frame.get(str(kf_raw), []) or ocr_by_frame.get(kf_name, [])
                    if ocr_texts and col in ("director_note", "event"):
                        row[col] = f"[OCR detected: {'; '.join(ocr_texts[:3])}] "
                        has_prefill = True
                    else:
                        row[col] = ""
                else:
                    row[col] = ""
        fill_rows.append(row)

    fill_status = "partial" if has_prefill else "pending"
    seg = get_template_segmentation(template)
    perspective = get_template_perspective(template)
    template_context: dict[str, Any] = {}
    if perspective:
        template_context["perspective"] = perspective
    if seg:
        template_context["segmentation_strategy"] = seg.get("strategy", "")
        if seg.get("split_triggers"):
            template_context["split_triggers"] = seg["split_triggers"]
        if seg.get("keyframe_priority"):
            template_context["keyframe_priority"] = seg["keyframe_priority"]
        if seg.get("merge_bias"):
            template_context["merge_bias"] = seg["merge_bias"]

    fill_data = {
        "_instructions": (
            "Fill in the empty string fields for each block based on keyframe analysis. "
            "Fields starting with '[visual: ...]' or '[OCR detected: ...]' contain auto-generated hints -- "
            "incorporate or replace them with your analysis. "
            "Do NOT modify shot_block, start_time, end_time, or keyframe. "
            "Use 'temp: xxx' for unconfirmed names. "
            "After filling, this file can be used directly as input to build-final-skeleton or validate-cue-json."
        ),
        "template": template,
        "template_context": template_context if template_context else None,
        "video_title": Path(video.get("source_path", "untitled")).stem if video.get("source_path") else "untitled",
        "source_path": video.get("source_path", ""),
        "fill_status": fill_status,
        "rows": fill_rows,
    }
    write_json(fill_in_path, fill_data)

    summary = {
        "status": "ok",
        "stage": "draft-from-analysis",
        "template": template,
        "output_markdown": str(output_path),
        "output_fill_json": str(fill_in_path),
        "block_count": len(blocks),
        "fill_status": fill_status,
    }
    if hasattr(args, "output_format") and args.output_format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(str(output_path))
        print(f"JSON fill-in file: {fill_in_path}")
    return 0


__all__ = ["cmd_draft_from_analysis"]
