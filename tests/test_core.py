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
# 5. suggest-merges: threshold affects output
# ---------------------------------------------------------------------------

def _make_analysis_with_visual_features():
    """Build a synthetic analysis.json with 4 blocks.

    Blocks A1-A2 are visually similar (should merge at default threshold).
    Block A3 has a sharp visual break from A2 (should NOT merge).
    Block A4 is a short block after A3 (short_block_bonus, may merge with A3).
    """
    return {
        "draft_blocks": [
            {
                "shot_block": "A1", "start_seconds": 0.0, "end_seconds": 5.0,
                "start_time": "00:00:00.000", "end_time": "00:00:05.000",
                "keyframe": None, "candidate_score": 0.1,
                "visual_features": {
                    "brightness": 120.0, "contrast": 50.0,
                    "saturation": 80.0, "dominant_hue": 30.0,
                    "tone": "mid", "color_temp": "warm",
                },
            },
            {
                "shot_block": "A2", "start_seconds": 5.0, "end_seconds": 10.0,
                "start_time": "00:00:05.000", "end_time": "00:00:10.000",
                "keyframe": None, "candidate_score": 0.15,
                "visual_features": {
                    "brightness": 125.0, "contrast": 52.0,
                    "saturation": 82.0, "dominant_hue": 32.0,
                    "tone": "mid", "color_temp": "warm",
                },
            },
            {
                "shot_block": "A3", "start_seconds": 10.0, "end_seconds": 20.0,
                "start_time": "00:00:10.000", "end_time": "00:00:20.000",
                "keyframe": None, "candidate_score": 0.9,
                "visual_features": {
                    "brightness": 40.0, "contrast": 90.0,
                    "saturation": 20.0, "dominant_hue": 120.0,
                    "tone": "dark", "color_temp": "cool",
                },
            },
            {
                "shot_block": "A4", "start_seconds": 20.0, "end_seconds": 21.0,
                "start_time": "00:00:20.000", "end_time": "00:00:21.000",
                "keyframe": None, "candidate_score": 0.3,
                "visual_features": {
                    "brightness": 42.0, "contrast": 88.0,
                    "saturation": 22.0, "dominant_hue": 118.0,
                    "tone": "dark", "color_temp": "cool",
                },
            },
        ],
        "sampled_frames": [],
        "asr": {"status": "not-run", "segments": []},
    }


def test_suggest_merges_threshold_affects_output():
    """Changing --threshold should change which merges are suggested."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        analysis = _make_analysis_with_visual_features()
        analysis_path = Path(tmpdir) / "analysis.json"
        analysis_path.write_text(json.dumps(analysis), encoding="utf-8")

        # Low threshold: more merges
        out_low = Path(tmpdir) / "low.json"
        args_low = argparse.Namespace(
            analysis_json=str(analysis_path),
            output=str(out_low),
            threshold=0.3,
        )
        cc.cmd_suggest_merges(args_low)
        result_low = json.loads(out_low.read_text(encoding="utf-8"))
        merge_groups_low = [g for g in result_low["merges"] if len(g["source_blocks"]) > 1]

        # High threshold: fewer merges
        out_high = Path(tmpdir) / "high.json"
        args_high = argparse.Namespace(
            analysis_json=str(analysis_path),
            output=str(out_high),
            threshold=0.95,
        )
        cc.cmd_suggest_merges(args_high)
        result_high = json.loads(out_high.read_text(encoding="utf-8"))
        merge_groups_high = [g for g in result_high["merges"] if len(g["source_blocks"]) > 1]

        assert len(merge_groups_low) > len(merge_groups_high), (
            f"Lower threshold should produce more merge groups: "
            f"low({len(merge_groups_low)}) vs high({len(merge_groups_high)})"
        )
        # Verify threshold is recorded
        assert result_low["threshold"] == 0.3
        assert result_high["threshold"] == 0.95


def test_suggest_merges_pairwise_scores_present():
    """Each pair should have continuity_score and component_scores."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        analysis = _make_analysis_with_visual_features()
        analysis_path = Path(tmpdir) / "analysis.json"
        out_path = Path(tmpdir) / "suggest.json"
        analysis_path.write_text(json.dumps(analysis), encoding="utf-8")

        args = argparse.Namespace(
            analysis_json=str(analysis_path),
            output=str(out_path),
            threshold=0.65,
        )
        cc.cmd_suggest_merges(args)
        result = json.loads(out_path.read_text(encoding="utf-8"))

        pairs = result["pairwise_scores"]
        assert len(pairs) == 3, f"4 blocks should produce 3 pairs, got {len(pairs)}"
        for pair in pairs:
            assert "continuity_score" in pair
            assert "component_scores" in pair
            assert "suggest_merge" in pair
            assert isinstance(pair["continuity_score"], (int, float))


