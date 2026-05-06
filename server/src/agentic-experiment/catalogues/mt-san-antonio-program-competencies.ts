// session: 3c49b16f-46d0-491b-9dd1-033d94000d14

import { CatalogueType, ProviderModel } from "../../../../common/types";
import { AgentModel } from "../agentModels";
import {
  runAgenticExperiment,
  type AgenticCatalogueRunOptions,
  type AgenticExperimentOptions,
} from "../run";

export const mtSanAntonioExperimentOptions: AgenticExperimentOptions = {
  targetUrl: "https://www.mtsac.edu/slo/",
  catalogueType: CatalogueType.COMPETENCIES,
  modelOverride: ProviderModel.Gpt54Mini,
  agentModel: AgentModel.Sonnet,
  extraInstructions:
    "Follow each program displayed in the left navigation (you will need to follow the pages at the bottom, use clicks because pages are dynamic) and once you click each program and reach the program detail page, you need to navigate the pages of program courses table submit the entire content of all the pages to the xTRA tool. Do not leave anything out, except for banners, footers and navigation bars.",
};

export default function runmtSanAntonioExperiment(options?: AgenticCatalogueRunOptions) {
  return runAgenticExperiment({
    ...mtSanAntonioExperimentOptions,
    configName: options?.configName ?? "mtSanAntonio",
    extraInstructions: [
      mtSanAntonioExperimentOptions.extraInstructions,
      options?.extraInstructions,
    ]
      .filter(Boolean)
      .join(" "),
    resumeSession: options?.resumeSession,
    resumeFile: options?.resumeFile,
  });
}

if (require.main === module) {
  runmtSanAntonioExperiment().catch((err) => {
    console.error(err);
    process.exitCode = 1;
  });
}
