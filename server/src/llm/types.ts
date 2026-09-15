import { JSONSchema } from "../../../common/catalogueTypes";
import { Provider, ProviderModel } from "../../../common/types";

export type LlmImageMediaType = "image/webp" | "image/png" | "image/jpeg";

export type LlmContentPart =
  | { type: "text"; text: string }
  | { type: "image"; mediaType: LlmImageMediaType; data: string };

export interface LlmMessage {
  role: "system" | "user" | "assistant";
  content: string | LlmContentPart[];
}

export type ToolCallParameters = Record<string, unknown>;

export type ToolCallReturn<T extends ToolCallParameters> = {
  [key in keyof T]: unknown;
};

export interface LogApiCallOptions {
  callSite: string;
  extractionId: number;
  datasetId?: number;
  crawlPageId?: number;
}

export interface CompletionUsage {
  inputTokenCount: number;
  outputTokenCount: number;
}

export interface BaseCompletionOptions {
  messages: LlmMessage[];
  model?: ProviderModel;
  temperature?: number;
  top_p?: number;
  logApiCall?: LogApiCallOptions;
}

export interface SimpleToolCompletionOptions<
  T extends ToolCallParameters = ToolCallParameters,
> extends BaseCompletionOptions {
  toolName: string;
  parameters: T;
  requiredParameters?: Array<keyof T>;
}

export interface StructuredCompletionOptions<
  T extends ToolCallParameters = ToolCallParameters,
> extends BaseCompletionOptions {
  schema: JSONSchema;
  requiredParameters?: Array<keyof T>;
}

export interface SimpleToolCompletionResult<T extends ToolCallParameters> {
  toolCallArgs: ToolCallReturn<T> | null;
  inputTokenCount: number;
  outputTokenCount: number;
}

export interface StructuredCompletionResult<T extends ToolCallParameters> {
  result: ToolCallReturn<T> | null;
  inputTokenCount: number;
  outputTokenCount: number;
}

export interface LLMProviderApi {
  simpleToolCompletion<T extends ToolCallParameters>(
    options: SimpleToolCompletionOptions<T>
  ): Promise<SimpleToolCompletionResult<T>>;

  structuredCompletion<T extends ToolCallParameters>(
    options: StructuredCompletionOptions<T>
  ): Promise<StructuredCompletionResult<T>>;
}

export interface LlmProviderAdapter {
  readonly provider: Provider;
  simpleToolCompletion<T extends ToolCallParameters>(
    options: SimpleToolCompletionOptions<T>
  ): Promise<SimpleToolCompletionResult<T>>;
  structuredCompletion<T extends ToolCallParameters>(
    options: StructuredCompletionOptions<T>
  ): Promise<StructuredCompletionResult<T>>;
}

export type ErrorWithRetryFlag = Error & { noRetry?: boolean };

export function markNoRetry(error: unknown, noRetry: boolean): unknown {
  if (error instanceof Error) {
    (error as ErrorWithRetryFlag).noRetry = noRetry;
  }
  return error;
}

export function stripImageParts(messages: LlmMessage[]): LlmMessage[] {
  return messages.map((message) => ({
    ...message,
    content: Array.isArray(message.content)
      ? message.content.filter((part) => part.type !== "image")
      : message.content,
  }));
}
