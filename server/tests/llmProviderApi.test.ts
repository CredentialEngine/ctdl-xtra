import { afterEach, describe, expect, it, vi } from "vitest";
import { Provider, ProviderModel } from "../../common/types";
import { providerForModel } from "../../common/modelMetadata";
import { toOpenAiMessages } from "../src/llm/openaiAdapter";
import { toAnthropicMessagesPayload } from "../src/llm/anthropicAdapter";
import { estimateCost } from "../src/llm/pricing";
import { ANTHROPIC_MAX_TOKENS } from "../src/llm/models";
import {
  simpleToolCompletion,
  structuredCompletion,
} from "../src/llm/LLMProviderApi";
import { LlmMessage } from "../src/llm/types";

vi.mock("../src/utils", async () => {
  const actual = await vi.importActual<typeof import("../src/utils")>(
    "../src/utils"
  );
  return {
    ...actual,
    exponentialRetry: async <T>(fn: () => Promise<T>) => fn(),
  };
});

const createModelApiCallLog = vi.fn();

vi.mock("../src/data/extractions", () => ({
  createModelApiCallLog: (...args: unknown[]) => createModelApiCallLog(...args),
}));

const getOpenAi = vi.fn();
vi.mock("../src/openai", () => ({
  getOpenAi: (...args: unknown[]) => getOpenAi(...args),
}));

const getAnthropic = vi.fn();
vi.mock("../src/anthropic", async () => {
  const actual = await vi.importActual<typeof import("../src/anthropic")>(
    "../src/anthropic"
  );
  return {
    ...actual,
    getAnthropic: (...args: unknown[]) => getAnthropic(...args),
  };
});

function openAiToolResponse(args: object) {
  return {
    choices: [
      {
        message: {
          tool_calls: [
            {
              function: {
                arguments: JSON.stringify(args),
              },
            },
          ],
        },
      },
    ],
    usage: { prompt_tokens: 11, completion_tokens: 7 },
  };
}

function openAiStructuredResponse(result: object) {
  return {
    choices: [
      {
        message: {
          content: JSON.stringify(result),
        },
      },
    ],
    usage: { prompt_tokens: 9, completion_tokens: 4 },
  };
}

function anthropicToolResponse(input: object) {
  return {
    content: [
      {
        type: "tool_use",
        id: "toolu_1",
        name: "result",
        input,
      },
    ],
    usage: { input_tokens: 13, output_tokens: 5 },
  };
}

function anthropicTextResponse(text: string) {
  return {
    content: [{ type: "text", text }],
    usage: { input_tokens: 8, output_tokens: 3 },
  };
}

const logApiCall = {
  callSite: "testCall",
  extractionId: 42,
};

const userImageMessage: LlmMessage = {
  role: "user",
  content: [
    { type: "text", text: "extract this page" },
    { type: "image", mediaType: "image/webp", data: "abc123" },
  ],
};

describe("providerForModel", () => {
  it("maps every ProviderModel to OpenAI or Anthropic", () => {
    const expected: Record<ProviderModel, Provider> = {
      [ProviderModel.Gpt4o]: Provider.OpenAI,
      [ProviderModel.Gpt41]: Provider.OpenAI,
      [ProviderModel.O3Mini]: Provider.OpenAI,
      [ProviderModel.O4Mini]: Provider.OpenAI,
      [ProviderModel.Gpt5]: Provider.OpenAI,
      [ProviderModel.Gpt5Nano]: Provider.OpenAI,
      [ProviderModel.Gpt54]: Provider.OpenAI,
      [ProviderModel.Gpt54Mini]: Provider.OpenAI,
      [ProviderModel.Gpt54Nano]: Provider.OpenAI,
      [ProviderModel.ClaudeHaiku45]: Provider.Anthropic,
      [ProviderModel.ClaudeSonnet5]: Provider.Anthropic,
      [ProviderModel.ClaudeOpus5]: Provider.Anthropic,
      [ProviderModel.ClaudeFable51]: Provider.Anthropic,
    };

    for (const model of Object.values(ProviderModel)) {
      expect(providerForModel(model), model).toBe(expected[model]);
    }
  });
});

