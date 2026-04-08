"""Naming table derivation, application, and temp marker extraction."""
from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any

from cc.constants import (
    _TEMP_MARKER_RE,
    _TEMPLATE_REGISTRY,
    NAMING_CATEGORY_FIELDS,
    NAMING_REPLACE_FIELDS,
)
from cc.utils import read_json, write_json

# ---------------------------------------------------------------------------
# Template-aware naming field detection
# ---------------------------------------------------------------------------

def _get_naming_fields_from_template(template: str) -> set[str]:
    """Return the set of field names marked naming_field=true in the template.
    Falls back to the hardcoded NAMING_CATEGORY_FIELDS keys if the template
    has no naming_field metadata."""
    tmpl = _TEMPLATE_REGISTRY.get(template)
    if tmpl and "columns" in tmpl:
        fields = {
            col["field"] for col in tmpl["columns"]
            if isinstance(col, dict) and col.get("naming_field")
        }
        if fields:
            return fields
    # Fallback
    result: set[str] = set()
    for field_list in NAMING_CATEGORY_FIELDS.values():
        result.update(field_list)
    return result


# ---------------------------------------------------------------------------
# Temp marker extraction
# ---------------------------------------------------------------------------

def extract_temp_markers(text: str) -> list[str]:
    """Extract all 'temp: XYZ' markers from a text string."""
    if not text or "temp:" not in text.lower():
        return []
    return _TEMP_MARKER_RE.findall(text)


# ---------------------------------------------------------------------------
# Naming table derivation
# ---------------------------------------------------------------------------

def derive_naming_tables_from_rows(
    rows: list[dict[str, Any]],
    template: str = "production",
) -> dict[str, list[dict[str, Any]]]:
    """Scan rows for temp: markers, deduplicate, and aggregate block references.

    Only fields marked naming_field=true in the template are scanned (with a
    fallback to NAMING_CATEGORY_FIELDS for backward compat).  This prevents
    false positives from free-text descriptive fields like 'event'.

    Returns: {"characters": [...], "scenes": [...], "props": [...]}
    Each entry: {"temporary_name": ..., "appears_in_blocks": [...], "evidence": ..., "confidence": "low"}
    """
    # Determine which fields to scan for naming markers
    naming_fields = _get_naming_fields_from_template(template)

    # Build a field -> category mapping from template metadata + fallback
    field_to_category: dict[str, str] = {}

    # First: check template column metadata for naming_category
    tmpl = _TEMPLATE_REGISTRY.get(template)
    if tmpl and "columns" in tmpl:
        for col in tmpl["columns"]:
            if isinstance(col, dict) and col.get("naming_field") and "field" in col:
                cat = col.get("naming_category", "")
                if cat in ("characters", "scenes", "props"):
                    field_to_category[col["field"]] = cat

    # Second: fill in from hardcoded NAMING_CATEGORY_FIELDS for fields not yet mapped
    for category, fields in NAMING_CATEGORY_FIELDS.items():
        for f in fields:
            if f in naming_fields and f not in field_to_category:
                field_to_category[f] = category

    # Third: any remaining naming_field without a category gets "props" (least harmful default)
    for f in naming_fields:
        if f not in field_to_category:
            field_to_category[f] = "props"

    # category -> { marker_text -> set of block IDs }
    category_map: dict[str, dict[str, set[str]]] = {
        "characters": {},
        "scenes": {},
        "props": {},
    }

    for row in rows:
        block_id = row.get("shot_block", "?")
        for field, category in field_to_category.items():
            value = row.get(field, "")
            if not value:
                continue
            markers = extract_temp_markers(value)
            for marker in markers:
                normalized = marker.strip()
                if normalized not in category_map[category]:
                    category_map[category][normalized] = set()
                category_map[category][normalized].add(block_id)

    # Build structured output
    result: dict[str, list[dict[str, Any]]] = {}
    for category in ("characters", "scenes", "props"):
        entries: list[dict[str, Any]] = []
        for marker, block_ids in sorted(category_map[category].items()):
            sorted_blocks = sorted(block_ids, key=lambda b: (len(b), b))
            entries.append({
                "temporary_name": marker,
                "appears_in_blocks": sorted_blocks,
                "evidence": f"Found in {len(sorted_blocks)} block(s): {', '.join(sorted_blocks)}",
                "confidence": "low",
                "confirmed_name": "",
                "status": "pending",
            })
        result[category] = entries

    return result


