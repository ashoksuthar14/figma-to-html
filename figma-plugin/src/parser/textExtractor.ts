/**
 * Text extractor: reads text content and style information from Figma text nodes,
 * including mixed-style text segments (e.g., bold words within a paragraph).
 */

import type { TextProperties, TextSegment, Color } from '../types/designSpec';
import { figmaRgbToColor, figmaColorToRgba } from '../utils/colorUtils';
import { roundPx } from '../utils/unitUtils';

/**
 * Extract text properties from a Figma TextNode.
 *
 * @param node - The Figma TextNode
 * @returns TextProperties object with content and style segments
 */
export function extractText(node: TextNode): TextProperties {
  const characters = node.characters;

  const props: TextProperties = {
    characters,
    textAlignHorizontal: mapTextAlignHorizontal(node.textAlignHorizontal),
    textAlignVertical: mapTextAlignVertical(node.textAlignVertical),
    textAutoResize: mapTextAutoResize(node.textAutoResize),
    paragraphSpacing: roundPx(node.paragraphSpacing ?? 0),
    paragraphIndent: roundPx(node.paragraphIndent ?? 0),
    segments: extractTextSegments(node),
  };

  if ('textTruncation' in node) {
    const truncation = (node as any).textTruncation;
    if (truncation === 'ENDING') {
      props.textTruncation = 'ENDING';
    }
  }

  if ('maxLines' in node) {
    const ml = (node as any).maxLines;
    if (typeof ml === 'number' && ml > 0) {
      props.maxLines = ml;
    }
  }

  return props;
}

/**
 * Extract text segments with potentially different styling.
 * Figma text can have mixed styles within a single text node (e.g., some words bold,
 * some italic, different colors, etc.). This function detects style boundaries
 * and creates separate segments for each distinct style run.
 */
function extractTextSegments(node: TextNode): TextSegment[] {
  const text = node.characters;
  if (text.length === 0) {
    return [];
  }

  // Check if text has uniform styling (no mixed styles)
  if (!hasMixedStyles(node)) {
    return [createUniformSegment(node, 0, text.length)];
  }

  // For mixed styles, walk character by character to find style boundaries
  return extractMixedSegments(node);
}

/**
 * Check if a text node has any mixed (non-uniform) styling.
 */
function hasMixedStyles(node: TextNode): boolean {
  return (
    node.fontName === figma.mixed ||
    node.fontSize === figma.mixed ||
    node.fontWeight === figma.mixed ||
    node.letterSpacing === figma.mixed ||
    node.lineHeight === figma.mixed ||
    node.textDecoration === figma.mixed ||
    node.fills === figma.mixed
  );
}

/**
 * Create a single text segment for uniformly-styled text.
 */
function createUniformSegment(node: TextNode, start: number, end: number): TextSegment {
  const fontName = node.fontName as FontName;
  const fontSize = node.fontSize as number;
  const letterSpacing = node.letterSpacing as LetterSpacing;
  const lineHeight = node.lineHeight as LineHeight;
  const textDecoration = node.textDecoration as string;
  const fills = node.fills as readonly Paint[];

  return {
    characters: node.characters.substring(start, end),
    start,
    end,
    fontFamily: fontName?.family ?? 'Inter',
    fontSize: roundPx(fontSize ?? 16),
    fontWeight: mapFontWeight(fontName?.style ?? 'Regular'),
    fontStyle: isFontItalic(fontName?.style ?? 'Regular') ? 'italic' : 'normal',
    lineHeight: extractLineHeight(lineHeight),
    lineHeightUnit: extractLineHeightUnit(lineHeight),
    letterSpacing: extractLetterSpacing(letterSpacing),
    letterSpacingUnit: extractLetterSpacingUnit(letterSpacing),
    color: extractTextColor(fills),
    textDecoration: mapTextDecoration(textDecoration),
    textCase: extractTextCase(node),
  };
}

