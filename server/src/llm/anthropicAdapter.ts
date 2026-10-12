import Anthropic from "@anthropic-ai/sdk";
import { JSONSchema } from "../../../common/catalogueTypes";
import { Provider, ProviderModel } from "../../../common/types";
import { getAnthropic, textFromAnthropicMessage } from "../anthropic";
import getLogger from "../logging";
import { ANTHROPIC_MAX_TOKENS, usesForcedToolChoice } from "./models";
import {
  LlmContentPart,
  LlmMessage,
  LlmProviderAdapter,
  SimpleToolCompletionOptions,
  SimpleToolCompletionResult,
  StructuredCompletionOptions,
  StructuredCompletionResult,
  ToolCallParameters,
  markNoRetry,
  stripImageParts,
} from "./types";

const logger = getLogger("llm.anthropicAdapter");

const structuredFallbackWarned = new Set<string>();

type AnthropicMessageParam = Anthropic.MessageParam;
type AnthropicContentBlockParam = Anthropic.ContentBlockParam;
type AnthropicTextBlockParam = Anthropic.TextBlockParam;

export interface AnthropicMessagesPayload {
  system?: string | AnthropicTextBlockParam[];
  messages: AnthropicMessageParam[];
}

function toAnthropicContentBlock(
  part: LlmContentPart
): AnthropicContentBlockParam {
  if (part.type === "text") {
    return { type: "text", text: part.text };
  }
  return {
    type: "image",
    source: {
      type: "base64",
      media_type: part.mediaType,
      data: part.data,
    },
  };
}

export function toAnthropicMessagesPayload(
  messages: LlmMessage[]
): AnthropicMessagesPayload {
  const systemMessages = messages.filter((message) => message.role === "system");
  const conversation = messages.filter((message) => message.role !== "system");

  let system: AnthropicMessagesPayload["system"];
  if (systemMessages.length) {
    const blocks: AnthropicTextBlockParam[] = systemMessages.flatMap(
      (message) => {
        if (typeof message.content === "string") {
          return [{ type: "text", text: message.content }];
        }
        return message.content
          .filter((part): part is { type: "text"; text: string } => part.type === "text")
          .map((part) => ({ type: "text" as const, text: part.text }));
      }
    );
    system = blocks.length === 1 ? blocks[0].text : blocks;
  }

  const anthropicMessages: AnthropicMessageParam[] = conversation.map(
    (message) => ({
      role: message.role as "user" | "assistant",
      content:
        typeof message.content === "string"
          ? message.content
          : message.content.map(toAnthropicContentBlock),
    })
  );

  return { system, messages: anthropicMessages };
}

function isInvalidAnthropicImageError(error: unknown): boolean {
  if (!(error instanceof Anthropic.APIError)) {
    return false;
  }
  const message = error.message.toLowerCase();
  return (
    message.includes("image") &&
    (message.includes("invalid") ||
      message.includes("could not process") ||
      message.includes("media") ||
      message.includes("base64") ||
      message.includes("format"))
  );
}

function isForcedToolChoiceUnsupported(error: unknown): boolean {
  if (!(error instanceof Anthropic.APIError) || error.status !== 400) {
    return false;
  }
  const message = error.message.toLowerCase();
  return (
    message.includes("tool_choice") ||
    (message.includes("not supported") && message.includes("tool"))
  );
}

function markNonRetryableAnthropicError(error: unknown) {
  const isAuth =
    error instanceof Anthropic.AuthenticationError ||
    (error instanceof Anthropic.APIError &&
      (error.status === 401 || error.status === 403));
  const message = error instanceof Error ? error.message.toLowerCase() : "";
  const isBilling = /credit|billing|too low|purchase credits/.test(message);
  return markNoRetry(error, Boolean(isAuth || isBilling));
}

function warnStructuredFallback(model: string) {
  if (structuredFallbackWarned.has(model)) {
    return;
  }
  structuredFallbackWarned.add(model);
  logger.warn(
    `Model ${model} rejected forced tool_choice; using structured JSON output`
  );
}

function toolObjectSchema(
  parameters: ToolCallParameters,
  requiredParameters?: Array<string | number | symbol>
): Anthropic.Tool.InputSchema {
  return {
    type: "object",
    properties: parameters,
    required: (requiredParameters as string[] | undefined) ?? [],
    additionalProperties: false,
  };
}

function parseJsonText(text: string): unknown {
  const trimmed = text.trim();
  if (!trimmed) {
    return null;
  }
  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/);
  const raw = fenced ? fenced[1].trim() : trimmed;
  return JSON.parse(raw);
}