def format_naming_tables_md(tables: dict[str, list[dict[str, Any]]]) -> str:
    """Format naming tables as Markdown sections."""
    lines: list[str] = []

    lines.append("## Naming Confirmation Tables")
    lines.append("")

    lines.append("### Characters")
    lines.append("")
    lines.append("| temporary_name | appears_in_blocks | evidence | confidence | confirmed_name | status |")
    lines.append("|---|---|---|---|---|---|")
    for entry in tables.get("characters", []):
        lines.append(
            f"| {entry['temporary_name']} "
            f"| {', '.join(entry['appears_in_blocks'])} "
            f"| {entry['evidence']} "
            f"| {entry['confidence']} "
            f"| {entry['confirmed_name']} "
            f"| {entry['status']} |"
        )
    if not tables.get("characters"):
        lines.append("| *(none detected)* | | | | | |")
    lines.append("")

    lines.append("### Scenes / Setups")
    lines.append("")
    lines.append("| temporary_name | appears_in_blocks | evidence | confidence | confirmed_name | status |")
    lines.append("|---|---|---|---|---|---|")
    for entry in tables.get("scenes", []):
        lines.append(
            f"| {entry['temporary_name']} "
            f"| {', '.join(entry['appears_in_blocks'])} "
            f"| {entry['evidence']} "
            f"| {entry['confidence']} "
            f"| {entry['confirmed_name']} "
            f"| {entry['status']} |"
        )
    if not tables.get("scenes"):
        lines.append("| *(none detected)* | | | | | |")
    lines.append("")

    lines.append("### Props")
    lines.append("")
    lines.append("| temporary_name | appears_in_blocks | evidence | confidence | confirmed_name | status |")
    lines.append("|---|---|---|---|---|---|")
    for entry in tables.get("props", []):
        lines.append(
            f"| {entry['temporary_name']} "
            f"| {', '.join(entry['appears_in_blocks'])} "
            f"| {entry['evidence']} "
            f"| {entry['confidence']} "
            f"| {entry['confirmed_name']} "
            f"| {entry['status']} |"
        )
    if not tables.get("props"):
        lines.append("| *(none detected)* | | | | | |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_derive_naming_tables(args: "argparse.Namespace") -> int:  # noqa: F821
    """Scan a filled draft_fill.json for temp: markers and generate naming_tables.json
    + optionally update cue_sheet.md with derived naming confirmation tables."""
    import re

    source_path = Path(args.source_json)
    if not source_path.exists():
        raise FileNotFoundError(f"Source JSON not found: {source_path}")

    source = read_json(source_path)
    rows = source.get("rows", [])
    template = source.get("template", "production")

    import sys
    if not rows:
        print("WARNING: No rows found in source JSON.", file=sys.stderr)

    tables = derive_naming_tables_from_rows(rows, template)

    # Count total markers found
    total = sum(len(entries) for entries in tables.values())

    # Output naming_tables.json
    output_path = Path(args.output)
    output_data = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": str(source_path),
        "template": template,
        "total_temp_markers": total,
        "tables": tables,
    }
    write_json(output_path, output_data)
    is_json = hasattr(args, "output_format") and args.output_format == "json"
    if not is_json:
        print(f"Naming tables: {output_path} ({total} temp marker(s) found)")

    # Optionally update cue_sheet.md
    if args.md:
        md_path = Path(args.md)
        if not md_path.exists():
            print(f"WARNING: Markdown file not found: {md_path}", file=sys.stderr)
        else:
            md_content = md_path.read_text(encoding="utf-8")
            new_tables_md = format_naming_tables_md(tables)

            # Replace existing naming confirmation tables section if present
            pattern = r"## Naming Confirmation Tables\n.*?(?=\n## |\Z)"
            if re.search(pattern, md_content, re.DOTALL):
                md_content = re.sub(pattern, new_tables_md.rstrip(), md_content, count=1, flags=re.DOTALL)
            else:
                # Append before "## Pending Questions" or at end
                pending_match = re.search(r"\n## Pending Questions", md_content)
                if pending_match:
                    md_content = (
                        md_content[:pending_match.start()]
                        + "\n" + new_tables_md + "\n"
                        + md_content[pending_match.start():]
                    )
                else:
                    md_content = md_content.rstrip() + "\n\n" + new_tables_md

            md_path.write_text(md_content, encoding="utf-8")
            if not is_json:
                print(f"Updated: {md_path}")

    # Summary
    if hasattr(args, "output_format") and args.output_format == "json":
        print(json.dumps(output_data, ensure_ascii=False, indent=2))
    else:
        for cat in ("characters", "scenes", "props"):
            count = len(tables.get(cat, []))
            if count:
                items = ", ".join(e["temporary_name"] for e in tables[cat])
                print(f"  {cat}: {count} ({items})")

    return 0


# ---------------------------------------------------------------------------
# Naming application
# ---------------------------------------------------------------------------

def apply_naming_to_text(text: str, mapping: dict[str, str]) -> str:
    """Apply naming replacements, longest keys first to avoid substring collisions."""
    result = text
    for old_name, new_name in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True):
        result = result.replace(old_name, new_name)
    return result