/**
 * Extract segments from a text node with mixed styles.
 * Uses Figma's range-based style getters to find style boundaries.
 */
function extractMixedSegments(node: TextNode): TextSegment[] {
  const text = node.characters;
  const segments: TextSegment[] = [];

  let segStart = 0;

  while (segStart < text.length) {
    // Find the end of the current style run
    let segEnd = segStart + 1;

    // Get the style at the start position
    const startStyle = getStyleAtIndex(node, segStart);

    // Extend the segment as long as the style matches
    while (segEnd < text.length) {
      const currentStyle = getStyleAtIndex(node, segEnd);
      if (!stylesMatch(startStyle, currentStyle)) {
        break;
      }
      segEnd++;
    }

    segments.push({
      characters: text.substring(segStart, segEnd),
      start: segStart,
      end: segEnd,
      ...startStyle,
    });

    segStart = segEnd;
  }

  return mergeAdjacentSegments(segments);
}

/**
 * Style properties extracted at a specific character index.
 */
interface CharStyle {
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  fontStyle: 'normal' | 'italic';
  lineHeight: number | 'auto';
  lineHeightUnit?: 'PIXELS' | 'PERCENT' | 'AUTO';
  letterSpacing: number;
  letterSpacingUnit?: 'PIXELS' | 'PERCENT';
  color: Color;
  textDecoration: 'NONE' | 'UNDERLINE' | 'STRIKETHROUGH';
  textCase?: 'ORIGINAL' | 'UPPER' | 'LOWER' | 'TITLE';
}

/**
 * Get the text style properties at a specific character index.
 */
function getStyleAtIndex(node: TextNode, index: number): CharStyle {
  let fontFamily = 'Inter';
  let fontStyle = 'Regular';
  let fontSize = 16;
  let letterSpacing: LetterSpacing = { value: 0, unit: 'PIXELS' };
  let lineHeight: LineHeight = { unit: 'AUTO' };
  let textDecoration = 'NONE';
  let fills: readonly Paint[] = [];
  let textCase = 'ORIGINAL';

  try {
    const fontNameResult = node.getRangeFontName(index, index + 1);
    if (fontNameResult !== figma.mixed) {
      fontFamily = (fontNameResult as FontName).family;
      fontStyle = (fontNameResult as FontName).style;
    }
  } catch {
    // Fallback if range query fails
  }

  try {
    const fontSizeResult = node.getRangeFontSize(index, index + 1);
    if (fontSizeResult !== figma.mixed) {
      fontSize = fontSizeResult as number;
    }
  } catch {
    // Fallback
  }

  try {
    const lsResult = node.getRangeLetterSpacing(index, index + 1);
    if (lsResult !== figma.mixed) {
      letterSpacing = lsResult as LetterSpacing;
    }
  } catch {
    // Fallback
  }

  try {
    const lhResult = node.getRangeLineHeight(index, index + 1);
    if (lhResult !== figma.mixed) {
      lineHeight = lhResult as LineHeight;
    }
  } catch {
    // Fallback
  }

  try {
    const tdResult = node.getRangeTextDecoration(index, index + 1);
    if (tdResult !== figma.mixed) {
      textDecoration = tdResult as string;
    }
  } catch {
    // Fallback
  }

  try {
    const fillsResult = node.getRangeFills(index, index + 1);
    if (fillsResult !== figma.mixed) {
      fills = fillsResult as readonly Paint[];
    }
  } catch {
    // Fallback
  }

  try {
    const tcResult = node.getRangeTextCase(index, index + 1);
    if (tcResult !== figma.mixed) {
      textCase = tcResult as string;
    }
  } catch {
    // Fallback
  }

  return {
    fontFamily,
    fontSize: roundPx(fontSize),
    fontWeight: mapFontWeight(fontStyle),
    fontStyle: isFontItalic(fontStyle) ? 'italic' : 'normal',
    lineHeight: extractLineHeight(lineHeight),
    lineHeightUnit: extractLineHeightUnit(lineHeight),
    letterSpacing: extractLetterSpacing(letterSpacing),
    letterSpacingUnit: extractLetterSpacingUnit(letterSpacing),
    color: extractTextColor(fills),
    textDecoration: mapTextDecoration(textDecoration),
    textCase: mapTextCase(textCase),
  };
}