describe("message conversion", () => {
  it("converts LlmMessage to OpenAI Chat Completions payload", () => {
    const payload = toOpenAiMessages([
      { role: "system", content: "Be precise." },
      userImageMessage,
    ]);

    expect(payload[0]).toEqual({
      role: "system",
      content: "Be precise.",
    });
    expect(payload[1]).toEqual({
      role: "user",
      content: [
        { type: "text", text: "extract this page" },
        {
          type: "image_url",
          image_url: { url: "data:image/webp;base64,abc123" },
        },
      ],
    });
  });

  it("lifts system messages and converts images for Anthropic", () => {
    const payload = toAnthropicMessagesPayload([
      { role: "system", content: "Be precise." },
      userImageMessage,
    ]);

    expect(payload.system).toBe("Be precise.");
    expect(payload.messages).toEqual([
      {
        role: "user",
        content: [
          { type: "text", text: "extract this page" },
          {
            type: "image",
            source: {
              type: "base64",
              media_type: "image/webp",
              data: "abc123",
            },
          },
        ],
      },
    ]);
  });
});

describe("estimateCost", () => {
  it("prices a GPT model", () => {
    expect(
      estimateCost(ProviderModel.Gpt54Mini, 1_000_000, 1_000_000)
    ).toBeCloseTo(5.25);
  });

  it("prices a Claude model", () => {
    expect(
      estimateCost(ProviderModel.ClaudeSonnet5, 1_000_000, 1_000_000)
    ).toBeCloseTo(12);
  });

  it("throws when a model has no prices", () => {
    expect(() =>
      estimateCost("not-a-model" as ProviderModel, 1, 1)
    ).toThrow(/No pricing configured/);
  });
});

