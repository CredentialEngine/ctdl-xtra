import {
  CourseStructuredData,
  PageType,
  RecipeConfiguration,
} from "@common/types";
import { router } from "./routers";
import { cataloguesRouter } from "./routers/catalogues";
import { datasetsRouter } from "./routers/datasets";
import { extractionsRouter } from "./routers/extractions";
import { recipesRouter } from "./routers/recipes";
import { settingsRouter } from "./routers/settings";
import { usersRouter } from "./routers/users";
import { DetectConfigurationProgress } from "./workers";

const appRouter = router({
  catalogues: cataloguesRouter,
  datasets: datasetsRouter,
  settings: settingsRouter,
  recipes: recipesRouter,
  extractions: extractionsRouter,
  users: usersRouter,
});

export { appRouter };

export type {
  CourseStructuredData,
  DetectConfigurationProgress,
  PageType as PAGE_DATA_TYPE,
  RecipeConfiguration,
};

export type AppRouter = typeof appRouter;
