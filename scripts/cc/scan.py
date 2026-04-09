"""Video analysis, keyframe extraction, ASR, OCR, motion estimation."""
from __future__ import annotations

import datetime as dt
import importlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

from cc.constants import DENSITY_PRESETS, TEMPLATE_COLUMNS
from cc.env import resolve_command_path
from cc.utils import (
    format_seconds,
    make_block_id,
    parse_fps,
    run_command,
    safe_float,
    seconds_from_timecode,
    truncate_text,
    write_json,
)

# ---------------------------------------------------------------------------
# Runtime requirements
# ---------------------------------------------------------------------------

def require_runtime_for_scan() -> tuple[Any, Any, Any]:
    ffprobe_path, _ffprobe_source = resolve_command_path("ffprobe")
    ffmpeg_path, _ffmpeg_source = resolve_command_path("ffmpeg")
    missing = []
    if not ffprobe_path:
        missing.append("ffprobe")
    if not ffmpeg_path:
        missing.append("ffmpeg")
    if missing:
        raise RuntimeError("Missing command: " + ", ".join(missing))

    missing_modules = []
    modules: dict[str, Any] = {}
    for import_name in ("cv2", "numpy", "PIL"):
        try:
            modules[import_name] = importlib.import_module(import_name)
        except Exception:
            missing_modules.append(import_name)
    if missing_modules:
        raise RuntimeError("Missing Python module: " + ", ".join(missing_modules))
    return modules["cv2"], modules["numpy"], modules["PIL"]


# ---------------------------------------------------------------------------
# Video probing
# ---------------------------------------------------------------------------

def ffprobe_metadata(video_path: Path) -> dict[str, Any]:
    ffprobe_path, _source = resolve_command_path("ffprobe")
    if not ffprobe_path:
        raise RuntimeError("Missing command: ffprobe")
    command = [
        ffprobe_path, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(video_path),
    ]
    completed = run_command(command)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "ffprobe read failed")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ffprobe output not parseable: {exc}") from exc


def build_video_info(metadata: dict[str, Any]) -> dict[str, Any]:
    streams = metadata.get("streams", [])
    format_info = metadata.get("format", {})
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    fps = parse_fps(video_stream.get("avg_frame_rate")) or parse_fps(video_stream.get("r_frame_rate"))
    duration = safe_float(video_stream.get("duration"))
    if duration is None:
        duration = safe_float(format_info.get("duration"), 0.0) or 0.0

    return {
        "source_path": format_info.get("filename"),
        "format_name": format_info.get("format_name"),
        "duration_seconds": round(duration, 3),
        "duration_timecode": format_seconds(duration),
        "resolution": {"width": width, "height": height},
        "fps": round(fps, 3) if fps else None,
        "video_codec": video_stream.get("codec_name"),
        "audio_tracks": len(audio_streams),
        "audio_codecs": [s.get("codec_name") for s in audio_streams if s.get("codec_name")],
        "bit_rate": safe_float(format_info.get("bit_rate")),
        "size_bytes": safe_float(format_info.get("size")),
    }


# ---------------------------------------------------------------------------
# Frame-level helpers
# ---------------------------------------------------------------------------

def compute_hist_distance(cv2: Any, np: Any, frame_a: Any, frame_b: Any) -> float:
    hist_a = []
    hist_b = []
    for channel in range(3):
        h1 = cv2.calcHist([frame_a], [channel], None, [32], [0, 256])
        h2 = cv2.calcHist([frame_b], [channel], None, [32], [0, 256])
        cv2.normalize(h1, h1)
        cv2.normalize(h2, h2)
        hist_a.append(h1)
        hist_b.append(h2)
    distances = []
    for h1, h2 in zip(hist_a, hist_b):
        corr = cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)
        distances.append(1.0 - max(min(corr, 1.0), -1.0))
    score = float(np.mean(distances))
    return max(score, 0.0)


def resize_frame(cv2: Any, frame: Any, max_width: int) -> Any:
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame
    scale = max_width / float(width)
    new_size = (int(width * scale), int(height * scale))
    return cv2.resize(frame, new_size)


def read_frame_at(cv2: Any, capture: Any, seconds: float) -> Any | None:
    capture.set(cv2.CAP_PROP_POS_MSEC, max(seconds, 0.0) * 1000.0)
    success, frame = capture.read()
    if not success:
        return None
    return frame


# ---------------------------------------------------------------------------
# Scene detection
# ---------------------------------------------------------------------------

