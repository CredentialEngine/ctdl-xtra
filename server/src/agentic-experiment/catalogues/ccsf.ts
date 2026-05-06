import { CatalogueType, ProviderModel } from "../../../../common/types";
import {
  runAgenticExperiment,
  type AgenticCatalogueRunOptions,
  type AgenticExperimentOptions,
} from "../run";

export const ccsfExperimentOptions: AgenticExperimentOptions = {
  targetUrl:
    "https://www.ccsf.edu/academics/ccsf-catalog/courses-by-department",
  catalogueType: CatalogueType.COMPETENCIES,
  modelOverride: ProviderModel.Gpt5,
  extraInstructions:
    "PROGRAM Competencies are within the page holding the credential information. If you click on a program area, then the credential, it is on that layer under \"Learning Outcomes\"",
};

export default function runCcsfExperiment(options?: AgenticCatalogueRunOptions) {
  return runAgenticExperiment({
    ...ccsfExperimentOptions,
    configName: options?.configName ?? "ccsf",
    extraInstructions: [
      ccsfExperimentOptions.extraInstructions,
      options?.extraInstructions,
    ]
      .filter(Boolean)
      .join(" "),
    resumeSession: options?.resumeSession,
    resumeFile: options?.resumeFile,
  });
}

if (require.main === module) {
  runCcsfExperiment().catch((err) => {
    console.error(err);
    process.exitCode = 1;
  });
}
