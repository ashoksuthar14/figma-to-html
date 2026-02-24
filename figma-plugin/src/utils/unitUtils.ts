/**
 * Numeric utility functions for unit conversion, rounding, and clamping.
 * Ensures consistent precision throughout the design spec extraction.
 */

/**
 * Round a pixel value to 1 decimal place.
 * This provides enough precision for CSS rendering while keeping
 * the output clean and readable.
 *
 * @param value - The raw pixel value
 * @returns The value rounded to 1 decimal place
 *
 * @example
 * roundPx(12.34567) // => 12.3
 * roundPx(100)      // => 100
 * roundPx(0.05)     // => 0.1
 */
export function roundPx(value: number): number {
  return Math.round(value * 10) / 10;
}

/**
 * Round a value to a specified number of decimal places.
 *
 * @param value - The raw value
 * @param decimals - Number of decimal places (default 2)
 * @returns The rounded value
 */
export function roundTo(value: number, decimals: number = 2): number {
  const factor = Math.pow(10, decimals);
  return Math.round(value * factor) / factor;
}

/**
 * Clamp a numeric value between a minimum and maximum.
 *
 * @param value - The value to clamp
 * @param min - Minimum allowed value
 * @param max - Maximum allowed value
 * @returns The clamped value
 *
 * @example
 * clamp(150, 0, 100)  // => 100
 * clamp(-5, 0, 100)   // => 0
 * clamp(50, 0, 100)   // => 50
 */
export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/**
 * Convert a Figma percentage value (0-100) to a normalized fraction (0-1).
 */
export function percentToFraction(percent: number): number {
  return clamp(percent / 100, 0, 1);
}

/**
 * Convert a normalized fraction (0-1) to a percentage (0-100).
 */
export function fractionToPercent(fraction: number): number {
  return roundTo(clamp(fraction, 0, 1) * 100, 1);
}

/**
 * Check if a number is effectively zero (within floating point tolerance).
 */
export function isNearZero(value: number, tolerance: number = 0.001): boolean {
  return Math.abs(value) < tolerance;
}

/**
 * Convert degrees to radians.
 */
export function degToRad(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

/**
 * Convert radians to degrees.
 */
export function radToDeg(radians: number): number {
  return (radians * 180) / Math.PI;
}

/**
 * Normalize an angle to the 0-360 degree range.
 */
export function normalizeAngle(degrees: number): number {
  const normalized = degrees % 360;
  return normalized < 0 ? normalized + 360 : normalized;
}
