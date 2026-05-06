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
      "Go through each department on the left, then select the each course from the course section (ignore the programs section), " +
      "after clicking the course, click the Course Outline Report and find the Learning Outcomes and Objectives section, register the entire page content" +
      " to the xTRA tool.",
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
