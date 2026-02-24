"""Deterministic HTML/CSS generator: walks the design tree and produces
pixel-perfect code directly from DesignSpec data — no LLM calls needed."""

from __future__ import annotations

import hashlib
import logging
import re

from agents.code_generator import _map_font
from schemas.design_spec import (
    Bounds,
    DesignNode,
    Fill,
    Stroke,
    Effect,
    TextSegment,
)
from schemas.layout_plan import LayoutPlan, LayoutStrategy

logger = logging.getLogger(__name__)

# Known serif and monospace font families for correct generic fallback (design-agnostic).
_SERIF_FONTS = frozenset(
    {
        "georgia", "times", "times new roman", "palatino", "garamond", "bookman",
        "playfair display", "merriweather", "lora", "source serif", "libre baskerville",
        "cambria", "constantia", "serif", "baskerville", "bodoni", "didot", "hoefler text",
    }
)
_MONO_FONTS = frozenset(
    {
        "courier", "monaco", "menlo", "consolas", "monospace", "fira code",
        "source code pro", "jetbrains mono", "ubuntu mono", "roboto mono", "inconsolata",
    }
)


# ────────────────────────────── helpers ──────────────────────────────


def _px(v: float) -> str:
    """Format a float as a CSS px value, dropping '.0' for integers."""
    if v == int(v):
        return f"{int(v)}px"
    # Round to 1 decimal to avoid floating-point noise like 6.600000000000001
    rounded = round(v, 1)
    if rounded == int(rounded):
        return f"{int(rounded)}px"
    return f"{rounded}px"


def _num(v: float) -> str:
    """Format a bare number, dropping '.0' for integers."""
    if v == int(v):
        return str(int(v))
    rounded = round(v, 1)
    if rounded == int(rounded):
        return str(int(rounded))
    return str(rounded)


_CSS_CLASS_MAX_LEN = 60


def _kebab(name: str) -> str:
    """Convert a Figma node name to a valid CSS class name (kebab-case).
    Truncate to _CSS_CLASS_MAX_LEN chars and append a short hash when truncated
    to avoid huge selectors and ensure uniqueness."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
    s = s or "node"
    # CSS class names must not start with a digit; prefix with "n" if needed
    if s and s[0].isdigit():
        s = f"n{s}"
    if len(s) > _CSS_CLASS_MAX_LEN:
        base = s[: _CSS_CLASS_MAX_LEN].rstrip("-")
        suffix = hashlib.md5(name.encode()).hexdigest()[:8]
        s = f"{base}-{suffix}" if base else f"node-{suffix}"
    return s


class _ClassNamer:
    """Generates unique CSS class names, deduplicating as needed."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def get(self, name: str) -> str:
        base = _kebab(name)
        if not base:
            base = "node"
        self._counts.setdefault(base, 0)
        self._counts[base] += 1
        if self._counts[base] == 1:
            return base
        return f"{base}-{self._counts[base]}"


# ────────────────────────────── CSS builders ─────────────────────────


def _fill_layer_value(fill: Fill, bg_asset_map: dict[str, str] | None = None) -> str | None:
    """Return the CSS value for one background layer (for stacked fills)."""
    if not fill.visible:
        return None
    if fill.type == "SOLID" and fill.color:
        if fill.opacity < 1.0:
            r, g, b = round(fill.color.r * 255), round(fill.color.g * 255), round(fill.color.b * 255)
            a = round(fill.color.a * fill.opacity, 3)
            return f"rgba({r}, {g}, {b}, {a})"
        return fill.color.to_css_rgba()
    if fill.type == "GRADIENT_LINEAR" and fill.gradient_stops:
        stops = ", ".join(
            f"{s.color.to_css_rgba() if s.color else '#000'} {s.position * 100:.1f}%"
            for s in fill.gradient_stops
        )
        angle = fill.gradient_angle_deg()
        angle_str = f"{angle}deg, " if angle is not None else ""
        return f"linear-gradient({angle_str}{stops})"
    if fill.type == "GRADIENT_RADIAL" and fill.gradient_stops:
        stops = ", ".join(
            f"{s.color.to_css_rgba() if s.color else '#000'} {s.position * 100:.1f}%"
            for s in fill.gradient_stops
        )
        return f"radial-gradient({stops})"
    if fill.type == "GRADIENT_ANGULAR" and fill.gradient_stops:
        stops = ", ".join(
            f"{s.color.to_css_rgba() if s.color else '#000'} {s.position * 100:.1f}%"
            for s in fill.gradient_stops
        )
        angle = fill.gradient_angle_deg()
        angle_str = f"from {angle}deg, " if angle is not None else ""
        return f"conic-gradient({angle_str}{stops})"
    if fill.type == "IMAGE" and fill.image_ref and bg_asset_map:
        asset_key = f"bg-{fill.image_ref}"
        asset_path = bg_asset_map.get(asset_key)
        if asset_path:
            return f"url('{asset_path}')"
    return None