# ---------------------------------------------------------------------------
# 6. draft-from-analysis: draft_fill.json correctness
# ---------------------------------------------------------------------------

def _make_synthetic_analysis(tmpdir, asr_segments=None, ocr_detections=None):
    """Build a minimal synthetic analysis.json with 2 blocks."""
    kf_dir = Path(tmpdir) / "keyframes"
    kf_dir.mkdir(exist_ok=True)
    # Create dummy keyframe files
    kf1 = kf_dir / "frame_0001_0000000000.jpg"
    kf2 = kf_dir / "frame_0002_0000005000.jpg"
    kf1.write_bytes(b"\xff\xd8\xff\xe0")  # minimal JPEG header
    kf2.write_bytes(b"\xff\xd8\xff\xe0")

    analysis = {
        "video": {
            "source_path": "/fake/path/my_cool_video.mp4",
            "duration_seconds": 10.0,
            "duration_timecode": "00:00:10.000",
            "resolution": {"width": 1920, "height": 1080},
            "fps": 24.0,
            "audio_tracks": 1,
        },
        "agent_summary": {
            "total_blocks": 2,
            "blocks": [
                {"id": "A1", "start": "00:00:00.000", "end": "00:00:05.000",
                 "keyframe": "keyframes/frame_0001_0000000000.jpg"},
                {"id": "A2", "start": "00:00:05.000", "end": "00:00:10.000",
                 "keyframe": "keyframes/frame_0002_0000005000.jpg"},
            ],
            "keyframe_batches": [[str(kf1), str(kf2)]],
            "asr_status": "ok" if asr_segments else "not-run",
            "asr_segments": [],
            "ocr_status": "ok" if ocr_detections else "not-run",
            "ocr_detections": [],
        },
        "analysis_config": {
            "detection_method": "scenedetect",
            "effective_range": {"is_clip": False},
        },
        "draft_blocks": [
            {
                "shot_block": "A1", "start_seconds": 0.0, "end_seconds": 5.0,
                "start_time": "00:00:00.000", "end_time": "00:00:05.000",
                "keyframe": str(kf1), "candidate_score": 1.0,
                "visual_features": {
                    "brightness": 120.0, "contrast": 55.0,
                    "saturation": 80.0, "dominant_hue": 15.0,
                    "tone": "mid", "color_temp": "warm",
                },
            },
            {
                "shot_block": "A2", "start_seconds": 5.0, "end_seconds": 10.0,
                "start_time": "00:00:05.000", "end_time": "00:00:10.000",
                "keyframe": str(kf2), "candidate_score": 0.8,
                "visual_features": {
                    "brightness": 60.0, "contrast": 80.0,
                    "saturation": 30.0, "dominant_hue": 100.0,
                    "tone": "dark", "color_temp": "cool",
                },
            },
        ],
        "asr": {
            "status": "ok" if asr_segments else "not-run",
            "segments": asr_segments or [],
        },
        "ocr": {
            "status": "ok" if ocr_detections else "not-run",
            "detections": ocr_detections or [],
        },
        "notes": [],
    }
    return analysis


def test_draft_fill_json_video_title_is_stem():
    """draft_fill.json video_title should be Path.stem, not the full path."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        analysis = _make_synthetic_analysis(tmpdir)
        analysis_path = Path(tmpdir) / "analysis.json"
        analysis_path.write_text(json.dumps(analysis), encoding="utf-8")

        md_out = Path(tmpdir) / "cue_sheet.md"
        args = argparse.Namespace(
            analysis_json=str(analysis_path),
            output=str(md_out),
            template="production",
        )
        result = cc.cmd_draft_from_analysis(args)
        assert result == 0, "draft-from-analysis should succeed"

        fill_path = Path(tmpdir) / "draft_fill.json"
        assert fill_path.exists(), "draft_fill.json should be created"
        fill = json.loads(fill_path.read_text(encoding="utf-8"))

        # video_title should be stem only, not full path
        assert fill["video_title"] == "my_cool_video", (
            f"Expected 'my_cool_video', got '{fill['video_title']}'"
        )
        assert "/" not in fill["video_title"], "video_title should not contain path separators"
        assert "\\" not in fill["video_title"], "video_title should not contain backslash"


def test_draft_fill_json_fill_status():
    """fill_status should be 'partial' when pre-fills exist (e.g. confidence)."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        analysis = _make_synthetic_analysis(tmpdir)
        analysis_path = Path(tmpdir) / "analysis.json"
        analysis_path.write_text(json.dumps(analysis), encoding="utf-8")

        md_out = Path(tmpdir) / "cue_sheet.md"
        args = argparse.Namespace(
            analysis_json=str(analysis_path),
            output=str(md_out),
            template="production",
        )
        cc.cmd_draft_from_analysis(args)

        fill_path = Path(tmpdir) / "draft_fill.json"
        fill = json.loads(fill_path.read_text(encoding="utf-8"))

        # confidence and needs_confirmation are always pre-filled → status should be partial
        assert fill["fill_status"] == "partial", (
            f"Expected 'partial' (pre-fills exist), got '{fill['fill_status']}'"
        )


