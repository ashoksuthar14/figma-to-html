/**
 * Main parser orchestrator: coordinates all extractors to build a complete
 * DesignSpec from a selected Figma frame.
 *
 * This is the primary entry point for the extraction pipeline:
 * 1. Validate the selection
 * 2. Extract the node tree (structure, layout, styles, text, components)
 * 3. Export assets (images, complex vectors)
 * 4. Assemble the complete DesignSpec
 */

import type { DesignSpec, AssetReference, DesignNode } from '../types/designSpec';
import type { ExportSettings } from '../types/messages';
import { extractNodes, NodeExtractorOptions } from './nodeExtractor';
import { extractAssets, extractBackgroundAssets, deduplicateAssets, uint8ArrayToBase64 } from './assetExtractor';
import { countDescendants } from '../utils/figmaHelpers';

/** Plugin version for the DesignSpec metadata */
const PLUGIN_VERSION = '1.0.0';

/** Design spec schema version */
const SCHEMA_VERSION = '1.0';

/** Progress callback type */
export type ProgressCallback = (step: string, progress: number, detail?: string) => void;

/**
 * Parse a selected Figma frame into a complete DesignSpec.
 *
 * @param frameNode - The selected frame node to parse
 * @param settings - Export settings from the UI
 * @param onProgress - Callback for reporting progress to the UI
 * @returns Complete DesignSpec ready to send to the backend
 */
export async function parseFrame(
  frameNode: FrameNode | ComponentNode | InstanceNode | SectionNode,
  settings: ExportSettings,
  onProgress?: ProgressCallback
): Promise<DesignSpec> {
  const startTime = Date.now();

  // ── Step 1: Count nodes for progress estimation ────────────────────────────
  reportProgress(onProgress, 'Analyzing frame structure...', 0.05);
  const totalNodes = countDescendants(frameNode);
  let extractedCount = 0;

  // ── Step 2: Extract the node tree ──────────────────────────────────────────
  reportProgress(onProgress, 'Extracting node tree...', 0.1, `${totalNodes} nodes found`);

  const extractorOptions: NodeExtractorOptions = {
    includeInvisible: settings.includeInvisible,
    maxDepth: settings.maxDepth,
    onProgress: (count: number, nodeName: string) => {
      extractedCount = count;
      const progress = 0.1 + (count / totalNodes) * 0.5; // 10% to 60%
      reportProgress(
        onProgress,
        'Extracting nodes...',
        Math.min(progress, 0.6),
        `${count}/${totalNodes}: ${nodeName}`
      );
    },
  };

  const nodes = extractNodes(frameNode, extractorOptions);

  reportProgress(
    onProgress,
    'Node extraction complete',
    0.6,
    `${extractedCount} nodes extracted`
  );

  // ── Step 3: Export assets ──────────────────────────────────────────────────
  let assets: AssetReference[] = [];

  if (settings.exportAssets) {
    reportProgress(onProgress, 'Exporting assets...', 0.65);

    const assetCount = countAssetNodes(nodes);
    let assetsProcessed = 0;

    assets = await extractAssets(
      frameNode,
      { format: settings.assetFormat, scale: settings.assetScale },
      (current: number, total: number, name: string) => {
        assetsProcessed = current;
        const progress = 0.65 + (current / Math.max(total, 1)) * 0.2; // 65% to 85%
        reportProgress(
          onProgress,
          'Exporting assets...',
          Math.min(progress, 0.85),
          `${current}/${total}: ${name}`
        );
      }
    );

    // Deduplicate assets
    assets = deduplicateAssets(assets);

    // Export background images from containers with IMAGE fills.
    // These containers are not flattened (their children are preserved),
    // but the background image data needs to be exported separately.
    reportProgress(onProgress, 'Exporting background images...', 0.82);
    try {
      const bgAssets = await extractBackgroundAssets(frameNode);
      if (bgAssets.length > 0) {
        assets.push(...bgAssets);
        reportProgress(
          onProgress,
          'Background images exported',
          0.84,
          `${bgAssets.length} background images`
        );
      }
    } catch (err) {
      console.error('Background image export failed:', err);
    }

    reportProgress(
      onProgress,
      'Asset export complete',
      0.85,
      `${assets.length} assets exported`
    );
  } else {
    reportProgress(onProgress, 'Skipping asset export', 0.85);
  }

  // ── Step 3b: Capture frame screenshot for visual verification ────────────
  reportProgress(onProgress, 'Capturing frame screenshot...', 0.87);
  let frameScreenshot: string | undefined;
  try {
    const screenshotBytes = await frameNode.exportAsync({
      format: 'PNG',
      constraint: { type: 'SCALE', value: 2 },
    });
    frameScreenshot = uint8ArrayToBase64(screenshotBytes);
    reportProgress(
      onProgress,
      'Frame screenshot captured',
      0.89,
      `${screenshotBytes.byteLength} bytes (base64: ${frameScreenshot.length} chars)`
    );
  } catch (err) {
    // Screenshot capture is non-critical, continue without it
    console.error('Frame screenshot capture failed:', err);
    reportProgress(
      onProgress,
      'Frame screenshot skipped',
      0.89,
      `Error: ${err instanceof Error ? err.message : String(err)}`
    );
  }

  // ── Step 4: Assemble the DesignSpec ────────────────────────────────────────
  reportProgress(onProgress, 'Assembling design specification...', 0.9);

  const absoluteBounds = frameNode.absoluteBoundingBox;
  const frameWidth = absoluteBounds ? absoluteBounds.width : 0;
  const frameHeight = absoluteBounds ? absoluteBounds.height : 0;

  const designSpec: DesignSpec = {
    version: SCHEMA_VERSION,
    metadata: {
      fileName: getFileName(),
      lastModified: new Date().toISOString(),
      pluginVersion: PLUGIN_VERSION,
    },
    frameName: frameNode.name,
    frameWidth: Math.round(frameWidth),
    frameHeight: Math.round(frameHeight),
    nodes,
    assets,
  };

  // Attach frame screenshot if captured
  if (frameScreenshot) {
    designSpec.frameScreenshot = frameScreenshot;
  }

  // ── Step 5: Extract global styles (if available) ───────────────────────────
  try {
    const colorStyles = extractColorStyles();
    if (colorStyles && Object.keys(colorStyles).length > 0) {
      designSpec.colorStyles = colorStyles;
    }

    const textStyles = extractTextStyles();
    if (textStyles && Object.keys(textStyles).length > 0) {
      designSpec.textStyles = textStyles;
    }
  } catch {
    // Style extraction is non-critical, continue without it
  }

  const elapsed = Date.now() - startTime;
  reportProgress(
    onProgress,
    'Design specification ready',
    1.0,
    `Completed in ${(elapsed / 1000).toFixed(1)}s`
  );

  return designSpec;
}

