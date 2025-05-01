import { OpenAI } from "openai";
import { JSONSchema } from "openai/lib/jsonschema";
import {
  ChatCompletion,
  ChatCompletionCreateParams,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";
import { Provider, ProviderModel } from "../../common/types";
import { createModelApiCallLog } from "./data/extractions";
import { findSetting } from "./data/settings";
import { exponentialRetry } from "./utils";

export const ModelPrices = {
  [ProviderModel.Gpt4o]: {
    per1MInput: 5.0,
    per1MOutput: 15.0,
  },
  [ProviderModel.O3Mini]: {
    per1MInput: 1.1,
    per1MOutput: 4.4,
  },
};

export class BadToolCallResponseError extends Error {}

export class UnknownPaginationTypeError extends Error {}

export function estimateCost(
  model: ProviderModel,
  inputTokens: number,
  outputTokens: number
) {
  const prices = ModelPrices[model];
  const inputCost = (inputTokens / 1_000_000) * prices.per1MInput;
  const outputCost = (outputTokens / 1_000_000) * prices.per1MOutput;
  return inputCost + outputCost;
}

export async function findOpenAiApiKey() {
  const apiKey = await findSetting("OPENAI_API_KEY", true);
  if (!apiKey) {
    throw new Error("OpenAI API Key not found");
  }
  return apiKey.value;
}

export async function getOpenAi() {
  const apiKey = await findOpenAiApiKey();
  return new OpenAI({ apiKey });
}

export type ToolCallParameters = Record<string, unknown>;

export type ToolCallReturn<T extends ToolCallParameters> = {
  [key in keyof T]: unknown;
};

export async function simpleToolCompletion<
  T extends ToolCallParameters,
>(options: {
  messages: Array<ChatCompletionMessageParam>;
  toolName: string;
  parameters: T;
  model?: ProviderModel;
  requiredParameters?: Array<keyof T>;
  temperature?: number;
  top_p?: number;
  logApiCall?: {
    callSite: string;
    extractionId: number;
  };
}): Promise<{
  toolCallArgs: ToolCallReturn<T> | null;
  inputTokenCount: number;
  outputTokenCount: number;
}> {
  return exponentialRetry(async () => {
    const openai = await getOpenAi();
    let chatCompletion: ChatCompletion;
    const completionOptions: ChatCompletionCreateParams = {
      messages: options.messages,
      model: options.model || ProviderModel.Gpt4o,
      temperature: options?.temperature ?? 1,
      top_p: options?.top_p ?? 1,
      tools: [
        {
          type: "function",
          function: {
            name: options.toolName,
            parameters: {
              type: "object",
              properties: options.parameters,
              required: options.requiredParameters || undefined,
            },
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
    try {
      if (options.model === ProviderModel.O3Mini) {
        // @ts-ignore
        completionOptions.messages = options.messages.map((m) => ({
          ...m,
          content: Array.isArray(m.content)
            ? m.content.filter((c) => c.type !== "image_url")
            : m.content,
        }));
      }

      chatCompletion = await openai.chat.completions.create(completionOptions);
    } catch (e) {
      if (
        e instanceof OpenAI.APIError &&
        ["invalid_base64", "invalid_image_format"].includes(e.code || "")
      ) {
        console.log(
          `OpenAI API Error: ${e.code}. Likely invalid base64 screenshot; retrying without screenshots`
        );

        const messagesWithoutScreenshots = options.messages.map((m) => ({
          ...m,
          content: Array.isArray(m.content)
            ? m.content.filter((c) => c.type !== "image_url")
            : m.content,
        }));

        const completionOptionsWithoutScreenshots = {
          ...completionOptions,
          messages: messagesWithoutScreenshots as ChatCompletionMessageParam[],
        };
        chatCompletion = await openai.chat.completions.create(
          completionOptionsWithoutScreenshots
        );
      } else {
        throw e;
      }
    }

    const inputTokenCount = chatCompletion.usage?.prompt_tokens || 0;
    const outputTokenCount = chatCompletion.usage?.completion_tokens || 0;

    if (options.logApiCall) {
      await createModelApiCallLog(
        options.logApiCall.extractionId,
        Provider.OpenAI,
        ProviderModel.Gpt4o,
        options.logApiCall.callSite,
        inputTokenCount,
        outputTokenCount
      );
    }

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
  }, 10);
}

export async function structuredCompletion<
  T extends ToolCallParameters,
>(options: {
  messages: Array<ChatCompletionMessageParam>;
  schema: JSONSchema;
  model?: ProviderModel;
  requiredParameters?: Array<keyof T>;
  temperature?: number;
  top_p?: number;
  logApiCall?: {
    callSite: string;
    extractionId: number;
  };
}): Promise<{
  result: ToolCallReturn<T> | null;
  inputTokenCount: number;
  outputTokenCount: number;
}> {
  return exponentialRetry(async () => {
    const openai = await getOpenAi();
    let chatCompletion: ChatCompletion;

    const completionOptions: ChatCompletionCreateParams = {
      messages: options.messages,
      model: options.model || ProviderModel.Gpt4o,
      temperature: options?.temperature ?? 1,
      top_p: options?.top_p ?? 1,
      frequency_penalty: 0,
      presence_penalty: 0,
      response_format: {
        type: "json_schema",
        json_schema: {
          strict: true,
          name: "schema",
          schema: options.schema,
        },
      } as any,
    };

    try {
      if (options.model === ProviderModel.O3Mini) {
        // @ts-ignore
        completionOptions.messages = completionOptions.messages.map((m) => ({
          ...m,
          content: Array.isArray(m.content)
            ? m.content.filter((c) => c.type !== "image_url")
            : m.content,
        }));
      }

      chatCompletion = (await openai.chat.completions.create(
        completionOptions
      )) as ChatCompletion;
    } catch (e) {
      if (
        e instanceof OpenAI.APIError &&
        ["invalid_base64", "invalid_image_format"].includes(e.code || "")
      ) {
        console.log(
          `OpenAI API Error: ${e.code}. Likely invalid base64 screenshot; retrying without screenshots`
        );

        const messagesWithoutScreenshots = completionOptions.messages.map(
          (m) => ({
            ...m,
            content: Array.isArray(m.content)
              ? m.content.filter((c) => c.type !== "image_url")
              : m.content,
          })
        );

        const completionOptionsWithoutScreenshots = {
          ...completionOptions,
          messages: messagesWithoutScreenshots as ChatCompletionMessageParam[],
        };
        chatCompletion = (await openai.chat.completions.create(
          completionOptionsWithoutScreenshots
        )) as ChatCompletion;
      } else {
        throw e;
      }
    }

    const inputTokenCount = chatCompletion.usage?.prompt_tokens || 0;
    const outputTokenCount = chatCompletion.usage?.completion_tokens || 0;

    if (options.logApiCall) {
      await createModelApiCallLog(
        options.logApiCall.extractionId,
        Provider.OpenAI,
        ProviderModel.Gpt4o,
        options.logApiCall.callSite,
        inputTokenCount,
        outputTokenCount
      );
    }

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
  }, 10);
}

export function assertBool(obj: Record<string, unknown>, key: string) {
  const value = obj[key];
  if (typeof value == "string") {
    if (["yes", "true"].includes(value.toLowerCase())) {
      return true;
    }
    if (["no", "false", "null"].includes(value.toLowerCase())) {
      return false;
    }
    throw new BadToolCallResponseError(
      `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
    );
  }
  if (typeof value == "boolean") {
    return value;
  }
  throw new BadToolCallResponseError(
    `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
  );
}

export function assertString(obj: Record<string, unknown>, key: string) {
  const value = obj[key];
  if (typeof value !== "string") {
    throw new BadToolCallResponseError(
      `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
    );
  }
  return value;
}

export function assertStringEnum<T extends string>(
  obj: Record<string, unknown>,
  key: string,
  values: readonly T[]
): T {
  const value = assertString(obj, key);
  if (!values.includes(value as T)) {
    throw new BadToolCallResponseError(
      `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
    );
  }
  return value as T;
}

export function assertNumber(
  obj: Record<string, unknown>,
  key: string
): number {
  const value = obj[key];
  if (typeof value === "string") {
    if (!value.match(/^\d+$/)) {
      throw new BadToolCallResponseError(
        `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
      );
    }
    return parseInt(value, 10);
  }
  if (typeof value !== "number") {
    throw new BadToolCallResponseError(
      `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
    );
  }
  return value;
}

export function assertArray<T>(obj: Record<string, unknown>, key: string): T[] {
  const value = obj[key];
  if (Array.isArray(value)) {
    return value as T[];
  }
  throw new BadToolCallResponseError(
    `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
  );
}
