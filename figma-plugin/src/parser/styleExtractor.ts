/**
 * Style extractor: reads visual styles (fills, strokes, border radius, effects,
 * blend modes, overflow) from Figma nodes and maps them to our Style type.
 */

import type {
  Style,
  Fill,
  FillType,
  Stroke,
  Effect,
  EffectType,
  BorderRadius,
  Color,
  GradientStop,
  GradientTransform,
} from '../types/designSpec';
import { figmaColorToRgba, figmaRgbToColor } from '../utils/colorUtils';
import { roundPx } from '../utils/unitUtils';
import { hasFills, hasStrokes, hasEffects, hasCornerRadius } from '../utils/figmaHelpers';

/**
 * Extract all visual style properties from a Figma node.
 *
 * @param node - The Figma scene node
 * @returns Complete Style object
 */
export function extractStyle(node: SceneNode): Style {
  const style: Style = {
    fills: extractFills(node),
    strokes: extractStrokes(node),
    borderRadius: extractBorderRadius(node),
    effects: extractEffects(node),
    blendMode: extractBlendMode(node),
    overflow: extractOverflow(node),
  };

  if ('cornerSmoothing' in node) {
    const smoothing = (node as any).cornerSmoothing;
    if (typeof smoothing === 'number' && smoothing > 0) {
      style.cornerSmoothing = Math.round(smoothing * 1000) / 1000;
    }
  }

  if ('strokeTopWeight' in node && 'strokeWeight' in node) {
    const geoNode = node as GeometryMixin;
    if (geoNode.strokeWeight === figma.mixed) {
      const frame = node as FrameNode;
      style.strokeTopWeight = roundPx(frame.strokeTopWeight ?? 0);
      style.strokeRightWeight = roundPx((frame as any).strokeRightWeight ?? 0);
      style.strokeBottomWeight = roundPx(frame.strokeBottomWeight ?? 0);
      style.strokeLeftWeight = roundPx((frame as any).strokeLeftWeight ?? 0);
    }
  }

  return style;
}

// ─── Fills ────────────────────────────────────────────────────────────────────

/**
 * Extract fill layers from a node.
 * Handles SOLID, GRADIENT_LINEAR, GRADIENT_RADIAL, GRADIENT_ANGULAR,
 * GRADIENT_DIAMOND, and IMAGE fill types.
 */
function extractFills(node: SceneNode): Fill[] {
  if (!hasFills(node)) return [];

  const fills = (node as GeometryMixin).fills;
  if (fills === figma.mixed || !Array.isArray(fills)) return [];

  return fills.map((paint: Paint) => mapPaintToFill(paint));
}

/**
 * Map a single Figma Paint to our Fill type.
 */
function mapPaintToFill(paint: Paint): Fill {
  const base: Fill = {
    type: mapFillType(paint.type),
    visible: paint.visible !== false,
    opacity: paint.opacity ?? 1,
    blendMode: paint.blendMode ?? 'NORMAL',
  };

  switch (paint.type) {
    case 'SOLID': {
      const solidPaint = paint as SolidPaint;
      base.color = figmaRgbToColor(solidPaint.color, solidPaint.opacity ?? 1);
      break;
    }

    case 'GRADIENT_LINEAR':
    case 'GRADIENT_RADIAL':
    case 'GRADIENT_ANGULAR':
    case 'GRADIENT_DIAMOND': {
      const gradientPaint = paint as GradientPaint;
      base.gradientStops = gradientPaint.gradientStops.map((stop) =>
        mapGradientStop(stop)
      );
      if (gradientPaint.gradientTransform) {
        base.gradientTransform = gradientPaint.gradientTransform as GradientTransform;
      }
      break;
    }

    case 'IMAGE': {
      const imagePaint = paint as ImagePaint;
      base.imageHash = imagePaint.imageHash ?? undefined;
      base.scaleMode = imagePaint.scaleMode as Fill['scaleMode'];
      if (imagePaint.imageTransform) {
        base.imageTransform = imagePaint.imageTransform as Fill['imageTransform'];
      }
      break;
    }
  }

  return base;
}

