/**
 * Helper functions for working with the Figma plugin API.
 * Provides type guards, node inspection utilities, and coordinate helpers.
 */

import type { Bounds } from '../types/designSpec';
import { roundPx } from './unitUtils';

/**
 * Check if a node is visible (not hidden by the user in the layers panel
 * and has non-zero opacity).
 *
 * @param node - The Figma scene node
 * @returns true if the node is visible
 */
export function isVisibleNode(node: SceneNode): boolean {
  return node.visible !== false;
}

/**
 * Type guard: check if a node can have children.
 * In the Figma API, these node types contain a `children` property.
 */
export function hasChildren(
  node: SceneNode
): node is FrameNode | GroupNode | ComponentNode | InstanceNode | BooleanOperationNode | SectionNode | ComponentSetNode {
  return (
    node.type === 'FRAME' ||
    node.type === 'GROUP' ||
    node.type === 'COMPONENT' ||
    node.type === 'INSTANCE' ||
    node.type === 'BOOLEAN_OPERATION' ||
    node.type === 'SECTION' ||
    node.type === 'COMPONENT_SET'
  );
}

/**
 * Type guard: check if a node supports fills.
 */
export function hasFills(
  node: SceneNode
): node is GeometryMixin & SceneNode {
  return 'fills' in node && node.type !== 'GROUP' && node.type !== 'SLICE';
}

/**
 * Type guard: check if a node supports strokes.
 */
export function hasStrokes(
  node: SceneNode
): node is GeometryMixin & SceneNode {
  return 'strokes' in node;
}

/**
 * Type guard: check if a node supports effects (shadows, blurs).
 */
export function hasEffects(
  node: SceneNode
): node is BlendMixin & SceneNode {
  return 'effects' in node;
}

/**
 * Type guard: check if a node has corner radius properties.
 */
export function hasCornerRadius(
  node: SceneNode
): node is (RectangleNode | FrameNode | ComponentNode | InstanceNode) & SceneNode {
  return 'cornerRadius' in node;
}

/**
 * Type guard: check if a node has auto-layout (flexbox) properties.
 */
export function hasAutoLayout(
  node: SceneNode
): node is FrameNode | ComponentNode | InstanceNode {
  return (
    (node.type === 'FRAME' || node.type === 'COMPONENT' || node.type === 'INSTANCE') &&
    'layoutMode' in node
  );
}

/**
 * Type guard: check if a node is a text node.
 */
export function isTextNode(node: SceneNode): node is TextNode {
  return node.type === 'TEXT';
}

/**
 * Get the absolute bounding box of a node relative to a root frame offset.
 * This converts Figma's absolute coordinates into coordinates relative to
 * the exported root frame, making the output portable.
 *
 * @param node - The Figma scene node
 * @param frameOffset - The x/y position of the root frame in Figma's canvas
 * @returns Bounds relative to the root frame
 */
export function getAbsoluteBounds(
  node: SceneNode,
  frameOffset: { x: number; y: number }
): Bounds {
  const absBounds = node.absoluteBoundingBox;

  if (!absBounds) {
    // Fallback for nodes without absoluteBoundingBox (rare edge case)
    return {
      x: 0,
      y: 0,
      width: 0,
      height: 0,
      rotation: 0,
    };
  }

  const bounds: Bounds = {
    x: roundPx(absBounds.x - frameOffset.x),
    y: roundPx(absBounds.y - frameOffset.y),
    width: roundPx(absBounds.width),
    height: roundPx(absBounds.height),
  };

  // Include rotation if the node is rotated
  if ('rotation' in node && typeof node.rotation === 'number' && node.rotation !== 0) {
    bounds.rotation = roundPx(node.rotation);
  }

  return bounds;
}

/**
 * Get the render bounds of a node (includes effects like shadows that
 * extend beyond the node's geometry).
 */
export function getRenderBounds(
  node: SceneNode,
  frameOffset: { x: number; y: number }
): Bounds {
  const renderBounds = node.absoluteRenderBounds;

  if (!renderBounds) {
    return getAbsoluteBounds(node, frameOffset);
  }

  return {
    x: roundPx(renderBounds.x - frameOffset.x),
    y: roundPx(renderBounds.y - frameOffset.y),
    width: roundPx(renderBounds.width),
    height: roundPx(renderBounds.height),
  };
}

