/**
 * Complete design specification types for the Figma-to-HTML/CSS converter.
 * These types represent the intermediate design representation between
 * Figma's internal model and the backend code generator.
 */

/** Supported node types from Figma */
export type DesignNodeType =
  | 'FRAME'
  | 'TEXT'
  | 'RECTANGLE'
  | 'ELLIPSE'
  | 'VECTOR'
  | 'GROUP'
  | 'INSTANCE'
  | 'COMPONENT'
  | 'LINE'
  | 'POLYGON'
  | 'STAR'
  | 'BOOLEAN_OPERATION'
  | 'SECTION';

/** RGBA color representation */
export interface Color {
  r: number; // 0-255
  g: number; // 0-255
  b: number; // 0-255
  a: number; // 0-1
}

/** A single gradient color stop */
export interface GradientStop {
  position: number; // 0-1
  color: Color;
}

/** Transform matrix for gradients (2x3 affine transform) */
export type GradientTransform = [[number, number, number], [number, number, number]];

/** Fill types supported */
export type FillType = 'SOLID' | 'GRADIENT_LINEAR' | 'GRADIENT_RADIAL' | 'GRADIENT_ANGULAR' | 'GRADIENT_DIAMOND' | 'IMAGE';

/** A single fill layer */
export interface Fill {
  type: FillType;
  visible: boolean;
  opacity: number;
  blendMode: string;
  /** Solid fill color */
  color?: Color;
  /** Gradient stops */
  gradientStops?: GradientStop[];
  /** Gradient transform matrix */
  gradientTransform?: GradientTransform;
  /** Image hash for IMAGE fills */
  imageHash?: string;
  /** Scale mode for IMAGE fills */
  scaleMode?: 'FILL' | 'FIT' | 'CROP' | 'TILE';
  /** Image transform (crop/rotation) for IMAGE fills */
  imageTransform?: GradientTransform;
}

/** A single stroke */
export interface Stroke {
  type: FillType;
  visible: boolean;
  opacity: number;
  color?: Color;
  weight: number;
  align: 'INSIDE' | 'OUTSIDE' | 'CENTER';
  dashPattern?: number[];
  cap?: string;
  join?: string;
}

/** Effect types */
export type EffectType = 'DROP_SHADOW' | 'INNER_SHADOW' | 'LAYER_BLUR' | 'BACKGROUND_BLUR';

/** A single effect (shadow, blur) */
export interface Effect {
  type: EffectType;
  visible: boolean;
  /** Shadow offset X */
  offsetX?: number;
  /** Shadow offset Y */
  offsetY?: number;
  /** Blur radius */
  radius: number;
  /** Shadow spread (for shadows) */
  spread?: number;
  /** Effect color (for shadows) */
  color?: Color;
  /** Blend mode */
  blendMode?: string;
  /** Whether the shadow appears only on the outside or through transparent areas */
  showShadowBehindNode?: boolean;
}

/** Border radius specification */
export interface BorderRadius {
  topLeft: number;
  topRight: number;
  bottomRight: number;
  bottomLeft: number;
}

/** Style properties for a node */
export interface Style {
  fills: Fill[];
  strokes: Stroke[];
  borderRadius: BorderRadius;
  effects: Effect[];
  blendMode: string;
  overflow: 'VISIBLE' | 'HIDDEN' | 'SCROLL';
  cornerSmoothing?: number;
  strokeTopWeight?: number;
  strokeRightWeight?: number;
  strokeBottomWeight?: number;
  strokeLeftWeight?: number;
}

/** Layout type */
export type LayoutType = 'NONE' | 'AUTO_LAYOUT' | 'ABSOLUTE';

/** Auto-layout direction */
export type LayoutDirection = 'HORIZONTAL' | 'VERTICAL';

/** Alignment */
export type AxisAlign = 'MIN' | 'CENTER' | 'MAX' | 'SPACE_BETWEEN' | 'BASELINE';

/** Counter-axis alignment */
export type CounterAxisAlign = 'MIN' | 'CENTER' | 'MAX' | 'BASELINE';

/** Wrap mode for auto-layout */
export type LayoutWrap = 'NO_WRAP' | 'WRAP';