def build_draft_blocks(scene_candidates: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    ordered = sorted(scene_candidates, key=lambda item: item["seconds"])
    deduped: list[dict[str, Any]] = []
    last_seconds: float | None = None
    for item in ordered:
        seconds = float(item["seconds"])
        if last_seconds is not None and abs(seconds - last_seconds) < 0.001:
            continue
        deduped.append(item)
        last_seconds = seconds
    if not deduped:
        return []

    blocks = []
    for idx, item in enumerate(deduped, start=1):
        start = float(item["seconds"])
        end = duration if idx == len(deduped) else float(deduped[idx]["seconds"])
        if end < start:
            end = start
        blocks.append({
            "shot_block": make_block_id(idx),
            "start_seconds": round(start, 3),
            "start_time": format_seconds(start),
            "end_seconds": round(end, 3),
            "end_time": format_seconds(end),
            "keyframe": item.get("image_path"),
            "candidate_score": item.get("score"),
            "cut_reason": item.get("reason"),
            "visual_features": item.get("visual_features"),
        })
    return blocks


def detect_scenes_scenedetect(video_path: Path, threshold: float) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Use PySceneDetect ContentDetector if available. Returns (candidates, error_message)."""
    try:
        from scenedetect import SceneManager, open_video
        from scenedetect.detectors import ContentDetector
    except ImportError:
        return None, "scenedetect not installed"

    try:
        video = open_video(str(video_path))
        manager = SceneManager()
        manager.add_detector(ContentDetector(threshold=threshold))
        manager.detect_scenes(video)
        scene_list = manager.get_scene_list()

        candidates: list[dict[str, Any]] = []
        candidates.append({
            "index": 1, "seconds": 0.0,
            "timecode": format_seconds(0.0), "score": 1.0, "reason": "start",
        })

        for idx, (start_tc, _end_tc) in enumerate(scene_list, start=2):
            seconds = start_tc.get_seconds()
            if seconds <= 0.001:
                continue
            candidates.append({
                "index": idx, "seconds": round(seconds, 3),
                "timecode": format_seconds(seconds), "score": 1.0,
                "reason": f"scenedetect_content>={threshold}",
            })

        return candidates, None
    except Exception as exc:
        return None, f"SceneDetect runtime error: {exc}"


# ---------------------------------------------------------------------------
# Audio / ASR
# ---------------------------------------------------------------------------

def extract_audio_track(video_path: Path, out_dir: Path, start: float | None = None, end: float | None = None) -> tuple[Path | None, str | None]:
    """Extract first audio track to WAV using ffmpeg."""
    ffmpeg_path, _source = resolve_command_path("ffmpeg")
    if not ffmpeg_path:
        return None, "Missing command: ffmpeg"
    audio_path = out_dir / "audio.wav"
    cmd = [ffmpeg_path, "-y"]
    if start is not None and start > 0.001:
        cmd.extend(["-ss", format_seconds(start)])
    cmd.extend(["-i", str(video_path)])
    if end is not None:
        duration = end - (start or 0.0)
        if duration > 0:
            cmd.extend(["-t", f"{duration:.3f}"])
    cmd.extend(["-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(audio_path)])
    result = run_command(cmd)
    if result.returncode != 0:
        stderr_summary = truncate_text(result.stderr, limit=500)
        return None, f"ffmpeg audio extraction failed (rc={result.returncode}): {stderr_summary}"
    if not audio_path.exists():
        return None, "ffmpeg completed but audio.wav was not created"
    return audio_path, None


def run_asr_faster_whisper(
    audio_path: Path,
    model_size: str = "base",
    device: str = "auto",
    compute_type: str = "auto",
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Run faster-whisper ASR."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None, "faster-whisper not installed"

    try:
        # Resolve "auto" device: prefer CUDA if available, fallback to CPU
        if device == "auto":
            try:
                import torch
                resolved_device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                resolved_device = "cpu"
        else:
            resolved_device = device

        # Resolve "auto" compute_type based on device
        if compute_type == "auto":
            resolved_compute = "float16" if resolved_device == "cuda" else "int8"
        else:
            resolved_compute = compute_type

        model = WhisperModel(model_size, device=resolved_device, compute_type=resolved_compute)
        segments_iter, _info = model.transcribe(str(audio_path), beam_size=5)
        results: list[dict[str, Any]] = []
        for segment in segments_iter:
            results.append({
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "start_time": format_seconds(segment.start),
                "end_time": format_seconds(segment.end),
                "text": segment.text.strip(),
            })
        return results, None
    except Exception as exc:
        return None, f"ASR runtime error: {exc}"


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def run_ocr_on_frames(frame_paths: list[str]) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Run OCR on selected keyframes. Tries rapidocr > easyocr > paddleocr."""
    ocr_engine = None
    engine_name = None
    init_notes: list[str] = []

    try:
        from rapidocr_onnxruntime import RapidOCR
        ocr_engine = RapidOCR()
        engine_name = "rapidocr"
    except Exception as exc:
        init_notes.append(f"rapidocr init failed: {exc}")

    if ocr_engine is None:
        try:
            import easyocr
            reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
            ocr_engine = reader
            engine_name = "easyocr"
        except Exception as exc:
            init_notes.append(f"easyocr init failed: {exc}")

    if ocr_engine is None:
        try:
            from paddleocr import PaddleOCR
            ocr_engine = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
            engine_name = "paddleocr"
        except Exception as exc:
            init_notes.append(f"paddleocr init failed: {exc}")

    if ocr_engine is None:
        detail = "; ".join(init_notes) if init_notes else "no engines installed"
        return None, f"No OCR engine available ({detail})"

    results: list[dict[str, Any]] = []
    frame_errors: list[str] = []
    for frame_path in frame_paths:
        texts: list[str] = []
        try:
            if engine_name == "rapidocr":
                result, _elapse = ocr_engine(frame_path)
                if result:
                    texts = [item[1] for item in result if item[1]]
            elif engine_name == "easyocr":
                raw = ocr_engine.readtext(frame_path)
                texts = [item[1] for item in raw if item[1]]
            elif engine_name == "paddleocr":
                result = ocr_engine.ocr(frame_path, cls=True)
                if result and result[0]:
                    texts = [line[1][0] for line in result[0] if line[1] and line[1][0]]
        except Exception as exc:
            frame_errors.append(f"{Path(frame_path).name}: {exc}")
            continue

        if texts:
            results.append({"frame": frame_path, "texts": texts, "engine": engine_name})
    if frame_errors:
        error_summary = f"OCR failed on {len(frame_errors)} frame(s): {'; '.join(frame_errors[:5])}"
        if len(frame_errors) > 5:
            error_summary += f" ... and {len(frame_errors) - 5} more"
        return (results, error_summary)
    return (results, None) if results else ([], None)


# ---------------------------------------------------------------------------
# Visual analysis
# ---------------------------------------------------------------------------

def compute_frame_sharpness(cv2: Any, frame: Any) -> float:
    """Compute Laplacian variance as a sharpness score."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def compute_visual_features(cv2: Any, np: Any, frame: Any) -> dict[str, Any]:
    """Compute objective visual features from a single frame."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))
    saturation = float(np.mean(hsv[:, :, 1]))
    # Dominant hue: use histogram mode instead of mean to handle bimodal distributions
    # (e.g., a red+blue scene would average to green with np.mean, but the mode finds
    # the actual most frequent hue correctly)
    hue_hist = cv2.calcHist([hsv], [0], None, [180], [0, 180])
    dominant_hue = float(np.argmax(hue_hist))
    if brightness < 80:
        tone = "dark"
    elif brightness > 170:
        tone = "bright"
    else:
        tone = "mid"
    if 10 < dominant_hue < 30:
        color_temp = "warm"
    elif 90 < dominant_hue < 130:
        color_temp = "cool"
    else:
        color_temp = "neutral"
    return {
        "brightness": round(brightness, 1), "contrast": round(contrast, 1),
        "saturation": round(saturation, 1), "dominant_hue": round(dominant_hue, 1),
        "tone": tone, "color_temp": color_temp,
    }


def estimate_motion_hint(
    cv2: Any, np: Any, capture: Any,
    block_start: float, block_end: float,
    num_samples: int = 4,
    static_threshold: float = 2.0,
) -> dict[str, Any]:
    """Estimate camera motion for a block using phase correlation."""
    duration = block_end - block_start
    if duration < 0.2 or num_samples < 2:
        return {"motion_hint": "uncertain", "motion_confidence": 0.0,
                "avg_displacement": 0.0, "max_displacement": 0.0}

    step = duration / (num_samples - 1) if num_samples > 1 else duration
    times = [block_start + i * step for i in range(num_samples)]

    frames_gray: list[Any] = []
    for t in times:
        capture.set(cv2.CAP_PROP_POS_MSEC, max(t, 0.0) * 1000.0)
        ok, frame = capture.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        if w > 320:
            scale = 320.0 / w
            gray = cv2.resize(gray, (320, int(h * scale)))
        frames_gray.append(np.float32(gray))

    if len(frames_gray) < 2:
        return {"motion_hint": "uncertain", "motion_confidence": 0.0,
                "avg_displacement": 0.0, "max_displacement": 0.0}

    displacements: list[float] = []
    for i in range(len(frames_gray) - 1):
        (dx, dy), _response = cv2.phaseCorrelate(frames_gray[i], frames_gray[i + 1])
        disp = math.sqrt(dx * dx + dy * dy)
        displacements.append(disp)

    avg_disp = sum(displacements) / len(displacements) if displacements else 0.0
    max_disp = max(displacements) if displacements else 0.0

    if avg_disp < static_threshold and max_disp < static_threshold * 2:
        hint = "likely-static"
        confidence = min(1.0, (static_threshold - avg_disp) / static_threshold)
    elif avg_disp > static_threshold * 3:
        hint = "likely-camera-move"
        confidence = min(1.0, avg_disp / (static_threshold * 6))
    else:
        hint = "uncertain"
        confidence = 0.3

    return {
        "motion_hint": hint, "motion_confidence": round(confidence, 2),
        "avg_displacement": round(avg_disp, 2), "max_displacement": round(max_disp, 2),
    }




# ---------------------------------------------------------------------------
# Best-frame selection (local CV sharpness refinement)
# ---------------------------------------------------------------------------

def refine_keyframe_selection(
    cv2: Any,
    np: Any,
    draft_blocks: list[dict[str, Any]],
    video_path: Path,
    out_dir: Path,
    max_candidates: int = 7,
    max_width: int = 1280,
) -> int:
    """For each block, sample multiple frames within its time range and pick
    the sharpest one as the keyframe — replacing motion-blurred or poorly
    timed frames with the clearest available frame.

    This is a pure-CV refinement pass. It re-opens the video, samples
    *max_candidates* evenly spaced frames within each block's
    [start_seconds, end_seconds] range, computes Laplacian sharpness on
    each, and keeps the winner. The old keyframe image is NOT deleted
    (contact sheets may still reference it); the block's ``keyframe``
    field is updated to point to the new best image.

    Returns the number of blocks whose keyframe was upgraded.
    """
    if not draft_blocks:
        return 0

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return 0

    keyframe_dir = out_dir / "keyframes"
    keyframe_dir.mkdir(parents=True, exist_ok=True)
    upgraded = 0

    try:
        for block in draft_blocks:
            start = block.get("start_seconds", 0.0)
            end = block.get("end_seconds", start)
            span = end - start

            # Skip very short blocks — the current frame is likely fine
            if span < 0.1:
                continue

            # Sample candidate timestamps evenly within the block
            n = min(max_candidates, max(3, int(span / 0.15)))  # ~1 sample per 150ms, min 3
            step = span / n if n > 1 else span
            timestamps = [start + i * step for i in range(n)]
            # Ensure we also sample close to the original keyframe time
            # (the cut point is often important even if blurry)

            best_score = -1.0
            best_frame = None
            best_seconds = start
            current_sharpness = block.get("visual_features", {}).get("sharpness", 0.0) if block.get("visual_features") else 0.0
            mid_time = (start + end) / 2.0

            for ts in timestamps:
                frame = read_frame_at(cv2, capture, ts)
                if frame is None:
                    continue
                frame = resize_frame(cv2, frame, max_width=max_width)
                sharpness = compute_frame_sharpness(cv2, frame)
                # Mid-block representativeness bias: frames closer to block center
                # get up to 10% bonus. This favors "representative" frames over
                # edge frames that may be transitional.
                distance_from_mid = abs(ts - mid_time) / max(span / 2.0, 0.01)
                mid_bonus = 1.0 + 0.10 * (1.0 - min(distance_from_mid, 1.0))
                score = sharpness * mid_bonus
                if score > best_score:
                    best_score = score
                    best_frame = frame
                    best_seconds = ts

            # Only upgrade if the new frame is meaningfully sharper (>15% better raw sharpness)
            best_raw_sharpness = compute_frame_sharpness(cv2, best_frame) if best_frame is not None else 0.0
            if best_frame is not None and best_raw_sharpness > current_sharpness * 1.15:
                image_name = f"frame_best_{block['shot_block']}_{int(best_seconds * 1000):010d}.jpg"
                image_path = keyframe_dir / image_name
                ok = cv2.imwrite(str(image_path), best_frame)
                if ok:
                    rel_path = os.path.relpath(str(image_path), str(out_dir)).replace("\\", "/")
                    block["keyframe"] = rel_path
                    # Update visual features with the new frame
                    block["visual_features"] = compute_visual_features(cv2, np, best_frame)
                    block["visual_features"]["sharpness"] = round(best_raw_sharpness, 2)
                    block["_keyframe_refined"] = True
                    block["_refinement_gain"] = round(best_raw_sharpness / max(current_sharpness, 0.01), 2)
                    upgraded += 1
    finally:
        capture.release()

    return upgraded


# ---------------------------------------------------------------------------
# Similar-frame deduplication (local CV, no LLM)
# ---------------------------------------------------------------------------

def deduplicate_similar_blocks(
    cv2: Any,
    np: Any,
    draft_blocks: list[dict[str, Any]],
    out_dir: Path,
    similarity_threshold: float = 0.08,
) -> tuple[list[dict[str, Any]], int]:
    """Merge consecutive blocks whose keyframes are nearly identical.

    Compares each block's keyframe to the next using histogram distance.
    If the distance is below *similarity_threshold*, the blocks are merged
    (the later block's time range is absorbed into the earlier one, and the
    sharpest keyframe is kept).

    This is a pure-CV operation — no LLM needed.  It dramatically reduces
    block count in dense/frame-accurate scans where many consecutive frames
    look the same (e.g. a static hold, a slow pan).

    Returns (deduplicated_blocks, merge_count).
    """
    if len(draft_blocks) < 2:
        return draft_blocks, 0

    # Load keyframe images for comparison
    frames: dict[str, Any] = {}  # block_id -> cv2 image
    for block in draft_blocks:
        kf = block.get("keyframe", "")
        if not kf:
            continue
        kf_path = Path(kf) if Path(kf).is_absolute() else out_dir / kf
        if kf_path.exists():
            img = cv2.imread(str(kf_path))
            if img is not None:
                # Resize to small for fast comparison
                h, w = img.shape[:2]
                if w > 320:
                    scale = 320.0 / w
                    img = cv2.resize(img, (320, int(h * scale)))
                frames[block["shot_block"]] = img

    if len(frames) < 2:
        return draft_blocks, 0

    merged: list[dict[str, Any]] = []
    current = draft_blocks[0]
    merge_count = 0

    for i in range(1, len(draft_blocks)):
        next_block = draft_blocks[i]
        curr_id = current["shot_block"]
        next_id = next_block["shot_block"]

        # If either block has no loaded frame, keep them separate
        if curr_id not in frames or next_id not in frames:
            merged.append(current)
            current = next_block
            continue

        dist = compute_hist_distance(cv2, np, frames[curr_id], frames[next_id])

        if dist < similarity_threshold:
            # Merge: extend current block's time range, keep sharpest keyframe
            current["end_seconds"] = next_block["end_seconds"]
            current["end_time"] = next_block["end_time"]
            # Keep the keyframe with better sharpness (if available)
            curr_sharp = current.get("visual_features", {}).get("sharpness", 0) if current.get("visual_features") else 0
            next_sharp = next_block.get("visual_features", {}).get("sharpness", 0) if next_block.get("visual_features") else 0
            if next_sharp > curr_sharp:
                current["keyframe"] = next_block.get("keyframe")
                current["visual_features"] = next_block.get("visual_features")
            # Merge motion hints: if either says camera-move, keep that
            curr_motion = current.get("motion_hint", {}).get("motion_hint", "uncertain")
            next_motion = next_block.get("motion_hint", {}).get("motion_hint", "uncertain")
            if next_motion == "likely-camera-move" and curr_motion != "likely-camera-move":
                current["motion_hint"] = next_block.get("motion_hint")
            merge_count += 1
        else:
            merged.append(current)
            current = next_block

    merged.append(current)

    # Renumber blocks
    for idx, block in enumerate(merged, start=1):
        block["shot_block"] = make_block_id(idx)

    return merged, merge_count


# ---------------------------------------------------------------------------
# Contact sheet generation (batch keyframe grids)
# ---------------------------------------------------------------------------

def build_contact_sheets(
    cv2: Any,
    np: Any,
    draft_blocks: list[dict[str, Any]],
    out_dir: Path,
    batch_size: int = 6,
    grid_cols: int = 3,
    thumb_width: int = 420,
    label_height: int = 28,
) -> list[dict[str, Any]]:
    """Build contact sheet images — one per keyframe batch.

    Each contact sheet is a grid of keyframe thumbnails with block ID labels,
    so an LLM agent can view one image to see an entire batch of keyframes.
    This reduces the tool calls from N (one per keyframe) to N/batch_size.

    Returns a list of dicts: [{"batch_index": 1, "block_ids": [...],
    "image_path": "keyframes/contact_batch_1.jpg", "keyframe_count": 6}, ...]
    """
    # Collect blocks that have keyframe paths
    blocks_with_kf = []
    for block in draft_blocks:
        kf = block.get("keyframe")
        if kf:
            blocks_with_kf.append(block)

    if not blocks_with_kf:
        return []

    # Split into batches
    batches: list[list[dict[str, Any]]] = []
    for i in range(0, len(blocks_with_kf), batch_size):
        batches.append(blocks_with_kf[i:i + batch_size])

    contact_dir = out_dir / "keyframes"
    contact_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []

    for batch_idx, batch in enumerate(batches, start=1):
        thumbnails: list[tuple[str, Any]] = []  # (block_id, resized_frame)

        for block in batch:
            kf_path_str = block.get("keyframe", "")
            # Resolve: relative paths are relative to out_dir
            kf_path = Path(kf_path_str)
            if not kf_path.is_absolute():
                kf_path = out_dir / kf_path
            if not kf_path.exists():
                continue

            frame = cv2.imread(str(kf_path))
            if frame is None:
                continue

            # Resize to thumbnail width, preserving aspect ratio
            h, w = frame.shape[:2]
            scale = thumb_width / float(w) if w > thumb_width else 1.0
            new_w = int(w * scale)
            new_h = int(h * scale)
            if scale < 1.0:
                frame = cv2.resize(frame, (new_w, new_h))
            else:
                new_w, new_h = w, h

            thumbnails.append((block.get("shot_block", "?"), frame, new_w, new_h))

        if not thumbnails:
            continue

        # Compute uniform cell size (max dimensions across all thumbs in this batch)
        cell_w = max(t[2] for t in thumbnails)
        cell_h = max(t[3] for t in thumbnails) + label_height

        grid_rows = math.ceil(len(thumbnails) / grid_cols)
        canvas_w = cell_w * min(len(thumbnails), grid_cols)
        canvas_h = cell_h * grid_rows

        # Create canvas (white background)
        canvas = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)

        block_ids: list[str] = []
        for idx, (block_id, thumb, tw, th) in enumerate(thumbnails):
            row = idx // grid_cols
            col = idx % grid_cols
            x_offset = col * cell_w
            y_offset = row * cell_h

            # Center the thumbnail in the cell horizontally
            x_start = x_offset + (cell_w - tw) // 2
            y_start = y_offset + label_height  # leave room for label

            # Place thumbnail
            canvas[y_start:y_start + th, x_start:x_start + tw] = thumb[:th, :tw]

            # Draw label background (dark bar)
            cv2.rectangle(canvas, (x_offset, y_offset),
                          (x_offset + cell_w, y_offset + label_height), (30, 30, 30), -1)

            # Draw block ID text
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.7
            thickness = 2
            text = f"{block_id}"
            text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
            text_x = x_offset + (cell_w - text_size[0]) // 2
            text_y = y_offset + label_height - 6
            cv2.putText(canvas, text, (text_x, text_y), font, font_scale, (255, 255, 255), thickness)

            # Draw block time range below ID
            block_data = next((b for b in draft_blocks if b.get("shot_block") == block_id), None)
            if block_data:
                time_text = f"{block_data.get('start_time', '')} - {block_data.get('end_time', '')}"
                time_scale = 0.4
                time_size = cv2.getTextSize(time_text, font, time_scale, 1)[0]
                time_x = x_offset + (cell_w - time_size[0]) // 2
                time_y = y_offset + label_height - 6 + text_size[1] + 2
                # Only draw if it fits within the label area — otherwise skip
                if time_y < y_offset + label_height + th:
                    cv2.putText(canvas, time_text, (time_x, min(time_y, y_start - 2)),
                                font, time_scale, (200, 200, 200), 1)

            block_ids.append(block_id)

        # Save contact sheet
        contact_path = contact_dir / f"contact_batch_{batch_idx}.jpg"
        cv2.imwrite(str(contact_path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 90])

        rel_path = os.path.relpath(str(contact_path), str(out_dir)).replace("\\", "/")
        results.append({
            "batch_index": batch_idx,
            "block_ids": block_ids,
            "image_path": rel_path,
            "keyframe_count": len(thumbnails),
        })

    return results