def test_draft_fill_json_asr_prefills_dialogue():
    """ASR segments should pre-fill important_dialogue for overlapping blocks."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        asr_segments = [
            {"start": 1.0, "end": 3.5, "start_time": "00:00:01.000",
             "end_time": "00:00:03.500", "text": "Hello world"},
            {"start": 6.0, "end": 8.0, "start_time": "00:00:06.000",
             "end_time": "00:00:08.000", "text": "Second segment"},
        ]
        analysis = _make_synthetic_analysis(tmpdir, asr_segments=asr_segments)
        analysis_path = Path(tmpdir) / "analysis.json"
        analysis_path.write_text(json.dumps(analysis), encoding="utf-8")

        md_out = Path(tmpdir) / "cue_sheet.md"
        args = argparse.Namespace(
            analysis_json=str(analysis_path),
            output=str(md_out),
            template="production",
        )
        cc.cmd_draft_from_analysis(args)

        fill_path = Path(tmpdir) / "draft_fill.json"
        fill = json.loads(fill_path.read_text(encoding="utf-8"))
        rows = fill["rows"]

        # Block A1 (0-5s) should have "Hello world" from ASR
        a1_dialogue = rows[0].get("important_dialogue", "")
        assert "Hello world" in a1_dialogue, (
            f"A1 dialogue should contain ASR text, got: '{a1_dialogue}'"
        )

        # Block A2 (5-10s) should have "Second segment" from ASR
        a2_dialogue = rows[1].get("important_dialogue", "")
        assert "Second segment" in a2_dialogue, (
            f"A2 dialogue should contain ASR text, got: '{a2_dialogue}'"
        )


def test_draft_fill_json_ocr_prefills():
    """OCR detections should pre-fill director_note with [OCR detected: ...] hints."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create the keyframe files with known names
        kf_dir = Path(tmpdir) / "keyframes"
        kf_dir.mkdir(exist_ok=True)
        kf1 = kf_dir / "frame_0001_0000000000.jpg"
        kf1.write_bytes(b"\xff\xd8\xff\xe0")

        ocr_detections = [
            {"frame": str(kf1), "texts": ["GAME OVER", "Score: 100"], "engine": "rapidocr"},
        ]
        analysis = _make_synthetic_analysis(tmpdir, ocr_detections=ocr_detections)
        analysis_path = Path(tmpdir) / "analysis.json"
        analysis_path.write_text(json.dumps(analysis), encoding="utf-8")

        md_out = Path(tmpdir) / "cue_sheet.md"
        args = argparse.Namespace(
            analysis_json=str(analysis_path),
            output=str(md_out),
            template="production",
        )
        cc.cmd_draft_from_analysis(args)

        fill_path = Path(tmpdir) / "draft_fill.json"
        fill = json.loads(fill_path.read_text(encoding="utf-8"))
        rows = fill["rows"]

        # Block A1 should have OCR hints in director_note or event
        a1 = rows[0]
        ocr_found = False
        for field in ("director_note", "event"):
            if "[OCR detected:" in a1.get(field, ""):
                ocr_found = True
                break
        assert ocr_found, (
            f"A1 should have OCR hint in director_note or event, got: "
            f"director_note='{a1.get('director_note', '')}', event='{a1.get('event', '')}'"
        )


