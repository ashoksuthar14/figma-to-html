/**
 * Component extractor: detects component instances and their properties,
 * including variant information, component descriptions, and overrides.
 */

import type { ComponentInfo } from '../types/designSpec';

/**
 * Extract component information from a Figma node.
 * Returns ComponentInfo if the node is a component or instance, undefined otherwise.
 *
 * @param node - The Figma scene node
 * @returns ComponentInfo object, or undefined for non-component nodes
 */
export function extractComponent(node: SceneNode): ComponentInfo | undefined {
  if (node.type === 'INSTANCE') {
    return extractInstanceInfo(node as InstanceNode);
  }

  if (node.type === 'COMPONENT') {
    return extractComponentNodeInfo(node as ComponentNode);
  }

  if (node.type === 'COMPONENT_SET') {
    return extractComponentSetInfo(node as ComponentSetNode);
  }

  return undefined;
}

/**
 * Extract information from a component instance.
 */
function extractInstanceInfo(node: InstanceNode): ComponentInfo {
  const mainComponent = node.mainComponent;

  const info: ComponentInfo = {
    componentId: mainComponent?.id ?? node.id,
    componentName: mainComponent?.name ?? node.name,
  };

  // Extract variant properties from the main component
  if (mainComponent) {
    const variantProps = extractVariantProperties(mainComponent);
    if (variantProps && Object.keys(variantProps).length > 0) {
      info.variantProperties = variantProps;
    }

    // Get description from the main component
    if (mainComponent.description) {
      info.description = mainComponent.description;
    }

    // Check if main component belongs to a component set (variant)
    if (mainComponent.parent && mainComponent.parent.type === 'COMPONENT_SET') {
      info.isComponentSet = false; // This is a variant instance, not the set itself
      info.componentName = mainComponent.parent.name;

      // Get variant properties from the component name (Figma uses "Property=Value, ..." format)
      const parsedVariants = parseVariantName(mainComponent.name);
      if (parsedVariants && Object.keys(parsedVariants).length > 0) {
        info.variantProperties = parsedVariants;
      }
    }
  }

  // Also check component properties on the instance itself
  try {
    const componentProps = node.componentProperties;
    if (componentProps && Object.keys(componentProps).length > 0) {
      const mappedProps = mapComponentProperties(componentProps);
      if (Object.keys(mappedProps).length > 0) {
        info.variantProperties = {
          ...info.variantProperties,
          ...mappedProps,
        };
      }
    }
  } catch {
    // componentProperties may not be available in all contexts
  }

  return info;
}

/**
 * Extract information from a component definition node.
 */
function extractComponentNodeInfo(node: ComponentNode): ComponentInfo {
  const info: ComponentInfo = {
    componentId: node.id,
    componentName: node.name,
  };

  if (node.description) {
    info.description = node.description;
  }

  // If this component is part of a component set (variant group)
  if (node.parent && node.parent.type === 'COMPONENT_SET') {
    const parsedVariants = parseVariantName(node.name);
    if (parsedVariants && Object.keys(parsedVariants).length > 0) {
      info.variantProperties = parsedVariants;
    }
    info.componentName = node.parent.name;
  }

  return info;
}

/**
 * Extract information from a component set (variant group).
 */
function extractComponentSetInfo(node: ComponentSetNode): ComponentInfo {
  const info: ComponentInfo = {
    componentId: node.id,
    componentName: node.name,
    isComponentSet: true,
  };

  if (node.description) {
    info.description = node.description;
  }

  // Extract available variant properties from the component set
  try {
    const variantGroupProperties = node.variantGroupProperties;
    if (variantGroupProperties) {
      const variants: Record<string, string> = {};
      for (const [key, prop] of Object.entries(variantGroupProperties)) {
        // Store the possible values as comma-separated string
        variants[key] = (prop as { values: string[] }).values?.join(', ') ?? '';
      }
      if (Object.keys(variants).length > 0) {
        info.variantProperties = variants;
      }
    }
  } catch {
    // variantGroupProperties may not be available
  }

  return info;
}

/**
 * Extract variant properties from a component node.
 * Figma components that are variants have their properties encoded in their name.
 */
function extractVariantProperties(component: ComponentNode): Record<string, string> | undefined {
  // Check if the component is a variant (child of a ComponentSet)
  if (!component.parent || component.parent.type !== 'COMPONENT_SET') {
    return undefined;
  }

  return parseVariantName(component.name);
}

/**
 * Parse variant properties from a Figma component variant name.
 * Figma encodes variant properties in the format: "Property1=Value1, Property2=Value2"
 *
 * @param name - The variant component name
 * @returns Record of property name to value, or undefined
 */
function parseVariantName(name: string): Record<string, string> | undefined {
  if (!name || !name.includes('=')) {
    return undefined;
  }

  const properties: Record<string, string> = {};

  // Split by comma and parse each "Key=Value" pair
  const pairs = name.split(',').map((s) => s.trim());

  for (const pair of pairs) {
    const eqIndex = pair.indexOf('=');
    if (eqIndex > 0) {
      const key = pair.substring(0, eqIndex).trim();
      const value = pair.substring(eqIndex + 1).trim();
      if (key && value) {
        properties[key] = value;
      }
    }
  }

  return Object.keys(properties).length > 0 ? properties : undefined;
}

/**
 * Map Figma component properties to a flat Record<string, string>.
 */
function mapComponentProperties(
  props: Record<string, ComponentProperty>
): Record<string, string> {
  const result: Record<string, string> = {};

  for (const [key, prop] of Object.entries(props)) {
    // Clean up the key (Figma appends #id to property keys)
    const cleanKey = key.replace(/#\d+:\d+$/, '').trim();

    switch (prop.type) {
      case 'BOOLEAN':
        result[cleanKey] = String(prop.value);
        break;
      case 'TEXT':
        result[cleanKey] = String(prop.value);
        break;
      case 'INSTANCE_SWAP':
        result[cleanKey] = String(prop.value);
        break;
      case 'VARIANT':
        result[cleanKey] = String(prop.value);
        break;
      default:
        result[cleanKey] = String(prop.value);
        break;
    }
  }

  return result;
}

/**
 * Type for Figma component property (simplified).
 */
interface ComponentProperty {
  type: 'BOOLEAN' | 'TEXT' | 'INSTANCE_SWAP' | 'VARIANT';
  value: string | boolean;
  preferredValues?: Array<{ type: string; key: string }>;
}
