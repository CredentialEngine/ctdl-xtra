import { describe, expect, it } from "vitest";
import {
  normalizeStrictJsonSchema,
  toolParametersJsonSchema,
} from "../src/llm/jsonSchema";

describe("jsonSchema", () => {
  it("sets additionalProperties on nested object tool parameters", () => {
    const schema = toolParametersJsonSchema(
      {
        items: {
          type: "array",
          items: {
            type: "object",
            properties: { name: { type: "string" } },
            required: ["name"],
          },
        },
      },
      ["items"]
    );

    expect(schema.additionalProperties).toBe(false);
    const itemSchema = (schema.properties as Record<string, unknown>).items as {
      items: { additionalProperties: boolean };
    };
    expect(itemSchema.items.additionalProperties).toBe(false);
  });

  it("normalizes structured output schemas", () => {
    const schema = normalizeStrictJsonSchema({
      type: "object",
      properties: {
        nested: {
          type: "object",
          properties: { ok: { type: "boolean" } },
          required: ["ok"],
        },
      },
      required: ["nested"],
    });

    expect(schema.additionalProperties).toBe(false);
    const nested = schema.properties?.nested as { additionalProperties: boolean };
    expect(nested.additionalProperties).toBe(false);
  });
});