/**
 * Map a Figma gradient stop to our GradientStop type.
 */
function mapGradientStop(stop: ColorStop): GradientStop {
  return {
    position: Math.round(stop.position * 1000) / 1000,
    color: figmaColorToRgba(stop.color),
  };
}

/**
 * Map Figma paint type string to our FillType enum.
 */
function mapFillType(type: string): FillType {
  switch (type) {
    case 'SOLID':
      return 'SOLID';
    case 'GRADIENT_LINEAR':
      return 'GRADIENT_LINEAR';
    case 'GRADIENT_RADIAL':
      return 'GRADIENT_RADIAL';
    case 'GRADIENT_ANGULAR':
      return 'GRADIENT_ANGULAR';
    case 'GRADIENT_DIAMOND':
      return 'GRADIENT_DIAMOND';
    case 'IMAGE':
      return 'IMAGE';
    default:
      return 'SOLID';
  }
}

// ─── Strokes ──────────────────────────────────────────────────────────────────

/**
 * Extract stroke properties from a node.
 */
function extractStrokes(node: SceneNode): Stroke[] {
  if (!hasStrokes(node)) return [];

  const geometryNode = node as GeometryMixin & IndividualStrokesMixin;
  const strokes = geometryNode.strokes;
  if (!Array.isArray(strokes) || strokes.length === 0) return [];

  // Get stroke weight - handle individual stroke weights if available
  const strokeWeight = getStrokeWeight(node);
  const strokeAlign = getStrokeAlign(node);

  return strokes.map((paint: Paint) => {
    const stroke: Stroke = {
      type: mapFillType(paint.type),
      visible: paint.visible !== false,
      opacity: paint.opacity ?? 1,
      weight: roundPx(strokeWeight),
      align: strokeAlign,
    };

    if (paint.type === 'SOLID') {
      const solidPaint = paint as SolidPaint;
      stroke.color = figmaRgbToColor(solidPaint.color, solidPaint.opacity ?? 1);
    }

    // Dash pattern
    if ('dashPattern' in geometryNode && Array.isArray(geometryNode.dashPattern) && geometryNode.dashPattern.length > 0) {
      stroke.dashPattern = geometryNode.dashPattern.map((v: number) => roundPx(v));
    }

    // Stroke cap
    if ('strokeCap' in geometryNode && geometryNode.strokeCap !== figma.mixed) {
      stroke.cap = geometryNode.strokeCap as string;
    }

    // Stroke join
    if ('strokeJoin' in geometryNode && geometryNode.strokeJoin !== figma.mixed) {
      stroke.join = geometryNode.strokeJoin as string;
    }

    return stroke;
  });
}

/**
 * Get the stroke weight from a node, handling the mixed case.
 */
function getStrokeWeight(node: SceneNode): number {
  if ('strokeWeight' in node) {
    const weight = (node as GeometryMixin).strokeWeight;
    if (typeof weight === 'number') {
      return weight;
    }
    // If mixed (per-side strokes), use the top stroke weight as representative
    if ('strokeTopWeight' in node) {
      return (node as FrameNode).strokeTopWeight ?? 1;
    }
  }
  return 0;
}

/**
 * Get the stroke alignment from a node.
 */
function getStrokeAlign(node: SceneNode): 'INSIDE' | 'OUTSIDE' | 'CENTER' {
  if ('strokeAlign' in node) {
    const align = (node as GeometryMixin).strokeAlign;
    if (align === 'INSIDE' || align === 'OUTSIDE' || align === 'CENTER') {
      return align;
    }
  }
  return 'CENTER';
}

// ─── Border Radius ────────────────────────────────────────────────────────────

/**
 * Extract border radius from a node.
 * Handles both uniform cornerRadius and individual corner radii.
 */
