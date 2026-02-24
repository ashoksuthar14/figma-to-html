"""Agent 6 - Componentizer: Detects and consolidates repeated CSS patterns."""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from typing import Optional

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


def _parse_css_rules(css: str) -> list[dict]:
    """Parse CSS into a list of rule dicts with selector and properties.

    Returns:
        List of dicts with keys: 'selector', 'properties' (dict of prop: value),
        'raw' (original text).
    """
    rules: list[dict] = []

    # Remove comments
    css_clean = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)

    # Match CSS rules (simple parser, handles most cases)
    pattern = re.compile(r"([^{}]+?)\{([^{}]*)\}", re.DOTALL)

    for match in pattern.finditer(css_clean):
        selector = match.group(1).strip()
        body = match.group(2).strip()

        # Skip empty rules
        if not body:
            continue

        # Parse properties
        props: dict[str, str] = {}
        for declaration in body.split(";"):
            declaration = declaration.strip()
            if ":" not in declaration:
                continue
            prop, _, value = declaration.partition(":")
            prop = prop.strip()
            value = value.strip()
            if prop and value:
                props[prop] = value

        rules.append({
            "selector": selector,
            "properties": props,
            "raw": match.group(0),
        })

    return rules


def _find_repeated_property_sets(
    rules: list[dict],
    min_shared_props: int = 3,
) -> list[tuple[frozenset, list[str]]]:
    """Find groups of rules that share the same set of properties.

    Args:
        rules: Parsed CSS rules.
        min_shared_props: Minimum number of shared properties to consider.

    Returns:
        List of (shared_properties_frozenset, list_of_selectors).
    """
    # Group rules by their property sets (prop+value pairs)
    prop_set_groups: defaultdict[frozenset, list[str]] = defaultdict(list)

    for rule in rules:
        if len(rule["properties"]) < min_shared_props:
            continue

        # Create a frozenset of (property, value) tuples
        prop_set = frozenset(rule["properties"].items())
        prop_set_groups[prop_set].append(rule["selector"])

    # Filter to only groups with 2+ selectors
    repeated = [
        (prop_set, selectors)
        for prop_set, selectors in prop_set_groups.items()
        if len(selectors) >= 2
    ]

    # Sort by number of shared properties (descending) then by group size
    repeated.sort(key=lambda x: (len(x[0]), len(x[1])), reverse=True)

    return repeated


def _find_common_property_subsets(
    rules: list[dict],
    min_props: int = 3,
    min_selectors: int = 3,
) -> list[dict]:
    """Find common property subsets shared across multiple rules.

    More flexible than exact match - finds partial overlaps.
    """
    # Collect all property-value pairs and their selectors
    prop_to_selectors: defaultdict[tuple[str, str], list[str]] = defaultdict(list)

    for rule in rules:
        for prop, value in rule["properties"].items():
            prop_to_selectors[(prop, value)].append(rule["selector"])

    # Find property-value pairs that appear in 3+ rules
    common_pairs = {
        pv: selectors
        for pv, selectors in prop_to_selectors.items()
        if len(selectors) >= min_selectors
    }

    if not common_pairs:
        return []

    # Group selectors that share the same set of common properties
    selector_shared_props: defaultdict[str, set[tuple[str, str]]] = defaultdict(set)
    for pv, selectors in common_pairs.items():
        for sel in selectors:
            selector_shared_props[sel].add(pv)

    # Find clusters of selectors with enough shared properties
    clusters: list[dict] = []
    processed: set[str] = set()

    selectors_list = list(selector_shared_props.keys())

    for i, sel_a in enumerate(selectors_list):
        if sel_a in processed:
            continue

        group = [sel_a]
        shared = selector_shared_props[sel_a].copy()

        for sel_b in selectors_list[i + 1:]:
            if sel_b in processed:
                continue
            overlap = shared & selector_shared_props[sel_b]
            if len(overlap) >= min_props:
                group.append(sel_b)
                shared = overlap  # Narrow to common subset

        if len(group) >= min_selectors and len(shared) >= min_props:
            clusters.append({
                "selectors": group,
                "shared_properties": {prop: val for prop, val in shared},
            })
            processed.update(group)

    return clusters


def _generate_common_class_name(
    index: int,
    properties: dict[str, str],
) -> str:
    """Generate a descriptive class name for a common pattern."""
    # Try to infer a name from the properties
    if "display" in properties:
        display_val = properties["display"]
        if display_val == "flex":
            return f"flex-container-{index}"
        if display_val == "grid":
            return f"grid-container-{index}"

    if "font-family" in properties or "font-size" in properties:
        return f"text-style-{index}"

    if "background" in properties or "background-color" in properties:
        return f"bg-style-{index}"

    if "border" in properties or "border-radius" in properties:
        return f"border-style-{index}"

    return f"common-style-{index}"


