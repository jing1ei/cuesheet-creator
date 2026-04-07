"""Template management commands: list, show, save, delete."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from cc.constants import (
    _BUILTIN_TEMPLATE_NAMES,
    _TEMPLATE_REGISTRY,
    SKILL_ROOT,
    TEMPLATE_COLUMNS,
    USER_DATA_DIR,
)
from cc.templates import (
    get_template_definition,
    load_templates,
    validate_template_json,
)
from cc.utils import read_json, write_json


def cmd_list_templates(args: "argparse.Namespace") -> int:  # noqa: F821
    """List all available templates (built-in + custom)."""
    templates_info: list[dict[str, Any]] = []
    for name in sorted(TEMPLATE_COLUMNS.keys()):
        tmpl = _TEMPLATE_REGISTRY.get(name, {})
        seg = tmpl.get("segmentation", {})
        templates_info.append({
            "name": name,
            "description": tmpl.get("description", ""),
            "strategy": seg.get("strategy", "unknown") if seg else "unknown",
            "columns": len(TEMPLATE_COLUMNS.get(name, [])),
            "source": tmpl.get("_source", "unknown"),
        })

    if args.output_format == "json":
        print(json.dumps({"templates": templates_info}, ensure_ascii=False, indent=2))
    else:
        print("=== Available Templates ===")
        for t in templates_info:
            source_tag = f"[{t['source']}]"
            print(f"  {t['name']:20s} {source_tag:16s} strategy={t['strategy']:16s} columns={t['columns']}")
            if t["description"]:
                print(f"    {t['description']}")
    return 0


def cmd_show_template(args: "argparse.Namespace") -> int:  # noqa: F821
    """Show full details of a template."""
    name = args.name
    tmpl = get_template_definition(name)
    if tmpl is None:
        available = ", ".join(sorted(TEMPLATE_COLUMNS.keys()))
        print(f"ERROR: Template '{name}' not found. Available: {available}", file=sys.stderr)
        return 1

    if args.output_format == "json":
        output = {k: v for k, v in tmpl.items() if not k.startswith("_")}
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"=== Template: {name} ===")
        print(f"  Description: {tmpl.get('description', '')}")
        print(f"  Source: {tmpl.get('_source', 'unknown')}")
        print(f"  Perspective: {tmpl.get('perspective', '(none)')}")
        seg = tmpl.get("segmentation", {})
        if seg:
            print("\n  Segmentation:")
            print(f"    Strategy: {seg.get('strategy', '')}")
            print(f"    Description: {seg.get('description', '')}")
            triggers = seg.get("split_triggers", [])
            if triggers:
                print("    Split triggers:")
                for t in triggers:
                    print(f"      - {t}")
            bias = seg.get("merge_bias", [])
            if bias:
                print("    Merge bias:")
                for b in bias:
                    print(f"      - {b}")
            kf = seg.get("keyframe_priority", [])
            if kf:
                print("    Keyframe priority:")
                for k in kf:
                    print(f"      - {k}")
        cols = tmpl.get("columns", [])
        if cols:
            print(f"\n  Columns ({len(cols)}):")
            for col in cols:
                flags = []
                if col.get("required"):
                    flags.append("required")
                if col.get("recommended"):
                    flags.append("recommended")
                if col.get("naming_field"):
                    flags.append("naming")
                ps = col.get("prefill_source")
                if ps:
                    flags.append(f"prefill:{ps}")
                flag_str = f" ({', '.join(flags)})" if flags else ""
                print(f"    - {col.get('field', ''):24s} \"{col.get('label', '')}\" width={col.get('width', 18)}{flag_str}")
        guidance = tmpl.get("fill_guidance", [])
        if guidance:
            print("\n  Fill guidance:")
            for g in guidance:
                print(f"    - {g}")
    return 0


def cmd_save_template(args: "argparse.Namespace") -> int:  # noqa: F821
    """Validate and save a template JSON file to the custom templates directory."""
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Template input file not found: {input_path}")

    data = read_json(input_path)

    errors = validate_template_json(data)
    if errors:
        print("=== Template validation FAILED ===", file=sys.stderr)
        for e in errors:
            print(f"  \u2717 {e}", file=sys.stderr)
        return 1

    name = data.get("name", "")
    if not name:
        print("ERROR: Template must have a 'name' field.", file=sys.stderr)
        return 1

    if name in _BUILTIN_TEMPLATE_NAMES and not args.overwrite:
        print(f"ERROR: '{name}' is a built-in template. Use --overwrite to replace with a custom version.", file=sys.stderr)
        return 1

    # Prefer source-layout custom dir if available (for dev workflows);
    # otherwise use user-data dir (for installed-package users).
    source_custom = SKILL_ROOT / "templates" / "custom"
    if (SKILL_ROOT / "templates").is_dir() and (SKILL_ROOT / "SKILL.md").is_file():
        custom_dir = source_custom
    else:
        custom_dir = USER_DATA_DIR / "templates" / "custom"
    custom_dir.mkdir(parents=True, exist_ok=True)
    dest = custom_dir / f"{name}.json"

    if dest.exists() and not args.overwrite:
        print(f"ERROR: Custom template '{name}' already exists at {dest}. Use --overwrite to replace.", file=sys.stderr)
        return 1

    write_json(dest, data)
    load_templates()

    seg = data.get("segmentation", {})
    cols = data.get("columns", [])
    print(f"=== Template saved: {name} ===")
    print(f"  Path: {dest}")
    print(f"  Description: {data.get('description', '')}")
    print(f"  Segmentation strategy: {seg.get('strategy', 'unknown')}")
    if seg.get("split_triggers"):
        print(f"  Split triggers: {len(seg['split_triggers'])}")
    if seg.get("merge_bias"):
        print(f"  Merge bias rules: {len(seg['merge_bias'])}")
    if seg.get("keyframe_priority"):
        print(f"  Keyframe priority rules: {len(seg['keyframe_priority'])}")
    print(f"  Columns: {len(cols)}")
    for col in cols:
        label = col.get("label", col.get("field", ""))
        print(f"    - {label}")
    return 0


def cmd_delete_template(args: "argparse.Namespace") -> int:  # noqa: F821
    """Delete a custom template. Refuses to delete built-in templates."""
    name = args.name

    if name in _BUILTIN_TEMPLATE_NAMES:
        tmpl = _TEMPLATE_REGISTRY.get(name, {})
        source = tmpl.get("_source", "")
        if source != "custom":
            print(f"ERROR: '{name}' is a built-in template and cannot be deleted.", file=sys.stderr)
            return 1

    tmpl = _TEMPLATE_REGISTRY.get(name)
    if tmpl is None:
        available = ", ".join(sorted(TEMPLATE_COLUMNS.keys()))
        print(f"ERROR: Template '{name}' not found. Available: {available}", file=sys.stderr)
        return 1

    source = tmpl.get("_source", "")
    if source in ("built-in", "hardcoded-fallback"):
        print(f"ERROR: '{name}' is a built-in template and cannot be deleted.", file=sys.stderr)
        return 1

    template_path = tmpl.get("_path")
    if not template_path or not Path(template_path).exists():
        print(f"ERROR: Template file not found: {template_path}", file=sys.stderr)
        return 1

    Path(template_path).unlink()
    load_templates()

    print(f"Deleted custom template: {name}")
    print(f"  Removed: {template_path}")
    return 0


__all__ = [
    "cmd_list_templates",
    "cmd_show_template",
    "cmd_save_template",
    "cmd_delete_template",
]