/** Padding specification */
export interface Padding {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

/** Constraint axis mode */
export type ConstraintType = 'MIN' | 'CENTER' | 'MAX' | 'STRETCH' | 'SCALE';

/** Layout constraints for absolutely positioned children */
export interface Constraints {
  horizontal: ConstraintType;
  vertical: ConstraintType;
}

/** Sizing mode for auto-layout children */
export type SizingMode = 'FIXED' | 'HUG' | 'FILL';

/** Layout properties */
export interface Layout {
  type: LayoutType;
  direction?: LayoutDirection;
  gap?: number;
  padding?: Padding;
  primaryAxisAlign?: AxisAlign;
  counterAxisAlign?: CounterAxisAlign;
  wrap?: LayoutWrap;
  constraints?: Constraints;
  /** Sizing behavior of this node within its parent auto-layout */
  primaryAxisSizing?: SizingMode;
  counterAxisSizing?: SizingMode;
  /** Position mode for the node itself */
  positionType?: 'AUTO' | 'ABSOLUTE';
}

/** Bounding box of a node */
export interface Bounds {
  x: number;
  y: number;
  width: number;
  height: number;
  /** Rotation in degrees */
  rotation?: number;
}

/** A text style segment within a text node */
export interface TextSegment {
  characters: string;
  start: number;
  end: number;
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
  openTypeFeatures?: Record<string, boolean>;
}

/** Text properties for TEXT nodes */
export interface TextProperties {
  characters: string;
  textAlignHorizontal: 'LEFT' | 'CENTER' | 'RIGHT' | 'JUSTIFIED';
  textAlignVertical: 'TOP' | 'CENTER' | 'BOTTOM';
  textAutoResize?: 'NONE' | 'WIDTH_AND_HEIGHT' | 'HEIGHT' | 'TRUNCATE';
  textTruncation?: 'DISABLED' | 'ENDING';
  maxLines?: number;
  paragraphSpacing?: number;
  paragraphIndent?: number;
  segments: TextSegment[];
}

/** Component information for INSTANCE / COMPONENT nodes */
export interface ComponentInfo {
  componentId: string;
  componentName: string;
  /** Variant properties, e.g., { "Size": "Large", "State": "Hover" } */
  variantProperties?: Record<string, string>;
  /** Whether this is a component set (variants parent) */
  isComponentSet?: boolean;
  /** Description from the main component */
  description?: string;
}

/** Reference to an exported asset (image, SVG, etc.) */
export interface AssetReference {
  nodeId: string;
  nodeName: string;
  /** Export format */
  format: 'PNG' | 'SVG' | 'JPG' | 'PDF';
  /** Scale factor for raster exports */
  scale: number;
  /** Base64-encoded asset data */
  data: string;
  /** Byte size of the exported asset */
  byteSize: number;
  /** Content type */
  mimeType: string;
}

/** A single design node in the tree */
export interface DesignNode {
  id: string;
  name: string;
  type: DesignNodeType;
  visible: boolean;
  opacity: number;
  bounds: Bounds;
  layout: Layout;
  style: Style;
  /** Text-specific properties (only for TEXT nodes) */
  text?: TextProperties;
  /** Component information (for INSTANCE and COMPONENT nodes) */
  component?: ComponentInfo;
  /** Child nodes */
  children: DesignNode[];
  /** Whether this node is treated as an exportable asset */
  isAsset?: boolean;
  /** Whether this node is a mask */
  isMask?: boolean;
  /** Export settings if node should be exported */
  exportSettings?: Array<{
    format: 'PNG' | 'SVG' | 'JPG' | 'PDF';
    suffix: string;
    constraint: { type: 'SCALE' | 'WIDTH' | 'HEIGHT'; value: number };
  }>;
}

/** Metadata about the source file */
export interface FileMetadata {
  fileName: string;
  lastModified: string;
  pluginVersion: string;
}

/** The top-level design specification document */
export interface DesignSpec {
  /** Schema version for forward compatibility */
  version: string;
  /** File metadata */
  metadata: FileMetadata;
  /** The root frame name */
  frameName: string;
  /** Root frame dimensions */
  frameWidth: number;
  frameHeight: number;
  /** The tree of design nodes */
  nodes: DesignNode[];
  /** Exported assets */
  assets: AssetReference[];
  /** Base64-encoded PNG screenshot of the frame (for visual verification) */
  frameScreenshot?: string;
  /** Global color styles used in the design */
  colorStyles?: Record<string, { name: string; color: Color }>;
  /** Global text styles used in the design */
  textStyles?: Record<string, { name: string; fontFamily: string; fontSize: number; fontWeight: number }>;
}
