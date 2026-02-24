"""Agent 5 - Auto-Fixer: Iteratively fixes CSS based on visual diff reports."""

from __future__ import annotations

import io
import logging
import re
import time
from pathlib import Path
from typing import Optional

from PIL import Image

from agents.base import BaseAgent
from config import settings
from schemas.diff_report import DiffReport
from services.diff_service import get_region_suspect_selectors
from services.openai_service import call_gpt4

_VISION_MAX_DIM = 2048


def _downscale_for_vision(img_bytes: bytes, max_dim: int = _VISION_MAX_DIM) -> bytes:
    """Downscale an image so its longest side is at most *max_dim* pixels.

    GPT-4 Vision resizes internally anyway; sending oversized payloads risks
    hitting OpenAI's request-size limit and wasting bandwidth.
    """
    img = Image.open(io.BytesIO(img_bytes))
    w, h = img.size
    if max(w, h) <= max_dim:
        return img_bytes
    scale = max_dim / max(w, h)
    new_w, new_h = int(w * scale), int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    logger.debug("Downscaled vision image from %dx%d to %dx%d", w, h, new_w, new_h)
    return buf.getvalue()

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _extract_css_from_response(response: str) -> Optional[str]:
    """Extract CSS from the GPT-4 fixer response."""
    # Try ```css ... ``` block first
    css_match = re.search(
        r"```css\s*\n(.*?)```",
        response,
        re.DOTALL,
    )
    if css_match:
        content = css_match.group(1).strip()
        # Strip leading "css" language tag GPT-4 sometimes includes inside the block
        content = re.sub(r"^\s*css\s*\n", "", content)
        return content

    # Try any code block
    code_match = re.search(
        r"```\s*\n(.*?)```",
        response,
        re.DOTALL,
    )
    if code_match:
        content = code_match.group(1).strip()
        content = re.sub(r"^\s*css\s*\n", "", content)
        # Verify it looks like CSS
        if "{" in content and "}" in content:
            return content

    # Try to find CSS-like content directly
    if "{" in response and "}" in response:
        # Find the first CSS rule
        first_rule = re.search(r"[.#\w][^{]*\{[^}]*\}", response)
        if first_rule:
            # Extract from first rule to last closing brace
            start = first_rule.start()
            # Find the last closing brace
            last_brace = response.rfind("}")
            if last_brace >= start:
                content = response[start : last_brace + 1].strip()
                content = re.sub(r"^\s*css\s*\n", "", content)
                return content

    return None


def _parse_css_rules(css_text: str) -> dict[str, str]:
    """Parse CSS text into a dict of selector → full rule (selector + block).

    Handles nested media queries by flattening them.
    Returns {selector: "selector { ... }"} for each rule.
    """
    rules: dict[str, str] = {}

    # Remove comments
    cleaned = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)

    # Match top-level rules: selector { properties }
    # This regex handles nested braces (one level deep for things like @media)
    pos = 0
    while pos < len(cleaned):
        # Skip whitespace
        while pos < len(cleaned) and cleaned[pos] in " \t\n\r":
            pos += 1
        if pos >= len(cleaned):
            break

        # Find the opening brace
        brace_start = cleaned.find("{", pos)
        if brace_start == -1:
            break

        selector = cleaned[pos:brace_start].strip()
        if not selector:
            pos = brace_start + 1
            continue

        # Find matching closing brace (handle one level of nesting)
        depth = 1
        i = brace_start + 1
        while i < len(cleaned) and depth > 0:
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
            i += 1

        block = cleaned[brace_start:i]
        full_rule = f"{selector} {block}"
        rules[selector] = full_rule
        pos = i

    return rules


def _parse_css_properties(rule_text: str) -> dict[str, str]:
    """Parse the properties inside a CSS rule block into a dict.

    Given 'selector { prop1: val1; prop2: val2; }', returns
    {'prop1': 'val1', 'prop2': 'val2'}.
    """
    # Extract the block content between { and }
    match = re.search(r"\{(.*)\}", rule_text, re.DOTALL)
    if not match:
        return {}
    block = match.group(1)
    props: dict[str, str] = {}
    for decl in block.split(";"):
        decl = decl.strip()
        if ":" in decl:
            prop, _, val = decl.partition(":")
            prop = prop.strip()
            val = val.strip()
            if prop and val:
                props[prop] = val
    return props


