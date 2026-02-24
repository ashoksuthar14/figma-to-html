"""Agent 3 - HTML/CSS Generator: Converts design spec + layout plan into code."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agents.base import BaseAgent
from config import settings
from schemas.design_spec import (
    AssetReference,
    DesignNode,
    DesignSpec,
)
from schemas.layout_plan import LayoutPlan
from services.openai_service import call_gpt4

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Fonts that are available on Google Fonts (common subset for fast lookup).
# If a font is NOT in this set, we map it to a visually similar alternative.
_GOOGLE_FONTS_COMMON: set[str] = {
    "ABeeZee", "Abel", "Abril Fatface", "Acme", "Alegreya", "Alegreya Sans",
    "Alfa Slab One", "Alice", "Amatic SC", "Amiri", "Anton", "Archivo",
    "Archivo Narrow", "Arimo", "Arvo", "Asap", "Assistant", "Barlow",
    "Barlow Condensed", "Bebas Neue", "Bitter", "Cairo", "Cabin", "Catamaran",
    "Chakra Petch", "Cinzel", "Comfortaa", "Cormorant Garamond", "Crimson Text",
    "DM Sans", "DM Serif Display", "Dancing Script", "Domine", "Dosis",
    "EB Garamond", "Exo 2", "Fira Sans", "Fjalla One", "Fredoka One",
    "Gelasio", "Gloria Hallelujah", "Gothic A1", "Great Vibes", "Heebo",
    "Hind", "IBM Plex Sans", "IBM Plex Serif", "Inconsolata", "Inter",
    "Josefin Sans", "Josefin Slab", "Jost", "Kanit", "Karla", "Kalam",
    "Lato", "Lexend", "Libre Baskerville", "Libre Franklin", "Lilita One",
    "Lobster", "Lora", "Lusitana", "Merriweather", "Merriweather Sans",
    "Montserrat", "Mukta", "Mulish", "Nanum Gothic", "Neuton", "Noto Sans",
    "Noto Serif", "Nunito", "Nunito Sans", "Open Sans", "Oswald", "Outfit",
    "Overpass", "Oxygen", "PT Sans", "PT Serif", "Pacifico", "Pathway Gothic One",
    "Playfair Display", "Plus Jakarta Sans", "Poppins", "Prompt", "Public Sans",
    "Quicksand", "Rajdhani", "Raleway", "Red Hat Display", "Roboto",
    "Roboto Condensed", "Roboto Mono", "Roboto Slab", "Rubik", "Sarabun",
    "Satisfy", "Signika", "Slabo 27px", "Source Code Pro", "Source Sans 3",
    "Source Sans Pro", "Source Serif Pro", "Space Grotesk", "Space Mono",
    "Spectral", "Syne", "Teko", "Tenor Sans", "Titillium Web", "Ubuntu",
    "Urbanist", "Varela Round", "Vollkorn", "Work Sans", "Yanone Kaffeesatz",
    "Zilla Slab",
}

# Mapping from unavailable Figma fonts → best available Google Fonts alternative.
# Keys are lowercased for case-insensitive matching.
_FONT_FALLBACK_MAP: dict[str, str] = {
    # Condensed / Gothic fonts
    "alternate gothic std": "Oswald",
    "alternate gothic": "Oswald",
    "alternate gothic no2": "Oswald",
    "alternate gothic no3": "Oswald",
    "alternate gothic atf": "Oswald",
    "alternate gothic condensed atf": "Barlow Condensed",
    "alternate gothic condensed": "Barlow Condensed",
    "franklin gothic": "Libre Franklin",
    "franklin gothic medium": "Libre Franklin",
    "franklin gothic book": "Libre Franklin",
    "itc franklin gothic": "Libre Franklin",
    "trade gothic": "Barlow Condensed",
    "trade gothic next": "Barlow Condensed",
    "news gothic": "Roboto Condensed",
    "news gothic std": "Roboto Condensed",
    # Humanist sans-serif
    "helvetica": "Inter",
    "helvetica neue": "Inter",
    "helvetica now": "Inter",
    "arial": "Inter",
    "sf pro": "Inter",
    "sf pro display": "Inter",
    "sf pro text": "Inter",
    "san francisco": "Inter",
    "segoe ui": "Inter",
    # Geometric sans-serif
    "futura": "Jost",
    "futura pt": "Jost",
    "futura std": "Jost",
    "avenir": "Nunito Sans",
    "avenir next": "Nunito Sans",
    "century gothic": "Raleway",
    "proxima nova": "Montserrat",
    "gotham": "Montserrat",
    "gotham rounded": "Nunito",
    "brandon grotesque": "Raleway",
    "museo sans": "Mulish",
    # Serif fonts
    "georgia": "Lora",
    "times": "Source Serif Pro",
    "times new roman": "Source Serif Pro",
    "garamond": "EB Garamond",
    "adobe garamond": "EB Garamond",
    "minion": "Source Serif Pro",
    "minion pro": "Source Serif Pro",
    "caslon": "Libre Baskerville",
    "baskerville": "Libre Baskerville",
    "palatino": "Spectral",
    # Slab serif
    "rockwell": "Roboto Slab",
    "courier new": "Roboto Mono",
    "courier": "Roboto Mono",
    # Display fonts
    "impact": "Anton",
    "gill sans": "Raleway",
    "gill sans mt": "Raleway",
    "din": "Teko",
    "din next": "Teko",
    "din pro": "Teko",
    "din condensed": "Barlow Condensed",
}


def _map_font(font_family: str) -> str:
    """Map a font family to a Google Fonts-available alternative if needed.

    Returns the original font if it's available on Google Fonts,
    or the best fallback alternative otherwise.
    """
    if not font_family:
        return "Inter"

    # Check if already available
    if font_family in _GOOGLE_FONTS_COMMON:
        return font_family

    # Check fallback map (case-insensitive)
    lower = font_family.lower().strip()
    if lower in _FONT_FALLBACK_MAP:
        return _FONT_FALLBACK_MAP[lower]

    # Partial match: try stripping common suffixes
    for suffix in (" std", " pro", " mt", " lt", " book", " medium",
                   " bold", " regular", " display", " text"):
        base = lower.replace(suffix, "").strip()
        if base in _FONT_FALLBACK_MAP:
            return _FONT_FALLBACK_MAP[base]

    # If the font name contains "gothic" or "condensed", use a condensed fallback
    if "gothic" in lower or "condensed" in lower:
        return "Roboto Condensed"
    if "mono" in lower or "code" in lower:
        return "Roboto Mono"
    if "serif" in lower:
        return "Source Serif Pro"
    if "slab" in lower:
        return "Roboto Slab"

    # Default: return as-is (browser will use its fallback)
    return font_family

# Patterns indicating GPT-4 abbreviated/truncated its output
_ABBREVIATION_PATTERNS = [
    r"/\*\s*Continue\s+with",
    r"/\*\s*\.\.\.\s*\*/",
    r"/\*\s*remaining\b",
    r"/\*\s*etc\.?\s*\*/",
    r"/\*\s*Add\s+more\b",
    r"/\*\s*Rest\s+of\b",
    r"/\*\s*Similar\s+styles?\b",
    r"/\*\s*Repeat\b",
    r"<!--\s*Continue\s+with",
    r"<!--\s*\.\.\.\s*-->",
    r"<!--\s*remaining\b",
    r"<!--\s*Add\s+more\b",
    r"<!--\s*Rest\s+of\b",
    r"<!--\s*Repeat\b",
    r"<!--\s*Similar\b",
]
_ABBREVIATION_RE = re.compile("|".join(_ABBREVIATION_PATTERNS), re.IGNORECASE)


@dataclass
class CompletenessReport:
    """Result of validating generated HTML/CSS against the design spec."""
    total_design_nodes: int
    html_element_count: int
    coverage_ratio: float
    has_abbreviation: bool
    abbreviation_matches: list[str]

    @property
    def is_complete(self) -> bool:
        return self.coverage_ratio >= 0.75 and not self.has_abbreviation


def _count_nodes(node: DesignNode) -> int:
    """Count total visible nodes in a design tree."""
    count = 1
    for child in node.children:
        if child.visible:
            count += _count_nodes(child)
    return count


def _detect_abbreviation(html: str, css: str) -> list[str]:
    """Scan HTML and CSS for abbreviation/truncation patterns."""
    combined = html + "\n" + css
    return [m.group(0) for m in _ABBREVIATION_RE.finditer(combined)]


def _validate_completeness(html: str, css: str, root: DesignNode) -> CompletenessReport:
    """Validate that generated code covers enough of the design nodes."""
    total_nodes = _count_nodes(root)
    # Count HTML elements (opening tags)
    html_elements = len(re.findall(r"<[a-zA-Z][^/>\s]*(?:\s[^>]*)?>", html))
    coverage = html_elements / max(total_nodes, 1)
    abbreviations = _detect_abbreviation(html, css)
    return CompletenessReport(
        total_design_nodes=total_nodes,
        html_element_count=html_elements,
        coverage_ratio=coverage,
        has_abbreviation=len(abbreviations) > 0,
        abbreviation_matches=abbreviations,
    )


def _partition_children(
    root: DesignNode,
    max_nodes_per_section: int,
) -> list[list[DesignNode]]:
    """Split root's direct visible children into groups within the token budget.

    Each group becomes one GPT-4 call.
    """
    visible_children = [c for c in root.children if c.visible]
    if not visible_children:
        return []

    sections: list[list[DesignNode]] = []
    current_section: list[DesignNode] = []
    current_count = 0

    for child in visible_children:
        child_node_count = _count_nodes(child)
        # If adding this child would exceed the budget, start a new section
        # (unless current section is empty — always include at least one child)
        if current_section and current_count + child_node_count > max_nodes_per_section:
            sections.append(current_section)
            current_section = [child]
            current_count = child_node_count
        else:
            current_section.append(child)
            current_count += child_node_count

    if current_section:
        sections.append(current_section)

    return sections


def _node_to_summary(
    node: DesignNode,
    layout_plan: LayoutPlan,
    depth: int = 0,
    asset_map: dict[str, str] | None = None,
) -> str:
    """Convert a DesignNode to a concise text summary for the GPT prompt."""
    indent = "  " * depth
    lines: list[str] = []

    decision = layout_plan.get_decision(node.id)
    layout_str = ""
    if decision:
        layout_str = f" [layout: {decision.strategy.value}"
        if decision.flex_direction:
            layout_str += f", direction: {decision.flex_direction}"
        if decision.gap:
            layout_str += f", gap: {decision.gap}"
        if decision.justify_content:
            layout_str += f", justify: {decision.justify_content}"
        if decision.align_items:
            layout_str += f", align: {decision.align_items}"
        if decision.grid_template_columns:
            layout_str += f", columns: {decision.grid_template_columns}"
        # Padding from Figma auto-layout
        if any(v > 0 for v in [node.layout.padding_top, node.layout.padding_right,
                                node.layout.padding_bottom, node.layout.padding_left]):
            layout_str += (f", padding: {node.layout.padding_top}px {node.layout.padding_right}px "
                           f"{node.layout.padding_bottom}px {node.layout.padding_left}px")
        # Sizing modes
        if node.layout.primary_axis_sizing != "AUTO":
            layout_str += f", primarySizing: {node.layout.primary_axis_sizing}"
        if node.layout.counter_axis_sizing != "AUTO":
            layout_str += f", counterSizing: {node.layout.counter_axis_sizing}"
        # Wrap
        if node.layout.layout_wrap == "WRAP":
            layout_str += ", wrap: wrap"
        layout_str += "]"

    bounds = node.bounds
    style_parts: list[str] = []

    # Image asset reference
    has_image = False
    if asset_map and node.id in asset_map:
        style_parts.append(f"image_url: {asset_map[node.id]}")
        has_image = True

    # Background fills
    for fill in node.style.fills:
        if fill.visible and fill.type == "IMAGE":
            if not has_image and fill.image_ref and asset_map:
                # Try to find asset by image_ref
                for nid, url in asset_map.items():
                    if fill.image_ref in url:
                        style_parts.append(f"image_url: {url}")
                        has_image = True
                        break
            if not has_image:
                style_parts.append("image_fill: true (needs <img> or background-image)")
        elif fill.visible and fill.type == "SOLID" and fill.color:
            style_parts.append(f"bg: {fill.color.to_css_rgba()}")
        elif fill.visible and fill.type.startswith("GRADIENT_"):
            # Build gradient CSS hint from stops
            if fill.gradient_stops:
                stops = ", ".join(
                    f"{s.color.to_css_rgba() if s.color else '#000'} {s.position * 100:.0f}%"
                    for s in fill.gradient_stops
                )
                if fill.type == "GRADIENT_LINEAR":
                    angle = fill.gradient_angle_deg()
                    angle_str = f"{angle}deg, " if angle is not None else ""
                    style_parts.append(f"bg: linear-gradient({angle_str}{stops})")
                elif fill.type == "GRADIENT_RADIAL":
                    style_parts.append(f"bg: radial-gradient({stops})")
                else:
                    style_parts.append(f"bg: gradient({stops})")
            else:
                style_parts.append(f"bg: gradient")

    # Border / stroke
    for stroke in node.style.strokes:
        if stroke.visible:
            style_parts.append(
                f"border: {stroke.weight}px {stroke.color.to_css_rgba()}"
            )

    # Corner radius
    if node.style.corner_radius:
        cr = node.style.corner_radius
        if not cr.is_uniform or cr.top_left > 0:
            style_parts.append(f"radius: {cr.to_css()}")

    # Opacity
    if node.style.opacity < 1.0:
        style_parts.append(f"opacity: {node.style.opacity}")

    # Rotation
    if node.style.rotation and node.style.rotation != 0:
        style_parts.append(f"rotation: {node.style.rotation}deg")

    # Effects (shadows, blur)
    for eff in node.style.effects:
        if eff.visible:
            if eff.type in ("DROP_SHADOW", "INNER_SHADOW"):
                ox = eff.offset.get("x", 0) if eff.offset else 0
                oy = eff.offset.get("y", 0) if eff.offset else 0
                blur = eff.radius
                spread = eff.spread
                color_str = eff.color.to_css_rgba() if eff.color else "rgba(0,0,0,0.25)"
                inset = "inset " if eff.type == "INNER_SHADOW" else ""
                style_parts.append(
                    f"shadow: {inset}{ox}px {oy}px {blur}px {spread}px {color_str}"
                )
            elif "BLUR" in eff.type:
                style_parts.append(f"blur: {eff.radius}px")

    # Overflow
    if node.style.overflow != "VISIBLE":
        style_parts.append(f"overflow: {node.style.overflow.lower()}")

    style_str = f" ({', '.join(style_parts)})" if style_parts else ""

    # Text content
    text_str = ""
    if node.text and node.text.characters:
        chars = node.text.characters[:80]
        if len(node.text.characters) > 80:
            chars += "..."
        text_str = f' text="{chars}"'
        # Text alignment
        if node.text.text_align_horizontal and node.text.text_align_horizontal != "LEFT":
            text_str += f" textAlign={node.text.text_align_horizontal.lower()}"
        if node.text.segments:
            if len(node.text.segments) == 1:
                # Single segment — compact format with full properties
                seg = node.text.segments[0]
                text_str += f" font={_map_font(seg.font_family)}/{seg.font_weight}/{seg.font_size}px"
                if seg.fill and seg.fill.color:
                    text_str += f" color={seg.fill.color.to_css_rgba()}"
                if seg.line_height is not None:
                    text_str += f" lineHeight={seg.line_height}px"
                if seg.letter_spacing and seg.letter_spacing != 0:
                    text_str += f" letterSpacing={seg.letter_spacing}px"
                if seg.text_decoration and seg.text_decoration != "NONE":
                    text_str += f" textDecoration={seg.text_decoration.lower()}"
                if seg.text_transform and seg.text_transform not in ("NONE", "ORIGINAL"):
                    text_str += f" textCase={seg.text_transform.lower()}"
            else:
                # Multiple segments — list each segment's style with full properties
                seg_parts: list[str] = []
                for seg in node.text.segments:
                    seg_desc = f'"{seg.characters}" font={_map_font(seg.font_family)}/{seg.font_weight}/{seg.font_size}px'
                    if seg.fill and seg.fill.color:
                        seg_desc += f" color={seg.fill.color.to_css_rgba()}"
                    if seg.line_height is not None:
                        seg_desc += f" lineHeight={seg.line_height}px"
                    if seg.letter_spacing and seg.letter_spacing != 0:
                        seg_desc += f" letterSpacing={seg.letter_spacing}px"
                    if seg.text_decoration and seg.text_decoration != "NONE":
                        seg_desc += f" textDecoration={seg.text_decoration.lower()}"
                    if seg.text_transform and seg.text_transform not in ("NONE", "ORIGINAL"):
                        seg_desc += f" textCase={seg.text_transform.lower()}"
                    seg_parts.append(seg_desc)
                text_str += f" segments=[{', '.join(seg_parts)}]"

    lines.append(
        f"{indent}<{node.type} id=\"{node.id}\" name=\"{node.name}\""
        f" x={bounds.x} y={bounds.y} w={bounds.width} h={bounds.height}"
        f"{layout_str}{style_str}{text_str}>"
    )

    for child in node.children:
        if child.visible:
            lines.append(_node_to_summary(child, layout_plan, depth + 1, asset_map))

    lines.append(f"{indent}</{node.type}>")

    return "\n".join(lines)


def _find_node_by_id(root: DesignNode, node_id: str) -> DesignNode | None:
    """Find a node in the tree by its ID."""
    if root.id == node_id:
        return root
    for child in root.children:
        found = _find_node_by_id(child, node_id)
        if found:
            return found
    return None


def _is_css_renderable_asset(
    asset: "AssetReference",
    root: DesignNode,
) -> bool:
    """Check if an asset should be rendered as CSS instead of <img>.

    Always returns False so all assets are included in the asset map and
    rendered as <img> tags (no filtering).
    """
    return False


def _build_font_list(spec: DesignSpec) -> list[str]:
    """Extract the list of fonts used in the design, mapped to web-available alternatives."""
    raw_fonts = set(spec.fonts_used)

    def _collect_fonts(node: DesignNode) -> None:
        if node.text:
            for seg in node.text.segments:
                raw_fonts.add(seg.font_family)
        for child in node.children:
            _collect_fonts(child)

    _collect_fonts(spec.root)

    # Map each font to a Google Fonts-available alternative
    mapped: set[str] = set()
    for font in raw_fonts:
        if font:
            mapped.add(_map_font(font))
    return sorted(mapped)


def _extract_html_css(response: str) -> tuple[str, str]:
    """Parse GPT-4 response to extract HTML and CSS blocks.

    Handles various formats:
    - ```html ... ``` and ```css ... ``` code blocks
    - HTML and CSS in a single response
    - Raw HTML/CSS without code fences
    """
    html_content = ""
    css_content = ""

    # Try to find ```html ... ``` block
    html_match = re.search(
        r"```html\s*\n(.*?)```",
        response,
        re.DOTALL,
    )
    if html_match:
        html_content = html_match.group(1).strip()

    # Try to find ```css ... ``` block
    css_match = re.search(
        r"```css\s*\n(.*?)```",
        response,
        re.DOTALL,
    )
    if css_match:
        css_content = css_match.group(1).strip()

    # Strip stray language tags that GPT-4 sometimes includes inside code blocks
    if html_content:
        html_content = re.sub(r"^\s*html\s*\n", "", html_content)
    if css_content:
        css_content = re.sub(r"^\s*css\s*\n", "", css_content)

    # If no HTML found, try to find HTML between body tags or any HTML
    if not html_content:
        body_match = re.search(
            r"<body[^>]*>(.*?)</body>",
            response,
            re.DOTALL | re.IGNORECASE,
        )
        if body_match:
            html_content = body_match.group(1).strip()
        else:
            # Look for any HTML-like content
            html_tag_match = re.search(
                r"(<div[^>]*>.*</div>)",
                response,
                re.DOTALL,
            )
            if html_tag_match:
                html_content = html_tag_match.group(1).strip()

    # If no CSS found, try to extract from <style> tags
    if not css_content:
        style_match = re.search(
            r"<style[^>]*>(.*?)</style>",
            response,
            re.DOTALL | re.IGNORECASE,
        )
        if style_match:
            css_content = style_match.group(1).strip()

    return html_content, css_content


def _post_process_html(html: str) -> str:
    """Post-process generated HTML for correctness."""
    # Ensure no duplicate IDs (common GPT mistake)
    # Remove any DOCTYPE/html/head/body wrappers that GPT might add
    html = re.sub(r"<!DOCTYPE[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"</?html[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<head>.*?</head>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"</?body[^>]*>", "", html, flags=re.IGNORECASE)
    return html.strip()


def _post_process_css(css: str) -> str:
    """Post-process generated CSS to ensure pixel accuracy."""
    # Inject box-sizing reset if not present
    reset = "*, *::before, *::after { box-sizing: border-box; }"
    if "box-sizing" not in css:
        css = reset + "\n\n" + css

    return css.strip()


class CodeGeneratorAgent(BaseAgent):
    """Generates HTML + CSS code from the design spec and layout plan."""

    async def execute(
        self,
        design_spec: DesignSpec,
        layout_plan: LayoutPlan,
        base_url: str = "",
        figma_screenshot: Optional[bytes] = None,
    ) -> dict[str, str]:
        """Generate HTML and CSS from the design specification.

        For large designs (> CHUNK_NODE_THRESHOLD nodes), uses chunked generation
        to avoid GPT-4 output truncation.

        Args:
            design_spec: The parsed Figma design specification.
            layout_plan: The layout strategy decisions.
            base_url: Base URL for constructing asset URLs.
            figma_screenshot: Optional Figma screenshot for vision-based generation.

        Returns:
            Dict with 'html', 'css', and 'completeness' keys.
        """
        agent_start = time.monotonic()
        logger.info("[job:%s] Code generation started", self.job_id)
        await self.report_progress("Building code generation prompt")

        # Build asset map: node_id → URL (filter out small CSS-renderable shapes)
        asset_map: dict[str, str] = {}
        for asset in design_spec.assets:
            if _is_css_renderable_asset(asset, design_spec.root):
                logger.debug("[job:%s] Skipping CSS-renderable asset: %s", self.job_id, asset.node_id)
                continue
            url = asset.url or f"assets/{asset.filename}"
            asset_map[asset.node_id] = url

        # Count nodes to decide strategy
        total_nodes = _count_nodes(design_spec.root)
        threshold = settings.CHUNK_NODE_THRESHOLD

        if total_nodes > threshold:
            logger.info(
                "[job:%s] Large design detected (%d nodes > %d threshold), using chunked generation",
                self.job_id, total_nodes, threshold,
            )
            await self.report_progress(
                f"Large design ({total_nodes} nodes), using chunked generation"
            )
            result = await self._execute_chunked(
                design_spec, layout_plan, asset_map, figma_screenshot,
            )
        else:
            result = await self._execute_single(
                design_spec, layout_plan, asset_map, figma_screenshot,
            )

        # Validate completeness
        completeness = _validate_completeness(
            result["html"], result["css"], design_spec.root,
        )
        self.completeness = completeness

        if completeness.has_abbreviation:
            logger.warning(
                "[job:%s] Abbreviation detected in output: %s",
                self.job_id, completeness.abbreviation_matches[:3],
            )
        logger.info(
            "[job:%s] Completeness: %d HTML elements / %d design nodes (%.0f%%), abbreviations=%s",
            self.job_id, completeness.html_element_count, completeness.total_design_nodes,
            completeness.coverage_ratio * 100, completeness.has_abbreviation,
        )

        logger.info("[job:%s] Code generation complete in %.2fs",
                     self.job_id, time.monotonic() - agent_start)
        await self.report_progress(
            "Code generation complete",
            {
                "html_length": len(result["html"]),
                "css_length": len(result["css"]),
                "coverage_ratio": completeness.coverage_ratio,
                "has_abbreviation": completeness.has_abbreviation,
            },
        )

        return result

    async def _execute_single(
        self,
        design_spec: DesignSpec,
        layout_plan: LayoutPlan,
        asset_map: dict[str, str],
        figma_screenshot: Optional[bytes] = None,
    ) -> dict[str, str]:
        """Generate code in a single GPT-4 call (original approach)."""
        prompt_path = PROMPTS_DIR / "code_generation.txt"
        system_prompt = prompt_path.read_text(encoding="utf-8")

        user_prompt = self._build_user_prompt(
            design_spec, layout_plan, asset_map,
            has_vision=figma_screenshot is not None,
        )

        await self.report_progress("Calling GPT-4 for code generation")

        images: list[bytes] | None = None
        if figma_screenshot:
            images = [figma_screenshot]
            logger.info("[job:%s] Including Figma screenshot (%d bytes) in GPT-4 vision call",
                        self.job_id, len(figma_screenshot))

        gpt_start = time.monotonic()
        gpt_response = await call_gpt4(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            images=images,
            temperature=0.1,
            max_tokens=16384,
        )
        logger.info("[job:%s] GPT-4 response received (%d chars, finish_reason=%s) in %.2fs",
                     self.job_id, len(gpt_response.content), gpt_response.finish_reason,
                     time.monotonic() - gpt_start)

        if gpt_response.was_truncated:
            logger.warning("[job:%s] Single-call response was TRUNCATED", self.job_id)

        await self.report_progress("Parsing GPT-4 response")

        html_content, css_content = _extract_html_css(gpt_response.content)

        if not html_content:
            logger.error("No HTML content extracted from GPT response")
            raise RuntimeError("GPT-4 did not generate valid HTML content")

        html_content = _post_process_html(html_content)
        css_content = _post_process_css(css_content)
        logger.info("[job:%s] Code extraction: html=%d chars, css=%d chars",
                     self.job_id, len(html_content), len(css_content))

        return {"html": html_content, "css": css_content}

    async def _execute_chunked(
        self,
        design_spec: DesignSpec,
        layout_plan: LayoutPlan,
        asset_map: dict[str, str],
        figma_screenshot: Optional[bytes] = None,
    ) -> dict[str, str]:
        """Generate code in multiple GPT-4 calls for large designs.

        Phase 1: Generate skeleton (root container + section placeholders)
        Phase 2: Generate each section's HTML+CSS in parallel
        Phase 3: Merge sections into the skeleton
        """
        root = design_spec.root
        max_per_section = settings.CHUNK_MAX_NODES_PER_SECTION
        max_concurrent = settings.CHUNK_MAX_CONCURRENT

        sections = _partition_children(root, max_per_section)
        logger.info("[job:%s] Partitioned into %d sections", self.job_id, len(sections))
        await self.report_progress(f"Split into {len(sections)} sections for chunked generation")

        prompt_path = PROMPTS_DIR / "code_generation.txt"
        system_prompt = prompt_path.read_text(encoding="utf-8")

        # --- Phase 1: Generate skeleton (deterministic, no GPT-4 call) ---
        await self.report_progress("Phase 1: Generating page skeleton")
        skeleton_html, skeleton_css = self._generate_skeleton(
            design_spec, sections,
        )

        # --- Phase 2: Generate sections in parallel ---
        await self.report_progress("Phase 2: Generating sections")
        semaphore = asyncio.Semaphore(max_concurrent)
        section_results: list[tuple[str, str]] = [("", "")] * len(sections)

        async def _gen_section(idx: int, section_nodes: list[DesignNode]) -> None:
            async with semaphore:
                await self.report_progress(f"Generating section {idx + 1}/{len(sections)}")
                html, css = await self._generate_section(
                    idx, section_nodes, design_spec, layout_plan,
                    asset_map, system_prompt,
                )
                section_results[idx] = (html, css)

        tasks = [
            _gen_section(i, section_nodes)
            for i, section_nodes in enumerate(sections)
        ]
        await asyncio.gather(*tasks)

        # --- Phase 3: Merge ---
        await self.report_progress("Phase 3: Merging sections")
        merged_html = skeleton_html
        all_css_parts = [skeleton_css]

        # Strip box-sizing resets from individual sections (will be added once at the end)
        _box_sizing_re = re.compile(
            r"\*\s*,\s*\*::before\s*,\s*\*::after\s*\{\s*box-sizing\s*:\s*border-box\s*;\s*\}\s*",
        )

        for i, (section_html, section_css) in enumerate(section_results):
            placeholder = f"<!-- SECTION {i} CONTENT -->"
            if placeholder in merged_html:
                merged_html = merged_html.replace(placeholder, section_html)
            else:
                # Fallback: append before the closing root div
                logger.warning("[job:%s] Placeholder for section %d not found, appending", self.job_id, i)
                close_tag = merged_html.rfind("</div>")
                if close_tag != -1:
                    merged_html = merged_html[:close_tag] + section_html + "\n" + merged_html[close_tag:]
                else:
                    merged_html += f"\n{section_html}"
            if section_css.strip():
                # Remove duplicate box-sizing resets that GPT-4 may have added
                cleaned_css = _box_sizing_re.sub("", section_css).strip()
                if cleaned_css:
                    all_css_parts.append(f"/* --- Section {i + 1} --- */\n{cleaned_css}")

        merged_css = "\n\n".join(all_css_parts)

        merged_html = _post_process_html(merged_html)
        merged_css = _post_process_css(merged_css)

        logger.info("[job:%s] Chunked generation merged: html=%d chars, css=%d chars",
                     self.job_id, len(merged_html), len(merged_css))

        return {"html": merged_html, "css": merged_css}

    def _generate_skeleton(
        self,
        spec: DesignSpec,
        sections: list[list[DesignNode]],
    ) -> tuple[str, str]:
        """Generate the root container skeleton deterministically (no GPT-4 call).

        Produces a single root div with position: relative and section placeholder
        comments placed directly inside it — NO wrapper divs. This avoids broken
        positioning contexts that caused overlapping sections.
        """
        root = spec.root
        width = root.bounds.width
        height = root.bounds.height

        # Derive root class name from Figma node name
        root_class = re.sub(r"[^a-zA-Z0-9-]", "-", root.name.lower()).strip("-")
        if not root_class:
            root_class = "root-frame"

        # Build root background CSS property
        root_bg_str = ""
        for fill in root.style.fills:
            if fill.visible and fill.type == "SOLID" and fill.color:
                root_bg_str = f"  background-color: {fill.color.to_css_rgba()};\n"
                break
            elif fill.visible and fill.type.startswith("GRADIENT_") and fill.gradient_stops:
                stops = ", ".join(
                    f"{s.color.to_css_rgba() if s.color else '#000'} {s.position * 100:.0f}%"
                    for s in fill.gradient_stops
                )
                if fill.type == "GRADIENT_LINEAR":
                    angle = fill.gradient_angle_deg()
                    angle_str = f"{angle}deg, " if angle is not None else ""
                    root_bg_str = f"  background: linear-gradient({angle_str}{stops});\n"
                elif fill.type == "GRADIENT_RADIAL":
                    root_bg_str = f"  background: radial-gradient({stops});\n"
                break

        # Build HTML: root container with section placeholders directly inside (no wrappers)
        placeholders = "\n".join(
            f"  <!-- SECTION {i} CONTENT -->"
            for i in range(len(sections))
        )
        html = f'<div class="{root_class}">\n{placeholders}\n</div>'

        # Build CSS: just the root container styles
        # Use fixed height + overflow: hidden to constrain page to exact frame size.
        # Default to white background if no fill is specified (RC1 + RC4).
        if not root_bg_str:
            root_bg_str = "  background-color: #ffffff;\n"
        css = (
            f".{root_class} {{\n"
            f"  position: relative;\n"
            f"  width: {width}px;\n"
            f"  height: {height}px;\n"
            f"  overflow: hidden;\n"
            f"{root_bg_str}"
            f"}}"
        )

        logger.info(
            "[job:%s] Deterministic skeleton: class=%s, %d sections, %dx%d",
            self.job_id, root_class, len(sections), width, height,
        )

        return html, css

    async def _generate_section(
        self,
        section_idx: int,
        section_nodes: list[DesignNode],
        spec: DesignSpec,
        plan: LayoutPlan,
        asset_map: dict[str, str],
        system_prompt: str,
    ) -> tuple[str, str]:
        """Generate HTML+CSS for a single section of the design."""
        root = spec.root

        # Build tree summaries for this section's nodes only
        section_trees = []
        for node in section_nodes:
            section_trees.append(_node_to_summary(node, plan, depth=0, asset_map=asset_map))
        tree_text = "\n\n".join(section_trees)

        # Section-specific assets
        section_asset_str = ""
        section_node_ids = set()
        for node in section_nodes:
            section_node_ids.add(node.id)
            for desc in node.get_all_descendants():
                section_node_ids.add(desc.id)

        section_assets = {
            nid: url for nid, url in asset_map.items()
            if nid in section_node_ids
        }
        if section_assets:
            asset_lines = [
                f'  - node "{nid}" → <img src="{url}" alt="..." class="...">'
                for nid, url in section_assets.items()
            ]
            section_asset_str = (
                "\n## Available Image Assets\n"
                + "\n".join(asset_lines)
            )

        # Layout decisions for this section
        section_layout_parts = []
        for nid in section_node_ids:
            decision = plan.get_decision(nid)
            if decision:
                section_layout_parts.append(
                    f"  {nid}: {decision.strategy.value}"
                    + (f" ({decision.flex_direction})" if decision.flex_direction else "")
                )
        layout_text = "\n".join(section_layout_parts) if section_layout_parts else "  (use layout from node tree)"

        node_count = sum(_count_nodes(n) for n in section_nodes)

        section_prompt = f"""Generate HTML and CSS for Section {section_idx + 1} of a large Figma design.
