"""Micro-fixer agent: applies targeted CSS/HTML fixes to a single element."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Optional

from agents.base import BaseAgent
from services.openai_service import call_gpt4

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _extract_node_subtree(html: str, node_id: str) -> str:
    """Extract the HTML subtree containing the target node and its context."""
    pattern = re.compile(
        r'(<[^>]*data-node-id=["\']' + re.escape(node_id) + r'["\'][^>]*>)',
        re.DOTALL,
    )
    match = pattern.search(html)
    if not match:
        return ""

    start = match.start()
    context_start = max(0, start - 500)
    context_end = min(len(html), match.end() + 2000)

    tag_match = re.match(r"<(\w+)", match.group(1))
    if tag_match:
        tag_name = tag_match.group(1)
        close_tag = f"</{tag_name}>"
        close_pos = html.find(close_tag, match.end())
        if close_pos != -1:
            context_end = max(context_end, close_pos + len(close_tag))

    return html[context_start:context_end]


def _extract_relevant_css(css: str, html_subtree: str) -> str:
    """Extract CSS rules whose selectors match classes found in the subtree."""
    classes = set(re.findall(r'class=["\']([^"\']+)["\']', html_subtree))
    class_names: set[str] = set()
    for cls_attr in classes:
        for name in cls_attr.split():
            class_names.add(name)

    if not class_names:
        return css[:3000]

    relevant_rules: list[str] = []
    pos = 0
    cleaned = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)

    while pos < len(cleaned):
        while pos < len(cleaned) and cleaned[pos] in " \t\n\r":
            pos += 1
        if pos >= len(cleaned):
            break

        brace_start = cleaned.find("{", pos)
        if brace_start == -1:
            break

        selector = cleaned[pos:brace_start].strip()
        if not selector:
            pos = brace_start + 1
            continue

        depth = 1
        i = brace_start + 1
        while i < len(cleaned) and depth > 0:
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
            i += 1

        full_rule = cleaned[pos:i].strip()

        for name in class_names:
            if name in selector:
                relevant_rules.append(full_rule)
                break

        pos = i

    return "\n\n".join(relevant_rules) if relevant_rules else css[:3000]


def _extract_css_from_response(response: str) -> Optional[str]:
    """Extract CSS from the GPT response."""
    css_match = re.search(r"```css\s*\n(.*?)```", response, re.DOTALL)
    if css_match:
        return css_match.group(1).strip()

    code_match = re.search(r"```\s*\n(.*?)```", response, re.DOTALL)
    if code_match:
        content = code_match.group(1).strip()
        if "{" in content and "}" in content:
            return content

    return None


def _extract_html_from_response(response: str) -> Optional[str]:
    """Extract HTML from the GPT response."""
    html_match = re.search(r"```html\s*\n(.*?)```", response, re.DOTALL)
    if html_match:
        return html_match.group(1).strip()
    return None


def _extract_description(response: str) -> str:
    """Extract the explanation text before any code blocks."""
    parts = response.split("```")
    if parts:
        desc = parts[0].strip()
        if len(desc) > 200:
            desc = desc[:200] + "..."
        return desc
    return "Fix applied."


def _merge_css_patch(original_css: str, patch_css: str) -> str:
    """Merge patched CSS rules into the original CSS at property level."""
    if not patch_css or not patch_css.strip():
        return original_css

    def parse_rules(text: str) -> dict[str, str]:
        rules: dict[str, str] = {}
        cleaned = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        pos = 0
        while pos < len(cleaned):
            while pos < len(cleaned) and cleaned[pos] in " \t\n\r":
                pos += 1
            if pos >= len(cleaned):
                break
            brace_start = cleaned.find("{", pos)
            if brace_start == -1:
                break
            selector = cleaned[pos:brace_start].strip()
            if not selector:
                pos = brace_start + 1
                continue
            depth = 1
            i = brace_start + 1
            while i < len(cleaned) and depth > 0:
                if cleaned[i] == "{":
                    depth += 1
                elif cleaned[i] == "}":
                    depth -= 1
                i += 1
            rules[selector] = cleaned[pos:i].strip()
            pos = i
        return rules

    def parse_props(rule: str) -> dict[str, str]:
        match = re.search(r"\{(.*)\}", rule, re.DOTALL)
        if not match:
            return {}
        props: dict[str, str] = {}
        for decl in match.group(1).split(";"):
            decl = decl.strip()
            if ":" in decl:
                prop, _, val = decl.partition(":")
                prop = prop.strip()
                val = val.strip()
                if prop and val:
                    props[prop] = val
        return props

    original_rules = parse_rules(original_css)
    patch_rules = parse_rules(patch_css)
    merged = original_css
    appended: list[str] = []

    for selector, patch_rule in patch_rules.items():
        if selector in original_rules:
            orig_props = parse_props(original_rules[selector])
            patch_props = parse_props(patch_rule)
            merged_props = {**orig_props, **patch_props}
            for guarded in ("color", "font-family", "font-size"):
                if guarded in orig_props and guarded in patch_props:
                    merged_props[guarded] = orig_props[guarded]
            prop_lines = ";\n  ".join(f"{k}: {v}" for k, v in merged_props.items())
            new_rule = f"{selector} {{\n  {prop_lines};\n}}"
            merged = merged.replace(original_rules[selector], new_rule)
        else:
            appended.append(patch_rule)

    if appended:
        merged = merged.rstrip() + "\n\n" + "\n\n".join(appended) + "\n"

    return merged


def _apply_html_patch(original_html: str, patch_html: str, node_id: str) -> str:
    """Replace the targeted node's HTML with the patched version."""
    pattern = re.compile(
        r'(<[^>]*data-node-id=["\']' + re.escape(node_id) + r'["\'][^>]*>)',
        re.DOTALL,
    )
    match = pattern.search(patch_html)
    if not match:
        return original_html

    orig_match = pattern.search(original_html)
    if not orig_match:
        return original_html

    tag_match = re.match(r"<(\w+)", orig_match.group(1))
    if not tag_match:
        return original_html

    tag_name = tag_match.group(1)
    close_tag = f"</{tag_name}>"

    orig_close = original_html.find(close_tag, orig_match.end())
    if orig_close == -1:
        return original_html
    orig_end = orig_close + len(close_tag)

    patch_tag_match = re.match(r"<(\w+)", match.group(1))
    if not patch_tag_match:
        return original_html
    patch_close = patch_html.find(f"</{patch_tag_match.group(1)}>", match.end())
    if patch_close == -1:
        return original_html
    patch_end = patch_close + len(f"</{patch_tag_match.group(1)}>")

    replacement = patch_html[match.start():patch_end]
    return original_html[:orig_match.start()] + replacement + original_html[orig_end:]