function parseStructuredJson(message: Anthropic.Message): unknown {
  const text = textFromAnthropicMessage(message);
  if (!text) {
    return null;
  }
  return parseJsonText(text);
}

function parseToolUseInput(message: Anthropic.Message): unknown {
  const block = message.content.find((part) => part.type === "tool_use");
  if (!block || block.type !== "tool_use") {
    return null;
  }
  return block.input;
}

function usageFrom(message: Anthropic.Message) {
  return {
    inputTokenCount: message.usage?.input_tokens || 0,
    outputTokenCount: message.usage?.output_tokens || 0,
  };
}

async function createMessage(
  client: Anthropic,
  body: Anthropic.MessageCreateParamsNonStreaming,
  messages: LlmMessage[]
): Promise<Anthropic.Message> {
  const payload = toAnthropicMessagesPayload(messages);
  const request: Anthropic.MessageCreateParamsNonStreaming = {
    ...body,
    max_tokens: ANTHROPIC_MAX_TOKENS,
    messages: payload.messages,
    ...(payload.system ? { system: payload.system } : {}),
  };
  try {
    return await client.messages.create(request);
  } catch (error) {
    if (isInvalidAnthropicImageError(error)) {
      logger.warn(
        "Anthropic API Error: invalid image. Likely invalid base64 screenshot; retrying without screenshots"
      );
      const stripped = toAnthropicMessagesPayload(stripImageParts(messages));
      return await client.messages.create({
        ...request,
        messages: stripped.messages,
        ...(stripped.system ? { system: stripped.system } : {}),
      });
    }
    throw markNonRetryableAnthropicError(error);
  }
}

async function structuredJsonCompletion(
  client: Anthropic,
  messages: LlmMessage[],
  model: ProviderModel,
  schema: JSONSchema
): Promise<{ parsed: unknown; usage: ReturnType<typeof usageFrom> }> {
  const message = await createMessage(
    client,
    {
      model,
      max_tokens: ANTHROPIC_MAX_TOKENS,
      messages: [],
      output_config: {
        format: {
          type: "json_schema",
          schema,
        },
      },
    },
    messages
  );
  return {
    parsed: parseStructuredJson(message),
    usage: usageFrom(message),
  };
}

export const anthropicAdapter: LlmProviderAdapter = {
  provider: Provider.Anthropic,

  async simpleToolCompletion<T extends ToolCallParameters>(
    options: SimpleToolCompletionOptions<T>
  ): Promise<SimpleToolCompletionResult<T>> {
    const client = await getAnthropic();
    const selectedModel = options.model || ProviderModel.Gpt5;
    const schema = toolObjectSchema(
      options.parameters,
      options.requiredParameters
    );

    if (!usesForcedToolChoice(selectedModel)) {
      const { parsed, usage } = await structuredJsonCompletion(
        client,
        options.messages,
        selectedModel,
        schema
      );
      return {
        toolCallArgs: (parsed as SimpleToolCompletionResult<T>["toolCallArgs"]) ?? null,
        ...usage,
      };
    }

    try {
      const message = await createMessage(
        client,
        {
          model: selectedModel,
          max_tokens: ANTHROPIC_MAX_TOKENS,
          messages: [],
          tools: [
            {
              name: options.toolName,
              description: "Return the result.",
              input_schema: schema,
              strict: true,
            },
          ],
          tool_choice: {
            type: "tool",
            name: options.toolName,
            disable_parallel_tool_use: true,
          },
        },
        options.messages
      );
      const toolCallArgs = parseToolUseInput(message);
      return {
        toolCallArgs:
          (toolCallArgs as SimpleToolCompletionResult<T>["toolCallArgs"]) ??
          null,
        ...usageFrom(message),
      };
    } catch (error) {
      if (!isForcedToolChoiceUnsupported(error)) {
        throw error;
      }
      warnStructuredFallback(selectedModel);
      const { parsed, usage } = await structuredJsonCompletion(
        client,
        options.messages,
        selectedModel,
        schema
      );
      return {
        toolCallArgs: (parsed as SimpleToolCompletionResult<T>["toolCallArgs"]) ?? null,
        ...usage,
      };
    }
  },

  async structuredCompletion<T extends ToolCallParameters>(
    options: StructuredCompletionOptions<T>
  ): Promise<StructuredCompletionResult<T>> {
    const client = await getAnthropic();
    const selectedModel = options.model || ProviderModel.Gpt5;
    const { parsed, usage } = await structuredJsonCompletion(
      client,
      options.messages,
      selectedModel,
      options.schema
    );
    return {
      result: (parsed as StructuredCompletionResult<T>["result"]) ?? null,
      ...usage,
    };
  },
};
