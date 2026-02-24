"""Pydantic models matching the Design Spec JSON schema from the Figma plugin."""

from __future__ import annotations

import math
import re
from enum import Enum
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _to_camel(s: str) -> str:
    """Convert snake_case to camelCase for Figma plugin compatibility."""
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class _CamelBase(BaseModel):
    """Base model that accepts both camelCase (plugin) and snake_case (backend) field names."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=_to_camel,
        extra="ignore",
    )


class BlendMode(str, Enum):
    PASS_THROUGH = "PASS_THROUGH"
    NORMAL = "NORMAL"
    DARKEN = "DARKEN"
    MULTIPLY = "MULTIPLY"
    COLOR_BURN = "COLOR_BURN"
    LIGHTEN = "LIGHTEN"
    SCREEN = "SCREEN"
    COLOR_DODGE = "COLOR_DODGE"
    OVERLAY = "OVERLAY"
    SOFT_LIGHT = "SOFT_LIGHT"
    HARD_LIGHT = "HARD_LIGHT"
    DIFFERENCE = "DIFFERENCE"
    EXCLUSION = "EXCLUSION"
    HUE = "HUE"
    SATURATION = "SATURATION"
    COLOR = "COLOR"
    LUMINOSITY = "LUMINOSITY"


class Color(_CamelBase):
    """RGBA color representation."""
    r: float = Field(0.0, ge=0.0, le=1.0, description="Red channel 0-1")
    g: float = Field(0.0, ge=0.0, le=1.0, description="Green channel 0-1")
    b: float = Field(0.0, ge=0.0, le=1.0, description="Blue channel 0-1")
    a: float = Field(1.0, ge=0.0, le=1.0, description="Alpha channel 0-1")

    @model_validator(mode="before")
    @classmethod
    def _normalize_color_range(cls, data: Any) -> Any:
        """Accept both 0-255 (plugin) and 0-1 (Figma API) color ranges."""
        if isinstance(data, dict):
            for ch in ("r", "g", "b"):
                val = data.get(ch)
                if isinstance(val, (int, float)) and val > 1.0:
                    data[ch] = val / 255.0
        return data

    def to_css_rgba(self) -> str:
        """Convert to CSS rgba() string."""
        r = round(self.r * 255)
        g = round(self.g * 255)
        b = round(self.b * 255)
        if self.a == 1.0:
            return f"rgb({r}, {g}, {b})"
        return f"rgba({r}, {g}, {b}, {round(self.a, 3)})"

    def to_css_hex(self) -> str:
        """Convert to CSS hex string."""
        r = round(self.r * 255)
        g = round(self.g * 255)
        b = round(self.b * 255)
        if self.a < 1.0:
            a = round(self.a * 255)
            return f"#{r:02x}{g:02x}{b:02x}{a:02x}"
        return f"#{r:02x}{g:02x}{b:02x}"


class GradientStop(_CamelBase):
    """Gradient color stop."""
    position: float = Field(0.0, ge=0.0, le=1.0)
    color: Color = Field(default_factory=Color)


class Fill(_CamelBase):
    """Fill paint specification."""
    type: str = Field("SOLID", description="SOLID, GRADIENT_LINEAR, GRADIENT_RADIAL, GRADIENT_ANGULAR, GRADIENT_DIAMOND, IMAGE")
    color: Optional[Color] = None
    opacity: float = Field(1.0, ge=0.0, le=1.0)
    visible: bool = True
    blend_mode: str = "NORMAL"
    gradient_stops: list[GradientStop] = Field(default_factory=list)
    gradient_handle_positions: list[dict[str, float]] = Field(default_factory=list)
    gradient_transform: Optional[list[list[float]]] = None
    image_ref: Optional[str] = None
    scale_mode: Optional[str] = None
    image_transform: Optional[list[list[float]]] = None

    @model_validator(mode="before")
    @classmethod
    def _accept_plugin_fields(cls, data: Any) -> Any:
        """Remap plugin field: imageHash -> image_ref."""
        if isinstance(data, dict):
            if "imageHash" in data and "imageRef" not in data and "image_ref" not in data:
                data["image_ref"] = data.pop("imageHash")
        return data

    def gradient_angle_deg(self) -> float | None:
        """Compute CSS gradient angle from the Figma gradient transform matrix.

        Figma's gradientTransform is a 2x3 affine matrix [[a, b, tx], [c, d, ty]].
        The gradient direction vector is (a, c) which we convert to a CSS angle
        (0deg = bottom-to-top, 90deg = left-to-right).

        Falls back to gradientHandlePositions if no transform is present.
        Returns None if neither is available.
        """
        if self.gradient_transform and len(self.gradient_transform) >= 2:
            row0 = self.gradient_transform[0]
            row1 = self.gradient_transform[1]
            if len(row0) >= 2 and len(row1) >= 1:
                # Direction vector from the affine matrix
                dx, dy = row0[0], row1[0]
                angle_rad = math.atan2(dx, -dy)
                angle_deg = math.degrees(angle_rad) % 360
                return round(angle_deg, 1)
        # Fallback: derive from handle positions
        if len(self.gradient_handle_positions) >= 2:
            start = self.gradient_handle_positions[0]
            end = self.gradient_handle_positions[1]
            dx = end.get("x", 0) - start.get("x", 0)
            dy = end.get("y", 0) - start.get("y", 0)
            if dx != 0 or dy != 0:
                angle_rad = math.atan2(dx, -dy)
                angle_deg = math.degrees(angle_rad) % 360
                return round(angle_deg, 1)
        return None


class Stroke(_CamelBase):
    """Stroke specification."""
    type: str = "SOLID"
    color: Color = Field(default_factory=Color)
    opacity: float = Field(1.0, ge=0.0, le=1.0)
    weight: float = 1.0
    align: str = Field("INSIDE", description="INSIDE, OUTSIDE, CENTER")
    visible: bool = True
    dash_pattern: list[float] = Field(default_factory=list)


class Effect(_CamelBase):
    """Visual effect (shadow, blur, etc.)."""
    type: str = Field(..., description="DROP_SHADOW, INNER_SHADOW, LAYER_BLUR, BACKGROUND_BLUR")
    visible: bool = True
    color: Optional[Color] = None
    offset: Optional[dict[str, float]] = None
    radius: float = 0.0
    spread: float = 0.0
    blend_mode: str = "NORMAL"

    @model_validator(mode="before")
    @classmethod
    def _accept_plugin_fields(cls, data: Any) -> Any:
        """Remap plugin offset fields: offsetX/offsetY → offset: {x, y}."""
        if isinstance(data, dict):
            if "offset" not in data:
                ox = data.pop("offsetX", None)
                oy = data.pop("offsetY", None)
                if ox is not None or oy is not None:
                    data["offset"] = {
                        "x": float(ox) if ox is not None else 0.0,
                        "y": float(oy) if oy is not None else 0.0,
                    }
        return data


class TextSegment(_CamelBase):
    """A segment of text with consistent styling."""
    characters: str = ""
    font_family: str = "Inter"
    font_weight: int = 400
    font_size: float = 16.0
    line_height: Optional[float] = None
    line_height_unit: str = "AUTO"
    letter_spacing: float = 0.0
    letter_spacing_unit: str = "PIXELS"
    text_decoration: str = "NONE"
    text_transform: str = "NONE"
    fill: Optional[Fill] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_fields(cls, data: Any) -> Any:
        """Normalize plugin-format fields.

        - lineHeight: 'auto' → None
        - color (bare RGBA dict) → fill: {type: SOLID, color: ...}
        """
        if isinstance(data, dict):
            # Convert lineHeight: 'auto' to None
            for key in ("line_height", "lineHeight"):
                if data.get(key) == "auto":
                    data[key] = None
            # Plugin sends bare 'color' dict; wrap it into a Fill
            if "color" in data and "fill" not in data:
                color_val = data.pop("color")
                if isinstance(color_val, dict):
                    data["fill"] = {"type": "SOLID", "color": color_val}
        return data


class Bounds(_CamelBase):
    """Bounding box of a node."""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0


class CornerRadius(_CamelBase):
    """Corner radius specification."""
    top_left: float = 0.0
    top_right: float = 0.0
    bottom_right: float = 0.0
    bottom_left: float = 0.0

    @property
    def is_uniform(self) -> bool:
        return (
            self.top_left == self.top_right == self.bottom_right == self.bottom_left
        )

    @staticmethod
    def _fmt(v: float) -> str:
        """Format a float as integer string if it has no fractional part."""
        return str(int(v)) if v == int(v) else str(v)

    def to_css(self) -> str:
        if self.is_uniform:
            if self.top_left == 0:
                return ""
            return f"{self._fmt(self.top_left)}px"
        return (
            f"{self._fmt(self.top_left)}px {self._fmt(self.top_right)}px "
            f"{self._fmt(self.bottom_right)}px {self._fmt(self.bottom_left)}px"
        )


class Layout(_CamelBase):
    """Auto-layout properties from Figma."""
    mode: str = Field("NONE", description="NONE, HORIZONTAL, VERTICAL")
    padding_top: float = 0.0
    padding_right: float = 0.0
    padding_bottom: float = 0.0
    padding_left: float = 0.0
    item_spacing: float = 0.0
    counter_axis_spacing: float = 0.0
    primary_axis_align: str = Field("MIN", description="MIN, CENTER, MAX, SPACE_BETWEEN")
    counter_axis_align: str = Field("MIN", description="MIN, CENTER, MAX, BASELINE")
    layout_wrap: str = Field("NO_WRAP", description="NO_WRAP, WRAP")
    primary_axis_sizing: str = Field("AUTO", description="AUTO, FIXED")
    counter_axis_sizing: str = Field("AUTO", description="AUTO, FIXED")


class Constraints(_CamelBase):
    """Layout constraints for the node."""
    horizontal: str = Field("LEFT", description="LEFT, RIGHT, CENTER, LEFT_RIGHT, SCALE")
    vertical: str = Field("TOP", description="TOP, BOTTOM, CENTER, TOP_BOTTOM, SCALE")


class Style(_CamelBase):
    """Visual style properties of a node."""
    fills: list[Fill] = Field(default_factory=list)
    strokes: list[Stroke] = Field(default_factory=list)
    effects: list[Effect] = Field(default_factory=list)
    opacity: float = Field(1.0, ge=0.0, le=1.0)
    corner_radius: Optional[CornerRadius] = None
    blend_mode: str = "PASS_THROUGH"
    overflow: str = Field("VISIBLE", description="VISIBLE, HIDDEN, SCROLL")
    rotation: float = 0.0
    corner_smoothing: float = Field(0.0, description="iOS-style squircle smoothing (0-1)")
    # Per-side stroke weights (from Figma); when set, generator uses border-top/right/bottom/left
    stroke_top_weight: Optional[float] = None
    stroke_bottom_weight: Optional[float] = None
    stroke_left_weight: Optional[float] = None
    stroke_right_weight: Optional[float] = None


class TextInfo(_CamelBase):
    """Text-specific information."""
    characters: str = ""
    segments: list[TextSegment] = Field(default_factory=list)
    text_align_horizontal: str = Field("LEFT", description="LEFT, CENTER, RIGHT, JUSTIFIED")
    text_align_vertical: str = Field("TOP", description="TOP, CENTER, BOTTOM")
    text_auto_resize: str = Field("NONE", description="NONE, WIDTH_AND_HEIGHT, HEIGHT, TRUNCATE")
    max_lines: Optional[int] = Field(None, description="Max lines when textTruncation is set (Figma)")
    paragraph_spacing: float = Field(0.0, description="Vertical space between paragraphs (px)")
    paragraph_indent: float = Field(0.0, description="First-line indent for paragraphs (px)")


class ComponentInfo(_CamelBase):
    """Component metadata."""
    component_id: Optional[str] = None
    component_name: Optional[str] = None
    is_instance: bool = False
    main_component_id: Optional[str] = None
    variant_properties: dict[str, str] = Field(default_factory=dict)


class DesignNode(_CamelBase):
    """A single node in the Figma design tree."""
    id: str
    name: str = ""
    type: str = Field(..., description="FRAME, GROUP, TEXT, RECTANGLE, ELLIPSE, VECTOR, INSTANCE, COMPONENT, etc.")
    visible: bool = True
    bounds: Bounds = Field(default_factory=Bounds)
    absolute_bounds: Optional[Bounds] = None
    style: Style = Field(default_factory=Style)
    layout: Layout = Field(default_factory=Layout)
    constraints: Optional[Constraints] = None
    text: Optional[TextInfo] = None
    component: Optional[ComponentInfo] = None
    children: list[DesignNode] = Field(default_factory=list)
    export_settings: list[dict[str, Any]] = Field(default_factory=list)
    is_mask: bool = False
    clip_content: bool = False

    def is_container(self) -> bool:
        """Check if this node can have children."""
        return self.type in ("FRAME", "GROUP", "INSTANCE", "COMPONENT", "COMPONENT_SET", "SECTION")

    def has_auto_layout(self) -> bool:
        """Check if this node has auto-layout enabled."""
        return self.layout.mode != "NONE"

    def get_all_descendants(self) -> list[DesignNode]:
        """Recursively get all descendant nodes."""
        descendants: list[DesignNode] = []
        for child in self.children:
            descendants.append(child)
            descendants.extend(child.get_all_descendants())
        return descendants


class AssetReference(_CamelBase):
    """Reference to an exported asset."""
    node_id: str
    filename: str = ""
    format: str = "png"
    scale: float = 1.0
    url: Optional[str] = None
    data_base64: Optional[str] = None
    byte_size: Optional[int] = None
    mime_type: Optional[str] = None

    _FORMAT_EXT_MAP: ClassVar[dict[str, str]] = {
        "SVG": "svg",
        "PNG": "png",
        "JPG": "jpg",
        "JPEG": "jpg",
        "PDF": "pdf",
    }

    @model_validator(mode="before")
    @classmethod
    def _accept_plugin_fields(cls, data: Any) -> Any:
        """Remap plugin field names: nodeName→filename, data→data_base64."""
        if isinstance(data, dict):
            # Plugin sends 'nodeName' instead of 'filename'
            if "nodeName" in data and "filename" not in data and "file_name" not in data:
                node_name = data.pop("nodeName")
                if "." not in node_name:
                    fmt = (data.get("format") or "png").upper()
                    ext = cls._FORMAT_EXT_MAP.get(fmt, "png")
                    node_name = f"{node_name}.{ext}"
                data["filename"] = node_name
            # Plugin sends 'data' instead of 'dataBase64' / 'data_base64'
            if "data" in data and "dataBase64" not in data and "data_base64" not in data:
                data["data_base64"] = data.pop("data")

            # Ensure filename uniqueness by incorporating node_id
            node_id = data.get("nodeId") or data.get("node_id", "")
            filename = data.get("filename", "")
            if node_id and filename:
                safe_id = re.sub(r'[^a-zA-Z0-9]', '-', node_id).strip('-')
                if "." in filename:
                    name, ext = filename.rsplit(".", 1)
                else:
                    fmt = (data.get("format") or "png").upper()
                    ext = cls._FORMAT_EXT_MAP.get(fmt, "png")
                    name = filename
                data["filename"] = f"{name}-{safe_id}.{ext}"
        return data


class Metadata(_CamelBase):
    """Design spec metadata."""
    file_key: str = ""
    file_name: str = ""
    frame_id: str = ""
    frame_name: str = ""
    exported_at: str = ""
    plugin_version: str = ""
    figma_schema_version: str = ""

    @model_validator(mode="before")
    @classmethod
    def _accept_plugin_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Plugin sends lastModified instead of exportedAt
            if "lastModified" in data and "exportedAt" not in data and "exported_at" not in data:
                data["exported_at"] = data.pop("lastModified")
        return data


class DesignSpec(_CamelBase):
    """Complete design specification from the Figma plugin."""
    metadata: Metadata = Field(default_factory=Metadata)
    root: DesignNode
    assets: list[AssetReference] = Field(default_factory=list)
    fonts_used: list[str] = Field(default_factory=list)
    color_palette: list[Color] = Field(default_factory=list)
    frame_screenshot: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _accept_plugin_format(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Plugin sends nodes: [rootNode] instead of root: rootNode
            if "nodes" in data and "root" not in data:
                nodes = data.pop("nodes")
                if isinstance(nodes, list) and nodes:
                    data["root"] = nodes[0]

            # Plugin sends frameName at top level; copy into metadata
            frame_name = data.get("frameName") or data.get("frame_name")
            if frame_name:
                meta = data.get("metadata") or {}
                if isinstance(meta, dict):
                    if not meta.get("frameName") and not meta.get("frame_name"):
                        meta["frame_name"] = frame_name
                    data["metadata"] = meta
        return data
