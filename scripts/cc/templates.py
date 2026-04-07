"""Template system: registry, validation, column helpers."""
from __future__ import annotations

from cuesheet_creator import (
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
    load_templates,
    validate_template_json,
    validate_template_name,
)

__all__ = ['validate_template_json', '_template_columns_from_json', '_template_column_widths_from_json', 'load_templates', 'get_template_definition', 'get_template_segmentation', 'get_template_perspective', 'get_template_fill_guidance', 'get_template_prefill_map', 'get_template_column_widths', 'validate_template_name', 'get_recommended_fields', 'get_required_fields']