def _fill_css(fill: Fill, bg_asset_map: dict[str, str] | None = None) -> str | None:
    """Convert a single visible Fill to a CSS property string (without trailing semicolon)."""
    if not fill.visible:
        return None
    if fill.type == "SOLID" and fill.color:
        color = fill.color.to_css_rgba()
        if fill.opacity < 1.0:
            # Apply fill-level opacity by modulating the alpha channel
            r, g, b = round(fill.color.r * 255), round(fill.color.g * 255), round(fill.color.b * 255)
            a = round(fill.color.a * fill.opacity, 3)
            return f"background-color: rgba({r}, {g}, {b}, {a})"
        return f"background-color: {color}"
    if fill.type == "GRADIENT_LINEAR" and fill.gradient_stops:
        stops = ", ".join(
            f"{s.color.to_css_rgba() if s.color else '#000'} {s.position * 100:.1f}%"
            for s in fill.gradient_stops
        )
        angle = fill.gradient_angle_deg()
        angle_str = f"{angle}deg, " if angle is not None else ""
        return f"background: linear-gradient({angle_str}{stops})"
    if fill.type == "GRADIENT_RADIAL" and fill.gradient_stops:
        stops = ", ".join(
            f"{s.color.to_css_rgba() if s.color else '#000'} {s.position * 100:.1f}%"
            for s in fill.gradient_stops
        )
        return f"background: radial-gradient({stops})"
    if fill.type == "GRADIENT_ANGULAR" and fill.gradient_stops:
        stops = ", ".join(
            f"{s.color.to_css_rgba() if s.color else '#000'} {s.position * 100:.1f}%"
            for s in fill.gradient_stops
        )
        angle = fill.gradient_angle_deg()
        angle_str = f"from {angle}deg, " if angle is not None else ""
        return f"background: conic-gradient({angle_str}{stops})"
    # IMAGE fills: use the background asset map to resolve the image URL
    if fill.type == "IMAGE" and fill.image_ref and bg_asset_map:
        asset_key = f"bg-{fill.image_ref}"
        asset_path = bg_asset_map.get(asset_key)
        if asset_path:
            scale_mode = fill.scale_mode or "FILL"
            size = "cover" if scale_mode in ("FILL", "CROP") else "contain"
            return (
                f"background-image: url('{asset_path}'); "
                f"background-size: {size}; "
                f"background-position: center; "
                f"background-repeat: no-repeat"
            )
    return None


def _stroke_css(stroke: Stroke) -> str | None:
    """Convert a Stroke to a CSS border property."""
    if not stroke.visible:
        return None
    color = stroke.color.to_css_rgba()
    return f"border: {_px(stroke.weight)} solid {color}"


def _effect_css(effects: list[Effect]) -> list[str]:
    """Convert a list of Effects to CSS properties."""
    shadows: list[str] = []
    filters: list[str] = []
    backdrop_filters: list[str] = []
    for eff in effects:
        if not eff.visible:
            continue
        if eff.type in ("DROP_SHADOW", "INNER_SHADOW"):
            ox = eff.offset.get("x", 0) if eff.offset else 0
            oy = eff.offset.get("y", 0) if eff.offset else 0
            blur = eff.radius
            spread = eff.spread
            color = eff.color.to_css_rgba() if eff.color else "rgba(0,0,0,0.25)"
            inset = "inset " if eff.type == "INNER_SHADOW" else ""
            shadows.append(f"{inset}{ox}px {oy}px {blur}px {spread}px {color}")
        elif eff.type == "LAYER_BLUR":
            filters.append(f"blur({eff.radius}px)")
        elif eff.type == "BACKGROUND_BLUR":
            backdrop_filters.append(f"blur({eff.radius}px)")
    props: list[str] = []
    if shadows:
        props.append(f"box-shadow: {', '.join(shadows)}")
    if filters:
        props.append(f"filter: {' '.join(filters)}")
    if backdrop_filters:
        props.append(f"backdrop-filter: {' '.join(backdrop_filters)}")
    return props


