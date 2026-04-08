"""Block merging and continuity scoring."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from cc.templates import get_template_segmentation
from cc.utils import format_seconds, make_block_id, read_json, write_json


def _strategy_weight_multipliers(strategy: str) -> dict[str, float]:
    """Return weight multipliers for continuity scoring based on segmentation strategy."""
    if strategy == "emotional-arc":
        return {
            "visual_similarity": 1.2, "cut_weakness": 0.6,
            "same_tone": 1.5, "same_color_temp": 1.5,
            "asr_continuity": 0.8, "short_block_bonus": 1.0,
        }
    if strategy == "action-event":
        return {
            "visual_similarity": 0.7, "cut_weakness": 0.8,
            "same_tone": 0.8, "same_color_temp": 0.5,
            "asr_continuity": 1.5, "short_block_bonus": 1.2,
        }
    if strategy == "narrative-beat":
        return {
            "visual_similarity": 0.9, "cut_weakness": 1.0,
            "same_tone": 1.0, "same_color_temp": 0.8,
            "asr_continuity": 1.3, "short_block_bonus": 1.0,
        }
    return {
        "visual_similarity": 1.0, "cut_weakness": 1.0,
        "same_tone": 1.0, "same_color_temp": 1.0,
        "asr_continuity": 1.0, "short_block_bonus": 1.0,
    }


def compute_block_continuity(
    block_a: dict[str, Any],
    block_b: dict[str, Any],
    asr_segments: list[dict[str, Any]],
    threshold: float = 0.65,
    strategy: str = "scene-cut",
) -> dict[str, Any]:
    """Compute a continuity score between two adjacent blocks."""
    scores: dict[str, float] = {}

    vf_a = block_a.get("visual_features") or {}
    vf_b = block_b.get("visual_features") or {}
    if vf_a and vf_b:
        brightness_diff = abs(vf_a.get("brightness", 128) - vf_b.get("brightness", 128)) / 255.0
        contrast_diff = abs(vf_a.get("contrast", 50) - vf_b.get("contrast", 50)) / 128.0
        saturation_diff = abs(vf_a.get("saturation", 50) - vf_b.get("saturation", 50)) / 255.0
        hue_diff = abs(vf_a.get("dominant_hue", 90) - vf_b.get("dominant_hue", 90)) / 180.0
        visual_sim = 1.0 - (brightness_diff * 0.3 + contrast_diff * 0.2 + saturation_diff * 0.2 + hue_diff * 0.3)
        scores["visual_similarity"] = round(max(visual_sim, 0.0), 3)
        scores["same_tone"] = 1.0 if vf_a.get("tone") == vf_b.get("tone") else 0.0
        scores["same_color_temp"] = 1.0 if vf_a.get("color_temp") == vf_b.get("color_temp") else 0.0
    else:
        scores["visual_similarity"] = 0.5

    b_score = block_b.get("candidate_score")
    if isinstance(b_score, (int, float)):
        scores["cut_weakness"] = round(1.0 - min(b_score, 1.0), 3)
    else:
        scores["cut_weakness"] = 0.5

    boundary = block_a.get("end_seconds", 0.0)
    tolerance = 1.0
    asr_spans = any(
        s.get("start", 0) < boundary + tolerance and s.get("end", 0) > boundary - tolerance
        for s in asr_segments
    )
    scores["asr_continuity"] = 1.0 if asr_spans else 0.0

    dur_a = block_a.get("end_seconds", 0) - block_a.get("start_seconds", 0)
    dur_b = block_b.get("end_seconds", 0) - block_b.get("start_seconds", 0)
    short_block = dur_a < 1.5 or dur_b < 1.5
    scores["short_block_bonus"] = 0.3 if short_block else 0.0

    mults = _strategy_weight_multipliers(strategy)
    base_weights = {
        "visual_similarity": 0.35, "cut_weakness": 0.25,
        "same_tone": 0.10, "same_color_temp": 0.05,
        "asr_continuity": 0.15, "short_block_bonus": 0.10,
    }
    raw_total = 0.0
    weight_sum = 0.0
    for key, base_w in base_weights.items():
        adjusted_w = base_w * mults.get(key, 1.0)
        raw_total += scores.get(key, 0) * adjusted_w
        weight_sum += adjusted_w
    total = raw_total / weight_sum if weight_sum > 0 else 0.0

    return {
        "block_a": block_a.get("shot_block", ""),
        "block_b": block_b.get("shot_block", ""),
        "continuity_score": round(total, 3),
        "component_scores": scores,
        "suggest_merge": total >= threshold,
    }


def cmd_suggest_merges(args: "argparse.Namespace") -> int:  # noqa: F821
    """Compute inter-block continuity scores and suggest merge candidates."""
    analysis_path = Path(args.analysis_json)
    if not analysis_path.exists():
        raise FileNotFoundError(f"analysis.json not found: {analysis_path}")

    analysis = read_json(analysis_path)
    draft_blocks = analysis.get("draft_blocks", [])
    asr_segments = analysis.get("asr", {}).get("segments", [])

    if len(draft_blocks) < 2:
        print("Not enough blocks to suggest merges (need at least 2).", file=sys.stderr)
        return 0

    threshold = float(args.threshold) if hasattr(args, "threshold") and args.threshold else 0.65

    template_name = getattr(args, "template", None)
    if not template_name:
        draft_fill_path = analysis_path.parent / "draft_fill.json"
        if draft_fill_path.exists():
            try:
                draft_fill = read_json(draft_fill_path)
                template_name = draft_fill.get("template")
            except Exception:
                pass
    if not template_name:
        template_name = "production"
    seg = get_template_segmentation(template_name)
    strategy = seg.get("strategy", "scene-cut") if seg else "scene-cut"

    pairs: list[dict[str, Any]] = []
    for i in range(len(draft_blocks) - 1):
        pair = compute_block_continuity(
            draft_blocks[i], draft_blocks[i + 1], asr_segments,
            threshold=threshold, strategy=strategy,
        )
        pairs.append(pair)

    merge_groups: list[dict[str, Any]] = []
    current_group: list[str] = [draft_blocks[0]["shot_block"]]
    current_reasons: list[str] = []

    for pair in pairs:
        if pair["suggest_merge"]:
            current_group.append(pair["block_b"])
            scores = pair["component_scores"]
            reasons = []
            if scores.get("visual_similarity", 0) > 0.7:
                reasons.append("visually similar")
            if scores.get("asr_continuity", 0) > 0:
                reasons.append("dialogue spans boundary")
            if scores.get("short_block_bonus", 0) > 0:
                reasons.append("short block")
            if scores.get("cut_weakness", 0) > 0.6:
                reasons.append("weak cut boundary")
            current_reasons.extend(reasons)
        else:
            if len(current_group) > 1:
                merge_groups.append({
                    "source_blocks": current_group, "new_id": current_group[0],
                    "keyframe": None,
                    "reason": f"auto-suggested: {'; '.join(set(current_reasons)) if current_reasons else 'high continuity score'}",
                    "confidence": "auto",
                })
            current_group = [pair["block_b"]]
            current_reasons = []

    if len(current_group) > 1:
        merge_groups.append({
            "source_blocks": current_group, "new_id": current_group[0],
            "keyframe": None,
            "reason": f"auto-suggested: {'; '.join(set(current_reasons)) if current_reasons else 'high continuity score'}",
            "confidence": "auto",
        })

    merged_ids = set()
    for g in merge_groups:
        merged_ids.update(g["source_blocks"])
    singletons = [b["shot_block"] for b in draft_blocks if b["shot_block"] not in merged_ids]
    for sid in singletons:
        merge_groups.append({
            "source_blocks": [sid], "new_id": sid, "keyframe": None,
            "reason": "no merge suggested — keep as separate block", "confidence": "auto",
        })

    for idx, group in enumerate(merge_groups, start=1):
        group["new_id"] = make_block_id(idx)

    output = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "_instructions": (
            "This is an AUTO-GENERATED merge suggestion based on visual continuity scoring. "
            "The LLM should REVIEW and ADJUST this plan before passing to merge-blocks. "
            "Specifically: check that narrative function boundaries are respected "
            "(scene changes, flashback transitions, format changes should NOT be merged)."
        ),
        "threshold": threshold,
        "total_blocks": len(draft_blocks),
        "suggested_merge_groups": len([g for g in merge_groups if len(g["source_blocks"]) > 1]),
        "pairwise_scores": pairs,
        "merges": merge_groups,
    }

    output_path = Path(args.output)
    write_json(output_path, output)

    merged_count = sum(1 for g in merge_groups if len(g["source_blocks"]) > 1)
    kept_count = sum(1 for g in merge_groups if len(g["source_blocks"]) == 1)
    summary = {
        "status": "ok", "stage": "suggest-merges", "output": str(output_path),
        "threshold": threshold, "total_blocks": len(draft_blocks),
        "suggested_merge_groups": merged_count, "kept_separate": kept_count,
    }
    if hasattr(args, "output_format") and args.output_format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Suggested merge plan: {merged_count} merge group(s), {kept_count} kept separate.")
        print(f"Output: {output_path}")
        if merged_count > 0:
            print("Merge suggestions:")
            for g in merge_groups:
                if len(g["source_blocks"]) > 1:
                    print(f"  {' + '.join(g['source_blocks'])} -> {g['new_id']} ({g['reason']})")
        print("NOTE: LLM should review this plan for narrative-function boundaries before executing.")
    return 0


def cmd_merge_blocks(args: "argparse.Namespace") -> int:  # noqa: F821
    """Merge draft blocks based on a merge plan."""
    analysis_path = Path(args.analysis_json)
    if not analysis_path.exists():
        raise FileNotFoundError(f"analysis.json not found: {analysis_path}")
    merge_plan_path = Path(args.merge_plan)
    if not merge_plan_path.exists():
        raise FileNotFoundError(f"Merge plan not found: {merge_plan_path}")

    analysis = read_json(analysis_path)
    merge_plan = read_json(merge_plan_path)
    draft_blocks = analysis.get("draft_blocks", [])
    block_lookup: dict[str, dict[str, Any]] = {b["shot_block"]: b for b in draft_blocks}
    all_source_ids: set[str] = set(block_lookup.keys())

    merges = merge_plan.get("merges", [])
    errors: list[str] = []
    warnings: list[str] = []
    referenced_ids: list[str] = []
    seen_new_ids: set[str] = set()

    for idx, group in enumerate(merges):
        source_ids = group.get("source_blocks", [])
        new_id = group.get("new_id", f"A{idx+1}")
        if new_id in seen_new_ids:
            errors.append(f"Merge group {idx+1}: duplicate new_id '{new_id}'.")
        seen_new_ids.add(new_id)
        if not source_ids:
            errors.append(f"Merge group {idx+1} ('{new_id}'): source_blocks is empty.")
        for sid in source_ids:
            if sid not in block_lookup:
                errors.append(f"Merge group {idx+1} ('{new_id}'): source block '{sid}' not found in analysis.")
            if sid in referenced_ids:
                errors.append(f"Merge group {idx+1} ('{new_id}'): source block '{sid}' already used in another group.")
            referenced_ids.append(sid)

    unreferenced = all_source_ids - set(referenced_ids)
    strict = bool(args.strict) if hasattr(args, "strict") else False
    if unreferenced:
        if strict:
            errors.append(f"Blocks not referenced in merge plan: {', '.join(sorted(unreferenced))}. In strict mode this is an error.")
        else:
            warnings.append(f"Blocks not referenced in merge plan: {', '.join(sorted(unreferenced))}. They will be auto-appended as unmerged blocks.")

    if errors:
        report = {"generated_at": dt.datetime.now().isoformat(timespec="seconds"), "valid": False, "errors": errors, "warnings": warnings}
        if args.output:
            write_json(Path(args.output), report)
        print("=== merge-blocks validation FAILED ===", file=sys.stderr)
        for e in errors:
            print(f"  \u2717 {e}", file=sys.stderr)
        for w in warnings:
            print(f"  \u26a0 {w}", file=sys.stderr)
        return 1

    merged_blocks: list[dict[str, Any]] = []
    for idx, group in enumerate(merges, start=1):
        source_ids = group.get("source_blocks", [])
        new_id = group.get("new_id", f"A{idx}")
        sources = [block_lookup[sid] for sid in source_ids if sid in block_lookup]
        if not sources:
            continue
        start_seconds = min(s["start_seconds"] for s in sources)
        end_seconds = max(s["end_seconds"] for s in sources)
        # Pick keyframe: explicit override > sharpest source frame > first source
        keyframe = group.get("keyframe")
        if not keyframe:
            best_src = max(
                sources,
                key=lambda s: (s.get("visual_features") or {}).get("sharpness", 0),
            )
            keyframe = best_src.get("keyframe") or sources[0].get("keyframe")
        merged_blocks.append({
            "shot_block": new_id,
            "start_seconds": start_seconds, "start_time": format_seconds(start_seconds),
            "end_seconds": end_seconds, "end_time": format_seconds(end_seconds),
            "keyframe": keyframe, "source_blocks": source_ids,
            "merge_reason": group.get("reason", ""),
        })

    if unreferenced and not strict:
        unref_blocks = sorted(
            [block_lookup[sid] for sid in unreferenced if sid in block_lookup],
            key=lambda b: b["start_seconds"],
        )
        for block in unref_blocks:
            merged_blocks.append({
                "shot_block": block["shot_block"],
                "start_seconds": block["start_seconds"], "start_time": block["start_time"],
                "end_seconds": block["end_seconds"], "end_time": block["end_time"],
                "keyframe": block.get("keyframe"), "source_blocks": [block["shot_block"]],
                "merge_reason": "auto-appended: not referenced in merge plan", "unmerged": True,
            })

    # Sort all merged blocks by timeline before validation and output.
    # This prevents false overlap warnings when the merge plan is valid
    # but its groups are not in chronological order.
    merged_blocks.sort(key=lambda b: (b["start_seconds"], b["end_seconds"]))

    for i in range(1, len(merged_blocks)):
        prev_end = merged_blocks[i - 1]["end_seconds"]
        curr_start = merged_blocks[i]["start_seconds"]
        if curr_start < prev_end - 0.05:
            msg = (
                f"Block '{merged_blocks[i]['shot_block']}' starts at {merged_blocks[i]['start_time']} "
                f"which overlaps with previous block ending at {merged_blocks[i-1]['end_time']}."
            )
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)

    if errors:
        report = {"generated_at": dt.datetime.now().isoformat(timespec="seconds"), "valid": False, "strict": strict, "errors": errors, "warnings": warnings}
        if args.output:
            write_json(Path(args.output), report)
        print("=== merge-blocks validation FAILED ===", file=sys.stderr)
        for e in errors:
            print(f"  \u2717 {e}", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    output_data = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source_analysis": str(analysis_path), "merge_plan": str(merge_plan_path),
        "original_block_count": len(draft_blocks), "merged_block_count": len(merged_blocks),
        "unreferenced_blocks": sorted(unreferenced), "warnings": warnings, "blocks": merged_blocks,
    }
    write_json(output_path, output_data)

    if warnings:
        for w in warnings:
            print(f"  \u26a0 {w}", file=sys.stderr)

    summary = {
        "status": "ok", "stage": "merge-blocks", "output": str(output_path),
        "original_block_count": len(draft_blocks), "merged_block_count": len(merged_blocks),
        "unreferenced_blocks": sorted(unreferenced), "warnings": warnings,
    }
    if hasattr(args, "output_format") and args.output_format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(str(output_path))
    return 0


__all__ = [
    "_strategy_weight_multipliers",
    "compute_block_continuity",
    "cmd_suggest_merges",
    "cmd_merge_blocks",
]