function extractBorderRadius(node: SceneNode): BorderRadius {
  if (!hasCornerRadius(node)) {
    return { topLeft: 0, topRight: 0, bottomRight: 0, bottomLeft: 0 };
  }

  const radiusNode = node as RectangleNode | FrameNode | ComponentNode | InstanceNode;
  const cornerRadius = radiusNode.cornerRadius;

  // Uniform corner radius
  if (typeof cornerRadius === 'number' && cornerRadius !== figma.mixed) {
    const r = roundPx(cornerRadius);
    return { topLeft: r, topRight: r, bottomRight: r, bottomLeft: r };
  }

  // Individual corner radii (cornerRadius is figma.mixed)
  return {
    topLeft: roundPx(radiusNode.topLeftRadius ?? 0),
    topRight: roundPx(radiusNode.topRightRadius ?? 0),
    bottomRight: roundPx(radiusNode.bottomRightRadius ?? 0),
    bottomLeft: roundPx(radiusNode.bottomLeftRadius ?? 0),
  };
}

// ─── Effects ──────────────────────────────────────────────────────────────────

/**
 * Extract effects (shadows, blurs) from a node.
 */
function extractEffects(node: SceneNode): Effect[] {
  if (!hasEffects(node)) return [];

  const blendNode = node as BlendMixin;
  if (!blendNode.effects || blendNode.effects.length === 0) return [];

  return blendNode.effects.map((effect) => mapEffect(effect));
}

/**
 * Map a single Figma effect to our Effect type.
 */
function mapEffect(effect: Effect_Figma): Effect {
  const base: Effect = {
    type: mapEffectType(effect.type),
    visible: effect.visible !== false,
    radius: roundPx(effect.radius ?? 0),
  };

  // Shadow-specific properties
  if (effect.type === 'DROP_SHADOW' || effect.type === 'INNER_SHADOW') {
    const shadowEffect = effect as DropShadowEffect | InnerShadowEffect;
    base.offsetX = roundPx(shadowEffect.offset?.x ?? 0);
    base.offsetY = roundPx(shadowEffect.offset?.y ?? 0);
    base.spread = roundPx(shadowEffect.spread ?? 0);
    base.blendMode = shadowEffect.blendMode ?? 'NORMAL';

    if (shadowEffect.color) {
      base.color = figmaColorToRgba(shadowEffect.color);
    }

    if ('showShadowBehindNode' in shadowEffect) {
      base.showShadowBehindNode = (shadowEffect as DropShadowEffect).showShadowBehindNode;
    }
  }

  return base;
}

/**
 * Type alias for Figma's Effect type to avoid name collision.
 */
type Effect_Figma = {
  type: string;
  visible?: boolean;
  radius?: number;
  offset?: { x: number; y: number };
  spread?: number;
  color?: RGBA;
  blendMode?: string;
  showShadowBehindNode?: boolean;
};

function mapEffectType(type: string): EffectType {
  switch (type) {
    case 'DROP_SHADOW':
      return 'DROP_SHADOW';
    case 'INNER_SHADOW':
      return 'INNER_SHADOW';
    case 'LAYER_BLUR':
      return 'LAYER_BLUR';
    case 'BACKGROUND_BLUR':
      return 'BACKGROUND_BLUR';
    default:
      return 'DROP_SHADOW';
  }
}

// ─── Blend Mode & Overflow ────────────────────────────────────────────────────

/**
 * Extract the blend mode from a node.
 */
function extractBlendMode(node: SceneNode): string {
  if ('blendMode' in node) {
    return (node as BlendMixin).blendMode ?? 'NORMAL';
  }
  return 'NORMAL';
}

/**
 * Extract overflow behavior from a node.
 * Maps Figma's clipsContent to visible/hidden.
 */
function extractOverflow(node: SceneNode): 'VISIBLE' | 'HIDDEN' | 'SCROLL' {
  if ('clipsContent' in node) {
    const frameNode = node as FrameNode;
    // Check for scrolling behavior
    if ('overflowDirection' in frameNode) {
      const overflow = (frameNode as any).overflowDirection;
      if (overflow && overflow !== 'NONE') {
        return 'SCROLL';
      }
    }
    return frameNode.clipsContent ? 'HIDDEN' : 'VISIBLE';
  }
  return 'VISIBLE';
}
