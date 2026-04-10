"""Quick smoke test for split-blocks and gameplay-music template."""
import sys, json, tempfile, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cuesheet_creator as cc

cc.load_templates()

# 1. Verify gameplay-music template loads
assert "gameplay-music" in cc.TEMPLATE_COLUMNS, "gameplay-music template not loaded"
cols = cc.TEMPLATE_COLUMNS["gameplay-music"]
assert "game_phase" in cols, "game_phase column missing"
assert "ui_text" in cols, "ui_text column missing"
assert "music_layer" in cols, "music_layer column missing"
print("OK: gameplay-music template loaded with", len(cols), "columns")

# 2. Test split-blocks with a gameplay scenario
draft_fill = {
    "template": "gameplay-music",
    "video_title": "test_gameplay",
    "source_path": "",
    "fill_status": "complete",
    "rows": [
        {
            "shot_block": "A1",
            "start_time": "00:00:00.000",
            "end_time": "00:00:59.000",
            "keyframe": "keyframes/A1.jpg",
            "game_phase": "lobby -> combat",
            "mood": "building tension",
            "event": "Full gameplay sequence with title card at ~30s",
            "ui_text": "",
            "music_note": "transition at 30s when title appears",
            "music_layer": "ambient -> combat loop",
            "rhythm_change": "",
            "instrumentation": "",
            "dynamics": "pp -> ff",
            "important_dialogue": "",
            "confidence": "medium",
            "needs_confirmation": "phase boundary at ~30s",
            "_split_at": [
                {"time": "00:00:30.000", "reason": "UI title trigger: phase transition to battle loop"}
            ],
        },
        {
            "shot_block": "A2",
            "start_time": "00:00:59.000",
            "end_time": "00:01:30.000",
            "keyframe": "keyframes/A2.jpg",
            "game_phase": "result screen",
            "mood": "release",
            "event": "Battle result",
            "ui_text": "Victory",
            "music_note": "victory sting",
            "music_layer": "result loop",
            "rhythm_change": "",
            "instrumentation": "",
            "dynamics": "ff -> mp",
            "important_dialogue": "",
            "confidence": "high",
            "needs_confirmation": "",
        },
    ],
}

with tempfile.TemporaryDirectory() as tmpdir:
    fill_path = Path(tmpdir) / "draft_fill.json"
    cc.write_json(fill_path, draft_fill)

    args = argparse.Namespace(
        source_json=str(fill_path),
        output=str(fill_path),
        output_format="text",
    )
    rc = cc.cmd_split_blocks(args)
    assert rc == 0, f"split-blocks should succeed, got rc={rc}"

    result = cc.read_json(fill_path)
    rows = result["rows"]
    assert len(rows) == 3, f"Expected 3 rows (1 split + 1 untouched), got {len(rows)}"
    assert result["fill_status"] == "partial", f"fill_status should be partial, got {result['fill_status']}"

    # Verify block structure
    print(f"\nAfter split: {len(rows)} rows, fill_status={result['fill_status']}")
    for row in rows:
        phase = row.get("game_phase", "")
        event = row.get("event", "")
        print(f"  {row['shot_block']}: {row['start_time']} - {row['end_time']}  game_phase={repr(phase[:40])}")

    # First sub-block: 0-30s, inherits content
    assert rows[0]["start_time"] == "00:00:00.000"
    assert rows[0]["end_time"] == "00:00:30.000"
    assert rows[0]["game_phase"] == "lobby -> combat", f"First sub-block should inherit content, got {rows[0]['game_phase']}"
    assert rows[0]["mood"] == "building tension"

    # Second sub-block: 30-59s, empty content (needs re-fill)
    assert rows[1]["start_time"] == "00:00:30.000"
    assert rows[1]["end_time"] == "00:00:59.000"
    assert rows[1]["game_phase"] == "", f"Second sub-block should have empty content for re-fill, got {repr(rows[1]['game_phase'])}"
    assert "_split_reason" in rows[1], "Second sub-block should have _split_reason"

    # Third block: untouched A2
    assert rows[2]["start_time"] == "00:00:59.000"
    assert rows[2]["end_time"] == "00:01:30.000"
    assert rows[2]["game_phase"] == "result screen"

    # No _split_at should remain
    for row in rows:
        assert "_split_at" not in row, f"_split_at should be removed from {row['shot_block']}"

print("\nOK: split-blocks works correctly for gameplay scenario")

# 3. Test no-op when no annotations
with tempfile.TemporaryDirectory() as tmpdir:
    no_split = {"template": "production", "rows": [
        {"shot_block": "A1", "start_time": "00:00:00.000", "end_time": "00:00:10.000"},
    ]}
    p = Path(tmpdir) / "no_split.json"
    cc.write_json(p, no_split)
    args = argparse.Namespace(source_json=str(p), output=str(p), output_format="text")
    rc = cc.cmd_split_blocks(args)
    assert rc == 0
    print("OK: no-op when no _split_at annotations")

# 4. Verify gameplay-phase strategy in merge weights
weights = cc._strategy_weight_multipliers("gameplay-phase")
assert weights["visual_similarity"] < 1.0, "Gameplay should downweight visual similarity"
assert weights["asr_continuity"] > 1.0, "Gameplay should upweight ASR/OCR continuity"
print("OK: gameplay-phase merge strategy weights correct")

print("\nAll smoke tests passed.")
