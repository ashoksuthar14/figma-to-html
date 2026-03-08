import * as cheerio from "cheerio";

function escapeHtmlText(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function updateTextContent(
  html: string,
  nodeId: string,
  newText: string
): string {
  const escaped = escapeHtmlText(newText);
  const marker = `data-node-id="${nodeId}"`;
  const markerIdx = html.indexOf(marker);
  if (markerIdx === -1) {
    console.warn("[updateTextContent] node not found:", nodeId);
    return html;
  }

  const closeAngle = html.indexOf(">", markerIdx);
  if (closeAngle === -1) return html;
  const contentStart = closeAngle + 1;

  const tagStart = html.lastIndexOf("<", markerIdx);
  if (tagStart === -1) return html;
  const tagMatch = html.substring(tagStart).match(/^<(\w+)/);
  if (!tagMatch) return html;
  const tagName = tagMatch[1];

  const closingTag = `</${tagName}>`;
  const contentEnd = html.indexOf(closingTag, contentStart);
  if (contentEnd === -1) return html;

  return html.substring(0, contentStart) + escaped + html.substring(contentEnd);
}

export function updateCssProperty(
  css: string,
  className: string,
  property: string,
  value: string
): string {
  const regex = new RegExp(
    `(\\.${escapeRegex(className)}\\s*\\{[^}]*?)${escapeRegex(property)}\\s*:\\s*[^;]+;`,
    "s"
  );
  if (regex.test(css)) {
    return css.replace(regex, `$1${property}: ${value};`);
  }

  const appendRegex = new RegExp(
    `(\\.${escapeRegex(className)}\\s*\\{[^}]*)\\}`,
    "s"
  );
  if (appendRegex.test(css)) {
    return css.replace(appendRegex, `$1  ${property}: ${value};\n}`);
  }

  return css;
}

export function getNodeInfo(
  html: string,
  nodeId: string
): { tagName: string; textContent: string; className: string } | null {
  const $ = cheerio.load(html);
  const el = $(`[data-node-id="${nodeId}"]`);
  if (el.length === 0) return null;

  const firstEl = el.get(0);
  return {
    tagName: firstEl && "tagName" in firstEl ? (firstEl.tagName ?? "") : "",
    textContent: el.text().trim(),
    className: el.attr("class") ?? "",
  };
}

/**
 * Update spacing (margin/padding) for a node.
 * Prefers CSS class rule update; falls back to inline style.
 */
export function updateSpacing(
  html: string,
  css: string,
  nodeId: string,
  property: string,
  value: string
): { html: string; css: string } {
  const $ = cheerio.load(html);
  const el = $(`[data-node-id="${nodeId}"]`);
  if (el.length === 0) return { html, css };

  const className = el.attr("class")?.split(/\s+/)[0] ?? "";

  if (className && css.includes(`.${className}`)) {
    const newCss = updateCssProperty(css, className, property, value);
    if (newCss !== css) {
      return { html, css: newCss };
    }
  }

  const existingStyle = el.attr("style") ?? "";
  const propRegex = new RegExp(`${escapeRegex(property)}\\s*:\\s*[^;]+;?`, "g");
  const cleaned = existingStyle.replace(propRegex, "").trim();
  const newStyle = cleaned
    ? `${cleaned}; ${property}: ${value};`
    : `${property}: ${value};`;
  el.attr("style", newStyle);
  return { html: $.html(), css };
}

const SAFE_PROTOCOLS = ["http:", "https:", "mailto:", "tel:"];

function isUrlSafe(url: string): boolean {
  try {
    if (url.startsWith("mailto:") || url.startsWith("tel:")) return true;
    const parsed = new URL(url);
    return SAFE_PROTOCOLS.includes(parsed.protocol);
  } catch {
    if (url.startsWith("/") || url.startsWith("#")) return true;
    return false;
  }
}

/**
 * Wrap element content with a link or update existing link.
 */
export function wrapWithLink(
  html: string,
  nodeId: string,
  url: string,
  newTab: boolean
): string {
  if (!isUrlSafe(url)) return html;

  const $ = cheerio.load(html);
  const el = $(`[data-node-id="${nodeId}"]`);
  if (el.length === 0) return html;

  const tag = el.get(0) && "tagName" in el.get(0)! ? el.get(0)!.tagName : "";
  const targetAttr = newTab ? ' target="_blank" rel="noopener noreferrer"' : "";

  if (tag === "a") {
    el.attr("href", url);
    if (newTab) {
      el.attr("target", "_blank");
      el.attr("rel", "noopener noreferrer");
    } else {
      el.removeAttr("target");
      el.removeAttr("rel");
    }
    return $.html();
  }

  const innerHtml = el.html() ?? el.text();
  el.html(`<a href="${url}"${targetAttr}>${innerHtml}</a>`);
  return $.html();
}

/**
 * Remove link from element (unwrap <a> tag).
 */
export function removeLink(html: string, nodeId: string): string {
  const $ = cheerio.load(html);
  const el = $(`[data-node-id="${nodeId}"]`);
  if (el.length === 0) return html;

  const tag = el.get(0) && "tagName" in el.get(0)! ? el.get(0)!.tagName : "";

  if (tag === "a") {
    const inner = el.html() ?? el.text();
    el.replaceWith(`<span data-node-id="${nodeId}">${inner}</span>`);
    return $.html();
  }

  const link = el.find("a").first();
  if (link.length > 0) {
    const inner = link.html() ?? link.text();
    link.replaceWith(inner);
    return $.html();
  }

  return html;
}

/**
 * Get current inline styles for a node.
 */
export function getInlineStyles(
  html: string,
  nodeId: string
): Record<string, string> {
  const $ = cheerio.load(html);
  const el = $(`[data-node-id="${nodeId}"]`);
  if (el.length === 0) return {};

  const style = el.attr("style") ?? "";
  const result: Record<string, string> = {};
  for (const decl of style.split(";")) {
    const trimmed = decl.trim();
    if (!trimmed) continue;
    const colonIdx = trimmed.indexOf(":");
    if (colonIdx === -1) continue;
    const prop = trimmed.slice(0, colonIdx).trim();
    const val = trimmed.slice(colonIdx + 1).trim();
    if (prop && val) result[prop] = val;
  }
  return result;
}

/**
 * Apply an array of CSS property patches produced by positionCalculator.
 * Reuses updateSpacing for each patch (handles class-based vs inline).
 */
export function applyPositionDelta(
  html: string,
  css: string,
  nodeId: string,
  patches: { property: string; value: string }[]
): { html: string; css: string } {
  let currentHtml = html;
  let currentCss = css;

  for (const patch of patches) {
    const result = updateSpacing(currentHtml, currentCss, nodeId, patch.property, patch.value);
    currentHtml = result.html;
    currentCss = result.css;
  }

  return { html: currentHtml, css: currentCss };
}

/**
 * Update a typography CSS property (font-size, line-height, letter-spacing) for a node.
 * Works like updateSpacing: prefers CSS class rule, falls back to inline style.
 */
export function updateTypographyProperty(
  html: string,
  css: string,
  nodeId: string,
  property: string,
  value: string
): { html: string; css: string } {
  return updateSpacing(html, css, nodeId, property, value);
}

/**
 * Update the `gap` property on the parent container of a node.
 * Finds the parent element by walking up from the target node in the HTML,
 * then applies the gap change via CSS class or inline style.
 */
export function updateParentGap(
  html: string,
  css: string,
  nodeId: string,
  gapValue: string
): { html: string; css: string } {
  const $ = cheerio.load(html);
  const el = $(`[data-node-id="${nodeId}"]`);
  if (el.length === 0) return { html, css };

  const parent = el.parent().closest("[data-node-id]");
  if (parent.length === 0) return { html, css };

  const parentNodeId = parent.attr("data-node-id") ?? "";
  if (!parentNodeId) return { html, css };

  return updateSpacing(html, css, parentNodeId, "gap", gapValue);
}

function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
