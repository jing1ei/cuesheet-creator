"""LLM output normalization: enum standardization, hint stripping, lint."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from cc.constants import (
    _MOTION_HINT_RE,
    _OCR_HINT_RE,
    _VISUAL_HINT_RE,
    MOTION_ALIASES,
    MOTION_ENUM,
    SHOT_SIZE_ALIASES,
    SHOT_SIZE_ENUM,
    TEMPLATE_COLUMNS,
)
from cc.utils import read_json, write_json


def is_hint_only_value(value: str) -> bool:
    """Check if a field value is only a machine-generated hint (not real content).

    Returns True if the value is empty or contains only [visual: ...],
    [OCR detected: ...], or [motion-hint: ...] prefixes with no user/LLM content after.
    This is the single source of truth for hint-only detection, used by
    build-final-skeleton (completeness warnings) and normalize-fill.
    """
    if not value or not value.strip():
        return True
    stripped = _VISUAL_HINT_RE.sub("", value)
    stripped = _OCR_HINT_RE.sub("", stripped)
    stripped = _MOTION_HINT_RE.sub("", stripped)
    return not stripped.strip()


def normalize_shot_size(value: str) -> tuple[str, bool]:
    """Normalize shot_size to enum value. Returns (normalized, was_changed)."""
    stripped = value.strip()
    if not stripped:
        return stripped, False
    upper = stripped.upper()
    if upper in SHOT_SIZE_ENUM:
        if stripped != upper:
            return upper, True
        return stripped, False
    lower = stripped.lower()
    if lower in SHOT_SIZE_ALIASES:
        return SHOT_SIZE_ALIASES[lower], True
    # Try matching with extra text like "WS (wide shot)"
    for enum_val in SHOT_SIZE_ENUM:
        if upper.startswith(enum_val):
            return enum_val, True
    return stripped, False


def normalize_motion(value: str) -> tuple[str, bool]:
    """Normalize motion to enum value. Returns (normalized, was_changed)."""
    stripped = value.strip()
    if not stripped:
        return stripped, False
    lower = stripped.lower()
    if lower in MOTION_ENUM:
        if stripped != lower:
            return lower, True
        return stripped, False
    if lower in MOTION_ALIASES:
        return MOTION_ALIASES[lower], True
    # Partial match: "slow push-in" -> "push-in"
    for enum_val in MOTION_ENUM:
        if enum_val in lower:
            return enum_val, True
    return stripped, False


def strip_hint_prefixes(value: str) -> tuple[str, bool]:
    """Remove [visual: ...], [OCR detected: ...], and [motion-hint: ...] hint prefixes."""
    if not value:
        return value, False
    cleaned = _VISUAL_HINT_RE.sub("", value)
    cleaned = _OCR_HINT_RE.sub("", cleaned)
    cleaned = _MOTION_HINT_RE.sub("", cleaned)
    cleaned = cleaned.strip()
    return cleaned, cleaned != value.strip()


def cmd_normalize_fill(args: "argparse.Namespace") -> int:  # noqa: F821
    """Normalize / lint a filled draft_fill.json or final_cues.json.

    Modes:
    - lint (default): report issues without modifying the file
    - fix: auto-normalize + report, write output
    """
    # Lazy imports to avoid circular dependency issues at module level
    from cc.templates import get_recommended_fields, get_required_fields
    from cc.validation import validate_temp_marker_coverage

    source_path = Path(args.source_json)
    if not source_path.exists():
        raise FileNotFoundError(f"Source JSON not found: {source_path}")

    source = read_json(source_path)
    rows = source.get("rows", [])
    template = source.get("template", "production")
    fix_mode = bool(args.fix)

    issues: list[dict[str, Any]] = []
    fixes_applied: list[dict[str, Any]] = []

    columns = TEMPLATE_COLUMNS.get(template, TEMPLATE_COLUMNS.get("production", []))

    for row in rows:
        block_id = row.get("shot_block", "?")

        # 1. Normalize shot_size
        if "shot_size" in row and row["shot_size"]:
            normalized, changed = normalize_shot_size(row["shot_size"])
            if changed:
                fix_rec = {
                    "block": block_id, "field": "shot_size",
                    "old": row["shot_size"], "new": normalized,
                    "type": "normalize",
                }
                if fix_mode:
                    row["shot_size"] = normalized
                    fixes_applied.append(fix_rec)
                else:
                    issues.append({**fix_rec, "severity": "fixable"})
            elif row["shot_size"].strip() and row["shot_size"].upper() not in SHOT_SIZE_ENUM:
                issues.append({
                    "block": block_id, "field": "shot_size",
                    "value": row["shot_size"],
                    "type": "unknown_enum",
                    "severity": "warning",
                    "message": f"shot_size '{row['shot_size']}' not in enum: {', '.join(sorted(SHOT_SIZE_ENUM))}",
                })

        # 2. Normalize motion
        if "motion" in row and row["motion"]:
            normalized, changed = normalize_motion(row["motion"])
            if changed:
                fix_rec = {
                    "block": block_id, "field": "motion",
                    "old": row["motion"], "new": normalized,
                    "type": "normalize",
                }
                if fix_mode:
                    row["motion"] = normalized
                    fixes_applied.append(fix_rec)
                else:
                    issues.append({**fix_rec, "severity": "fixable"})

        # 3. Strip [visual: ...] and [OCR detected: ...] hint prefixes
        for field in columns:
            value = row.get(field, "")
            if not isinstance(value, str):
                continue
            cleaned, changed = strip_hint_prefixes(value)
            if changed:
                fix_rec = {
                    "block": block_id, "field": field,
                    "old": value[:80], "new": cleaned[:80],
                    "type": "strip_hint",
                }
                if fix_mode:
                    row[field] = cleaned
                    fixes_applied.append(fix_rec)
                else:
                    issues.append({**fix_rec, "severity": "fixable"})

        # 4. Check temp: markers vs needs_confirmation (shared logic)
        marker_gaps = validate_temp_marker_coverage(row, template)
        for gap_msg in marker_gaps:
            issues.append({
                "block": block_id, "field": "needs_confirmation",
                "type": "orphaned_temp_marker",
                "severity": "warning",
                "message": gap_msg,
            })

        # 5. Report empty required / recommended fields
        req_set = set(get_required_fields(template))
        for req_field in req_set:
            if req_field in set(columns) and not str(row.get(req_field, "")).strip():
                issues.append({
                    "block": block_id, "field": req_field,
                    "type": "empty_required",
                    "severity": "warning",
                    "message": f"Required field '{req_field}' is empty",
                })
        for rec_field in get_recommended_fields(template):
            if rec_field in req_set:
                continue  # Already reported as required
            if rec_field in set(columns) and not str(row.get(rec_field, "")).strip():
                issues.append({
                    "block": block_id, "field": rec_field,
                    "type": "empty_recommended",
                    "severity": "info",
                    "message": f"Recommended field '{rec_field}' is empty",
                })

    # Build report
    report = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": str(source_path),
        "template": template,
        "mode": "fix" if fix_mode else "lint",
        "total_rows": len(rows),
        "issues": issues,
        "fixes_applied": fixes_applied,
        "summary": {
            "fixable": len([i for i in issues if i.get("severity") == "fixable"]),
            "warnings": len([i for i in issues if i.get("severity") == "warning"]),
            "fixes_applied": len(fixes_applied),
        },
    }

    # Write output
    is_json = hasattr(args, "output_format") and args.output_format == "json"
    if fix_mode:
        out_path = Path(args.output) if args.output else source_path
        write_json(out_path, source)
        if not is_json:
            print(f"Fixed: {out_path} ({len(fixes_applied)} fix(es) applied)")

    if args.report_out:
        write_json(Path(args.report_out), report)

    # Print summary
    if is_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        mode_label = "fix" if fix_mode else "lint"
        print(f"=== normalize-fill ({mode_label}, {template}) ===")
        print(f"Rows: {len(rows)}")
        if fixes_applied:
            print(f"Fixes applied: {len(fixes_applied)}")
            for f in fixes_applied[:10]:
                print(f"  {f['block']}.{f['field']}: '{f['old']}' -> '{f['new']}'")
            if len(fixes_applied) > 10:
                print(f"  ... and {len(fixes_applied) - 10} more")
        if issues:
            fixable = [i for i in issues if i.get("severity") == "fixable"]
            warnings_list = [i for i in issues if i.get("severity") == "warning"]
            if fixable:
                print(f"Fixable issues: {len(fixable)} (run with --fix to auto-normalize)")
                for i in fixable[:5]:
                    print(f"  {i['block']}.{i['field']}: '{i.get('old', '')}' -> '{i.get('new', '')}'")
            if warnings_list:
                print(f"Warnings: {len(warnings_list)}")
                for i in warnings_list[:10]:
                    print(f"  {i['block']}.{i['field']}: {i.get('message', i.get('type', ''))}")
        if not issues and not fixes_applied:
            print("  No issues found.")

    return 0


__all__ = [
    "is_hint_only_value",
    "normalize_shot_size",
    "normalize_motion",
    "strip_hint_prefixes",
    "cmd_normalize_fill",
]
