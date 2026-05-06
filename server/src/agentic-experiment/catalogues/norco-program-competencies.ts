import { CatalogueType, ProviderModel } from "../../../../common/types";
import { AgentModel } from "../agentModels";
import {
  runAgenticExperiment,
  type AgenticCatalogueRunOptions,
  type AgenticExperimentOptions,
} from "../run";

export const norcoExperimentOptions: AgenticExperimentOptions = {
  targetUrl: "https://rccd.curriqunet.com/catalog/alias/nc-catalog/iq/5358",
  catalogueType: CatalogueType.COMPETENCIES,
  modelOverride: ProviderModel.Gpt54Mini,
  agentModel: AgentModel.Sonnet,
  extraInstructions:
    "Select Degrees and Certificate Programs from the left navigation, then make sure to select the Degrees and Certificate Index tab and click each one to get the program details (end page).",
};

export default function runnorcoExperiment(options?: AgenticCatalogueRunOptions) {
  return runAgenticExperiment({
    ...norcoExperimentOptions,
    configName: options?.configName ?? "norco",
    extraInstructions: [
      norcoExperimentOptions.extraInstructions,
      options?.extraInstructions,
    ]
      .filter(Boolean)
      .join(" "),
    resumeSession: options?.resumeSession,
    resumeFile: options?.resumeFile,
  });
}

if (require.main === module) {
  runnorcoExperiment().catch((err) => {
    console.error(err);
    process.exitCode = 1;
  });
}
