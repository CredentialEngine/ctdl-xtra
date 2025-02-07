import db from "../data";

export async function findOrgsByUser(userId: number) {
  return db.query.orgsUsers.findMany({
    where(fields, { eq }) {
      return eq(fields?.userId, userId)
    },
  });
}