/**
 * Get the number of all descendant nodes in a subtree.
 * Useful for estimating export complexity and progress.
 */
export function countDescendants(node: SceneNode): number {
  let count = 1;
  if (hasChildren(node)) {
    for (const child of node.children) {
      count += countDescendants(child);
    }
  }
  return count;
}

/**
 * Check if a node has image fills that need to be exported as assets.
 */
export function hasImageFills(node: SceneNode): boolean {
  if (!hasFills(node)) return false;
  const fills = node.fills;
  if (fills === figma.mixed || !Array.isArray(fills)) return false;
  return fills.some(
    (fill: Paint) => fill.type === 'IMAGE' && fill.visible !== false
  );
}

/**
 * Check if a node is a simple shape that can be rendered purely with CSS.
 * Always returns false so all shapes are exported as assets (no filtering).
 */
export function isSimpleCssShape(node: SceneNode): boolean {
  return false;
}

/**
 * Check if a node should be exported as a raster/vector asset rather
 * than being converted to HTML/CSS elements.
 */
export function shouldExportAsAsset(node: SceneNode): boolean {
  // Simple CSS-renderable shapes should NOT be exported as assets
  if (isSimpleCssShape(node)) {
    return false;
  }

  // Container nodes with children should NOT be flattened to assets.
  // Their children contain semantic content that must be preserved.
  // Background images on containers are exported separately via getImageByHash().
  if (hasChildren(node)) {
    const children = (node as FrameNode).children;
    if (children && children.length > 0) {
      return false;
    }
  }

  // Nodes with explicit export settings (leaf nodes only at this point)
  if ('exportSettings' in node) {
    const settings = (node as FrameNode).exportSettings;
    if (settings && settings.length > 0) {
      return true;
    }
  }

  // Nodes with image fills
  if (hasImageFills(node)) {
    return true;
  }

  // Complex vector nodes that cannot be represented in CSS
  if (node.type === 'VECTOR' || node.type === 'BOOLEAN_OPERATION') {
    return true;
  }

  // Lines, stars, and polygons are better as SVGs
  if (node.type === 'LINE' || node.type === 'STAR' || node.type === 'POLYGON') {
    return true;
  }

  // Diamond gradients have no CSS equivalent — export as PNG
  if (hasFills(node)) {
    const fills = (node as GeometryMixin).fills;
    if (fills !== figma.mixed && Array.isArray(fills)) {
      const hasDiamondGradient = fills.some(
        (f: Paint) => f.type === 'GRADIENT_DIAMOND' && f.visible !== false
      );
      if (hasDiamondGradient) {
        return true;
      }
    }
  }

  // Ellipses with non-default arcs (partial circles, donuts) can't be
  // represented with CSS border-radius alone — export as SVG
  if (node.type === 'ELLIPSE') {
    const ellipse = node as EllipseNode;
    if (
      ellipse.arcData &&
      (ellipse.arcData.startingAngle !== 0 ||
        ellipse.arcData.endingAngle !== Math.PI * 2 ||
        ellipse.arcData.innerRadius !== 0)
    ) {
      return true;
    }
  }

  // Mask nodes should be exported as SVG for clip-path usage
  if ('isMask' in node && (node as any).isMask) {
    return true;
  }

  // Multiple fills with non-NORMAL per-fill blend modes can't be composited
  // correctly via CSS — export as PNG
  if (hasFills(node)) {
    const fills = (node as GeometryMixin).fills;
    if (fills !== figma.mixed && Array.isArray(fills) && fills.length > 1) {
      const hasBlendMode = fills.some(
        (f: Paint) => f.visible !== false && f.blendMode && f.blendMode !== 'NORMAL' && f.blendMode !== 'PASS_THROUGH'
      );
      if (hasBlendMode) {
        return true;
      }
    }
  }

  // Nodes with cornerSmoothing (squircle shapes) can't be accurately
  // represented by CSS border-radius — export as SVG
  if ('cornerSmoothing' in node) {
    const smoothing = (node as any).cornerSmoothing;
    if (typeof smoothing === 'number' && smoothing > 0) {
      return true;
    }
  }

  return false;
}

/**
 * Get the opacity of a node, handling edge cases.
 */
export function getNodeOpacity(node: SceneNode): number {
  if ('opacity' in node) {
    return typeof node.opacity === 'number' ? node.opacity : 1;
  }
  return 1;
}
