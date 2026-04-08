"""Final skeleton generation from draft/merged blocks."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from cc.constants import TEMPLATE_COLUMNS
from cc.normalize import is_hint_only_value
from cc.templates import validate_template_name
from cc.utils import read_json, write_json


def cmd_build_final_skeleton(args: "argparse.Namespace") -> int:  # noqa: F821
    """Generate a final_cues.json skeleton from merged blocks, analysis draft_blocks,
    or a filled draft_fill.json."""
    source_path = Path(args.source_json)
    if not source_path.exists():
        raise FileNotFoundError(f"Source JSON not found: {source_path}")

    source = read_json(source_path)

    is_fill_input = "fill_status" in source
    if is_fill_input and source.get("rows"):
        blocks = source["rows"]
        fill_status = source.get("fill_status", "unknown")
        if fill_status == "partial":
            STRUCTURAL_FIELDS = {"shot_block", "start_time", "end_time", "keyframe"}
            active_template = source.get("template", "production")
            template_cols = set(TEMPLATE_COLUMNS.get(active_template, TEMPLATE_COLUMNS.get("production", [])))
            content_cols = template_cols - STRUCTURAL_FIELDS
            empty_count = 0
            for row in blocks:
                for f in content_cols:
                    val = row.get(f, "")
                    if is_hint_only_value(val):
                        empty_count += 1
            if empty_count > 0:
                print(f"WARNING: fill_status is 'partial' — {empty_count} content field(s) still empty or hint-only "
                      f"(template={active_template}, {len(content_cols)} content fields per block). "
                      f"LLM fill-in may be incomplete.", file=sys.stderr)
        elif fill_status == "pending":
            print("WARNING: fill_status is 'pending' — no LLM fill-in has been done. "
                  "The final JSON will have mostly empty content fields.", file=sys.stderr)
    else:
        blocks = source.get("blocks") or source.get("draft_blocks", [])

    template = args.template or source.get("template") or "production"
    validate_template_name(template)

    columns = TEMPLATE_COLUMNS[template]
    rows: list[dict[str, Any]] = []

    for block in blocks:
        row: dict[str, Any] = {}
        for col in columns:
            if col == "shot_block":
                row[col] = block.get("shot_block", "")
            elif col == "start_time":
                row[col] = block.get("start_time", "")
            elif col == "end_time":
                row[col] = block.get("end_time", "")
            elif col == "keyframe":
                row[col] = block.get("keyframe", "")
            else:
                existing = block.get(col, "")
                row[col] = existing if existing else ""
        # Always preserve keyframe path even if the template doesn't have
        # a keyframe column — xlsx/md export may need it for --embed-keyframes.
        if "keyframe" not in columns and block.get("keyframe"):
            row["_keyframe"] = block.get("keyframe", "")
        rows.append(row)

    raw_title = args.video_title or source.get("video_title") or source.get("video", {}).get("source_path")
    if raw_title and not args.video_title and not source.get("video_title"):
        video_title = Path(raw_title).stem
    elif raw_title:
        video_title = raw_title
    else:
        print("WARNING: --video-title not provided and source JSON has no video metadata. "
              "Falling back to 'untitled'. Consider passing --video-title explicitly.", file=sys.stderr)
        video_title = "untitled"
    source_path_value = args.source_path or source.get("source_path") or source.get("video", {}).get("source_path") or source.get("source_analysis", "")
    if not source_path_value:
        print("WARNING: --source-path not provided and source JSON has no video metadata. "
              "Falling back to source_analysis path. Consider passing --source-path explicitly.", file=sys.stderr)

    skeleton = {
        "template": template,
        "video_title": video_title,
        "source_path": source_path_value,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "rows": rows,
    }

    output_path = Path(args.output)
    write_json(output_path, skeleton)
    summary = {
        "status": "ok", "stage": "build-final-skeleton",
        "output": str(output_path), "template": template,
        "video_title": video_title, "row_count": len(rows),
    }
    if hasattr(args, "output_format") and args.output_format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(str(output_path))
    return 0


__all__ = ["cmd_build_final_skeleton"]
