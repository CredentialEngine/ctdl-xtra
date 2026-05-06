import { CatalogueType, ProviderModel } from "../../../../common/types";
import { AgentModel } from "../agentModels";
import {
  runAgenticExperiment,
  type AgenticCatalogueRunOptions,
  type AgenticExperimentOptions,
} from "../run";

export const morenoExperimentOptions: AgenticExperimentOptions = {
  targetUrl: "https://bcc.curriqunet.com/catalog/view/",
  catalogueType: CatalogueType.COMPETENCIES,
  modelOverride: ProviderModel.Gpt54Mini,
  agentModel: AgentModel.Sonnet,
  extraInstructions:
    "Select Degrees and Certificate Programs from the left navigation, then make sure to select the Degrees and Certificate Index tab and click each one to get the program details (end page).",
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
