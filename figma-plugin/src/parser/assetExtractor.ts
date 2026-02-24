/**
 * Asset extractor: identifies nodes that should be exported as raster or vector
 * assets (images, complex SVGs) and exports them using Figma's exportAsync API.
 */

import type { AssetReference } from '../types/designSpec';
import { hasImageFills, shouldExportAsAsset, hasChildren } from '../utils/figmaHelpers';

/** Format to MIME type mapping */
const FORMAT_MIME_MAP: Record<string, string> = {
  PNG: 'image/png',
  SVG: 'image/svg+xml',
  JPG: 'image/jpeg',
  PDF: 'application/pdf',
};

/**
 * Identify and export all asset nodes in the tree.
 * This recursively walks the node tree, finds nodes that need to be exported
 * as images/SVGs, and calls exportAsync on each.
 *
 * @param rootNode - The root frame to scan
 * @param settings - Export settings (format, scale)
 * @param onProgress - Optional progress callback
 * @returns Array of AssetReference with base64-encoded data
 */
export async function extractAssets(
  rootNode: SceneNode,
  settings: { format: 'PNG' | 'SVG'; scale: number },
  onProgress?: (current: number, total: number, nodeName: string) => void
): Promise<AssetReference[]> {
  // First pass: collect all nodes that need to be exported
  const assetNodes = collectAssetNodes(rootNode);

  if (assetNodes.length === 0) {
    return [];
  }

  const assets: AssetReference[] = [];
  let processed = 0;

  for (const node of assetNodes) {
    try {
      if (onProgress) {
        onProgress(processed, assetNodes.length, node.name);
      }

      const asset = await exportNode(node, settings);
      if (asset) {
        assets.push(asset);
      }
    } catch (error) {
      // Log the error but continue exporting other assets
      console.error(`Failed to export asset "${node.name}" (${node.id}):`, error);
    }

    processed++;
  }

  if (onProgress) {
    onProgress(assetNodes.length, assetNodes.length, 'Done');
  }

  return assets;
}

/**
 * Recursively collect all nodes that should be exported as assets.
 */
function collectAssetNodes(node: SceneNode): SceneNode[] {
  const result: SceneNode[] = [];

  if (shouldExportAsAsset(node)) {
    result.push(node);
    // Don't recurse into asset nodes - they'll be exported as a whole
    return result;
  }

  // Recurse into children
  if (hasChildren(node)) {
    for (const child of node.children) {
      result.push(...collectAssetNodes(child));
    }
  }

  return result;
}

/**
 * Export a single node as an asset.
 *
 * @param node - The node to export
 * @param settings - Format and scale settings
 * @returns AssetReference with base64 data, or null if export fails
 */
async function exportNode(
  node: SceneNode,
  settings: { format: 'PNG' | 'SVG'; scale: number }
): Promise<AssetReference | null> {
  // Determine the best format for this node
  const format = determineExportFormat(node, settings.format);
  const scale = format === 'SVG' ? 1 : settings.scale;

  // Build the export settings for Figma's API
  const exportSettings: ExportSettings_Figma = buildExportSettings(format, scale);

  // Call Figma's exportAsync
  const bytes = await (node as FrameNode).exportAsync(exportSettings);

  if (!bytes || bytes.length === 0) {
    return null;
  }

  // Convert Uint8Array to base64
  const base64 = uint8ArrayToBase64(bytes);

  return {
    nodeId: node.id,
    nodeName: sanitizeAssetName(node.name),
    format,
    scale,
    data: base64,
    byteSize: bytes.length,
    mimeType: FORMAT_MIME_MAP[format] ?? 'application/octet-stream',
  };
}

/**
 * Determine the best export format for a given node.
 * Vectors and simple shapes are better as SVG; nodes with image fills as PNG.
 */
function determineExportFormat(
  node: SceneNode,
  preferredFormat: 'PNG' | 'SVG'
): 'PNG' | 'SVG' | 'JPG' | 'PDF' {
  // If node has image fills, always use raster format
  if (hasImageFills(node)) {
    return 'PNG';
  }

  // Vectors and boolean operations are best as SVG
  if (
    node.type === 'VECTOR' ||
    node.type === 'BOOLEAN_OPERATION' ||
    node.type === 'STAR' ||
    node.type === 'POLYGON' ||
    node.type === 'LINE'
  ) {
    return 'SVG';
  }

  // Check if the node has explicit export settings
  if ('exportSettings' in node) {
    const nodeExportSettings = (node as FrameNode).exportSettings;
    if (nodeExportSettings && nodeExportSettings.length > 0) {
      const first = nodeExportSettings[0];
      if (first.format === 'PNG' || first.format === 'SVG' || first.format === 'JPG' || first.format === 'PDF') {
        return first.format;
      }
    }
  }

  return preferredFormat;
}

/**
 * Build Figma export settings object.
 */
