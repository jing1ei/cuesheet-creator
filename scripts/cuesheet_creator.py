#!/usr/bin/env python3
# ruff: noqa: F401, F811, I001, E402
"""cuesheet-creator -- turn a single video into a collaborative cue sheet.

This file is the CLI entry point. All business logic lives in the cc/ package.
Imports below are re-exported for backward compatibility with external consumers.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Import everything from the cc/ modular package
# ---------------------------------------------------------------------------

from cc.constants import (
    PREPARE_ENV_MODES,
    _CLI_COMMAND_OVERRIDES,
    __version__,
)
from cc.draft import cmd_draft_from_analysis
from cc.env import (
    cmd_install_deps,
    cmd_install_ffmpeg,
    cmd_prepare_env,
    cmd_selfcheck,
)
from cc.exporters.markdown import cmd_export_md
from cc.exporters.xlsx import cmd_build_xlsx
from cc.merge import cmd_merge_blocks, cmd_suggest_merges
from cc.naming import cmd_apply_naming, cmd_derive_naming_tables
from cc.normalize import cmd_normalize_fill
from cc.scan import cmd_scan_video
from cc.skeleton import cmd_build_final_skeleton
from cc.template_mgmt import (
    cmd_delete_template,
    cmd_list_templates,
    cmd_save_template,
    cmd_show_template,
)
from cc.templates import load_templates
from cc.utils import (
    ensure_parent,
    format_seconds,
    make_block_id,
    parse_fps,
    read_json,
    relpath_for_markdown,
    resolve_keyframe_path,
    resolved_path,
    run_command,
    safe_float,
    scale_dimensions,
    seconds_from_timecode,
    truncate_text,
    write_json,
)
from cc.validation import (
    cmd_validate_cue_json,
    evaluate_delivery_readiness,
    validate_temp_marker_coverage,
)

# Re-export additional symbols used by tests and external consumers
from cc.constants import (  # noqa: F811
    DEFAULT_COLUMN_WIDTHS,
    NAMING_CATEGORY_FIELDS,
    NAMING_REPLACE_FIELDS,
    OPTIONAL_COMPONENTS,
    REQUIRED_PACKAGES,
    SKILL_ROOT,
    SUPPORTED_OPTIONAL_GROUPS,
    TEMPLATE_COLUMNS,
    TEMPLATE_SCHEMA_VERSION,
    USER_DATA_DIR,
    _BUILTIN_TEMPLATE_COLUMNS,
    _BUILTIN_TEMPLATE_NAMES,
    _CC_PACKAGE_DIR,
    _STRUCTURAL_COLUMN_FIELDS,
    _TEMPLATE_REGISTRY,
    _TEMPLATE_REQUIRED_COLUMN_FIELDS,
    _TEMPLATE_REQUIRED_FIELDS,
    _TEMPLATE_REQUIRED_SEGMENTATION_FIELDS,
)
from cc.templates import (  # noqa: F811
    _template_column_widths_from_json,
    _template_columns_from_json,
    get_recommended_fields,
    get_required_fields,
    get_template_column_widths,
    get_template_definition,
    get_template_fill_guidance,
    get_template_perspective,
    get_template_prefill_map,
    get_template_segmentation,
    validate_template_json,
    validate_template_name,
)
from cc.naming import (  # noqa: F811
    _get_naming_fields_from_template,
    apply_naming_to_json_structured,
    apply_naming_to_text,
    derive_naming_tables_from_rows,
    extract_temp_markers,
    format_naming_tables_md,
)
from cc.normalize import (  # noqa: F811
    is_hint_only_value,
    normalize_motion,
    normalize_shot_size,
    strip_hint_prefixes,
)
from cc.env import (  # noqa: F811
    _common_ffmpeg_dirs,
    build_pip_install_command,
    check_command,
    check_module,
    collect_missing_python_packages,
    download_ffmpeg,
    ensure_pip_available,
    ffmpeg_install_hints,
    iter_local_ffmpeg_bin_dirs,
    load_requirements_constraints,
    make_selfcheck_report,
    normalize_optional_groups,
    print_install_report,
    print_prepare_env_report,
    print_selfcheck_text,
    resolve_command_path,
    resolve_prepare_env_output_paths,
    resolve_prepare_mode,
    run_install_deps_flow,
    stringify_output_paths,
    summarize_report,
)
from cc.scan import (  # noqa: F811
    build_draft_blocks,
    build_video_info,
    compute_frame_sharpness,
    compute_hist_distance,
    compute_visual_features,
    detect_scenes_scenedetect,
    estimate_motion_hint,
    extract_audio_track,
    ffprobe_metadata,
    read_frame_at,
    require_runtime_for_scan,
    resize_frame,
    run_asr_faster_whisper,
    run_ocr_on_frames,
    score_keyframe_candidates,
    build_contact_sheets,
)
from cc.merge import (  # noqa: F811
    _strategy_weight_multipliers,
    compute_block_continuity,
)
from cc.skeleton import cmd_build_final_skeleton  # noqa: F811

# Initialize template system
load_templates()


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="cuesheet-creator minimal toolkit")
    parser.add_argument("--version", action="version", version=f"cuesheet-creator {__version__}")
    parser.add_argument("--ffmpeg-path", type=resolved_path, default=None, help="Explicit path to ffmpeg executable (overrides auto-detection)")
    parser.add_argument("--ffprobe-path", type=resolved_path, default=None, help="Explicit path to ffprobe executable (overrides auto-detection)")
    parser.add_argument("--debug", action="store_true", default=False, help="Print full traceback on errors (also: CUESHEET_CREATOR_DEBUG=1)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- selfcheck ---
    selfcheck = subparsers.add_parser("selfcheck", help="Check runtime environment")
    selfcheck.add_argument("--json-out", type=resolved_path, help="Write JSON report to file")
    selfcheck.add_argument("--output-format", choices=["text", "json"], default="text")
    selfcheck.add_argument("--fail-on-missing-required", action="store_true")
    selfcheck.set_defaults(func=cmd_selfcheck)

    # --- install-deps ---
    install = subparsers.add_parser("install-deps", help="Install missing Python dependencies")
    install.add_argument("--include-optional", default="none", help="Optional dependency groups: none / scene / asr / ocr / ocr-extra / all / everything (comma-separated). 'all' = scene+asr+ocr; 'everything' = all groups incl. ocr-extra")
    install.add_argument("--dry-run", action="store_true", help="Output install plan only, do not install")
    install.add_argument("--report-out", type=resolved_path, help="Write install report JSON")
    install.add_argument("--output-format", choices=["text", "json"], default="text")
    install.add_argument("--index-url", help="pip index-url (e.g. domestic mirror)")
    install.add_argument("--extra-index-url", help="pip extra-index-url")
    install.add_argument("--upgrade-pip", action="store_true", help="Run pip install --upgrade pip first")
    install.add_argument("--fail-on-blocking", action="store_true", help="Return non-zero if blocking issues remain after install")
    install.set_defaults(func=cmd_install_deps)

    # --- install-ffmpeg ---
    install_ff = subparsers.add_parser("install-ffmpeg", help="Download and install FFmpeg to the local tools directory (Windows auto-download from gyan.dev)")
    install_ff.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without actually downloading")
    install_ff.add_argument("--output-format", choices=["text", "json"], default="text")
    install_ff.set_defaults(func=cmd_install_ffmpeg)

    # --- prepare-env ---
    prepare = subparsers.add_parser("prepare-env", help="One-command env check, install, and recheck")
    prepare.add_argument("--mode", choices=sorted(PREPARE_ENV_MODES), default="check-only", help="Prepare mode")
    prepare.add_argument("--out-dir", type=resolved_path, help="Output directory")
    prepare.add_argument("--dry-run", action="store_true", help="Output plan only, do not install")
    prepare.add_argument("--selfcheck-out", type=resolved_path, help="Write pre-check JSON")
    prepare.add_argument("--install-report-out", type=resolved_path, help="Write install-deps report JSON")
    prepare.add_argument("--postcheck-out", type=resolved_path, help="Write post-check JSON")
    prepare.add_argument("--report-out", type=resolved_path, help="Write prepare-env summary JSON")
    prepare.add_argument("--output-format", choices=["text", "json"], default="text")
    prepare.add_argument("--index-url", help="pip index-url")
    prepare.add_argument("--extra-index-url", help="pip extra-index-url")
    prepare.add_argument("--upgrade-pip", action="store_true", help="Run pip install --upgrade pip first")
    prepare.add_argument("--fail-on-blocking", action="store_true", help="Return non-zero if blocking issues remain")
    prepare.set_defaults(func=cmd_prepare_env)

    # --- scan-video ---
    scan = subparsers.add_parser("scan-video", help="Extract frames and generate analysis.json")
    scan.add_argument("--video", type=resolved_path, required=True, help="Video file path")
    scan.add_argument("--out-dir", type=resolved_path, default=None, help="Output directory (default: <video-dir>/<video-name>_cuesheet/)")
    scan.add_argument("--sample-interval", type=float, default=2.0, help="Sampling interval in seconds")
    scan.add_argument("--scene-threshold", type=float, default=0.35, help="Histogram cut threshold (fallback mode)")
    scan.add_argument("--content-threshold", type=float, default=27.0, help="PySceneDetect ContentDetector threshold")
    scan.add_argument("--max-samples", type=int, default=0, help="Max sample count, 0 for unlimited")
    scan.add_argument("--max-width", type=int, default=1280, help="Max keyframe export width")
    scan.add_argument("--asr", action="store_true", help="Enable ASR speech recognition (requires faster-whisper)")
    scan.add_argument("--asr-model", default="base", help="ASR model size: tiny / base / small / medium / large-v3")
    scan.add_argument("--asr-device", default="auto", help="ASR device: auto / cpu / cuda (default: auto)")
    scan.add_argument("--asr-compute-type", default="auto", help="ASR compute type: auto / int8 / float16 (default: auto)")
    scan.add_argument("--ocr", action="store_true", help="Enable OCR text detection (requires rapidocr / easyocr / paddleocr)")
    scan.add_argument("--start-time", default=None, help="Clip start time (HH:MM:SS.mmm or seconds). Note: SceneDetect still scans the full file; results are filtered to range.")
    scan.add_argument("--end-time", default=None, help="Clip end time (same formats). Histogram mode respects range directly.")
    scan.add_argument("--output-format", choices=["text", "json"], default="text", help="Output format")
    scan.set_defaults(func=cmd_scan_video)

    # --- draft-from-analysis ---
    draft = subparsers.add_parser("draft-from-analysis", help="Generate draft skeleton from analysis.json")
    draft.add_argument("--analysis-json", type=resolved_path, required=True, help="Path to analysis.json")
    draft.add_argument("--output", type=resolved_path, required=True, help="Output Markdown path")
    draft.add_argument("--template", default="production", help="Template name (default: production)")
    draft.add_argument("--output-format", choices=["text", "json"], default="text")
    draft.set_defaults(func=cmd_draft_from_analysis)

    # --- build-xlsx ---
    build = subparsers.add_parser("build-xlsx", help="Export Excel from final_cues.json")
    build.add_argument("--cue-json", type=resolved_path, required=True, help="Structured cue JSON")
    build.add_argument("--output", type=resolved_path, required=True, help="Output xlsx path")
    build.add_argument("--base-dir", type=resolved_path, help="Base directory for resolving relative keyframe paths")
    build.add_argument("--template", help="Override template in cue JSON")
    build.add_argument("--image-max-width", type=int, default=180)
    build.add_argument("--image-max-height", type=int, default=100)
    build.add_argument("--embed-keyframes", action="store_true", help="Force keyframe image embedding even if the template has no keyframe column (uses _keyframe field from final_cues.json)")
    build.add_argument("--output-format", choices=["text", "json"], default="text")
    build.add_argument("--fail-on-delivery-gap", action="store_true", help="Return non-zero exit code if delivery_ready is NO (for CI/pipeline use)")
    build.set_defaults(func=cmd_build_xlsx)

    # --- validate-cue-json ---
    validate = subparsers.add_parser("validate-cue-json", help="Validate final_cues.json structural integrity")
    validate.add_argument("--cue-json", type=resolved_path, required=True, help="Cue JSON to validate")
    validate.add_argument("--template", help="Override template for field validation")
    validate.add_argument("--report-out", type=resolved_path, help="Write validation report JSON")
    validate.add_argument("--base-dir", type=resolved_path, help="Base directory for resolving relative keyframe paths")
    validate.add_argument("--check-files", action="store_true", help="Verify that keyframe files actually exist on disk")
    validate.add_argument("--output-format", choices=["text", "json"], default="text")
    validate.set_defaults(func=cmd_validate_cue_json)

    # --- apply-naming ---
    apply_naming = subparsers.add_parser("apply-naming", help="Batch-apply naming overrides")
    apply_naming.add_argument("--overrides", type=resolved_path, required=True, help="Naming overrides JSON file")
    apply_naming.add_argument("--cue-json", type=resolved_path, help="final_cues.json to apply replacements to")
    apply_naming.add_argument("--md", type=resolved_path, help="cue_sheet.md to apply replacements to (modified in place)")
    apply_naming.add_argument("--output", type=resolved_path, help="Write updated JSON to this path instead of overwriting original (Markdown is always modified in place)")
    apply_naming.add_argument("--dry-run", action="store_true", help="Preview changes without writing files")
    apply_naming.add_argument("--report-out", type=resolved_path, help="Write replacement report JSON")
    apply_naming.add_argument("--output-format", choices=["text", "json"], default="text")
    apply_naming.set_defaults(func=cmd_apply_naming)

    # --- derive-naming-tables ---
    derive_naming = subparsers.add_parser("derive-naming-tables", help="Scan filled draft_fill.json for temp: markers")
    derive_naming.add_argument("--source-json", type=resolved_path, required=True, help="Filled draft_fill.json")
    derive_naming.add_argument("--output", type=resolved_path, required=True, help="Output naming_tables.json path")
    derive_naming.add_argument("--md", type=resolved_path, help="cue_sheet.md to update with derived naming tables")
    derive_naming.add_argument("--output-format", choices=["text", "json"], default="text")
    derive_naming.set_defaults(func=cmd_derive_naming_tables)

    # --- normalize-fill ---
    normalize = subparsers.add_parser("normalize-fill", help="Normalize/lint LLM-filled JSON")
    normalize.add_argument("--source-json", type=resolved_path, required=True, help="Filled draft_fill.json or final_cues.json")
    normalize.add_argument("--fix", action="store_true", help="Auto-normalize and write output (default: lint-only)")
    normalize.add_argument("--output", type=resolved_path, help="Output path for fixed JSON (default: overwrite source)")
    normalize.add_argument("--report-out", type=resolved_path, help="Write normalize report JSON")
    normalize.add_argument("--output-format", choices=["text", "json"], default="text")
    normalize.set_defaults(func=cmd_normalize_fill)

    # --- merge-blocks ---
    merge = subparsers.add_parser("merge-blocks", help="Merge draft blocks based on a merge plan")
    merge.add_argument("--analysis-json", type=resolved_path, required=True, help="Path to analysis.json")
    merge.add_argument("--merge-plan", type=resolved_path, required=True, help="Path to merge plan JSON")
    merge.add_argument("--output", type=resolved_path, required=True, help="Output merged blocks JSON")
    merge.add_argument("--strict", action="store_true", help="Fail on unreferenced blocks and time ordering issues")
    merge.add_argument("--output-format", choices=["text", "json"], default="text")
    merge.set_defaults(func=cmd_merge_blocks)

    # --- suggest-merges ---
    suggest = subparsers.add_parser("suggest-merges", help="Auto-suggest block merges based on visual continuity scoring")
    suggest.add_argument("--analysis-json", type=resolved_path, required=True, help="Path to analysis.json")
    suggest.add_argument("--output", type=resolved_path, required=True, help="Output suggested merge plan JSON")
    suggest.add_argument("--threshold", type=float, default=0.65, help="Continuity score threshold (0.0-1.0)")
    suggest.add_argument("--template", default=None, help="Template name for strategy-aware weight adjustment")
    suggest.add_argument("--output-format", choices=["text", "json"], default="text")
    suggest.set_defaults(func=cmd_suggest_merges)

    # --- export-md ---
    export_md = subparsers.add_parser("export-md", help="Generate Markdown final from final_cues.json")
    export_md.add_argument("--cue-json", type=resolved_path, required=True, help="Structured cue JSON")
    export_md.add_argument("--output", type=resolved_path, required=True, help="Output Markdown path")
    export_md.add_argument("--base-dir", type=resolved_path, help="Base directory for resolving relative keyframe paths")
    export_md.add_argument("--template", help="Override template in cue JSON")
    export_md.add_argument("--embed-keyframes", action="store_true", help="Force keyframe column even if the template has no keyframe column")
    export_md.add_argument("--output-format", choices=["text", "json"], default="text")
    export_md.add_argument("--fail-on-delivery-gap", action="store_true", help="Return non-zero exit code if delivery_ready is NO (for CI/pipeline use)")
    export_md.set_defaults(func=cmd_export_md)

    # --- build-final-skeleton ---
    skeleton = subparsers.add_parser("build-final-skeleton", help="Generate empty final_cues.json skeleton")
    skeleton.add_argument("--source-json", type=resolved_path, required=True, help="Merged blocks JSON or analysis.json")
    skeleton.add_argument("--output", type=resolved_path, required=True, help="Output final_cues.json skeleton path")
    skeleton.add_argument("--template", default=None, help="Template for field selection (default: from source JSON)")
    skeleton.add_argument("--video-title", default=None, help="Video title for the skeleton")
    skeleton.add_argument("--source-path", type=resolved_path, default=None, help="Video source path override")
    skeleton.add_argument("--output-format", choices=["text", "json"], default="text")
    skeleton.set_defaults(func=cmd_build_final_skeleton)

    # --- Template management ---
    list_tmpl = subparsers.add_parser("list-templates", help="List all available templates (built-in + custom)")
    list_tmpl.add_argument("--output-format", choices=["text", "json"], default="text")
    list_tmpl.set_defaults(func=cmd_list_templates)

    show_tmpl = subparsers.add_parser("show-template", help="Show full details of a template")
    show_tmpl.add_argument("--name", required=True, help="Template name to show")
    show_tmpl.add_argument("--output-format", choices=["text", "json"], default="text")
    show_tmpl.set_defaults(func=cmd_show_template)

    save_tmpl = subparsers.add_parser("save-template", help="Validate and save a template JSON to custom templates directory")
    save_tmpl.add_argument("--input", type=resolved_path, required=True, help="Path to template JSON file")
    save_tmpl.add_argument("--overwrite", action="store_true", help="Overwrite existing template with same name")
    save_tmpl.set_defaults(func=cmd_save_template)

    del_tmpl = subparsers.add_parser("delete-template", help="Delete a custom template (built-in templates cannot be deleted)")
    del_tmpl.add_argument("--name", required=True, help="Template name to delete")
    del_tmpl.set_defaults(func=cmd_delete_template)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    # Apply CLI overrides for ffmpeg/ffprobe paths
    if args.ffmpeg_path:
        _CLI_COMMAND_OVERRIDES["ffmpeg"] = args.ffmpeg_path
    if args.ffprobe_path:
        _CLI_COMMAND_OVERRIDES["ffprobe"] = args.ffprobe_path
    debug = args.debug or os.environ.get("CUESHEET_CREATOR_DEBUG", "").strip().lower() in ("1", "true", "yes")
    try:
        return int(args.func(args))
    except Exception as exc:
        if debug:
            import traceback
            traceback.print_exc()
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
            print("(use --debug or set CUESHEET_CREATOR_DEBUG=1 for full traceback)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
