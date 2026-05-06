import { CatalogueType, ProviderModel } from "../../../../common/types";
import { AgentModel } from "../agentModels";
import {
  runAgenticExperiment,
  type AgenticCatalogueRunOptions,
  type AgenticExperimentOptions,
} from "../run";

export const berkleyExperimentOptions: AgenticExperimentOptions = {
  targetUrl: "https://bcc.curriqunet.com/catalog/view//iq/29087/29366",
  catalogueType: CatalogueType.COMPETENCIES,
  modelOverride: ProviderModel.Gpt54Mini,
  agentModel: AgentModel.Sonnet,
  extraInstructions:
    "Select Degrees and Certificate Programs from the left navigation, then make sure to select the Degrees and Certificate Index tab and click each one to get the degree details (end page).",
};

export default function runBerkleyExperiment(options?: AgenticCatalogueRunOptions) {
  return runAgenticExperiment({
    ...berkleyExperimentOptions,
    configName: options?.configName ?? "berkley",
    extraInstructions: [
      berkleyExperimentOptions.extraInstructions,
      options?.extraInstructions,
    ]
      .filter(Boolean)
      .join(" "),
    resumeSession: options?.resumeSession,
    resumeFile: options?.resumeFile,
  });
}

if (require.main === module) {
  runBerkleyExperiment().catch((err) => {
    console.error(err);
    process.exitCode = 1;
  });
}
