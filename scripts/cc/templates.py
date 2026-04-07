"""Template system: registry, validation, column helpers."""
from __future__ import annotations

import json
import sys
from typing import Any

from cc.constants import (
    _BUILTIN_TEMPLATE_COLUMNS,
    _BUILTIN_TEMPLATE_NAMES,
    _CC_PACKAGE_DIR,
    _STRUCTURAL_COLUMN_FIELDS,
    _TEMPLATE_REGISTRY,
    _TEMPLATE_REQUIRED_COLUMN_FIELDS,
    _TEMPLATE_REQUIRED_FIELDS,
    _TEMPLATE_REQUIRED_SEGMENTATION_FIELDS,
    SKILL_ROOT,
    TEMPLATE_COLUMNS,
    TEMPLATE_SCHEMA_VERSION,
    USER_DATA_DIR,
)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_template_json(data: dict[str, Any]) -> list[str]:
    """Validate a template JSON dict. Returns list of error strings (empty = valid)."""
    errors: list[str] = []

    # Check schema version compatibility
    sv = data.get("schema_version")
    if sv is not None:
        if not isinstance(sv, int):
            errors.append(f"'schema_version' must be an integer, got {type(sv).__name__}")
        elif sv > TEMPLATE_SCHEMA_VERSION:
            errors.append(
                f"Template schema_version {sv} is newer than this script supports "
                f"(max {TEMPLATE_SCHEMA_VERSION}). Please upgrade cuesheet-creator."
            )

    # Check required top-level fields
    for field in _TEMPLATE_REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: '{field}'")

    name = data.get("name", "")
    if not name or not isinstance(name, str):
        errors.append("'name' must be a non-empty string")
    elif not all(c.isalnum() or c in "-_" for c in name):
        errors.append(f"'name' contains invalid characters: '{name}'. Use only alphanumeric, hyphens, underscores.")

    # Validate segmentation
    seg = data.get("segmentation")
    if isinstance(seg, dict):
        for sf in _TEMPLATE_REQUIRED_SEGMENTATION_FIELDS:
            if sf not in seg:
                errors.append(f"segmentation missing required field: '{sf}'")
        strategy = seg.get("strategy", "")
        if not strategy or not isinstance(strategy, str):
            errors.append("segmentation.strategy must be a non-empty string")
        for list_field in ("split_triggers", "merge_bias", "keyframe_priority"):
            val = seg.get(list_field)
            if val is not None and not isinstance(val, list):
                errors.append(f"segmentation.{list_field} must be a list")
    elif seg is not None:
        errors.append("'segmentation' must be a dict")

    # Validate columns
    columns = data.get("columns")
    _VALID_NAMING_CATEGORIES = {"characters", "scenes", "props"}
    if isinstance(columns, list):
        seen_fields: set[str] = set()
        has_structural = set()
        for idx, col in enumerate(columns):
            if not isinstance(col, dict):
                errors.append(f"columns[{idx}] must be a dict")
                continue
            for rf in _TEMPLATE_REQUIRED_COLUMN_FIELDS:
                if rf not in col:
                    errors.append(f"columns[{idx}] missing required field: '{rf}'")
            field_name = col.get("field", "")
            if field_name in seen_fields:
                errors.append(f"Duplicate column field name: '{field_name}'")
            seen_fields.add(field_name)
            if field_name in _STRUCTURAL_COLUMN_FIELDS:
                has_structural.add(field_name)
            # Validate naming_field type
            nf = col.get("naming_field")
            if nf is not None and not isinstance(nf, bool):
                errors.append(f"columns[{idx}] '{field_name}': naming_field must be a boolean")
            # Validate naming_category enum
            nc = col.get("naming_category")
            if nc is not None and nc not in _VALID_NAMING_CATEGORIES:
                errors.append(
                    f"columns[{idx}] '{field_name}': naming_category must be one of "
                    f"{', '.join(sorted(_VALID_NAMING_CATEGORIES))}, got '{nc}'"
                )
            # Validate width type
            w = col.get("width")
            if w is not None and not isinstance(w, int):
                errors.append(f"columns[{idx}] '{field_name}': width must be an integer")
        # Check that structural columns are present
        for sc in _STRUCTURAL_COLUMN_FIELDS:
            if sc not in has_structural:
                errors.append(f"Missing required structural column: '{sc}'. Templates must include shot_block, start_time, end_time.")
    elif columns is not None:
        errors.append("'columns' must be a list")

    return errors


