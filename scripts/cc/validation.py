"""Delivery readiness, temp marker coverage, cue JSON validation."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from cc.constants import TEMPLATE_COLUMNS
from cc.naming import (
    _get_naming_fields_from_template,
    extract_temp_markers,
)
from cc.templates import (
    get_recommended_fields,
    get_required_fields,
    validate_template_name,
)
from cc.utils import (
    resolve_keyframe_path,
    seconds_from_timecode,
    write_json,
)

# ---------------------------------------------------------------------------
# Shared temp-marker coverage validation
# ---------------------------------------------------------------------------

def validate_temp_marker_coverage(row: dict[str, Any], template: str = "production") -> list[str]:
    """Check that every temp: marker in naming fields has a matching entry in needs_confirmation.

    Returns a list of gap descriptions (empty = all markers covered).
    This is the single source of truth for temp-name consistency checks,
    used by evaluate_delivery_readiness, validate-cue-json, and normalize-fill.

    Naming fields are read from the template metadata (naming_field=true).
    Falls back to (scene, characters, location) for templates without metadata.
    """
    naming_fields = _get_naming_fields_from_template(template)
    needs_conf = str(row.get("needs_confirmation", "")).strip().lower()
    label = row.get("shot_block", "?")
    gaps: list[str] = []

    for nf in naming_fields:
        value = str(row.get(nf, ""))
        markers = extract_temp_markers(value)
        for marker in markers:
            # Extract the name portion after "temp: " for matching
            marker_key = marker.replace("temp:", "").strip().lower()
            if not marker_key:
                continue
            # Check if this specific marker (or a recognizable fragment) is
            # mentioned in needs_confirmation
            if marker_key not in needs_conf:
                gaps.append(
                    f"{label}: '{marker}' in '{nf}' has no matching entry in needs_confirmation"
                )
    return gaps


# ---------------------------------------------------------------------------
# Unified delivery readiness evaluation
# ---------------------------------------------------------------------------

def evaluate_delivery_readiness(
    rows: list[dict[str, Any]],
    template: str,
    base_dir: Path | None = None,
    check_files: bool = False,
) -> dict[str, Any]:
    """Single source of truth for delivery readiness assessment.

    Used by validate-cue-json, build-xlsx, and export-md to produce
    consistent delivery verdicts.

    Returns: {
        "row_count": int,
        "empty_required_fields": int,
        "empty_recommended_fields": int,
        "missing_keyframes": [block_labels],
        "temp_name_gaps": [descriptions],
        "delivery_ready": bool,
        "delivery_gaps": [descriptions],
    }
    """
    expected_columns = set(TEMPLATE_COLUMNS.get(template, []))
    req_fields = get_required_fields(template)
    rec_fields = get_recommended_fields(template)
    has_keyframe_col = "keyframe" in expected_columns

    empty_required = 0
    empty_recommended = 0
    missing_keyframes: list[str] = []
    temp_name_gaps: list[str] = []
    delivery_gaps: list[str] = []

    for row in rows:
        label = row.get("shot_block", "?")

        # Required fields
        for rf in req_fields:
            if rf in expected_columns and not str(row.get(rf, "")).strip():
                empty_required += 1
                delivery_gaps.append(f"{label}: required field '{rf}' is empty")

        # Recommended fields (tracked but not delivery-blocking)
        req_set = set(req_fields)
        for rec in rec_fields:
            if rec in req_set:
                continue
            if rec in expected_columns and not str(row.get(rec, "")).strip():
                empty_recommended += 1

        # temp: name consistency -- per-marker coverage check
        marker_gaps = validate_temp_marker_coverage(row, template)
        temp_name_gaps.extend(marker_gaps)
        delivery_gaps.extend(marker_gaps)

        # Keyframe existence
        if check_files and has_keyframe_col:
            kf_value = row.get("keyframe", "")
            if kf_value:
                kf_path = resolve_keyframe_path(base_dir, kf_value)
                if kf_path and not kf_path.exists():
                    missing_keyframes.append(label)
                    delivery_gaps.append(f"{label}: keyframe file not found: {kf_path}")

    delivery_ready = (
        len(rows) > 0
        and empty_required == 0
        and len(missing_keyframes) == 0
        and len(temp_name_gaps) == 0
    )

    return {
        "row_count": len(rows),
        "empty_required_fields": empty_required,
        "empty_recommended_fields": empty_recommended,
        "missing_keyframes": missing_keyframes,
        "temp_name_gaps": temp_name_gaps,
        "delivery_ready": delivery_ready,
        "delivery_gaps": delivery_gaps,
    }


# ---------------------------------------------------------------------------
# CLI command: validate-cue-json
# ---------------------------------------------------------------------------

def cmd_validate_cue_json(args: "argparse.Namespace") -> int:  # noqa: F821
    cue_json = Path(args.cue_json)
    if not cue_json.exists():
        raise FileNotFoundError(f"Cue JSON not found: {cue_json}")

    payload = json.loads(cue_json.read_text(encoding="utf-8"))
    template = args.template or payload.get("template") or "production"
    validate_template_name(template)

    rows = payload.get("rows", [])
    expected_columns = set(TEMPLATE_COLUMNS[template])
    errors: list[str] = []
    warnings: list[str] = []

    if not rows:
        errors.append("rows is empty; at least one shot block is required.")

    prev_end: float | None = None
    seen_blocks: set[str] = set()

    for idx, row in enumerate(rows):
        label = row.get("shot_block", f"row[{idx}]")

        if label in seen_blocks:
            errors.append(f"{label}: duplicate shot_block ID.")
        seen_blocks.add(label)

        for required_field in ("shot_block", "start_time", "end_time"):
            if not row.get(required_field):
                errors.append(f"{label}: missing required field '{required_field}'.")

        start_text = row.get("start_time", "")
        end_text = row.get("end_time", "")
        start_sec: float | None = None
        end_sec: float | None = None
        try:
            if start_text:
                start_sec = seconds_from_timecode(start_text)
        except Exception:
            errors.append(f"{label}: invalid start_time format '{start_text}', expected HH:MM:SS.mmm.")
        try:
            if end_text:
                end_sec = seconds_from_timecode(end_text)
        except Exception:
            errors.append(f"{label}: invalid end_time format '{end_text}', expected HH:MM:SS.mmm.")

        if start_sec is not None and end_sec is not None:
            if end_sec < start_sec:
                errors.append(f"{label}: end_time ({end_text}) is before start_time ({start_text}).")

        if prev_end is not None and start_sec is not None:
            gap = abs(start_sec - prev_end)
            if gap > 0.1:
                warnings.append(f"{label}: {gap:.3f}s gap from previous block end.")
            if start_sec < prev_end - 0.05:
                warnings.append(f"{label}: {prev_end - start_sec:.3f}s overlap with previous block.")

        if end_sec is not None:
            prev_end = end_sec

        row_keys = set(row.keys())
        extra_keys = row_keys - expected_columns
        if extra_keys:
            warnings.append(f"{label}: fields not defined in template '{template}': {', '.join(sorted(extra_keys))}.")

        # temp: marker coverage -- use shared per-marker validation
        marker_gaps = validate_temp_marker_coverage(row, template)
        for gap_msg in marker_gaps:
            warnings.append(f"{gap_msg}.")

        # Per-template field completeness: required vs recommended
        for req_field in get_required_fields(template):
            if req_field in expected_columns and not str(row.get(req_field, "")).strip():
                warnings.append(f"{label}: required field '{req_field}' is empty for template '{template}'.")
        for rec_field in get_recommended_fields(template):
            # Skip fields already covered by required check
            if rec_field in set(get_required_fields(template)):
                continue
            if rec_field in expected_columns and not str(row.get(rec_field, "")).strip():
                warnings.append(f"{label}: recommended field '{rec_field}' is empty for template '{template}'.")

    # --- Optional: keyframe file existence check ---
    if hasattr(args, "check_files") and args.check_files and "keyframe" in expected_columns:
        base_dir = Path(args.base_dir).resolve() if hasattr(args, "base_dir") and args.base_dir else cue_json.parent.resolve()
        for row in rows:
            label = row.get("shot_block", "?")
            kf_value = row.get("keyframe", "")
            if kf_value:
                kf_path = resolve_keyframe_path(base_dir, kf_value)
                if kf_path and not kf_path.exists():
                    warnings.append(f"{label}: keyframe file not found: {kf_path}")

    # Delivery readiness: required fields + temp-name consistency + keyframe existence
    delivery_gaps = [w for w in warnings if "required field" in w or "no matching entry in needs_confirmation" in w or "keyframe file not found" in w]
    delivery_ready = len(errors) == 0 and len(delivery_gaps) == 0

    report = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "template": template,
        "total_rows": len(rows),
        "errors": errors,
        "warnings": warnings,
        "valid": len(errors) == 0,
        "delivery_ready": delivery_ready,
        "delivery_gaps": delivery_gaps,
    }

    if args.report_out:
        write_json(Path(args.report_out), report)

    if args.output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"=== validate-cue-json ({template}) ===")
        print(f"Rows: {len(rows)}")
        if errors:
            print(f"Errors ({len(errors)}):")
            for e in errors:
                print(f"  \u2717 {e}")
        if warnings:
            print(f"Warnings ({len(warnings)}):")
            for w in warnings:
                print(f"  \u26a0 {w}")
        if not errors and not warnings:
            print("  \u2713 No errors, no warnings.")
        print(f"Valid: {'YES' if report['valid'] else 'NO'}")
        print(f"Delivery ready: {'YES' if delivery_ready else 'NO'}")
        if delivery_gaps:
            print(f"Delivery gaps ({len(delivery_gaps)}):")
            for g in delivery_gaps:
                print(f"  \u2192 {g}")

    return 0 if report["valid"] else 1


__all__ = [
    "validate_temp_marker_coverage",
    "evaluate_delivery_readiness",
    "cmd_validate_cue_json",
]