def _rebuild_rule(selector: str, properties: dict[str, str]) -> str:
    """Rebuild a CSS rule string from selector and property dict."""
    if not properties:
        return f"{selector} {{}}"
    prop_lines = ";\n  ".join(f"{k}: {v}" for k, v in properties.items())
    return f"{selector} {{\n  {prop_lines};\n}}"


def _get_root_selector_and_background(original_css: str) -> Optional[tuple[str, dict[str, str]]]:
    """Find the root container rule (first rule with position:relative + overflow:hidden) and its background props."""
    original_rules = _parse_css_rules(original_css)
    for selector, rule in original_rules.items():
        props = _parse_css_properties(rule)
        if props.get("position") == "relative" and "overflow" in props:
            # Root container — preserve background so fixer cannot flip it to black
            keep = {}
            if "background-color" in props:
                keep["background-color"] = props["background-color"]
            if "background" in props:
                keep["background"] = props["background"]
            if keep:
                return (selector, keep)
            return (selector, {})
    return None


def _merge_css_fixes(original_css: str, fix_css: str) -> str:
    """Merge changed CSS properties from fixer into the original CSS.

    Uses PROPERTY-LEVEL merging: for each rule in fix_css, merges individual
    CSS properties into the matching original rule. This preserves critical
    layout properties (position, width, height, overflow) that the fixer
    may not include in its partial fix output.

    For each rule in fix_css:
      - If selector exists in original → merge properties (override + add)
      - If selector is new → append at end

    After merging, the root container's background-color/background are
    restored from the original CSS so the fixer cannot change them (e.g. to black).
    Returns the merged CSS string.
    """
    if not fix_css or not fix_css.strip():
        return original_css

    original_rules = _parse_css_rules(original_css)
    fix_rules = _parse_css_rules(fix_css)

    if not fix_rules:
        logger.warning("No parseable CSS rules found in fixer output")
        return original_css

    root_background = _get_root_selector_and_background(original_css)

    merged_css = original_css
    appended_rules: list[str] = []

    for selector, fix_rule in fix_rules.items():
        if selector in original_rules:
            original_rule = original_rules[selector]
            # Parse properties from both rules
            orig_props = _parse_css_properties(original_rule)
            fix_props = _parse_css_properties(fix_rule)
            # Merge: fix properties override originals, originals preserved
            merged_props = {**orig_props, **fix_props}
            # Guard: preserve color, font-family, font-size — from Figma spec; fixer must not change them
            for guarded in ("color", "font-family", "font-size"):
                if guarded in orig_props and guarded in fix_props:
                    merged_props[guarded] = orig_props[guarded]
            # Guard: never let fixer change root container background
            if root_background and selector == root_background[0]:
                for k, v in root_background[1].items():
                    merged_props[k] = v
            merged_rule = _rebuild_rule(selector, merged_props)
            merged_css = merged_css.replace(original_rule, merged_rule)
        else:
            # New rule — append at end
            appended_rules.append(fix_rule)

    if appended_rules:
        merged_css = merged_css.rstrip() + "\n\n" + "\n\n".join(appended_rules) + "\n"

    # If root was not in fix_rules, ensure merged still has original root background
    if root_background:
        root_sel, root_props = root_background
        if root_sel in original_rules and root_props:
            merged_rules = _parse_css_rules(merged_css)
            if root_sel in merged_rules:
                merged_props = _parse_css_properties(merged_rules[root_sel])
                changed = False
                for k, v in root_props.items():
                    if merged_props.get(k) != v:
                        merged_props[k] = v
                        changed = True
                if changed:
                    merged_rule = _rebuild_rule(root_sel, merged_props)
                    merged_css = merged_css.replace(merged_rules[root_sel], merged_rule)
    logger.info("CSS merge: %d rules patched (property-level), %d rules appended",
                len(fix_rules) - len(appended_rules), len(appended_rules))
    return merged_css


