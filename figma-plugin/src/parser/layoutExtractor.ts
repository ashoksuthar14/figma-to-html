/**
 * Layout extractor: reads auto-layout and constraint information from Figma nodes
 * and converts them into our Layout type for CSS flexbox / positioning generation.
 */

import type {
  Layout,
  LayoutDirection,
  AxisAlign,
  CounterAxisAlign,
  LayoutWrap,
  Constraints,
  ConstraintType,
  Padding,
  SizingMode,
} from '../types/designSpec';
import { hasAutoLayout } from '../utils/figmaHelpers';
import { roundPx } from '../utils/unitUtils';

/**
 * Extract layout properties from a Figma scene node.
 *
 * @param node - The Figma scene node
 * @returns Layout specification object
 */
export function extractLayout(node: SceneNode): Layout {
  // Check if the node supports auto-layout
  if (hasAutoLayout(node)) {
    const layoutNode = node as FrameNode | ComponentNode | InstanceNode;

    // Check if auto-layout is actually enabled
    if (layoutNode.layoutMode && layoutNode.layoutMode !== 'NONE') {
      return extractAutoLayout(layoutNode);
    }
  }

  // For nodes inside auto-layout parents, extract sizing info
  const layout: Layout = {
    type: 'NONE',
  };

  // Extract constraints for absolutely positioned children
  if ('constraints' in node) {
    const constraintNode = node as FrameNode;
    layout.constraints = extractConstraints(constraintNode);
  }

  // Extract sizing mode if the node is a child of an auto-layout frame
  if ('layoutSizingHorizontal' in node) {
    const sizingNode = node as FrameNode;
    layout.primaryAxisSizing = mapSizingMode(sizingNode.layoutSizingHorizontal);
    layout.counterAxisSizing = mapSizingMode(sizingNode.layoutSizingVertical);
  }

  // Check if positioned absolutely within an auto-layout parent
  if ('layoutPositioning' in node) {
    const posNode = node as FrameNode;
    if (posNode.layoutPositioning === 'ABSOLUTE') {
      layout.positionType = 'ABSOLUTE';
    }
  }

  return layout;
}

/**
 * Extract auto-layout (flexbox) properties from a layout-enabled frame.
 */
function extractAutoLayout(node: FrameNode | ComponentNode | InstanceNode): Layout {
  const direction = mapLayoutDirection(node.layoutMode);
  const padding = extractPadding(node);
  const gap = roundPx(node.itemSpacing ?? 0);

  const layout: Layout = {
    type: 'AUTO_LAYOUT',
    direction,
    gap,
    padding,
    primaryAxisAlign: mapPrimaryAxisAlign(node.primaryAxisAlignItems),
    counterAxisAlign: mapCounterAxisAlign(node.counterAxisAlignItems),
  };

  // Layout wrap (Figma supports WRAP since late 2023)
  if ('layoutWrap' in node) {
    layout.wrap = mapLayoutWrap((node as FrameNode).layoutWrap);
  }

  // Sizing mode of this node
  if ('layoutSizingHorizontal' in node) {
    layout.primaryAxisSizing = mapSizingMode(node.layoutSizingHorizontal);
    layout.counterAxisSizing = mapSizingMode(node.layoutSizingVertical);
  }

  return layout;
}

/**
 * Extract padding from a frame's individual padding properties.
 */
function extractPadding(node: FrameNode | ComponentNode | InstanceNode): Padding {
  return {
    top: roundPx(node.paddingTop ?? 0),
    right: roundPx(node.paddingRight ?? 0),
    bottom: roundPx(node.paddingBottom ?? 0),
    left: roundPx(node.paddingLeft ?? 0),
  };
}

/**
 * Extract constraints from a node (used for absolute positioning).
 */
function extractConstraints(node: FrameNode | SceneNode): Constraints {
  if (!('constraints' in node)) {
    return { horizontal: 'MIN', vertical: 'MIN' };
  }

  const constraints = (node as FrameNode).constraints;
  if (!constraints) {
    return { horizontal: 'MIN', vertical: 'MIN' };
  }

  return {
    horizontal: mapConstraintType(constraints.horizontal),
    vertical: mapConstraintType(constraints.vertical),
  };
}

// ─── Mapping helpers ──────────────────────────────────────────────────────────

function mapLayoutDirection(mode: string): LayoutDirection {
  switch (mode) {
    case 'HORIZONTAL':
      return 'HORIZONTAL';
    case 'VERTICAL':
      return 'VERTICAL';
    default:
      return 'VERTICAL';
  }
}

function mapPrimaryAxisAlign(align: string): AxisAlign {
  switch (align) {
    case 'MIN':
      return 'MIN';
    case 'CENTER':
      return 'CENTER';
    case 'MAX':
      return 'MAX';
    case 'SPACE_BETWEEN':
      return 'SPACE_BETWEEN';
    default:
      return 'MIN';
  }
}

function mapCounterAxisAlign(align: string): CounterAxisAlign {
  switch (align) {
    case 'MIN':
      return 'MIN';
    case 'CENTER':
      return 'CENTER';
    case 'MAX':
      return 'MAX';
    case 'BASELINE':
      return 'BASELINE';
    default:
      return 'MIN';
  }
}

function mapLayoutWrap(wrap: string | undefined): LayoutWrap {
  if (wrap === 'WRAP') return 'WRAP';
  return 'NO_WRAP';
}

function mapConstraintType(type: string): ConstraintType {
  switch (type) {
    case 'MIN':
      return 'MIN';
    case 'CENTER':
      return 'CENTER';
    case 'MAX':
      return 'MAX';
    case 'STRETCH':
      return 'STRETCH';
    case 'SCALE':
      return 'SCALE';
    default:
      return 'MIN';
  }
}

function mapSizingMode(mode: string | undefined): SizingMode {
  switch (mode) {
    case 'FIXED':
      return 'FIXED';
    case 'HUG':
      return 'HUG';
    case 'FILL':
      return 'FILL';
    default:
      return 'FIXED';
  }
}