type ExportSettings_Figma = {
  format: 'PNG' | 'SVG' | 'JPG' | 'PDF';
  constraint?: { type: 'SCALE'; value: number };
  svgOutlineText?: boolean;
  svgIdAttribute?: boolean;
  svgSimplifyStroke?: boolean;
};

function buildExportSettings(format: 'PNG' | 'SVG' | 'JPG' | 'PDF', scale: number): ExportSettings_Figma {
  const settings: ExportSettings_Figma = { format };

  if (format === 'PNG' || format === 'JPG') {
    settings.constraint = { type: 'SCALE', value: scale };
  }

  if (format === 'SVG') {
    settings.svgOutlineText = true;
    settings.svgIdAttribute = true;
    settings.svgSimplifyStroke = true;
  }

  return settings;
}

/**
 * Base64 character lookup table.
 */
const BASE64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

/**
 * Convert a Uint8Array to a base64-encoded string.
 * Uses a pure JS implementation since the Figma plugin sandbox (QuickJS)
 * does NOT have btoa/atob available.
 */
export function uint8ArrayToBase64(bytes: Uint8Array): string {
  const len = bytes.byteLength;
  const parts: string[] = [];

  for (let i = 0; i < len; i += 3) {
    const b0 = bytes[i];
    const b1 = i + 1 < len ? bytes[i + 1] : 0;
    const b2 = i + 2 < len ? bytes[i + 2] : 0;

    parts.push(BASE64_CHARS[(b0 >> 2) & 0x3f]);
    parts.push(BASE64_CHARS[((b0 << 4) | (b1 >> 4)) & 0x3f]);
    parts.push(i + 1 < len ? BASE64_CHARS[((b1 << 2) | (b2 >> 6)) & 0x3f] : '=');
    parts.push(i + 2 < len ? BASE64_CHARS[b2 & 0x3f] : '=');
  }

  return parts.join('');
}

/**
 * Sanitize a node name for use as a file name.
 * Removes special characters and replaces spaces with hyphens.
 */
function sanitizeAssetName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9\s\-_]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .substring(0, 64) || 'asset';
}

/**
 * Collect background image fills from container nodes that have children.
 * These containers are NOT flattened to assets (their children are preserved),
 * but their IMAGE fill data needs to be exported separately so the backend
 * can use it as background-image.
 */
function collectBackgroundImageFills(node: SceneNode): { nodeId: string; hash: string }[] {
  const result: { nodeId: string; hash: string }[] = [];

  // Container with IMAGE fill AND children → export the background image separately
  if (hasImageFills(node) && hasChildren(node) && (node as FrameNode).children.length > 0) {
    const geoNode = node as GeometryMixin;
    const fills = geoNode.fills;
    if (fills !== figma.mixed && Array.isArray(fills)) {
      for (const fill of fills) {
        if (fill.type === 'IMAGE' && fill.visible !== false && (fill as ImagePaint).imageHash) {
          result.push({ nodeId: node.id, hash: (fill as ImagePaint).imageHash! });
        }
      }
    }
  }

  // Recurse into children
  if (hasChildren(node)) {
    for (const child of (node as FrameNode).children) {
      result.push(...collectBackgroundImageFills(child));
    }
  }

  return result;
}

/**
 * Export background image assets from container nodes with IMAGE fills.
 * Uses figma.getImageByHash() to get just the raw fill image data
 * (without rendering the node's children on top).
 */
export async function extractBackgroundAssets(rootNode: SceneNode): Promise<AssetReference[]> {
  const bgFills = collectBackgroundImageFills(rootNode);
  if (bgFills.length === 0) return [];

  const assets: AssetReference[] = [];
  const seenHashes = new Set<string>();

  for (const { hash } of bgFills) {
    if (seenHashes.has(hash)) continue;
    seenHashes.add(hash);

    try {
      const image = figma.getImageByHash(hash);
      if (!image) continue;

      const bytes = await image.getBytesAsync();
      if (!bytes || bytes.length === 0) continue;

      const base64 = uint8ArrayToBase64(bytes);
      assets.push({
        nodeId: `bg-${hash}`,
        nodeName: `bg-${hash}`,
        format: 'PNG',
        scale: 1,
        data: base64,
        byteSize: bytes.length,
        mimeType: 'image/png',
      });
    } catch (error) {
      console.error(`Failed to export background image hash ${hash}:`, error);
    }
  }

  return assets;
}

/**
 * Check if a node's assets have already been processed (for deduplication).
 * Nodes with the same image hash can share assets.
 */
export function deduplicateAssets(assets: AssetReference[]): AssetReference[] {
  const seen = new Set<string>();
  const unique: AssetReference[] = [];

  for (const asset of assets) {
    // Use nodeId as the dedup key since each node is unique
    if (!seen.has(asset.nodeId)) {
      seen.add(asset.nodeId);
      unique.push(asset);
    }
  }

  return unique;
}
