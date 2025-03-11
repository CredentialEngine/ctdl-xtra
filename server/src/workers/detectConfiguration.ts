import {
  createProcessor,
  DetectConfigurationJob,
  DetectConfigurationProgress,
} from ".";
import { CatalogueType, RecipeDetectionStatus } from "../../../common/types";
import { findRecipeById, updateRecipe } from "../data/recipes";
import { sendEmailToAll } from "../email";
import DetectConfigurationFail from "../emails/detectConfigurationFail";
import DetectConfigurationSuccess from "../emails/detectConfigurationSuccess";
import recursivelyDetectConfiguration from "../extraction/recursivelyDetectConfiguration";

export default createProcessor<
  DetectConfigurationJob,
  DetectConfigurationProgress
>(async function detectConfiguration(job) {
  const recipe = await findRecipeById(job.data.recipeId);
  if (!recipe) {
    throw new Error(`Recipe with ID ${job.data.recipeId} not found`);
  }
  await updateRecipe(recipe.id, {
    status: RecipeDetectionStatus.IN_PROGRESS,
  });
  try {
    const configuration = await recursivelyDetectConfiguration(
      recipe.url,
      recipe.catalogue.catalogueType as CatalogueType
    );
    await updateRecipe(recipe.id, {
      configuration,
      status: RecipeDetectionStatus.SUCCESS,
    });
    sendEmailToAll(
      DetectConfigurationSuccess,
      {
        catalogueId: recipe.catalogueId,
        recipeId: recipe.id,
        url: recipe.url,
      },
      `Recipe configuration detection #${recipe.id} is complete`
    );
  } catch (err: unknown) {
    let detectionFailureReason =
      err instanceof Error ? err.message : "Unknown error";
    await updateRecipe(recipe.id, {
      detectionFailureReason,
      status: RecipeDetectionStatus.ERROR,
    });
    if (job.attemptsStarted == job.opts.attempts) {
      sendEmailToAll(
        DetectConfigurationFail,
        {
          catalogueId: recipe.catalogueId,
          recipeId: recipe.id,
          url: recipe.url,
          reason: detectionFailureReason,
        },
        `Recipe configuration detection #${recipe.id} has failed`
      );
    }
    throw err;
  }
});