def _generic_font_family(font_name: str) -> str:
    """Return the CSS generic family (serif, monospace, sans-serif) for a font name."""
    key = (font_name or "").strip().lower()
    if key in _SERIF_FONTS:
        return "serif"
    if key in _MONO_FONTS:
        return "monospace"
    return "sans-serif"


def _text_segment_css(seg: TextSegment) -> dict[str, str]:
    """Build CSS property dict for a TextSegment."""
    css: dict[str, str] = {}
    mapped_font = _map_font(seg.font_family)
    generic = _generic_font_family(mapped_font)
    css["font-family"] = f"'{mapped_font}', {generic}"
    css["font-weight"] = str(seg.font_weight)
    css["font-size"] = _px(seg.font_size)
    if seg.line_height is not None:
        # Floor line-height at font-size to prevent glyph clipping when Figma reports smaller
        if seg.line_height < seg.font_size:
            css["line-height"] = "normal"
        else:
            css["line-height"] = _px(seg.line_height)
    if seg.letter_spacing and seg.letter_spacing != 0:
        unit = getattr(seg, "letter_spacing_unit", "PIXELS")
        if unit == "PERCENT":
            css["letter-spacing"] = f"{round(seg.font_size * seg.letter_spacing / 100, 2)}px"
        else:
            css["letter-spacing"] = _px(seg.letter_spacing)
    if seg.fill and seg.fill.color:
        css["color"] = seg.fill.color.to_css_rgba()
    if seg.text_decoration and seg.text_decoration != "NONE":
        css["text-decoration"] = seg.text_decoration.lower().replace("_", "-")
    if seg.text_transform and seg.text_transform not in ("NONE", "ORIGINAL"):
        css["text-transform"] = seg.text_transform.lower()
    return css


def _text_align_css(align: str) -> str | None:
    mapping = {"LEFT": "left", "CENTER": "center", "RIGHT": "right", "JUSTIFIED": "justify"}
    val = mapping.get(align)
    if val and val != "left":
        return f"text-align: {val}"
    return None


def _flex_align_map(figma_val: str) -> str:
    """Map Figma alignment enums to CSS flex alignment values."""
    mapping = {
        "MIN": "flex-start",
        "CENTER": "center",
        "MAX": "flex-end",
        "SPACE_BETWEEN": "space-between",
        "BASELINE": "baseline",
    }
    return mapping.get(figma_val, "flex-start")


def _collect_text_font_sizes(root: DesignNode) -> tuple[float, float]:
    """Collect font sizes from all text nodes and return (p75, p50) percentiles.

    Used for relative heading tag selection so thresholds adapt to the design
    rather than being hardcoded.
    """
    sizes: list[float] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "TEXT" and node.text and node.text.segments:
            for seg in node.text.segments:
                sizes.append(seg.font_size)
        stack.extend(node.children)
    if not sizes:
        return (24.0, 16.0)
    sizes.sort()
    n = len(sizes)
    p50 = sizes[min(int(n * 0.5), n - 1)]
    p75 = sizes[min(int(n * 0.75), n - 1)]
    return (p75, p50)


def _tag_for_node(
    node: DesignNode,
    is_image: bool,
    text_size_rank: tuple[float, float] | None = None,
) -> str:
    """Pick the right HTML tag for a node.

    text_size_rank is (p75_font_size, p50_font_size) computed from the entire
    design tree so heading detection is relative, not hardcoded.
    """
    if is_image:
        return "img"
    if node.type == "TEXT" and node.text:
        segs = node.text.segments
        if segs and segs[0].font_weight >= 600:
            size = segs[0].font_size
            p75, p50 = text_size_rank if text_size_rank else (24.0, 16.0)
            if size >= p75 and p75 > p50:
                return "h1"
            if size >= p50:
                return "h2"
            return "h3"
        return "p"
    return "div"


# ────────────────────────── recursive generator ──────────────────────


