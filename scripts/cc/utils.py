"""Shared utility functions for cuesheet-creator."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def ensure_parent(path: Path) -> None:
    """Create parent directories if they don't exist."""
    path.parent.mkdir(parents=True, exist_ok=True)




def write_json(path: Path, data: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file with BOM tolerance (utf-8-sig handles both BOM and plain UTF-8).

    This is the preferred way to load JSON files in the project — it handles
    Windows editors/tools that write UTF-8 BOM, PowerShell output, etc.
    """
    text = path.read_text(encoding="utf-8-sig")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc




def format_seconds(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    whole = int(seconds)
    millis = int(round((seconds - whole) * 1000))
    if millis == 1000:
        whole += 1
        millis = 0
    hours = whole // 3600
    minutes = (whole % 3600) // 60
    secs = whole % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"




def seconds_from_timecode(text: str) -> float:
    """Parse a timecode string into seconds.

    Accepted formats:
      HH:MM:SS.mmm   (canonical)
      HH:MM:SS,mmm   (SRT-style comma separator)
      HH:MM:SS        (no milliseconds — treated as .000)
      MM:SS.mmm
      MM:SS
      SS.mmm
      SS

    Raises ValueError with a user-friendly message on unrecognized input.
    """
    raw = text.strip()
    if not raw:
        raise ValueError("Empty timecode string.")

    # Normalize comma separator (SRT-style) to dot
    raw = raw.replace(",", ".")

    parts = raw.split(":")
    try:
        if len(parts) == 3:
            hh = int(parts[0])
            mm = int(parts[1])
            sec_parts = parts[2].split(".")
            ss = int(sec_parts[0])
            ms = int(sec_parts[1].ljust(3, "0")[:3]) if len(sec_parts) > 1 else 0
            return hh * 3600 + mm * 60 + ss + ms / 1000.0
        if len(parts) == 2:
            mm = int(parts[0])
            sec_parts = parts[1].split(".")
            ss = int(sec_parts[0])
            ms = int(sec_parts[1].ljust(3, "0")[:3]) if len(sec_parts) > 1 else 0
            return mm * 60 + ss + ms / 1000.0
        if len(parts) == 1:
            sec_parts = parts[0].split(".")
            ss = int(sec_parts[0])
            ms = int(sec_parts[1].ljust(3, "0")[:3]) if len(sec_parts) > 1 else 0
            return ss + ms / 1000.0
    except (ValueError, IndexError):
        pass

    raise ValueError(
        f"Unrecognized timecode format: '{text}'. "
        f"Expected HH:MM:SS.mmm, HH:MM:SS, MM:SS.mmm, MM:SS, or bare seconds."
    )




def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, capture_output=True, text=True, check=False,
        encoding="utf-8", errors="replace",
    )




def truncate_text(text: str | None, limit: int = 4000) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"




def resolved_path(value: str) -> str:
    """Argparse type helper: expand ~ and resolve to absolute path."""
    return str(Path(value).expanduser().resolve())




def detect_platform_family() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"




def command_filename(name: str) -> str:
    if detect_platform_family() == "windows" and not name.lower().endswith(".exe"):
        return f"{name}.exe"
    return name




def unique_in_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered




def make_block_id(index: int) -> str:
    return f"A{index}"




def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "N/A"):
            return default
        return float(value)
    except Exception:
        return default




def parse_fps(text: str | None) -> float | None:
    if not text or text in {"0/0", "N/A"}:
        return None
    if "/" in text:
        left, right = text.split("/", 1)
        denominator = float(right)
        if denominator == 0:
            return None
        return float(left) / denominator
    return float(text)




def relpath_for_markdown(target: str | None, md_path: Path) -> str:
    if not target:
        return ""
    try:
        return os.path.relpath(target, md_path.parent).replace("\\", "/")
    except Exception:
        return target.replace("\\", "/")




def resolve_keyframe_path(base_dir: Path | None, value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    if base_dir:
        return (base_dir / candidate).resolve()
    return candidate.resolve()




def scale_dimensions(width: int, height: int, max_width: int, max_height: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        return max_width, max_height
    ratio = min(max_width / width, max_height / height, 1.0)
    return max(int(width * ratio), 1), max(int(height * ratio), 1)


# ---------------------------------------------------------------------------
# Shared temp-marker coverage validation
# ---------------------------------------------------------------------------

