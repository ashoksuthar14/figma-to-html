import type { LayoutInfo, ComputedSpacing, CssPatch } from "@/types/editor";

function parsePxValue(val: string | undefined): number {
  if (!val) return 0;
  const n = parseFloat(val);
  return isNaN(n) ? 0 : n;
}

function formatPx(val: number): string {
  return `${Math.round(val)}px`;
}

/**
 * Compute the CSS property patches required to move an element
 * by (deltaX, deltaY) pixels, given its layout context.
 */
export function computePositionDelta(
  deltaX: number,
  deltaY: number,
  layoutInfo: LayoutInfo,
  computedStyles: ComputedSpacing
): CssPatch[] {
  const patches: CssPatch[] = [];

  if (Math.abs(deltaX) < 0.5 && Math.abs(deltaY) < 0.5) return patches;

  const pos = layoutInfo.position;

  if (pos === "absolute" || pos === "fixed") {
    return computeAbsolutePatches(deltaX, deltaY, layoutInfo);
  }

  const parentIsFlex =
    layoutInfo.parentDisplay === "flex" ||
    layoutInfo.parentDisplay === "inline-flex";

  if (parentIsFlex) {
    return computeFlexPatches(deltaX, deltaY, layoutInfo, computedStyles);
  }

  return computeFlowPatches(deltaX, deltaY, layoutInfo, computedStyles);
}

function computeAbsolutePatches(
  deltaX: number,
  deltaY: number,
  layoutInfo: LayoutInfo
): CssPatch[] {
  const patches: CssPatch[] = [];

  if (Math.abs(deltaX) >= 0.5) {
    const currentLeft = layoutInfo.hasExistingLeft ? layoutInfo.computedLeft : 0;
    patches.push({ property: "left", value: formatPx(currentLeft + deltaX) });
  }
  if (Math.abs(deltaY) >= 0.5) {
    const currentTop = layoutInfo.hasExistingTop ? layoutInfo.computedTop : 0;
    patches.push({ property: "top", value: formatPx(currentTop + deltaY) });
  }

  return patches;
}

function computeFlexPatches(
  deltaX: number,
  deltaY: number,
  layoutInfo: LayoutInfo,
  computedStyles: ComputedSpacing
): CssPatch[] {
  const patches: CssPatch[] = [];
  const dir = layoutInfo.parentFlexDirection || "row";

  if (dir === "column" || dir === "column-reverse") {
    if (Math.abs(deltaX) >= 0.5) {
      const current = parsePxValue(computedStyles.marginLeft);
      patches.push({ property: "margin-left", value: formatPx(current + deltaX) });
    }
    if (Math.abs(deltaY) >= 0.5) {
      const current = parsePxValue(computedStyles.marginTop);
      patches.push({ property: "margin-top", value: formatPx(current + deltaY) });
    }
  } else {
    if (Math.abs(deltaX) >= 0.5) {
      const current = parsePxValue(computedStyles.marginLeft);
      patches.push({ property: "margin-left", value: formatPx(current + deltaX) });
    }
    if (Math.abs(deltaY) >= 0.5) {
      const current = parsePxValue(computedStyles.marginTop);
      patches.push({ property: "margin-top", value: formatPx(current + deltaY) });
    }
  }

  return patches;
}

function computeFlowPatches(
  deltaX: number,
  deltaY: number,
  layoutInfo: LayoutInfo,
  computedStyles: ComputedSpacing
): CssPatch[] {
  const patches: CssPatch[] = [];

  if (layoutInfo.position === "relative") {
    if (Math.abs(deltaX) >= 0.5) {
      patches.push({ property: "left", value: formatPx(deltaX) });
    }
    if (Math.abs(deltaY) >= 0.5) {
      patches.push({ property: "top", value: formatPx(deltaY) });
    }
    return patches;
  }

  // static positioning - use margins
  if (Math.abs(deltaX) >= 0.5) {
    const current = parsePxValue(computedStyles.marginLeft);
    patches.push({ property: "margin-left", value: formatPx(current + deltaX) });
  }
  if (Math.abs(deltaY) >= 0.5) {
    const current = parsePxValue(computedStyles.marginTop);
    patches.push({ property: "margin-top", value: formatPx(current + deltaY) });
  }

  return patches;
}