def test_draft_fill_json_mood_visual_hints():
    """Mood field should contain [visual: ...] hints derived from visual features."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        analysis = _make_synthetic_analysis(tmpdir)
        analysis_path = Path(tmpdir) / "analysis.json"
        analysis_path.write_text(json.dumps(analysis), encoding="utf-8")

        md_out = Path(tmpdir) / "cue_sheet.md"
        args = argparse.Namespace(
            analysis_json=str(analysis_path),
            output=str(md_out),
            template="production",
        )
        cc.cmd_draft_from_analysis(args)

        fill_path = Path(tmpdir) / "draft_fill.json"
        fill = json.loads(fill_path.read_text(encoding="utf-8"))
        rows = fill["rows"]

        # A1 has warm color_temp → should have visual hint
        a1_mood = rows[0].get("mood", "")
        assert "[visual:" in a1_mood, (
            f"A1 mood should have [visual: ...] hint for warm color, got: '{a1_mood}'"
        )

        # A2 has dark tone + cool color → should have visual hint
        a2_mood = rows[1].get("mood", "")
        assert "[visual:" in a2_mood, (
            f"A2 mood should have [visual: ...] hint for dark/cool, got: '{a2_mood}'"
        )


# ---------------------------------------------------------------------------
# 7. build-final-skeleton: reads draft_fill.json and preserves content
# ---------------------------------------------------------------------------

def test_build_final_skeleton_from_filled_draft():
    """build-final-skeleton should read draft_fill.json with partial fill and preserve content."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        draft_fill = {
            "template": "production",
            "video_title": "test_video",
            "source_path": "/fake/test_video.mp4",
            "fill_status": "partial",
            "rows": [
                {
                    "shot_block": "A1",
                    "start_time": "00:00:00.000",
                    "end_time": "00:00:05.000",
                    "keyframe": "keyframes/A1.jpg",
                    "shot_size": "WS",
                    "angle_or_lens": "front",
                    "motion": "static",
                    "scene": "temp: Hall",
                    "mood": "calm",
                    "location": "interior",
                    "characters": "temp: Girl-A",
                    "event": "Establishing shot",
                    "important_dialogue": "Hello world",
                    "music_note": "pad",
                    "director_note": "Watch framing",
                    "confidence": "segment=high; names=low",
                    "needs_confirmation": "character names",
                },
            ],
        }
        fill_path = Path(tmpdir) / "draft_fill.json"
        fill_path.write_text(json.dumps(draft_fill), encoding="utf-8")

        out_path = Path(tmpdir) / "final_cues.json"
        args = argparse.Namespace(
            source_json=str(fill_path),
            output=str(out_path),
            template="production",
            video_title=None,
            source_path=None,
        )
        result = cc.cmd_build_final_skeleton(args)
        assert result == 0, "build-final-skeleton should succeed"

        final = json.loads(out_path.read_text(encoding="utf-8"))
        assert final["template"] == "production"
        assert final["video_title"] == "test_video"
        assert len(final["rows"]) == 1

        row = final["rows"][0]
        # All filled content should be preserved
        assert row["shot_size"] == "WS", f"shot_size not preserved: {row.get('shot_size')}"
        assert row["scene"] == "temp: Hall", f"scene not preserved: {row.get('scene')}"
        assert row["mood"] == "calm", f"mood not preserved: {row.get('mood')}"
        assert row["event"] == "Establishing shot"
        assert row["important_dialogue"] == "Hello world"
        assert row["director_note"] == "Watch framing"


