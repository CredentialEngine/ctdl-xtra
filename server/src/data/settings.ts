import db from "../data";
import { encryptForDb, settings } from "../data/schema";

export async function findSettings(orgId: number) {
  return db.query.settings.findMany({
    where(fields, { eq }) {
      return eq(fields?.orgId, orgId)
    },
  });
}

export async function createOrUpdate(
  key: string,
  value: string,
  isEncrypted: boolean = false,
  encryptedPreview: string | null,
  orgId: number,
) {
  value = isEncrypted ? encryptForDb(value) : value;
  return db
    .insert(settings)
    .values({
      key,
      value,
      isEncrypted,
      encryptedPreview,
      orgId,
    })
    .onConflictDoUpdate({
      target: settings.key,
      set: { value, isEncrypted, encryptedPreview },
    });
}