/**
 * Count the number of asset nodes in the extracted tree.
 */
function countAssetNodes(nodes: DesignNode[]): number {
  let count = 0;
  for (const node of nodes) {
    if (node.isAsset) count++;
    count += countAssetNodes(node.children);
  }
  return count;
}

/**
 * Report progress to the callback if available.
 */
function reportProgress(
  callback: ProgressCallback | undefined,
  step: string,
  progress: number,
  detail?: string
): void {
  if (callback) {
    callback(step, Math.round(progress * 100) / 100, detail);
  }
}

/**
 * Get the current Figma file name.
 */
function getFileName(): string {
  try {
    return figma.root.name ?? 'Untitled';
  } catch {
    return 'Untitled';
  }
}

/**
 * Extract local color styles from the Figma file.
 */
function extractColorStyles(): Record<string, { name: string; color: { r: number; g: number; b: number; a: number } }> | undefined {
  try {
    const paintStyles = figma.getLocalPaintStyles();
    if (!paintStyles || paintStyles.length === 0) return undefined;

    const result: Record<string, { name: string; color: { r: number; g: number; b: number; a: number } }> = {};

    for (const style of paintStyles) {
      if (style.paints.length > 0) {
        const firstPaint = style.paints[0];
        if (firstPaint.type === 'SOLID') {
          const solid = firstPaint as SolidPaint;
          result[style.id] = {
            name: style.name,
            color: {
              r: Math.round(solid.color.r * 255),
              g: Math.round(solid.color.g * 255),
              b: Math.round(solid.color.b * 255),
              a: solid.opacity ?? 1,
            },
          };
        }
      }
    }

    return Object.keys(result).length > 0 ? result : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Extract local text styles from the Figma file.
 */
function extractTextStyles(): Record<string, { name: string; fontFamily: string; fontSize: number; fontWeight: number }> | undefined {
  try {
    const textStyles = figma.getLocalTextStyles();
    if (!textStyles || textStyles.length === 0) return undefined;

    const result: Record<string, { name: string; fontFamily: string; fontSize: number; fontWeight: number }> = {};

    for (const style of textStyles) {
      const fontName = style.fontName as FontName;
      result[style.id] = {
        name: style.name,
        fontFamily: fontName?.family ?? 'Inter',
        fontSize: style.fontSize as number,
        fontWeight: mapFontStyleToWeight(fontName?.style ?? 'Regular'),
      };
    }

    return Object.keys(result).length > 0 ? result : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Map font style string to numeric weight (same logic as textExtractor).
 */
function mapFontStyleToWeight(style: string): number {
  const lower = style.toLowerCase().replace(/[- ]/g, '');
  if (lower.includes('thin')) return 100;
  if (lower.includes('extralight') || lower.includes('ultralight')) return 200;
  if (lower.includes('light')) return 300;
  if (lower.includes('regular') || lower.includes('normal')) return 400;
  if (lower.includes('medium')) return 500;
  if (lower.includes('semibold') || lower.includes('demibold')) return 600;
  if (lower.includes('extrabold') || lower.includes('ultrabold')) return 800;
  if (lower.includes('bold')) return 700;
  if (lower.includes('black') || lower.includes('heavy')) return 900;
  return 400;
}

// Re-export for convenience
export { extractNodes } from './nodeExtractor';
export { extractAssets } from './assetExtractor';
export { extractLayout } from './layoutExtractor';
export { extractStyle } from './styleExtractor';
export { extractText } from './textExtractor';
export { extractComponent } from './componentExtractor';
