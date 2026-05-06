import { CatalogueType, ProviderModel } from "../../../../common/types";
import { AgentModel } from "../agentModels";
import {
  runAgenticExperiment,
  type AgenticCatalogueRunOptions,
  type AgenticExperimentOptions,
} from "../run";

export const antelopeCourseCompetenciesExperimentOptions: AgenticExperimentOptions =
  {
    targetUrl: "https://avc.elumenapp.com/public/",
    catalogueType: CatalogueType.COMPETENCIES,
    modelOverride: ProviderModel.Gpt54,
    agentModel: AgentModel.Sonnet,
    extraInstructions:
      "Go through each department on the left, then select the each program from the programs section (ignore the courses section), " +
      "after clicking the program, click the Program Outline Report and register the entire page content" +
      " of the section to the xTRA tool.",
  };

export default function runAntelopeCourseCompetenciesExperiment(
  options?: AgenticCatalogueRunOptions
) {
  return runAgenticExperiment({
    ...antelopeCourseCompetenciesExperimentOptions,
    configName: options?.configName ?? "antelope-course-competencies",
    extraInstructions: [
      antelopeCourseCompetenciesExperimentOptions.extraInstructions,
      options?.extraInstructions,
    ]
      .filter(Boolean)
      .join(" "),
    resumeSession: options?.resumeSession,
    resumeFile: options?.resumeFile,
  });
}

if (require.main === module) {
  runAntelopeCourseCompetenciesExperiment().catch((err) => {
    console.error(err);
    process.exitCode = 1;
  });
}