def test_build_final_skeleton_video_title_from_source_path():
    """When video_title is not in source, it should derive from source_path stem."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        # analysis.json-like source without video_title
        source = {
            "video": {"source_path": "/videos/project_alpha.mp4"},
            "draft_blocks": [
                {
                    "shot_block": "A1",
                    "start_time": "00:00:00.000",
                    "end_time": "00:00:05.000",
                    "keyframe": "",
                },
            ],
        }
        source_path = Path(tmpdir) / "analysis.json"
        source_path.write_text(json.dumps(source), encoding="utf-8")

        out_path = Path(tmpdir) / "final.json"
        args = argparse.Namespace(
            source_json=str(source_path),
            output=str(out_path),
            template="production",
            video_title=None,
            source_path=None,
        )
        cc.cmd_build_final_skeleton(args)

        final = json.loads(out_path.read_text(encoding="utf-8"))
        assert final["video_title"] == "project_alpha", (
            f"video_title should be stem 'project_alpha', got '{final['video_title']}'"
        )


# ---------------------------------------------------------------------------
# 8. build-xlsx: empty rows → delivery_ready: NO
# ---------------------------------------------------------------------------

def test_build_xlsx_empty_rows_not_delivery_ready():
    """build-xlsx with zero rows should report delivery_ready: NO (via stdout check)."""
    import argparse
    import io
    import contextlib

    # Skip if openpyxl not available
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        print("  SKIP (openpyxl not installed)")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        cue = {
            "template": "production",
            "video_title": "test",
            "source_path": "",
            "rows": [],
        }
        cue_path = Path(tmpdir) / "cue.json"
        cue_path.write_text(json.dumps(cue), encoding="utf-8")

        out_path = Path(tmpdir) / "cue.xlsx"
        args = argparse.Namespace(
            cue_json=str(cue_path),
            output=str(out_path),
            base_dir=tmpdir,
            template=None,
            image_max_width=180,
            image_max_height=100,
        )

        # Capture stdout
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            result = cc.cmd_build_xlsx(args)

        assert result == 0, "build-xlsx should succeed even with empty rows"
        assert out_path.exists(), "xlsx file should be created"

        output_text = captured.getvalue()
        assert "delivery_ready: NO" in output_text, (
            f"Empty rows should report delivery_ready: NO, got: {output_text}"
        )


def test_build_xlsx_filled_rows_delivery_ready():
    """build-xlsx with fully filled rows should report delivery_ready: YES."""
    import argparse
    import io
    import contextlib

    # Skip if openpyxl or PIL not available
    try:
        import openpyxl  # noqa: F401
        from PIL import Image as PILImage
    except ImportError:
        print("  SKIP (openpyxl or Pillow not installed)")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a dummy keyframe
        kf_dir = Path(tmpdir) / "keyframes"
        kf_dir.mkdir()
        kf_path = kf_dir / "A1.jpg"
        img = PILImage.new("RGB", (100, 100), color="red")
        img.save(str(kf_path), "JPEG")

        cue = {
            "template": "production",
            "video_title": "test",
            "source_path": "",
            "rows": [{
                "shot_block": "A1",
                "start_time": "00:00:00.000",
                "end_time": "00:00:05.000",
                "keyframe": "keyframes/A1.jpg",
                "shot_size": "WS",
                "angle_or_lens": "front",
                "motion": "static",
                "scene": "Test Scene",
                "mood": "neutral",
                "location": "studio",
                "characters": "Actor",
                "event": "Test event",
                "important_dialogue": "Hello",
                "music_note": "pad",
                "director_note": "note",
                "confidence": "high",
                "needs_confirmation": "",
            }],
        }
        cue_path = Path(tmpdir) / "cue.json"
        cue_path.write_text(json.dumps(cue), encoding="utf-8")

        out_path = Path(tmpdir) / "cue.xlsx"
        args = argparse.Namespace(
            cue_json=str(cue_path),
            output=str(out_path),
            base_dir=tmpdir,
            template=None,
            image_max_width=180,
            image_max_height=100,
        )

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            result = cc.cmd_build_xlsx(args)

        assert result == 0
        output_text = captured.getvalue()
        assert "delivery_ready: YES" in output_text, (
            f"Fully filled rows should be delivery_ready, got: {output_text}"
        )


# ---------------------------------------------------------------------------
# 9. apply-naming: JSON and MD targets get consistent replacements
# ---------------------------------------------------------------------------

def test_apply_naming_json_and_md_consistent():
    """apply-naming should replace the same names in both JSON and MD targets."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        overrides = {
            "characters": {"temp: Girl-A": "Lin Xia", "temp: Boy-B": "Gu Yan"},
            "scenes": {"temp: Main Hall": "Central Hall"},
            "props": {},
        }
        overrides_path = Path(tmpdir) / "naming.json"
        overrides_path.write_text(json.dumps(overrides), encoding="utf-8")

        cue = {
            "template": "production",
            "rows": [
                {
                    "shot_block": "A1",
                    "start_time": "00:00:00.000",
                    "end_time": "00:00:05.000",
                    "keyframe": "",
                    "scene": "temp: Main Hall",
                    "characters": "temp: Girl-A; temp: Boy-B",
                    "location": "interior temp: Main Hall",
                    "event": "temp: Girl-A meets temp: Boy-B",
                    "needs_confirmation": "temp: Girl-A; temp: Boy-B; temp: Main Hall",
                    "shot_size": "WS", "angle_or_lens": "front", "motion": "static",
                    "mood": "neutral", "important_dialogue": "",
                    "music_note": "", "director_note": "", "confidence": "high",
                },
            ],
        }
        cue_path = Path(tmpdir) / "final_cues.json"
        cue_path.write_text(json.dumps(cue), encoding="utf-8")

        md_content = (
            "# Cue Sheet\n\n"
            "| A1 | temp: Main Hall | temp: Girl-A; temp: Boy-B |\n"
            "temp: Girl-A meets temp: Boy-B in temp: Main Hall.\n"
        )
        md_path = Path(tmpdir) / "cue_sheet.md"
        md_path.write_text(md_content, encoding="utf-8")

        json_out = Path(tmpdir) / "final_cues_named.json"
        args = argparse.Namespace(
            overrides=str(overrides_path),
            cue_json=str(cue_path),
            md=str(md_path),
            output=str(json_out),
            dry_run=False,
            report_out=None,
        )
        result = cc.cmd_apply_naming(args)
        assert result == 0, "apply-naming should succeed"

        # Check JSON output
        named_cue = json.loads(json_out.read_text(encoding="utf-8"))
        row = named_cue["rows"][0]
        assert "Lin Xia" in row["characters"], f"JSON characters not renamed: {row['characters']}"
        assert "Gu Yan" in row["characters"], f"JSON characters missing Gu Yan: {row['characters']}"
        assert row["scene"] == "Central Hall", f"JSON scene not renamed: {row['scene']}"
        assert "temp: Girl-A" not in row["characters"], "Old temp name should be gone from JSON"
        assert "Lin Xia" in row["event"], f"JSON event not renamed: {row['event']}"

        # Check MD output (applied in-place)
        md_updated = md_path.read_text(encoding="utf-8")
        assert "Lin Xia" in md_updated, f"MD not renamed: {md_updated}"
        assert "Central Hall" in md_updated, f"MD scene not renamed: {md_updated}"
        assert "temp: Girl-A" not in md_updated, "Old temp name should be gone from MD"