class MicroFixerAgent(BaseAgent):
    """Targeted fixer that modifies only a specific element and its children."""

    async def execute(
        self,
        node_id: str,
        user_prompt: str,
        html_content: str,
        css_content: str,
    ) -> dict:
        """Apply a targeted fix to a specific node.

        Returns:
            Dict with 'html', 'css', 'changes_made', 'description'.
        """
        start_time = time.monotonic()
        logger.info("[job:%s] Micro-fix started for node %s", self.job_id, node_id)
        await self.report_progress(f"Starting micro-fix for node {node_id}")

        system_prompt = (PROMPTS_DIR / "micro_fixer.txt").read_text(encoding="utf-8")

        html_subtree = _extract_node_subtree(html_content, node_id)
        relevant_css = _extract_relevant_css(css_content, html_subtree)

        if not html_subtree:
            logger.warning("[job:%s] Node %s not found in HTML", self.job_id, node_id)
            return {
                "html": html_content,
                "css": css_content,
                "changes_made": False,
                "description": f"Node {node_id} not found in the HTML.",
            }

        user_message = f"""## User Issue
{user_prompt}

## Target Node
data-node-id="{node_id}"

## HTML Context (around the target node)
```html
{html_subtree}
```

## Relevant CSS Rules
```css
{relevant_css}
```

Fix ONLY the issue described. Return minimal CSS changes (and HTML only if structurally necessary).
"""

        await self.report_progress("Calling GPT-4 for targeted fix")
        gpt_response = await call_gpt4(
            system_prompt=system_prompt,
            user_prompt=user_message,
            temperature=0.1,
            max_tokens=4096,
        )

        description = _extract_description(gpt_response.content)
        fix_css = _extract_css_from_response(gpt_response.content)
        fix_html = _extract_html_from_response(gpt_response.content)

        result_html = html_content
        result_css = css_content
        changes_made = False

        if fix_css:
            result_css = _merge_css_patch(css_content, fix_css)
            if result_css != css_content:
                changes_made = True

        if fix_html:
            patched = _apply_html_patch(html_content, fix_html, node_id)
            if patched != html_content:
                result_html = patched
                changes_made = True

        elapsed = time.monotonic() - start_time
        logger.info(
            "[job:%s] Micro-fix complete in %.2fs (changes=%s)",
            self.job_id, elapsed, changes_made,
        )
        await self.report_progress(
            f"Micro-fix complete ({elapsed:.1f}s, changes={'yes' if changes_made else 'no'})"
        )

        return {
            "html": result_html,
            "css": result_css,
            "changes_made": changes_made,
            "description": description,
        }