/**
 * Check if two character styles are identical.
 */
function stylesMatch(a: CharStyle, b: CharStyle): boolean {
  return (
    a.fontFamily === b.fontFamily &&
    a.fontSize === b.fontSize &&
    a.fontWeight === b.fontWeight &&
    a.fontStyle === b.fontStyle &&
    a.lineHeight === b.lineHeight &&
    a.letterSpacing === b.letterSpacing &&
    a.color.r === b.color.r &&
    a.color.g === b.color.g &&
    a.color.b === b.color.b &&
    a.color.a === b.color.a &&
    a.textDecoration === b.textDecoration &&
    a.textCase === b.textCase
  );
}

/**
 * Merge adjacent segments with identical styling to reduce output size.
 */
function mergeAdjacentSegments(segments: TextSegment[]): TextSegment[] {
  if (segments.length <= 1) return segments;

  const merged: TextSegment[] = [segments[0]];

  for (let i = 1; i < segments.length; i++) {
    const prev = merged[merged.length - 1];
    const curr = segments[i];

    // Check if styles match (excluding characters, start, end)
    if (
      prev.fontFamily === curr.fontFamily &&
      prev.fontSize === curr.fontSize &&
      prev.fontWeight === curr.fontWeight &&
      prev.fontStyle === curr.fontStyle &&
      prev.lineHeight === curr.lineHeight &&
      prev.letterSpacing === curr.letterSpacing &&
      prev.color.r === curr.color.r &&
      prev.color.g === curr.color.g &&
      prev.color.b === curr.color.b &&
      prev.color.a === curr.color.a &&
      prev.textDecoration === curr.textDecoration
    ) {
      // Merge: extend previous segment
      prev.characters += curr.characters;
      prev.end = curr.end;
    } else {
      merged.push(curr);
    }
  }

  return merged;
}

// ─── Mapping Helpers ──────────────────────────────────────────────────────────

/**
 * Map Figma font style string to numeric CSS font-weight.
 * Figma uses strings like "Regular", "Bold", "Semi Bold", etc.
 */
function mapFontWeight(style: string): number {
  const lower = style.toLowerCase().replace(/[- ]/g, '');

  if (lower.includes('thin') || lower.includes('hairline')) return 100;
  if (lower.includes('extralight') || lower.includes('ultralight')) return 200;
  if (lower.includes('light')) return 300;
  if (lower.includes('regular') || lower.includes('normal') || lower.includes('book')) return 400;
  if (lower.includes('medium')) return 500;
  if (lower.includes('semibold') || lower.includes('demibold')) return 600;
  if (lower.includes('extrabold') || lower.includes('ultrabold')) return 800;
  if (lower.includes('bold')) return 700;
  if (lower.includes('black') || lower.includes('heavy')) return 900;

  return 400;
}

/**
 * Check if a font style string indicates italic.
 */
function isFontItalic(style: string): boolean {
  return style.toLowerCase().includes('italic');
}

/**
 * Extract line height value from Figma's LineHeight type.
 */
function extractLineHeight(lh: LineHeight): number | 'auto' {
  if (!lh || lh.unit === 'AUTO') return 'auto';
  if (lh.unit === 'PIXELS') return roundPx(lh.value);
  if (lh.unit === 'PERCENT') return Math.round(lh.value) / 100;
  return 'auto';
}

/**
 * Extract the line height unit.
 */
function extractLineHeightUnit(lh: LineHeight): 'PIXELS' | 'PERCENT' | 'AUTO' | undefined {
  if (!lh || lh.unit === 'AUTO') return 'AUTO';
  return lh.unit as 'PIXELS' | 'PERCENT';
}

