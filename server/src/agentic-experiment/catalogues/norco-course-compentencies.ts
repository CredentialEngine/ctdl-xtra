import { CatalogueType, ProviderModel } from "../../../../common/types";
import { AgentModel } from "../agentModels";
import {
  runAgenticExperiment,
  type AgenticCatalogueRunOptions,
  type AgenticExperimentOptions,
} from "../run";

export const norcoExperimentOptions: AgenticExperimentOptions = {
  targetUrl: "https://rccd.curriqunet.com/",
  catalogueType: CatalogueType.COMPETENCIES,
  modelOverride: ProviderModel.Gpt54Mini,
  agentModel: AgentModel.Sonnet,
  extraInstructions:
    "Click Search, this shows a paginated list of courses. We will have to traverse all pages. For each Course that has Status = Active, click the \'Records\' button and from the dropdown that appears, select Course Outline. The page that opens is the final page you should submit the content of.",
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