class FixerAgent(BaseAgent):
    """Iteratively fixes CSS using vision-based comparison of screenshots."""

    def __init__(self, job_id: str):
        super().__init__(job_id)
        self._fix_history: list[dict] = []

    async def execute(
        self,
        html_content: str,
        css_content: str,
        diff_report: DiffReport,
        iteration: int = 1,
        design_context: str = "",
        allow_html_fixes: bool = False,
        figma_screenshot: Optional[bytes] = None,
        rendered_screenshot: Optional[bytes] = None,
    ) -> dict[str, str]:
        """Apply targeted CSS fixes by visually comparing Figma vs rendered output.

        Args:
            html_content: Current HTML content.
            css_content: Current CSS to fix.
            diff_report: The visual comparison report.
            iteration: Current fix iteration number.
            design_context: Condensed design spec info.
            allow_html_fixes: If True, allow HTML modifications.
            figma_screenshot: PNG bytes of the Figma design (reference).
            rendered_screenshot: PNG bytes of the current rendered HTML.

        Returns:
            Dict with 'css' key (always) and 'html' key (when HTML was fixed).
        """
        agent_start = time.monotonic()
        logger.info("[job:%s] Fixer iteration %d started (vision=%s, allow_html=%s)",
                     self.job_id, iteration,
                     figma_screenshot is not None and rendered_screenshot is not None,
                     allow_html_fixes)
        await self.report_progress(
            f"Starting fix iteration {iteration}",
            {"iteration": iteration, "allow_html_fixes": allow_html_fixes},
        )

        # Load the fixer prompt template
        prompt_path = PROMPTS_DIR / "fixer.txt"
        system_prompt = prompt_path.read_text(encoding="utf-8")

        if allow_html_fixes:
            # Remove the CSS-only restriction so the model may return HTML + CSS
            system_prompt = system_prompt.replace(
                "1. **CSS-only fixes**: You must ONLY modify CSS. Do not suggest HTML changes.\n2.",
                "2.",
            )
            system_prompt += (
                "\n\n## HTML FIXES ALLOWED\n"
                "For this iteration, you MAY also modify the HTML to fix layout issues.\n"
                "Return BOTH updated HTML and CSS changes in your response:\n\n"
                "```html\n(complete fixed HTML)\n```\n\n"
                "```css\n(only changed/added CSS rules)\n```\n"
            )

        # Build user prompt
        user_prompt = self._build_fix_prompt(
            html_content, css_content, diff_report, iteration, design_context,
        )

        # Build images list: Figma screenshot, rendered screenshot, diff heatmap
        # GPT-4 vision sees them in order so it can compare side by side
        # Downscale to avoid exceeding OpenAI's request-size limit on tall pages
        images: list[bytes] = []
        if figma_screenshot:
            images.append(_downscale_for_vision(figma_screenshot))
        if rendered_screenshot:
            images.append(_downscale_for_vision(rendered_screenshot))
        if diff_report.diff_image_path:
            try:
                raw = Path(diff_report.diff_image_path).read_bytes()
                images.append(_downscale_for_vision(raw))
            except Exception as e:
                logger.warning("[job:%s] Failed to load diff heatmap: %s", self.job_id, e)

        image_count = len(images)
        logger.info("[job:%s] Fixer sending %d images to GPT-4 vision", self.job_id, image_count)

        await self.report_progress(
            f"Calling GPT-4 vision with {image_count} images for CSS fixes"
        )

        gpt_response = await call_gpt4(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            images=images if images else None,
            temperature=0.1,
            max_tokens=16384,
            image_detail="high",
        )

        # Handle truncation
        if gpt_response.was_truncated:
            logger.warning(
                "[job:%s] Fixer response TRUNCATED (tokens=%d). Keeping original CSS.",
                self.job_id, gpt_response.completion_tokens,
            )
            await self.report_progress("Fix response truncated, keeping original CSS")
            return {"css": css_content}

        result: dict[str, str] = {}

        # Extract HTML if html fixes are allowed
        if allow_html_fixes:
            html_match = re.search(r"```html\s*\n(.*?)```", gpt_response.content, re.DOTALL)
            if html_match:
                fixed_html = html_match.group(1).strip()
                if fixed_html and len(fixed_html) > len(html_content) * 0.5:
                    result["html"] = fixed_html
                    logger.info("[job:%s] Fixer returned updated HTML (%d chars)",
                                self.job_id, len(fixed_html))

        # Extract the fix CSS (changed rules only)
        fix_css = _extract_css_from_response(gpt_response.content)

        if fix_css is None:
            logger.warning("Could not extract CSS from fixer response, keeping original")
            await self.report_progress("Fix extraction failed, keeping original CSS")
            return {"css": css_content}

        # Merge at property level — preserves existing layout properties
        merged_css = _merge_css_fixes(css_content, fix_css)
        result["css"] = merged_css

        # Record fix history
        fix_rule_count = len(_parse_css_rules(fix_css))
        self._fix_history.append({
            "iteration": iteration,
            "regions_fixed": len(diff_report.regions),
            "high_severity": len(diff_report.high_severity_regions),
            "mismatch_before": diff_report.pixel_mismatch_percent,
            "ssim_before": diff_report.ssim_score,
            "html_fixed": "html" in result,
            "rules_changed": fix_rule_count,
        })

        logger.info("[job:%s] Fixer iteration %d complete in %.2fs (%d CSS rules changed)",
                     self.job_id, iteration, time.monotonic() - agent_start, fix_rule_count)
        await self.report_progress(
            f"Fix iteration {iteration} complete ({fix_rule_count} CSS rules changed)",
            {
                "iteration": iteration,
                "css_length": len(merged_css),
                "changes_made": merged_css != css_content,
                "rules_changed": fix_rule_count,
            },
        )

        return result

    def _build_fix_prompt(
        self,
        html_content: str,
        css_content: str,
        diff_report: DiffReport,
        iteration: int,
        design_context: str = "",
    ) -> str:
        """Build the fix prompt with visual comparison context."""

        # Fix history for later iterations
        history_text = ""
        if self._fix_history:
            history_lines = []
            for entry in self._fix_history:
                history_lines.append(
                    f"  Iteration {entry['iteration']}: "
                    f"SSIM was {entry['ssim_before']:.4f}, "
                    f"mismatch was {entry['mismatch_before']:.2f}%, "
                    f"changed {entry['rules_changed']} rules"
                )
            history_text = (
                "\n\n## Previous Fix Attempts (score should improve each iteration)\n"
                + "\n".join(history_lines)
            )

        # Design context
        design_context_text = ""
        if design_context:
            design_context_text = f"\n\n## Design Context (exact values from Figma)\n{design_context}"

        # Region diagnostics: top 10 regions with coordinates, severity, issue, and suspect selectors
        region_diagnostics_text = ""
        if diff_report.regions:
            suspect_per_region = get_region_suspect_selectors(css_content, diff_report.regions)
            top_regions = diff_report.regions[:10]
            lines = []
            for i, r in enumerate(top_regions):
                suspects = suspect_per_region[i] if i < len(suspect_per_region) else []
                suspect_str = ", ".join(suspects[:5]) if suspects else "—"
                lines.append(
                    f"  Region at ({int(r.x)}, {int(r.y)}) {int(r.width)}x{int(r.height)}: "
                    f"{r.issue} — likely selectors: {suspect_str}"
                )
            region_diagnostics_text = "\n\n## Region diagnostics (map diff areas to selectors)\n" + "\n".join(lines)

        # Condensed HTML skeleton (tag types + class names + nesting, no text content)
        skeleton = re.sub(r">\s*[^<]*\s*<", "><", html_content)
        skeleton = re.sub(r"\n\s*\n", "\n", skeleton).strip()
        html_skeleton_text = f"\n\n## HTML skeleton (for selector context)\n```html\n{skeleton}\n```"

        prompt = f"""## Fix Iteration {iteration}

## Visual Comparison
- Image 1 (attached): **Figma design** — this is the REFERENCE (what it should look like)
- Image 2 (attached): **Current rendered HTML** — this is what the code produces now
- Image 3 (attached): **Diff heatmap** — red areas show visual differences

Compare Image 1 and Image 2 carefully. Identify the TOP differences and fix them.

## Current Scores
- SSIM score: {diff_report.ssim_score:.4f} (higher = better, target: {settings.SSIM_THRESHOLD:.2f}+)
- Pixel mismatch: {diff_report.pixel_mismatch_percent:.2f}% (lower = better, target: < 5%)
{history_text}
{design_context_text}{region_diagnostics_text}{html_skeleton_text}

## Current CSS (FIX THIS — change only what's needed to match the Figma design)
```css
{css_content}
```

## Instructions
1. LOOK at Image 1 (Figma) and Image 2 (rendered) — what are the biggest visual differences?
2. For each difference, find the CSS selector and fix the specific property
3. Focus on: backgrounds, positions, borders, shadows
4. Return ONLY changed CSS rules — do NOT return unchanged rules
5. Each fix should make Image 2 look more like Image 1

```css
/* only changed/added rules */
```
"""
        return prompt

    @property
    def fix_history(self) -> list[dict]:
        """Get the history of fix attempts."""
        return list(self._fix_history)