def _generate_node(
    node: DesignNode,
    parent: DesignNode | None,
    asset_map: dict[str, str],
    layout_plan: LayoutPlan,
    namer: _ClassNamer,
    html_lines: list[str],
    css_rules: list[str],
    depth: int = 0,
    parent_is_flex: bool = False,
    bg_asset_map: dict[str, str] | None = None,
    text_size_rank: tuple[float, float] | None = None,
    root_bounds: Bounds | None = None,
) -> None:
    """Recursively generate HTML + CSS for *node* and its visible children."""
    if not node.visible:
        return

    # Skip Figma mask definitions — these define clipping shapes in Figma
    # and should not be rendered as visible HTML elements.
    if node.is_mask:
        return

    # Skip nodes whose bounds fall entirely outside the root frame.
    # These are typically design annotations (e.g. "Manuscript" boxes)
    # placed beside the artboard in Figma — not actual content.
    if root_bounds is not None and parent is not None:
        nb = node.bounds
        rb = root_bounds
        if nb.x >= rb.x + rb.width or nb.x + nb.width <= rb.x:
            return
        if nb.y >= rb.y + rb.height or nb.y + nb.height <= rb.y:
            return

    # Skip invisible vector nodes that were filtered from asset_map:
    # these are tiny decorative paths with no meaningful fills or strokes to render.
    if node.type in ("VECTOR", "LINE", "STAR", "POLYGON") and node.id not in asset_map:
        visible_fills = [f for f in node.style.fills if f.visible and f.type == "SOLID"]
        visible_strokes = [s for s in node.style.strokes if s.visible]
        if not visible_fills and not visible_strokes:
            return

    # Skip clip-mask shapes: when parent has clip_content, the first child
    # can define the clipping boundary and should not be rendered visually —
    # the parent's overflow:hidden already handles clipping.
    if parent and getattr(parent, "clip_content", False) and node.id in asset_map:
        pb = parent.bounds
        nb = node.bounds
        covers_parent = (
            abs(nb.x - pb.x) < 2
            and abs(nb.y - pb.y) < 2
            and abs(nb.width - pb.width) < 2
            and abs(nb.height - pb.height) < 2
        )
        if covers_parent:
            return

    # Collapse redundant GROUP wrappers: if a GROUP has exactly one visible
    # child at identical bounds and no visual styling, skip the GROUP and
    # render the child directly.
    if node.type == "GROUP" and node.children:
        visible_kids = [c for c in node.children if c.visible]
        if len(visible_kids) == 1:
            child = visible_kids[0]
            same_bounds = (
                abs(child.bounds.x - node.bounds.x) < 1
                and abs(child.bounds.y - node.bounds.y) < 1
                and abs(child.bounds.width - node.bounds.width) < 1
                and abs(child.bounds.height - node.bounds.height) < 1
            )
            has_visual_styling = (
                any(f.visible for f in node.style.fills)
                or any(s.visible for s in node.style.strokes)
                or any(e.visible for e in node.style.effects)
                or getattr(node.style, "opacity", 1.0) < 1.0
                or getattr(node, "clip_content", False)
            )
            if same_bounds and not has_visual_styling:
                _generate_node(
                    child, parent, asset_map, layout_plan, namer,
                    html_lines, css_rules, depth, parent_is_flex, bg_asset_map,
                    text_size_rank, root_bounds,
                )
                return

    indent = "  " * depth
    cls = namer.get(node.name)
    node_id = node.id

    # ── Determine if this node is an image or text ──
    is_image = node_id in asset_map
    is_text = node.type == "TEXT" and node.text is not None and not is_image
    tag = _tag_for_node(node, is_image, text_size_rank)

    # ── Determine layout mode for this node's *children* ──
    decision = layout_plan.get_decision(node_id)
    has_auto_layout = node.has_auto_layout()
    use_flex = False
    flex_dir = "row"

    if decision and decision.strategy == LayoutStrategy.FLEX:
        use_flex = True
        flex_dir = decision.flex_direction or ("column" if node.layout.mode == "VERTICAL" else "row")
    elif has_auto_layout:
        use_flex = True
        flex_dir = "column" if node.layout.mode == "VERTICAL" else "row"

    has_children = bool(node.children) and node.type != "TEXT"
    children_absolute = has_children and not use_flex

    # ── CSS properties ──
    props: list[str] = []
    bx = node.bounds.x
    by = node.bounds.y
    bw = node.bounds.width
    bh = node.bounds.height

    # LINE nodes: Figma reports height=0 for the bounding box, but the stroke
    # weight defines the visual thickness.  Ensure the rendered element is visible
    # whether it's a CSS div or an <img> backed by an SVG asset.
    is_line_node = node.type == "LINE"
    if is_line_node:
        for stroke in node.style.strokes:
            if stroke.visible:
                min_dim = max(1, stroke.weight)
                if bh < min_dim:
                    bh = min_dim
                if bw < min_dim:
                    bw = min_dim
                break

    # Text auto-resize mode from Figma (NONE, WIDTH_AND_HEIGHT, HEIGHT, TRUNCATE)
    text_auto_resize = ""
    if is_text and node.text:
        text_auto_resize = getattr(node.text, "text_auto_resize", "NONE") or "NONE"

        # Compute font-size-proportional buffers for cross-engine rendering
        # differences. Browsers (Chrome, Firefox, Safari) render fonts with
        # different metrics than Figma's engine, so bounding boxes from Figma
        # are often too tight.  Scale buffer with both font size and character
        # count — cumulative per-glyph differences add up for longer strings.
        max_font_size = 16.0
        if node.text.segments:
            max_font_size = max(seg.font_size for seg in node.text.segments)
        text_chars = node.text.characters or ""
        char_count = max(1, len(text_chars.strip()))

        if max_font_size > 24:
            width_buffer = max(8, round(max_font_size * 0.15 * min(char_count, 6)))
        else:
            width_buffer = max(4, round(max_font_size * 0.08 * min(char_count, 10)))

        # Height buffer: Figma bounding boxes can be tighter than the
        # browser's glyph ascender.  A small buffer prevents the digit
        # bottoms from being clipped by overflow-y:clip while staying
        # within the gap before the next sibling element.
        height_buffer = max(4, round(max_font_size * 0.15))

        if text_auto_resize in ("WIDTH_AND_HEIGHT", "NONE"):
            bw += width_buffer
        elif text_auto_resize == "HEIGHT":
            bw += max(2, width_buffer // 3)
        if text_auto_resize != "TRUNCATE":
            bh += height_buffer

    # Positioning: if parent is flex, children flow; otherwise absolute
    if parent is None:
        props.append("position: relative")
        props.append(f"width: {_px(bw)}")
        props.append(f"height: {_px(bh)}")
        props.append("overflow: hidden")
    elif parent_is_flex:
        # Flex child: let flex handle position, but set size per text_auto_resize
        if is_text and text_auto_resize == "WIDTH_AND_HEIGHT":
            props.append(f"min-width: {_px(bw)}")
            props.append(f"min-height: {_px(bh)}")
        elif is_text and text_auto_resize == "HEIGHT":
            props.append(f"width: {_px(bw)}")
            props.append(f"min-height: {_px(bh)}")
        elif is_text:
            props.append(f"width: {_px(bw)}")
            props.append(f"height: {_px(bh)}")
        else:
            props.append(f"width: {_px(bw)}")
            props.append(f"height: {_px(bh)}")
        props.append("flex-shrink: 0")
    else:
        # Absolute-positioned child
        in_mask_group = (
            parent is not None
            and parent.type == "GROUP"
            and any(getattr(c, "is_mask", False) for c in parent.children)
        )
        if in_mask_group and is_image:
            props.append("position: absolute")
            props.append("left: 0")
            props.append("top: 0")
            props.append("width: 100%")
            props.append("height: 100%")
        else:
            px = parent.bounds.x if parent else 0
            py = parent.bounds.y if parent else 0
            left = bx - px
            top = by - py
            props.append("position: absolute")
            props.append(f"left: {_px(left)}")
            props.append(f"top: {_px(top)}")
            props.append(f"width: {_px(bw)}")
            props.append(f"height: {_px(bh)}")

    # Flex container
    if use_flex and has_children:
        props.append("display: flex")
        props.append(f"flex-direction: {flex_dir}")
        if node.layout.item_spacing > 0:
            props.append(f"gap: {_px(node.layout.item_spacing)}")
        if decision:
            if decision.justify_content:
                props.append(f"justify-content: {decision.justify_content}")
            else:
                props.append(f"justify-content: {_flex_align_map(node.layout.primary_axis_align)}")
            if decision.align_items:
                props.append(f"align-items: {decision.align_items}")
            else:
                props.append(f"align-items: {_flex_align_map(node.layout.counter_axis_align)}")
            if decision.flex_wrap:
                props.append(f"flex-wrap: {decision.flex_wrap}")
        else:
            props.append(f"justify-content: {_flex_align_map(node.layout.primary_axis_align)}")
            props.append(f"align-items: {_flex_align_map(node.layout.counter_axis_align)}")
            if node.layout.layout_wrap == "WRAP":
                props.append("flex-wrap: wrap")
        # Padding
        pt = node.layout.padding_top
        pr = node.layout.padding_right
        pb = node.layout.padding_bottom
        pl = node.layout.padding_left
        if any(v > 0 for v in (pt, pr, pb, pl)):
            props.append(f"padding: {_px(pt)} {_px(pr)} {_px(pb)} {_px(pl)}")
    elif children_absolute:
        if "position: relative" not in props and "position: absolute" not in props:
            props.append("position: relative")
        pt = node.layout.padding_top
        pr = node.layout.padding_right
        pb = node.layout.padding_bottom
        pl = node.layout.padding_left
        if any(v > 0 for v in (pt, pr, pb, pl)):
            props.append(f"padding: {_px(pt)} {_px(pr)} {_px(pb)} {_px(pl)}")

    is_mask_group = (
        node.type == "GROUP"
        and any(getattr(c, "is_mask", False) for c in node.children)
    )

    if "overflow: hidden" not in props:
        if is_mask_group:
            props.append("overflow: hidden")
        elif (node.style.overflow == "HIDDEN" or node.clip_content) and parent is not None:
            # Non-root containers: use overflow:clip with a small margin so
            # slight cross-engine rendering differences (font widths, SVG
            # rounding) are not visually truncated.
            props.append("overflow: clip")
            props.append("overflow-clip-margin: content-box 4px")
        elif node.style.overflow == "HIDDEN" or node.clip_content:
            props.append("overflow: hidden")

    # Fills (background) — skip for TEXT nodes (their fills are text color, not background)
    # Stacked fills: multiple visible fills as layered CSS backgrounds
    if not is_image and not is_text:
        visible_fills = [f for f in node.style.fills if f.visible]
        layer_values = []
        for f in visible_fills:
            v = _fill_layer_value(f, bg_asset_map=bg_asset_map)
            if v:
                layer_values.append(v)
        if len(layer_values) > 1:
            props.append(f"background: {', '.join(layer_values)}")
        elif len(layer_values) == 1:
            single_css = _fill_css(visible_fills[0], bg_asset_map=bg_asset_map)
            if single_css:
                props.append(single_css)

    # Strokes — per-side borders when widths differ; else single border
    if is_image:
        pass
    elif is_line_node:
        for stroke in node.style.strokes:
            if stroke.visible:
                props.append(f"background-color: {stroke.color.to_css_rgba()}")
                break
    else:
        st = getattr(node.style, "stroke_top_weight", None)
        sb = getattr(node.style, "stroke_bottom_weight", None)
        sl = getattr(node.style, "stroke_left_weight", None)
        sr = getattr(node.style, "stroke_right_weight", None)
        per_side = [x for x in (st, sb, sl, sr) if x is not None]
        if len(per_side) >= 2 and len(set(per_side)) > 1:
            # Per-side borders
            stroke_color = None
            for s in node.style.strokes:
                if s.visible and s.color:
                    stroke_color = s.color.to_css_rgba()
                    break
            if stroke_color:
                default_w = node.style.strokes[0].weight if node.style.strokes else 1.0
                top = _px(st) if st is not None else _px(default_w)
                bottom = _px(sb) if sb is not None else _px(default_w)
                left = _px(sl) if sl is not None else _px(default_w)
                right = _px(sr) if sr is not None else _px(default_w)
                props.append(f"border-top: {top} solid {stroke_color}")
                props.append(f"border-right: {right} solid {stroke_color}")
                props.append(f"border-bottom: {bottom} solid {stroke_color}")
                props.append(f"border-left: {left} solid {stroke_color}")
        else:
            for stroke in node.style.strokes:
                css_val = _stroke_css(stroke)
                if css_val:
                    props.append(css_val)
                    break

    # Corner radius
    if node.style.corner_radius:
        cr_css = node.style.corner_radius.to_css()
        if cr_css:
            props.append(f"border-radius: {cr_css}")

    # Effects (shadows, blur)
    props.extend(_effect_css(node.style.effects))

    # Opacity
    if node.style.opacity < 1.0:
        props.append(f"opacity: {node.style.opacity}")

    # Rotation
    if node.style.rotation and node.style.rotation != 0:
        props.append(f"transform: rotate({node.style.rotation}deg)")

    # Blend mode
    if node.style.blend_mode and node.style.blend_mode not in ("PASS_THROUGH", "NORMAL"):
        blend_css = node.style.blend_mode.lower().replace("_", "-")
        props.append(f"mix-blend-mode: {blend_css}")

    # Ellipse → 50% border-radius
    if node.type == "ELLIPSE":
        if "border-radius" not in " ".join(props):
            props.append("border-radius: 50%")

    # ── Text-specific styling ──
    text_content = ""
    segments = node.text.segments if is_text and node.text else []
    multi_segment = len(segments) > 1

    if is_text and node.text:
        # Figma uses \r for soft line-breaks (auto-wrap points within the text
        # box) and \n for hard line-breaks (explicit paragraph breaks).
        # Convert \r to a space so word boundaries are preserved in HTML
        # without forcing hard line breaks.  The container width handles wrapping.
        text_content = node.text.characters.replace("\r\n", "\n").replace("\r", " ")
        for seg in segments:
            seg.characters = seg.characters.replace("\r\n", "\n").replace("\r", " ")
        text_auto_resize = getattr(node.text, "text_auto_resize", "NONE") or "NONE"
        if text_auto_resize == "TRUNCATE":
            props.append("overflow-wrap: break-word")
            max_lines = getattr(node.text, "max_lines", None)
            props.append("overflow: hidden")
            if max_lines and max_lines > 1:
                props.append("display: -webkit-box")
                props.append("-webkit-box-orient: vertical")
                props.append(f"-webkit-line-clamp: {max_lines}")
            else:
                props.append("text-overflow: ellipsis")
                props.append("white-space: nowrap")
        elif text_auto_resize == "NONE":
            # Fixed text box: clip top/bottom only via clip-path so cross-
            # engine font-width differences don't truncate characters.
            # overflow:hidden is NOT used because it hard-clips horizontally.
            props.append("clip-path: inset(0 -9999px 0 -9999px)")
            if "\n" in text_content:
                props.append("overflow-wrap: break-word")
                props.append("white-space: pre-wrap")
            else:
                props.append("white-space: nowrap")
        else:
            # WIDTH_AND_HEIGHT or HEIGHT: Figma auto-sized this text box to
            # fit its content.  Use clip-path to clip the top/bottom edges
            # (preventing line-height from overlapping siblings) while leaving
            # left/right unclipped so cross-engine font-width differences
            # don't truncate visible characters (e.g. "100%" → "10").
            props.append("clip-path: inset(0 -9999px 0 -9999px)")
            if "\n" in text_content:
                props.append("overflow-wrap: break-word")
                props.append("white-space: pre-wrap")
            elif text_auto_resize == "WIDTH_AND_HEIGHT":
                props.append("white-space: nowrap")
        align_css = _text_align_css(node.text.text_align_horizontal)
        if align_css:
            props.append(align_css)

        para_indent = getattr(node.text, "paragraph_indent", 0.0) or 0.0
        if para_indent > 0:
            props.append(f"text-indent: {_px(para_indent)}")

        vert_align = node.text.text_align_vertical
        if vert_align in ("CENTER", "BOTTOM"):
            props.append("display: flex")
            props.append("flex-direction: column")
            vert_val = "center" if vert_align == "CENTER" else "flex-end"
            props.append(f"justify-content: {vert_val}")

        if not multi_segment and segments:
            seg = segments[0]
            seg_css = _text_segment_css(seg)
            for k, v in seg_css.items():
                props.append(f"{k}: {v}")
        elif not segments:
            # No segment info; only apply color from node-level fills (design-agnostic, no hardcoded font).
            for fill in node.style.fills:
                if fill.visible and fill.type == "SOLID" and fill.color:
                    props.append(f"color: {fill.color.to_css_rgba()}")
                    break

    # ── Image element ──
    img_src = ""
    if is_image:
        img_src = asset_map[node_id]
        if img_src.endswith(".svg"):
            props.append("object-fit: contain")
        else:
            props.append("object-fit: cover")
        props.append("display: block")

    # ── Write CSS rule ──
    css_block = ";\n  ".join(props)
    css_rules.append(f".{cls} {{\n  {css_block};\n}}")

    # Negative item_spacing: CSS gap doesn't support negative values, so emit
    # a sibling-margin rule that overlaps flex children by the negative amount.
    if use_flex and has_children and node.layout.item_spacing < 0:
        margin_prop = "margin-top" if flex_dir == "column" else "margin-left"
        css_rules.append(
            f".{cls} > * + * {{\n  {margin_prop}: {_px(node.layout.item_spacing)};\n}}"
        )

    # ── Write multi-segment span CSS ──
    span_classes: list[str] = []
    if multi_segment:
        for i, seg in enumerate(segments):
            span_cls = f"{cls}-seg-{i + 1}"
            span_classes.append(span_cls)
            seg_props = _text_segment_css(seg)
            seg_block = ";\n  ".join(f"{k}: {v}" for k, v in seg_props.items())
            css_rules.append(f".{span_cls} {{\n  {seg_block};\n}}")

    # ── Write HTML ──
    if tag == "img":
        # Use descriptive alt for real content images, empty alt for decorative
        alt_text = _escape_html(node.name) if bw > 100 and bh > 100 else ""
        html_lines.append(
            f'{indent}<img class="{cls}" data-node-id="{node_id}" '
            f'src="{img_src}" alt="{alt_text}" '
            f'width="{int(bw)}" height="{int(bh)}">'
        )
        return  # <img> is void — no children

    # Self-closing-ish: leaf node with no children and no text
    if not has_children and not is_text:
        html_lines.append(
            f'{indent}<{tag} class="{cls}" data-node-id="{node_id}"></{tag}>'
        )
        return

    # Text node
    para_spacing = 0.0
    if is_text and node.text:
        para_spacing = getattr(node.text, "paragraph_spacing", 0.0) or 0.0

    if is_text:
        if multi_segment:
            inner = ""
            for i, seg in enumerate(segments):
                escaped = _escape_html(seg.characters)
                inner += f'<span class="{span_classes[i]}">{escaped}</span>'
            html_lines.append(
                f'{indent}<{tag} class="{cls}" data-node-id="{node_id}">{inner}</{tag}>'
            )
        elif para_spacing > 0 and "\n" in text_content:
            paragraphs = text_content.split("\n")
            para_cls = f"{cls}-para"
            css_rules.append(
                f".{para_cls} {{\n  display: block;\n  margin-bottom: {_px(para_spacing)};\n}}"
            )
            css_rules.append(f".{para_cls}:last-child {{\n  margin-bottom: 0;\n}}")
            inner = ""
            for para in paragraphs:
                escaped = _escape_html(para)
                inner += f'<span class="{para_cls}">{escaped}</span>'
            html_lines.append(
                f'{indent}<{tag} class="{cls}" data-node-id="{node_id}">{inner}</{tag}>'
            )
        else:
            escaped = _escape_html(text_content)
            html_lines.append(
                f'{indent}<{tag} class="{cls}" data-node-id="{node_id}">{escaped}</{tag}>'
            )
        return

    # Container node with children
    html_lines.append(f'{indent}<{tag} class="{cls}" data-node-id="{node_id}">')
    for child in node.children:
        if child.visible:
            _generate_node(
                child,
                parent=node,
                asset_map=asset_map,
                layout_plan=layout_plan,
                namer=namer,
                html_lines=html_lines,
                css_rules=css_rules,
                depth=depth + 1,
                parent_is_flex=use_flex,
                bg_asset_map=bg_asset_map,
                text_size_rank=text_size_rank,
                root_bounds=root_bounds,
            )
    html_lines.append(f"{indent}</{tag}>")


def _escape_html(text: str) -> str:
    """Minimal HTML escaping for text content."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ────────────────────────── public API ───────────────────────────────


def generate_deterministic_html_css(
    root: DesignNode,
    asset_map: dict[str, str],
    layout_plan: LayoutPlan,
) -> tuple[str, str]:
    """Produce HTML body content and CSS from a DesignNode tree.

    Args:
        root: The root DesignNode (top-level Figma frame).
        asset_map: Mapping of node_id → relative image path (e.g. ``assets/img.png``).
        layout_plan: Layout decisions for container nodes.

    Returns:
        ``(html_body, css_text)`` ready to be written to files.
    """
    namer = _ClassNamer()
    html_lines: list[str] = []
    css_rules: list[str] = []

    # Build a sub-map of background image assets (keyed by "bg-<imageHash>")
    bg_asset_map = {k: v for k, v in asset_map.items() if k.startswith("bg-")}

    # Compute font-size percentiles for relative heading tag selection
    text_size_rank = _collect_text_font_sizes(root)

    _generate_node(
        node=root,
        parent=None,
        asset_map=asset_map,
        layout_plan=layout_plan,
        namer=namer,
        html_lines=html_lines,
        css_rules=css_rules,
        depth=0,
        parent_is_flex=False,
        bg_asset_map=bg_asset_map if bg_asset_map else None,
        text_size_rank=text_size_rank,
        root_bounds=root.bounds,
    )

    html_body = "\n".join(html_lines)
    css_text = "\n\n".join(css_rules)

    logger.info(
        "Deterministic generation complete: %d HTML lines, %d CSS rules",
        len(html_lines),
        len(css_rules),
    )
    return html_body, css_text