def apply_naming_to_json_structured(
    payload: dict[str, Any],
    mappings: dict[str, str],
    template: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Apply naming overrides to rows in a structured JSON payload.

    The set of fields to replace in is derived from:
      1. Template metadata (naming_field=true columns) — for custom template parity
      2. NAMING_REPLACE_FIELDS hardcoded whitelist — for broad free-text fields
    The union of both sets is used, so custom naming fields are always covered.

    Replacements are applied longest-key-first to avoid substring collisions.
    """
    result = copy.deepcopy(payload)
    changes = 0
    sorted_mappings = sorted(mappings.items(), key=lambda kv: len(kv[0]), reverse=True)

    # Build the effective set of fields to search for replacements
    effective_template = template or payload.get("template") or "production"
    template_naming_fields = _get_naming_fields_from_template(effective_template)
    replace_fields = NAMING_REPLACE_FIELDS | template_naming_fields

    for row in result.get("rows", []):
        for field in replace_fields:
            value = row.get(field)
            if not isinstance(value, str):
                continue
            new_value = value
            for old_name, new_name in sorted_mappings:
                new_value = new_value.replace(old_name, new_name)
            if new_value != value:
                row[field] = new_value
                changes += 1
    return result, changes


def cmd_apply_naming(args: "argparse.Namespace") -> int:  # noqa: F821
    import sys

    overrides_path = Path(args.overrides)
    if not overrides_path.exists():
        raise FileNotFoundError(f"Naming overrides file not found: {overrides_path}")

    overrides = read_json(overrides_path)
    all_mappings: dict[str, str] = {}
    for category in ("characters", "scenes", "props"):
        mappings = overrides.get(category, {})
        all_mappings.update(mappings)

    dry_run = bool(args.dry_run)
    is_json = hasattr(args, "output_format") and args.output_format == "json"

    if not all_mappings:
        if is_json:
            print(json.dumps({"status": "no-op", "message": "Naming overrides empty, no replacements needed.", "files_updated": 0}))
        else:
            print("Naming overrides empty, no replacements needed.")
        return 0

    if not args.cue_json and not args.md:
        msg = "At least one of --cue-json or --md must be specified."
        if is_json:
            print(json.dumps({"status": "error", "message": msg}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 1
    replaced_count = 0
    changes_detail: list[dict[str, Any]] = []

    if args.cue_json:
        cue_path = Path(args.cue_json)
        if not cue_path.exists():
            raise FileNotFoundError(f"Cue JSON not found: {cue_path}")
        payload = read_json(cue_path)
        effective_template = payload.get("template")
        new_payload, change_count = apply_naming_to_json_structured(payload, all_mappings, template=effective_template)
        changes_detail.append({"file": str(cue_path), "type": "json", "field_changes": change_count})
        if change_count > 0:
            if not dry_run:
                out_path = Path(args.output) if args.output else cue_path
                write_json(out_path, new_payload)
                if not is_json:
                    print(f"Updated ({change_count} field changes): {out_path}")
            else:
                if not is_json:
                    print(f"[dry-run] Would update {change_count} fields in: {cue_path}")
            replaced_count += 1
        else:
            if not is_json:
                print(f"No changes: {cue_path}")

    if args.md:
        md_path = Path(args.md)
        if not md_path.exists():
            raise FileNotFoundError(f"Markdown not found: {md_path}")
        raw = md_path.read_text(encoding="utf-8")
        new_raw = apply_naming_to_text(raw, all_mappings)
        md_changes = 1 if raw != new_raw else 0
        changes_detail.append({"file": str(md_path), "type": "md", "changed": bool(md_changes)})
        if md_changes:
            if not dry_run:
                md_path.write_text(new_raw, encoding="utf-8")
                if not is_json:
                    print(f"Updated: {md_path}")
            else:
                if not is_json:
                    print(f"[dry-run] Would update: {md_path}")
            replaced_count += 1
        else:
            if not is_json:
                print(f"No changes: {md_path}")

    report = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "mappings_count": len(all_mappings),
        "mappings": all_mappings,
        "files_processed": changes_detail,
        "files_updated": replaced_count,
    }

    if args.report_out:
        write_json(Path(args.report_out), report)

    if hasattr(args, "output_format") and args.output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        mode = "[dry-run] " if dry_run else ""
        print(f"{mode}Total {len(all_mappings)} mappings, {replaced_count} file(s) {'would be ' if dry_run else ''}updated.")
    return 0


__all__ = [
    "_get_naming_fields_from_template",
    "extract_temp_markers",
    "derive_naming_tables_from_rows",
    "format_naming_tables_md",
    "cmd_derive_naming_tables",
    "apply_naming_to_text",
    "apply_naming_to_json_structured",
    "cmd_apply_naming",
]