This section contains {node_count} nodes. Generate ALL of them — do not skip or abbreviate any.

## Positioning Context
The parent frame is {root.bounds.width}px × {root.bounds.height}px with `position: relative`.
Your elements will be placed DIRECTLY inside this root container (no section wrapper div).
All x/y coordinates in the design spec are FULL-FRAME coordinates (relative to the root frame origin 0,0).

Use `position: absolute` with `left` and `top` matching the x/y values from the spec.
Do NOT create any wrapper div for the section — output bare elements only.
{section_asset_str}

## Layout Decisions
{layout_text}

## Design Nodes for This Section
{tree_text}

## CRITICAL RULES
1. Generate HTML and CSS for ALL {node_count} nodes listed above. Every single one.
2. Do NOT abbreviate, truncate, or skip any nodes.
3. Do NOT write comments like "Continue with..." or "remaining elements..." or "etc."
4. Do NOT use "..." or placeholder comments for ungenerated content.
5. Use EXACT pixel values from the design spec — x/y are full-frame absolute coordinates.
6. CRITICAL: Every top-level element in your HTML output MUST have position: absolute in its CSS class. Elements without position: absolute will break the layout. Do NOT wrap elements in container divs — output flat, absolutely-positioned elements only.
7. Each top-level element MUST use `position: absolute; left: <x>px; top: <y>px; width: <w>px; height: <h>px`.
8. Generate class-based CSS, no inline styles.
9. Include ALL text content, colors, borders, shadows, border-radius values.
10. For nodes with image_url, use <img src="URL"> with width/height matching the node bounds. Style with object-fit: cover.
11. For RECTANGLE/ELLIPSE nodes with solid-color fills and NO image_url, use a <div> with background-color.