def test_apply_naming_dry_run_no_modification():
    """--dry-run should not modify any files."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        overrides = {
            "characters": {"temp: Girl-A": "Lin Xia"},
            "scenes": {},
            "props": {},
        }
        overrides_path = Path(tmpdir) / "naming.json"
        overrides_path.write_text(json.dumps(overrides), encoding="utf-8")

        cue = {
            "template": "production",
            "rows": [{
                "shot_block": "A1", "start_time": "00:00:00.000",
                "end_time": "00:00:05.000", "keyframe": "",
                "characters": "temp: Girl-A",
                "scene": "", "location": "", "event": "",
                "needs_confirmation": "", "shot_size": "", "angle_or_lens": "",
                "motion": "", "mood": "", "important_dialogue": "",
                "music_note": "", "director_note": "", "confidence": "",
            }],
        }
        cue_path = Path(tmpdir) / "final_cues.json"
        original_content = json.dumps(cue, ensure_ascii=False, indent=2)
        cue_path.write_text(original_content, encoding="utf-8")

        args = argparse.Namespace(
            overrides=str(overrides_path),
            cue_json=str(cue_path),
            md=None,
            output=None,
            dry_run=True,
            report_out=None,
        )
        cc.cmd_apply_naming(args)

        # File should NOT be modified
        after = cue_path.read_text(encoding="utf-8")
        assert after == original_content, "dry-run should not modify the file"


def test_apply_naming_longest_key_first():
    """Longer keys should be replaced first to avoid substring collision."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        # "temp: Girl-A-Long" contains "temp: Girl-A" as a substring
        overrides = {
            "characters": {
                "temp: Girl-A-Long": "Zhang Wei",
                "temp: Girl-A": "Lin Xia",
            },
            "scenes": {},
            "props": {},
        }
        overrides_path = Path(tmpdir) / "naming.json"
        overrides_path.write_text(json.dumps(overrides), encoding="utf-8")

        cue = {
            "template": "production",
            "rows": [{
                "shot_block": "A1", "start_time": "00:00:00.000",
                "end_time": "00:00:05.000", "keyframe": "",
                "characters": "temp: Girl-A-Long and temp: Girl-A",
                "scene": "", "location": "", "event": "",
                "needs_confirmation": "", "shot_size": "", "angle_or_lens": "",
                "motion": "", "mood": "", "important_dialogue": "",
                "music_note": "", "director_note": "", "confidence": "",
            }],
        }
        cue_path = Path(tmpdir) / "final_cues.json"
        cue_path.write_text(json.dumps(cue), encoding="utf-8")
        out_path = Path(tmpdir) / "out.json"

        args = argparse.Namespace(
            overrides=str(overrides_path),
            cue_json=str(cue_path),
            md=None,
            output=str(out_path),
            dry_run=False,
            report_out=None,
        )
        cc.cmd_apply_naming(args)

        result = json.loads(out_path.read_text(encoding="utf-8"))
        chars = result["rows"][0]["characters"]
        assert "Zhang Wei" in chars, f"Longer key should match first: {chars}"
        assert "Lin Xia" in chars, f"Shorter key should also match: {chars}"
        # "Zhang Wei" should NOT be further mangled by the shorter key
        assert "Lin Xia Wei" not in chars, f"Substring collision detected: {chars}"


# ---------------------------------------------------------------------------
# 10. derive-naming-tables
# ---------------------------------------------------------------------------

