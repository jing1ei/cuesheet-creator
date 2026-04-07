"""Markdown export."""
from __future__ import annotations

import json
import os
from pathlib import Path

from cc.constants import TEMPLATE_COLUMNS
from cc.templates import validate_template_name
from cc.utils import ensure_parent, read_json, resolve_keyframe_path
from cc.validation import evaluate_delivery_readiness


def cmd_export_md(args: "argparse.Namespace") -> int:  # noqa: F821
    cue_json = Path(args.cue_json)
    if not cue_json.exists():
        raise FileNotFoundError(f"Cue JSON not found: {cue_json}")

    payload = read_json(cue_json)
    template = args.template or payload.get("template") or "production"
    validate_template_name(template)

    base_dir = Path(args.base_dir).resolve() if hasattr(args, "base_dir") and args.base_dir else cue_json.parent.resolve()
    rows = payload.get("rows", [])
    columns = TEMPLATE_COLUMNS[template]
    output_path = Path(args.output)
    ensure_parent(output_path)

    lines: list[str] = []
    title = payload.get("video_title", "Untitled")
    lines.append(f"# Cue Sheet -- {title} ({template})")
    lines.append("")

    lines.append("## Video Info")
    lines.append("")
    lines.append(f"- **Source**: `{payload.get('source_path', '')}`")
    lines.append(f"- **Generated**: {payload.get('generated_at', '')}")
    lines.append(f"- **Template**: {template}")
    lines.append(f"- **Blocks**: {len(rows)}")
    lines.append("")

    lines.append("## Shot Blocks")
    lines.append("")

    header = "| " + " | ".join(columns) + " |"
    separator = "|" + "|".join(["---"] * len(columns)) + "|"
    lines.append(header)
    lines.append(separator)

    missing_keyframes_md: list[str] = []

    for row in rows:
        cells = []
        for col in columns:
            value = str(row.get(col, ""))
            if col == "keyframe" and value:
                kf_path = resolve_keyframe_path(base_dir, value)
                if kf_path and not kf_path.exists():
                    missing_keyframes_md.append(row.get("shot_block", "?"))
                try:
                    rel = os.path.relpath(str(kf_path or value), output_path.parent).replace("\\", "/")
                except Exception:
                    rel = value.replace("\\", "/")
                cells.append(f"![kf]({rel})")
            else:
                cells.append(value.replace("|", "\\|").replace("\n", " "))
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")

    has_unconfirmed = any(
        row.get("needs_confirmation")
        for row in rows
    )
    if has_unconfirmed:
        lines.append("## Pending Confirmation")
        lines.append("")
        for row in rows:
            nc = row.get("needs_confirmation", "")
            if nc:
                lines.append(f"- **{row.get('shot_block', '?')}**: {nc}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")

    delivery = evaluate_delivery_readiness(
        rows, template, base_dir=base_dir, check_files=True,
    )
    summary = {
        "status": "ok",
        "stage": "export-md",
        "output": str(output_path),
        "template": template,
        **delivery,
    }
    if hasattr(args, "output_format") and args.output_format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(str(output_path))
        print("--- delivery summary ---")
        print(f"  rows exported: {delivery['row_count']}")
        if not rows:
            print("  WARNING: no rows exported -- cue sheet is empty")
        if delivery["missing_keyframes"]:
            print(f"  WARNING: missing keyframes for blocks: {', '.join(delivery['missing_keyframes'])}")
        if delivery["empty_required_fields"] > 0:
            print(f"  WARNING: {delivery['empty_required_fields']} empty required field(s) across all rows")
        if delivery["temp_name_gaps"]:
            print(f"  WARNING: {len(delivery['temp_name_gaps'])} unconfirmed temp name(s)")
        print(f"  delivery_ready: {'YES' if delivery['delivery_ready'] else 'NO'}")
    return 0


__all__ = ["cmd_export_md"]
