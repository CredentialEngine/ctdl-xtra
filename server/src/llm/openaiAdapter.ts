import { OpenAI } from "openai";
import {
  ChatCompletion,
  ChatCompletionContentPart,
  ChatCompletionCreateParams,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";
import { JSONSchema } from "../../../common/catalogueTypes";
import { Provider, ProviderModel } from "../../../common/types";
import getLogger from "../logging";
import { getOpenAi } from "../openai";
import {
  normalizeStrictJsonSchema,
  openAiStrictToolResponseSchema,
  toolParametersJsonSchema,
} from "./jsonSchema";
import {
  openAiReasoningEffortNoneForTools,
  openAiUsesJsonSchemaForTools,
  stripsImages,
  supportsTopP,
} from "./models";
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

const logger = getLogger("llm.openaiAdapter");

export function toOpenAiContentPart(
  part: LlmContentPart
): ChatCompletionContentPart {
  if (part.type === "text") {
    return { type: "text", text: part.text };
  }
  return {
    type: "image_url",
    image_url: {
      url: `data:${part.mediaType};base64,${part.data}`,
    },
  };
}

export function toOpenAiMessages(
  messages: LlmMessage[]
): ChatCompletionMessageParam[] {
  return messages.map((message) => {
    if (typeof message.content === "string") {
      return {
        role: message.role,
        content: message.content,
      } as ChatCompletionMessageParam;
    }
    return {
      role: message.role,
      content: message.content.map(toOpenAiContentPart),
    } as ChatCompletionMessageParam;
  });
}

function isInvalidOpenAiImageError(error: unknown): boolean {
  return (
    error instanceof OpenAI.APIError &&
    ["invalid_base64", "invalid_image_format"].includes(error.code || "")
  );
}

function markNonRetryableOpenAiError(error: unknown) {
  const isQuotaError =
    error instanceof OpenAI.APIError && error.code === "insufficient_quota";
  return markNoRetry(error, isQuotaError);
}

function applySampling(
  completionOptions: ChatCompletionCreateParams,
  selectedModel: ProviderModel,
  options: { temperature?: number; top_p?: number }
) {
  completionOptions.temperature = options.temperature ?? 1;
  if (Number.isFinite(options.top_p) && supportsTopP(selectedModel)) {
    completionOptions.top_p = options.top_p;
  }
}

function applyOpenAiToolCompat(
  completionOptions: ChatCompletionCreateParams,
  selectedModel: ProviderModel
) {
  if (openAiReasoningEffortNoneForTools(selectedModel)) {
    (completionOptions as ChatCompletionCreateParams & {
      reasoning_effort?: "none";
    }).reasoning_effort = "none";
  }
}

async function openAiJsonSchemaCompletion(
  openai: OpenAI,
  options: {
    messages: LlmMessage[];
    model: ProviderModel;
    schema: JSONSchema;
    temperature?: number;
    top_p?: number;
  }
): Promise<ChatCompletion> {
  const completionOptions: ChatCompletionCreateParams = {
    messages: [],
    model: options.model,
    frequency_penalty: 0,
    presence_penalty: 0,
    response_format: {
      type: "json_schema",
      json_schema: {
        strict: true,
        name: "schema",
        schema: normalizeStrictJsonSchema(options.schema),
      },
    } as any,
  };
  applySampling(completionOptions, options.model, options);
  return createChatCompletion(
    openai,
    completionOptions,
    options.messages,
    options.model
  );
}

async function createChatCompletion(
  openai: OpenAI,
  completionOptions: ChatCompletionCreateParams,
  messages: LlmMessage[],
  selectedModel: ProviderModel
): Promise<ChatCompletion> {
  const requestMessages = toOpenAiMessages(
    stripsImages(selectedModel) ? stripImageParts(messages) : messages
  );
  try {
    return (await openai.chat.completions.create({
      ...completionOptions,
      messages: requestMessages,
    })) as ChatCompletion;
  } catch (error) {
    if (isInvalidOpenAiImageError(error)) {
      const code = error instanceof OpenAI.APIError ? error.code : "unknown";
      logger.warn(
        `OpenAI API Error: ${code}. Likely invalid base64 screenshot; retrying without screenshots`
      );
      return (await openai.chat.completions.create({
        ...completionOptions,
        messages: toOpenAiMessages(stripImageParts(messages)),
      })) as ChatCompletion;
    }
    throw markNonRetryableOpenAiError(error);
  }
}

export const openaiAdapter: LlmProviderAdapter = {
  provider: Provider.OpenAI,

  async simpleToolCompletion<T extends ToolCallParameters>(
    options: SimpleToolCompletionOptions<T>
  ): Promise<SimpleToolCompletionResult<T>> {
    const openai = await getOpenAi();
    const selectedModel = options.model || ProviderModel.Gpt5;

    if (openAiUsesJsonSchemaForTools(selectedModel)) {
      const schema = openAiStrictToolResponseSchema(
        toolParametersJsonSchema(
          options.parameters,
          options.requiredParameters as string[] | undefined
        )
      );
      const chatCompletion = await openAiJsonSchemaCompletion(openai, {
        messages: options.messages,
        model: selectedModel,
        schema,
        temperature: options.temperature,
        top_p: options.top_p,
      });
      const inputTokenCount = chatCompletion.usage?.prompt_tokens || 0;
      const outputTokenCount = chatCompletion.usage?.completion_tokens || 0;
      const content = chatCompletion.choices[0].message.content;
      if (!content) {
        return {
          toolCallArgs: null,
          inputTokenCount,
          outputTokenCount,
        };
      }
      return {
        toolCallArgs: JSON.parse(content) as SimpleToolCompletionResult<T>["toolCallArgs"],
        inputTokenCount,
        outputTokenCount,
      };
    }

    const completionOptions: ChatCompletionCreateParams = {
      messages: [],
      model: selectedModel,
      tools: [
        {
          type: "function",
          function: {
            name: options.toolName,
            parameters: toolParametersJsonSchema(
              options.parameters,
              options.requiredParameters as string[] | undefined
            ),
          },
        },
      ],
      tool_choice: {
        type: "function",
        function: {
          name: options.toolName,
        },
      },
    };
    applySampling(completionOptions, selectedModel, options);
    applyOpenAiToolCompat(completionOptions, selectedModel);

    const chatCompletion = await createChatCompletion(
      openai,
      completionOptions,
      options.messages,
      selectedModel
    );

    const inputTokenCount = chatCompletion.usage?.prompt_tokens || 0;
    const outputTokenCount = chatCompletion.usage?.completion_tokens || 0;

    if (!chatCompletion.choices[0].message.tool_calls?.length) {
      return {
        toolCallArgs: null,
        inputTokenCount,
        outputTokenCount,
      };
    }

    const toolArgs = JSON.parse(
      chatCompletion.choices[0].message.tool_calls[0].function.arguments
    );

    return {
      toolCallArgs: toolArgs,
      inputTokenCount,
      outputTokenCount,
    };
  },

  async structuredCompletion<T extends ToolCallParameters>(
    options: StructuredCompletionOptions<T>
  ): Promise<StructuredCompletionResult<T>> {
    const openai = await getOpenAi();
    const selectedModel = options.model || ProviderModel.Gpt5;

    const chatCompletion = await openAiJsonSchemaCompletion(openai, {
      messages: options.messages,
      model: selectedModel,
      schema: options.schema,
      temperature: options.temperature,
      top_p: options.top_p,
    });

    const inputTokenCount = chatCompletion.usage?.prompt_tokens || 0;
    const outputTokenCount = chatCompletion.usage?.completion_tokens || 0;

    if (!chatCompletion.choices[0].message.content) {
      return {
        result: null,
        inputTokenCount,
        outputTokenCount,
      };
    }

    const result = JSON.parse(chatCompletion.choices[0].message.content);

    return {
      result,
      inputTokenCount,
      outputTokenCount,
    };
  },
};
