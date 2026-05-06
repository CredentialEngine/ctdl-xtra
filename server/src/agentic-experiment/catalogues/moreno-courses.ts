//session: 2ddf8544-06f6-43a3-85bd-66acff4e62bc

import { CatalogueType, ProviderModel } from "../../../../common/types";
import { AgentModel } from "../agentModels";
import {
  runAgenticExperiment,
  type AgenticCatalogueRunOptions,
  type AgenticExperimentOptions,
} from "../run";

export const morenoExperimentOptions: AgenticExperimentOptions = {
  targetUrl: "https://rccd.curriqunet.com/catalog/alias/mvc-catalog/iq/4701/5015",
  catalogueType: CatalogueType.COURSES,
  modelOverride: ProviderModel.Gpt54Mini,
  agentModel: AgentModel.Sonnet,
  extraInstructions:
    "Make sure to select the Courses Index tab and click each one to get the course details (end page).",
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
