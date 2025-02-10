import { eq } from 'drizzle-orm'

import db from "../data";
import { memberships, orgs } from "./schema";

export async function findOrgsByUser(userId: number) {
  return db.selectDistinct()
    .from(orgs)
    .innerJoin(memberships, eq(memberships.userId, userId))
}