describe("LLMProviderApi", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("logs OpenAI completions as Provider.OpenAI", async () => {
    const create = vi.fn().mockResolvedValue(openAiToolResponse({ ok: true }));
    getOpenAi.mockResolvedValue({
      chat: { completions: { create } },
    });

    await simpleToolCompletion({
      messages: [{ role: "user", content: "hi" }],
      toolName: "result",
      parameters: { ok: { type: "boolean" } },
      model: ProviderModel.Gpt54Mini,
      logApiCall,
    });

    expect(createModelApiCallLog).toHaveBeenCalledWith(
      42,
      Provider.OpenAI,
      ProviderModel.Gpt54Mini,
      "testCall",
      11,
      7,
      expect.anything()
    );
  });

  it("logs Anthropic completions as Provider.Anthropic", async () => {
    const create = vi.fn().mockResolvedValue(anthropicToolResponse({ ok: true }));
    getAnthropic.mockResolvedValue({ messages: { create } });

    await simpleToolCompletion({
      messages: [{ role: "user", content: "hi" }],
      toolName: "result",
      parameters: { ok: { type: "boolean" } },
      model: ProviderModel.ClaudeSonnet5,
      logApiCall,
    });

    expect(createModelApiCallLog).toHaveBeenCalledWith(
      42,
      Provider.Anthropic,
      ProviderModel.ClaudeSonnet5,
      "testCall",
      13,
      5,
      expect.anything()
    );
  });

  it("sends Anthropic max_tokens and omits sampling knobs", async () => {
    const create = vi.fn().mockResolvedValue(anthropicTextResponse('{"items":[]}'));
    getAnthropic.mockResolvedValue({ messages: { create } });

    await structuredCompletion({
      messages: [userImageMessage],
      schema: {
        type: "object",
        properties: { items: { type: "array" } },
        required: ["items"],
        additionalProperties: false,
      },
      model: ProviderModel.ClaudeSonnet5,
      temperature: 0.2,
      top_p: 0.3,
    });

    const body = create.mock.calls[0][0];
    expect(body.max_tokens).toBe(ANTHROPIC_MAX_TOKENS);
    expect(body.temperature).toBeUndefined();
    expect(body.top_p).toBeUndefined();
    expect(body.thinking).toBeUndefined();
    expect(body.effort).toBeUndefined();
    expect(body.system).toBeUndefined();
    expect(body.messages[0].content[1]).toEqual({
      type: "image",
      source: {
        type: "base64",
        media_type: "image/webp",
        data: "abc123",
      },
    });
    expect(body.output_config).toEqual({
      format: {
        type: "json_schema",
        schema: {
          type: "object",
          properties: { items: { type: "array" } },
          required: ["items"],
          additionalProperties: false,
        },
      },
    });
  });

  it("parses Anthropic tool_use.input for simpleToolCompletion", async () => {
    const create = vi
      .fn()
      .mockResolvedValue(anthropicToolResponse({ page_type: "DETAIL" }));
    getAnthropic.mockResolvedValue({ messages: { create } });

    const result = await simpleToolCompletion({
      messages: [{ role: "user", content: "classify" }],
      toolName: "page_type",
      parameters: { page_type: { type: "string" } },
      model: ProviderModel.ClaudeHaiku45,
    });

    expect(result.toolCallArgs).toEqual({ page_type: "DETAIL" });
    expect(create.mock.calls[0][0].tool_choice).toEqual({
      type: "tool",
      name: "page_type",
      disable_parallel_tool_use: true,
    });
  });

  it("parses Anthropic structured JSON from text blocks", async () => {
    const create = vi
      .fn()
      .mockResolvedValue(anthropicTextResponse('{"present":true,"explanation":"yes"}'));
    getAnthropic.mockResolvedValue({ messages: { create } });

    const result = await structuredCompletion({
      messages: [{ role: "user", content: "is it there?" }],
      schema: {
        type: "object",
        properties: {
          present: { type: "boolean" },
          explanation: { type: "string" },
        },
        required: ["present", "explanation"],
        additionalProperties: false,
      },
      model: ProviderModel.ClaudeOpus5,
    });

    expect(result.result).toEqual({ present: true, explanation: "yes" });
  });

  it("uses structured output for Fable instead of forced tool_choice", async () => {
    const create = vi
      .fn()
      .mockResolvedValue(anthropicTextResponse('{"items":["a"]}'));
    getAnthropic.mockResolvedValue({ messages: { create } });

    const result = await simpleToolCompletion({
      messages: [{ role: "user", content: "extract" }],
      toolName: "result",
      parameters: { items: { type: "array" } },
      requiredParameters: ["items"],
      model: ProviderModel.ClaudeFable51,
    });

    expect(result.toolCallArgs).toEqual({ items: ["a"] });
    expect(create.mock.calls[0][0].tools).toBeUndefined();
    expect(create.mock.calls[0][0].tool_choice).toBeUndefined();
    expect(create.mock.calls[0][0].output_config.format.type).toBe("json_schema");
  });

  it("strips image parts after an invalid OpenAI screenshot error", async () => {
    const { OpenAI } = await import("openai");
    const invalid = new OpenAI.APIError(
      400,
      { code: "invalid_base64", message: "bad image" },
      "bad image",
      undefined
    );
    const create = vi
      .fn()
      .mockRejectedValueOnce(invalid)
      .mockResolvedValueOnce(openAiToolResponse({ items: [] }));
    getOpenAi.mockResolvedValue({
      chat: { completions: { create } },
    });

    await simpleToolCompletion({
      messages: [userImageMessage],
      toolName: "result",
      parameters: { items: { type: "array" } },
      model: ProviderModel.Gpt54Mini,
    });

    expect(create).toHaveBeenCalledTimes(2);
    const firstParts = create.mock.calls[0][0].messages[0].content as Array<{
      type: string;
    }>;
    const secondParts = create.mock.calls[1][0].messages[0].content as Array<{
      type: string;
    }>;
    expect(firstParts.some((part) => part.type === "image_url")).toBe(true);
    expect(secondParts.some((part) => part.type === "image_url")).toBe(false);
  });

  it("strips image parts after an invalid Anthropic screenshot error", async () => {
    const Anthropic = (await import("@anthropic-ai/sdk")).default;
    const invalid = new Anthropic.APIError(
      400,
      { type: "invalid_request_error", message: "Could not process image" },
      "Could not process image",
      undefined
    );
    const create = vi
      .fn()
      .mockRejectedValueOnce(invalid)
      .mockResolvedValueOnce(anthropicToolResponse({ ok: true }));
    getAnthropic.mockResolvedValue({ messages: { create } });

    await simpleToolCompletion({
      messages: [userImageMessage],
      toolName: "result",
      parameters: { ok: { type: "boolean" } },
      model: ProviderModel.ClaudeSonnet5,
    });

    expect(create).toHaveBeenCalledTimes(2);
    const firstParts = create.mock.calls[0][0].messages[0].content as Array<{
      type: string;
    }>;
    const secondParts = create.mock.calls[1][0].messages[0].content as Array<{
      type: string;
    }>;
    expect(firstParts.some((part) => part.type === "image")).toBe(true);
    expect(secondParts.some((part) => part.type === "image")).toBe(false);
  });
});