# ---------------------------------------------------------------------------
# Main scan command
# ---------------------------------------------------------------------------

def cmd_scan_video(args: "argparse.Namespace") -> int:  # noqa: F821, C901
    cv2, np, _pil = require_runtime_for_scan()

    video_path = Path(args.video)
    if not video_path.exists() or not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        out_dir = video_path.parent / f"{video_path.stem}_cuesheet"

    keyframe_dir = out_dir / "keyframes"
    keyframe_dir.mkdir(parents=True, exist_ok=True)

    probe = ffprobe_metadata(video_path)
    video_info = build_video_info(probe)

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError("OpenCV cannot open video")

    fps = video_info.get("fps") or capture.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = video_info.get("duration_seconds") or 0.0
    if (not duration or duration <= 0) and fps and frame_count:
        duration = frame_count / float(fps)
        video_info["duration_seconds"] = round(duration, 3)
        video_info["duration_timecode"] = format_seconds(duration)
    video_info["frame_count"] = frame_count

    if duration <= 0:
        raise RuntimeError("Cannot determine video duration")

    effective_start = 0.0
    effective_end = duration
    if args.start_time:
        effective_start = seconds_from_timecode(args.start_time)
    if args.end_time:
        effective_end = seconds_from_timecode(args.end_time)
    effective_start = max(0.0, min(effective_start, duration))
    effective_end = max(effective_start, min(effective_end, duration))
    effective_duration = effective_end - effective_start
    if effective_duration <= 0:
        raise RuntimeError(f"Effective clip range is zero: {format_seconds(effective_start)} - {format_seconds(effective_end)}")

    sample_interval = max(float(args.sample_interval), 0.2)
    dedup_threshold = 0.08  # default
    density_name = getattr(args, "density", None)
    if density_name and density_name in DENSITY_PRESETS:
        preset = DENSITY_PRESETS[density_name]
        sample_interval = preset["sample_interval"]
        dedup_threshold = preset["dedup_threshold"]
    max_samples = int(args.max_samples) if args.max_samples else None

    sampled_frames: list[dict[str, Any]] = []
    scene_candidates: list[dict[str, Any]] = []
    notes: list[str] = []
    detection_method = "histogram"

    if density_name and density_name in DENSITY_PRESETS:
        notes.append(f"Density preset: {density_name} (sample_interval={sample_interval}s, dedup_threshold={dedup_threshold})")

    sd_threshold = float(args.scene_threshold)
    sd_content_threshold = float(args.content_threshold) if hasattr(args, "content_threshold") and args.content_threshold else 27.0

    # Clip-range optimization: pre-trim video for scenedetect to avoid scanning full file
    is_clip = effective_start > 0.001 or effective_end < duration - 0.001
    clip_video_path = video_path
    clip_offset = 0.0
    _clip_temp_path: Path | None = None
    if is_clip:
        ffmpeg_path_for_trim, _ = resolve_command_path("ffmpeg")
        if ffmpeg_path_for_trim:
            _clip_temp_path = out_dir / "_clip_temp.mp4"
            clip_cmd = [
                ffmpeg_path_for_trim, "-y",
                "-ss", format_seconds(effective_start),
                "-i", str(video_path),
                "-t", f"{effective_duration:.3f}",
                "-c", "copy",
                str(_clip_temp_path),
            ]
            trim_result = run_command(clip_cmd)
            if trim_result.returncode == 0 and _clip_temp_path.exists():
                clip_video_path = _clip_temp_path
                clip_offset = effective_start
                notes.append(
                    f"Pre-trimmed clip ({format_seconds(effective_start)} - {format_seconds(effective_end)}) "
                    f"for faster scene detection"
                )
            else:
                _clip_temp_path = None  # fallback to full-file scan

    sd_candidates, sd_err = detect_scenes_scenedetect(clip_video_path, sd_content_threshold)
    if sd_candidates is not None:
        detection_method = "scenedetect"
        if is_clip and clip_offset > 0:
            # Shift scenedetect timestamps back to original video time
            for c in sd_candidates:
                c["seconds"] = round(c["seconds"] + clip_offset, 3)
                c["timecode"] = format_seconds(c["seconds"])
        if is_clip and _clip_temp_path is None:
            notes.append(
                "NOTE: PySceneDetect scanned the full video file (pre-trim failed or ffmpeg unavailable). "
                "Scene candidates are filtered to the clip range afterward."
            )
        filtered = [
            c for c in sd_candidates
            if c["seconds"] >= effective_start - 0.05 and c["seconds"] <= effective_end + 0.05
        ]
        if not filtered or filtered[0]["seconds"] > effective_start + 0.1:
            filtered.insert(0, {
                "index": 1, "seconds": round(effective_start, 3),
                "timecode": format_seconds(effective_start), "score": 1.0, "reason": "start",
            })
        for i, c in enumerate(filtered, start=1):
            c["index"] = i
        scene_candidates = filtered
        notes.append(f"Using PySceneDetect ContentDetector (threshold={sd_content_threshold})")
    else:
        notes.append(f"PySceneDetect unavailable ({sd_err}), falling back to histogram-based cut detection")
        notes.append("TIP: For better scene detection (especially dissolves/fades), install scenedetect: python scripts/cuesheet_creator.py prepare-env --mode install-scene --out-dir <out-dir>")

    prev_frame = None
    times: list[float] = []
    current = effective_start
    while current < effective_end:
        times.append(round(current, 3))
        current += sample_interval
    if not times or abs(times[-1] - effective_end) > 0.05:
        times.append(round(max(effective_end - 0.001, 0.0), 3))

    if max_samples and len(times) > max_samples:
        stride = math.ceil(len(times) / max_samples)
        times = times[::stride]
        if times[-1] < effective_end - 0.05:
            times.append(round(max(effective_end - 0.001, 0.0), 3))
        notes.append(f"Too many sample points, downsampled with stride={stride}")

    try:
        for idx, seconds in enumerate(times, start=1):
            frame = read_frame_at(cv2, capture, seconds)
            if frame is None:
                # End-of-video frame extraction failures are normal (edge decode boundary).
                # Only warn for mid-video failures that indicate real problems.
                is_last_sample = (idx == len(times))
                is_near_end = abs(seconds - effective_end) < sample_interval
                if not (is_last_sample or is_near_end):
                    notes.append(f"{format_seconds(seconds)} frame extraction failed, skipped")
                continue
            frame = resize_frame(cv2, frame, max_width=args.max_width)
            image_name = f"frame_{idx:04d}_{int(seconds * 1000):010d}.jpg"
            image_path = keyframe_dir / image_name
            ok = cv2.imwrite(str(image_path), frame)
            if not ok:
                raise RuntimeError(f"Failed to write keyframe: {image_path}")

            sharpness = round(compute_frame_sharpness(cv2, frame), 2)
            visual_features = compute_visual_features(cv2, np, frame)
            score = 1.0 if prev_frame is None else round(compute_hist_distance(cv2, np, prev_frame, frame), 4)
            frame_record = {
                "index": idx, "seconds": round(seconds, 3),
                "timecode": format_seconds(seconds),
                "image_path": os.path.relpath(str(image_path), str(out_dir)).replace("\\", "/"),
                "score_from_previous": score, "sharpness": sharpness,
                "visual_features": visual_features,
            }
            sampled_frames.append(frame_record)

            if detection_method == "histogram":
                if prev_frame is None or score >= sd_threshold:
                    reason = "start" if prev_frame is None else f"hist_diff>={sd_threshold}"
                    scene_candidates.append({
                        "index": len(scene_candidates) + 1,
                        "seconds": round(seconds, 3),
                        "timecode": format_seconds(seconds),
                        "image_path": os.path.relpath(str(image_path), str(out_dir)).replace("\\", "/"),
                        "score": score, "reason": reason,
                        "visual_features": visual_features,
                    })
            prev_frame = frame
    finally:
        pass  # Keep capture open for motion estimation below

    if detection_method == "scenedetect":
        for candidate in scene_candidates:
            cs = candidate["seconds"]
            best_frame = None
            best_sharpness = -1.0
            for sf in sampled_frames:
                if sf["seconds"] >= cs and sf["seconds"] < cs + sample_interval * 3:
                    if sf["sharpness"] > best_sharpness:
                        best_sharpness = sf["sharpness"]
                        best_frame = sf
            if best_frame is None and sampled_frames:
                closest = min(sampled_frames, key=lambda sf: abs(sf["seconds"] - cs))
                best_frame = closest
                notes.append(
                    f"Keyframe fallback for candidate at {format_seconds(cs)}: "
                    f"no frame in primary window, using closest frame at "
                    f"{format_seconds(closest['seconds'])} "
                    f"(distance={abs(closest['seconds'] - cs):.3f}s)"
                )
            if best_frame:
                candidate["image_path"] = best_frame["image_path"]
                candidate["sharpness"] = best_frame.get("sharpness", 0.0)
                candidate["visual_features"] = best_frame.get("visual_features")

    if len(scene_candidates) <= 1:
        notes.append("Very few scene candidates detected; consider manual merging or denser sampling in draft phase")

    draft_blocks = build_draft_blocks(scene_candidates, float(effective_end))

    if not draft_blocks:
        notes.append("ERROR: No draft blocks generated. Scene detection may have failed or video is too short.")
        print("ERROR: No draft blocks could be generated from this video. "
              "Check scene detection settings or try a different --sample-interval.", file=sys.stderr)

    # Reuse main capture for motion estimation (avoid re-opening video file)
    if draft_blocks:
        if capture.isOpened():
            for block in draft_blocks:
                hint = estimate_motion_hint(
                    cv2, np, capture,
                    block["start_seconds"], block["end_seconds"],
                )
                block["motion_hint"] = hint

    # Release the main capture now — no longer needed
    capture.release()

    # --- Refine keyframe selection (pick sharpest frame per block) ---
    if draft_blocks:
        refined_count = refine_keyframe_selection(
            cv2, np, draft_blocks, video_path, out_dir,
            max_candidates=7, max_width=args.max_width,
        )
        if refined_count > 0:
            notes.append(f"Refined keyframes for {refined_count}/{len(draft_blocks)} block(s) — replaced with sharper frames")

    # --- Deduplicate visually similar consecutive blocks ---
    skip_dedup = getattr(args, "no_dedup", False)
    if skip_dedup:
        notes.append("Visual deduplication disabled (--no-dedup)")
    elif draft_blocks and len(draft_blocks) > 1:
        original_count = len(draft_blocks)
        draft_blocks, dedup_merges = deduplicate_similar_blocks(
            cv2, np, draft_blocks, out_dir,
            similarity_threshold=dedup_threshold,
        )
        if dedup_merges > 0:
            notes.append(
                f"Deduplicated {dedup_merges} visually similar consecutive block(s): "
                f"{original_count} → {len(draft_blocks)} blocks"
            )

    # --- ASR ---
    asr_result: dict[str, Any] = {"status": "not-run", "segments": []}
    if args.asr:
        notes.append("Attempting ASR speech recognition...")
        audio_path, audio_err = extract_audio_track(video_path, out_dir, start=effective_start, end=effective_end)
        if audio_path:
            asr_model = args.asr_model if hasattr(args, "asr_model") and args.asr_model else "base"
            asr_device = args.asr_device if hasattr(args, "asr_device") and args.asr_device else "auto"
            asr_compute = args.asr_compute_type if hasattr(args, "asr_compute_type") and args.asr_compute_type else "auto"
            segments, asr_err = run_asr_faster_whisper(
                audio_path, model_size=asr_model, device=asr_device, compute_type=asr_compute,
            )
            if segments is not None:
                if effective_start > 0.001:
                    for seg in segments:
                        seg["start"] = round(seg["start"] + effective_start, 3)
                        seg["end"] = round(seg["end"] + effective_start, 3)
                        seg["start_time"] = format_seconds(seg["start"])
                        seg["end_time"] = format_seconds(seg["end"])
                asr_result = {"status": "ok", "model": asr_model, "segments": segments}
                notes.append(f"ASR complete, recognized {len(segments)} speech segments (model={asr_model})")
            elif asr_err and "not installed" in asr_err:
                asr_result = {"status": "unavailable", "segments": [], "error": asr_err}
                notes.append(f"faster-whisper unavailable, ASR skipped: {asr_err}")
            else:
                asr_result = {"status": "runtime-failed", "segments": [], "error": asr_err or "unknown"}
                notes.append(f"ASR runtime failed (continuing without speech data): {asr_err}")
        else:
            asr_result = {"status": "no-audio", "segments": [], "error": audio_err or "unknown"}
            notes.append(f"Cannot extract audio track, ASR skipped: {audio_err}")

    # --- OCR (runs on final draft_block keyframes, post-refinement/dedup) ---
    ocr_result: dict[str, Any] = {"status": "not-run", "detections": []}
    if args.ocr:
        notes.append("Attempting OCR text recognition...")
        ocr_frame_paths = []
        for block in draft_blocks:
            ip = block.get("keyframe")
            if ip:
                abs_ip = (out_dir / ip).resolve()
                if abs_ip.exists():
                    ocr_frame_paths.append(str(abs_ip))
        if ocr_frame_paths:
            detections, ocr_err = run_ocr_on_frames(ocr_frame_paths)
            if ocr_err is not None:
                if "No OCR engine" in ocr_err:
                    ocr_result = {"status": "unavailable", "detections": [], "error": ocr_err}
                    notes.append(f"OCR engine unavailable, skipped: {ocr_err}")
                elif detections:
                    ocr_result = {"status": "partial-ok", "detections": detections, "error": ocr_err}
                    notes.append(f"OCR partial: text detected in {len(detections)} frame(s), but {ocr_err}")
                else:
                    ocr_result = {"status": "runtime-failed", "detections": [], "error": ocr_err}
                    notes.append(f"OCR runtime failed (continuing without text data): {ocr_err}")
            elif detections is not None and len(detections) > 0:
                ocr_result = {"status": "ok", "detections": detections}
                notes.append(f"OCR complete, text detected in {len(detections)} frames")
            else:
                ocr_result = {"status": "ok-no-text", "detections": []}
                notes.append("OCR completed successfully but no on-screen text was detected")
        else:
            ocr_result = {"status": "no-frames", "detections": []}
            notes.append("No keyframes available for OCR")

    # --- agent_summary ---
    KEYFRAME_BATCH_SIZE = 6
    block_overview: list[dict[str, Any]] = []
    all_keyframe_paths: list[str] = []
    for block in draft_blocks:
        kf = block.get("keyframe")
        kf_rel = ""
        if kf:
            kf_rel = kf.replace("\\", "/") if isinstance(kf, str) else ""
            all_keyframe_paths.append(kf_rel)
        block_overview.append({
            "id": block["shot_block"], "start": block["start_time"],
            "end": block["end_time"], "keyframe": kf_rel,
            "cut_reason": block.get("cut_reason", ""),
            "visual_features": block.get("visual_features"),
            "motion_hint": block.get("motion_hint"),
        })

    keyframe_batches: list[list[str]] = []
    for i in range(0, len(all_keyframe_paths), KEYFRAME_BATCH_SIZE):
        keyframe_batches.append(all_keyframe_paths[i:i + KEYFRAME_BATCH_SIZE])

    # --- Contact sheets (batch keyframe grids) ---
    contact_sheets: list[dict[str, Any]] = []
    try:
        contact_sheets = build_contact_sheets(
            cv2, np, draft_blocks, out_dir,
            batch_size=KEYFRAME_BATCH_SIZE, grid_cols=3, thumb_width=420,
        )
        if contact_sheets:
            notes.append(f"Generated {len(contact_sheets)} contact sheet(s) for batch keyframe review")
    except Exception as exc:
        notes.append(f"Contact sheet generation failed (non-blocking): {exc}")

    asr_compact: list[dict[str, str]] = []
    for seg in asr_result.get("segments", [])[:20]:
        asr_compact.append({
            "time": f"{seg.get('start_time', '')} - {seg.get('end_time', '')}",
            "text": seg.get("text", "")[:120],
        })

    ocr_compact: list[dict[str, Any]] = []
    for det in ocr_result.get("detections", [])[:15]:
        ocr_compact.append({
            "frame": Path(det.get("frame", "")).name,
            "texts": det.get("texts", [])[:5],
        })

    agent_summary = {
        "_purpose": "Compact overview for LLM fill-in. Read THIS instead of the full analysis.json.",
        "video_duration": video_info.get("duration_timecode", ""),
        "video_resolution": f"{video_info.get('resolution', {}).get('width', '')}x{video_info.get('resolution', {}).get('height', '')}",
        "total_blocks": len(draft_blocks),
        "detection_method": detection_method,
        "blocks": block_overview,
        "keyframe_batches": keyframe_batches,
        "contact_sheets": contact_sheets,
        "asr_status": asr_result["status"],
        "asr_segments": asr_compact,
        "ocr_status": ocr_result["status"],
        "ocr_detections": ocr_compact,
        "degradation_notes": [n for n in notes if "unavailable" in n.lower() or "failed" in n.lower() or "degraded" in n.lower() or "fallback" in n.lower()],
    }

    analysis = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "video": video_info,
        "agent_summary": agent_summary,
        "analysis_config": {
            "sample_interval_sec": sample_interval,
            "scene_threshold": sd_threshold,
            "content_threshold": sd_content_threshold,
            "detection_method": detection_method,
            "max_samples": max_samples,
            "max_width": int(args.max_width),
            "asr_enabled": bool(args.asr),
            "ocr_enabled": bool(args.ocr),
            "effective_range": {
                "start": round(effective_start, 3),
                "start_time": format_seconds(effective_start),
                "end": round(effective_end, 3),
                "end_time": format_seconds(effective_end),
                "is_clip": effective_start > 0.001 or effective_end < duration - 0.001,
            },
        },
        "scene_candidates": scene_candidates,
        "draft_blocks": draft_blocks,
        "asr": asr_result,
        "ocr": ocr_result,
        "notes": notes,
        "degradation": {
            "asr": asr_result["status"],
            "ocr": ocr_result["status"],
            "scene_detection": detection_method,
        },
    }

    # Include full sampled_frames metadata only when requested (saves 40-60% of JSON size on dense scans)
    keep_all = getattr(args, "keep_all_frames", False)
    if keep_all:
        analysis["sampled_frames"] = sampled_frames
    else:
        analysis["sampled_frame_count"] = len(sampled_frames)

    analysis_path = out_dir / "analysis.json"
    write_json(analysis_path, analysis)

    generated_files = [str(analysis_path), str(keyframe_dir)]
    if asr_result.get("status") == "ok":
        generated_files.append(str(out_dir / "audio.wav"))

    summary: dict[str, Any] = {
        "status": "ok",
        "stage": "scan-video",
        "output_directory": str(out_dir),
        "generated": generated_files,
        "sampled_frame_count": len(sampled_frames),
        "scene_candidate_count": len(scene_candidates),
        "draft_block_count": len(draft_blocks),
        "detection_method": detection_method,
        "warnings": [n for n in notes if "unavailable" in n.lower() or "failed" in n.lower() or "degraded" in n.lower() or "skipped" in n.lower()],
        "notes": notes,
        "degradation": analysis["degradation"],
        "next_recommended_step": f"draft-from-analysis --analysis-json {analysis_path} --output {out_dir / 'cue_sheet.md'} --template <TEMPLATE>",
        "available_templates": sorted(TEMPLATE_COLUMNS.keys()),
    }

    if args.output_format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Output directory: {out_dir}")
        print(f"  analysis.json : {analysis_path}")
        print(f"  keyframes/    : {keyframe_dir} ({len(sampled_frames)} frames)")
        if asr_result.get("status") == "ok":
            print(f"  audio.wav     : {out_dir / 'audio.wav'}")
        if summary["warnings"]:
            for w in summary["warnings"]:
                print(f"  WARNING: {w}")
        print("Next step: draft-from-analysis")

    # Clean up temporary clip file if created
    if _clip_temp_path and _clip_temp_path.exists():
        try:
            _clip_temp_path.unlink()
        except OSError:
            pass

    return 0


