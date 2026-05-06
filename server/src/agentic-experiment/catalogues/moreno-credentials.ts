// session: 3c49b16f-46d0-491b-9dd1-033d94000d14

import { CatalogueType, ProviderModel } from "../../../../common/types";
import { AgentModel } from "../agentModels";
import {
  runAgenticExperiment,
  type AgenticCatalogueRunOptions,
  type AgenticExperimentOptions,
} from "../run";

export const morenoExperimentOptions: AgenticExperimentOptions = {
  targetUrl: "https://rccd.curriqunet.com/Catalog/archive/70/iq/3247/3263",
  catalogueType: CatalogueType.CREDENTIALS,
  modelOverride: ProviderModel.Gpt54Mini,
  agentModel: AgentModel.Sonnet,
  extraInstructions:
    "Select Degrees and Certificate Programs from the left navigation, then make sure to select the Degrees and Certificate Index tab and click each one to get the degree details (end page).",
};

export default function runmorenoExperiment(options?: AgenticCatalogueRunOptions) {
  return runAgenticExperiment({
    ...morenoExperimentOptions,
    configName: options?.configName ?? "moreno",
    extraInstructions: [
      morenoExperimentOptions.extraInstructions,
      options?.extraInstructions,
    ]
      .filter(Boolean)
      .join(" "),
    resumeSession: options?.resumeSession,
    resumeFile: options?.resumeFile,
  });
}

if (require.main === module) {
  runmorenoExperiment().catch((err) => {
    console.error(err);
    process.exitCode = 1;
  });
}
