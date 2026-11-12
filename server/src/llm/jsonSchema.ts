import { JSONSchema } from "../../../common/catalogueTypes";
import type { ToolCallParameters } from "./types";

/** Ensures every `type: "object"` node has `additionalProperties: false` (OpenAI / Anthropic strict). */
export function normalizeStrictJsonSchema(schema: JSONSchema): JSONSchema {
  return normalizeNode(schema) as JSONSchema;
}

function normalizeNode(node: unknown): unknown {
  if (node === null || typeof node !== "object") {
    return node;
  }
  if (Array.isArray(node)) {
    return node.map(normalizeNode);
  }

  const obj = { ...(node as Record<string, unknown>) };

  if (
    obj.properties &&
    typeof obj.properties === "object" &&
    !Array.isArray(obj.properties)
  ) {
    const props = obj.properties as Record<string, unknown>;
    obj.properties = Object.fromEntries(
      Object.entries(props).map(([key, value]) => [key, normalizeNode(value)])
    );
  }

  if (obj.items !== undefined) {
    obj.items = normalizeNode(obj.items);
  }

  for (const combiner of ["anyOf", "allOf", "oneOf"] as const) {
    if (Array.isArray(obj[combiner])) {
      obj[combiner] = (obj[combiner] as unknown[]).map(normalizeNode);
    }
  }

  if (obj.type === "object") {
    obj.additionalProperties = false;
  }

  return obj;
}

export function toolParametersJsonSchema(
  properties: ToolCallParameters,
  requiredParameters?: string[]
): JSONSchema {
  const schema: JSONSchema = {
    type: "object",
    properties,
    additionalProperties: false,
  };
  if (requiredParameters !== undefined) {
    schema.required = requiredParameters;
  }
  return normalizeStrictJsonSchema(schema);
}
