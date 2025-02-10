import { InferSelectModel } from "drizzle-orm";
import { orgs } from "./schema";

export type Organizations = InferSelectModel<typeof orgs>;