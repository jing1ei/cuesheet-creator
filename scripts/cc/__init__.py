"""cuesheet-creator — modular package.

This package provides modular import paths for the cuesheet-creator toolkit.
All functions are currently implemented in the monolith (cuesheet_creator.py)
and re-exported here for a clean import API.

Usage:
    from cc.templates import get_template_definition
    from cc.validation import evaluate_delivery_readiness
    from cc.scan import cmd_scan_video
"""
from __future__ import annotations

# Re-export version from the monolith
import sys
from pathlib import Path

# Ensure the monolith is importable
_scripts_dir = str(Path(__file__).resolve().parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from cuesheet_creator import __version__  # noqa: E402, F401

__all__ = ["__version__"]