def test_derive_naming_tables_extracts_temp_markers():
    """derive-naming-tables should find temp: markers and group by category."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        draft_fill = {
            "template": "production",
            "video_title": "test",
            "source_path": "",
            "fill_status": "complete",
            "rows": [
                {
                    "shot_block": "A1", "start_time": "00:00:00.000",
                    "end_time": "00:00:05.000", "keyframe": "",
                    "shot_size": "WS", "angle_or_lens": "front",
                    "motion": "static", "scene": "temp: Main Hall",
                    "mood": "calm", "location": "interior temp: Main Hall",
                    "characters": "temp: Girl-A; temp: Boy-B",
                    "event": "temp: Girl-A enters",
                    "important_dialogue": "", "music_note": "",
                    "director_note": "", "confidence": "high",
                    "needs_confirmation": "",
                },
                {
                    "shot_block": "A2", "start_time": "00:00:05.000",
                    "end_time": "00:00:10.000", "keyframe": "",
                    "shot_size": "CU", "angle_or_lens": "front",
                    "motion": "static", "scene": "temp: Main Hall",
                    "mood": "tense", "location": "interior temp: Main Hall",
                    "characters": "temp: Girl-A",
                    "event": "Close-up on temp: Girl-A",
                    "important_dialogue": "", "music_note": "",
                    "director_note": "", "confidence": "high",
                    "needs_confirmation": "",
                },
            ],
        }
        fill_path = Path(tmpdir) / "draft_fill.json"
        fill_path.write_text(json.dumps(draft_fill), encoding="utf-8")

        out_path = Path(tmpdir) / "naming_tables.json"
        args = argparse.Namespace(
            source_json=str(fill_path),
            output=str(out_path),
            md=None,
        )
        result = cc.cmd_derive_naming_tables(args)
        assert result == 0, "derive-naming-tables should succeed"

        tables = json.loads(out_path.read_text(encoding="utf-8"))
        chars = tables["tables"]["characters"]
        scenes = tables["tables"]["scenes"]

        # Girl-A should appear in both A1 and A2
        girl_a = next((c for c in chars if "Girl-A" in c["temporary_name"]), None)
        assert girl_a is not None, f"temp: Girl-A not found in characters: {chars}"
        assert "A1" in girl_a["appears_in_blocks"] and "A2" in girl_a["appears_in_blocks"], (
            f"Girl-A should appear in A1 and A2, got: {girl_a['appears_in_blocks']}"
        )

        # Boy-B should appear only in A1
        boy_b = next((c for c in chars if "Boy-B" in c["temporary_name"]), None)
        assert boy_b is not None, f"temp: Boy-B not found in characters: {chars}"
        assert boy_b["appears_in_blocks"] == ["A1"], (
            f"Boy-B should appear only in A1, got: {boy_b['appears_in_blocks']}"
        )

        # Main Hall in scenes
        main_hall = next((s for s in scenes if "Main Hall" in s["temporary_name"]), None)
        assert main_hall is not None, f"temp: Main Hall not found in scenes: {scenes}"
        assert set(main_hall["appears_in_blocks"]) == {"A1", "A2"}

        assert tables["total_temp_markers"] >= 3, (
            f"Expected at least 3 unique markers, got {tables['total_temp_markers']}"
        )


def test_derive_naming_tables_updates_markdown():
    """derive-naming-tables should replace naming tables section in cue_sheet.md."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        draft_fill = {
            "template": "production",
            "fill_status": "complete",
            "rows": [{
                "shot_block": "A1", "start_time": "00:00:00.000",
                "end_time": "00:00:05.000", "keyframe": "",
                "characters": "temp: Girl-A",
                "scene": "temp: Main Hall",
                "shot_size": "", "angle_or_lens": "", "motion": "",
                "mood": "", "location": "", "event": "",
                "important_dialogue": "", "music_note": "",
                "director_note": "", "confidence": "", "needs_confirmation": "",
            }],
        }
        fill_path = Path(tmpdir) / "draft_fill.json"
        fill_path.write_text(json.dumps(draft_fill), encoding="utf-8")

        # Create a cue_sheet.md with placeholder naming tables
        md_path = Path(tmpdir) / "cue_sheet.md"
        md_path.write_text(
            "# Cue Sheet\n\n"
            "## Naming Confirmation Tables\n\n"
            "### Characters\n\n"
            "| temporary_name | evidence | confidence | confirmed_name | status |\n"
            "|---|---|---|---|---|\n"
            "| temp: Character-A | placeholder | low |  | pending |\n\n"
            "## Pending Questions\n\n"
            "- Do characters have official names?\n",
            encoding="utf-8",
        )

        out_path = Path(tmpdir) / "naming_tables.json"
        args = argparse.Namespace(
            source_json=str(fill_path),
            output=str(out_path),
            md=str(md_path),
        )
        cc.cmd_derive_naming_tables(args)

        updated_md = md_path.read_text(encoding="utf-8")
        # Should now contain actual derived names, not placeholders
        assert "temp: Girl-A" in updated_md, "Derived temp: Girl-A should be in MD"
        assert "temp: Main Hall" in updated_md, "Derived temp: Main Hall should be in MD"
        # Placeholder should be gone
        assert "temp: Character-A" not in updated_md, "Old placeholder should be replaced"
        # Pending Questions section should still exist
        assert "## Pending Questions" in updated_md, "Pending Questions should be preserved"