Output:

```html
(section HTML content — no outer wrapper, just the elements directly)
```

```css
(section CSS — all styles for these elements)
```
"""
        gpt_start = time.monotonic()
        gpt_response = await call_gpt4(
            system_prompt=system_prompt,
            user_prompt=section_prompt,
            temperature=0.1,
            max_tokens=16384,
        )
        logger.info(
            "[job:%s] Section %d: %d chars, finish_reason=%s, in %.2fs",
            self.job_id, section_idx, len(gpt_response.content),
            gpt_response.finish_reason, time.monotonic() - gpt_start,
        )

        if gpt_response.was_truncated:
            logger.warning("[job:%s] Section %d was TRUNCATED", self.job_id, section_idx)

        html, css = _extract_html_css(gpt_response.content)
        if html:
            html = _post_process_html(html)
        return html, css

    def _build_user_prompt(
        self,
        spec: DesignSpec,
        plan: LayoutPlan,
        asset_map: dict[str, str] | None = None,
        has_vision: bool = False,
    ) -> str:
        """Build the detailed user prompt for code generation."""
        # Frame dimensions
        root = spec.root
        width = root.bounds.width
        height = root.bounds.height

        # Extract root frame background for emphasis
        root_bg_str = ""
        for fill in root.style.fills:
            if fill.visible and fill.type == "SOLID" and fill.color:
                root_bg_str = f"background-color: {fill.color.to_css_rgba()}"
                break
            elif fill.visible and fill.type.startswith("GRADIENT_") and fill.gradient_stops:
                stops = ", ".join(
                    f"{s.color.to_css_rgba() if s.color else '#000'} {s.position * 100:.0f}%"
                    for s in fill.gradient_stops
                )
                if fill.type == "GRADIENT_LINEAR":
                    angle = fill.gradient_angle_deg()
                    angle_str = f"{angle}deg, " if angle is not None else ""
                    root_bg_str = f"background: linear-gradient({angle_str}{stops})"
                elif fill.type == "GRADIENT_RADIAL":
                    root_bg_str = f"background: radial-gradient({stops})"
                break

        # Node tree summary
        tree_summary = _node_to_summary(root, plan, asset_map=asset_map)

        # Font list
        fonts = _build_font_list(spec)
        fonts_str = ", ".join(fonts) if fonts else "Inter (system default)"

        # Color palette
        colors_str = ""
        if spec.color_palette:
            color_list = [c.to_css_hex() for c in spec.color_palette[:20]]
            colors_str = f"\nColor palette used: {', '.join(color_list)}"

        # Layout decisions summary
        layout_summary_parts: list[str] = []
        for node_id, decision in plan.decisions.items():
            layout_summary_parts.append(
                f"  {node_id}: {decision.strategy.value}"
                + (f" ({decision.flex_direction})" if decision.flex_direction else "")
                + (f" - {decision.notes}" if decision.notes else "")
            )
        layout_summary = "\n".join(layout_summary_parts)

        # Asset list — distinguish real images from decorative shapes
        asset_str = ""
        if asset_map:
            asset_lines = [
                f"  - node \"{nid}\" → <img src=\"{url}\" alt=\"...\" class=\"...\">"
                for nid, url in asset_map.items()
            ]
            asset_str = (
                "\n## Available Image Assets\n"
                "These are REAL images (photos, illustrations, icons) that MUST use <img> tags.\n"
                "Decorative shapes (solid-color rectangles/ellipses) are NOT listed here — render those as <div> with CSS.\n"
                + "\n".join(asset_lines)
            )

        # Vision reference section
        vision_str = ""
        if has_vision:
            vision_str = """
