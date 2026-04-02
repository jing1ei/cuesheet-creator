"""Minimal tests for cuesheet-creator core logic.

Run: python -m pytest tests/test_core.py -v
  or: python tests/test_core.py  (standalone, no pytest required)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Add scripts/ to path so we can import the module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cuesheet_creator as cc


# ---------------------------------------------------------------------------
# 1. Timecode parsing
# ---------------------------------------------------------------------------

def test_seconds_from_timecode_canonical():
    assert cc.seconds_from_timecode("00:01:23.456") == 83.456

def test_seconds_from_timecode_no_millis():
    assert cc.seconds_from_timecode("00:01:23") == 83.0

def test_seconds_from_timecode_mm_ss():
    assert cc.seconds_from_timecode("01:23.456") == 83.456

def test_seconds_from_timecode_mm_ss_no_millis():
    assert cc.seconds_from_timecode("01:23") == 83.0

def test_seconds_from_timecode_bare_seconds():
    assert cc.seconds_from_timecode("83") == 83.0

def test_seconds_from_timecode_bare_with_millis():
    assert cc.seconds_from_timecode("83.456") == 83.456

def test_seconds_from_timecode_srt_comma():
    assert cc.seconds_from_timecode("00:01:23,456") == 83.456

def test_seconds_from_timecode_two_digit_millis():
    """Two-digit millis should be left-padded: .12 → .120, not .012"""
    assert cc.seconds_from_timecode("00:00:05.12") == 5.120

def test_seconds_from_timecode_single_digit_millis():
    assert cc.seconds_from_timecode("00:00:05.1") == 5.100

def test_seconds_from_timecode_zero():
    assert cc.seconds_from_timecode("00:00:00.000") == 0.0

def test_seconds_from_timecode_bad_format():
    try:
        cc.seconds_from_timecode("not-a-time")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unrecognized timecode format" in str(e)

def test_seconds_from_timecode_empty():
    try:
        cc.seconds_from_timecode("")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Empty timecode" in str(e)


# ---------------------------------------------------------------------------
# 2. format_seconds round-trip
# ---------------------------------------------------------------------------

def test_format_seconds_round_trip():
    for original in [0.0, 1.5, 83.456, 3661.999, 7200.0]:
        formatted = cc.format_seconds(original)
        parsed = cc.seconds_from_timecode(formatted)
        assert abs(parsed - original) < 0.002, f"Round-trip failed: {original} → {formatted} → {parsed}"


# ---------------------------------------------------------------------------
# 3. Merge-blocks auto-append behavior
# ---------------------------------------------------------------------------

def test_merge_blocks_auto_append():
    """Unreferenced blocks should be auto-appended with unmerged=True in non-strict mode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        analysis = {
            "draft_blocks": [
                {"shot_block": "A1", "start_seconds": 0.0, "start_time": "00:00:00.000",
                 "end_seconds": 5.0, "end_time": "00:00:05.000", "keyframe": None},
                {"shot_block": "A2", "start_seconds": 5.0, "start_time": "00:00:05.000",
                 "end_seconds": 10.0, "end_time": "00:00:10.000", "keyframe": None},
                {"shot_block": "A3", "start_seconds": 10.0, "start_time": "00:00:10.000",
                 "end_seconds": 15.0, "end_time": "00:00:15.000", "keyframe": None},
            ]
        }
        merge_plan = {
            "merges": [
                {"source_blocks": ["A1", "A2"], "new_id": "B1", "keyframe": None, "reason": "test merge"}
            ]
        }
        # A3 is not referenced — should be auto-appended
        analysis_path = Path(tmpdir) / "analysis.json"
        merge_path = Path(tmpdir) / "merge_plan.json"
        output_path = Path(tmpdir) / "merged.json"

        analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
        merge_path.write_text(json.dumps(merge_plan), encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            analysis_json=str(analysis_path),
            merge_plan=str(merge_path),
            output=str(output_path),
            strict=False,
        )
        result = cc.cmd_merge_blocks(args)
        assert result == 0, "merge-blocks should succeed"

        output = json.loads(output_path.read_text(encoding="utf-8"))
        blocks = output["blocks"]
        assert len(blocks) == 2, f"Expected 2 blocks (1 merged + 1 appended), got {len(blocks)}"
        assert blocks[0]["shot_block"] == "B1"
        assert blocks[1]["shot_block"] == "A3"
        assert blocks[1].get("unmerged") is True, "Auto-appended block should have unmerged=True"


# ---------------------------------------------------------------------------
# 4. validate-cue-json behavior
# ---------------------------------------------------------------------------

def test_validate_sample_json():
    """The sample JSON should pass validation."""
    sample_path = Path(__file__).resolve().parent.parent / "assets" / "final_cues.sample.json"
    if not sample_path.exists():
        print(f"  SKIP (sample not found at {sample_path})")
        return

    import argparse
    args = argparse.Namespace(
        cue_json=str(sample_path),
        template=None,
        report_out=None,
        output_format="json",
        base_dir=None,
        check_files=False,
    )
    result = cc.cmd_validate_cue_json(args)
    assert result == 0, "Sample JSON should pass validation"


def test_validate_empty_rows():
    """A JSON with empty rows should fail validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cue_path = Path(tmpdir) / "empty.json"
        cue_path.write_text(json.dumps({"template": "production", "rows": []}), encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            cue_json=str(cue_path),
            template=None,
            report_out=None,
            output_format="json",
            base_dir=None,
            check_files=False,
        )
        result = cc.cmd_validate_cue_json(args)
        assert result == 1, "Empty rows should fail validation"


def test_validate_missing_keyframe_with_check_files():
    """When --check-files is set, missing keyframes should appear in delivery_gaps."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cue = {
            "template": "production",
            "rows": [{
                "shot_block": "A1",
                "start_time": "00:00:00.000",
                "end_time": "00:00:05.000",
                "keyframe": "keyframes/nonexistent.jpg",
                "shot_size": "WS",
                "angle_or_lens": "front",
                "motion": "static",
                "scene": "Test",
                "mood": "neutral",
                "location": "studio",
                "characters": "Actor",
                "event": "Test event",
                "important_dialogue": "",
                "music_note": "none",
                "director_note": "none",
                "confidence": "high",
                "needs_confirmation": "",
            }]
        }
        cue_path = Path(tmpdir) / "cue.json"
        report_path = Path(tmpdir) / "report.json"
        cue_path.write_text(json.dumps(cue), encoding="utf-8")

        import argparse
        args = argparse.Namespace(
            cue_json=str(cue_path),
            template=None,
            report_out=str(report_path),
            output_format="json",
            base_dir=tmpdir,
            check_files=True,
        )
        cc.cmd_validate_cue_json(args)

        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["valid"] is True, "Structurally valid"
        assert report["delivery_ready"] is False, "Missing keyframe should make delivery_ready=False"
        assert any("keyframe file not found" in g for g in report["delivery_gaps"])


# ---------------------------------------------------------------------------
# Runner (standalone, no pytest required)
# ---------------------------------------------------------------------------

def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for fn in tests:
        name = fn.__name__
        try:
            fn()
            print(f"  ✓ {name}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
