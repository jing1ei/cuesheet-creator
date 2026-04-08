"""Constants and configuration for cuesheet-creator."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

__version__ = "1.4.1"

REQUIRED_PACKAGES = {
    "opencv-python-headless": "cv2",
    "numpy": "numpy",
    "Pillow": "PIL",
    "openpyxl": "openpyxl",
}

OPTIONAL_COMPONENTS = {
    "scene:scenedetect": {
        "group": "scene",
        "pip_name": "scenedetect[opencv]",
        "pip_spec": "scenedetect[opencv]>=0.6,<1",
        "import_name": "scenedetect",
    },
    "asr:faster-whisper": {
        "group": "asr",
        "pip_name": "faster-whisper",
        "pip_spec": "faster-whisper>=1.0,<2",
        "import_name": "faster_whisper",
    },
    "ocr:rapidocr": {
        "group": "ocr",
        "pip_name": "rapidocr-onnxruntime",
        "pip_spec": "rapidocr-onnxruntime>=1.3,<2",
        "import_name": "rapidocr_onnxruntime",
    },
    "ocr:easyocr": {
        "group": "ocr-extra",
        "pip_name": "easyocr",
        "pip_spec": "easyocr>=1.7,<2",
        "import_name": "easyocr",
    },
    "ocr:paddleocr": {
        "group": "ocr-extra",
        "pip_name": "paddleocr",
        "pip_spec": "paddleocr>=2.7,<3",
        "import_name": "paddleocr",
    },
}

_BUILTIN_TEMPLATE_COLUMNS: dict[str, list[str]] = {
    "script": [
        "shot_block", "start_time", "end_time", "scene", "location",
        "characters", "event", "important_dialogue", "confidence", "needs_confirmation",
    ],
    "production": [
        "shot_block", "start_time", "end_time", "keyframe", "shot_size",
        "angle_or_lens", "motion", "scene", "mood", "location", "characters",
        "event", "important_dialogue", "music_note", "director_note",
        "confidence", "needs_confirmation",
    ],
    "music-director": [
        "shot_block", "start_time", "end_time", "mood", "event",
        "important_dialogue", "music_note", "rhythm_change", "instrumentation",
        "dynamics", "confidence", "needs_confirmation",
    ],
}

# Template system runtime state
_TEMPLATE_REGISTRY: dict[str, dict[str, Any]] = {}
TEMPLATE_COLUMNS: dict[str, list[str]] = {}
_BUILTIN_TEMPLATE_NAMES: set[str] = set()

# Template schema
_TEMPLATE_REQUIRED_FIELDS = {"name", "description", "perspective", "segmentation", "columns"}
_TEMPLATE_REQUIRED_SEGMENTATION_FIELDS = {"strategy", "description", "split_triggers", "merge_bias", "keyframe_priority"}
_TEMPLATE_REQUIRED_COLUMN_FIELDS = {"field", "label"}
_STRUCTURAL_COLUMN_FIELDS = {"shot_block", "start_time", "end_time"}
TEMPLATE_SCHEMA_VERSION = 2

DEFAULT_COLUMN_WIDTHS = {
    "shot_block": 12, "start_time": 14, "end_time": 14, "keyframe": 24,
    "shot_size": 12, "angle_or_lens": 20, "motion": 18, "scene": 18,
    "mood": 20, "location": 18, "characters": 20, "event": 28,
    "important_dialogue": 30, "music_note": 28, "director_note": 28,
    "confidence": 18, "needs_confirmation": 24, "rhythm_change": 20,
    "instrumentation": 20, "dynamics": 18,
}

SUPPORTED_OPTIONAL_GROUPS = {"asr", "ocr", "ocr-extra", "scene"}

# Density presets: map high-level intent to mechanical scan parameters.
# "frame-accurate" is intentionally excluded — it requires the two-pass workflow
# described in SKILL.md and cannot be achieved with a single scan-video invocation.
DENSITY_PRESETS: dict[str, dict[str, float]] = {
    "sparse": {"sample_interval": 5.0, "dedup_threshold": 0.10},
    "normal": {"sample_interval": 2.0, "dedup_threshold": 0.08},
    "dense":  {"sample_interval": 0.5, "dedup_threshold": 0.06},
}

PREPARE_ENV_MODES = {
    "check-only": set(),
    "install-required": set(),
    "install-scene": {"scene"},
    "install-asr": {"asr"},
    "install-ocr": {"ocr"},
    "install-ocr-extra": {"ocr", "ocr-extra"},
    "install-all": {"asr", "ocr", "scene"},  # aligned with pyproject.toml [all] extra
    "install-everything": set(SUPPORTED_OPTIONAL_GROUPS),  # truly everything incl. ocr-extra
}

PREPARE_ENV_DEFAULT_FILES = {
    "precheck": "selfcheck.pre.json",
    "install_report": "install_report.json",
    "postcheck": "selfcheck.post.json",
    "report": "prepare_env.json",
}

# Skill root: detect source-layout vs installed-package layout.
# Source layout: repo/scripts/cc/constants.py -> repo root is parent.parent.parent
# Installed:     site-packages/cc/constants.py -> no meaningful repo root
_CC_PACKAGE_DIR = Path(__file__).resolve().parent

def _detect_skill_root() -> Path:
    """Return the repo root if running from source, or the package dir otherwise."""
    candidate = _CC_PACKAGE_DIR.parent.parent  # scripts/ -> repo root
    # Heuristic: source layout has templates/ and SKILL.md at the root
    if (candidate / "templates").is_dir() and (candidate / "SKILL.md").is_file():
        return candidate
    # Installed mode — return the cc package dir as fallback
    return _CC_PACKAGE_DIR

SKILL_ROOT = _detect_skill_root()

# User-writable data directory for custom templates and other mutable state.
# Cross-platform: ~/.cuesheet-creator/
USER_DATA_DIR = Path.home() / ".cuesheet-creator"

LOCAL_FFMPEG_BIN_ENV = "CUESHEET_CREATOR_FFMPEG_BIN_DIR"
LOCAL_FFMPEG_SEARCH_ROOT = SKILL_ROOT / "tools" / "ffmpeg"

# Runtime overrides set by --ffmpeg-path / --ffprobe-path CLI args.
_CLI_COMMAND_OVERRIDES: dict[str, str] = {}

# Naming
NAMING_REPLACE_FIELDS = {"scene", "characters", "location", "event", "important_dialogue", "needs_confirmation", "director_note", "music_note"}

NAMING_CATEGORY_FIELDS: dict[str, list[str]] = {
    "characters": ["characters"],
    "scenes": ["scene", "location"],
    "props": [],
}

# Normalize enums
SHOT_SIZE_ENUM = {"WS", "MS", "CU", "EWS", "ECU"}
SHOT_SIZE_ALIASES: dict[str, str] = {
    "wide shot": "WS", "wide": "WS",
    "medium shot": "MS", "medium": "MS", "mid": "MS", "mid shot": "MS",
    "close-up": "CU", "close up": "CU", "closeup": "CU", "cu": "CU",
    "extreme wide shot": "EWS", "extreme wide": "EWS",
    "extreme close-up": "ECU", "extreme close up": "ECU", "extreme closeup": "ECU",
    "ws": "WS", "ms": "MS", "ews": "EWS", "ecu": "ECU",
}

MOTION_ENUM = {"static", "push-in", "pull-out", "pan", "tracking", "handheld"}
MOTION_ALIASES: dict[str, str] = {
    "push in": "push-in", "pushin": "push-in",
    "pull out": "pull-out", "pullout": "pull-out",
    "track": "tracking", "dolly": "tracking",
    "hand-held": "handheld", "hand held": "handheld",
    "still": "static", "locked": "static", "fixed": "static",
    "panning": "pan",
}

# ---------------------------------------------------------------------------
# Compiled regex patterns (shared across modules)
# ---------------------------------------------------------------------------

# Regex for temp: markers.  Matches "temp: Girl-A", "Temp: Dr. Smith",
# "TEMP: O'Brien", CJK names, etc.  Case-insensitive prefix.
# Stops at punctuation that signals the start of a verb phrase
# (avoids "temp: Girl-A enters" false positive).
_TEMP_MARKER_RE = re.compile(
    r"temp:\s*[A-Za-z0-9\u4e00-\u9fff]"           # must start with alnum / CJK
    r"[\w\u4e00-\u9fff.'\-]*"                       # word chars, dots, apostrophes, hyphens
    r"(?:\s+[A-Z\u4e00-\u9fff][\w\u4e00-\u9fff.'\-]*)*",  # additional capitalized / CJK words
    re.UNICODE | re.IGNORECASE,
)

_VISUAL_HINT_RE = re.compile(r"\[visual:\s*[^\]]*\]\s*")
_OCR_HINT_RE = re.compile(r"\[OCR detected:\s*[^\]]*\]\s*")
_MOTION_HINT_RE = re.compile(r"\[motion-hint:\s*[^\]]*\]\s*")