## Visual Reference
An image of the Figma design is attached. Match the visual appearance EXACTLY.
Use both the image AND the numeric data below for pixel-perfect output.
"""

        # Root background emphasis
        root_bg_section = ""
        if root_bg_str:
            root_bg_section = f"""
CRITICAL: The root frame background MUST be: {root_bg_str};
Apply this to the outermost container element.
"""

        prompt = f"""Generate pixel-perfect HTML and CSS for the following Figma design.
{vision_str}{root_bg_section}
## Frame Dimensions
Width: {width}px, Height: {height}px

## Fonts Used
{fonts_str}
{colors_str}
{asset_str}

## Layout Decisions
{layout_summary}

## Design Node Tree
{tree_summary}

## MANDATORY (must be followed exactly)
1. Use EXACT pixel values from the design spec for ALL positioning, sizing, spacing, font-size, line-height, letter-spacing.
2. Follow the layout decisions above (flex/grid/absolute/block) for each container.
3. Set explicit width and height on every non-text element matching the w and h values.
4. Reproduce ALL colors, gradients, backgrounds — especially the root frame background.
5. Include ALL borders, shadows, rounded corners, opacity values, rotations.
6. For nodes with image_url, use <img src="URL"> with width/height matching the node bounds. Style with object-fit: cover.
7. For RECTANGLE/ELLIPSE nodes with solid-color fills and NO image_url, use a <div> with background-color. NEVER use <img>.
8. Set padding on every container where padding is specified in the layout bracket.

## IMPORTANT (follow unless conflicting with MANDATORY)
9. Use semantic HTML elements where appropriate (section, nav, header, main, footer, h1-h6, p, span, etc.).
10. Generate clean, class-based CSS (no inline styles). Derive class names from node names (kebab-case).
11. Include all text content exactly as specified, with correct font-family, weight, size, color, line-height, letter-spacing.
12. For nodes marked image_fill without a URL, use a placeholder via https://placehold.co/WIDTHxHEIGHT/png.

## BEST PRACTICES
13. Use box-sizing: border-box on all elements (this is already applied by the CSS reset).
14. Group related CSS properties logically.
15. Use descriptive class names based on node names.

Output your response with two code blocks:

```html
(your HTML here - only the body content, no DOCTYPE/html/head/body wrapper)
```

```css
(your CSS here - all styles needed)
```
"""
        return prompt
