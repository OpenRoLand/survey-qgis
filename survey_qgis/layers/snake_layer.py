"""Backwards-compatible aliases for the path-lines memory layer."""

from __future__ import annotations

from survey_qgis.layers.path_lines_layer import (
    PATH_LINES_LAYER_PROPERTY as SNAKE_LAYER_PROPERTY,
    add_path_lines_layer as add_snake_layer,
    apply_path_lines_color_scale as apply_snake_color_scale,
    create_path_lines_layer as create_snake_layer,
    is_path_lines_layer as is_snake_layer,
    rebuild_path_lines_layer as rebuild_snake_layer,
)

# Older call sites used the "hidden" name for legend placement.
add_snake_layer_hidden = add_snake_layer

__all__ = [
    "SNAKE_LAYER_PROPERTY",
    "create_snake_layer",
    "is_snake_layer",
    "rebuild_snake_layer",
    "add_snake_layer",
    "add_snake_layer_hidden",
    "apply_snake_color_scale",
]