# ---------------------------------------------------------------------------
# 11. normalize-fill
# ---------------------------------------------------------------------------

def test_normalize_fill_lint_mode():
    """normalize-fill in lint mode should report issues without modifying the file."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        source = {
            "template": "production",
            "fill_status": "complete",
            "rows": [{
                "shot_block": "A1", "start_time": "00:00:00.000",
                "end_time": "00:00:05.000", "keyframe": "",
                "shot_size": "wide shot",  # should normalize to WS
                "angle_or_lens": "front",
                "motion": "Push In",  # should normalize to push-in
                "scene": "temp: Main Hall",
                "mood": "[visual: dark tones, cool color] tense",  # has hint prefix
                "location": "interior",
                "characters": "temp: Girl-A",
                "event": "Test event",
                "important_dialogue": "[OCR detected: GAME OVER] overlay",  # has hint
                "music_note": "", "director_note": "",
                "confidence": "high",
                "needs_confirmation": "",  # missing for temp markers!
            }],
        }
        source_path = Path(tmpdir) / "draft_fill.json"
        original = json.dumps(source, ensure_ascii=False, indent=2)
        source_path.write_text(original, encoding="utf-8")

        report_path = Path(tmpdir) / "report.json"
        args = argparse.Namespace(
            source_json=str(source_path),
            fix=False,
            output=None,
            report_out=str(report_path),
        )
        result = cc.cmd_normalize_fill(args)
        assert result == 0

        # Source should NOT be modified
        assert source_path.read_text(encoding="utf-8") == original, "lint mode should not modify file"

        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["mode"] == "lint"
        # Should have fixable issues for shot_size, motion, and hint prefixes
        fixable = [i for i in report["issues"] if i.get("severity") == "fixable"]
        assert len(fixable) >= 3, f"Expected at least 3 fixable issues, got {len(fixable)}"
        # Should have warnings for orphaned temp markers
        warnings = [i for i in report["issues"] if i.get("type") == "orphaned_temp_marker"]
        assert len(warnings) >= 1, f"Expected orphaned_temp_marker warnings, got {len(warnings)}"


def test_normalize_fill_fix_mode():
    """normalize-fill --fix should auto-normalize enums and strip hints."""
    import argparse

    with tempfile.TemporaryDirectory() as tmpdir:
        source = {
            "template": "production",
            "fill_status": "complete",
            "rows": [{
                "shot_block": "A1", "start_time": "00:00:00.000",
                "end_time": "00:00:05.000", "keyframe": "",
                "shot_size": "Close-Up",
                "angle_or_lens": "front",
                "motion": "hand held",
                "scene": "test",
                "mood": "[visual: mid tones] calm and steady",
                "location": "studio",
                "characters": "Actor",
                "event": "Test event",
                "important_dialogue": "",
                "music_note": "", "director_note": "",
                "confidence": "high",
                "needs_confirmation": "",
            }],
        }
        source_path = Path(tmpdir) / "draft_fill.json"
        source_path.write_text(json.dumps(source), encoding="utf-8")

        out_path = Path(tmpdir) / "fixed.json"
        args = argparse.Namespace(
            source_json=str(source_path),
            fix=True,
            output=str(out_path),
            report_out=None,
        )
        result = cc.cmd_normalize_fill(args)
        assert result == 0

        fixed = json.loads(out_path.read_text(encoding="utf-8"))
        row = fixed["rows"][0]
        assert row["shot_size"] == "CU", f"shot_size should be CU, got '{row['shot_size']}'"
        assert row["motion"] == "handheld", f"motion should be handheld, got '{row['motion']}'"
        assert "[visual:" not in row["mood"], f"[visual:] hint should be stripped from mood: '{row['mood']}'"
        assert "calm" in row["mood"], f"mood content should be preserved: '{row['mood']}'"


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