class ComponentizerAgent(BaseAgent):
    """Detects repeated CSS patterns and extracts common classes."""

    async def execute(
        self,
        html_content: str,
        css_content: str,
    ) -> dict[str, str]:
        """Analyze and optimize CSS by extracting repeated patterns.

        Args:
            html_content: Current HTML content.
            css_content: Current CSS to optimize.

        Returns:
            Dict with 'html' and 'css' keys containing optimized code.
        """
        logger.info("[job:%s] Componentizer started", self.job_id)
        await self.report_progress("Analyzing CSS for repeated patterns")

        rules = _parse_css_rules(css_content)
        logger.info("[job:%s] Parsed %d CSS rules", self.job_id, len(rules))

        if len(rules) < 3:
            logger.info("[job:%s] Too few CSS rules (%d) to optimize, returning early", self.job_id, len(rules))
            await self.report_progress("Too few CSS rules to optimize")
            return {"html": html_content, "css": css_content}

        # Phase 1: Find exact duplicate property sets
        repeated = _find_repeated_property_sets(rules, min_shared_props=3)
        logger.info("[job:%s] Found %d exact duplicate groups", self.job_id, len(repeated))

        # Phase 2: Find common property subsets
        clusters = _find_common_property_subsets(rules, min_props=3, min_selectors=3)
        logger.info("[job:%s] Found %d property subset clusters", self.job_id, len(clusters))

        if not repeated and not clusters:
            logger.info("[job:%s] No repeated patterns found", self.job_id)
            await self.report_progress("No significant repeated patterns found")
            return {"html": html_content, "css": css_content}

        # Phase 3: Generate common classes and rewrite CSS
        new_css = css_content
        new_html = html_content
        common_classes: list[str] = []
        class_index = 0

        for prop_set, selectors in repeated:
            class_index += 1
            props_dict = dict(prop_set)
            class_name = _generate_common_class_name(class_index, props_dict)

            # Build the common class CSS
            props_css = "\n".join(
                f"  {prop}: {val};" for prop, val in sorted(props_dict.items())
            )
            common_class_css = f".{class_name} {{\n{props_css}\n}}"
            common_classes.append(common_class_css)

            # Remove the shared properties from individual rules
            for selector in selectors:
                # Find and modify the rule in the CSS
                for rule in rules:
                    if rule["selector"] == selector:
                        remaining_props = {
                            k: v
                            for k, v in rule["properties"].items()
                            if (k, v) not in prop_set
                        }
                        if remaining_props:
                            remaining_css = "\n".join(
                                f"  {p}: {v};"
                                for p, v in sorted(remaining_props.items())
                            )
                            new_rule = f"{selector} {{\n{remaining_css}\n}}"
                        else:
                            new_rule = f"/* {selector} - see .{class_name} */"

                        new_css = new_css.replace(rule["raw"], new_rule)
                        break

                # Add the common class to HTML elements
                # Try to find the element by class name from the selector
                if selector.startswith("."):
                    original_class = selector[1:].split(" ")[0].split(":")[0]
                    # Add the common class to elements with the original class
                    pattern = re.compile(
                        rf'class="([^"]*\b{re.escape(original_class)}\b[^"]*)"'
                    )
                    new_html = pattern.sub(
                        lambda m: f'class="{m.group(1)} {class_name}"',
                        new_html,
                    )

        # Prepend common classes to CSS
        if common_classes:
            common_section = (
                "/* === Common Patterns === */\n"
                + "\n\n".join(common_classes)
                + "\n\n/* === Component Styles === */\n"
            )
            # Insert after the box-sizing reset if present
            reset_marker = "box-sizing: border-box;"
            if reset_marker in new_css:
                insert_pos = new_css.index(reset_marker)
                insert_pos = new_css.index("}", insert_pos) + 1
                new_css = (
                    new_css[: insert_pos]
                    + "\n\n"
                    + common_section
                    + new_css[insert_pos:]
                )
            else:
                new_css = common_section + "\n" + new_css

        # Clean up redundant whitespace
        new_css = re.sub(r"\n{3,}", "\n\n", new_css)

        logger.info("[job:%s] Componentization complete: %d common classes extracted",
                     self.job_id, len(common_classes))
        await self.report_progress(
            f"Componentization complete: {len(common_classes)} common patterns extracted",
            {
                "common_classes": len(common_classes),
                "clusters_found": len(clusters),
            },
        )

        return {"html": new_html, "css": new_css}