/**
 * Extract letter spacing value from Figma's LetterSpacing type.
 */
function extractLetterSpacing(ls: LetterSpacing): number {
  if (!ls) return 0;
  return roundPx(ls.value ?? 0);
}

/**
 * Extract the letter spacing unit.
 */
function extractLetterSpacingUnit(ls: LetterSpacing): 'PIXELS' | 'PERCENT' | undefined {
  if (!ls) return 'PIXELS';
  return ls.unit as 'PIXELS' | 'PERCENT';
}

/**
 * Extract the primary text color from fills array.
 */
function extractTextColor(fills: readonly Paint[] | typeof figma.mixed): Color {
  if (!fills || fills === figma.mixed || !Array.isArray(fills) || fills.length === 0) {
    return { r: 0, g: 0, b: 0, a: 1 }; // default to black
  }

  // Find the first visible solid fill
  const visibleSolid = fills.find(
    (f: Paint) => f.type === 'SOLID' && f.visible !== false
  ) as SolidPaint | undefined;

  if (visibleSolid) {
    return figmaRgbToColor(visibleSolid.color, visibleSolid.opacity ?? 1);
  }

  // Fallback to black
  return { r: 0, g: 0, b: 0, a: 1 };
}

/**
 * Map Figma text decoration to our TextDecoration type.
 */
function mapTextDecoration(decoration: string): 'NONE' | 'UNDERLINE' | 'STRIKETHROUGH' {
  switch (decoration) {
    case 'UNDERLINE':
      return 'UNDERLINE';
    case 'STRIKETHROUGH':
      return 'STRIKETHROUGH';
    default:
      return 'NONE';
  }
}

/**
 * Map text horizontal alignment.
 */
function mapTextAlignHorizontal(
  align: string
): 'LEFT' | 'CENTER' | 'RIGHT' | 'JUSTIFIED' {
  switch (align) {
    case 'LEFT':
      return 'LEFT';
    case 'CENTER':
      return 'CENTER';
    case 'RIGHT':
      return 'RIGHT';
    case 'JUSTIFIED':
      return 'JUSTIFIED';
    default:
      return 'LEFT';
  }
}

/**
 * Map text vertical alignment.
 */
function mapTextAlignVertical(
  align: string
): 'TOP' | 'CENTER' | 'BOTTOM' {
  switch (align) {
    case 'TOP':
      return 'TOP';
    case 'CENTER':
      return 'CENTER';
    case 'BOTTOM':
      return 'BOTTOM';
    default:
      return 'TOP';
  }
}

/**
 * Map text auto resize mode.
 */
function mapTextAutoResize(
  mode: string
): 'NONE' | 'WIDTH_AND_HEIGHT' | 'HEIGHT' | 'TRUNCATE' {
  switch (mode) {
    case 'NONE':
      return 'NONE';
    case 'WIDTH_AND_HEIGHT':
      return 'WIDTH_AND_HEIGHT';
    case 'HEIGHT':
      return 'HEIGHT';
    case 'TRUNCATE':
      return 'TRUNCATE';
    default:
      return 'NONE';
  }
}

/**
 * Extract text case from a TextNode.
 */
function extractTextCase(node: TextNode): 'ORIGINAL' | 'UPPER' | 'LOWER' | 'TITLE' | undefined {
  if (!('textCase' in node)) return undefined;
  const tc = node.textCase;
  if (tc === figma.mixed) return undefined;
  return mapTextCase(tc as string);
}

/**
 * Map Figma text case value.
 */
function mapTextCase(tc: string): 'ORIGINAL' | 'UPPER' | 'LOWER' | 'TITLE' {
  switch (tc) {
    case 'UPPER':
      return 'UPPER';
    case 'LOWER':
      return 'LOWER';
    case 'TITLE':
      return 'TITLE';
    default:
      return 'ORIGINAL';
  }
}
