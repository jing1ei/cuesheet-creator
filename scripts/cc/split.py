"""Post-fill block splitting based on LLM _split_at annotations."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from cc.utils import format_seconds, make_block_id, read_json, seconds_from_timecode, write_json


def _find_nearest_keyframe(
    target_seconds: float,
    all_blocks: list[dict[str, Any]],
    out_dir: Path | None = None,
) -> str:
    """Find the keyframe path closest in time to *target_seconds*."""
    best_path = ""
    best_dist = float("inf")
    for block in all_blocks:
        kf = block.get("keyframe", "")
        if not kf:
            continue
        block_mid = (block.get("start_seconds", 0) + block.get("end_seconds", 0)) / 2
        # If we don't have start_seconds, parse from timecode
        if "start_seconds" not in block:
            try:
                block_mid = (
                    seconds_from_timecode(block.get("start_time", "0"))
                    + seconds_from_timecode(block.get("end_time", "0"))
                ) / 2
            except Exception:
                continue
        dist = abs(target_seconds - block_mid)
        if dist < best_dist:
            best_dist = dist
            best_path = kf
    return best_path


def _perform_splits(rows: list[dict[str, Any]], template: str) -> tuple[list[dict[str, Any]], int]:
    """Process _split_at annotations and return (new_rows, split_count).

    For each row with _split_at:
      - Split at each specified time, creating N+1 sub-blocks from N split points
      - First sub-block inherits all content fields from the original
      - Subsequent sub-blocks get empty content fields (LLM re-fills them)
      - Keyframes: original row's keyframe goes to the first sub-block;
        remaining sub-blocks get the nearest keyframe by time
    """
    # Structural fields that are always recomputed, never copied
    _STRUCTURAL = {"shot_block", "start_time", "end_time"}
    # Fields that should NOT be blanked (metadata, not content)
    _METADATA = {"keyframe", "confidence", "needs_confirmation", "_split_at"}

    new_rows: list[dict[str, Any]] = []
    split_count = 0

    for row in rows:
        split_points = row.get("_split_at")
        if not split_points or not isinstance(split_points, list):
            # No split requested -- keep row as-is, strip _split_at if empty
            cleaned = {k: v for k, v in row.items() if k != "_split_at"}
            new_rows.append(cleaned)
            continue

        # Parse and validate split times
        try:
            row_start = seconds_from_timecode(row.get("start_time", "0"))
        except Exception:
            row_start = 0.0
        try:
            row_end = seconds_from_timecode(row.get("end_time", "0"))
        except Exception:
            row_end = row_start

        valid_times: list[float] = []
        for sp in split_points:
            if not isinstance(sp, dict) or "time" not in sp:
                continue
            try:
                t = seconds_from_timecode(sp["time"])
            except Exception:
                continue
            if row_start < t < row_end:
                valid_times.append(t)

        if not valid_times:
            # No valid split points -- keep row as-is
            cleaned = {k: v for k, v in row.items() if k != "_split_at"}
            new_rows.append(cleaned)
            continue

        # Sort and deduplicate split times
        valid_times = sorted(set(valid_times))

        # Build sub-blocks: boundaries are [row_start, t1, t2, ..., row_end]
        boundaries = [row_start] + valid_times + [row_end]

        for i in range(len(boundaries) - 1):
            sub_start = boundaries[i]
            sub_end = boundaries[i + 1]

            sub_row: dict[str, Any] = {}
            sub_row["start_time"] = format_seconds(sub_start)
            sub_row["end_time"] = format_seconds(sub_end)

            if i == 0:
                # First sub-block: inherit all content from original
                for k, v in row.items():
                    if k in _STRUCTURAL or k == "_split_at":
                        continue
                    sub_row[k] = v
                # Adjust end_time (content may describe the full original block,
                # but structurally it now covers only the first segment)
            else:
                # Subsequent sub-blocks: empty content, need LLM re-fill
                for k, v in row.items():
                    if k in _STRUCTURAL or k == "_split_at":
                        continue
                    if k in _METADATA:
                        sub_row[k] = v  # preserve keyframe, confidence
                    else:
                        sub_row[k] = ""  # blank content for re-fill

                # Try to assign the nearest keyframe by time
                nearest_kf = _find_nearest_keyframe(
                    (sub_start + sub_end) / 2, rows,
                )
                if nearest_kf:
                    sub_row["keyframe"] = nearest_kf

                # Add a hint about why this block was created
                reason_parts = [
                    sp.get("reason", "LLM split request")
                    for sp in split_points
                    if isinstance(sp, dict)
                    and "time" in sp
                ]
                try:
                    sp_time = boundaries[i]
                    matching = [
                        sp.get("reason", "")
                        for sp in split_points
                        if isinstance(sp, dict)
                        and abs(seconds_from_timecode(sp.get("time", "0")) - sp_time) < 0.05
                    ]
                    if matching and matching[0]:
                        sub_row["_split_reason"] = matching[0]
                    elif reason_parts:
                        sub_row["_split_reason"] = reason_parts[0]
                except Exception:
                    pass

            new_rows.append(sub_row)
            if i > 0:
                split_count += 1

    # Renumber all blocks
    for idx, row in enumerate(new_rows, start=1):
        row["shot_block"] = make_block_id(idx)

    return new_rows, split_count


def cmd_split_blocks(args: "argparse.Namespace") -> int:  # noqa: F821
    """Split blocks at LLM-annotated _split_at points in a filled draft_fill.json."""
    source_path = Path(args.source_json)
    if not source_path.exists():
        raise FileNotFoundError(f"Source JSON not found: {source_path}")

    source = read_json(source_path)
    rows = source.get("rows", [])
    template = source.get("template", "production")

    # Count rows with split annotations
    annotated = [r for r in rows if r.get("_split_at")]
    if not annotated:
        msg = "No _split_at annotations found in any row. Nothing to split."
        is_json = hasattr(args, "output_format") and args.output_format == "json"
        if is_json:
            print(json.dumps({"status": "no-op", "message": msg, "row_count": len(rows)}))
        else:
            print(msg)
        return 0

    new_rows, split_count = _perform_splits(rows, template)

    # Update source
    source["rows"] = new_rows
    if split_count > 0:
        source["fill_status"] = "partial"  # new empty blocks need LLM fill

    # Write output
    out_path = Path(args.output) if args.output else source_path
    write_json(out_path, source)

    summary = {
        "status": "ok",
        "stage": "split-blocks",
        "output": str(out_path),
        "original_row_count": len(rows),
        "new_row_count": len(new_rows),
        "splits_performed": split_count,
        "annotated_rows": len(annotated),
        "fill_status": source.get("fill_status", "partial"),
    }

    is_json = hasattr(args, "output_format") and args.output_format == "json"
    if is_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Split {split_count} new block(s) from {len(annotated)} annotated row(s).")
        print(f"  {len(rows)} rows -> {len(new_rows)} rows")
        print(f"  Output: {out_path}")
        if split_count > 0:
            print(f"  fill_status set to 'partial' — re-run LLM fill-in on new empty blocks.")
    return 0


__all__ = ["cmd_split_blocks", "_perform_splits"]
