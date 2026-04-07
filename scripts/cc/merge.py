"""Block merging and continuity scoring."""
from __future__ import annotations

from cuesheet_creator import (
    _strategy_weight_multipliers,
    cmd_merge_blocks,
    cmd_suggest_merges,
    compute_block_continuity,
)

__all__ = ['_strategy_weight_multipliers', 'compute_block_continuity', 'cmd_suggest_merges', 'cmd_merge_blocks']
