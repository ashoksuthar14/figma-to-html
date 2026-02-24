/**
 * Color conversion utilities for translating between Figma's color model
 * and standard web color formats (hex, rgba).
 *
 * Figma uses 0-1 float ranges for r/g/b/a. Our Color type uses 0-255 for
 * r/g/b and 0-1 for alpha.
 */

import type { Color } from '../types/designSpec';

/**
 * Convert a Figma RGBA color object to our normalized Color type.
 * Figma colors have r, g, b in 0-1 range and a in 0-1 range.
 *
 * @param figmaColor - The Figma RGBA color (0-1 per channel)
 * @param opacity - Optional additional opacity multiplier (node opacity, fill opacity, etc.)
 * @returns Normalized Color with r/g/b in 0-255 and a in 0-1
 */
export function figmaColorToRgba(figmaColor: RGBA, opacity?: number): Color {
  const effectiveOpacity = opacity !== undefined ? figmaColor.a * opacity : figmaColor.a;

  return {
    r: Math.round(figmaColor.r * 255),
    g: Math.round(figmaColor.g * 255),
    b: Math.round(figmaColor.b * 255),
    a: Math.round(effectiveOpacity * 1000) / 1000, // round to 3 decimals
  };
}

/**
 * Convert a Figma RGB color (without alpha) to our Color type.
 *
 * @param figmaColor - The Figma RGB color (0-1 per channel)
 * @param alpha - The alpha value (0-1), defaults to 1
 * @returns Normalized Color
 */
export function figmaRgbToColor(figmaColor: RGB, alpha: number = 1): Color {
  return {
    r: Math.round(figmaColor.r * 255),
    g: Math.round(figmaColor.g * 255),
    b: Math.round(figmaColor.b * 255),
    a: Math.round(alpha * 1000) / 1000,
  };
}

/**
 * Convert a Color to a hex string.
 * If alpha is 1, returns #RRGGBB. Otherwise returns #RRGGBBAA.
 *
 * @param color - The Color object (r/g/b in 0-255, a in 0-1)
 * @returns Hex color string
 */
export function colorToHex(color: Color): string {
  const r = clampByte(color.r).toString(16).padStart(2, '0');
  const g = clampByte(color.g).toString(16).padStart(2, '0');
  const b = clampByte(color.b).toString(16).padStart(2, '0');

  if (color.a >= 0.999) {
    return `#${r}${g}${b}`;
  }

  const a = Math.round(color.a * 255)
    .toString(16)
    .padStart(2, '0');
  return `#${r}${g}${b}${a}`;
}

/**
 * Convert a Color to an rgba() CSS string.
 *
 * @param color - The Color object (r/g/b in 0-255, a in 0-1)
 * @returns CSS rgba() string, e.g., "rgba(255, 0, 128, 0.5)"
 */
export function colorToRgbaString(color: Color): string {
  const r = clampByte(color.r);
  const g = clampByte(color.g);
  const b = clampByte(color.b);
  const a = Math.round(color.a * 1000) / 1000;

  if (a >= 0.999) {
    return `rgb(${r}, ${g}, ${b})`;
  }

  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

/**
 * Check if a Color is fully transparent.
 */
export function isTransparent(color: Color): boolean {
  return color.a < 0.001;
}

/**
 * Check if two colors are visually identical (within tolerance).
 */
export function colorsEqual(a: Color, b: Color, tolerance: number = 1): boolean {
  return (
    Math.abs(a.r - b.r) <= tolerance &&
    Math.abs(a.g - b.g) <= tolerance &&
    Math.abs(a.b - b.b) <= tolerance &&
    Math.abs(a.a - b.a) <= 0.01
  );
}

/**
 * Clamp a value to valid byte range (0-255).
 */
function clampByte(value: number): number {
  return Math.max(0, Math.min(255, Math.round(value)));
}