# ---------------------------------------------------------------------------
# Column helpers
# ---------------------------------------------------------------------------

def _template_columns_from_json(data: dict[str, Any]) -> list[str]:
    """Extract ordered column field names from a template JSON definition."""
    columns = data.get("columns", [])
    return [col["field"] for col in columns if isinstance(col, dict) and "field" in col]


def _template_column_widths_from_json(data: dict[str, Any]) -> dict[str, int]:
    """Extract column width overrides from a template JSON definition."""
    widths: dict[str, int] = {}
    for col in data.get("columns", []):
        if isinstance(col, dict) and "field" in col and "width" in col:
            widths[col["field"]] = int(col["width"])
    return widths


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------

def load_templates() -> None:
    """Scan built-in and custom template directories, populate the runtime registry.

    Built-in templates are searched in this order:
      1. <skill-root>/templates/*.json   (source / editable install layout)
      2. cc/data/templates/*.json         (wheel-installed package data)
    Custom templates:
      - <skill-root>/templates/custom/*.json  (source layout)
      - ~/.cuesheet-creator/templates/custom/*.json (always, for both modes)
    """
    from pathlib import Path

    _TEMPLATE_REGISTRY.clear()
    TEMPLATE_COLUMNS.clear()
    _BUILTIN_TEMPLATE_NAMES.clear()

    # --- Built-in templates ---
    # Try source-layout first, then package-bundled data
    builtin_dirs: list[Path] = []
    source_tmpl_dir = SKILL_ROOT / "templates"
    if source_tmpl_dir.is_dir() and any(source_tmpl_dir.glob("*.json")):
        builtin_dirs.append(source_tmpl_dir)
    else:
        # Installed mode: templates bundled inside cc/data/templates/
        pkg_tmpl_dir = _CC_PACKAGE_DIR / "data" / "templates"
        if pkg_tmpl_dir.is_dir():
            builtin_dirs.append(pkg_tmpl_dir)

    for builtin_dir in builtin_dirs:
        for json_file in sorted(builtin_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                errors = validate_template_json(data)
                if errors:
                    print(f"WARNING: Skipping built-in template {json_file.name} — validation errors: {errors}", file=sys.stderr)
                    continue
                name = data.get("name", json_file.stem)
                data["_source"] = "built-in"
                data["_path"] = str(json_file)
                _TEMPLATE_REGISTRY[name] = data
                TEMPLATE_COLUMNS[name] = _template_columns_from_json(data)
                _BUILTIN_TEMPLATE_NAMES.add(name)
            except Exception as exc:
                print(f"WARNING: Failed to load built-in template {json_file.name}: {exc}", file=sys.stderr)

    # --- Custom templates ---
    # Search both source-layout custom dir and user-data custom dir
    custom_dirs: list[Path] = []
    source_custom = source_tmpl_dir / "custom"
    if source_custom.is_dir():
        custom_dirs.append(source_custom)
    user_custom = USER_DATA_DIR / "templates" / "custom"
    if user_custom.is_dir() and user_custom != source_custom:
        custom_dirs.append(user_custom)

    for custom_dir in custom_dirs:
        for json_file in sorted(custom_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                errors = validate_template_json(data)
                if errors:
                    print(f"WARNING: Skipping custom template {json_file.name} — validation errors: {errors}", file=sys.stderr)
                    continue
                name = data.get("name", json_file.stem)
                data["_source"] = "custom"
                data["_path"] = str(json_file)
                _TEMPLATE_REGISTRY[name] = data
                TEMPLATE_COLUMNS[name] = _template_columns_from_json(data)
            except Exception as exc:
                print(f"WARNING: Failed to load custom template {json_file.name}: {exc}", file=sys.stderr)

    # Fallback: if no templates were loaded from JSON, use the hardcoded ones
    if not TEMPLATE_COLUMNS:
        TEMPLATE_COLUMNS.update(_BUILTIN_TEMPLATE_COLUMNS)
        for name, cols in _BUILTIN_TEMPLATE_COLUMNS.items():
            _TEMPLATE_REGISTRY[name] = {
                "name": name,
                "description": f"Built-in {name} template (hardcoded fallback)",
                "columns": [{"field": f, "label": f} for f in cols],
                "_source": "hardcoded-fallback",
            }
            _BUILTIN_TEMPLATE_NAMES.add(name)


# ---------------------------------------------------------------------------
# Template accessors
# ---------------------------------------------------------------------------

def get_template_definition(name: str) -> dict[str, Any] | None:
    """Get the full template definition dict by name, or None if not found."""
    return _TEMPLATE_REGISTRY.get(name)


def get_template_segmentation(name: str) -> dict[str, Any]:
    """Get the segmentation config for a template. Returns empty dict if not found."""
    tmpl = _TEMPLATE_REGISTRY.get(name, {})
    return tmpl.get("segmentation", {})


def get_template_perspective(name: str) -> str:
    """Get the perspective text for a template."""
    tmpl = _TEMPLATE_REGISTRY.get(name, {})
    return tmpl.get("perspective", "")


def get_template_fill_guidance(name: str) -> list[str]:
    """Get the fill guidance list for a template."""
    tmpl = _TEMPLATE_REGISTRY.get(name, {})
    return tmpl.get("fill_guidance", [])


def get_template_prefill_map(name: str) -> dict[str, str | None]:
    """Get a field -> prefill_source mapping from the template definition.

    Returns {field_name: prefill_source_or_None} for all columns.
    This allows the pre-fill logic to be driven by template metadata
    instead of hardcoded field names.
    """
    tmpl = _TEMPLATE_REGISTRY.get(name)
    if tmpl and "columns" in tmpl:
        return {
            col["field"]: col.get("prefill_source")
            for col in tmpl["columns"]
            if isinstance(col, dict) and "field" in col
        }
    return {}


def get_template_column_widths(name: str) -> dict[str, int]:
    """Get column width overrides from a template definition."""
    tmpl = _TEMPLATE_REGISTRY.get(name)
    if tmpl:
        return _template_column_widths_from_json(tmpl)
    return {}


def validate_template_name(template: str) -> None:
    """Validate that a template name exists in the registry. Raises ValueError if not."""
    if template not in TEMPLATE_COLUMNS:
        available = ", ".join(sorted(TEMPLATE_COLUMNS.keys()))
        raise ValueError(
            f"Unknown template: '{template}'. Available templates: {available}"
        )


def get_recommended_fields(template: str) -> list[str]:
    """Get recommended fields from the template definition."""
    tmpl = _TEMPLATE_REGISTRY.get(template)
    if tmpl and "columns" in tmpl:
        return [
            col["field"] for col in tmpl["columns"]
            if isinstance(col, dict) and col.get("recommended", False)
        ]
    # Hardcoded fallback for backward compat
    _FALLBACK_RECOMMENDED: dict[str, list[str]] = {
        "production": ["scene", "event", "shot_size", "mood", "characters"],
        "music-director": ["mood", "event", "music_note", "rhythm_change", "dynamics"],
        "script": ["scene", "event", "characters", "location"],
    }
    return _FALLBACK_RECOMMENDED.get(template, [])


def get_required_fields(template: str) -> list[str]:
    """Get required content fields from the template definition.

    Returns fields marked required=true EXCLUDING structural fields
    (shot_block, start_time, end_time, keyframe) which are always
    enforced separately.
    """
    structural = {"shot_block", "start_time", "end_time", "keyframe"}
    tmpl = _TEMPLATE_REGISTRY.get(template)
    if tmpl and "columns" in tmpl:
        return [
            col["field"] for col in tmpl["columns"]
            if isinstance(col, dict) and col.get("required", False)
            and col.get("field", "") not in structural
        ]
    # Fallback: treat recommended as required for backward compat
    return get_recommended_fields(template)


__all__ = [
    "validate_template_json",
    "_template_columns_from_json",
    "_template_column_widths_from_json",
    "load_templates",
    "get_template_definition",
    "get_template_segmentation",
    "get_template_perspective",
    "get_template_fill_guidance",
    "get_template_prefill_map",
    "get_template_column_widths",
    "validate_template_name",
    "get_recommended_fields",
    "get_required_fields",
]
