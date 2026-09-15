import { providerForModel } from "../../../common/modelMetadata";
import { Provider, ProviderModel } from "../../../common/types";
import { createModelApiCallLog } from "../data/extractions";
import { exponentialRetry } from "../utils";
import { anthropicAdapter } from "./anthropicAdapter";
import { openaiAdapter } from "./openaiAdapter";
import {
  LLMProviderApi,
  LlmProviderAdapter,
  SimpleToolCompletionOptions,
  SimpleToolCompletionResult,
  StructuredCompletionOptions,
  StructuredCompletionResult,
  ToolCallParameters,
} from "./types";

export { estimateCost } from "./pricing";
export type {
  LLMProviderApi,
  LlmContentPart,
  LlmMessage,
  SimpleToolCompletionOptions,
  StructuredCompletionOptions,
  ToolCallParameters,
  ToolCallReturn,
} from "./types";

async function logCompletion(
  provider: Provider,
  options: {
    model?: ProviderModel;
    logApiCall?: SimpleToolCompletionOptions["logApiCall"];
  },
  usage: { inputTokenCount: number; outputTokenCount: number }
) {
  if (!options.logApiCall) {
    return;
  }
  await createModelApiCallLog(
    options.logApiCall.extractionId,
    provider,
    options.model || ProviderModel.Gpt5,
    options.logApiCall.callSite,
    usage.inputTokenCount,
    usage.outputTokenCount,
    {
      datasetId: options.logApiCall.datasetId,
      crawlPageId: options.logApiCall.crawlPageId,
    }
  );
}

function wrapAdapter(adapter: LlmProviderAdapter): LLMProviderApi {
  return {
    async simpleToolCompletion<T extends ToolCallParameters>(
      options: SimpleToolCompletionOptions<T>
    ): Promise<SimpleToolCompletionResult<T>> {
      return exponentialRetry(async () => {
        const result = await adapter.simpleToolCompletion(options);
        await logCompletion(adapter.provider, options, result);
        return result;
      }, 10);
    },
    async structuredCompletion<T extends ToolCallParameters>(
      options: StructuredCompletionOptions<T>
    ): Promise<StructuredCompletionResult<T>> {
      return exponentialRetry(async () => {
        const result = await adapter.structuredCompletion(options);
        await logCompletion(adapter.provider, options, result);
        return result;
      }, 10);
    },
  };
}

export function getLLMProviderApi(model?: ProviderModel): LLMProviderApi {
  const selectedModel = model || ProviderModel.Gpt5;
  const provider = providerForModel(selectedModel);
  const adapter =
    provider === Provider.Anthropic ? anthropicAdapter : openaiAdapter;
  return wrapAdapter(adapter);
}

export async function simpleToolCompletion<T extends ToolCallParameters>(
  options: SimpleToolCompletionOptions<T>
): Promise<SimpleToolCompletionResult<T>> {
  return getLLMProviderApi(options.model).simpleToolCompletion(options);
}

export async function structuredCompletion<T extends ToolCallParameters>(
  options: StructuredCompletionOptions<T>
): Promise<StructuredCompletionResult<T>> {
  return getLLMProviderApi(options.model).structuredCompletion(options);
}