__all__ = [
    "require_runtime_for_scan",
    "ffprobe_metadata",
    "build_video_info",
    "compute_hist_distance",
    "resize_frame",
    "read_frame_at",
    "build_draft_blocks",
    "detect_scenes_scenedetect",
    "extract_audio_track",
    "run_asr_faster_whisper",
    "run_ocr_on_frames",
    "compute_frame_sharpness",
    "compute_visual_features",
    "estimate_motion_hint",
    "refine_keyframe_selection",
    "deduplicate_similar_blocks",
    "build_contact_sheets",
    "cmd_scan_video",
    "cmd_plan_scan",
]


def cmd_plan_scan(args: "argparse.Namespace") -> int:  # noqa: F821
    """Convert template + optional density override into explicit scan-video parameters.

    This is a pure-mechanical planner: no video access, no LLM.
    It reads the template's recommended_density, applies any override,
    and outputs the exact scan-video command line to use.
    """
    from cc.templates import get_template_definition, load_templates

    load_templates()

    template_name = args.template
    tmpl = get_template_definition(template_name)
    if not tmpl:
        from cc.constants import TEMPLATE_COLUMNS
        available = ", ".join(sorted(TEMPLATE_COLUMNS.keys()))
        msg = f"Unknown template: '{template_name}'. Available: {available}"
        if hasattr(args, "output_format") and args.output_format == "json":
            print(json.dumps({"status": "error", "message": msg}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    # Resolve density: explicit override > template recommended > "normal"
    density = getattr(args, "density", None)
    if not density:
        density = tmpl.get("recommended_density", "normal")

    if density not in DENSITY_PRESETS:
        density = "normal"

    preset = DENSITY_PRESETS[density]
    seg = tmpl.get("segmentation", {})

    # Build the plan
    plan: dict[str, Any] = {
        "template": template_name,
        "density": density,
        "density_rationale": tmpl.get("density_rationale", ""),
        "sample_interval": preset["sample_interval"],
        "dedup_threshold": preset["dedup_threshold"],
        "segmentation_strategy": seg.get("strategy", "scene-cut"),
        "recommended_flags": [],
        "scan_command_args": [],
    }

    # Build recommended flags
    scan_args = [
        "--density", density,
    ]
    if density == "dense":
        plan["recommended_flags"].append("Consider --no-dedup for beat-accurate passes")
        if seg.get("strategy") == "emotional-arc":
            scan_args.append("--no-dedup")
            plan["recommended_flags"].append("--no-dedup auto-enabled for emotional-arc strategy with dense density")

    plan["scan_command_args"] = scan_args
    plan["suggested_command"] = "cuesheet-creator scan-video --video <VIDEO> " + " ".join(scan_args)

    is_json = hasattr(args, "output_format") and args.output_format == "json"
    if is_json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print(f"Template: {template_name}")
        print(f"Density: {density} (sample_interval={preset['sample_interval']}s, dedup_threshold={preset['dedup_threshold']})")
        if tmpl.get("density_rationale"):
            print(f"Rationale: {tmpl['density_rationale']}")
        print(f"Strategy: {seg.get('strategy', 'scene-cut')}")
        if plan["recommended_flags"]:
            print("Recommendations:")
            for flag in plan["recommended_flags"]:
                print(f"  - {flag}")
        print("\nSuggested command:")
        print(f"  cuesheet-creator scan-video --video <VIDEO> {' '.join(scan_args)}")

    return 0
