/**
 * Node extractor: recursively walks the Figma node tree, extracting
 * structural information and delegating to specialized extractors
 * for layout, style, text, and component data.
 */

import type { DesignNode, DesignNodeType } from '../types/designSpec';
import { extractLayout } from './layoutExtractor';
import { extractStyle } from './styleExtractor';
import { extractText } from './textExtractor';
import { extractComponent } from './componentExtractor';
import {
  isVisibleNode,
  hasChildren,
  isTextNode,
  getAbsoluteBounds,
  getNodeOpacity,
  shouldExportAsAsset,
} from '../utils/figmaHelpers';

/** Options for the node extraction process */
export interface NodeExtractorOptions {
  /** Whether to include invisible (hidden) nodes */
  includeInvisible: boolean;
  /** Maximum depth to traverse (0 = unlimited) */
  maxDepth: number;
  /** Callback for progress reporting */
  onProgress?: (processedCount: number, nodeName: string) => void;
}

/** Internal state for tracking progress during extraction */
interface ExtractionState {
  processedCount: number;
  options: NodeExtractorOptions;
  frameOffset: { x: number; y: number };
}

/**
 * Extract the design node tree from a Figma root node.
 * Recursively walks all children, extracting structural info, layout,
 * styles, text, and component data for each node.
 *
 * @param rootNode - The root Figma frame/component to extract
 * @param options - Extraction options (include invisible, max depth, etc.)
 * @returns Array of DesignNode objects representing the tree
 */
export function extractNodes(
  rootNode: SceneNode,
  options: NodeExtractorOptions
): DesignNode[] {
  // Calculate the root frame offset so all child positions are relative
  const absoluteBounds = rootNode.absoluteBoundingBox;
  const frameOffset = absoluteBounds
    ? { x: absoluteBounds.x, y: absoluteBounds.y }
    : { x: 0, y: 0 };

  const state: ExtractionState = {
    processedCount: 0,
    options,
    frameOffset,
  };

  // Extract the root node and its children
  const rootDesignNode = extractSingleNode(rootNode, state, 0);
  if (!rootDesignNode) {
    return [];
  }

  return [rootDesignNode];
}

/**
 * Extract a single Figma node into a DesignNode, recursing into children.
 *
 * @param node - The Figma scene node
 * @param state - Shared extraction state
 * @param depth - Current recursion depth
 * @returns DesignNode or null if the node should be skipped
 */
function extractSingleNode(
  node: SceneNode,
  state: ExtractionState,
  depth: number
): DesignNode | null {
  // Skip invisible nodes if configured
  if (!state.options.includeInvisible && !isVisibleNode(node)) {
    return null;
  }

  // Respect max depth
  if (state.options.maxDepth > 0 && depth > state.options.maxDepth) {
    return null;
  }

  // Report progress
  state.processedCount++;
  if (state.options.onProgress) {
    state.options.onProgress(state.processedCount, node.name);
  }

  // Build the DesignNode
  const designNode: DesignNode = {
    id: node.id,
    name: node.name,
    type: mapNodeType(node.type),
    visible: isVisibleNode(node),
    opacity: getNodeOpacity(node),
    bounds: getAbsoluteBounds(node, state.frameOffset),
    layout: extractLayout(node),
    style: extractStyle(node),
    children: [],
  };

  // Extract text properties for TEXT nodes
  if (isTextNode(node)) {
    designNode.text = extractText(node);
  }

  // Extract component info for INSTANCE and COMPONENT nodes
  if (
    node.type === 'INSTANCE' ||
    node.type === 'COMPONENT' ||
    node.type === 'COMPONENT_SET'
  ) {
    const componentInfo = extractComponent(node);
    if (componentInfo) {
      designNode.component = componentInfo;
    }
  }

  // Mark as asset if it should be exported as an image/SVG
  if (shouldExportAsAsset(node)) {
    designNode.isAsset = true;
  }

  // Check if node is a mask
  if ('isMask' in node && (node as any).isMask) {
    designNode.isMask = true;
  }

  // Extract export settings if present
  if ('exportSettings' in node) {
    const exportSettings = (node as FrameNode).exportSettings;
    if (exportSettings && exportSettings.length > 0) {
      designNode.exportSettings = exportSettings.map((es) => ({
        format: es.format as 'PNG' | 'SVG' | 'JPG' | 'PDF',
        suffix: es.suffix ?? '',
        constraint: {
          type: es.constraint?.type ?? 'SCALE',
          value: es.constraint?.value ?? 1,
        },
      }));
    }
  }

  // Recursively extract children.
  // Only skip children for leaf-type asset nodes (VECTOR, BOOLEAN_OPERATION, STAR, POLYGON).
  // Container nodes with IMAGE fills are no longer marked as assets, but as a safety net,
  // always extract children for container types even if isAsset is set.
  const isLeafAsset = designNode.isAsset &&
    ['VECTOR', 'BOOLEAN_OPERATION', 'STAR', 'POLYGON'].includes(node.type);
  if (hasChildren(node) && !isLeafAsset) {
    designNode.children = extractChildNodes(node, state, depth);
  }

  return designNode;
}

/**
 * Extract all child nodes from a container node.
 */
function extractChildNodes(
  parentNode: SceneNode & ChildrenMixin,
  state: ExtractionState,
  parentDepth: number
): DesignNode[] {
  const children: DesignNode[] = [];

  for (const child of parentNode.children) {
    const childNode = extractSingleNode(child, state, parentDepth + 1);
    if (childNode) {
      children.push(childNode);
    }
  }

  return children;
}

/**
 * Map Figma's node type string to our DesignNodeType.
 */
function mapNodeType(type: string): DesignNodeType {
  switch (type) {
    case 'FRAME':
      return 'FRAME';
    case 'TEXT':
      return 'TEXT';
    case 'RECTANGLE':
      return 'RECTANGLE';
    case 'ELLIPSE':
      return 'ELLIPSE';
    case 'VECTOR':
      return 'VECTOR';
    case 'GROUP':
      return 'GROUP';
    case 'INSTANCE':
      return 'INSTANCE';
    case 'COMPONENT':
      return 'COMPONENT';
    case 'COMPONENT_SET':
      return 'COMPONENT';
    case 'LINE':
      return 'LINE';
    case 'POLYGON':
      return 'POLYGON';
    case 'STAR':
      return 'STAR';
    case 'BOOLEAN_OPERATION':
      return 'BOOLEAN_OPERATION';
    case 'SECTION':
      return 'SECTION';
    default:
      return 'FRAME';
  }
}
